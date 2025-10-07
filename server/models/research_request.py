from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ResearchRequest:
    request_id: str
    topic: str
    preferences: Dict[str, str]
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    plan: Optional[Dict[str, Any]] = None
    draft_versions: List[Dict[str, Any]] = field(default_factory=list)

    # TODO: Convert to ORM model aligned with chosen persistence library
