"""
PixelLayer MCP Server Entry Point
=================================
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
from mcp.server.fastmcp.server import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.engine.models.birefnet import create_birefnet_models
from src.engine.models.isnet import create_isnet_model
from src.engine.models.registry import registry
from src.engine.models.rmbg import create_rmbg_model
from src.mcp_server.tools import register_all_tools
from src.utils.config import config
from src.utils.logging import setup_logging

logger = logging.getLogger(__name__)


def create_server(
    host: str | None = None,
    port: int | None = None,
    allowed_hosts: list[str] | None = None,
    enable_dns_rebinding: bool | None = None,
) -> FastMCP:
    """Create and configure the PixelLayer MCP server.

    1. Setup logging (stderr only)
    2. Register all model wrappers (NO weight loading)
    3. Configure transport security (DNS rebinding protection)
    4. Register health check and all MCP tools
    5. Return configured FastMCP instance
    """
    # 1. Logging — stderr only (stdout reserved for MCP stdio)
    setup_logging(level=logging.INFO)
    logger.info("Initializing PixelLayer MCP server...")

    # 2. Register models (lightweight — just metadata, NO loading)
    for model in create_birefnet_models():
        registry.register(model)
    registry.register(create_rmbg_model())
    registry.register(create_isnet_model())

    model_count = len(registry.list_models())
    logger.info(f"Registered {model_count} models (none loaded)")

    # 3. Create FastMCP server and register tools
    server_host = host or config.HOST
    server_port = port or config.PORT

    rebinding_enabled = (
        config.ENABLE_DNS_REBINDING if enable_dns_rebinding is None else enable_dns_rebinding
    )
    hosts_list = allowed_hosts if allowed_hosts is not None else list(config.ALLOWED_HOSTS)

    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=rebinding_enabled,
        allowed_hosts=hosts_list,
        allowed_origins=config.ALLOWED_ORIGINS,
    )

    mcp = FastMCP(
        "pixellayer",
        host=server_host,
        port=server_port,
        transport_security=transport_security,
        instructions=(
            "PixelLayer provides local, AI-powered image processing tools. "
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

    # Health check endpoint (Rule 2: Zero idle resources, does NOT load models)
    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "healthy",
                "service": "pixellayer",
                "version": "0.1.0",
            }
        )

    register_all_tools(mcp)
    logger.info("All tools registered. Server ready.")

    return mcp


def main() -> None:
    """CLI entry point supporting stdio and remote transports (sse, streamable-http)."""
    import argparse

    parser = argparse.ArgumentParser(description="PixelLayer MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=config.TRANSPORT,
        help="Transport protocol: stdio (default), sse, or streamable-http",
    )
    parser.add_argument(
        "--host",
        default=config.HOST,
        help="Host address to bind for SSE/HTTP (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=config.PORT,
        help="Port to bind for SSE/HTTP (default: 8000)",
    )
    parser.add_argument(
        "--allowed-hosts",
        nargs="*",
        default=None,
        help="Allowed Host headers for DNS rebinding protection (e.g. mcp.yourdomain.com)",
    )
    parser.add_argument(
        "--disable-dns-rebinding",
        action="store_true",
        default=False,
        help="Disable DNS rebinding protection (recommended when behind trusted reverse proxy or VPN)",
    )

    args, _ = parser.parse_known_args()

    # Reuse module-level default server instance and adjust settings in-place
    server = mcp
    if args.host != server.settings.host or args.port != server.settings.port:
        server.settings.host = args.host
        server.settings.port = args.port

    if args.disable_dns_rebinding:
        if server.settings.transport_security:
            server.settings.transport_security.enable_dns_rebinding_protection = False
        else:
            server.settings.transport_security = TransportSecuritySettings(
                enable_dns_rebinding_protection=False
            )

    if args.allowed_hosts:
        if server.settings.transport_security:
            server.settings.transport_security.allowed_hosts = list(args.allowed_hosts)
        else:
            server.settings.transport_security = TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=list(args.allowed_hosts),
            )

    logger.info(
        f"Starting PixelLayer server on transport '{args.transport}' "
        + (
            f"({server.settings.host}:{server.settings.port})"
            if args.transport != "stdio"
            else "(stdio)"
        )
    )
    server.run(transport=args.transport)


# Create default server instance
mcp = create_server()

if __name__ == "__main__":
    main()
