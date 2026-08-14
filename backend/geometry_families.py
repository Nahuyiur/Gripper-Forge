from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import trimesh
from shapely.geometry import Polygon


# These coordinates intentionally match the shared body/mount contract in
# backend.model.  This module only creates the active body above the interface;
# the fixed three-hole mount and coupled Robotiq base remain owned by model.py.
MOUNT_TOP_Y_MM = 55.0
MOUNT_OVERLAP_MM = 1.0
ROOT_THICKNESS_MM = 26.0
Z_CENTER_MM = -13.0


ARC_WRAP_GENES = {
    "finger_length_mm": {
        "min": 55.0, "max": 100.0, "step": 0.5, "group": "envelope",
        "label": "包覆指有效长度", "unit": "毫米",
        "blurb": "控制安装区以上宽面指身的长度，不改变共享三孔接口。",
    },
    "tip_depth_mm": {
        "min": 7.0, "max": 16.0, "step": 0.5, "group": "envelope",
        "label": "指端纵深", "unit": "毫米",
        "blurb": "控制侧视图中指端的实体纵深；根部保持宽厚并连续渐缩。",
    },
    "contact_width_mm": {
        "min": 14.0, "max": 30.0, "step": 0.5, "group": "contact",
        "label": "宽面接触宽度", "unit": "毫米",
        "blurb": "控制指端沿孔轴方向的宽度，形成适合圆物包覆的宽接触面。",
    },
    "wrap_depth_mm": {
        "min": 0.0, "max": 6.0, "step": 0.25, "group": "contact",
        "label": "连续弧槽深度", "unit": "毫米",
        "blurb": "在接触侧形成连续平滑弧槽；零值为平直接触面。",
    },
    "toe_lip_mm": {
        "min": 0.0, "max": 4.0, "step": 0.25, "group": "contact",
        "label": "圆钝止挡高度", "unit": "毫米",
        "blurb": "让最前端平滑内收，帮助限制圆柱沿指长方向滑出。",
    },
}

ARC_WRAP_GROUPS = [
    {"key": "envelope", "title": "宽面薄身轮廓"},
    {"key": "contact", "title": "弧面包覆接触"},
]

ARC_WRAP_DEFAULT = {
    "finger_length_mm": 78.0,
    "tip_depth_mm": 10.0,
    "contact_width_mm": 22.0,
    "wrap_depth_mm": 3.5,
    "toe_lip_mm": 1.5,
}


PRECISION_TIP_GENES = {
    "finger_length_mm": {
        "min": 45.0, "max": 78.0, "step": 0.5, "group": "wedge",
        "label": "精密指有效长度", "unit": "毫米",
        "blurb": "控制紧凑楔形主体的有效长度，不改变共享三孔接口。",
    },
    "taper_start": {
        "min": 0.20, "max": 0.70, "step": 0.01, "group": "wedge",
        "label": "渐缩起点", "unit": "比例",
        "blurb": "控制前宽后窄轮廓从何处开始收尖。",
    },
    "tip_depth_mm": {
        "min": 2.5, "max": 8.0, "step": 0.25, "group": "tip",
        "label": "楔尖纵深", "unit": "毫米",
        "blurb": "控制侧视图中精密指端的厚薄。",
    },
    "tip_width_mm": {
        "min": 4.0, "max": 14.0, "step": 0.5, "group": "tip",
        "label": "楔尖接触宽度", "unit": "毫米",
        "blurb": "控制指端沿孔轴方向的窄接触宽度。",
    },
    "tip_offset_mm": {
        "min": -4.0, "max": 4.0, "step": 0.25, "group": "tip",
        "label": "楔尖侧偏", "unit": "毫米",
        "blurb": "让尖端中心线平滑侧偏，便于适配受限空间。",
    },
    "contact_pad_mm": {
        "min": 4.0, "max": 16.0, "step": 0.5, "group": "tip",
        "label": "平直接触段长度", "unit": "毫米",
        "blurb": "在楔形末端保留一段等纵深的局部平直接触区。",
    },
}

PRECISION_TIP_GROUPS = [
    {"key": "wedge", "title": "紧凑楔形主体"},
    {"key": "tip", "title": "精密接触尖端"},
]

PRECISION_TIP_DEFAULT = {
    # 由用户提供的 gripper-fingers.zip / 夹爪手指.stl 反算：在紧凑
    # 20 x 20 mm 三孔接口下，包围盒、尖端截面和体积均与参考件一致。
    "finger_length_mm": 64.0,
    "taper_start": 0.30,
    "tip_depth_mm": 4.5,
    "tip_width_mm": 4.5,
    "tip_offset_mm": -1.75,
    "contact_pad_mm": 5.0,
}


FAMILY_SPECS = {
    "arc-wrap-solid": ARC_WRAP_GENES,
    "precision-wedge-solid": PRECISION_TIP_GENES,
}

FAMILY_DEFAULTS = {
    "arc-wrap-solid": ARC_WRAP_DEFAULT,
    "precision-wedge-solid": PRECISION_TIP_DEFAULT,
}


@dataclass(frozen=True)
class ActiveBody:
    mesh: trimesh.Trimesh
    genes: dict[str, float | int]
    contact_feature_count: int
    opening_loss_mm: float
    note: str


def _smoothstep(value: np.ndarray | float) -> np.ndarray | float:
    t = np.clip(value, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def normalize_family_genes(generator: str, raw: dict[str, Any] | None) -> dict[str, float | int]:
    try:
        specs = FAMILY_SPECS[generator]
        defaults = FAMILY_DEFAULTS[generator]
    except KeyError as exc:
        raise ValueError(f"未知的程序构型生成器：{generator}") from exc
    raw = raw or {}
    normalized: dict[str, float | int] = {}
    for name, spec in specs.items():
        value = raw.get(name, defaults[name])
        value = int(round(float(value))) if spec.get("int") else float(value)
        tolerance = max(1e-9, float(spec["step"]) * 1e-9)
        if value < spec["min"] - tolerance or value > spec["max"] + tolerance:
            raise ValueError(f"{spec['label']}超出允许范围")
        normalized[name] = max(spec["min"], min(spec["max"], value))
    return normalized


def _profile_mesh(
    contact_x: Callable[[float], float],
    back_x: Callable[[float], float],
    length: float,
    tip_width: float,
) -> trimesh.Trimesh:
    """Extrude one continuous solid profile, then taper its axial width."""
    samples = max(120, int(length * 3.0))
    positions = np.linspace(-MOUNT_OVERLAP_MM, length, samples)
    contact = [(float(u), float(contact_x(float(u)))) for u in positions]
    back = [(float(u), float(back_x(float(u)))) for u in positions[::-1]]
    region = Polygon(contact + back).buffer(0).simplify(0.015, preserve_topology=True)
    if region.geom_type != "Polygon" or region.is_empty or not region.is_valid or region.area <= 1.0:
        raise ValueError("当前参数无法形成有效的连续实体轮廓")

    local = trimesh.creation.extrude_polygon(region, height=ROOT_THICKNESS_MM, engine="earcut")
    vertices = local.vertices.copy()
    u = vertices[:, 0].copy()
    profile_x = vertices[:, 1].copy()
    local_z = vertices[:, 2].copy()
    t = np.asarray(_smoothstep(np.clip(u / max(length, 1e-6), 0.0, 1.0)), dtype=np.float64)
    width_factor = 1.0 + (tip_width / ROOT_THICKNESS_MM - 1.0) * t
    # Sink the first millimetre slightly into the fixed mount so boolean union
    # never depends on merely coincident top/bottom faces.
    join = 0.985 + 0.015 * np.asarray(
        _smoothstep(np.clip((u + MOUNT_OVERLAP_MM) / 4.0, 0.0, 1.0)),
        dtype=np.float64,
    )
    vertices[:, 0] = profile_x
    vertices[:, 1] = MOUNT_TOP_Y_MM + u
    vertices[:, 2] = Z_CENTER_MM + (local_z - ROOT_THICKNESS_MM / 2.0) * width_factor * join
    mesh = trimesh.Trimesh(vertices=vertices, faces=local.faces.copy(), process=True)
    if mesh.volume < 0:
        mesh.invert()
    mesh.remove_unreferenced_vertices()
    return mesh


def _arc_wrap_body(raw: dict[str, Any] | None) -> ActiveBody:
    genes = normalize_family_genes("arc-wrap-solid", raw)
    length = float(genes["finger_length_mm"])
    tip_depth = float(genes["tip_depth_mm"])
    wrap_depth = float(genes["wrap_depth_mm"])
    toe_lip = float(genes["toe_lip_mm"])
    # 与原创构型默认 22 mm 双孔轴距下约 31.93 mm 的底座外沿对齐，
    # 避免底座在双孔侧单独凸出，同时保留约 5 mm 的孔边距。
    root_depth = 31.5

    def contact_x(u: float) -> float:
        t = float(np.clip(u / length, 0.0, 1.0))
        cradle = wrap_depth * float(np.sin(np.pi * t) ** 2)
        toe = toe_lip * float(_smoothstep((t - 0.78) / 0.22))
        return cradle - toe

    def back_x(u: float) -> float:
        t = float(np.clip(u / length, 0.0, 1.0))
        depth = root_depth + (tip_depth - root_depth) * float(_smoothstep(t))
        return contact_x(u) + depth

    mesh = _profile_mesh(contact_x, back_x, length, float(genes["contact_width_mm"]))
    feature_count = int(wrap_depth > 0.0) + int(toe_lip > 0.0)
    return ActiveBody(
        mesh=mesh,
        genes=genes,
        contact_feature_count=feature_count,
        opening_loss_mm=toe_lip,
        note="原创宽面弧槽构型：连续实心薄身与圆钝止挡共用固定三孔根部。",
    )


def _precision_tip_body(raw: dict[str, Any] | None) -> ActiveBody:
    genes = normalize_family_genes("precision-wedge-solid", raw)
    length = float(genes["finger_length_mm"])
    taper_start = float(genes["taper_start"])
    tip_depth = float(genes["tip_depth_mm"])
    tip_offset = float(genes["tip_offset_mm"])
    pad_length = float(genes["contact_pad_mm"])
    # 紧凑三孔布局下，楔身根部覆盖到双孔侧底座外沿附近，再向窄尖渐缩。
    root_depth = 31.5

    def taper_t(u: float) -> float:
        t = float(np.clip(u / length, 0.0, 1.0))
        return float(_smoothstep((t - taper_start) / max(1.0 - taper_start, 1e-6)))

    def center_shift(u: float) -> float:
        t = float(np.clip(u / length, 0.0, 1.0))
        return tip_offset * float(_smoothstep(t))

    def depth_at(u: float) -> float:
        # A constant-depth terminal segment creates the local rectangular pad
        # while the preceding shoulder remains visibly wedge-shaped.
        pad_start = max(0.0, length - pad_length)
        if u >= pad_start:
            return tip_depth
        return root_depth + (tip_depth - root_depth) * taper_t(u)

    def contact_x(u: float) -> float:
        return center_shift(u)

    def back_x(u: float) -> float:
        return center_shift(u) + depth_at(u)

    mesh = _profile_mesh(contact_x, back_x, length, float(genes["tip_width_mm"]))
    return ActiveBody(
        mesh=mesh,
        genes=genes,
        contact_feature_count=1,
        opening_loss_mm=max(0.0, -tip_offset),
        note="原创紧凑精密构型：前宽后窄楔身连接局部平直窄尖。",
    )


FAMILY_BUILDERS: dict[str, Callable[[dict[str, Any] | None], ActiveBody]] = {
    "arc-wrap-solid": _arc_wrap_body,
    "precision-wedge-solid": _precision_tip_body,
}


def build_active_body(generator: str, raw: dict[str, Any] | None) -> ActiveBody:
    try:
        builder = FAMILY_BUILDERS[generator]
    except KeyError as exc:
        raise ValueError(f"未知的程序构型生成器：{generator}") from exc
    return builder(raw)
