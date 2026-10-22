use crate::{
    contracts::*,
    error::{AppError, Result},
    files::Workspace,
    model::ModelManager,
};
use image::{imageops::FilterType, DynamicImage, ImageFormat};
use serde_json::{json, Value};
use std::{
    fs,
    io::Cursor,
    path::{Path, PathBuf},
    sync::Mutex,
    time::Instant,
};

pub const MAX_PIXELS: u64 = 50_000_000;
pub struct Engine {
    pub workspace: Workspace,
    pub models: ModelManager,
    pub require_preparation: bool,
    pub prepared_output: Mutex<Option<PathBuf>>,
}

impl Engine {
    pub fn context(&self) -> Value {
        let mut context = self.workspace.info();
        let output = self.prepared_output.lock().ok().and_then(|v| v.clone());
        context["prepared"] = json!(output.is_some());
        context["preparation_required"] = json!(self.require_preparation);
        if let Some(output) = output {
            context["output_directory"] = json!(self.workspace.relative(&output));
            context["output_absolute_directory"] = json!(Workspace::native(&output));
        }
        context
    }
    fn require_ready(&self) -> Result<()> {
        let ready = self
            .prepared_output
            .lock()
            .map_err(|_| AppError::new("WORKSPACE_ERROR", "Workspace lock unavailable"))?
            .is_some();
        if self.require_preparation && !ready {
            return Err(AppError::new("WORKSPACE_NOT_PREPARED", "Call prepare_workspace with the caller's actual project directory and requested output directory before processing. Do not guess paths, copy files to another root or search the filesystem.")
                .with_details(json!({"workspace": self.context()})));
        }
        Ok(())
    }
    fn output(
        &self,
        input: &Path,
        explicit: Option<&str>,
        suffix: &str,
        ext: &str,
    ) -> Result<PathBuf> {
        let prepared = self
            .prepared_output
            .lock()
            .map_err(|_| AppError::new("WORKSPACE_ERROR", "Workspace lock unavailable"))?
            .clone();
        let default = prepared.as_ref().map(|dir| {
            self.workspace.relative(&dir.join(format!(
                "{}{suffix}.{ext}",
                input.file_stem().unwrap().to_string_lossy()
            )))
        });
        let path = self.workspace.output(
            input,
            explicit.or(default.as_deref()),
            suffix,
            ext,
            self.require_preparation,
        )?;
        if let Some(directory) = prepared {
            if !path.starts_with(&directory) {
                return Err(AppError::new("OUTPUT_DIRECTORY_MISMATCH", "Output must be inside the directory selected by prepare_workspace. Use its default output or prepare the user-requested directory first.")
                    .with_details(json!({"workspace": self.context(), "requested_output": explicit})));
            }
        }
        Ok(path)
    }
    pub fn prepare(&self, args: PrepareArgs) -> Result<Value> {
        // Invalidate the old destination first, including failed/reused preparations.
        *self
            .prepared_output
            .lock()
            .map_err(|_| AppError::new("WORKSPACE_ERROR", "Workspace lock unavailable"))? = None;
        if !self.workspace.matches(&args.expected_workspace) {
            return Err(AppError::new("WORKSPACE_MISMATCH", "The MCP workspace differs from the caller's project. Stop processing and correct only the selected MCP --workspace configuration through authorized setup. Do not copy images, change the expected directory to silence this error, or search other folders.")
                .with_details(json!({"expected_workspace": args.expected_workspace, "workspace": self.context()})));
        }
        let input_dir = self.workspace.directory(&args.input_directory)?;
        let output_dir = self.workspace.directory(&args.output_directory)?;
        let input_exists = input_dir.is_dir();
        let mut images = Vec::new();
        let mut truncated = false;
        if input_exists {
            let mut entries = fs::read_dir(&input_dir)?.collect::<std::io::Result<Vec<_>>>()?;
            entries.sort_by_key(|entry| entry.file_name());
            for entry in entries {
                let path = entry.path();
                let ext = path
                    .extension()
                    .and_then(|v| v.to_str())
                    .unwrap_or("")
                    .to_ascii_lowercase();
                if !matches!(ext.as_str(), "png" | "webp" | "jpg" | "jpeg") {
                    continue;
                }
                if images.len() == 100 {
                    truncated = true;
                    break;
                }
                let relative = self.workspace.relative(&path);
                match self.workspace.input(&relative).and_then(|path| Ok((self.open(&path)?, fs::metadata(&path)?.len()))) {
                    Ok((image, size)) => images.push(json!({"image_path": relative,
                        "absolute_path": Workspace::native(&path), "path_aliases": Workspace::path_aliases(&path), "width": image.width(), "height": image.height(),
                        "file_size_bytes": size, "alpha": alpha_info(&image), "status": "ready"})),
                    Err(error) => images.push(json!({"image_path": relative, "status": "error", "error": error.json()})),
                }
            }
        }
        let ready_count = images
            .iter()
            .filter(|item| item["status"] == "ready")
            .count();
        let error_count = images.len() - ready_count;
        let input_absolute = Workspace::native(&input_dir);
        let (input_status, next_step) = if !input_exists {
            ("missing_directory", format!("The input directory does not exist: {input_absolute}. Input paths are relative to the authorized workspace. Ask the user to make the requested images available there through the client's authorized file workflow, or prepare a user-selected folder inside the workspace (input_directory: \".\" selects its root). No image_path was returned. Do not create/copy files automatically, search outside the workspace or change expected_workspace to silence a mismatch."))
        } else if images.is_empty() {
            ("no_supported_images", format!("The input directory exists but contains no directly listed PNG, WebP or JPEG images: {input_absolute}. Subfolders are not scanned recursively. Ask the user to supply images there or select the intended subfolder inside the workspace; input_directory: \".\" selects its root. No image_path was returned. Do not search outside the workspace or copy files to bypass a mismatch."))
        } else if ready_count == 0 {
            ("unreadable_images", format!("No readable image was found in {input_absolute}. Report each returned image error and ask the user to provide a supported readable image or select another authorized input folder. Do not process status:error entries or claim that images were processed."))
        } else if error_count > 0 {
            ("partially_readable", "Use only returned images with status:ready; report status:error entries separately. Omit output_path for automatic names in the selected output directory. For cut + SVG use vectorize_image(remove_background=true); the engine keeps the PNG. Do not search for replacements outside the workspace.".to_string())
        } else {
            ("ready", "Use an exact returned image_path with status:ready. Omit output_path for automatic names in the selected output directory. For cut + SVG use vectorize_image(remove_background=true); the engine keeps the PNG. Never use shell to locate, delete or move outputs.".to_string())
        };
        let input_relative = self.workspace.relative(&input_dir);
        *self
            .prepared_output
            .lock()
            .map_err(|_| AppError::new("WORKSPACE_ERROR", "Workspace lock unavailable"))? =
            Some(output_dir);
        Ok(
            json!({"success": true, "workspace": self.context(), "models": [self.models.info()],
            "input_directory": if input_relative.is_empty() { "." } else { &input_relative },
            "input_directory_exists": input_exists, "input_absolute_directory": input_absolute,
            "input_path_aliases": Workspace::path_aliases(&input_dir),
            "input_status": input_status, "input_ready": ready_count > 0,
            "ready_count": ready_count, "error_count": error_count,
            "images": images, "truncated": truncated,
            "next_step": next_step}),
        )
    }
    pub fn call(&self, tool: &str, params: Value) -> Result<Value> {
        match tool {
            "prepare_workspace" => self.prepare(serde_json::from_value(params)?),
            "convert_format" => self.convert(serde_json::from_value(params)?),
            "resize_image" => self.resize(serde_json::from_value(params)?),
            "vectorize_image" => self.vectorize(serde_json::from_value(params)?),
            "remove_background" => self.remove(serde_json::from_value(params)?),
            "get_result_info" => self.result_info(serde_json::from_value(params)?),
            "list_models" => {
                let _: EmptyArgs = serde_json::from_value(params)?;
                Ok(
                    json!({"success": true, "models": [self.models.info()], "workspace": self.context()}),
                )
            }
            "get_model_info" => {
                let args: ModelArgs = serde_json::from_value(params)?;
                ModelManager::check_id(&args.model_id)?;
                Ok(
                    json!({"success": true, "model": self.models.info(), "workspace": self.context()}),
                )
            }
            _ => Err(AppError::new(
                "TOOL_NOT_FOUND",
                "Unknown tool; use --help or MCP tools/list",
            )),
        }
    }
    fn open(&self, path: &Path) -> Result<DynamicImage> {
        let mut reader = image::ImageReader::open(path)?.with_guessed_format()?;
        if !matches!(
            reader.format(),
            Some(ImageFormat::Png | ImageFormat::WebP | ImageFormat::Jpeg)
        ) {
            return Err(AppError::new(
                "UNSUPPORTED_FORMAT",
                "Supported raster formats: PNG, WebP, JPEG",
            ));
        }
        let mut limits = image::Limits::default();
        limits.max_alloc = Some(512 * 1024 * 1024);
        reader.limits(limits);
        // Check dimensions before decoding and allocating the full image.
        let (width, height) = image::ImageReader::open(path)?
            .with_guessed_format()?
            .into_dimensions()?;
        check_dimensions(width, height)?;
        Ok(reader.decode()?)
    }
    fn image_result(
        &self,
        input: &Path,
        out: &Path,
        image: &DynamicImage,
        format: Format,
        start: Instant,
    ) -> Result<Value> {
        let size = fs::metadata(out)?.len();
        let original = fs::metadata(input)?.len();
        Ok(
            json!({"success": true, "image": {"file_path": self.workspace.relative(out), "absolute_path": Workspace::native(out), "path_aliases": Workspace::path_aliases(out),
            "format": format.extension(), "width": image.width(), "height": image.height(),
            "file_size_bytes": size, "file_size_human": human_size(size)},
            "source_image_path": self.workspace.relative(input), "source_absolute_path": Workspace::native(input),
            "workspace": self.context(), "alpha": if format == Format::Jpeg { json!({"channel_present": false, "has_transparency": false, "min": 255, "max": 255}) } else { alpha_info(image) }, "visual_review": "not_performed",
            "original_size_bytes": original,
            "reduction_percent": if original == 0 { 0.0 } else { ((1.0 - size as f64 / original as f64) * 10000.0).round() / 100.0 },
            "processing_time_ms": start.elapsed().as_millis()}),
        )
    }
    pub fn convert(&self, args: ConvertArgs) -> Result<Value> {
        let start = Instant::now();
        self.require_ready()?;
        if !(1..=100).contains(&args.quality) {
            return Err(AppError::invalid("quality must be between 1 and 100"));
        }
        if args.lossless && args.target_format != Format::Webp {
            return Err(AppError::invalid("lossless is supported for WebP only"));
        }
        let input = self.workspace.input(&args.image_path)?;
        let out = self.output(
            &input,
            args.output_path.as_deref(),
            "_converted",
            args.target_format.extension(),
        )?;
        let image = self.open(&input)?;
        let (bytes, warning) = encode(&image, args.target_format, args.quality, args.lossless)?;
        self.workspace.write(&out, &bytes)?;
        let mut result = self.image_result(&input, &out, &image, args.target_format, start)?;
        result["original_format"] = json!(image::ImageReader::open(input)?
            .with_guessed_format()?
            .format()
            .map(|f| f.extensions_str()[0]));
        if let Some(warning) = warning {
            result["warnings"] = json!([warning]);
        }
        Ok(result)
    }
    pub fn resize(&self, args: ResizeArgs) -> Result<Value> {
        let start = Instant::now();
        self.require_ready()?;
        let input = self.workspace.input(&args.image_path)?;
        let image = self.open(&input)?;
        let (w, h) = (image.width(), image.height());
        if args.width == Some(0) || args.height == Some(0) {
            return Err(AppError::invalid("Dimensions must be positive"));
        }
        let (width, height) = match args.mode {
            ResizeMode::Percentage => {
                if args.width.is_some() || args.height.is_some() {
                    return Err(AppError::invalid("percentage mode uses scale_percent only"));
                }
                let scale = args
                    .scale_percent
                    .ok_or_else(|| AppError::invalid("percentage mode requires scale_percent"))?;
                if !scale.is_finite() || scale <= 0.0 {
                    return Err(AppError::invalid(
                        "scale_percent must be finite and positive",
                    ));
                }
                (
                    ((w as f64 * scale / 100.0).round().max(1.0)) as u32,
                    ((h as f64 * scale / 100.0).round().max(1.0)) as u32,
                )
            }
            _ => {
                if args.scale_percent.is_some() {
                    return Err(AppError::invalid("scale_percent requires mode percentage"));
                }
                if matches!(args.mode, ResizeMode::Fill | ResizeMode::Exact)
                    && (args.width.is_none() || args.height.is_none())
                {
                    return Err(AppError::invalid("fill and exact require width and height"));
                }
                match (args.width, args.height) {
                    (Some(w), Some(h)) => (w, h),
                    (Some(width), None) => (
                        width,
                        ((h as f64 * width as f64 / w as f64).round().max(1.0)) as u32,
                    ),
                    (None, Some(height)) => (
                        ((w as f64 * height as f64 / h as f64).round().max(1.0)) as u32,
                        height,
                    ),
                    _ => return Err(AppError::invalid("Specify width or height")),
                }
            }
        };
        check_dimensions(width, height)?;
        let filter = match args.resample {
            Resample::Lanczos => FilterType::Lanczos3,
            Resample::Bicubic => FilterType::CatmullRom,
            Resample::Bilinear => FilterType::Triangle,
            Resample::Nearest => FilterType::Nearest,
        };
        // Cap the intermediate fill image too; extreme aspect ratios can otherwise allocate huge buffers.
        if matches!(args.mode, ResizeMode::Fill) {
            let scale = (width as f64 / w as f64).max(height as f64 / h as f64);
            if (w as f64 * scale).ceil() * (h as f64 * scale).ceil() > MAX_PIXELS as f64 {
                return Err(AppError::invalid(
                    "Fill intermediate exceeds the 50 million pixel limit",
                ));
            }
        }
        let resized = match args.mode {
            ResizeMode::Fit => image.resize(width, height, filter),
            ResizeMode::Fill => image.resize_to_fill(width, height, filter),
            _ => image.resize_exact(width, height, filter),
        };
        // PNG is the default to retain transparency; explicit output may select a supported format.
        let format = output_format(args.output_path.as_deref())?;
        let out = self.output(
            &input,
            args.output_path.as_deref(),
            "_resized",
            format.extension(),
        )?;
        let (bytes, warning) = encode(&resized, format, 90, true)?;
        self.workspace.write(&out, &bytes)?;
        let mut result = self.image_result(&input, &out, &resized, format, start)?;
        result["original_width"] = json!(w);
        result["original_height"] = json!(h);
        if let Some(warning) = warning {
            result["warnings"] = json!([warning]);
        }
        Ok(result)
    }
    pub fn remove(&self, args: RemoveArgs) -> Result<Value> {
        let start = Instant::now();
        self.require_ready()?;
        ModelManager::check_id(&args.model)?;
        if args.output_format == Format::Jpeg {
            return Err(AppError::invalid(
                "Background removal requires PNG or WebP to retain alpha",
            ));
        }
        let input = self.workspace.input(&args.image_path)?;
        let out = self.output(
            &input,
            args.output_path.as_deref(),
            "_nobg",
            args.output_format.extension(),
        )?;
        let phase = Instant::now();
        let image = self.open(&input)?;
        let decode_ms = phase.elapsed().as_secs_f64() * 1000.0;
        let (rgba, mut inference) = self.models.remove(&image)?;
        let result_image = DynamicImage::ImageRgba8(rgba);
        let phase = Instant::now();
        let (bytes, _) = encode(&result_image, args.output_format, 100, true)?;
        self.workspace.write(&out, &bytes)?;
        inference["timings_ms"]["encode_write_ms"] = json!(phase.elapsed().as_secs_f64() * 1000.0);
        inference["timings_ms"]["decode_ms"] = json!(decode_ms);
        let mut result =
            self.image_result(&input, &out, &result_image, args.output_format, start)?;
        result["model_used"] = json!(args.model);
        result["inference"] = inference;
        Ok(result)
    }
    pub fn vectorize(&self, args: VectorArgs) -> Result<Value> {
        let start = Instant::now();
        self.require_ready()?;
        let input = self.workspace.input(&args.image_path)?;
        let out = self.output(&input, args.output_path.as_deref(), "_vector", "svg")?;
        if args.remove_background {
            let png_path = out.with_file_name(format!(
                "{}_nobg.png",
                out.file_stem().unwrap().to_string_lossy()
            ));
            let removed = self.remove(RemoveArgs {
                image_path: args.image_path.clone(),
                model: crate::model::MODEL_ID.into(),
                output_path: Some(self.workspace.relative(&png_path)),
                output_format: Format::Png,
            })?;
            let png = removed["image"]["file_path"].as_str().ok_or_else(|| {
                AppError::new("PROCESSING_ERROR", "Missing intermediate PNG path")
            })?;
            let mut traced = self.vectorize(VectorArgs {
                image_path: png.into(), remove_background: false,
                detail_level: args.detail_level, color_mode: args.color_mode,
                output_path: Some(self.workspace.relative(&out)),
            }).map_err(|error| error.with_details(json!({"partial": true, "stage": "vectorize",
                "source_image_path": self.workspace.relative(&input), "intermediate_image": removed["image"],
                "workspace": self.context(), "recovery": "PNG retained; report partial result. Do not delete outputs."})))?;
            let vector_ms = traced["processing_time_ms"].clone();
            traced["traced_image_size_bytes"] = traced["original_size_bytes"].clone();
            traced["original_size_bytes"] = json!(fs::metadata(&input)?.len());
            traced["intermediate_image"] = removed["image"].clone();
            traced["intermediate_alpha"] = removed["alpha"].clone();
            traced["inference"] = removed["inference"].clone();
            traced["operation"] = json!("remove_background_then_vectorize");
            traced["traced_image_path"] = json!(png);
            traced["source_image_path"] = json!(self.workspace.relative(&input));
            traced["source_absolute_path"] = json!(Workspace::native(&input));
            traced["stages_ms"] =
                json!({"remove_background": removed["processing_time_ms"], "vectorize": vector_ms});
            traced["processing_time_ms"] = json!(start.elapsed().as_millis());
            return Ok(traced);
        }
        let mut image = self.open(&input)?.to_rgba8();
        for p in image.pixels_mut() {
            p[3] = if p[3] > 50 { 255 } else { 0 };
        }
        let (width, height) = image.dimensions();
        let mut config = vtracer::Config::default();
        let (precision, difference, corner, length, splice, speckle, path_precision) =
            match args.detail_level {
                Detail::Logo => (6, 20, 80, 6.0, 60, 10, 4),
                Detail::Low => (4, 32, 120, 8.0, 90, 8, 3),
                Detail::Medium => (6, 16, 60, 4.0, 45, 4, 5),
                Detail::High => (8, 8, 30, 2.0, 22, 2, 8),
            };
        config.color_mode = match args.color_mode {
            ColorMode::Color => vtracer::ColorMode::Color,
            ColorMode::Binary => vtracer::ColorMode::Binary,
        };
        config.color_precision = precision;
        config.layer_difference = difference;
        config.corner_threshold = corner;
        config.length_threshold = length;
        config.splice_threshold = splice;
        config.filter_speckle = speckle;
        config.path_precision = Some(path_precision);
        let source = vtracer::ColorImage {
            pixels: image.into_raw(),
            width: width as usize,
            height: height as usize,
        };
        let svg = vtracer::convert(source, config)
            .map_err(|e| AppError::new("PROCESSING_ERROR", e))?
            .to_string();
        // Keep the intrinsic size while supporting responsive embedding.
        let svg = svg.replacen(
            "<svg ",
            &format!("<svg viewBox=\"0 0 {width} {height}\" "),
            1,
        );
        self.workspace.write(&out, svg.as_bytes())?;
        Ok(
            json!({"success": true, "svg_path": self.workspace.relative(&out), "svg_absolute_path": Workspace::native(&out), "svg_path_aliases": Workspace::path_aliases(&out), "visual_review": "not_performed",
            "width": width, "height": height, "source_image_path": self.workspace.relative(&input),
            "source_absolute_path": Workspace::native(&input), "workspace": self.context(), "svg_size_bytes": svg.len(),
            "svg_size_human": human_size(svg.len() as u64), "original_size_bytes": fs::metadata(input)?.len(),
            "path_count": svg.matches("<path").count(), "processing_time_ms": start.elapsed().as_millis()}),
        )
    }

    pub fn result_info(&self, args: ResultInfoArgs) -> Result<Value> {
        self.require_ready()?;
        let prepared_directory = self
            .prepared_output
            .lock()
            .map_err(|_| AppError::new("WORKSPACE_ERROR", "Workspace lock unavailable"))?
            .clone();
        let directory = match prepared_directory {
            Some(directory) => directory,
            None if !self.require_preparation => match args.output_path.as_deref() {
                Some(raw) => self.workspace.input(raw)?.parent().unwrap().to_path_buf(),
                None => self.workspace.directory("output")?,
            },
            None => {
                return Err(AppError::new(
                    "WORKSPACE_NOT_PREPARED",
                    "Prepare the output directory first",
                ))
            }
        };
        let mut paths = if let Some(raw) = args.output_path {
            vec![self.workspace.input(&raw)?]
        } else if directory.is_dir() {
            let mut paths = Vec::new();
            for entry in fs::read_dir(&directory)? {
                let path = entry?.path();
                if path.extension().and_then(|v| v.to_str()).is_some_and(|e| {
                    matches!(
                        e.to_ascii_lowercase().as_str(),
                        "png" | "webp" | "jpg" | "jpeg" | "svg"
                    )
                }) {
                    paths.push(path);
                }
            }
            paths
        } else {
            Vec::new()
        };
        paths.sort();
        let truncated = paths.len() > 100;
        let mut results = Vec::new();
        for path in paths.into_iter().take(100) {
            let relative = self.workspace.relative(&path);
            let entry = (|| -> Result<Value> {
                let path = self.workspace.input(&relative)?;
                if !path.starts_with(&directory) {
                    return Err(AppError::new(
                        "OUTPUT_DIRECTORY_MISMATCH",
                        "Read only outputs inside the prepared output directory",
                    ));
                }
                let size = fs::metadata(&path)?.len();
                let mut value = json!({"status": "ready", "file_path": self.workspace.relative(&path),
                    "absolute_path": Workspace::native(&path), "path_aliases": Workspace::path_aliases(&path),
                    "file_size_bytes": size, "visual_review": "not_performed"});
                if path
                    .extension()
                    .is_some_and(|e| e.eq_ignore_ascii_case("svg"))
                {
                    if size > 64 * 1024 * 1024 {
                        return Err(AppError::invalid("SVG metadata inspection limit is 64 MiB"));
                    }
                    let svg = fs::read_to_string(&path)?;
                    value["format"] = json!("svg");
                    value["path_count"] = json!(svg.matches("<path").count());
                    value["has_view_box"] = json!(svg.contains("viewBox="));
                    value["xml_validation_performed"] = json!(false);
                } else {
                    let image = self.open(&path)?;
                    value["width"] = json!(image.width());
                    value["height"] = json!(image.height());
                    value["alpha"] = alpha_info(&image);
                }
                Ok(value)
            })();
            results.push(match entry {
                Ok(value) => value,
                Err(error) => {
                    json!({"file_path": relative, "status": "error", "error": error.json()})
                }
            });
        }
        Ok(
            json!({"success": true, "workspace": self.context(), "results": results, "truncated": truncated,
            "processing_repeated": false, "historical_inference_metadata_available": false,
            "next_step": "Use the existing returned paths. This reads current file metadata, not historical timings or visual quality. Do not repeat completed image operations to recover a response."}),
        )
    }
}

fn alpha_info(image: &DynamicImage) -> Value {
    if !image.color().has_alpha() {
        return json!({"channel_present": false, "has_transparency": false, "min": 255, "max": 255});
    }
    let rgba = image.to_rgba8();
    let (min, max) = rgba
        .pixels()
        .fold((255u8, 0u8), |(lo, hi), p| (lo.min(p[3]), hi.max(p[3])));
    json!({"channel_present": true, "has_transparency": min < 255, "min": min, "max": max})
}

fn check_dimensions(width: u32, height: u32) -> Result<()> {
    if width == 0 || height == 0 || width as u64 * height as u64 > MAX_PIXELS {
        return Err(AppError::invalid(
            "Image must have positive dimensions and at most 50 million pixels",
        ));
    }
    Ok(())
}
fn output_format(path: Option<&str>) -> Result<Format> {
    match path
        .and_then(|p| Path::new(p).extension())
        .and_then(|e| e.to_str())
        .map(str::to_ascii_lowercase)
        .as_deref()
    {
        None | Some("png") => Ok(Format::Png),
        Some("webp") => Ok(Format::Webp),
        Some("jpg" | "jpeg") => Ok(Format::Jpeg),
        _ => Err(AppError::new(
            "UNSUPPORTED_FORMAT",
            "Output must be PNG, WebP or JPEG",
        )),
    }
}
fn human_size(size: u64) -> String {
    if size < 1024 {
        format!("{size} B")
    } else if size < 1024 * 1024 {
        format!("{:.1} KiB", size as f64 / 1024.0)
    } else {
        format!("{:.1} MiB", size as f64 / 1048576.0)
    }
}
fn encode(
    image: &DynamicImage,
    format: Format,
    quality: u8,
    lossless: bool,
) -> Result<(Vec<u8>, Option<&'static str>)> {
    let mut cursor = Cursor::new(Vec::new());
    match format {
        Format::Png => image.write_to(&mut cursor, ImageFormat::Png)?,
        Format::Webp => {
            let rgba = image.to_rgba8();
            let encoder = webp::Encoder::from_rgba(rgba.as_raw(), image.width(), image.height());
            let bytes = if lossless {
                encoder.encode_lossless()
            } else {
                encoder.encode(quality as f32)
            };
            return Ok((bytes.to_vec(), None));
        }
        Format::Jpeg => {
            let rgba = image.to_rgba8();
            let transparent = rgba.pixels().any(|p| p[3] != 255);
            let mut rgb = image.to_rgb8();
            if transparent {
                for (dest, source) in rgb.pixels_mut().zip(rgba.pixels()) {
                    let alpha = source[3] as u32;
                    for c in 0..3 {
                        dest[c] =
                            ((source[c] as u32 * alpha + 255 * (255 - alpha) + 127) / 255) as u8;
                    }
                }
            }
            image::codecs::jpeg::JpegEncoder::new_with_quality(&mut cursor, quality)
                .encode_image(&rgb)?;
            return Ok((
                cursor.into_inner(),
                transparent.then_some("JPEG has no alpha; transparency was composited over white."),
            ));
        }
    }
    Ok((cursor.into_inner(), None))
}
