# PixelLayer 0.5.1 — Windows x64

This package contains the local CLI/MCP server and its native runtime libraries.
Compare the ZIP SHA-256 with the published release manifest before extraction.
Inside the extracted package directory, run PowerShell:

```powershell
.\verify.ps1
.\setup.ps1 -Workspace 'C:\path\to\your\images' -Client claude-code -AcceptDownload
```

Setup installs under `%LOCALAPPDATA%\Programs\PixelLayer\0.5.1`, verifies or
downloads the BiRefNet General CPU FP32 model (~928 MiB), and returns an MCP
configuration draft. Apply only the selected client's entry, then reconnect or
restart that client. Setup does not edit live agent settings or change PATH.
Rust, Python, Node and administrator privileges are not needed to use the package.
Keep all native libraries beside the executable. The model cache is shared per user.

To remove this program version, disconnect its MCP server and stop the process:

```powershell
$installed = Join-Path $env:LOCALAPPDATA 'Programs\PixelLayer\0.5.1'
.\uninstall.ps1 -Destination $installed -WhatIf
.\uninstall.ps1 -Destination $installed
```

Model cache, client configuration, the separately installed skill and other
versions are preserved. Conversion, resize and direct SVG tracing do not need
model weights. Source, BiRefNet, runtime and dependency notices are in `licenses/`.
