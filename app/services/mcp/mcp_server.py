#!/usr/bin/env python3
"""
Common Chronicle MCP Server - Based on best practices

This module creates MCP server and generates ASGI application,
which is used to mount to FastAPI main application.
Uses "mount MCP server" mode recommended by fastmcp,
rather than automatic conversion of REST API.
"""

from app.services.mcp.mcp_tools import mcp
from app.utils.logger import setup_logger

logger = setup_logger("mcp_server")


def create_mcp_app():
    """
    Create MCP ASGI application

    Returns:
        ASGI application, can be mounted to FastAPI main application
    """
    logger.info("Creating MCP ASGI application...")

    # Generate ASGI application, path is /mcp
    mcp_app = mcp.http_app(path="/mcp")

    logger.info("MCP ASGI application created successfully")
    # Note: get_tools() is async, we don't call it in synchronous function
    # Tool information will be displayed when the server starts
    logger.info("MCP tools will be available once the server starts")

    return mcp_app


# Create MCP ASGI application instance
mcp_app = create_mcp_app()
