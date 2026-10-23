# Releases and distribution

## Download contract

[GitHub Releases](https://github.com/juanmh10/pixellayer/releases) and the public GCS
bucket mirror the approved Windows package and separate skill ZIP. End users do
not need GitHub authentication or the GitHub CLI. The stable pointer is:

`https://storage.googleapis.com/pixellayer-prod-downloads-website-prod-juan/channels/stable.json`

Fixed versions use `releases/VERSION/release.json` under that same HTTPS base.
`schema_version:1` contains `version`, `channel`, source/engine commits,
`packages.windows-x64` and `skill`. Each download entry supplies filename, byte
size, SHA-256, primary URL and GitHub fallback URL. The engine package also has a
`package_manifest_sha256`. Preserve the selected version on fallback; do not
substitute another build or conceal a hash mismatch.

Versioned objects are immutable. The stable pointer is uncached and updated only
after publication/anonymous verification; generation preconditions prevent a
concurrent pointer update from being overwritten. A new default-branch commit
does not automatically replace the released EXE, skill or versioned files.
Rebuilt/revised distributable bytes require a new release version. Documentation
updates outside those archives can be published independently.

## CI and publication controls

The public repository contains three workflows:

| Workflow | Trigger and purpose |
| --- | --- |
| `ci.yml` | Push to `main`/`product/**`, PR to `main`, or manual dispatch: formatting, Clippy, five native builds and package checksums. Changes only under `distribution/manifests/` skip rebuilds. |
| `security.yml` | Push, PR, weekly schedule or manual dispatch: Git integrity, Gitleaks history/files, RustSec dependency audit and workflow lint. |
| `publish-windows.yml` | Manual dispatch on `main` with an approved stable version: verify artifacts, authenticate via Google OIDC, publish and verify downloads. |

Actions are pinned by commit SHA. Build artifacts in GitHub Actions expire after
30 days; those are distinct from the published release downloads. Native targets
are Windows x64, Linux x64/ARM64 and macOS Intel/ARM64. The current public installer
release is Windows x64; other CI builds do not imply validation in every client.

Publication uses a restricted OIDC identity with short-lived credentials rather
than a stored service-account key. Its trust is limited to this repository's
manual publication workflow on `main`. The publisher can manage download objects;
it does not provision buckets, change IAM or change lifecycle configuration.

## Release operator sequence

Publishing requires repository permissions and Google OIDC access; this section
is for release operators, not the end-user installation path.

1. Select a successful public `ci.yml` run and successful `security.yml` run for the
   same full source commit. Preserve the inner Windows/skill ZIPs and checksums as
   produced by CI; an Actions download wrapper is not the native package.
2. Create a draft GitHub release `vVERSION` targeting that source commit. Attach
   exactly the Windows ZIP, skill ZIP and each ZIP's `.sha256` file.
3. Review and commit `distribution/manifests/VERSION.json` with version/platform,
   source and engine commits, `build_run_id`, Windows archive size/hash,
   `package_manifest_sha256`, `executable_sha256`, and the skill's
   version/filename/size/hash. The [0.5.1 approval](../distribution/manifests/0.5.1.json)
   records the published package's exact values. Different packaging/engine commits
   can be legitimate and are checked independently.
4. Run **Publish Windows release** from GitHub Actions on `main`, supplying VERSION.
   It validates the matching successful build/security run and the approved bytes
   before Google authentication. It publishes both ZIPs/checksums and `release.json`
   to GCS, publishes the GitHub draft, verifies anonymous downloads, and then updates
   `channels/stable.json`.
5. Confirm workflow success and that fixed/stable manifests agree for the selected
   version. Do not overwrite an existing version to repair a failed promotion.
   Inspect partial state first; identical immutable objects can be reused.

The publisher accepts stable semantic versions and refuses stable downgrades.
Rollback of the channel requires a separate reviewed operator action using the
current object generation. Previous immutable downloads remain available while
retained; do not rewrite them as a substitute for a rollback.

## Retention

The GCS bucket uses `us-central1`. Publication protects the three most recent
stable versions with temporary holds. Older versions become eligible for lifecycle
deletion 180 days after the publisher marks them retired with `customTime` and
releases the hold. This interval starts at retirement, not initial publication.
Historical prerelease objects have a 30-day age rule. GitHub release assets are
not deleted by the GCS lifecycle. The lifecycle policy is versioned in
[distribution/lifecycle.json](../distribution/lifecycle.json); changing that file
alone does not apply a cloud configuration change.
