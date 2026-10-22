# PixelLayer — setup supplement

Read this only when setup needs detail. SKILL.md contains the essential route when
connector attachments are unavailable. Loading the skill does not install/update
the engine. Do not export/save a commercial skill as an engine-installation step.

## Installation priority

Reuse compatible installation/MCP/cache first. Prefer a validated native host
installer when supplied, then complete PixelLayer setup, then authorized agent
configuration, then concise manual guidance if the host cannot execute it.
No PixelLayer MCPB has been validated yet. A native Desktop extension requires
user installation/approval; no model-callable MCP installation tool is assumed.

Public Windows setup uses the GCS and GitHub hierarchy in SKILL.md. Other public
platforms are not yet released. The skill is separate from the public engine ZIP.

For Claude Desktop Code sessions, use the claude-code project draft. After applying
it, reconnect the MCP or fully restart the application if necessary. Desktop chat
without shell access cannot execute setup; do not invent a claude-desktop client flag.

## One authorization for complete setup

Tell the user setup prepares the program, packaged ONNX Runtime CPU 1.22.0 and
pinned FP32 model (972666916 bytes, ~928 MiB). Existing valid cache is reused.
Do not ask which features to enable or ask again for model consent per image.
A program-only portable installation remains an explicitly chosen technical route;
conversion, resize and direct SVG do not inherently require model weights.

Verify the archive sidecar first. Extract to fresh staging outside the image task;
run Windows `verify.ps1 -PackageRoot PACKAGE_ROOT`, or `bash verify.sh` from the Unix
package directory. Read only manifest version/target/source_commit/source_dirty.
Retain all DLL/so/dylib files together. Never register a temporary executable.

Windows PowerShell, using actual absolute paths and the chosen existing cache:

```powershell
& "$package/verify.ps1" -PackageRoot $package
& "$package/setup.ps1" -Workspace $task -CacheDirectory $cache -Client claude-code -AcceptDownload
```

Native Unix:

```bash
cd "$package"
bash verify.sh
bash setup.sh --workspace "$task" --cache-dir "$cache" --client codex-cli --accept-download
```

Both scripts install into the per-user versioned directory and run complete setup.
Windows accepts -Destination; Unix --destination. Use a fresh permanent sibling
when another/damaged build already occupies the same 0.5.1 directory. Identical
verified builds are reused; previous versions are retained. Default install/cache
paths are in SKILL.md. Prefer native Linux under WSL unless Windows interop was
selected. No compiler, Python or Node is needed by the installed engine.

For an already installed updated engine:

```bash
"$exe" --workspace "$task" --cache-dir "$cache" setup --client CLIENT --accept-download
```

PowerShell uses `& $exe`. --accept-download records existing setup authorization;
without it and with no model, SETUP_CONSENT_REQUIRED reports the bytes/cache before
downloading. Existing models are verified and never silently replaced if corrupt.
Standard complete setup uses FP32, not the optional experimental INT8 model.

setup_complete means runtime file presence and pinned model integrity were checked.
It does not claim successful runtime loading/inference or an established MCP
connection. It returns these flags explicitly. Package verification checks the
libraries against the build manifest; a real processing call validates execution.

## Selected-client configuration and activation

With --client, setup returns configuration_draft. configure --client CLIENT
produces the same draft without installing/downloading. Draft contents:

- JSON clients: apply configuration only; --existing ABSOLUTE_JSON merges in memory.
- Codex: apply configuration_text only to mcp_servers.pixellayer, preserving other TOML.
- Wrappers are diagnostic output, not the client's configuration format.
- --existing and --wsl-interop require --client. WSL interop is for a Windows engine
  with a WSL launcher; engine arguments remain Windows-native paths.

No setup command or script edits live client settings. Apply the draft through the
host's authorized edit flow, preserving other servers. Prefer the actual task's
project scope; avoid duplicate registrations. Reconnect/reload, or fully restart
the application if required, then discover eight tools and prepare_workspace with
the actual task root. If still unavailable, report the specific startup failure;
do not keep reinstalling. [Client routes](references/harness-installation.md)
contains scope and version-specific alternatives; read only the relevant client.

The workspace remains fixed per running process. Another task reuses program/cache
but needs its own correctly scoped entry and reconnection. Never broaden access to
a home directory/drive or move images into an old root to pass mismatch checks.

## Download and failure handling

Progress goes to stderr; CLI stdout remains one final JSON result. Downloads use
a 30-second connection timeout, 1800-second request timeout and at most three
attempts for transient connection/HTTP/body errors, with bounded delay. A request
may resume bytes from the same temporary file when Range is honored. A server
ignoring Range restarts that temporary file. Temporary partial data is not a valid
cache. Handled failures normally clean it up; abrupt termination can leave a
partial file. Do not treat it as a verified model or promise restart-resume.

DOWNLOAD_ERROR reports stage, HTTP status where available, timeout/connection
flags, transferred bytes and the underlying cause chain. These fields support
investigation; they do not automatically identify a certificate/proxy issue.
Do not disable TLS, print credentials, use an unverified model or silently switch
precision. A hash/size mismatch remains an integrity failure, not a retry success.

If the host tool times out while setup is still running, continue/poll that process
through the host's existing task mechanism. Do not spawn duplicate downloads or
repeat installation. No shell/task access means presenting the concrete action to
the user, not claiming setup finished. On antivirus quarantine, stop and report
version/hash/detector; never restore/exclude/disable as part of product setup.
