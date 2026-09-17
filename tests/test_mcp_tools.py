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
