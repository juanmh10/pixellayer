# PixelLayer

PixelLayer is a local image-processing engine with a command-line interface and
an MCP server for AI agents. It removes image backgrounds, converts PNG, WebP and
JPEG, resizes images, and traces SVG files. Processing runs on your computer;
MCP exchanges file paths and metadata, not image contents. Original files are
preserved.

## Windows x64 quick start

Download the [Windows x64 ZIP](https://storage.googleapis.com/pixellayer-prod-downloads-website-prod-juan/releases/0.5.1/pixellayer-0.5.1-windows-x64.zip)
from the versioned download endpoint, or use the [PixelLayer 0.5.1 GitHub release](https://github.com/juanmh10/pixellayer/releases/tag/v0.5.1).
The package includes the engine and ONNX Runtime CPU 1.22.0. The BiRefNet model
is a separate download of about 928 MiB and is cached outside the package.

Compare the ZIP SHA-256 with the value in the [release manifest](https://storage.googleapis.com/pixellayer-prod-downloads-website-prod-juan/releases/0.5.1/release.json).
Extract the ZIP, open PowerShell in its extracted package folder, and run:

```powershell
.\verify.ps1
.\setup.ps1 -Workspace 'C:\path\to\your\image-workspace' -Client claude-code -AcceptDownload
```

Setup installs PixelLayer for your user, downloads and verifies the model, and
prints an MCP configuration draft. Apply that draft to the selected client's
settings, then reconnect or restart the client and discover the PixelLayer tools.
The setup scripts do not edit live agent settings. Other supported client names
are listed in `skill/pixellayer/config/`.

To remove one installed version, disconnect its MCP server and stop it, then use
the matching package's `uninstall.ps1` with the exact install directory:

```powershell
.\uninstall.ps1 -Destination "$env:LOCALAPPDATA\Programs\PixelLayer\0.5.1" -WhatIf
.\uninstall.ps1 -Destination "$env:LOCALAPPDATA\Programs\PixelLayer\0.5.1"
```

The uninstaller removes only that version. It keeps model cache, agent settings,
the separately installed skill, and other PixelLayer versions.

## Skill

The lightweight agent skill is in [`skill/pixellayer/`](skill/pixellayer/).
Download the [skill ZIP](https://github.com/juanmh10/pixellayer/releases/download/v0.5.1/pixellayer-skill-0.5.1.zip)
or install that folder using your agent's skill mechanism. Its `SKILL.md` includes
the essential setup and usage instructions; setup templates for Claude Code,
Cursor, and GitHub Copilot in VS Code are in `skill/pixellayer/config/`.

Windows x64 is the validated public distribution target. Other native targets are
built in CI. Copilot templates are included; Copilot validation is planned for a
later iteration.

## Documentation

Start with the [documentation index](docs/index.md), or go directly to
[installation](docs/installation.md), [client configuration](docs/clients.md),
[image operations](docs/usage.md), [uninstall](docs/uninstall.md),
[troubleshooting](docs/troubleshooting.md), [release operation](docs/releases.md)
and [licenses/model provenance](docs/licenses.md).

The published 0.5.1 archives remain tied to their recorded source commit. Later
changes on `main` do not replace the released binaries or skill ZIP.

## License

PixelLayer source is declared under the MIT License in `Cargo.toml`; see
[`LICENSE`](LICENSE). The BiRefNet model is MIT-licensed. ONNX Runtime is also
MIT-licensed. Their notices are included in `licenses/`. The Windows package
also contains Microsoft Visual C++ runtime components, which remain subject to
their applicable Microsoft terms.
