"""
Progress Callback System for Timeline Generation.

This module provides progress notifications through multiple channels:
- WebSocket: For web client real-time updates
- A2A: For A2A protocol clients
- Dual: For both channels simultaneously
"""

from .a2a_progress_callback import A2AProgressCallback
from .dual_progress_callback import DualProgressCallback

__all__ = [
    "DualProgressCallback",
    "A2AProgressCallback",
]
