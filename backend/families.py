from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ConstructionFamily:
    """一个可编辑基本构型的完整注册信息。"""

    family_id: str
    title: str
    description: str
    generator: str
    default_template: str
    genes: dict[str, dict[str, Any]]
    groups: list[dict[str, str]]
    seed: dict[str, Any]
    version: int = 1

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.family_id,
            "title": self.title,
            "description": self.description,
            "generator": self.generator,
            "default_template": self.default_template,
            "genes": self.genes,
            "groups": self.groups,
            "seed": self.seed,
            "version": self.version,
        }


class FamilyRegistry:
    """保持构型 ID 唯一，并为 API 和几何分发提供单一事实来源。"""

    def __init__(self, families: Iterable[ConstructionFamily] = ()) -> None:
        self._families: dict[str, ConstructionFamily] = {}
        for family in families:
            self.register(family)

    def register(self, family: ConstructionFamily) -> None:
        normalized_id = family.family_id.replace("-", "").replace("_", "")
        if not family.family_id or not normalized_id.isalnum():
            raise ValueError("构型 ID 只能包含字母、数字、下划线和短横线")
        if family.family_id in self._families:
            raise ValueError(f"构型 ID 重复：{family.family_id}")
        self._families[family.family_id] = family

    def require(self, family_id: str) -> ConstructionFamily:
        try:
            return self._families[family_id]
        except KeyError as exc:
            raise ValueError(f"未知的基本构型：{family_id}") from exc

    def values(self) -> tuple[ConstructionFamily, ...]:
        return tuple(self._families.values())

    def public_catalog(self) -> list[dict[str, Any]]:
        return [family.to_public() for family in self.values()]

    def gene_sets(self) -> dict[str, dict[str, dict[str, Any]]]:
        return {family.family_id: family.genes for family in self.values()}

    def group_sets(self) -> dict[str, list[dict[str, str]]]:
        return {family.family_id: family.groups for family in self.values()}
