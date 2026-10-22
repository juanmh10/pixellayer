#!/usr/bin/env python3
"""Promote a reviewed Windows archive; never build or execute the engine."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPO = 'juanmh10/pixellayer'
PROJECT = 'website-prod-juan'
BUCKET = 'pixellayer-prod-downloads-website-prod-juan'
BASE = f'https://storage.googleapis.com/{BUCKET}'
VERSION_RE = re.compile(r'0|[1-9][0-9]*')


def version_tuple(version):
    parts = version.split('.')
    if len(parts) != 3 or not all(VERSION_RE.fullmatch(p) for p in parts):
        raise ValueError('Expected a stable MAJOR.MINOR.PATCH version')
    return tuple(map(int, parts))


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def encoded(value):
    return urllib.parse.quote(value, safe='')


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def public_bytes(url):
    for attempt in range(5):
        try:
            request = urllib.request.Request(url, headers={'Cache-Control': 'no-cache'})
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError):
            if attempt == 4:
                raise RuntimeError('Public download verification failed') from None
            time.sleep(2 ** attempt)


def verify(directory, approval):
    archive = directory / approval['archive']
    data = archive.read_bytes()
    if len(data) != approval['size_bytes'] or digest(data) != approval['sha256']:
        raise ValueError('Archive does not match committed approval')
    checksum = directory / (archive.name + '.sha256')
    if checksum.read_text().strip() != f"{approval['sha256']}  {archive.name}":
        raise ValueError('Checksum file does not match committed approval')
    prefix = f"pixellayer-{approval['version']}-windows-x64/"
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or any(i.is_dir() for i in z.infolist()):
            raise ValueError('Duplicate or unexpected ZIP entries')
        files = {}
        for name in names:
            p = PurePosixPath(name)
            if not name.startswith(prefix) or '\\' in name or ':' in name or '..' in p.parts:
                raise ValueError('Unsafe ZIP path')
            relative = name[len(prefix):]
            if not relative or relative.startswith(('skill/', 'src/', '.github/')):
                raise ValueError('Unapproved package content')
            if sum(i.file_size for i in z.infolist()) > 150_000_000:
                raise ValueError('Unexpected expanded package size')
            files[relative] = z.read(name)
        raw = files.pop('manifest.json')
        if digest(raw) != approval['package_manifest_sha256']:
            raise ValueError('Package manifest differs from approval')
        manifest = json.loads(raw)
        if (manifest['version'] != approval['version']
                or manifest['target'] != 'x86_64-pc-windows-msvc'
                or manifest['source_dirty'] is not False
                or manifest['source_commit'] != approval['engine_commit']
                or manifest['engine_commit'] != approval['engine_commit']
                or manifest['distribution'] != 'public-windows-v1'):
            raise ValueError('Unexpected package provenance')
        listed = [entry['path'] for entry in manifest['files']]
        if len(listed) != len(set(listed)) or set(listed) != set(files):
            raise ValueError('Package inventory differs from manifest')
        for entry in manifest['files']:
            payload = files[entry['path']]
            if len(payload) != entry['size_bytes'] or digest(payload) != entry['sha256']:
                raise ValueError('Package file integrity failure')
        required = {'pixellayer.exe', 'onnxruntime.dll', 'install.ps1', 'setup.ps1',
                    'verify.ps1', 'uninstall.ps1', 'README.md'}
        if not required.issubset(files):
            raise ValueError('Package lacks required files')
    print(f"Verified approved Windows package: {len(data)} bytes, SHA-256 {approval['sha256']}")


class Storage:
    def __init__(self):
        # Captured in memory only. Never print the access token or request headers.
        self.token = run('gcloud', 'auth', 'print-access-token', f'--project={PROJECT}')

    def request(self, method, url, data=None, content_type='application/json', missing_ok=False):
        request = urllib.request.Request(url, data=data, method=method, headers={
            'Authorization': 'Bearer ' + self.token, 'Content-Type': content_type})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as error:
            if missing_ok and error.code == 404:
                return None
            raise RuntimeError(f'GCS {method} failed with HTTP {error.code}') from None

    def object_url(self, name):
        return f'https://storage.googleapis.com/storage/v1/b/{BUCKET}/o/{encoded(name)}'

    def get(self, name):
        return self.request('GET', self.object_url(name), missing_ok=True)

    def metadata(self, name, metadata):
        current = self.get(name)
        if current is None:
            raise ValueError('Cannot update missing object')
        url = self.object_url(name) + '?ifMetagenerationMatch=' + current['metageneration']
        self.request('PATCH', url, json_bytes(metadata))

    def put(self, name, data, content_type, immutable=True, expected_generation=None):
        current = self.get(name)
        if current and immutable:
            if public_bytes(f'{BASE}/{name}') != data:
                raise ValueError('Refusing to replace an immutable release object')
            return
        generation = current['generation'] if current else '0'
        if expected_generation is not None and generation != expected_generation:
            raise ValueError('Object generation changed; refusing replacement')
        metadata = {'name': name, 'contentType': content_type,
                    'cacheControl': 'public,max-age=31536000,immutable' if immutable else 'no-cache,max-age=0',
                    'temporaryHold': immutable}
        boundary = 'pixellayer-publication-boundary'
        body = (f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'.encode()
                + json_bytes(metadata)
                + f'\r\n--{boundary}\r\nContent-Type: {content_type}\r\n\r\n'.encode()
                + data + f'\r\n--{boundary}--\r\n'.encode())
        query = urllib.parse.urlencode({'uploadType': 'multipart', 'ifGenerationMatch': generation})
        self.request('POST', f'https://storage.googleapis.com/upload/storage/v1/b/{BUCKET}/o?{query}',
                     body, f'multipart/related; boundary={boundary}')

    def objects(self):
        result = []
        page = None
        while True:
            query = {'prefix': 'releases/', 'maxResults': '1000'}
            if page:
                query['pageToken'] = page
            response = self.request('GET', f'https://storage.googleapis.com/storage/v1/b/{BUCKET}/o?'
                                    + urllib.parse.urlencode(query))
            result.extend(response.get('items', []))
            page = response.get('nextPageToken')
            if not page:
                return result


def maintain_retention(storage, timestamp):
    objects = storage.objects()
    versions = set()
    for item in objects:
        parts = item['name'].split('/')
        if len(parts) == 3 and parts[2] == 'release.json':
            version_tuple(parts[1])
            versions.add(parts[1])
    protected = set(sorted(versions, key=version_tuple, reverse=True)[:3])
    for item in objects:
        parts = item['name'].split('/')
        if len(parts) != 3 or parts[1] not in versions:
            raise ValueError('Unexpected release layout; refusing retirement')
        if parts[1] in protected:
            if not item.get('temporaryHold', False):
                storage.metadata(item['name'], {'temporaryHold': True})
        else:
            patch = {'temporaryHold': False}
            if not item.get('customTime'):
                patch['customTime'] = timestamp
            storage.metadata(item['name'], patch)
    print(f'Retention: protecting {len(protected)} stable releases')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'publish', 'verify'])
    parser.add_argument('--version', required=True)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    version_tuple(args.version)
    approval = json.loads((Path(__file__).parent / 'manifests' / f'{args.version}.json').read_text())
    if approval['version'] != args.version or approval['platform'] != 'windows-x64':
        raise ValueError('Wrong release approval')
    if approval['archive'] != f'pixellayer-{args.version}-windows-x64.zip':
        raise ValueError('Invalid approved archive name')
    directory = args.directory
    directory.mkdir(parents=True, exist_ok=True)
    tag = 'v' + args.version
    if args.mode == 'verify':
        verify(directory, approval)
        return
    candidates = []
    page_number = 1
    while True:
        page = json.loads(run('gh', 'api', f'repos/{REPO}/releases?per_page=100&page={page_number}'))
        candidates.extend(item for item in page if item['tag_name'] == tag)
        if len(page) < 100:
            break
        page_number += 1
    if len(candidates) != 1:
        raise ValueError('Expected exactly one matching draft or published release')
    release = candidates[0]
    if release['tag_name'] != tag or release['prerelease']:
        raise ValueError('Expected stable release candidate')
    expected = {approval['archive'], approval['archive'] + '.sha256'}
    actual = {asset['name'] for asset in release['assets']}
    if not expected.issubset(actual) or actual - expected - {'release.json'}:
        raise ValueError('Draft assets differ from approved public inventory')
    if args.mode == 'prepare':
        for name in sorted(expected):
            subprocess.run(['gh', 'release', 'download', tag, '--repo', REPO,
                            '--pattern', name, '--dir', str(directory), '--clobber'], check=True)
        verify(directory, approval)
        return
    verify(directory, approval)
    storage = Storage()
    old_pointer = storage.get('channels/stable.json')
    if old_pointer:
        old = json.loads(public_bytes(BASE + '/channels/stable.json'))
        if version_tuple(old['version']) > version_tuple(args.version):
            raise ValueError('Refusing a stable channel downgrade')
    name = approval['archive']
    prefix = f'releases/{args.version}'
    manifest = {'schema_version': 1, 'version': args.version, 'channel': 'stable',
                'published_at': release['created_at'], 'engine_commit': approval['engine_commit'],
                'packages': {'windows-x64': {
                    'filename': name, 'size_bytes': approval['size_bytes'], 'sha256': approval['sha256'],
                    'url': f'{BASE}/{prefix}/{name}',
                    'fallback_url': f'https://github.com/{REPO}/releases/download/{tag}/{name}',
                    'package_manifest_sha256': approval['package_manifest_sha256']}}}
    manifest_data = json_bytes(manifest)
    for filename, content_type in [(name, 'application/zip'), (name + '.sha256', 'text/plain')]:
        content = (directory / filename).read_bytes()
        storage.put(f'{prefix}/{filename}', content, content_type)
        if public_bytes(f'{BASE}/{prefix}/{filename}') != content:
            raise ValueError('Anonymous GCS verification failed')
    storage.put(f'{prefix}/release.json', manifest_data, 'application/json')
    if public_bytes(f'{BASE}/{prefix}/release.json') != manifest_data:
        raise ValueError('Public release manifest verification failed')
    local_manifest = directory / 'release.json'
    local_manifest.write_bytes(manifest_data)
    if 'release.json' in actual:
        subprocess.run(['gh', 'release', 'download', tag, '--repo', REPO, '--pattern', 'release.json',
                        '--dir', str(directory / 'existing'), '--clobber'], check=True)
        if (directory / 'existing/release.json').read_bytes() != manifest_data:
            raise ValueError('GitHub release manifest differs')
    else:
        subprocess.run(['gh', 'release', 'upload', tag, str(local_manifest), '--repo', REPO], check=True)
    if release['draft']:
        subprocess.run(['gh', 'release', 'edit', tag, '--repo', REPO, '--draft=false', '--latest'], check=True)
    if digest(public_bytes(manifest['packages']['windows-x64']['fallback_url'])) != approval['sha256']:
        raise ValueError('Anonymous GitHub verification failed')
    maintain_retention(storage, datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'))
    # Use the generation seen before publication, preventing a concurrent rollback being overwritten.
    current = storage.get('channels/stable.json')
    if (current or {}).get('generation') != (old_pointer or {}).get('generation'):
        raise ValueError('Stable channel changed during publication; refusing replacement')
    storage.put('channels/stable.json', manifest_data, 'application/json', immutable=False,
                expected_generation=(old_pointer or {}).get('generation', '0'))
    if public_bytes(BASE + '/channels/stable.json') != manifest_data:
        raise ValueError('Stable channel verification failed')
    print(f'Published {tag}: Windows x64 on GCS and GitHub; stable channel verified')


if __name__ == '__main__':
    main()
