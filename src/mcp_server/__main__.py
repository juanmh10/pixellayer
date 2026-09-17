"""
img-cut MCP Server Entry Point
================================
Initializes the FastMCP server, registers all models (without loading),
registers all tools, and starts the stdio transport.

Run with:
    python -m src.mcp_server
    uv run python -m src.mcp_server

The server starts instantly (< 1s) — no model loading at boot.
Models are lazy-loaded on first inference call.
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from src.engine.models.birefnet import create_birefnet_models
from src.engine.models.isnet import create_isnet_model
from src.engine.models.registry import registry
from src.engine.models.rmbg import create_rmbg_model
from src.mcp_server.tools import register_all_tools
from src.utils.logging import setup_logging

logger = logging.getLogger(__name__)


def create_server() -> FastMCP:
    """Create and configure the img-cut MCP server.

    1. Setup logging (stderr only)
    2. Register all model wrappers (NO weight loading)
    3. Register all MCP tools
    4. Return configured FastMCP instance
    """
    # 1. Logging — stderr only (stdout reserved for MCP stdio)
    setup_logging(level=logging.INFO)
    logger.info("Initializing img-cut MCP server...")

    # 2. Register models (lightweight — just metadata, NO loading)
    for model in create_birefnet_models():
        registry.register(model)
    registry.register(create_rmbg_model())
    registry.register(create_isnet_model())

    model_count = len(registry.list_models())
    logger.info(f"Registered {model_count} models (none loaded)")

    # 3. Create FastMCP server and register tools
    mcp = FastMCP(
        "img-cut",
        instructions=(
            "img-cut provides local, AI-powered image processing tools. "
            "IMPORTANT RULES FOR CALLING AGENTS:\n"
            "1. PATH-ONLY: Pass and expect workspace-relative file paths (e.g. 'input/photo.png', 'output/vector.svg'). "
            "Never send or ask for base64, raw bytes, or system absolute paths.\n"
            "2. DEFAULT PRESETS: When requesting SVG vectorization, the 'logo' preset is the default (clean Bézier curves, "
            "transparent background, zero noise). For background removal, 'birefnet-general' is the default with pure alpha.\n"
            "3. SEMANTIC CLARITY: Use 'remove_background' (or 'batch_remove_background') for AI background cutout. "
            "Use 'crop_image' for geometric/bounding box cropping or autocrop to trim empty borders.\n"
            "4. MULTI-IMAGE: Use 'batch_remove_background' when processing multiple images in one turn to minimize token overhead.\n"
            "5. ISOLATION & PERMISSIONS: Operations are restricted to authorized workspaces. "
            "No shell commands, arbitrary disk reads/writes outside workspace, or credential access are supported or permitted."
        ),
    )
    register_all_tools(mcp)
    logger.info("All tools registered. Server ready.")

    return mcp


# Create and run
mcp = create_server()

if __name__ == "__main__":
    mcp.run()
