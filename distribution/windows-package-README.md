# PixelLayer 0.5.0 — Windows x64

Local CPU image processing: background removal, PNG/WebP/JPEG conversion,
resize and SVG tracing. Includes the engine, ONNX Runtime, Microsoft Visual C++
runtime libraries, setup, verification and per-version uninstall scripts.

Downloads and documentation: https://github.com/juanmh10/pixellayer

## Verify and install

In PowerShell, from the extracted package directory:

```powershell
.\verify.ps1 -PackageRoot .
.\setup.ps1 -Workspace 'C:\path\to\images' -Client claude-code -AcceptDownload
```

Choose your real workspace and client. Clients include claude-code, codex-cli,
cursor, copilot-vscode and agy. Setup installs the program permanently, verifies
or downloads the BiRefNet General FP32 model (~928 MiB), and prints an MCP
configuration draft. Apply that draft to the selected client and reconnect it.
The model is separate; existing verified model cache is reused. No Python,
Node, Rust compiler or GitHub login is required to use this package.

For program-only installation: `.\install.ps1 -Destination 'C:\path\to\PixelLayer\0.5.0'`.
Preserve the extracted package for verification and uninstallation. If the
standard destination already contains another build, choose a sibling directory.

## Remove one installation

Disconnect the MCP client and stop its server. From this matching package copy:

```powershell
.\uninstall.ps1 -Destination 'C:\exact\installed\directory' -WhatIf
.\uninstall.ps1 -Destination 'C:\exact\installed\directory'
```

Removal preserves models/cache, agent configuration, separately installed skills
and other versions. Modified files, extra files and active processes prevent removal.
Do not use this package's uninstaller for an installation with another manifest.

Original images are preserved. Review image results before relying on their quality.
If antivirus blocks a file, stop and report the detection. This package is not
code signed; public hosting does not resolve antivirus or reputation issues.

The `licenses/` directory contains distribution notices. Model license notices
are in `docs/licenses/`. Model weights and the separately distributed agent skill
are not included. Engine binaries match the approved native build identified in
manifest.json; this public archive omits internal onboarding documents and skill.
