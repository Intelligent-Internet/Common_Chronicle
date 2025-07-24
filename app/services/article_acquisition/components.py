"""
Article Acquisition Components - Core Search and Embedding Components

This module provides the fundamental components for article acquisition, including
semantic search capabilities, BM25 text search, and embedding generation. It serves
as the foundation for various search strategies by offering reusable, high-performance
search components.

The module implements both traditional keyword-based search (BM25) and modern
semantic search using sentence transformers, with optimized database queries
and efficient embedding generation.
"""

import re
from typing import Any

import torch
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.db import DatasetAsyncSessionLocal
from app.schemas import SourceArticle
from app.services.embedding_service import embedding_service
from app.utils.logger import setup_logger

logger = setup_logger("article_acquisition_components")


DEFAULT_SEMANTIC_SEARCH_MODEL = "Snowflake/snowflake-arctic-embed-m-v2.0"
SNOWFLAKE_QUERY_PREFIX = "query: "
EXPECTED_DIMENSION = 768  # For Snowflake/


CHUNK_CANDIDATE_POOL_SIZE = 100


def escape_paradedb_query(query_text: str) -> str:
    """
    Escape special characters for ParadeDB BM25 search to prevent syntax errors.
    """
    # Remove or escape problematic characters for ParadeDB
    # Approach: Remove special characters and use simple text search
    escaped_query = re.sub(r'[():"\'\\]', " ", query_text)

    # Clean up multiple spaces
    escaped_query = re.sub(r"\s+", " ", escaped_query).strip()

    # If the query becomes empty, use a fallback
    if not escaped_query:
        return "search"

    return escaped_query


class SemanticSearchComponent:
    """Component for performing semantic search using the unified embedding service."""

    def __init__(
        self,
        model_name: str = DEFAULT_SEMANTIC_SEARCH_MODEL,
        device: str | None = None,
    ):
        # Use unified embedding service instead of loading own model
        logger.info("SemanticSearchComponent using unified embedding service")
        self.model_name = model_name
        self.device = (
            device if device else ("cuda" if torch.cuda.is_available() else "cpu")
        )

        # Check if unified service is ready
        if embedding_service.is_ready():
            logger.info("Unified embedding service is ready for semantic search")
        else:
            logger.warning("Unified embedding service is not ready")

    async def search_articles_by_title_only_bm25(
        self, query_text: str, article_limit: int
    ) -> list[dict]:
        """
        Performs BM25 search ONLY on the title using ParadeDB.
        This method will return the raw database rows as dictionaries.
        """
        # Escape the query to prevent syntax errors
        escaped_query = escape_paradedb_query(query_text)

        # Use a simpler query format without field specification to avoid syntax errors
        sql_query = text(
            """
            SELECT id, title, url, source_id, chunk_index, chunk_text, paradedb.score(id) as score
            FROM public.ts_wikipedia_en_embed
            WHERE chunk_text @@@ :query
            ORDER BY score DESC
            LIMIT :limit
        """
        )
        try:
            async with DatasetAsyncSessionLocal() as session:
                result = await session.execute(
                    sql_query, {"query": escaped_query, "limit": article_limit}
                )
                # Return list of dicts directly
                return [row._asdict() for row in result.fetchall()]
        except SQLAlchemyError as e:
            logger.error(
                f"Database error during title-only BM25 search: {e}", exc_info=True
            )
            return []
        except Exception as e:
            logger.error(
                f"An unexpected error occurred during title-only BM25 search: {e}",
                exc_info=True,
            )
            return []

    async def get_embedding(
        self, text_content: str
    ) -> str | None:  # Returns string for pgvector
        """Generates a normalized embedding string for the given text content using the unified embedding service."""
        try:
            # Use unified embedding service
            return embedding_service.get_embedding_for_pgvector(text_content)
        except Exception as e:
            logger.error(
                f"Error generating embedding for text using unified service: {e}",
                exc_info=True,
            )
            return None

    async def search_articles(
        self, query_text: str, article_limit: int = settings.default_article_limit
    ) -> list[SourceArticle]:
        """
        Searches for articles in the local Wikipedia dataset semantically similar to the query_text.
        """
        if not embedding_service.is_ready():
            logger.error("Unified embedding service not ready. Cannot perform search.")
            return []

        # query_embedding_str will now be the string from get_embedding
        query_embedding_str = await self.get_embedding(query_text)
        if query_embedding_str is None:  # Check if string generation failed
            logger.error(
                "Failed to generate query embedding string. Cannot perform search."
            )
            return []

        # logger.info(f"Generated query embedding dimension: {len(query_embedding)}") # This is 384, confirmed by DEBUG logs

        articles_data: list[SourceArticle] = []
        # query_embedding_str = str(query_embedding) # No longer convert to string here

        # This SQL query is complex and involves multiple steps:
        # 1. Find relevant chunks using vector similarity (cosine distance '<=>').
        # 2. Identify unique parent articles (source_id) from these chunks.
        # 3. Limit to the top 'article_limit' articles.
        # 4. Fetch all chunks for these selected articles.
        # 5. Fetch metadata for these articles from the main articles table.
        # 6. Reconstruct article text and create SourceArticle objects.
        # Note: 'ts_wikipedia_en' is assumed to be the articles metadata table (id, title, url)
        #       'ts_wikipedia_en_embed' is assumed to have (id, source_id, chunk_text, chunk_index, embedding)
        #       'source_id' in 'ts_wikipedia_en_embed' links to 'id' in 'ts_wikipedia_en'.

        sql_query = text(
            """
        WITH RankedChunks AS (
            -- Find chunks most similar to the query embedding using cosine distance
            SELECT
                source_id,
                chunk_text,
                chunk_index,
                (vector <=> CAST(:query_embedding AS vector)) as distance,
                ((2 - (vector <=> CAST(:query_embedding AS vector))) / 2) as similarity
            FROM
                public.ts_wikipedia_en_embed
            ORDER BY
                (vector <=> CAST(:query_embedding AS vector)) ASC
            LIMIT :chunk_candidate_pool_size -- Limit initial chunk pool to avoid excessive processing
        ),
        TopArticles AS (
            -- From the ranked chunks, select distinct articles and their best (min) distance
            SELECT
                source_id,
                MIN(distance) as min_distance
            FROM
                RankedChunks
            GROUP BY
                source_id
            ORDER BY
                min_distance ASC
            LIMIT :article_limit
        ),
        ArticleChunks AS (
            -- Get all chunks for the selected top articles
            SELECT
                ta.source_id,
                rce.chunk_text,
                rce.chunk_index
            FROM
                public.ts_wikipedia_en_embed rce
            JOIN
                TopArticles ta ON rce.source_id = ta.source_id
            ORDER BY
                ta.source_id, rce.chunk_index ASC
        ),
        ArticleMetadata AS (
            -- Get metadata for the selected top articles
            SELECT
                id, -- This is the page_id, corresponds to source_id
                title,
                url
                -- revision_id, -- if needed
                -- article_timestamp -- if needed
            FROM
                public.ts_wikipedia_en -- Main metadata table for Wikipedia articles
            WHERE
                id IN (SELECT source_id FROM TopArticles)
        )
        -- Combine metadata with concatenated chunks
        SELECT
            am.id AS article_id,
            am.title AS article_title,
            am.url AS article_url,
            ac.chunk_text,
            ac.chunk_index
        FROM
            ArticleMetadata am
        JOIN
            ArticleChunks ac ON am.id = ac.source_id
        ORDER BY
            am.id, ac.chunk_index ASC;
        """
        )

        if not DatasetAsyncSessionLocal:
            logger.error(
                "DatasetAsyncSessionLocal is not configured. Cannot query semantic search DB."
            )
            return []

        reconstructed_articles: dict[str, dict[str, Any]] = {}

        try:
            async with DatasetAsyncSessionLocal() as session:
                logger.info(
                    f"Executing semantic search for query: '{query_text[:100]}...' with limit {article_limit}"
                )
                result = await session.execute(
                    sql_query,
                    {
                        "query_embedding": query_embedding_str,  # Use the formatted string
                        "article_limit": article_limit,
                        "chunk_candidate_pool_size": CHUNK_CANDIDATE_POOL_SIZE,
                    },
                )
                rows = result.fetchall()  # list of Row objects

                if not rows:
                    logger.info("Semantic search returned no results from database.")
                    return []

                # Group chunks by article_id and reconstruct text
                for row in rows:
                    # Access columns by their string names (labels in the SELECT statement)
                    page_id = str(row.article_id)  # Ensure string ID
                    title = row.article_title
                    url = row.article_url
                    chunk_text = row.chunk_text
                    # chunk_index = row.chunk_index # Not directly used in Article model here, but good for ordering

                    if page_id not in reconstructed_articles:
                        reconstructed_articles[page_id] = {
                            "page_id": page_id,
                            "title": title,
                            "url": url,
                            "chunks": [],
                            # Store metadata for the Article object
                            "metadata": {
                                "retrieved_title": title,
                                "retrieved_url": url,
                                "query_text": query_text,
                            },
                        }
                    if chunk_text:  # Ensure chunk_text is not None before appending
                        reconstructed_articles[page_id]["chunks"].append(chunk_text)

                for page_id, data in reconstructed_articles.items():
                    full_text = "".join(data["chunks"]).strip()
                    if not full_text:
                        logger.warning(
                            f"SourceArticle ID {page_id} (Title: {data['title']}) resulted in empty text after chunk concatenation. Skipping."
                        )
                        continue

                    articles_data.append(
                        SourceArticle(
                            source_name="wikipedia_local_semantic",
                            source_url=data["url"],
                            source_identifier=page_id,  # Using page_id from ts_wikipedia_en.id as the identifier
                            title=data["title"],
                            text_content=full_text,
                            language="en",  # Assuming local Wikipedia is English
                            metadata=data["metadata"],
                        )
                    )
                logger.info(
                    f"Semantic search successfully processed {len(articles_data)} articles."
                )

        except Exception as e:
            logger.error(f"Database error during semantic search: {e}", exc_info=True)

        return articles_data

    async def perform_semantic_search(
        self, query_text: str, limit: int = settings.default_article_limit
    ) -> list[str]:
        """
        Performs semantic search and returns a list of unique parent document IDs.
        """
        # ... implementation ...

    async def get_documents_by_ids(self, doc_ids: list[str]) -> list[dict[str, Any]]:
        """
        Retrieves full document data for a list of document IDs.
        """
        # ... implementation ...

    async def search_article_chunks(
        self, query_text: str, limit: int = settings.default_article_limit
    ) -> list[dict[str, Any]]:
        """
        Searches for individual text chunks most similar to the query text.
        This is the new, efficient method that returns raw chunks instead of full articles.
        """
        if not self.is_ready():
            logger.error("SemanticSearchComponent not ready. Cannot perform search.")
            return []

        query_embedding_str = await self.get_embedding(query_text)
        if not query_embedding_str:
            logger.error("Failed to generate query embedding. Cannot perform search.")
            return []

        sql_query = text(
            """
            SELECT
                meta.id as doc_id,
                meta.title,
                meta.url,
                embed.chunk_text,
                embed.chunk_index,
                ((2 - (embed.vector <=> CAST(:query_embedding AS vector))) / 2) as similarity
            FROM
                public.ts_wikipedia_en_embed AS embed
            JOIN
                public.ts_wikipedia_en AS meta ON embed.source_id = meta.id
            ORDER BY
                embed.vector <=> CAST(:query_embedding AS vector)
            LIMIT :limit
            """
        )

        async with DatasetAsyncSessionLocal() as session:
            result = await session.execute(
                sql_query,
                {"query_embedding": query_embedding_str, "limit": limit},
            )
            chunks = [dict(row) for row in result.mappings()]
            return chunks

    def is_ready(self) -> bool:
        """Check if the component is ready to be used."""
        return embedding_service.is_ready()


# Example Usage (for testing, not part of the component itself)
# async def main():
#     semantic_search_component = SemanticSearchComponent()
#     if semantic_search_component.model: # Check if model loaded
#         query = "Impact of World War II on global economy"
#         results = await semantic_search_component.search_articles(query, article_limit=3)
#         for article in results:
#             print(f"Title: {article.title}")
#             print(f"URL: {article.source_url}")
#             print(f"Identifier: {article.source_identifier}")
#             print(f"Source: {article.source_name}")
#             print(f"Text Preview: {article.text_content[:200]}...")
#             print("---")

# if __name__ == "__main__":
#     # This requires a running asyncio event loop and proper DB setup to test.
#     # You might need to set up environment variables for DB connection if DatasetAsyncSessionLocal relies on them.
#     # e.g., by loading .env file if your db.py does that.
#     # from dotenv import load_dotenv
#     # load_dotenv()
#     asyncio.run(main())
