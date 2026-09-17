# img-cut 🔪

> Local MCP server for AI-powered image processing — background removal, format conversion, optimization, and vectorization.

## What is this?

**img-cut** is a Python-based MCP (Model Context Protocol) server that exposes image processing tools to AI coding agents. When you're developing in any repo and need to process images, your agent calls img-cut's tools via MCP — no base64, no token bloat, just file paths in and out.

### Key Features

- 🎯 **Perfect Background Removal** — ARGB alpha channel, no fill, no quality loss
- 🤖 **Multi-Model Support** — BiRefNet (general/portrait/matting/hr), RMBG-2.0, IS-Net
- 🖼️ **Format Conversion** — PNG ↔ WebP ↔ JPEG with quality control
- 📐 **Smart Resize** — Aspect-ratio-preserving resize with multiple algorithms
- 🗜️ **Optimization** — File size reduction with configurable quality targets
- ✒️ **Vectorization** — Raster to SVG via vtracer
- ⚡ **Zero Idle Cost** — Models lazy-load on first call, auto-unload after TTL
- 🔌 **MCP Native** — Works with any MCP-compatible agent (Codex, Antigravity, Claude, etc.)

## Visual Examples

### 1. Background Removal (`remove_background`)

| Before (`input/to-cut.png`) | After (`output/to-cut-nobg.png`) |
| :---: | :---: |
| <img src="input/to-cut.png" alt="Before: Original Photo" width="100%" /> | <img src="output/to-cut-nobg.png" alt="After: Background Removed" width="100%" /> |

### 2. Raster to Vector SVG (`vectorize_image`)

| Before (`input/carro-to-svg.png`) | After (`output/carro-to-svg.svg`) |
| :---: | :---: |
| <img src="input/carro-to-svg.png" alt="Before: Raster PNG" width="100%" /> | <img src="output/carro-to-svg.svg" alt="After: Vector SVG" width="100%" /> |

## Quick Start

```bash
# Install dependencies
uv sync

# Run the MCP server (stdio transport)
uv run python -m src.mcp_server

# Or with pip
pip install -e .
python -m src.mcp_server
```

## Agent Configuration

Configure **img-cut** in your preferred AI agent environment. Replace `<path-to-img-cut>` with your local repository clone path and `<path-to-workspaces>` with the directories authorized for image processing.

### 1. Antigravity CLI (AGY)
**Config File:** `~/.gemini/config/mcp_config.json` (JSON)

```json
{
  "mcpServers": {
    "img-cut": {
      "command": "<path-to-img-cut>/.venv/bin/python",
      "args": [
        "-m",
        "src.mcp_server"
      ],
      "env": {
        "PYTHONPATH": "<path-to-img-cut>",
        "IMGCUT_ALLOWED_WORKSPACES": "<path-to-workspaces>",
        "IMGCUT_LOG_DIR": "<path-to-img-cut>/logs",
        "IMGCUT_MODEL_TTL": "300"
      }
    }
  }
}
```

### 2. Codex CLI
**Config File:** `~/.codex/config.toml` (TOML)

```toml
[mcp_servers.img-cut]
command = "<path-to-img-cut>/.venv/bin/python"
args = ["-m", "src.mcp_server"]
startup_timeout_sec = 30.0
tool_timeout_sec = 120.0

[mcp_servers.img-cut.env]
PYTHONPATH = "<path-to-img-cut>"
IMGCUT_ALLOWED_WORKSPACES = "<path-to-workspaces>"
IMGCUT_LOG_DIR = "<path-to-img-cut>/logs"
IMGCUT_MODEL_TTL = "300"
```

### 3. Claude Code
**Config File:** `.mcp.json` (in your project root) or `~/.claude.json` (JSON)

```json
{
  "mcpServers": {
    "img-cut": {
      "command": "<path-to-img-cut>/.venv/bin/python",
      "args": [
        "-m",
        "src.mcp_server"
      ],
      "env": {
        "PYTHONPATH": "<path-to-img-cut>",
        "IMGCUT_ALLOWED_WORKSPACES": "<path-to-workspaces>",
        "IMGCUT_LOG_DIR": "<path-to-img-cut>/logs",
        "IMGCUT_MODEL_TTL": "300"
      }
    }
  }
}
```

*Or configure directly via CLI:*
```bash
claude mcp add img-cut <path-to-img-cut>/.venv/bin/python -m src.mcp_server -e PYTHONPATH=<path-to-img-cut> -e IMGCUT_ALLOWED_WORKSPACES=<path-to-workspaces>
```

### 4. OpenCode
**Config File:** `~/.config/opencode/opencode.json` (or `opencode.json` in project root) (JSON)

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "img-cut": {
      "type": "local",
      "command": [
        "<path-to-img-cut>/.venv/bin/python",
        "-m",
        "src.mcp_server"
      ],
      "environment": {
        "PYTHONPATH": "<path-to-img-cut>",
        "IMGCUT_ALLOWED_WORKSPACES": "<path-to-workspaces>",
        "IMGCUT_LOG_DIR": "<path-to-img-cut>/logs",
        "IMGCUT_MODEL_TTL": "300"
      },
      "enabled": true,
      "timeout": 120000
    }
  }
}
```

## Available Tools

| Tool | Description |
|---|---|
| `remove_background` | Remove background with alpha transparency (AI) |
| `batch_remove_background` | Batch background removal across multiple images |
| `crop_image` | Geometric crop (coordinates or autocrop trimming empty margins) |
| `convert_format` | Convert between PNG/WebP/JPEG |
| `optimize_image` | Reduce file size with quality control |
| `resize_image` | Resize preserving aspect ratio |
| `vectorize_image` | Convert raster to SVG |
| `batch_process` | Chain multiple sequential operations on an image |
| `list_models` | List available models (no GPU load) |
| `get_model_info` | Model details and capabilities |
| `save_image` | Copy/relocate image within workspace (Path-Only) |

## How It Works

1. Your AI agent discovers img-cut tools via MCP
2. Agent calls a tool with an **image file path** + parameters
3. img-cut processes the image locally (lazy-loads model if needed)
4. Returns the **output file path** + metadata (size, dimensions, reduction %)
5. **No image data flows through the MCP protocol** — only paths and metadata

## License

MIT
