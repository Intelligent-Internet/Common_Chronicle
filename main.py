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
from sqlalchemy.exc import DBAPIError, OperationalError

from app.api.auth import router as auth_router
from app.api.http import router as http_router
from app.api.users import router as users_router
from app.api.ws import router as ws_router
from app.config import settings
from app.db import check_db_connection, init_db
from app.services.llm_service import close_all_llm_clients, initialize_all_llm_clients
from app.utils.logger import setup_logger

logger = setup_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup...")
    db_ready = False
    try:
        initialize_all_llm_clients()
        logger.info("LLM client initialized attempt complete.")

        logger.info("Attempting to initialize database...")
        await init_db()
        logger.info("Database initialization attempt complete.")

        logger.info("Attempting to check database connectivity...")
        if await check_db_connection():
            logger.info("Database connectivity confirmed.")
            db_ready = True
        else:
            logger.critical(
                "Database connectivity check unexpectedly returned False. Forcing application shutdown."
            )
            raise SystemExit(
                "Application startup failed due to an unexpected database connectivity check result."
            )

    except (OSError, DBAPIError, OperationalError, RuntimeError) as e:
        logger.critical(
            f"Critical database issue during application startup: {type(e).__name__} - {str(e)}",
            exc_info=True,
        )
        logger.critical(settings.db_unavailable_hint)
        raise SystemExit(
            f"Application startup failed due to database connection issues: {settings.db_unavailable_hint}"
        ) from e
    except Exception as e:
        logger.critical(
            f"Unexpected error during application startup: {type(e).__name__} - {str(e)}",
            exc_info=True,
        )
        raise SystemExit(
            "Application startup failed due to an unexpected error."
        ) from e

    if not db_ready:
        logger.critical(
            "Database was not marked as ready after startup sequence. This should not happen. Exiting."
        )
        raise SystemExit("Database not ready after startup due to an unknown reason.")

    logger.info("Application startup successful. Database is ready.")
    yield
    logger.info("Application shutdown...")
    await close_all_llm_clients()
    logger.info("LLM client closed.")


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
    return app


app = create_app()


def main():
    uvicorn.run(
        "main:app",
        host=settings.server_host,
        port=settings.server_port,
        workers=settings.server_workers,
    )


if __name__ == "__main__":
    main()
