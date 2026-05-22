"""Shared worker return contract for generation workers.

This module is intentionally small so technique-specific worker modules can
return pipeline-compatible results without importing generation_pipeline and
creating circular imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class WorkerResult:
    technique: str
    testcases: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    elapsed_ms: int = 0
    error: Optional[str] = None
