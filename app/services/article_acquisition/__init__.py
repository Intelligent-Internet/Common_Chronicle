"""
Article Acquisition Package - Multi-Source Content Discovery and Retrieval

This package provides sophisticated article acquisition capabilities for the Common Chronicle
system. It implements multiple strategies for discovering and retrieving relevant historical
content from various sources, using both traditional keyword search and modern semantic
search techniques.

Core Components:
- service.py: Main ArticleAcquisitionService orchestrating the acquisition process
- strategies.py: Implementation of various data acquisition strategies
- components.py: Reusable components like semantic search functionality
- hybrid_strategy.py: Advanced hybrid search combining multiple approaches
"""

from app.services.article_acquisition.components import SemanticSearchComponent
from app.services.article_acquisition.service import ArticleAcquisitionService
from app.services.article_acquisition.strategies import (
    DataAcquisitionStrategy,
    DatasetWikipediaEnStrategy,
    OnlineWikinewsStrategy,
    OnlineWikipediaStrategy,
)

__all__ = [
    "DataAcquisitionStrategy",
    "OnlineWikipediaStrategy",
    "OnlineWikinewsStrategy",
    "DatasetWikipediaEnStrategy",
    "ArticleAcquisitionService",
    "SemanticSearchComponent",
]
