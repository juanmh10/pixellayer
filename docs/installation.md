# Installation

## Requirements and downloads

The public 0.5.1 package targets Windows x64. It includes the engine, ONNX Runtime
CPU 1.22.0 and required native libraries. No Rust, Python, Node, GitHub account or
GitHub CLI is required to use it. Installation is per user.

Use these public sources in order: an existing verified matching installation,
a supplied/cached verified package, GCS, then GitHub for the same version.

- [Stable channel manifest](https://storage.googleapis.com/pixellayer-prod-downloads-website-prod-juan/channels/stable.json)
- [0.5.1 manifest](https://storage.googleapis.com/pixellayer-prod-downloads-website-prod-juan/releases/0.5.1/release.json)
- [GitHub release](https://github.com/juanmh10/pixellayer/releases/tag/v0.5.1)
- [Skill ZIP](https://github.com/juanmh10/pixellayer/releases/download/v0.5.1/pixellayer-skill-0.5.1.zip)

The manifest provides filenames, sizes, SHA-256 values, the package manifest hash,
source/engine commits and fallback URLs. On an unavailable origin, use its listed
fallback. An integrity mismatch stops installation; changing origins is not a way
to accept different bytes. Keep HTTPS verification enabled.

## Verify and install on Windows

Run PowerShell in a download folder outside the image workspace. The destination
folder below must not already exist. Replace the image workspace with your actual
existing directory and select the client you use.

```powershell
$base = 'https://storage.googleapis.com/pixellayer-prod-downloads-website-prod-juan'
$release = Invoke-RestMethod -Uri "$base/releases/0.5.1/release.json"
$info = $release.packages.'windows-x64'
$archive = Join-Path (Get-Location).Path $info.filename
Invoke-WebRequest -UseBasicParsing -Uri $info.url -OutFile $archive
if ((Get-Item -LiteralPath $archive).Length -ne $info.size_bytes) { throw 'ZIP size mismatch' }
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $info.sha256) { throw 'ZIP SHA-256 mismatch' }
$staging = Join-Path (Get-Location).Path 'PixelLayer-0.5.1'
if (Test-Path -LiteralPath $staging) { throw 'Choose a fresh extraction directory' }
Expand-Archive -LiteralPath $archive -DestinationPath $staging
$package = Join-Path $staging 'pixellayer-0.5.1-windows-x64'
$manifestHash = (Get-FileHash -LiteralPath (Join-Path $package 'manifest.json') -Algorithm SHA256).Hash
if ($manifestHash -ne $info.package_manifest_sha256) { throw 'Package manifest mismatch' }
& (Join-Path $package 'verify.ps1') -PackageRoot $package
& (Join-Path $package 'setup.ps1') -Workspace 'C:\path\to\images' -Client claude-code -AcceptDownload
```

Setup installs permanently under `%LOCALAPPDATA%\Programs\PixelLayer\0.5.1`,
verifies/reuses or downloads the FP32 model, and returns a selected-client MCP
configuration draft. It does not edit live agent settings. Apply only that draft's
configuration entry and reconnect or restart the client; see [Clients](clients.md).
Setup checks runtime file presence and model integrity, not completed inference
or a connected MCP session.

Do not register an executable under a temporary extraction folder. Keep libraries
beside the installed executable. An identical installation is reused; a different
or modified build in the same destination is refused. Preserve it and pass a new
permanent sibling directory through `-Destination` when needed.

## Model and shared cache

Standard complete setup prepares BiRefNet General ONNX FP32 on CPU: 972,666,916
bytes (about 928 MiB), downloaded separately from the program and skill. It is
accepted only after pinned size and SHA-256 verification. See [Licenses](licenses.md)
for the source revision and hash. There is no automatic model download during an
image tool call. Reuse the selected cache rather than creating one per project.

| Setup wrapper | Default program directory | Default model cache |
| --- | --- | --- |
| Windows | `%LOCALAPPDATA%\Programs\PixelLayer\0.5.1` | `%LOCALAPPDATA%\PixelLayer\models` |
| Linux | `${XDG_DATA_HOME:-$HOME/.local/share}/pixellayer/0.5.1` | `${XDG_CACHE_HOME:-$HOME/.cache}/pixellayer/models` |
| macOS | `$HOME/Library/Application Support/PixelLayer/0.5.1` | `$HOME/Library/Caches/PixelLayer/models` |

`PIXELLAYER_MODELS_CACHE` or an explicit setup cache option selects another cache.
Use that same absolute path in the MCP draft. These are setup-wrapper defaults;
when using CLI commands directly, pass the selected cache explicitly rather than
assuming its platform-derived default is identical.

Conversion, resize and SVG tracing without removal do not need weights. Program-only
installation with `install.ps1`/`install.sh` is a separate technical option; standard
complete setup includes the model. Experimental INT8 has no public download or
supported preparation flow; retain FP32.

For a supplied matching native Unix package, run `bash verify.sh` followed by
`bash setup.sh --workspace /path/to/images --client codex-cli --accept-download`.
Use a native Linux package in WSL unless Windows interoperability was deliberately
selected. Never substitute the Windows package for a native Linux/macOS package.
