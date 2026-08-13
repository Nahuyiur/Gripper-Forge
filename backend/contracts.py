from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class DesignRequest(BaseModel):
    design: dict[str, Any]
    pair_id: str | None = None


class ImportPairRequest(BaseModel):
    body_name: str
    body_base64: str
    base_name: str
    base_base64: str
