use crate::{
    engine::Engine,
    error::{AppError, Result},
    files::Workspace,
};
use serde_json::{json, Value};
use std::{fs, path::Path};

#[derive(Debug, Clone, Copy, clap::ValueEnum)]
pub enum Client {
    ClaudeCode,
    Cursor,
    CopilotVscode,
    CodexCli,
    Agy,
    OpenCode,
    OpenCodeV1,
    ChatgptWork,
}

pub fn complete(
    engine: &Engine,
    accept_download: bool,
    client: Option<Client>,
    wsl_interop: bool,
    existing: Option<&Path>,
) -> Result<Value> {
    let model = engine.models.info();
    if model["precision"] != "fp32" {
        return Err(AppError::invalid("Complete setup uses the standard FP32 model; preserve experimental configurations and use model commands for them."));
    }
    // Validate the requested client/configuration before a large download.
    let configuration = match client {
        Some(client) => Some(configure(engine, client, wsl_interop, existing)?),
        None if wsl_interop || existing.is_some() => {
            return Err(AppError::invalid(
                "--wsl-interop/--existing require --client",
            ));
        }
        None => None,
    };
    let runtime = engine.models.configured_runtime_path()?;
    if !runtime.is_file() {
        return Err(AppError::new("RUNTIME_NOT_FOUND", "Complete setup requires the packaged ONNX Runtime 1.22.0 beside the installed executable or --ort-dylib."));
    }
    if !engine.models.path().exists() && !accept_download {
        return Err(AppError::new("SETUP_CONSENT_REQUIRED", "Complete setup needs the FP32 model (about 928 MiB). With the user's setup authorization, rerun setup --accept-download; no separate feature selection is needed.")
            .with_details(json!({"download_size_bytes": model["download_size_bytes"], "cache_path": Workspace::native(&engine.models.path()), "next_step": "Obtain authorization once for complete setup, not separately for each image operation."})));
    }
    let reused = engine.models.path().exists();
    engine.models.download()?; // Existing cache is verified; never silently replaced.
    let mut result = json!({"success": true, "setup_complete": true,
        "version": env!("CARGO_PKG_VERSION"), "model_reused": reused,
        "model_integrity_verified": true, "model_path": Workspace::native(&engine.models.path()),
        "runtime_present": true, "runtime_path": Workspace::native(&runtime),
        "runtime_load_checked": false, "inference_checked": false,
        "mcp_connection_checked": false, "configuration_applied": false,
        "next_step": "Apply only the selected client's MCP draft if requested, reconnect as required by the host, discover eight tools and prepare the actual image workspace. No live client settings were edited."});
    if let Some(configuration) = configuration {
        result["configuration_draft"] = configuration;
    }
    Ok(result)
}

pub fn doctor(engine: &Engine, verify: bool) -> Result<Value> {
    let runtime = engine.models.configured_runtime_path()?;
    let model = engine.models.info();
    let integrity = if verify {
        match engine.models.verify() {
            Ok(_) => json!({"checked": true, "valid": true}),
            Err(error) => json!({"checked": true, "valid": false, "error": error.json()}),
        }
    } else {
        json!({"checked": false, "valid": null})
    };
    Ok(
        json!({"success": true, "version": env!("CARGO_PKG_VERSION"),
        "platform": std::env::consts::OS, "architecture": std::env::consts::ARCH,
        "executable": Workspace::native(&std::env::current_exe()?),
        "workspace": engine.context(), "model": model,
        "model_path": Workspace::native(&engine.models.path()), "model_integrity": integrity,
        "runtime": {"path": Workspace::native(&runtime), "exists": runtime.is_file(),
            "load_checked": false, "required_version": "1.22.0"},
        "ready_for_non_ai_operations": true,
        "background_removal_dependencies_present": runtime.is_file() && model["downloaded"] == true,
        "inference_checked": false, "mcp_connection_checked": false,
        "next_step": "Use configure for a draft, reconnect the selected client and prepare the actual task. Missing model/runtime affects removal only. Presence is not a load or integrity check; --verify-model checks the weights."}),
    )
}

fn replace(value: &mut Value, tokens: &[(&str, String)]) {
    match value {
        Value::String(s) => {
            for (token, replacement) in tokens {
                *s = s.replace(token, replacement);
            }
        }
        Value::Array(items) => items.iter_mut().for_each(|v| replace(v, tokens)),
        Value::Object(items) => items.values_mut().for_each(|v| replace(v, tokens)),
        _ => {}
    }
}

fn merge(existing: &mut Value, draft: Value) -> Result<()> {
    let target = existing
        .as_object_mut()
        .ok_or_else(|| AppError::invalid("Settings must be a JSON object"))?;
    for (key, value) in draft.as_object().unwrap() {
        if value.is_object() {
            let entry = target.entry(key.clone()).or_insert_with(|| json!({}));
            if key == "pixellayer" {
                *entry = value.clone();
            } else {
                merge(entry, value.clone())?;
            }
        } else {
            target.insert(key.clone(), value.clone());
        }
    }
    Ok(())
}

fn wsl_command(native: &str) -> Result<String> {
    let b = native.as_bytes();
    if b.len() < 3 || b[1] != b':' || !b[0].is_ascii_alphabetic() {
        return Err(AppError::invalid(
            "WSL interop requires an executable on a mounted Windows drive",
        ));
    }
    Ok(format!(
        "/mnt/{}/{}",
        (b[0] as char).to_ascii_lowercase(),
        native[3..].replace('\\', "/")
    ))
}

pub fn configure(
    engine: &Engine,
    client: Client,
    interop: bool,
    existing: Option<&Path>,
) -> Result<Value> {
    if interop && !cfg!(windows) {
        return Err(AppError::invalid(
            "--wsl-interop is for the Windows EXE. A native Linux engine uses native paths.",
        ));
    }
    let executable = Workspace::native(&std::env::current_exe()?);
    let command = if interop {
        wsl_command(&executable)?
    } else {
        executable
    };
    let workspace = engine.context()["root"].as_str().unwrap().to_string();
    let model_path = engine.models.path();
    let cache = Workspace::native(model_path.parent().unwrap());
    let runtime = Workspace::native(&engine.models.configured_runtime_path()?);
    let info = engine.models.info();
    let tokens = [
        ("__PIXELLAYER_EXE__", command.clone()),
        ("__PIXELLAYER_WORKSPACE__", workspace.clone()),
        ("__PIXELLAYER_CACHE__", cache.clone()),
        ("__PIXELLAYER_RUNTIME__", runtime.clone()),
    ];
    let args = json!([
        "--workspace",
        workspace,
        "--cache-dir",
        cache,
        "--ort-dylib",
        runtime,
        "--threads",
        info["threads"],
        "--model-ttl",
        info["ttl_seconds"],
        "--precision",
        info["precision"],
        "mcp"
    ]);
    // Every argv element is a string, including numbers from model metadata.
    let args: Vec<String> = args
        .as_array()
        .unwrap()
        .iter()
        .map(|v| {
            v.as_str()
                .map(str::to_owned)
                .unwrap_or_else(|| v.to_string())
        })
        .collect();
    if matches!(client, Client::CodexCli) {
        if existing.is_some() {
            return Err(AppError::invalid("Codex uses TOML. Merge only this mcp_servers.pixellayer table manually; --existing accepts JSON clients only."));
        }
        let q = |v: &str| serde_json::to_string(v).unwrap();
        let text = format!("[mcp_servers.pixellayer]\ncommand = {}\nargs = [{}]\nstartup_timeout_sec = 30\ntool_timeout_sec = 300\n",
            q(&command), args.iter().map(|s| q(s)).collect::<Vec<_>>().join(", "));
        return Ok(
            json!({"success": true, "format": "toml", "configuration_text": text,
            "applied": false, "workspace": engine.context(), "reconnect_required": true}),
        );
    }
    let template = match client {
        Client::ClaudeCode => include_str!("../skill/pixellayer/config/claude-code.mcp.json"),
        Client::Cursor => include_str!("../skill/pixellayer/config/cursor.mcp.json"),
        Client::CopilotVscode => include_str!("../skill/pixellayer/config/copilot-vscode.mcp.json"),
        Client::Agy => include_str!("../skill/pixellayer/config/agy.mcp.json"),
        Client::OpenCode => include_str!("../skill/pixellayer/config/opencode.mcp.json"),
        Client::OpenCodeV1 => include_str!("../skill/pixellayer/config/opencode-v1.mcp.json"),
        Client::ChatgptWork => include_str!("../skill/pixellayer/config/chatgpt-work.mcp.json"),
        Client::CodexCli => unreachable!(),
    };
    let mut draft: Value = serde_json::from_str(template)?;
    replace(&mut draft, &tokens);
    let entry = match client {
        Client::CopilotVscode => &mut draft["servers"]["pixellayer"],
        Client::OpenCode => &mut draft["mcp"]["servers"]["pixellayer"],
        Client::OpenCodeV1 => &mut draft["mcp"]["pixellayer"],
        _ => &mut draft["mcpServers"]["pixellayer"],
    };
    if matches!(client, Client::OpenCode | Client::OpenCodeV1) {
        entry["command"] = json!(std::iter::once(command).chain(args).collect::<Vec<_>>());
    } else {
        entry["args"] = json!(args);
    }
    if let Some(path) = existing {
        let mut settings = serde_json::from_str(&fs::read_to_string(path)?)?;
        merge(&mut settings, draft)?;
        draft = settings;
    }
    Ok(
        json!({"success": true, "format": "json", "configuration": draft, "applied": false,
        "workspace": engine.context(), "reconnect_required": true}),
    )
}
