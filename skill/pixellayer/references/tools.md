# PixelLayer Rust tools — examples

Use discovered MCP tool schemas as the current contract. Each call below sends only
parameters; use the actual host-specific tool name. These examples assume files in
the authorized workspace. Omit `output_path` for unique automatic filenames.

## Prepare the actual task directory first (engine 0.5.1)

`prepare_workspace` is mandatory for MCP image operations. Example, only when
`/mnt/d/MyTask` is the caller's actual project directory:

```json
{"expected_workspace":"/mnt/d/MyTask","input_directory":"input","output_directory":"output/2"}
```

Consume `images` (exact paths, dimensions, alpha) and active model/precision.
`workspace.root` and its aliases must match this task, not a previous workspace.
`WORKSPACE_MISMATCH` is a setup blocker, not a reason to copy files elsewhere.
Until a successful preparation, image tools return `WORKSPACE_NOT_PREPARED`.
A failed new preparation invalidates the previous one. No AI is loaded during
preparation. Input inventory is nonrecursive and limited to 100 supported images;
`truncated` indicates that the caller should select a more specific input folder.

`input` is optional: `input_directory: "."` selects the root; `photos` selects that
subfolder. Preparation never creates or copies input files. `input_absolute_directory`
and `input_path_aliases` identify the selected location. `input_status` is one of
`missing_directory`, `no_supported_images`, `unreadable_images`, `partially_readable`
or `ready`; `input_ready`, `ready_count` and `error_count` summarize the returned
inventory. `success: true` can accompany no usable inputs; follow `next_step` and
process only status:ready entries. Counts cover the returned nonrecursive inventory,
not unscanned subfolders or entries beyond the limit. Client attachments must be
made available through an authorized host workflow inside the real workspace.

## Transparent cutout

```json
{"image_path":"input/photo.png","output_format":"png"}
```

Tool: `remove_background`. PNG/WebP preserves dimensions and multiplies existing
alpha. `model` defaults to `birefnet-general`; precision comes from server startup.
A model must already exist in the configured cache. Omit `output_path` for an
automatic name inside the prepared output directory.

## Cut and vectorize in one call

```json
{"image_path":"input/cut-vector.png","remove_background":true,"detail_level":"logo","color_mode":"color"}
```

Tool: `vectorize_image`. The motor creates a PNG intermediate, traces that exact
file and retains it. Read `source_image_path`, `traced_image_path`,
`intermediate_image.file_path` / `absolute_path` / `path_aliases`, and
`svg_path` / `svg_absolute_path` / `svg_path_aliases`. Report both deliverables.
Do not implement a separate remove/trace chain or use another asset's last output.
A tracing failure can expose the retained PNG in `details.intermediate_image`;
report partial completion rather than claiming SVG success.

## Preserve an image while tracing

```json
{"image_path":"input/vector.png","detail_level":"logo","color_mode":"color"}
```

`remove_background` defaults to false. This preserves opaque backgrounds and
existing alpha without loading AI. Use for plain vectorization or a verified
transparent cutout. Logo/light backgrounds are not automatic removal requests.
Presets: logo/low/medium/high; color modes: color/binary. Returned width/height are
SVG canvas dimensions; path count/file size do not approve visual quality.

## Convert

```json
{"image_path":"input/photo.png","target_format":"webp","lossless":true}
```

Formats png/webp/jpeg (`jpg` alias); quality 1–100, default 90. `lossless:true` is
supported only for WebP. JPEG composites alpha over white and returns a warning.

## Resize

```json
{"image_path":"input/photo.png","mode":"percentage","scale_percent":50}
```

```json
{"image_path":"input/photo.png","width":800,"mode":"fit"}
```

Use the user's actual target. `fit` preserves aspect ratio. `fill` crops and
requires both dimensions; `exact` requires both and may distort. `percentage`
requires scale_percent and no width/height. Filters: lanczos (default), bicubic,
bilinear, nearest. Default output PNG; explicit extensions can select WebP/JPEG.

## Results and recovery

Raster outputs include `image.file_path`, `absolute_path`, `path_aliases`, format,
dimensions and size; `alpha` describes transparency, `workspace` describes the root
and selected output directory. SVG has corresponding `svg_*` paths and canvas
width/height. Windows and WSL drive aliases are provided for compatible host
viewers; do not search for a returned path under an unrelated CWD.

In prepared MCP calls, omission of output_path selects automatic names and existing
output names receive numeric suffixes. Originals and existing files are preserved.
Explicit output paths must remain inside the selected output directory. If
`OUTPUT_EXISTS` still occurs (e.g. requesting the original path), choose a new
name/omit output_path. Never delete, overwrite or rename files to bypass a refusal.
`OUTPUT_DIRECTORY_MISMATCH` means use the prepared default or re-prepare the actual
user-requested output folder. Do not bypass errors through shell tools.

MCP exposes `structuredContent` plus text. Failures have `success:false`, `error`,
`message`, sometimes `details`, and `isError:true`. File-size reduction can be
negative; success means processing finished, not visual approval. View only returned
paths with available host viewers. If SVG rendering is unavailable, say so.

`list_models` / `get_model_info` inspect active precision and workspace without
loading weights; they do not replace preparation. `model verify` is a CLI command,
not an MCP tool. Missing FP32 can be downloaded during authorized setup; missing
experimental INT8 requires its prepared local artifact, not a precision switch.

For explicitly chosen CLI use: `pixellayer --workspace ACTUAL_TASK call TOOL
--json-file request.json`, with a UTF-8 request file and an explicit output path in
the task. CLI authorizes its chosen workspace per invocation; MCP preparation is
session-scoped. The legacy CLI refuses explicit collisions instead of replacing
files. CLI exit codes: 0 success, 1 execution error, 2 syntax error. Progress is
stderr; stdout is JSON except help/version. CLI is not a fallback to bypass a
mismatched MCP root. Image limit: 50 million pixels; EXIF is not preserved.

## Recover existing outputs (0.5.1)

After preparation, get_result_info accepts optional output_path inside the prepared
output directory. With {} it lists up to 100 supported files, without recursion.
Per-file results contain paths, bytes, raster dimensions/alpha, or SVG path count
and viewBox presence. Read status for every entry; inventory success does not mean
every file was inspected. It writes nothing and does not load inference. Source
provenance and timings from a lost response are not reconstructed.
