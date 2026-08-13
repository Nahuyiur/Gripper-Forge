from __future__ import annotations

from typing import Any

import trimesh

from .model import base_mesh_for_design, design_report
from .storage import ensure_interface_supported, resolve_pair


def evaluate_design(
    design: dict[str, Any],
    pair_id: str | None,
) -> tuple[dict[str, trimesh.Trimesh], dict[str, Any], trimesh.Trimesh]:
    """所有检查、预览与导出共用同一条几何求值路径。"""
    body, base, pair = resolve_pair(pair_id)
    if pair is not None and not pair["report"]["editable"]:
        raise ValueError("当前导入模型没有通过接口与编辑基准检查")
    ensure_interface_supported(design, pair)
    meshes, report = design_report(design, body, base)
    coupled_base = base_mesh_for_design(design, base)
    return meshes, report, coupled_base


def ready_design(
    design: dict[str, Any],
    pair_id: str | None,
) -> tuple[dict[str, trimesh.Trimesh], dict[str, Any], trimesh.Trimesh]:
    meshes, report, coupled_base = evaluate_design(design, pair_id)
    if not report["ready"]:
        raise ValueError("；".join(report["problems"]))
    return meshes, report, coupled_base
