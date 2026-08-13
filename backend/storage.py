from __future__ import annotations

import base64
import threading
from pathlib import Path
from typing import Any

import trimesh

from .model import ROOT, base_mesh, interface_is_default, source_mesh

OUT = ROOT / "backend" / "out"
OUT.mkdir(parents=True, exist_ok=True)

JOBS: dict[str, dict[str, Any]] = {}
IMPORTED_PAIRS: dict[str, dict[str, Any]] = {}
LOCK = threading.Lock()


def decode_stl(name: str, encoded: str) -> tuple[bytes, trimesh.Trimesh]:
    if Path(name).suffix.lower() != ".stl":
        raise ValueError("只能导入 STL 文件")
    try:
        content = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("STL 文件内容无法读取") from exc
    if not content or len(content) > 20 * 1024 * 1024:
        raise ValueError("单个 STL 文件必须小于 20 MB")
    try:
        mesh = trimesh.load_mesh(trimesh.util.wrap_as_stream(content), file_type="stl", process=True)
    except Exception as exc:
        raise ValueError(f"{Path(name).name} 不是有效的 STL 网格") from exc
    if not isinstance(mesh, trimesh.Trimesh):
        if not getattr(mesh, "geometry", None):
            raise ValueError(f"{Path(name).name} 中没有可用实体")
        mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))
    if len(mesh.faces) == 0:
        raise ValueError(f"{Path(name).name} 中没有三角面")
    return content, mesh


def resolve_pair(pair_id: str | None) -> tuple[trimesh.Trimesh, trimesh.Trimesh, dict[str, Any] | None]:
    if not pair_id:
        return source_mesh(), base_mesh(), None
    pair = IMPORTED_PAIRS.get(pair_id)
    if pair is None:
        raise ValueError("导入模型已失效，请重新选择主体和底座")
    return pair["body_mesh"], pair["base_mesh"], pair


def ensure_interface_supported(design: dict[str, Any], pair: dict[str, Any] | None) -> None:
    if pair is not None and not interface_is_default(design.get("interface")):
        raise ValueError("导入模型缺少可重建接口的特征语义；仅支持默认三孔参数")


def store_imported_pair(pair_id: str, pair: dict[str, Any]) -> None:
    with LOCK:
        IMPORTED_PAIRS[pair_id] = pair


def get_imported_pair(pair_id: str) -> dict[str, Any] | None:
    return IMPORTED_PAIRS.get(pair_id)


def set_job(job_id: str, data: dict[str, Any]) -> None:
    with LOCK:
        JOBS[job_id] = data


def get_job(job_id: str) -> dict[str, Any] | None:
    return JOBS.get(job_id)
