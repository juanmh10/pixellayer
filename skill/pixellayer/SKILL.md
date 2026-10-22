---
name: pixellayer
description: Process local images with PixelLayer to remove backgrounds, convert PNG/WebP/JPEG, resize, or trace SVG. Also use when setting up or troubleshooting its local MCP server.
---

# PixelLayer

Process images locally through the PixelLayer MCP. The engine/model are separate
from this lightweight skill. Inputs stay on the engine machine; tools accept
paths and return paths/metadata, never image bytes/base64. Preserve originals.

## Choose the available setup route

1. **Reuse:** discover available/deferred PixelLayer tools (names may be prefixed).
   Engine 0.5.1 has prepare_workspace, get_result_info, remove_background,
   convert_format, resize_image, vectorize_image, list_models and get_model_info.
   An old engine lacking prepare_workspace must be upgraded before processing.
   Without get_result_info, compatible prepared operations may continue but output
   recovery needs an upgrade. Updating the skill does not update the executable.
2. **Native host installation:** prefer a host-supported installer only when an
   actual compatible PixelLayer package is supplied and validated. No PixelLayer
   MCPB is currently validated; do not claim that the model has a native tool to
   install another MCP or invent such a call. User UI approval may be needed.
3. **Complete PixelLayer setup:** use a real native package as below. With setup
   authorized, prepare engine, runtime and the verified FP32 model together; do
   not ask which image features to install or request consent again per operation.
4. **Agent setup:** when shell/filesystem access and authorization exist, install
   and apply only the current client's MCP entry. Preserve unrelated settings.
5. **Manual instructions:** if the host cannot execute setup, give the concrete
   missing action. Writing config or launching MCP in a terminal does not expose
   tools in the current conversation. Reconnect/trust/reload or restart the host
   as required, then rediscover tools before claiming readiness. Report this expected
   activation step concisely; do not describe unselected client configurations as errors.

An image request alone does not authorize installing software or downloading the
~928 MiB model. Reuse existing authorization; otherwise ask once for **complete
setup**, explaining its size, selected client and paths. Do not install package
managers/gh in a cascade. Report an antivirus block and stop; do not disable AV,
restore quarantine or create exclusions. No terminal access means instructions,
not a claim that installation happened.

### Complete setup when required

First inspect the selected client's PixelLayer entry and executable/version.
A missing PATH command does not prove no installation: installers do not edit PATH.
Reuse a working matching installation/cache. Use the engine's OS/architecture;
WSL defaults to native Linux unless Windows interoperability was selected.

| OS | Native archive (0.5.1) | Permanent installation default |
| --- | --- | --- |
| Windows x64 | pixellayer-0.5.1-windows-x64.zip | %LOCALAPPDATA%\Programs\PixelLayer\0.5.1 |
| Linux x64 / ARM64 | pixellayer-0.5.1-linux-x64.tar.gz / linux-aarch64.tar.gz | ${XDG_DATA_HOME:-$HOME/.local/share}/pixellayer/0.5.1 |
| macOS Intel / ARM64 | pixellayer-0.5.1-osx-x86_64.tar.gz / osx-arm64.tar.gz | $HOME/Library/Application Support/PixelLayer/0.5.1 |

Acquire packages in this order: a verified matching installation, a supplied or
cached verified archive, then the public GCS download, then the **same version**
on GitHub Releases. Public setup requires no GitHub account, gh, or compiler.
Only Windows x64 is publicly released initially. Do not substitute a Windows
package for WSL/Linux/macOS; report unavailable public platforms unless
a matching native archive was supplied.

Public stable manifest:
`https://storage.googleapis.com/pixellayer-prod-downloads-website-prod-juan/channels/stable.json`

For a requested fixed version, use `releases/VERSION/release.json` under that
same HTTPS base instead of selecting a different version. Read schema_version
(currently 1), version, engine_commit and packages[PLATFORM]. The package entry
contains filename, size_bytes, sha256, package_manifest_sha256, url and fallback_url.
Download from url; on connection failure/unavailability only, try fallback_url.
If the GCS manifest is unavailable, the same version's release.json is available
at `https://github.com/juanmh10/pixellayer/releases/download/vVERSION/release.json`.
Without a requested version, resolve the public latest stable release. Require
version 0.5.1 or newer for this skill; if that version is not yet published, report
release unavailable and stop. Do not substitute an older release or a prerelease.
Accept downloads only over HTTPS from the stated GCS
bucket or juanmh10/pixellayer GitHub Releases (GitHub asset redirects are normal).
A size/hash mismatch stops setup; do not switch origins to hide integrity errors.

Stage outside image folders. Verify archive size/SHA-256 against the selected
manifest, extract to fresh temporary staging, verify manifest.json's SHA-256,
then run Windows `verify.ps1 -PackageRoot PACKAGE_ROOT`; Unix `bash verify.sh`
from PACKAGE_ROOT when an authorized Unix package exists. Read only manifest
version, target, source_commit, engine_commit and source_dirty. Match the selected
version/platform and each published commit independently; packaging and engine
commits can differ. source_dirty must be false. Do not print full manifests.
Different package inventories can have different manifests even with the same
engine commit: reuse an installation only after matching the
exact package manifest; otherwise select a sibling permanent directory.
Keep runtime libraries together. No Python, Node or compiler is needed.

Use package `setup.ps1 -Workspace TASK -CacheDirectory CACHE -Client CLIENT
-AcceptDownload` on Windows; Unix `bash setup.sh --workspace TASK --cache-dir CACHE
--client CLIENT --accept-download`. Resolve actual paths and quote for the host
shell. Scripts install permanently and return a configuration draft; they do not
apply live agent settings. If a supplied older package lacks setup scripts, install
with install.ps1/install.sh and use its documented model download/verify commands;
follow that package's documented capabilities.

To remove one program version, first disconnect its MCP client and stop the
server. On Windows, preview with `uninstall.ps1 -Destination PATH -WhatIf`, then
run `uninstall.ps1 -Destination PATH`. On Unix, preview with
`bash uninstall.sh --dry-run PATH`, then run `bash uninstall.sh PATH`. Pass the
exact install directory and a matching package copy. The uninstaller refuses changed builds, added files,
symlinks and active processes; it leaves weights/cache, agent configuration,
separately installed skill and sibling versions in place.

For an already installed **updated** engine, use:

```bash
"$exe" --workspace "$task" --cache-dir "$cache" setup --client CLIENT --accept-download
```

PowerShell uses `& $exe`. This verifies/reuses existing weights; downloaded weights
are accepted only after pinned size/SHA checks. Standard model: BiRefNet General
ONNX FP32, MIT, revision 534d3c82d3bb8b2f0867db6dfbc3a525b8e42f67,
972666916 bytes, SHA-256 58f621f00f5d756097615970a88a791584600dcf7c45b18a0a6267535a1ebd3c.
Keep inference CPU/FP32; experimental INT8 has no automatic download endpoint and
must not replace FP32 to complete a task. Setup does not load inference or prove
MCP connection. Conversion, resize and direct tracing still work without weights
in explicitly selected technical/program-only installations.

Reuse cache from the selected entry, PIXELLAYER_MODELS_CACHE or doctor. If none
exists, choose Windows %LOCALAPPDATA%\PixelLayer\models, Linux
${XDG_CACHE_HOME:-$HOME/.cache}/pixellayer/models, macOS
$HOME/Library/Caches/PixelLayer/models. Resolve these expressions to absolute paths;
pass the same cache to setup and MCP. No new cache per project/agent/version.

Use the permanently installed executable/runtime, never TEMP/Downloads staging.
An identical build is verified/reused; another/damaged build in the same version
folder is refused. Preserve it and select a fresh permanent sibling such as
0.5.1-SOURCE_SHORT_SHA. Keep previous versions for rollback. Skill delivery is
separate: never ask a buyer to export/save their commercial skill to install the
engine. Read [SETUP.md](SETUP.md) only for setup detail if available; this section
contains the essential steps without connector attachments.

### Apply only the selected MCP configuration

Clients: claude-code, cursor, copilot-vscode, codex-cli, agy, open-code,
open-code-v1, chatgpt-work. Confirm the actual client/format, not its display name.
`setup` returns configuration_draft; `configure --client CLIENT` generates a draft
without downloading. Within either draft apply **configuration** (JSON clients)
or **configuration_text** (Codex TOML), not the enclosing result. JSON --existing
ABSOLUTE_SETTINGS_PATH merges in memory; no live file is written. Preserve other
entries and back up the chosen config. For Codex change only mcp_servers.pixellayer.

Prefer project scope; reuse the buyer's chosen scope rather than creating duplicate
active servers. Project routes: Claude .mcp.json; Cursor .cursor/mcp.json;
Copilot .vscode/mcp.json; Codex .codex/config.toml (trusted project); AGY
.agents/mcp_config.json; OpenCode opencode.json. ChatGPT Work needs the actual
host-supported stdio surface/selected plugin format, not a guessed global file.
Use optional [client reference](references/harness-installation.md) for user-scope
routes or version-specific formats when attachments are available.

All executable/workspace/cache/runtime values are absolute engine-native paths,
serialized as JSON/TOML; literal ~, environment placeholders or shell quotes are
not config paths. WSL launching Windows uses --wsl-interop on setup/configure:
launcher /mnt/...; engine arguments Windows paths. Native Linux does not use it.
The configured workspace is fixed at startup. Changing tasks reuses install/cache
but requires a selected entry pointing at the new authorized root and reconnection.
Never widen it to home/a drive to avoid reconfiguration. If discovery still fails,
report the startup blocker; do not keep reinstalling. Some clients need legacy MCP
initialize fallback; server/discover method-not-found is not an image-tool error.

## Prepare the actual task

Before image operations, call prepare_workspace once:

- expected_workspace: actual absolute image task directory supplied by the user/host,
  not a root copied from a server error or the engine installation directory.
- input_directory: user's selection. If unspecified, explicitly use "." first;
  consider conventional input within the same workspace only if the image is absent.
  No recursive/global search; input is never mandatory. Use exact returned paths.
- output_directory: user's relative destination, otherwise "output". Do not ask for
  a destination when that default satisfies the request. It bounds subsequent output.

Relative paths resolve under the server root, not the agent CWD. Windows accepts
native drive paths and /mnt/<drive>/ aliases. On WORKSPACE_MISMATCH stop processing,
align the authorized selected entry and reconnect. Never change expected_workspace
to pass the check, copy images to the old root or search unrelated host directories.
Client attachments are not automatically local files: use only the host's authorized
file-placement flow inside the task and prepare again after placement.

Inspect input_status, input_ready and per-file status. missing_directory reports
the full path; if merely conventional, try the actual root before asking. Empty
folders, unsupported files and unreadable images are input problems, not missing
models. For partially_readable process only selected status:ready files and report
failures. success:true with input_ready:false is not a processed image. Do not repeat
unchanged preparation. No disk/model/inference changes occur during preparation.

## Process with explicit defaults

| Request | Default/action |
| --- | --- |
| Remove background | remove_background, output_format png (WebP if requested). |
| Cut + SVG | One vectorize_image call, remove_background:true; retain/report PNG and SVG. |
| SVG without a removal request | vectorize_image, remove_background:false, detail_level:logo, color_mode:color. |
| Already transparent cutout | Preserve its alpha and trace directly when appropriate; do not re-segment automatically. Explicit user removal requests take precedence. |
| Convert | convert_format with requested target_format; quality 90 unless requested otherwise; lossless only for WebP. |
| Resize | User's dimensions/mode or scale_percent; ask once if missing. Never invent a size. |
| Missing response / existing outputs | get_result_info after preparation, optionally exact output_path; list limited to 100 outputs, not historical timings. |

Filenames do not authorize unrelated operations or specify missing dimensions.
Ask only for unresolved intent, ambiguous input, required resize/format parameters
or genuinely missing setup authorization. Continue independent authorized images.
A white background or PNG extension does not imply background removal. Trace each
asset's actual source, not the previous asset's output. Omit output_path for automatic
collision-safe names; never delete/overwrite/rename existing outputs to clear errors.
On OUTPUT_EXISTS choose a new unused name or omit output_path. If tracing fails after
segmentation, report/retain details.intermediate_image as partial success.

Consume structuredContent or parse JSON text once. Keep source/intermediate/final
paths and success/error, not full payloads. Raster results expose absolute_path and
path_aliases; SVG has svg_absolute_path/svg_path_aliases; combined calls include
intermediate_image and traced/source paths. A lost response calls for recovery,
not repeated inference. get_result_info does not perform visual review.

## Review and report

When a host image viewer exists (Read, view_image or equivalent), **open the original
and generated PNG/WebP** using returned paths and compare edges, missing detail,
letters, halos and unwanted background. Review SVG separately when a supported
viewer exists; PNG review alone is not SVG validation. Keep any visual diagnostics
inside the authorized workspace. Do not use shell to search/copy/move/delete/render
outputs to bypass MCP constraints. If a format/viewer is unsupported, mark that
visual review pending. File existence, alpha metadata or SVG path count are not
visual approval. Do not claim user acceptance on their behalf.

Summarize each input: operation, success/pending/error, actual output paths and
visual-review status. Combined cut+SVG reports both retained PNG and SVG. Report
actual error code/stage; never claim failed work completed. Download progress is on
stderr and final CLI output is JSON. If a setup download runs beyond a tool timeout,
poll the existing task/process using the host mechanism; do not start duplicate
downloads or repeat program installation. Report the detailed DOWNLOAD_ERROR cause;
never disable TLS or substitute an unverified model.

CPU inference is heavier than conversion/resize/tracing. Preserve selected threads,
TTL and precision; do not promise GPU use or universal RAM/performance. SVG is an
approximation and may be large. Optional tool schemas and client references are
supplements, not required for the normal prepared workflow.
