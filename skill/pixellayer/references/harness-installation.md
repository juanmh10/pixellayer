# Harness installation reference

This is a supplement for client-specific paths and technical/manual alternatives.
For normal complete setup use SKILL.md/SETUP.md and the package setup wrappers;
program-only installation below does not prepare the standard FP32 model.
SKILL.md retains the essential setup and workspace rules.

## Program, MCP and skill setup

Installing the **program**, downloading **weights**, registering **MCP**, and loading
**the skill** are separate steps. Updating a skill does not update an old EXE or
change the server workspace. Use the native 0.5.1 program and retain its libraries.
The Rust server uses local **stdio**, not an HTTP/SSE URL.

### Obtain and install the program once

Use the verified supplied archive or SKILL.md's public GCS/GitHub download hierarchy.
A source checkout is not required. The skill ZIP excludes engine, runtime and weights.
Stage downloads outside the image workspace and install into a permanent per-user
directory. Check the archive against the selected release manifest before extraction.

**Windows x64 / PowerShell**, from the actual downloaded ZIP location:

```powershell
$zip = (Resolve-Path '.\pixellayer-0.5.1-windows-x64.zip').Path
$expected = ((Get-Content -LiteralPath "$zip.sha256" -Raw) -split '\s+')[0]
if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash -ne $expected) { throw 'ZIP checksum mismatch' }
Expand-Archive -LiteralPath $zip -DestinationPath '.\PixelLayer-new'
$package = (Resolve-Path '.\PixelLayer-new\pixellayer-0.5.1-windows-x64').Path
& (Join-Path $package 'verify.ps1') -PackageRoot $package
& (Join-Path $package 'install.ps1')
$exe = Join-Path $env:LOCALAPPDATA 'Programs\PixelLayer\0.5.1\pixellayer.exe'
```

The installer does not edit PATH or agent settings. Do not overwrite an existing
installation. Native **Linux/macOS** uses the supplied matching `.tar.gz`: compare
`sha256sum archive.tar.gz` (Linux) or `shasum -a 256 archive.tar.gz` (macOS) with its
sidecar, extract into a new directory, run `bash verify.sh`, then `bash install.sh`; use the installed absolute
`pixellayer` path with its adjacent `.so`/`.dylib` libraries. Use SKILL.md's
per-OS install/cache table and retain an existing verified cache. No Rust, Python or Node
is required by the extracted program.

### Choose the four real paths, then download weights if needed

| Token in the templates | Meaning |
| --- | --- |
| `__PIXELLAYER_EXE__` | Native executable, or the `/mnt/<drive>/...exe` launcher for a WSL client using Windows interop |
| `__PIXELLAYER_WORKSPACE__` | Existing image task directory, not the source-code installation or a previous task directory |
| `__PIXELLAYER_CACHE__` | One reusable model cache; same path for downloading and launching every client |
| `__PIXELLAYER_RUNTIME__` | Actual `onnxruntime.dll`, `libonnxruntime.so` or `libonnxruntime.dylib` |

JSON/TOML template tokens must become literal absolute paths; `$HOME`, `~` and
PowerShell variables are not expanded by a generic JSON reader. Preserve unrelated
entries and prefer the selected project scope. Direct execution from an extracted
folder requires explicit portable-mode selection and a permanent directory.
Register only the selected server. Global configurations with fixed
workspace paths do not follow the project currently open in the editor.

PowerShell, after obtaining `$exe` above:

```powershell
$workspace = (Resolve-Path 'D:/MyImageTask').Path # choose an existing task folder
$cache = Join-Path $env:LOCALAPPDATA 'PixelLayer/models' # or reuse your verified cache
$runtime = Join-Path (Split-Path $exe) 'onnxruntime.dll'
& $exe --version
# Only for background removal / cut + SVG, with download authorized:
& $exe --cache-dir $cache model download
& $exe --cache-dir $cache model verify
```

Native Unix equivalent: set `exe`, `workspace`, `cache`, and `runtime` to your actual
absolute paths; run `"$exe" --cache-dir "$cache" model download` and then `model verify`.
Pinned FP32 weights are 972,666,916 bytes (~928 MiB), with SHA-256 checked by the
engine. Direct SVG, resize, conversion and startup need no model download. INT8 is
an optional local experiment with no download endpoint; retain FP32 for standard setup.

For **WSL + Windows EXE**, only the launcher is a WSL path. Workspace, cache and
DLL arguments stay Windows paths (`D:/...`). Native Linux uses Linux paths and `.so`.
Do not mix these modes. A Windows-native client uses Windows paths for all four.

### Generate optional drafts without modifying clients

From `skill/pixellayer/config/`, PowerShell can generate eight drafts (seven clients,
with two OpenCode formats). Resolve variables above first; `$newDraftFolder` must
be a new absolute directory:

```powershell
.\render-config.ps1 -Executable $exe -Workspace $workspace -CacheDirectory $cache -OutputDirectory $newDraftFolder
# When the client runs under WSL but launches this Windows program, add:
# -AgentPlatform WSL
```

The renderer does not install/configure a client, launch MCP or download weights.
Merge just the selected draft into the correct client/scope. Native Unix users can
fill the same templates manually. Templates are linked below; their paths are
relative to this document's location.

### Claude Code — CLI or JSON, local/project/user scope

- **CLI:** `claude mcp add --transport stdio --scope project pixellayer -- "$exe" --workspace "$workspace" --cache-dir "$cache" --ort-dylib "$runtime" mcp`.
  This shell command uses previously resolved variables. Use `--scope user` for
  user scope, or `--scope local` for the current project's private scope.
- **Manual:** merge the [Claude template](../config/claude-code.mcp.json) under
  `mcpServers.pixellayer` in project `.mcp.json`. User/local registrations are
  managed in `~/.claude.json` by Claude; preserve its existing structure.
- **Activate:** inspect `/mcp`, accept the selected project's trust prompt when
  applicable, and reconnect. Do not replace the whole `~/.claude.json` with a template.
- **Skill:** copy the public source `skill/pixellayer/` contents to project
  `.claude/skills/pixellayer/` or user `~/.claude/skills/pixellayer/`. Invoke
  `/pixellayer` or let the client select it. Skill loading does not register MCP.

[Claude MCP](https://code.claude.com/docs/en/mcp) · [Claude skills](https://code.claude.com/docs/en/skills)

### Cursor — project/global JSON or custom server UI

Merge the [Cursor template](../config/cursor.mcp.json) under `mcpServers.pixellayer`
in project `.cursor/mcp.json` or user `~/.cursor/mcp.json`. Alternatively use
Customize / MCP controls to add a custom local stdio server with the executable
and the same arguments. This product is not claimed to be listed in Cursor's store.
Enable/reconnect the server, then check available tools.

Install the public skill in `.cursor/skills/pixellayer/` (project) or
`~/.cursor/skills/pixellayer/` (user); `.agents/skills` is also supported. Avoid
unintentional duplicate copies. Cloud/remote sessions need their own accessible
program/files; a local skill or EXE is not automatically available remotely.

[Cursor MCP](https://cursor.com/docs/mcp) · [Cursor skills](https://cursor.com/docs/skills)

### Copilot in VS Code — workspace/profile JSON or guided UI

Merge the [VS Code template](../config/copilot-vscode.mcp.json) under
`servers.pixellayer` in workspace `.vscode/mcp.json`. For user/profile installation,
use **MCP: Add Server**, choose **Command (stdio)** and the desired configuration
target; the UI opens/selects the correct profile file. The equivalent entry point
is **Chat: Open Customizations → MCP Servers → Add Server**. Supply the actual
executable plus arguments, start/trust the server and refresh the chat's tools.
Do not put a `mcpServers` wrapper inside `.vscode/mcp.json` or register duplicates.

Install the public skill in project `.github/skills/pixellayer/` or user
`~/.copilot/skills/pixellayer/`; `.claude/skills` and `.agents/skills` are also
supported. Use the Agent Customizations editor for workspace/user skills. Keep the entire skill folder, not just a pointer
to a SKILL.md outside the visible workspace.

[VS Code MCP](https://code.visualstudio.com/docs/agent-customization/mcp-servers) · [VS Code skills](https://code.visualstudio.com/docs/agent-customization/agent-skills)

### OpenCode — choose the installed client's format

Project `opencode.json`/`opencode.jsonc` and user `~/.config/opencode/opencode.json`
are distinct scopes. Back up the selected file, then preserve its existing schema.
`opencode --version` identifies the client version, not the PixelLayer version.

| Client format | Template | Entry and activation fields |
| --- | --- | --- |
| V1 / direct `mcp` map | [OpenCode V1](../config/opencode-v1.mcp.json) | `mcp.pixellayer`, `enabled: true`, numeric `timeout` |
| V2 | [OpenCode V2](../config/opencode.mcp.json) | `mcp.servers.pixellayer`, `disabled: false` if supplied; `timeout` is an object |

Both use `type: local` and a **command array** containing the executable followed
by its arguments, not separate `command`/`args` strings. The same server entry
cannot simply be pasted under both layouts. V2 offers a CLI alternative:
`opencode mcp add pixellayer --global -- "$exe" --workspace "$workspace" --cache-dir "$cache" --ort-dylib "$runtime" mcp`.
For older clients consult `opencode mcp add --help` before using version-specific
flags; editing the matching JSON is the portable route. Reconnect the selected
server/session; changing files does not replace an already running old process.

Install the public skill under `.opencode/skills/pixellayer/` or
`~/.config/opencode/skills/pixellayer/`. OpenCode can also discover `.agents/skills`
and `.claude/skills`; choose one intended source rather than conflicting IDs.

[OpenCode V1 MCP](https://opencode.ai/docs/mcp-servers/) · [V2 migration](https://opencode.ai/v2/docs/migrate-v1) · [V2 CLI](https://opencode.ai/v2/docs/cli/commands) · [Skills](https://opencode.ai/docs/skills/)

### Antigravity CLI (AGY) / IDE — JSON and MCP management

Merge the [AGY template](../config/agy.mcp.json) under `mcpServers.pixellayer` in
project `.agents/mcp_config.json` or user `~/.gemini/config/mcp_config.json`.
For the IDE, use the agent panel's **MCP Servers → Manage MCP Servers → View raw config**
and merge the same entry. Inspect MCP connection status and reconnect the selected
server. Do not confuse the `agy` client with a different Gemini CLI configuration.

Skills: project `.agents/skills/pixellayer/`; current CLI user scope
`~/.gemini/antigravity-cli/skills/pixellayer/`; App/IDE user scope
`~/.gemini/config/skills/pixellayer/`. Use the location for the installed surface.
No plugin-store publication is required to configure this local stdio engine.

[Antigravity MCP](https://antigravity.google/docs/mcp) · [Antigravity skills](https://antigravity.google/docs/skills)

### Codex CLI / IDE — CLI, TOML or host UI

- **CLI:** `codex mcp add pixellayer -- "$exe" --workspace "$workspace" --cache-dir "$cache" --ort-dylib "$runtime" mcp`.
  This registers with the active host's configuration. Do not create a duplicate
  if a selected plugin/server already supplies PixelLayer.
- **TOML:** merge the [Codex template](../config/codex-cli.mcp.toml) as
  `[mcp_servers.pixellayer]` in user `~/.codex/config.toml` or trusted project
  `.codex/config.toml`. JSON `mcpServers` is not TOML syntax.
- **IDE UI:** MCP settings → Add server → STDIO; provide the same command and
  arguments. Check `/mcp` or MCP status, then restart/reconnect as needed.
- **Skill:** project `.agents/skills/pixellayer/` or user `~/.agents/skills/pixellayer/`.
  Invoke `$pixellayer`/the skill selector. A different OS/remote host has different
  files and configuration, even when it shares a product account.

[OpenAI MCP documentation](https://learn.chatgpt.com/docs/extend/mcp) · [Skills](https://learn.chatgpt.com/docs/build-skills)

### ChatGPT Desktop / Work — desktop STDIO or existing plugin

**Desktop UI:** Settings → MCP servers → Add server → STDIO; enter the program and
arguments, save and restart the server. On the same supported Codex host, its
`config.toml` MCP configuration can also be shared with the CLI/IDE. Use native
paths for the host actually running the command; a web/cloud chat does not make
a local executable or image directory available automatically.

**Existing local plugin:** the [Work template](../config/chatgpt-work.mcp.json)
preserves the observed Windows plugin `.mcp.json` / `mcpServers` format and explicit
FP32. Merge only the server entry into the actual selected plugin. This is not a
complete plugin or a universal ChatGPT config-file location. Portable `mcp.json`
and compatibility `.mcp.json` are different formats; do not rename one blindly.

For a locally authored skill/plugin, keep the skill under the selected plugin's
`skills/pixellayer/` as its manifest expects. For a skill supplied by Agensi, use
its connector-delivered instructions; do not require exporting/saving its commercial
content to install the public engine. This repository does not claim an OpenAI
plugin-store listing. Reconnect and verify tools in the actual Work session.

[OpenAI desktop MCP](https://learn.chatgpt.com/docs/extend/mcp) · [Plugin packaging](https://developers.openai.com/plugins/build/plugins)

### Install the public skill folder, then verify the connected program

The locations above are **alternative targets**, not a request to create every
copy. From the public source checkout, choose one new destination:

```bash
# Example: OpenCode global skill. Refuse replacement; review/back up existing copies.
skill_destination="$HOME/.config/opencode/skills/pixellayer"
test ! -e "$skill_destination" || { echo 'Skill exists; review its local instructions first'; exit 1; }
mkdir -p "$(dirname "$skill_destination")"
cp -R skill/pixellayer "$skill_destination"
```

PowerShell equivalent: choose `$skillDestination`, refuse an existing path, then
`Copy-Item -LiteralPath 'skill/pixellayer' -Destination $skillDestination -Recurse`
after creating its parent directory. Preserve existing local instructions
when updating a public local copy. These copy commands do not apply to commercial
skill content delivered through a marketplace connector.

Before any image processing, require eight tools including `prepare_workspace`.
If it is absent, **stop before remove_background/resize/vectorize/conversion**:
a six-tool server is not the current workflow. Run the actual installed EXE's
`--version` during authorized setup; cache/model status alone does not identify
the engine. Prepare the real workspace and requested output folder, then inspect
`workspace.root`, returned absolute paths/aliases and ready inputs. A mismatch is
an error to fix in the chosen server configuration, never permission to copy images
to an old root or switch to another port/CLI. Restart the MCP process after changing
its EXE or arguments; refresh the session's tool list.

Use `input_directory: "."` for root images or the user's actual subfolder;
`input` is optional. Report missing/empty/unreadable inputs by the returned absolute
location. A successful preparation with no ready images is not a processed task.
Changing skill files, registering MCP and obtaining a working image result are
separate checks. Protocol connectivity alone does not establish visual quality.
