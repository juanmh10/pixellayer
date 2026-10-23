use crate::error::{AppError, Result};
use image::{imageops::FilterType, DynamicImage, GrayImage, RgbaImage};
use ort::{session::Session, value::Tensor};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{Read, Seek, SeekFrom, Write},
    path::{Path, PathBuf},
    sync::Mutex,
    time::{Duration, Instant},
};

pub const MODEL_ID: &str = "birefnet-general";
pub const REVISION: &str = "534d3c82d3bb8b2f0867db6dfbc3a525b8e42f67";

#[derive(Debug, Clone, Copy, clap::ValueEnum, Default)]
pub enum Precision {
    #[default]
    Fp32,
    Int8,
}
impl Precision {
    pub fn name(self) -> &'static str {
        match self {
            Self::Fp32 => "fp32",
            Self::Int8 => "int8",
        }
    }
    fn spec(self) -> ModelSpec {
        match self {
            Self::Fp32 => ModelSpec {
                file: "birefnet-general-fp32-534d3c82.onnx",
                sha: "58f621f00f5d756097615970a88a791584600dcf7c45b18a0a6267535a1ebd3c",
                size: 972_666_916,
                url: Some("https://huggingface.co/onnx-community/BiRefNet-ONNX/resolve/534d3c82d3bb8b2f0867db6dfbc3a525b8e42f67/onnx/model.onnx"),
                variant: "birefnet-general-fp32-534d3c82",
            },
            Self::Int8 => ModelSpec {
                file: "birefnet-general-int8-dynamic-v1.onnx",
                sha: "9bbbe01d6fae545257715c012266692b3fa6f68a05a992ae1d527bef059e8c30",
                size: 391_300_624,
                url: None,
                variant: "birefnet-general-int8-dynamic-v1",
            },
        }
    }
}
struct ModelSpec {
    file: &'static str,
    sha: &'static str,
    size: u64,
    url: Option<&'static str>,
    variant: &'static str,
}

struct Loaded {
    session: Session,
    last_used: Instant,
}
pub struct ModelManager {
    cache: PathBuf,
    precision: Precision,
    runtime: Option<PathBuf>,
    threads: usize,
    ttl: Duration,
    state: Mutex<Option<Loaded>>,
}

impl ModelManager {
    pub fn new(
        cache: PathBuf,
        runtime: Option<PathBuf>,
        threads: usize,
        ttl_secs: u64,
        precision: Precision,
    ) -> Self {
        Self {
            cache,
            precision,
            runtime,
            threads,
            ttl: Duration::from_secs(ttl_secs),
            state: Mutex::new(None),
        }
    }
    pub fn path(&self) -> PathBuf {
        self.cache.join(self.precision.spec().file)
    }
    pub fn check_id(id: &str) -> Result<()> {
        if id != MODEL_ID {
            return Err(AppError::new(
                "MODEL_NOT_FOUND",
                "This port supports birefnet-general only",
            ));
        }
        Ok(())
    }
    pub fn info(&self) -> Value {
        let spec = self.precision.spec();
        let loaded = self.state.lock().map(|s| s.is_some()).unwrap_or(false);
        json!({"id": MODEL_ID, "name": format!("BiRefNet General ONNX {}", self.precision.name()), "license": "MIT",
            "source": "onnx-community/BiRefNet-ONNX", "base_model": "ZhengPeng7/BiRefNet",
            "revision": REVISION, "sha256": spec.sha, "download_size_bytes": spec.size,
            "variant": spec.variant, "cache_filename": spec.file, "threads": self.threads,
            "size_bytes": spec.size,
            "artifact_origin": if matches!(self.precision, Precision::Int8) { "local derivation; experimental artifact supplied separately" } else { "pinned upstream ONNX" },
            "experimental": matches!(self.precision, Precision::Int8),
            "download_available": spec.url.is_some(),
            "quantization": if matches!(self.precision, Precision::Int8) { "dynamic constant-weight MatMul INT8 per-channel; Conv and remaining operators FP32" } else { "none" },
            "downloaded": self.path().is_file(), "loaded": loaded, "input_size": [1024, 1024],
            "precision": self.precision.name(), "device": "cpu", "ttl_seconds": self.ttl.as_secs(),
            "runtime_version": "1.22.0"})
    }
    pub fn verify(&self) -> Result<Value> {
        verify_file(&self.path(), &self.precision.spec())?;
        Ok(json!({"success": true, "model": self.info(), "integrity_verified": true}))
    }
    pub fn download(&self) -> Result<Value> {
        if self.path().exists() {
            return self.verify();
        }
        let spec = self.precision.spec();
        let url = spec.url.ok_or_else(|| AppError::new("MODEL_NOT_DOWNLOADABLE",
            "INT8 is a local experimental artifact, not a published download. See docs/handoff-int8-ab.md for the pinned artifact and generation recipe."))?;
        fs::create_dir_all(&self.cache)?;
        let mut temp = tempfile::NamedTempFile::new_in(&self.cache)?;
        eprintln!(
            "Downloading BiRefNet {} ({} bytes); no images are uploaded.",
            self.precision.name(),
            spec.size
        );
        let client = reqwest::blocking::Client::builder()
            .https_only(true)
            .connect_timeout(Duration::from_secs(30))
            .timeout(Duration::from_secs(1800))
            .user_agent(concat!("pixellayer-rust/", env!("CARGO_PKG_VERSION")))
            .build()
            .map_err(|e| download_error(e, "client", 0))?;
        let mut hash = Sha256::new();
        let mut total = 0_u64;
        // Keep the same temporary file across bounded retries. It is never a valid
        // cache entry until the pinned size/hash have both been verified.
        for attempt in 1..=3 {
            match download_attempt(&client, url, &spec, &mut temp, &mut hash, &mut total) {
                Ok(()) => break,
                Err(mut error) => {
                    let retryable = error
                        .details
                        .as_ref()
                        .and_then(|d| d["retryable"].as_bool())
                        .unwrap_or(false);
                    if let Some(details) = error.details.as_mut() {
                        details["attempt"] = json!(attempt);
                        details["max_attempts"] = json!(3);
                    }
                    if !retryable || attempt == 3 {
                        return Err(error);
                    }
                    eprintln!(
                        "Download interrupted at {total}/{} bytes; retry {}/3 in {attempt}s.",
                        spec.size,
                        attempt + 1
                    );
                    std::thread::sleep(Duration::from_secs(attempt));
                }
            }
        }
        if total != spec.size || format!("{:x}", hash.finalize()) != spec.sha {
            return Err(AppError::new(
                "MODEL_INTEGRITY_ERROR",
                "Model size or SHA-256 does not match the pinned artifact",
            ));
        }
        temp.as_file().sync_all()?;
        match temp.persist_noclobber(self.path()) {
            Ok(_) => {}
            Err(e) if e.error.kind() == std::io::ErrorKind::AlreadyExists => {
                verify_file(&self.path(), &self.precision.spec())?;
            }
            Err(e) => return Err(e.error.into()),
        }
        Ok(json!({"success": true, "model": self.info(), "integrity_verified": true}))
    }
    pub fn configured_runtime_path(&self) -> Result<PathBuf> {
        let path = if let Some(ref path) = self.runtime {
            crate::files::Workspace::client_path(&path.to_string_lossy())
        } else {
            let executable = std::env::current_exe()?;
            executable.parent().unwrap().join(if cfg!(windows) {
                "onnxruntime.dll"
            } else if cfg!(target_os = "macos") {
                "libonnxruntime.dylib"
            } else {
                "libonnxruntime.so"
            })
        };
        Ok(std::path::absolute(path)?)
    }
    fn runtime_path(&self) -> Result<PathBuf> {
        let path = self.configured_runtime_path()?;
        if !path.is_file() {
            return Err(AppError::new("RUNTIME_NOT_FOUND", "ONNX Runtime 1.22.0 library is missing. Place it beside the executable or set PIXELLAYER_ORT_DYLIB."));
        }
        Ok(path)
    }
    pub fn unload_idle(&self) {
        if let Ok(mut state) = self.state.try_lock() {
            if state
                .as_ref()
                .is_some_and(|s| s.last_used.elapsed() >= self.ttl)
            {
                *state = None;
                eprintln!("Unloaded idle BiRefNet session.");
            }
        }
    }
    pub fn remove(&self, image: &DynamicImage) -> Result<(RgbaImage, Value)> {
        let mut timings = json!({"integrity_ms": 0.0, "session_load_ms": 0.0});
        let mut state = self
            .state
            .lock()
            .map_err(|_| AppError::new("MODEL_LOAD_ERROR", "Model session lock is unavailable"))?;
        let session_cold = state.is_none();
        if session_cold {
            if !self.path().is_file() {
                let message = match self.precision {
                    Precision::Fp32 => "Run `pixellayer model download` with the same cache directory before background removal.",
                    Precision::Int8 => "Pinned experimental INT8 artifact is missing; see docs/handoff-int8-ab.md. No automatic download or FP32 fallback is performed.",
                };
                return Err(AppError::new("MODEL_NOT_DOWNLOADED", message));
            }
            let phase = Instant::now();
            verify_file(&self.path(), &self.precision.spec())?;
            timings["integrity_ms"] = json!(phase.elapsed().as_secs_f64() * 1000.0);
            let phase = Instant::now();
            let runtime = self.runtime_path()?;
            eprintln!(
                "Loading BiRefNet {} on CPU ({} threads).",
                self.precision.name(),
                self.threads
            );
            // The wrapper can panic on DLL load/version errors. Keep those failures out of stdout.
            let session = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| -> Result<Session> {
                ort::init_from(runtime.to_string_lossy()).with_name("pixellayer").commit()?;
                Ok(Session::builder()?.with_intra_threads(self.threads)?
                    .commit_from_file(self.path())?)
            })).map_err(|_| AppError::new("MODEL_LOAD_ERROR", "Unable to load ONNX Runtime; check version 1.22.0, architecture and native dependencies"))??;
            timings["session_load_ms"] = json!(phase.elapsed().as_secs_f64() * 1000.0);
            *state = Some(Loaded {
                session,
                last_used: Instant::now(),
            });
        }
        let loaded = state.as_mut().unwrap();
        let inference = (|| -> Result<RgbaImage> {
            let phase = Instant::now();
            let rgb = image.to_rgb8();
            let resized = image::imageops::resize(&rgb, 1024, 1024, FilterType::Triangle);
            let mut data = vec![0_f32; 3 * 1024 * 1024];
            let mean = [0.485_f32, 0.456, 0.406];
            let std = [0.229_f32, 0.224, 0.225];
            for (i, pixel) in resized.pixels().enumerate() {
                for c in 0..3 {
                    data[c * 1024 * 1024 + i] = (pixel[c] as f32 / 255.0 - mean[c]) / std[c];
                }
            }
            let tensor = Tensor::from_array(([1usize, 3, 1024, 1024], data.into_boxed_slice()))?;
            timings["preprocess_ms"] = json!(phase.elapsed().as_secs_f64() * 1000.0);
            let phase = Instant::now();
            let outputs = loaded.session.run(ort::inputs!["input_image" => tensor])?;
            timings["inference_ms"] = json!(phase.elapsed().as_secs_f64() * 1000.0);
            let phase = Instant::now();
            let output = outputs.get("output_image").ok_or_else(|| {
                AppError::new("MODEL_CONTRACT_ERROR", "Expected output_image tensor")
            })?;
            let (shape, logits) = output.try_extract_tensor::<f32>()?;
            if shape.as_ref() != [1, 1, 1024, 1024] || logits.len() != 1024 * 1024 {
                return Err(AppError::new(
                    "MODEL_CONTRACT_ERROR",
                    "Expected float32 output [1,1,1024,1024]",
                ));
            }
            let mask: Vec<u8> = logits
                .iter()
                .map(|v| ((1.0 / (1.0 + (-v).exp())) * 255.0) as u8)
                .collect();
            let mask = GrayImage::from_raw(1024, 1024, mask).unwrap();
            let mask =
                image::imageops::resize(&mask, image.width(), image.height(), FilterType::Triangle);
            let mut rgba = image.to_rgba8();
            for (pixel, alpha) in rgba.pixels_mut().zip(mask.pixels()) {
                // Retain pre-existing transparency rather than making transparent pixels opaque.
                pixel[3] = ((pixel[3] as u16 * alpha[0] as u16 + 127) / 255) as u8;
            }
            timings["postprocess_ms"] = json!(phase.elapsed().as_secs_f64() * 1000.0);
            Ok(rgba)
        })();
        loaded.last_used = Instant::now();
        Ok((
            inference?,
            json!({"precision": self.precision.name(), "variant": self.precision.spec().variant,
            "sha256": self.precision.spec().sha, "threads": self.threads, "session_cold": session_cold,
            "timings_ms": timings}),
        ))
    }
}

fn verify_file(path: &Path, spec: &ModelSpec) -> Result<()> {
    if !path.is_file() {
        return Err(AppError::new(
            "MODEL_NOT_DOWNLOADED",
            "Run `pixellayer model download` first",
        ));
    }
    let mut file = fs::File::open(path)?;
    if file.metadata()?.len() != spec.size {
        return Err(AppError::new(
            "MODEL_INTEGRITY_ERROR",
            "Model size differs from pinned artifact; remove it and download again",
        ));
    }
    let mut hash = Sha256::new();
    let mut buffer = vec![0; 1024 * 1024];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        hash.update(&buffer[..count]);
    }
    if format!("{:x}", hash.finalize()) != spec.sha {
        return Err(AppError::new(
            "MODEL_INTEGRITY_ERROR",
            "Model SHA-256 mismatch; remove it and download again",
        ));
    }
    Ok(())
}

fn is_certificate_failure(error: &(dyn std::error::Error + 'static)) -> bool {
    if matches!(
        error.downcast_ref::<rustls::Error>(),
        Some(rustls::Error::InvalidCertificate(_) | rustls::Error::NoCertificatesPresented)
    ) {
        return true;
    }
    // Some HTTP connectors wrap the TLS error in io::Error. Inspect its inner
    // value too: Error::source() can otherwise omit that wrapper's typed value.
    error
        .downcast_ref::<std::io::Error>()
        .and_then(|e| e.get_ref())
        .is_some_and(|inner| is_certificate_failure(inner))
}

fn download_error(error: reqwest::Error, stage: &str, transferred: u64) -> AppError {
    let status = error.status().map(|s| s.as_u16());
    let timeout = error.is_timeout();
    let connect = error.is_connect();
    // Keep only the failing request's hostname. Redirect paths/query strings
    // can contain signed credentials and must never appear in diagnostics.
    let hostname = error
        .url()
        .and_then(|url| url.host_str())
        .map(str::to_owned);
    let error = error.without_url();
    let mut causes = vec![download_message(&error.to_string())];
    let mut certificate_error = is_certificate_failure(&error);
    let mut source = std::error::Error::source(&error);
    while let Some(cause) = source {
        certificate_error |= is_certificate_failure(cause);
        if causes.len() >= 8 {
            break;
        }
        causes.push(download_message(&cause.to_string()));
        source = cause.source();
    }
    let retryable = !certificate_error
        && (timeout || connect || status.is_some_and(|s| s == 408 || s == 429 || s >= 500));
    let next_step = if certificate_error {
        "The engine uses system-trusted certificate authorities. Check the reported hostname and the OS trust configuration for HTTPS inspection/proxies. Do not disable TLS or reinstall the program; retry model download after correcting trust."
    } else {
        "Check the reported cause and the host network/certificate/proxy configuration. Do not disable TLS or repeat installations. Re-run model download after resolving the cause; a verified cache is reused."
    };
    AppError::new(
        "DOWNLOAD_ERROR",
        format!(
            "Model download failed during {stage}: {}",
            causes.join(": ")
        ),
    )
    .with_details(
        json!({"stage": stage, "http_status": status, "hostname": hostname,
            "timeout": timeout, "connection_error": connect, "retryable": retryable,
            "certificate_error": certificate_error, "tls_root_store": "native",
            "transferred_bytes": transferred, "causes": causes, "next_step": next_step}),
    )
}

fn download_attempt(
    client: &reqwest::blocking::Client,
    url: &str,
    spec: &ModelSpec,
    temp: &mut tempfile::NamedTempFile,
    hash: &mut Sha256,
    total: &mut u64,
) -> Result<()> {
    if *total == spec.size {
        return Ok(());
    }
    let mut request = client
        .get(url)
        .header(reqwest::header::ACCEPT_ENCODING, "identity");
    if *total > 0 {
        request = request.header(reqwest::header::RANGE, format!("bytes={total}-"));
    }
    let mut response = request
        .send()
        .and_then(|r| r.error_for_status())
        .map_err(|e| download_error(e, "request", *total))?;
    if response.status() == reqwest::StatusCode::PARTIAL_CONTENT {
        let range = response
            .headers()
            .get(reqwest::header::CONTENT_RANGE)
            .and_then(|h| h.to_str().ok())
            .unwrap_or("");
        if !range.starts_with(&format!("bytes {total}-"))
            || !range.ends_with(&format!("/{}", spec.size))
        {
            return Err(AppError::new(
                "MODEL_INTEGRITY_ERROR",
                "Server returned an unexpected download range",
            ));
        }
    } else if response.status() == reqwest::StatusCode::OK {
        if *total > 0 {
            eprintln!("Server does not resume this request; restarting the temporary download.");
            temp.as_file_mut().set_len(0)?;
            temp.as_file_mut().seek(SeekFrom::Start(0))?;
            *total = 0;
            *hash = Sha256::new();
        }
    } else {
        return Err(AppError::new("DOWNLOAD_ERROR", "Server returned an unsupported download status")
            .with_details(json!({"stage": "response", "http_status": response.status().as_u16(), "retryable": false})));
    }
    let mut progress = Instant::now();
    let mut buffer = vec![0; 1024 * 1024];
    loop {
        let len = response.read(&mut buffer).map_err(|e| {
            let message = download_message(&e.to_string());
            let mut causes = vec![message.clone()];
            let mut source = std::error::Error::source(&e);
            while let Some(cause) = source {
                if causes.len() >= 8 { break; }
                causes.push(download_message(&cause.to_string()));
                source = cause.source();
            }
            AppError::new("DOWNLOAD_ERROR", format!("Model download interrupted: {}", causes.join(": ")))
                .with_details(json!({"stage": "body", "transferred_bytes": *total, "retryable": true, "causes": causes}))
        })?;
        if len == 0 {
            break;
        }
        *total += len as u64;
        if *total > spec.size {
            return Err(AppError::new(
                "MODEL_INTEGRITY_ERROR",
                "Download exceeds expected size",
            ));
        }
        hash.update(&buffer[..len]);
        temp.write_all(&buffer[..len])?;
        if progress.elapsed() >= Duration::from_secs(5) || *total == spec.size {
            eprintln!(
                "Model download: {total}/{} bytes ({:.1}%).",
                spec.size,
                *total as f64 * 100.0 / spec.size as f64
            );
            progress = Instant::now();
        }
    }
    if *total != spec.size {
        return Err(AppError::new(
            "DOWNLOAD_ERROR",
            "Model download ended before the expected size",
        )
        .with_details(json!({"stage": "body", "transferred_bytes": *total, "retryable": true})));
    }
    Ok(())
}

// Never include redirected signed URLs or proxy credentials in diagnostics.
fn download_message(message: &str) -> String {
    message
        .split_whitespace()
        .map(|word| {
            if word.contains("://") {
                "[URL omitted]"
            } else {
                word
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}
