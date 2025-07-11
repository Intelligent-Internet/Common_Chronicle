"""
This file contains shared fixtures and configuration for the test suite.

Pytest will automatically discover and use the fixtures defined in this file.

NOTE: All database-related fixtures have been removed as they are not currently
required by any tests. If you add tests that need a database, you will need
to re-introduce the database setup fixtures.
"""

import asyncio
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """
    Creates a new event loop for the entire test session, ensuring isolation.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def app(event_loop: asyncio.AbstractEventLoop) -> FastAPI:
    """
    Create a new application instance for the test session.
    """
    # Import the factory function here to ensure it's fresh for the test session.
    from main import create_app

    app_ = create_app()
    # Note: DB dependency override is removed as DB is not used in current tests.
    return app_


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """
    Fixture to get a test client for making API requests.
    The TestClient handles the application's lifespan events (startup/shutdown).
    """
    with TestClient(app) as c:
        return c
