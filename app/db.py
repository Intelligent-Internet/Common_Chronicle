import argparse
import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime

from sqlalchemy import distinct, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import models  # noqa: F401
from app.config import settings
from app.models.base import Base
from app.models.task import Task
from app.utils.logger import setup_logger

logger = setup_logger("db")

# --- Application DB ---
if not settings.app_database_url:
    raise ValueError(
        "COMMON_CHRONICLE_DATABASE_URL environment variable not set for Application DB"
    )

if not settings.app_database_url.startswith("postgresql+asyncpg://"):
    if settings.app_database_url.startswith("postgresql://"):
        settings.app_database_url = settings.app_database_url.replace(
            "postgresql://", "postgresql+asyncpg://", 1
        )
    else:
        raise ValueError(
            f"Unsupported settings.app_database_url prefix: {settings.app_database_url}"
        )

logger.debug(f"Application DB URL: {settings.app_database_url}")
app_engine = create_async_engine(
    settings.app_database_url,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=30,
    pool_timeout=60,
    pool_recycle=300,
    echo=False,
    connect_args={"timeout": 30},
)

AppAsyncSessionLocal = async_sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=app_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# --- Dataset DB ---
dataset_engine = None
DatasetAsyncSessionLocal = None

if not settings.dataset_database_url:
    logger.warning(
        "COMMON_CHRONICLE_DATASET_URL environment variable not set. Dataset DB will not be available."
    )
else:
    if not settings.dataset_database_url.startswith("postgresql+asyncpg://"):
        if settings.dataset_database_url.startswith("postgresql://"):
            settings.dataset_database_url = settings.dataset_database_url.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )
        else:
            logger.warning(
                f"Unsupported settings.dataset_database_url prefix: {settings.dataset_database_url}. Dataset DB will not be available."
            )
            settings.dataset_database_url = None  # Ensure it's None if invalid

    if settings.dataset_database_url:  # Proceed only if URL is valid
        logger.debug(f"Dataset DB URL: {settings.dataset_database_url}")
        try:
            dataset_engine = create_async_engine(
                settings.dataset_database_url,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
                pool_timeout=60,
                pool_recycle=1800,
                echo=False,
                connect_args={"timeout": 30},
            )
            DatasetAsyncSessionLocal = async_sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=dataset_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            logger.debug("Dataset DB engine and session maker configured.")
        except Exception as e:
            logger.error(
                f"Failed to create dataset_engine or DatasetAsyncSessionLocal: {e}",
                exc_info=True,
            )
            dataset_engine = None
            DatasetAsyncSessionLocal = None


# Ensure models are imported so Base.metadata is populated correctly.
# This needs to happen after Base is defined and before Base.metadata is used (e.g., in init_db).
# from app import models  # noqa: F401 # Moved up after Base import


# --- Dependency for FastAPI (Application DB) ---
async def get_app_db() -> AsyncGenerator[AsyncSession, None]:
    async with AppAsyncSessionLocal() as session:
        # Ensure the search_path is set for the session if models don't qualify schema
        # This is important if 'common_chronicle_test' is not in the default search_path
        # of the database user.
        # Using schema_name from settings
        await session.execute(
            text(f"SET search_path TO {settings.schema_name}, public")
        )
        yield session


# --- Dependency/Getter for Dataset DB ---
async def get_dataset_db() -> AsyncGenerator[AsyncSession, None]:
    if not DatasetAsyncSessionLocal:
        raise RuntimeError(
            "Dataset DB is not configured or COMMON_CHRONICLE_DATASET_URL is not set/valid."
        )
    async with DatasetAsyncSessionLocal() as session:
        # Dataset DB sessions typically don't need a specific search_path like the app DB,
        # as queries are often raw SQL or against public schemas.
        # If specific schema settings are needed for dataset_db, add them here.
        yield session


# --- Function to create tables (for Application DB) ---
async def init_db():
    # from app import models  # noqa: F401 # Moved to module level after Base definition

    # --- DEBUGGING ---
    logger.debug(
        f"Inside init_db (for Application DB, schema: {settings.schema_name}). Checking Base.metadata.tables BEFORE create_all."
    )
    # logger.debug(f"Base.metadata.tables: {Base.metadata.tables}")
    if not Base.metadata.tables:
        logger.warning(
            "Base.metadata.tables is EMPTY! No tables will be created for Application DB."
        )
    else:
        logger.debug(
            f"Tables registered in Base.metadata for Application DB: {list(Base.metadata.tables.keys())}"
        )

    async with app_engine.begin() as conn:
        await conn.execute(text("SET search_path TO public"))
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {settings.schema_name}"))
        await conn.execute(text(f"SET search_path TO {settings.schema_name}, public"))
        logger.debug(
            f"Calling Base.metadata.create_all for Application DB (schema: {settings.schema_name})..."
        )
        await conn.run_sync(Base.metadata.create_all)
        logger.debug(
            f"Base.metadata.create_all for Application DB (schema: {settings.schema_name}) finished. Checking tables in DB..."
        )
        result = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = :schema_name ORDER BY table_name"
            ),
            {"schema_name": settings.schema_name},
        )
        tables_in_db = [row[0] for row in result]
        logger.debug(
            f"Tables actually found in schema '{settings.schema_name}' (Application DB) via information_schema: {tables_in_db}"
        )
        # --- END DEBUGGING ---

    logger.debug(
        f"Database tables created or already exist in schema '{settings.schema_name}' (Application DB)."
    )
    logger.info("Database schema initialized.")


async def close_db():
    """Closes database connections."""
    logger.info("Closing database connections.")
    if app_engine:
        await app_engine.dispose()
    if dataset_engine:
        await dataset_engine.dispose()
    logger.info("Database connections closed.")


# --- Function to list tables in a given schema (uses app_engine by default) ---
async def list_tables_in_schema(
    schema_name: str, use_dataset_engine: bool = False
) -> list[str]:
    """Lists all tables in the specified schema. Can specify which engine to use."""
    table_names = []
    engine_to_use = dataset_engine if use_dataset_engine else app_engine
    db_name_log = "Dataset DB" if use_dataset_engine else "Application DB"

    if not engine_to_use:
        logger.error(
            f"{db_name_log} engine is not available for listing tables in schema '{schema_name}'."
        )
        return []

    async with engine_to_use.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = :schema_name ORDER BY table_name"
            ),
            {"schema_name": schema_name},
        )
        table_names = [row[0] for row in result.fetchall()]

    if table_names:
        logger.debug(
            f"Tables in schema '{schema_name}' (checked on {db_name_log}): {table_names}"
        )
    else:
        logger.debug(
            f"No tables found in schema '{schema_name}' (checked on {db_name_log}) or schema does not exist."
        )
    return table_names


# --- Function to reset database (for Application DB) ---
async def reset_db():
    logger.warning(
        f"Attempting to reset the Application database (schema: {settings.schema_name}). THIS IS A DESTRUCTIVE OPERATION."
    )
    async with app_engine.begin() as conn:
        # Drop the schema and all its contents
        logger.debug(f"Dropping schema '{settings.schema_name}' from Application DB...")
        # Ensure we can drop the schema even if it's in the current search_path by temporarily setting to public
        await conn.execute(text("SET search_path TO public"))
        await conn.execute(
            text(f"DROP SCHEMA IF EXISTS {settings.schema_name} CASCADE")
        )
        logger.info(f"Schema '{settings.schema_name}' dropped from Application DB.")

    # Re-initialize the database (creates schema and tables)
    logger.debug(
        f"Re-initializing Application database (schema: {settings.schema_name})..."
    )
    await init_db()  # init_db will set its own search_path as needed
    logger.info(
        f"Application database (schema: {settings.schema_name}) has been reset and re-initialized."
    )


async def recreate_schema():
    """Drops the schema and recreates it, leaving it empty for Alembic."""
    logger.warning(
        f"Attempting to recreate the Application database schema ({settings.schema_name}). THIS IS A DESTRUCTIVE OPERATION."
    )
    async with app_engine.begin() as conn:
        logger.debug(f"Dropping schema '{settings.schema_name}' from Application DB...")
        await conn.execute(text("SET search_path TO public"))
        await conn.execute(
            text(f"DROP SCHEMA IF EXISTS {settings.schema_name} CASCADE")
        )
        logger.info(f"Schema '{settings.schema_name}' dropped from Application DB.")

        logger.debug(
            f"Creating an empty schema '{settings.schema_name}' in Application DB..."
        )
        await conn.execute(text(f"CREATE SCHEMA {settings.schema_name}"))
        logger.info(f"Empty schema '{settings.schema_name}' created in Application DB.")


async def check_vector_extension():
    """Checks if the pgvector extension is installed in the database."""
    logger.info("Checking if 'vector' extension is installed in the Application DB...")
    async with app_engine.connect() as conn:
        try:
            result = await conn.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector' LIMIT 1")
            )
            if result.scalar_one_or_none() == 1:
                logger.info(
                    "✅ Success: 'vector' extension is installed in the database."
                )
            else:
                logger.error(
                    "❌ Failed: 'vector' extension is NOT installed in the database."
                )
                logger.error(
                    "Please ask your DBA to run 'CREATE EXTENSION vector;' as a superuser on the database."
                )
        except Exception as e:
            logger.error(f"An error occurred while checking for vector extension: {e}")


async def export_unique_task_topics(schema_name: str = None) -> None:
    """
    Export all unique topic_text values from tasks table to a local .txt file.
    """
    # Use default schema name if not provided
    if schema_name is None:
        schema_name = settings.schema_name

    output_file = f"{datetime.now().strftime('%Y-%m-%d')}_{schema_name}_task_topics.txt"
    logger.info(f"Starting export of unique task topics to {output_file}")

    try:
        async with AppAsyncSessionLocal() as session:
            # Set search path for the session
            await session.execute(text(f"SET search_path TO {schema_name}, public"))

            # Query all distinct topic_text values using async SQLAlchemy
            query = select(distinct(Task.topic_text)).where(
                Task.topic_text.isnot(None), Task.topic_text != ""
            )
            result = await session.execute(query)

            # Get all unique topics
            unique_topics: set[str] = set()
            for row in result:
                if row[0] and row[0].strip():  # Only add non-empty strings
                    unique_topics.add(row[0].strip())

            # Sort the topics for better readability
            sorted_topics = sorted(unique_topics)

            # Write to file
            with open(output_file, "w", encoding="utf-8") as f:
                f.write("# Unique Task Topics Export\n")
                f.write(
                    f"# Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                )
                f.write(f"# Total unique topics: {len(sorted_topics)}\n\n")

                for topic in sorted_topics:
                    f.write(f"{topic}\n")

            logger.info(
                f"Successfully exported {len(sorted_topics)} unique topics to {output_file}"
            )
            print(
                f"✅ Export completed: {len(sorted_topics)} unique topics saved to {output_file}"
            )

    except Exception as e:
        logger.error(f"Failed to export task topics: {e}", exc_info=True)
        print(f"❌ Export failed: {e}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"Application Database ({settings.schema_name}) Initialization Utility"
    )
    parser.add_argument(
        "action",
        choices=[
            "init",
            "reset",
            "list-tables",
            "recreate-schema",
            "check-vector",
            "export-topics",
        ],
        help=f"'init' to create/update tables in schema '{settings.schema_name}', "
        f"'reset' to drop schema '{settings.schema_name}' and recreate tables, "
        f"'recreate-schema' to drop and create an empty schema '{settings.schema_name}' for Alembic, "
        f"'list-tables' to show tables in schema '{settings.schema_name}', "
        f"'check-vector' to verify if the pgvector extension is installed, "
        f"'export-topics' to export unique task topics to a text file.",
    )
    parser.add_argument(
        "--schema",
        type=str,
        default=settings.schema_name,
        help=f"Specify the schema name to act upon for list-tables. Defaults to '{settings.schema_name}'.",
    )
    parser.add_argument(
        "--db_type",
        choices=["app", "dataset"],
        default="app",
        help="Specify the database type for list-tables ('app' or 'dataset'). Defaults to 'app'.",
    )
    args = parser.parse_args()

    if args.action == "init":
        logger.debug(
            f"Attempting to initialize Application database tables (schema: {settings.schema_name})..."
        )
        asyncio.run(init_db())
    elif args.action == "reset":
        confirm = input(
            f"WARNING: This will delete all data in schema '{settings.schema_name}' of the Application DB. Are you sure? (yes/no): "
        )
        if confirm.lower() == "yes":
            logger.info(
                f"Attempting to reset Application database (schema: {settings.schema_name})..."
            )
            asyncio.run(reset_db())
        else:
            logger.info("Application Database reset cancelled by user.")
    elif args.action == "list-tables":
        use_dataset_eng = True if args.db_type == "dataset" else False
        db_type_log_str = "Dataset DB" if use_dataset_eng else "Application DB"
        logger.debug(
            f"Attempting to list tables in schema '{args.schema}' using {db_type_log_str}..."
        )
        asyncio.run(
            list_tables_in_schema(args.schema, use_dataset_engine=use_dataset_eng)
        )
    elif args.action == "recreate-schema":
        confirm = input(
            f"WARNING: This will delete all data in schema '{settings.schema_name}' of the Application DB. Are you sure? (yes/no): "
        )
        if confirm.lower() == "yes":
            logger.info(
                f"Attempting to recreate schema '{settings.schema_name}' in Application DB..."
            )
            asyncio.run(recreate_schema())
        else:
            logger.info("Application Database schema recreation cancelled by user.")
    elif args.action == "check-vector":
        asyncio.run(check_vector_extension())
    elif args.action == "export-topics":
        asyncio.run(export_unique_task_topics(args.schema))
    logger.info(
        f"Application Database ({settings.schema_name}) utility script finished."
    )


async def check_db_connection(engine_to_check=None, db_name="Application DB"):
    """Performs a simple query to check actual DB connectivity."""
    if engine_to_check is None:
        engine_to_check = app_engine

    # Create a new sessionmaker for this check to ensure fresh state
    # It's important that this session_maker is configured like AppAsyncSessionLocal
    # if it needs to interact with the same schema settings, etc.
    # However, for a simple "SELECT 1", default settings are usually fine.
    session_maker = async_sessionmaker(
        bind=engine_to_check,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,  # Match AppAsyncSessionLocal
        autoflush=False,  # Match AppAsyncSessionLocal
    )
    async with session_maker() as session:
        try:
            # For Application DB, it might be important to set search_path if models are not schema-qualified
            # and the test query might interact with schema-specific elements (though "SELECT 1" does not).
            # For simplicity here, we assume "SELECT 1" is schema-agnostic.
            # If schema_name is needed for some basic check:
            # await session.execute(text(f"SET search_path TO {settings.schema_name}, public"))

            result = await session.execute(text("SELECT 1"))
            if result.scalar_one() == 1:
                logger.info(
                    f"Successfully connected to {db_name} and executed a test query."
                )
                return True
            else:
                # This case should technically not be reached if "SELECT 1" executes without error and returns something.
                logger.error(
                    f"Test query to {db_name} did not return 1. This is unexpected."
                )
                # Force an error state if the return is not what's expected.
                raise RuntimeError(
                    f"Test query to {db_name} returned an unexpected result."
                )
        except Exception as e:
            logger.error(
                f"Failed to execute test query on {db_name}: {e}", exc_info=True
            )
            # Re-raise a more specific error or wrap the original to be caught by lifespan
            raise RuntimeError(
                f"Database connectivity check failed for {db_name}."
            ) from e
