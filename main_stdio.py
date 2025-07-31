#!/usr/bin/env python3
"""
Common Chronicle MCP Server - With Progress Reporting

This version implements FastMCP best practices for long-running tasks
using the official progress reporting mechanism.
"""

import asyncio
import sys

# Add this block to switch asyncio event loop policy on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.services.mcp.mcp_tools import mcp
from app.utils.logger import setup_logger

logger = setup_logger("main_stdio")

# Global variables for lazy initialization
_services_initialized = False
_llm_clients_initialized = False
_db_initialized = False


async def ensure_services_initialized():
    """Initialize services only when needed (lazy loading)"""
    global _services_initialized, _llm_clients_initialized, _db_initialized

    if not _services_initialized:
        logger.info("Initializing services on demand...")

        # Initialize LLM clients only when needed
        if not _llm_clients_initialized:
            try:
                from app.services.llm_service import initialize_all_llm_clients

                initialize_all_llm_clients()
                _llm_clients_initialized = True
                logger.info("LLM clients initialized")
            except Exception as e:
                logger.warning(f"LLM client initialization failed: {e}")

        # Initialize database only when needed
        if not _db_initialized:
            try:
                from app.db import check_db_connection, init_db

                await init_db()
                if await check_db_connection():
                    _db_initialized = True
                    logger.info("Database initialized")
                else:
                    logger.warning("Database connectivity check failed")
            except Exception as e:
                logger.warning(f"Database initialization failed: {e}")

        _services_initialized = True
        logger.info("Services initialization completed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lightweight lifespan - minimal initialization"""
    logger.info("MCP STDIO Server with Progress Reporting startup...")

    # Only do minimal initialization here
    logger.info("Minimal initialization complete - services will be loaded on demand")
    logger.info("Progress reporting enabled for long-running tasks")

    yield

    logger.info("MCP STDIO Server shutdown...")

    # Cleanup only if services were actually initialized
    if _llm_clients_initialized:
        try:
            from app.services.llm_service import close_all_llm_clients

            await close_all_llm_clients()
            logger.info("LLM clients closed")
        except Exception as e:
            logger.warning(f"Error closing LLM clients: {e}")

    logger.info("Shutdown complete.")


def create_app():
    """
    Create FastAPI application for MCP STDIO with progress reporting
    """
    app = FastAPI(
        title="Common Chronicle MCP Server (With Progress)",
        description="Timeline generation service via MCP - with progress reporting for long tasks",
        lifespan=lifespan,
    )

    return app


def main():
    """Main entry point for MCP server with progress reporting"""
    logger.info("Starting Common Chronicle MCP Server (With Progress Reporting)")

    # Show available tools
    logger.info(
        "MCP server ready with progress reporting - services will initialize on first use"
    )
    logger.info("Long-running tasks will provide real-time progress updates")

    # Run MCP server with STDIO transport
    logger.info("Running MCP server with STDIO transport...")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
