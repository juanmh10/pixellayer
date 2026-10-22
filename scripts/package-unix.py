#!/usr/bin/env python3
"""Native Linux/macOS package builder. Python 3.11+ is a maintainer dependency only."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parent.parent
HOSTS = {
    ("Linux", "x86_64"): ("linux-x64", "x86_64-unknown-linux-gnu", "libonnxruntime.so"),
    ("Linux", "aarch64"): ("linux-aarch64", "aarch64-unknown-linux-gnu", "libonnxruntime.so"),
    ("Darwin", "x86_64"): ("osx-x86_64", "x86_64-apple-darwin", "libonnxruntime.dylib"),
    ("Darwin", "arm64"): ("osx-arm64", "aarch64-apple-darwin", "libonnxruntime.dylib"),
}


def run(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    try:
        runtime_platform, target, library = HOSTS[(platform.system(), platform.machine())]
    except KeyError:
        parser.error("Use native Linux glibc or macOS x64/ARM64. Windows has package-windows.ps1.")
    version = tomllib.loads((ROOT / "Cargo.toml").read_text())["package"]["version"]
    name = f"pixellayer-{version}-{runtime_platform}"
    output = args.output_directory.resolve()
    output.mkdir(parents=True, exist_ok=True)
    package = output / name
    archive = output / f"{name}.tar.gz"
    checksum = Path(f"{archive}.sha256")
    if any(p.exists() for p in (package, archive, checksum)):
        parser.error("Output exists. Choose a new --output-directory; packages are not overwritten.")
    with tempfile.TemporaryDirectory(prefix="pixellayer-package-") as temporary:
        staging = Path(temporary)
        # Always download and verify the pinned archive; ignore existing runtime caches.
        subprocess.run(["bash", str(ROOT / "scripts/setup-runtime.sh"), str(staging)], check=True)
        runtime = staging / f"onnxruntime-{runtime_platform}-1.22.0"
        subprocess.run(["cargo", "build", "--release", "--locked", "--target", target], cwd=ROOT, check=True)
        metadata = json.loads(run("cargo", "metadata", "--locked", "--offline", "--filter-platform", target,
                                  "--format-version", "1"))
        contents = staging / name
        contents.mkdir()
        executable = Path(metadata["target_directory"]) / target / "release/pixellayer"
        shutil.copy2(executable, contents / "pixellayer")
        libraries = [p for p in (runtime / "lib").iterdir()
                     if p.is_file() and (".so" in p.name or p.name.endswith(".dylib"))]
        if not any(p.name == library for p in libraries):
            raise RuntimeError(f"Missing runtime library: {library}")
        for source in libraries:
            # Dereference symlinks so every distributed library is covered by checksums.
            shutil.copy2(source, contents / source.name)
        licenses = contents / "licenses"
        licenses.mkdir()
        shutil.copy2(ROOT / "licenses/BiRefNet-MIT.txt", licenses / "BiRefNet-MIT.txt")
        shutil.copy2(ROOT / "licenses/ONNX-Runtime-MIT.txt", licenses / "ONNX-Runtime-MIT.txt")
        shutil.copy2(ROOT / "LICENSE", licenses / "PixelLayer-MIT.txt")
        shutil.copy2(runtime / "LICENSE", licenses / "ONNX-Runtime-MIT.txt")
        shutil.copy2(runtime / "ThirdPartyNotices.txt", licenses / "ONNX-Runtime-ThirdPartyNotices.txt")
        shutil.copy2(ROOT / "Cargo.toml", licenses / "PixelLayer-Cargo.toml")
        (licenses / "PixelLayer.txt").write_text(
            "PixelLayer declares MIT licensing in Cargo.toml. See PixelLayer-MIT.txt when included.\n"
            "Model/runtime and Rust dependency notices retain their own license terms.\n")
        notices = []
        resolved = {n["id"] for n in metadata["resolve"]["nodes"]}
        for dependency in sorted(metadata["packages"], key=lambda p: (p["name"], p["version"])):
            if dependency["name"] == "pixellayer" or dependency["id"] not in resolved:
                continue
            notices.append(f"\n{dependency['name']} {dependency['version']}\n"
                           f"License: {dependency['license']}\nRepository: {dependency['repository']}\n")
            crate = Path(dependency["manifest_path"]).parent
            files = {p for p in crate.rglob("*") if p.is_file() and
                     re.match(r"^(LICENSE|LICENCE|COPYING|COPYRIGHT|NOTICE)([-._].*)?$", p.name)}
            if dependency.get("license_file"):
                files.add(crate / dependency["license_file"])
            for path in sorted(files):
                notices.append(f"--- {path.relative_to(crate)} ---\n{path.read_text(errors='replace')}\n")
        (licenses / "Rust-ThirdPartyNotices.txt").write_text("".join(notices))
        shutil.copy2(ROOT / "packaging/unix/README.md", contents / "README.md")
        shutil.copy2(ROOT / "packaging/unix/verify.sh", contents / "verify.sh")
        shutil.copy2(ROOT / "packaging/unix/install.sh", contents / "install.sh")
        shutil.copy2(ROOT / "packaging/unix/uninstall.sh", contents / "uninstall.sh")
        shutil.copy2(ROOT / "packaging/unix/setup.sh", contents / "setup.sh")
        files = [{"path": p.relative_to(contents).as_posix(), "size_bytes": p.stat().st_size,
                  "sha256": sha(p)} for p in sorted(contents.rglob("*")) if p.is_file()]
        source_dirty = bool(run("git", "status", "--porcelain", "--untracked-files=no"))
        if source_dirty:
            raise RuntimeError("Public release packaging requires a clean tracked source tree")
        manifest = {"name": "pixellayer", "version": version, "target": target,
                    "source_commit": run("git", "rev-parse", "HEAD"),
                    "source_dirty": source_dirty,
                    "distribution": "public-unix-v1",
                    "engine_commit": run("git", "log", "-1", "--format=%H", "--", "rust", "Cargo.toml", "Cargo.lock", "rust-toolchain.toml"),
                    "rustc": run("rustc", "--version"), "onnx_runtime_version": "1.22.0",
                    "model_included": False, "files": files}
        (contents / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        covered = sorted(p for p in contents.rglob("*") if p.is_file())
        (contents / "SHA256SUMS").write_text("".join(
            f"{sha(p)}  {p.relative_to(contents).as_posix()}\n" for p in covered))
        subprocess.run(["bash", str(contents / "verify.sh")], check=True, stdout=subprocess.DEVNULL)
        subprocess.run([str(contents / "pixellayer"), "--version"], check=True)
        shutil.copytree(contents, package)
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(package, arcname=name)
    checksum.write_text(f"{sha(archive)}  {archive.name}\n")
    print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size, "sha256": sha(archive)}))


if __name__ == "__main__":
    main()
