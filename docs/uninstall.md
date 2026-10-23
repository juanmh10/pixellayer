# Uninstall one program version

Disconnect the selected MCP server and stop its process. Use the uninstaller from
the matching verified package and pass the exact installation directory. Preview
first; do not delete the entire PixelLayer parent directory as a substitute.

## Windows

From the matching extracted package directory:

```powershell
$installed = Join-Path $env:LOCALAPPDATA 'Programs\PixelLayer\0.5.1'
.\uninstall.ps1 -Destination $installed -WhatIf
.\uninstall.ps1 -Destination $installed
```

Use your actual destination if setup used a sibling/custom directory. No extra
confirmation is needed beyond the command's normal removal safeguards.

## Linux/macOS

From a matching native package:

```bash
bash uninstall.sh --dry-run /path/to/installed/version
bash uninstall.sh /path/to/installed/version
```

## Preserved data and refusals

Removal targets the verified files of that version. It preserves the shared model
cache, agent configuration, separately installed skill, other program versions,
image workspaces and generated images. Remove or update the selected client's
stale MCP entry separately if it still points to the removed executable.

Changed files, additional files, symlinks and active processes cause refusal.
Review the reported cause; do not force recursive deletion or relax verification.
Installation staging/download copies are separate from the installed destination
and are not removed by this operation.
