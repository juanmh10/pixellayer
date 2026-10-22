mod contracts;
mod engine;
mod error;
mod files;
mod mcp;
mod model;
mod setup;

use clap::{Parser, Subcommand};
use error::{AppError, Result};
use serde_json::{json, Value};
use std::{path::PathBuf, process::ExitCode, sync::Arc};

#[derive(Parser)]
#[command(
    name = "pixellayer",
    version,
    about = "Local image processing CLI and MCP server (Rust/ONNX CPU)"
)]
struct Cli {
    /// Authorized image workspace (defaults to the current directory).
    #[arg(long, global = true)]
    workspace: Option<PathBuf>,
    /// Model cache directory; independent from the image workspace.
    #[arg(long, global = true)]
    cache_dir: Option<PathBuf>,
    /// ONNX Runtime 1.22.0 dynamic library; defaults to beside the executable.
    #[arg(long, global = true)]
    ort_dylib: Option<PathBuf>,
    /// CPU inference threads (default 4).
    #[arg(long, global = true)]
    threads: Option<usize>,
    /// Unload idle model sessions after this many seconds (default 300).
    #[arg(long, global = true)]
    model_ttl: Option<u64>,
    /// Experimental model precision; fp32 remains the default.
    #[arg(long, global = true, value_enum)]
    precision: Option<model::Precision>,
    #[command(subcommand)]
    command: Command,
}
#[derive(Subcommand)]
enum Command {
    /// Prepare every standard feature: runtime presence, verified FP32 model and optional MCP draft.
    Setup {
        /// Authorize downloading the pinned FP32 model (about 928 MiB) if absent.
        #[arg(long)]
        accept_download: bool,
        #[arg(long, value_enum)]
        client: Option<setup::Client>,
        #[arg(long)]
        wsl_interop: bool,
        #[arg(long)]
        existing: Option<PathBuf>,
    },
    /// Call a tool; stdout is one JSON result. Same parameters as MCP tools.
    Call {
        /// prepare_workspace, remove_background, convert_format, resize_image, vectorize_image, list_models, get_model_info
        tool: String,
        /// JSON object with the tool parameters (PowerShell: see README for quoting).
        #[arg(long, default_value = "{}", conflicts_with = "json_file")]
        json: String,
        /// Read parameters from a UTF-8 JSON file instead of a command-line string.
        #[arg(long)]
        json_file: Option<PathBuf>,
    },
    /// Start a local stdio MCP server; stdout is reserved for MCP messages.
    Mcp,
    /// Inspect effective paths and readiness without loading AI or changing files.
    Doctor {
        /// Hash the cached model as well (reads about 928 MiB for FP32).
        #[arg(long)]
        verify_model: bool,
    },
    /// Generate a configuration draft; never edits live agent settings.
    Configure {
        #[arg(long, value_enum)]
        client: setup::Client,
        /// Windows EXE launched by a WSL client. Not for native Linux builds.
        #[arg(long)]
        wsl_interop: bool,
        /// Existing JSON settings to merge in memory, preserving other entries.
        #[arg(long)]
        existing: Option<PathBuf>,
    },
    /// Explicitly manage pinned model weights. No model downloads happen during tool calls.
    Model {
        #[command(subcommand)]
        command: ModelCommand,
    },
}
#[derive(Subcommand)]
enum ModelCommand {
    Download,
    Verify,
    Info,
}

fn env_path(name: &str) -> Option<PathBuf> {
    std::env::var_os(name)
        .filter(|s| !s.is_empty())
        .map(PathBuf::from)
}
fn env_number<T: std::str::FromStr>(name: &str) -> Result<Option<T>> {
    std::env::var(name)
        .ok()
        .map(|s| {
            s.parse()
                .map_err(|_| AppError::invalid(format!("Invalid {name}")))
        })
        .transpose()
}
fn make_engine(cli: &Cli) -> Result<Arc<engine::Engine>> {
    let workspace = cli
        .workspace
        .clone()
        .or_else(|| env_path("PIXELLAYER_WORKSPACE"))
        .unwrap_or(std::env::current_dir()?);
    let cache = cli
        .cache_dir
        .clone()
        .or_else(|| env_path("PIXELLAYER_MODELS_CACHE"))
        .or_else(|| {
            directories::ProjectDirs::from("", "", "PixelLayer")
                .map(|p| p.cache_dir().join("models"))
        })
        .ok_or_else(|| AppError::invalid("Set --cache-dir or PIXELLAYER_MODELS_CACHE"))?;
    let cache = std::path::absolute(files::Workspace::client_path(&cache.to_string_lossy()))?;
    let runtime = cli
        .ort_dylib
        .clone()
        .or_else(|| env_path("PIXELLAYER_ORT_DYLIB"))
        .or_else(|| env_path("ORT_DYLIB_PATH"));
    let threads = match cli.threads {
        Some(value) => value,
        None => env_number("PIXELLAYER_THREADS")?.unwrap_or(4),
    };
    let ttl = match cli.model_ttl {
        Some(value) => value,
        None => env_number("PIXELLAYER_MODEL_TTL")?.unwrap_or(300),
    };
    if threads == 0 || threads > 256 {
        return Err(AppError::invalid("threads must be between 1 and 256"));
    }
    if ttl == 0 {
        return Err(AppError::invalid("model-ttl must be positive"));
    }
    let precision = match cli.precision {
        Some(value) => value,
        None => match std::env::var("PIXELLAYER_PRECISION") {
            Ok(value) => <model::Precision as clap::ValueEnum>::from_str(&value, false)
                .map_err(AppError::invalid)?,
            Err(std::env::VarError::NotPresent) => model::Precision::Fp32,
            Err(_) => return Err(AppError::invalid("Invalid PIXELLAYER_PRECISION")),
        },
    };
    Ok(Arc::new(engine::Engine {
        require_preparation: matches!(cli.command, Command::Mcp),
        prepared_output: std::sync::Mutex::new(None),
        workspace: files::Workspace::new(&workspace)?,
        models: model::ModelManager::new(cache, runtime, threads, ttl, precision),
    }))
}

async fn execute(cli: Cli) -> Result<Option<Value>> {
    let engine = make_engine(&cli)?;
    match cli.command {
        Command::Setup {
            accept_download,
            client,
            wsl_interop,
            existing,
        } => {
            let result = tokio::task::spawn_blocking(move || {
                setup::complete(
                    &engine,
                    accept_download,
                    client,
                    wsl_interop,
                    existing.as_deref(),
                )
            })
            .await
            .map_err(|_| AppError::new("SETUP_ERROR", "Setup could not complete"))??;
            Ok(Some(result))
        }
        Command::Doctor { verify_model } => Ok(Some(setup::doctor(&engine, verify_model)?)),
        Command::Configure {
            client,
            wsl_interop,
            existing,
        } => Ok(Some(setup::configure(
            &engine,
            client,
            wsl_interop,
            existing.as_deref(),
        )?)),
        Command::Mcp => {
            mcp::serve(engine).await?;
            Ok(None)
        }
        Command::Call {
            tool,
            json,
            json_file,
        } => {
            let text = match json_file {
                Some(path) => std::fs::read_to_string(path)?,
                None => json,
            };
            let params: Value = serde_json::from_str(text.trim_start_matches('\u{feff}'))?;
            let result = tokio::task::spawn_blocking(move || engine.call(&tool, params))
                .await
                .map_err(|_| {
                    AppError::new("PROCESSING_ERROR", "Image operation could not complete")
                })??;
            Ok(Some(result))
        }
        Command::Model { command } => {
            let result = tokio::task::spawn_blocking(move || match command {
                ModelCommand::Download => engine.models.download(),
                ModelCommand::Verify => engine.models.verify(),
                ModelCommand::Info => Ok(json!({"success": true, "model": engine.models.info()})),
            })
            .await
            .map_err(|_| {
                AppError::new("MODEL_LOAD_ERROR", "Model management could not complete")
            })??;
            Ok(Some(result))
        }
    }
}

#[tokio::main]
async fn main() -> ExitCode {
    let cli = match Cli::try_parse() {
        Ok(cli) => cli,
        Err(error) => {
            if matches!(
                error.kind(),
                clap::error::ErrorKind::DisplayHelp | clap::error::ErrorKind::DisplayVersion
            ) {
                print!("{error}");
                return ExitCode::SUCCESS;
            }
            println!("{}", AppError::invalid(error.to_string()).json());
            return ExitCode::from(2);
        }
    };
    let is_mcp = matches!(cli.command, Command::Mcp);
    match execute(cli).await {
        Ok(Some(value)) => {
            println!("{value}");
            ExitCode::SUCCESS
        }
        Ok(None) => ExitCode::SUCCESS,
        Err(error) => {
            if is_mcp {
                eprintln!("{error}");
            } else {
                println!("{}", error.json());
            }
            ExitCode::from(1)
        }
    }
}
