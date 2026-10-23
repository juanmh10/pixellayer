# Clients and MCP activation

Loading the skill, installing the engine, applying MCP configuration and connecting
the tools are separate steps. Setup returns a draft for one client; it does not
register the server automatically or expose tools in an existing conversation.

## Choose the actual client

These are the draft formats accepted by PixelLayer, not a claim that every client
version or interface has been validated.

| `--client` / `-Client` | Draft/template | Project configuration |
| --- | --- | --- |
| `claude-code` | `mcpServers.pixellayer` | `.mcp.json` |
| `cursor` | `mcpServers.pixellayer` | `.cursor/mcp.json` |
| `codex-cli` | TOML `mcp_servers.pixellayer` | Trusted project `.codex/config.toml` or selected user configuration |
| `agy` | `mcpServers.pixellayer` | `.agents/mcp_config.json` |
| `open-code` | `mcp.servers.pixellayer` | Matching `opencode.json` client format |
| `open-code-v1` | `mcp.pixellayer` | Matching `opencode.json` client format |
| `chatgpt-work` | Selected local plugin `mcpServers.pixellayer` | Actual host-supported plugin configuration |
| `copilot-vscode` | `servers.pixellayer` | `.vscode/mcp.json`; template provided, validation deferred |

Templates are in [skill/pixellayer/config](../skill/pixellayer/config/). The
[client reference](../skill/pixellayer/references/harness-installation.md) contains
optional scope and format details. Check the installed client's actual format;
do not create registrations in every location in the table.

Claude Desktop **Code sessions** use the `claude-code` project route. A Desktop
chat without shell/filesystem access cannot execute this bootstrap. PixelLayer
does not supply a validated MCPB extension or a native host tool that installs
other MCP servers. Do not infer a universal Desktop configuration from its name.

## Apply one draft

The installed engine can generate the selected draft without downloading:

```powershell
$exe = Join-Path $env:LOCALAPPDATA 'Programs\PixelLayer\0.5.1\pixellayer.exe'
$cache = Join-Path $env:LOCALAPPDATA 'PixelLayer\models'
& $exe --workspace 'C:\path\to\images' --cache-dir $cache configure --client claude-code
```

For JSON clients, apply `configuration`; for Codex, apply `configuration_text`.
A complete setup result nests this under `configuration_draft`. Do not write the
entire result wrapper as the client's configuration. Back up the selected settings
and preserve unrelated servers. JSON `--existing ABSOLUTE_SETTINGS_PATH` merges in
memory; it does not write the live file. Use the emitted draft rather than
reimplementing the template renderer.

Executable, workspace, cache and runtime values must be absolute paths in the
engine's OS format. Resolve template variables before serialization. For a WSL
client launching a Windows EXE, engine `setup`/`configure --wsl-interop` generates a
WSL launcher with Windows-native engine arguments. Native Linux does not use that
flag. The Windows PowerShell setup wrapper exposes `-WslInterop`.

After applying the entry, use the client's reconnect/reload control; fully restart
the application if its tools do not refresh. This is an expected activation step.
Discover the eight tools before processing. Launching stdio in a terminal alone
does not connect it to the current chat.

## Workspace scope

The workspace is fixed when the MCP process starts. To change tasks, reuse the
installation and cache, update only the selected entry's authorized workspace,
then reconnect. Do not broaden access to an entire home directory or drive.

Call `prepare_workspace` with the actual task root. `WORKSPACE_MISMATCH` means fix
the selected entry, not change the expected root to hide the mismatch or move
images to another folder. Tools and outputs remain confined to that workspace.
