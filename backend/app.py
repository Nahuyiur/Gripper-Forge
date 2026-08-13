from __future__ import annotations

import io
import base64
import struct
import threading
import uuid
import zipfile
from pathlib import Path
from typing import Any

import trimesh

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from .model import (
    ROOT,
    base_mesh,
    base_mesh_for_design,
    default_mount_mesh,
    design_report,
    fixed_mount_mesh,
    interface_mount_top_y,
    inspect_model_pair,
    interface_is_default,
    source_mesh,
)
from .schema import public_schema

app = FastAPI(title="夹爪设计器几何服务", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

OUT = ROOT / "backend" / "out"
OUT.mkdir(parents=True, exist_ok=True)
JOBS: dict[str, dict[str, Any]] = {}
IMPORTED_PAIRS: dict[str, dict[str, Any]] = {}
LOCK = threading.Lock()


class DesignRequest(BaseModel):
    design: dict[str, Any]
    pair_id: str | None = None


class ImportPairRequest(BaseModel):
    body_name: str
    body_base64: str
    base_name: str
    base_base64: str


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


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "夹爪设计器几何服务"}


@app.get("/api/schema")
def schema() -> dict[str, Any]:
    return {"schema": public_schema(), "ready": True}


@app.get("/api/original")
def original() -> FileResponse:
    return FileResponse(ROOT / "public" / "zhuti-2-0813-original.stl", media_type="model/stl", filename="zhuti-2-0813-original.stl")


@app.get("/api/base")
def base() -> FileResponse:
    return FileResponse(ROOT / "public" / "底座-original.stl", media_type="model/stl", filename="底座.stl")


@app.get("/api/mount")
def mount() -> Response:
    """兼容旧客户端：返回默认接口安装区；可调版本使用 POST /api/preview?part=mount。"""
    return Response(content=default_mount_mesh().export(file_type="stl"), media_type="model/stl")


@app.post("/api/import-pair")
def import_pair(req: ImportPairRequest) -> dict[str, Any]:
    try:
        body_bytes, body = decode_stl(req.body_name, req.body_base64)
        base_bytes, base = decode_stl(req.base_name, req.base_base64)
        report = inspect_model_pair(body, base)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    pair_id = uuid.uuid4().hex[:16]
    with LOCK:
        IMPORTED_PAIRS[pair_id] = {
            "body_name": Path(req.body_name).name,
            "base_name": Path(req.base_name).name,
            "body_bytes": body_bytes,
            "base_bytes": base_bytes,
            "body_mesh": body,
            "base_mesh": base,
            "mount_bytes": fixed_mount_mesh(body).export(file_type="stl"),
            "report": report,
        }
    return {"pair_id": pair_id, "report": report}


@app.get("/api/imported")
def imported(pair_id: str, part: str) -> Response:
    pair = IMPORTED_PAIRS.get(pair_id)
    if pair is None:
        raise HTTPException(status_code=404, detail="导入模型已失效")
    if part not in {"body", "base", "mount"}:
        raise HTTPException(status_code=422, detail="零件类型无效")
    if part == "mount":
        return Response(content=pair["mount_bytes"], media_type="model/stl")
    return Response(content=pair[f"{part}_bytes"], media_type="model/stl")


@app.post("/api/check")
def check(req: DesignRequest) -> dict[str, Any]:
    try:
        body, base, pair = resolve_pair(req.pair_id)
        if pair is not None and not pair["report"]["editable"]:
            raise ValueError("当前导入模型没有通过接口与编辑基准检查")
        ensure_interface_supported(req.design, pair)
        _, report = design_report(req.design, body, base)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"report": report}


@app.post("/api/preview")
def preview(req: DesignRequest, part: str = Query("body", pattern="^(body|mount|base)$")) -> Response:
    """按零件返回与导出一致的热预览；body 已包含安装区，不能再叠加 mount。"""
    try:
        body, base, pair = resolve_pair(req.pair_id)
        if pair is not None and not pair["report"]["editable"]:
            raise ValueError("当前导入模型没有通过接口与编辑基准检查")
        ensure_interface_supported(req.design, pair)
        meshes, report = design_report(req.design, body, base)
        if not report["ready"]:
            raise ValueError("；".join(report["problems"]))
        role = "finger" if "finger" in meshes else "a"
        if part == "body":
            preview_mesh = meshes[role]
        elif part == "mount":
            preview_mesh = fixed_mount_mesh(
                meshes[role],
                interface_mount_top_y(req.design.get("interface")),
            )
        else:
            preview_mesh = base_mesh_for_design(req.design, base)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=preview_mesh.export(file_type="stl"),
        media_type="model/stl",
        headers={"X-Gripper-Part": part},
    )


@app.post("/api/preview-live")
def preview_live(req: DesignRequest) -> Response:
    """一次生成主体和底座，用紧凑二进制包支持滑块拖动时连续重建 STL。"""
    try:
        body, base, pair = resolve_pair(req.pair_id)
        if pair is not None and not pair["report"]["editable"]:
            raise ValueError("当前导入模型没有通过接口与编辑基准检查")
        ensure_interface_supported(req.design, pair)
        meshes, report = design_report(req.design, body, base)
        if not report["ready"]:
            raise ValueError("；".join(report["problems"]))
        role = "finger" if "finger" in meshes else "a"
        body_bytes = bytes(meshes[role].export(file_type="stl"))
        base_bytes = bytes(base_mesh_for_design(req.design, base).export(file_type="stl"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    header = struct.pack("<4sII", b"GRIP", len(body_bytes), len(base_bytes))
    return Response(
        content=header + body_bytes + base_bytes,
        media_type="application/vnd.gripper.live-preview",
        headers={
            "X-Gripper-Body-Bytes": str(len(body_bytes)),
            "X-Gripper-Base-Bytes": str(len(base_bytes)),
        },
    )


def build_job(job: str, design: dict[str, Any], pair_id: str | None) -> None:
    try:
        body, base, pair = resolve_pair(pair_id)
        if pair is not None and not pair["report"]["editable"]:
            raise ValueError("当前导入模型没有通过接口与编辑基准检查")
        ensure_interface_supported(design, pair)
        meshes, report = design_report(design, body, base)
        coupled_base = base_mesh_for_design(design, base)
        folder = OUT / job
        folder.mkdir(parents=True, exist_ok=True)
        files: dict[str, str] = {}
        for role, mesh in meshes.items():
            name = report["fingers"][role]["stl"]
            path = folder / name
            path.write_bytes(mesh.export(file_type="stl"))
            files[role] = str(path)
        with LOCK:
            JOBS[job] = {
                "state": "done",
                "report": report,
                "files": files,
                "base_bytes": coupled_base.export(file_type="stl"),
            }
    except Exception as exc:  # pragma: no cover - 防止后台线程静默失败
        with LOCK:
            JOBS[job] = {"state": "failed", "error": str(exc)}


@app.post("/api/build")
def build(req: DesignRequest, tasks: BackgroundTasks) -> dict[str, str]:
    job = uuid.uuid4().hex[:16]
    with LOCK:
        JOBS[job] = {"state": "running"}
    tasks.add_task(build_job, job, req.design, req.pair_id)
    return {"job": job}


@app.get("/api/job")
def job_status(job: str = Query(..., min_length=1)) -> dict[str, Any]:
    data = JOBS.get(job)
    if data is None:
        raise HTTPException(status_code=404, detail="没有找到这个构建任务")
    return {k: v for k, v in data.items() if k not in {"files", "base_bytes"}}


@app.get("/api/stl")
def stl(job: str, role: str) -> FileResponse:
    data = JOBS.get(job)
    if not data or data.get("state") != "done":
        raise HTTPException(status_code=404, detail="STL 尚未生成")
    path = data.get("files", {}).get(role)
    if not path or not Path(path).is_file():
        raise HTTPException(status_code=404, detail="没有找到这个手指文件")
    return FileResponse(path, media_type="model/stl", filename=Path(path).name)


@app.get("/api/package")
def package(job: str) -> Response:
    data = JOBS.get(job)
    if not data or data.get("state") != "done":
        raise HTTPException(status_code=404, detail="文件包尚未生成")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in data["files"].values():
            zf.write(path, arcname=Path(path).name)
        zf.writestr("Robotiq转接底座.stl", data["base_bytes"])
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="gripper-fingers.zip"'},
    )
