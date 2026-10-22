# PixelLayer 0.5.1 — Linux and macOS

Use the archive matching your native OS and architecture. Compare its SHA-256
with the published checksum before extraction. Inside the extracted directory:

```bash
bash verify.sh
bash setup.sh --workspace /path/to/images --client codex-cli --accept-download
```

Setup installs per user, verifies or downloads the BiRefNet General CPU FP32 model
(~928 MiB), and returns a selected-client MCP draft. Apply that entry and reconnect
the client. The model cache is shared per user. Setup does not edit live client
settings or change PATH. No Rust, Python or Node is required to run the package.
Keep native libraries beside the executable. Linux requires glibc and libstdc++;
macOS uses its system libraries. Alpine/musl is not supported by this package.

To remove one installed version, disconnect its MCP and stop the process. Pass the
exact version directory printed by setup:

```bash
bash uninstall.sh --dry-run /path/to/installed/version
bash uninstall.sh /path/to/installed/version
```

Cache, client configuration, the separately installed skill and other versions
are preserved. Conversion, resize and direct SVG tracing do not need weights.
Licenses and third-party notices are in `licenses/`.
