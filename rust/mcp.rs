use crate::{
    contracts::*,
    engine::Engine,
    error::{AppError, Result as AppResult},
};
use rmcp::{
    handler::server::{router::tool::ToolRouter, wrapper::Parameters},
    model::*,
    tool, tool_handler, tool_router, ServerHandler, ServiceExt,
};
use serde_json::{json, Value};
use std::{io::Cursor, sync::Arc};
use tokio::io::{AsyncBufReadExt, AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt, BufReader};

/// Newer clients may probe with server/discover before falling back to initialize.
/// The pinned legacy SDK cannot decode that method. Reject
/// the probe as a legacy server, keeping the same pipe open for the handshake.
/// This does not advertise support for the stateless 2026 protocol.
async fn initialization_transport<R, W>(
    input: R,
    mut output: W,
) -> AppResult<(impl AsyncRead + Unpin, W)>
where
    R: AsyncRead + Unpin,
    W: AsyncWrite + Unpin,
{
    const MAX_INITIAL_MESSAGE: u64 = 1024 * 1024;
    let mut input = BufReader::new(input);
    let mut first = Vec::new();
    loop {
        first.clear();
        (&mut input)
            .take(MAX_INITIAL_MESSAGE + 1)
            .read_until(b'\n', &mut first)
            .await?;
        if first.len() as u64 > MAX_INITIAL_MESSAGE {
            return Err(AppError::new(
                "MCP_ERROR",
                "MCP initialization message exceeds 1 MiB",
            ));
        }
        let message = serde_json::from_slice::<Value>(&first).ok();
        // Some clients publish advisory root changes while discovery is pending.
        // No roots have been requested and they cannot change our configured jail.
        if message.as_ref().is_some_and(|message| {
            message["jsonrpc"] == "2.0"
                && message["method"] == "notifications/roots/list_changed"
                && message.get("id").is_none()
        }) {
            continue;
        }
        let probe = message.filter(|message| {
            message["jsonrpc"] == "2.0"
                && message["method"] == "server/discover"
                && message
                    .get("id")
                    .is_some_and(|id| id.is_string() || id.is_i64() || id.is_u64())
        });
        let Some(probe) = probe else { break };
        let response = json!({
            "jsonrpc": "2.0",
            "id": probe["id"],
            "error": {
                "code": -32601,
                "message": "server/discover is not supported; use the initialize handshake"
            }
        });
        output.write_all(response.to_string().as_bytes()).await?;
        output.write_all(b"\n").await?;
        output.flush().await?;
    }
    // BufReader may already hold subsequent messages. Keep both the first line
    // and that buffered input, including when initialize arrives without a probe.
    Ok((Cursor::new(first).chain(input), output))
}

#[derive(Clone)]
pub struct PixelLayer {
    engine: Arc<Engine>,
    tool_router: ToolRouter<Self>,
}

#[tool_router]
impl PixelLayer {
    pub fn new(engine: Arc<Engine>) -> Self {
        Self {
            engine,
            tool_router: Self::tool_router(),
        }
    }
    async fn run<F>(&self, operation: F) -> Result<CallToolResult, rmcp::ErrorData>
    where
        F: FnOnce(&Engine) -> AppResult<Value> + Send + 'static,
    {
        let engine = self.engine.clone();
        Ok(
            match tokio::task::spawn_blocking(move || {
                // Serialize preparation and image work, bounding concurrent image
                // allocations and preventing output-folder changes mid-operation.
                static CALL_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());
                let _guard = CALL_LOCK.lock().map_err(|_| {
                    AppError::new("PROCESSING_ERROR", "Tool execution lock unavailable")
                })?;
                operation(&engine)
            })
            .await
            {
                Ok(Ok(value)) => CallToolResult::structured(value),
                Ok(Err(error)) => {
                    let mut value = error.json();
                    value["workspace"] = self.engine.context();
                    CallToolResult::structured_error(value)
                }
                Err(_) => CallToolResult::structured_error(
                    AppError::new("PROCESSING_ERROR", "Image operation could not complete").json(),
                ),
            },
        )
    }
    #[tool(
        description = "REQUIRED before image processing: pass expected_workspace as the agent's actual native absolute task directory (Windows also accepts /mnt/<drive>/ aliases), input_directory (default input; use . for root or a chosen subfolder), and output_directory (default output). Returns input_status, input_absolute_directory, ready/error counts, image paths, transparency and model status without loading AI or writing files. Empty preparation can succeed; process only status:ready images and follow next_step for missing/empty/unreadable inputs. Workspace mismatch blocks processing; never copy inputs to an old root or search the host."
    )]
    async fn prepare_workspace(
        &self,
        Parameters(args): Parameters<PrepareArgs>,
    ) -> Result<CallToolResult, rmcp::ErrorData> {
        self.run(move |e| e.prepare(args)).await
    }
    #[tool(
        description = "Read existing outputs after prepare_workspace without rerunning processing or loading AI. output_path optionally selects an exact output inside the prepared output directory; omit to list up to 100 PNG/WebP/JPEG/SVG files there (no recursion). Returns paths, sizes, raster dimensions/alpha or SVG path count. Does not recover historical timings/source provenance or perform visual review."
    )]
    async fn get_result_info(
        &self,
        Parameters(args): Parameters<ResultInfoArgs>,
    ) -> Result<CallToolResult, rmcp::ErrorData> {
        self.run(move |e| e.result_info(args)).await
    }
    #[tool(
        description = "Remove image background locally using BiRefNet CPU. PNG/WebP alpha output; originals preserved. Uses the precision selected at server startup (--precision fp32|int8); inspect list_models for variant/hash. FP32 requires explicit model download; experimental INT8 requires the pinned local artifact. Paths must be inside the configured workspace."
    )]
    async fn remove_background(
        &self,
        Parameters(args): Parameters<RemoveArgs>,
    ) -> Result<CallToolResult, rmcp::ErrorData> {
        self.run(move |e| e.remove(args)).await
    }
    #[tool(
        description = "Convert PNG/WebP/JPEG locally. WebP supports quality and lossless. JPEG composites transparency over white. Never overwrites files; returns paths and metadata only."
    )]
    async fn convert_format(
        &self,
        Parameters(args): Parameters<ConvertArgs>,
    ) -> Result<CallToolResult, rmcp::ErrorData> {
        self.run(move |e| e.convert(args)).await
    }
    #[tool(
        description = "Resize an image locally using fit, fill, exact or percentage. Default output PNG. Supports Lanczos, bicubic, bilinear and nearest. No AI model is needed."
    )]
    async fn resize_image(
        &self,
        Parameters(args): Parameters<ResizeArgs>,
    ) -> Result<CallToolResult, rmcp::ErrorData> {
        self.run(move |e| e.resize(args)).await
    }
    #[tool(
        description = "Trace an exact image_path from prepare_workspace into SVG. For cut + vector / transparent SVG from an opaque image set remove_background=true: the engine removes background, retains the intermediate PNG, and traces that exact PNG in one call. Default false preserves the image's existing background/alpha without AI. Omit output_path for automatic names in the prepared output directory; collisions get new names, never delete files. Returns source, intermediate and final absolute/relative paths and dimensions."
    )]
    async fn vectorize_image(
        &self,
        Parameters(args): Parameters<VectorArgs>,
    ) -> Result<CallToolResult, rmcp::ErrorData> {
        self.run(move |e| e.vectorize(args)).await
    }
    #[tool(
        description = "List the supported model and its download/session status. Does not download weights or load ONNX Runtime."
    )]
    async fn list_models(
        &self,
        Parameters(_args): Parameters<EmptyArgs>,
    ) -> Result<CallToolResult, rmcp::ErrorData> {
        self.run(|e| e.call("list_models", json!({}))).await
    }
    #[tool(
        description = "Inspect pinned model origin, license, revision, SHA-256 and status without loading or downloading it. Supported model_id: birefnet-general; precision is selected at process startup."
    )]
    async fn get_model_info(
        &self,
        Parameters(args): Parameters<ModelArgs>,
    ) -> Result<CallToolResult, rmcp::ErrorData> {
        self.run(move |e| e.call("get_model_info", json!({"model_id": args.model_id})))
            .await
    }
}

#[tool_handler(router = self.tool_router)]
impl ServerHandler for PixelLayer {
    fn get_info(&self) -> ServerInfo {
        let mut info = ServerInfo::new(ServerCapabilities::builder().enable_tools().build())
            .with_server_info(Implementation::new("pixellayer", env!("CARGO_PKG_VERSION")));
        info.instructions = Some(format!("Local PixelLayer Rust server. Configured workspace: {}. BEFORE processing, call prepare_workspace with expected_workspace equal to the caller's real project/task directory, not this server path unless it is the same directory. Pass the requested output_directory (e.g. output/2). A mismatch is a setup blocker: do not search the filesystem, copy inputs to another root or use shell to bypass it. Use exact returned image_path values; omit output_path to save under the prepared output directory with collision-safe names. For cut + vector use vectorize_image with remove_background=true; it retains PNG and produces SVG in one call. Report actual returned absolute paths; a tool success is not proof of visual quality. Shell access is controlled by the host, not by this MCP. Images stay local; weights/runtime are separate authorized dependencies. FP32 remains default; never switch precision to complete a task.", self.engine.workspace.info()["root"].as_str().unwrap_or("unavailable")));
        info
    }
}

pub async fn serve(engine: Arc<Engine>) -> AppResult<()> {
    let idle_engine = engine.clone();
    let cleanup = tokio::spawn(async move {
        let mut interval = tokio::time::interval(std::time::Duration::from_secs(1));
        loop {
            interval.tick().await;
            idle_engine.models.unload_idle();
        }
    });
    let result = async {
        let (input, output) = rmcp::transport::stdio();
        let transport = initialization_transport(input, output).await?;
        let service = PixelLayer::new(engine)
            .serve(transport)
            .await
            .map_err(|e| AppError::new("MCP_ERROR", e.to_string()))?;
        service
            .waiting()
            .await
            .map_err(|e| AppError::new("MCP_ERROR", e.to_string()))?;
        Ok(())
    }
    .await;
    cleanup.abort();
    result
}
