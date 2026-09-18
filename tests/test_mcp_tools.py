"""
MCP Server Tools Tests
======================
Verifies MCP tool execution, parameters, output contracts, and protocol error responses (isError: True).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp.types import CallToolRequest, CallToolRequestParams
from PIL import Image

from src.engine.models.registry import registry
from src.mcp_server.__main__ import create_server


@pytest.fixture
def mcp_server():
    """Create a configured FastMCP server instance."""
    return create_server()


@pytest.fixture
def test_image_file(tmp_path: Path) -> Path:
    """Create a temporary test image."""
    img = Image.new("RGB", (100, 80), color=(100, 150, 200))
    path = tmp_path / "test_mcp.png"
    img.save(str(path))
    return path


@pytest.mark.asyncio
async def test_mcp_list_models(mcp_server) -> None:
    handler = mcp_server._mcp_server.request_handlers[CallToolRequest]
    req = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(name="list_models", arguments={}),
    )
    res = await handler(req)
    assert res.root.isError is False
    assert "models" in res.root.content[0].text


@pytest.mark.asyncio
async def test_mcp_crop_image(mcp_server, test_image_file: Path, tmp_path: Path) -> None:
    handler = mcp_server._mcp_server.request_handlers[CallToolRequest]
    out_path = tmp_path / "cropped.png"
    req = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(
            name="crop_image",
            arguments={
                "image_path": str(test_image_file),
                "x": 10,
                "y": 10,
                "width": 40,
                "height": 30,
                "output_path": str(out_path),
            },
        ),
    )
    res = await handler(req)
    assert res.root.isError is False
    assert out_path.exists()


@pytest.mark.asyncio
async def test_mcp_error_returns_is_error_true(mcp_server) -> None:
    """Verify that errors produce isError: True in the MCP protocol response."""
    handler = mcp_server._mcp_server.request_handlers[CallToolRequest]
    req = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(
            name="remove_background",
            arguments={"image_path": "non_existent_image_12345.png"},
        ),
    )
    res = await handler(req)
    assert res.root.isError is True
    assert "FILE_NOT_FOUND" in res.root.content[0].text


@pytest.mark.asyncio
async def test_mcp_security_error_blocks_traversal(mcp_server) -> None:
    """Verify path traversal is blocked with isError: True."""
    handler = mcp_server._mcp_server.request_handlers[CallToolRequest]
    req = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(
            name="crop_image",
            arguments={
                "image_path": "../../etc/shadow",
                "x": 0,
                "y": 0,
                "width": 10,
                "height": 10,
            },
        ),
    )
    res = await handler(req)
    assert res.root.isError is True
    assert (
        "SECURITY_ERROR" in res.root.content[0].text
        or "outside authorized workspaces" in res.root.content[0].text
    )


def test_create_server_custom_host_port() -> None:
    """Verify create_server respects custom host and port for remote deployments."""
    server = create_server(host="0.0.0.0", port=9090)
    assert server.settings.host == "0.0.0.0"
    assert server.settings.port == 9090


def test_server_health_check_endpoint() -> None:
    """Verify /health endpoint returns 200 without triggering model loading (Rule 2)."""
    from starlette.testclient import TestClient

    server = create_server(host="127.0.0.1", port=8000)
    client = TestClient(server.sse_app())
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "pixellayer"
    assert data["version"] == "0.1.0"

    # Confirm zero idle resources (no model weights loaded)
    for model_info in registry.list_models():
        assert model_info["is_loaded"] is False


def test_create_server_transport_security() -> None:
    """Verify create_server configures TransportSecuritySettings correctly."""
    server = create_server(
        host="0.0.0.0",
        port=9090,
        allowed_hosts=["mcp.example.com", "127.0.0.1:*"],
        enable_dns_rebinding=False,
    )
    assert server.settings.transport_security is not None
    assert server.settings.transport_security.enable_dns_rebinding_protection is False
    assert server.settings.transport_security.allowed_hosts == ["mcp.example.com", "127.0.0.1:*"]


@pytest.mark.asyncio
async def test_transport_security_middleware_validation() -> None:
    """Verify TransportSecurityMiddleware allows configured hosts and blocks unlisted hosts."""
    from mcp.server.transport_security import TransportSecurityMiddleware
    from starlette.requests import Request

    server = create_server(allowed_hosts=["mcp.allowed.com", "127.0.0.1:*"])
    mw = TransportSecurityMiddleware(server.settings.transport_security)

    req_valid = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/sse",
            "headers": [(b"host", b"mcp.allowed.com")],
        }
    )
    res_valid = await mw.validate_request(req_valid, is_post=False)
    assert res_valid is None

    req_invalid = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/sse",
            "headers": [(b"host", b"attacker.com")],
        }
    )
    res_invalid = await mw.validate_request(req_invalid, is_post=False)
    assert res_invalid is not None
    assert res_invalid.status_code == 421


def test_main_cli_argument_parsing() -> None:
    """Verify CLI parser updates server settings and transport correctly."""
    import sys
    from unittest.mock import patch

    from src.mcp_server.__main__ import main, mcp

    test_args = [
        "__main__.py",
        "--transport",
        "sse",
        "--host",
        "0.0.0.0",
        "--port",
        "8888",
        "--allowed-hosts",
        "mcp.custom.io",
        "--disable-dns-rebinding",
    ]

    with patch.object(sys, "argv", test_args):
        with patch.object(mcp, "run") as mock_run:
            main()
            mock_run.assert_called_once_with(transport="sse")
            assert mcp.settings.host == "0.0.0.0"
            assert mcp.settings.port == 8888
            assert mcp.settings.transport_security is not None
            assert mcp.settings.transport_security.enable_dns_rebinding_protection is False
            assert mcp.settings.transport_security.allowed_hosts == ["mcp.custom.io"]
