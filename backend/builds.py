from __future__ import annotations

from typing import Any

from .service import ready_design
from .storage import OUT, set_job


def build_job(job: str, design: dict[str, Any], pair_id: str | None) -> None:
    try:
        meshes, report, coupled_base = ready_design(design, pair_id)
        folder = OUT / job
        folder.mkdir(parents=True, exist_ok=True)
        files: dict[str, str] = {}
        for role, mesh in meshes.items():
            name = report["fingers"][role]["stl"]
            path = folder / name
            path.write_bytes(mesh.export(file_type="stl"))
            files[role] = str(path)
        set_job(job, {
            "state": "done",
            "report": report,
            "files": files,
            "base_bytes": coupled_base.export(file_type="stl"),
        })
    except Exception as exc:  # pragma: no cover - 防止后台线程静默失败
        set_job(job, {"state": "failed", "error": str(exc)})
