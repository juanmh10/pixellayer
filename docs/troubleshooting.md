# Troubleshooting

| Symptom | Action |
| --- | --- |
| Tools absent after configuration | Reconnect/reload the selected server or restart the client; then rediscover tools. Do not reinstall repeatedly. |
| `WORKSPACE_MISMATCH` | Correct the selected entry's workspace and reconnect. Do not change the expected root to conceal the mismatch. |
| `WORKSPACE_NOT_PREPARED` | Call `prepare_workspace` with the actual task root before image operations. |
| No ready inputs | Inspect `input_status` and returned absolute directory; explicitly select `.` for root images or the real subfolder. |
| `OUTPUT_EXISTS` | Omit the MCP output name or choose a new unused one; preserve existing files. |
| `OUTPUT_DIRECTORY_MISMATCH` | Use the prepared output directory or prepare the user-selected directory again. |
| `SETUP_CONSENT_REQUIRED` | Obtain complete-setup authorization, then rerun with `--accept-download` (wrapper `-AcceptDownload`). |
| `RUNTIME_NOT_FOUND` | Verify that the matching runtime libraries remain beside the installed executable or check the explicit runtime path. |
| Existing destination differs | Preserve it; select a fresh permanent sibling installation directory. |

## Model download

Download progress goes to stderr and the final CLI result is JSON. If a host tool
times out while setup is still running, poll that existing task/process rather
than starting another download or installation. The configured connection timeout
is 30 seconds and request timeout is 1800 seconds; transient errors have at most
three application attempts. Permanent certificate errors do not use that retry loop.

`DOWNLOAD_ERROR` can include `stage`, `hostname`, `http_status`, `timeout`,
`connection_error`, `certificate_error`, `tls_root_store`, `transferred_bytes` and
`causes`. Report the available fields, without credentials or signed URL queries.
On a hash/size mismatch, stop: partial data is not an accepted model.

The engine uses OS-trusted certificate authorities. For an `UnknownIssuer` or
HTTPS-inspection/proxy problem, inspect the reported host and the OS trust setup.
Do not disable certificate verification or change antivirus settings as part of
PixelLayer setup. After the underlying issue is resolved, use the installed engine
and the same cache to retry the model download:

```powershell
& $exe --workspace $workspace --cache-dir $cache setup --client claude-code --accept-download
```

Handled failures normally remove their temporary file; an interrupted process may
leave a partial file. Its presence is not a valid cache and does not prove restart
resume support. Keep the pinned model unless its own integrity check fails.

## Antivirus and visual review

On a block/quarantine, stop and record version, detection, file and step. Do not
restore files, add exclusions or disable protection as an installation workaround.
Successful processing on one system does not establish universal AV acceptance.

If a raster viewer ignores alpha, use a transparency-aware viewer before concluding
removal failed. SVG needs a separate supported browser/vector viewer. PixelLayer
0.5.1 does not provide a dedicated SVG-to-PNG review tool. No suitable viewer means
visual review is pending, not failed processing.
