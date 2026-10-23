# Image operations

## Prepare the real workspace

Discover the eight PixelLayer tools, then call `prepare_workspace` once per task.
The following parameters are an example; replace the root with your actual folder:

```json
{"expected_workspace":"C:/path/to/images","input_directory":".","output_directory":"output"}
```

The engine's omitted `input_directory` default is `input`; the skill explicitly
selects `.` first when images are in the task root. `input` is not mandatory.
Inventory is nonrecursive and limited to 100 supported images. Use exact returned
paths with `status:ready`; `success:true` with `input_ready:false` is not a completed
image operation. A failed preparation invalidates the previous preparation.

## Tools and parameters

| Tool | Purpose |
| --- | --- |
| `prepare_workspace` | Check scope and inventory inputs without loading inference |
| `get_result_info` | Inspect up to 100 existing outputs or one selected output |
| `remove_background` | Create a PNG/WebP cutout with alpha |
| `convert_format` | Convert PNG/WebP/JPEG |
| `resize_image` | Fit, fill/crop, exact dimensions or percentage |
| `vectorize_image` | SVG tracing, optionally removing background first |
| `list_models` | Inspect active model/precision and availability |
| `get_model_info` | Inspect the selected model using `model_id` |

### Remove background

```json
{"image_path":"photo.png","output_format":"png"}
```

`remove_background` uses the configured model/cache. PNG/WebP preserve dimensions
and combine the new mask with existing alpha. JPEG cannot preserve transparency.

### Cut and trace SVG

```json
{"image_path":"photo.png","remove_background":true,"detail_level":"logo","color_mode":"color"}
```

Send this to `vectorize_image`. One call creates and retains a cutout PNG, then
traces that exact PNG. Report both paths. If tracing fails after removal, inspect
`details.intermediate_image` and retain/report the partial result.

For direct SVG, use `remove_background:false`; an opaque background stays opaque.
Preserve existing alpha unless a new segmentation was requested. Detail levels
are `logo`, `low`, `medium`, `high`; color modes are `color`, `binary`. Defaults are
`logo` and `color`. SVG is an approximation, and path count/file size does not
establish visual quality.

### Convert

```json
{"image_path":"photo.png","target_format":"webp","quality":90,"lossless":true}
```

`convert_format` accepts `png`, `webp`, `jpeg` (`jpg` alias). Quality is 1-100,
default 90; `lossless:true` is supported only for WebP. JPEG composites alpha over
white and reports a warning.

### Resize

```json
{"image_path":"photo.png","mode":"percentage","scale_percent":50,"resample":"lanczos"}
```

`resize_image` modes: `fit` preserves aspect ratio, `fill` crops, `exact` may distort,
and `percentage` uses only `scale_percent`. Fill/exact require both width and height;
fit accepts width, height or both. Resampling options are `lanczos` (default),
`bicubic`, `bilinear`, `nearest`. Ask for the target dimensions/percentage when
missing; do not infer them from a filename.

## Outputs and recovery

Omit `output_path` in prepared MCP calls for automatic collision-safe names inside
the selected output folder. Explicit paths must also remain in that folder.
Originals and existing outputs are preserved. On `OUTPUT_EXISTS`, select an unused
name rather than deleting an output. Inputs and generated images are limited to
50 million pixels; EXIF metadata is not preserved.

Consume `structuredContent` or parse the text JSON once. Keep status and actual
source/intermediate/final paths; do not print complete manifests or tool payloads.
If the response was lost, use `get_result_info` before repeating inference:

```json
{}
```

That call lists existing outputs without writes or inference. It does not recover
historical processing times or prove source provenance. Optional `output_path`
selects a specific existing file inside the prepared output directory.

Open original and output rasters in an available viewer. Use a transparency-aware
viewer: ignoring alpha can make a correct cutout appear opaque. Review SVG in a
browser/vector viewer separately. If no suitable viewer exists, report review as
pending; file creation and alpha metadata are not visual approval.

## Direct CLI

For an explicitly selected CLI workflow, store the tool parameters in a UTF-8 JSON
file without BOM and provide an explicit output path inside the task:

```json
{"image_path":"photo.png","target_format":"webp","output_path":"output/photo.webp"}
```

PowerShell, after saving that object as `request.json`:

```powershell
& $exe --workspace $workspace call convert_format --json-file request.json
```

Use `--json-file` to avoid native PowerShell quoting differences. CLI authorizes
its workspace per invocation; MCP preparation is session-scoped. CLI is not a way
to bypass a mismatched MCP workspace. Progress uses stderr, final results use JSON
on stdout; `mcp` reserves stdout for protocol messages. CLI exit codes are 0 for
success, 1 for execution errors and 2 for command syntax errors.
