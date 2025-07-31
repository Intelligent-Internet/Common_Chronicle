#!/usr/bin/env python3

"""
Main application entry point for Common Chronicle timeline generation service.

Architecture: FastAPI application with database, LLM providers, and WebSocket support.
Key Features: Lifecycle management, database health checks, error handling, CORS configuration.
"""

import asyncio
import sys

# Add this block to switch asyncio event loop policy on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import errno
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.http import router as http_router
from app.api.users import router as users_router
from app.api.ws import router as ws_router
from app.config import settings
from app.db import check_db_connection, init_db
from app.services.llm_service import close_all_llm_clients, initialize_all_llm_clients
from app.services.mcp.mcp_server import mcp_app
from app.utils.logger import setup_logger

logger = setup_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Merge the lifecycle management of the main application and the MCP server.
    """
    logger.info("Application startup...")
    try:
        initialize_all_llm_clients()
        logger.info("LLM client initialized.")

        logger.info("Initializing database...")
        await init_db()
        logger.info("Database initialization complete.")

        logger.info("Checking database connectivity...")
        if await check_db_connection():
            logger.info("Database connectivity confirmed.")
        else:
            logger.critical("Database connectivity check failed.")
            raise SystemExit("Database connection failed.")

    except Exception as e:
        logger.critical(f"Startup error: {e}")
        raise SystemExit(f"Startup failed: {e}") from e

    logger.info("Timeline Project API startup successful.")

    # Start MCP server
    async with mcp_app.lifespan(app):
        yield

    logger.info("Timeline Project API shutdown...")
    await close_all_llm_clients()
    logger.info("Shutdown complete.")


def create_app():
    app = FastAPI(title="Timeline Project API", lifespan=lifespan)

    @app.exception_handler(OSError)
    async def oserror_exception_handler(request: Request, exc: OSError):
        logger.error(
            f"OSError caught: {exc}, errno: {exc.errno}, winerror: {getattr(exc, 'winerror', None)}"
        )
        is_timeout_or_refused = False
        if hasattr(exc, "winerror") and exc.winerror == 121:
            is_timeout_or_refused = True
        elif exc.errno in [errno.ETIMEDOUT, errno.ECONNREFUSED]:
            is_timeout_or_refused = True

        if is_timeout_or_refused:
            logger.error(
                f"Returning 503 due to DB connection issue: {settings.db_unavailable_hint}"
            )
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"detail": settings.db_unavailable_hint},
            )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": f"An unexpected OS error occurred: {exc}"},
        )

    app.include_router(ws_router)
    app.include_router(http_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

    # Mount MCP server (based on best practices)
    app.mount("/mcp", mcp_app)
    logger.info("MCP server mounted at /mcp")

    return app


app = create_app()


def main():
    """
    Start FastAPI application, MCP server is mounted at /mcp path
    """
    port = int(settings.server_port)
    host = settings.server_host

    logger.info(f"Starting Common Chronicle API server on {host}:{port}")
    logger.info("MCP server is mounted at /mcp and will be available via HTTP")

    try:
        uvicorn.run(app, host=host, port=port, workers=settings.server_workers)
    except Exception as e:
        logger.error(f"Error starting server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
