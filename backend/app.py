from __future__ import annotations

import io
import struct
import uuid
import zipfile
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from .builds import build_job
from .contracts import DesignRequest, ImportPairRequest
from .model import (
    ROOT,
    default_mount_mesh,
    fixed_mount_mesh,
    interface_mount_top_y,
    inspect_model_pair,
)
from .schema import public_schema
from .service import evaluate_design, ready_design
from .storage import decode_stl, get_imported_pair, get_job, set_job, store_imported_pair

app = FastAPI(title="夹爪设计器几何服务", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    store_imported_pair(pair_id, {
        "body_name": Path(req.body_name).name,
        "base_name": Path(req.base_name).name,
        "body_bytes": body_bytes,
        "base_bytes": base_bytes,
        "body_mesh": body,
        "base_mesh": base,
        "mount_bytes": fixed_mount_mesh(body).export(file_type="stl"),
        "report": report,
    })
    return {"pair_id": pair_id, "report": report}


@app.get("/api/imported")
def imported(pair_id: str, part: str) -> Response:
    pair = get_imported_pair(pair_id)
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
        _, report, _ = evaluate_design(req.design, req.pair_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"report": report}


@app.post("/api/preview")
def preview(req: DesignRequest, part: str = Query("body", pattern="^(body|mount|base)$")) -> Response:
    """按零件返回与导出一致的热预览；body 已包含安装区，不能再叠加 mount。"""
    try:
        meshes, _, coupled_base = ready_design(req.design, req.pair_id)
        role = "finger" if "finger" in meshes else "a"
        if part == "body":
            preview_mesh = meshes[role]
        elif part == "mount":
            preview_mesh = fixed_mount_mesh(
                meshes[role],
                interface_mount_top_y(req.design.get("interface")),
            )
        else:
            preview_mesh = coupled_base
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
        meshes, _, coupled_base = ready_design(req.design, req.pair_id)
        role = "finger" if "finger" in meshes else "a"
        body_bytes = bytes(meshes[role].export(file_type="stl"))
        base_bytes = bytes(coupled_base.export(file_type="stl"))
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

@app.post("/api/build")
def build(req: DesignRequest, tasks: BackgroundTasks) -> dict[str, str]:
    job = uuid.uuid4().hex[:16]
    set_job(job, {"state": "running"})
    tasks.add_task(build_job, job, req.design, req.pair_id)
    return {"job": job}


@app.get("/api/job")
def job_status(job: str = Query(..., min_length=1)) -> dict[str, Any]:
    data = get_job(job)
    if data is None:
        raise HTTPException(status_code=404, detail="没有找到这个构建任务")
    return {k: v for k, v in data.items() if k not in {"files", "base_bytes"}}


@app.get("/api/stl")
def stl(job: str, role: str) -> FileResponse:
    data = get_job(job)
    if not data or data.get("state") != "done":
        raise HTTPException(status_code=404, detail="STL 尚未生成")
    path = data.get("files", {}).get(role)
    if not path or not Path(path).is_file():
        raise HTTPException(status_code=404, detail="没有找到这个手指文件")
    return FileResponse(path, media_type="model/stl", filename=Path(path).name)


@app.get("/api/package")
def package(job: str) -> Response:
    data = get_job(job)
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
