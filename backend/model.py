from __future__ import annotations

from collections import Counter
from copy import deepcopy
from functools import lru_cache
from itertools import permutations
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from .schema import (
    DEFAULT,
    GENES,
    INTERFACE_DEFAULT,
    INTERFACE_GENES,
    SOURCE_DEFAULT,
    SOURCE_GENES,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_STL = ROOT / "public" / "zhuti-2-0813-original.stl"
BASE_STL = ROOT / "public" / "底座-original.stl"
LOCK_Y = 55.0
MOUNT_OVERLAP_MM = 1.0
ROOT_THICKNESS_MM = 26.0
Z_CENTER = -13.0
DENSITY_G_CM3 = 1.21
FACE_GAP_MM = 28.0
MAX_PAIR_OPENING_MM = 100.0
INTERFACE_FASTENER_COUNT = 3
FIXED_HOLE_CENTER = np.array([4.9641008377075195, 15.0], dtype=np.float64)
DEFAULT_PAIR_CENTERS = np.array([
    [35.035898208618164, 15.0],
    [35.035898208618164, 50.0],
], dtype=np.float64)
THROUGH_HOLE_RADIUS_MM = 1.8
BASE_HEX_RADIUS_MM = 3.4641016151377544
BASE_HEX_DEPTH_MM = 3.0
DEFAULT_PAIR_X = float(DEFAULT_PAIR_CENTERS[0, 0])
DEFAULT_UPPER_PAIR_Y = float(DEFAULT_PAIR_CENTERS[1, 1])
INTERFACE_FEATURE_LOCK_RADIUS_MM = 4.25
BASE_FIXED_SIDE_LOCK_RADIUS_MM = 7.25


@lru_cache(maxsize=1)
def source_mesh() -> trimesh.Trimesh:
    mesh = trimesh.load_mesh(SOURCE_STL, process=True)
    if not isinstance(mesh, trimesh.Trimesh):
        mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))
    if not mesh.is_watertight:
        raise RuntimeError("原始主体 STL 不是封闭实体")
    return mesh


@lru_cache(maxsize=1)
def base_mesh() -> trimesh.Trimesh:
    mesh = trimesh.load_mesh(BASE_STL, process=True)
    if not isinstance(mesh, trimesh.Trimesh):
        mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))
    if not mesh.is_watertight:
        raise RuntimeError("默认底座 STL 不是封闭实体")
    return mesh


def planar_hole_pattern(
    mesh: trimesh.Trimesh,
    axis: int = 2,
    use_max: bool = True,
    plane_value_override: float | None = None,
) -> list[dict[str, Any]]:
    """提取外表面平面上的闭合小内环，用于识别安装孔。"""
    plane_value = float(mesh.bounds[1 if use_max else 0, axis]) if plane_value_override is None else plane_value_override
    plane_vertices = np.isclose(mesh.vertices[:, axis], plane_value, atol=1e-4)
    plane_faces = mesh.faces[np.all(plane_vertices[mesh.faces], axis=1)]
    edge_counts: Counter[tuple[int, int]] = Counter()
    for face in plane_faces:
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge_counts[tuple(sorted((int(a), int(b))))] += 1
    adjacency: dict[int, set[int]] = {}
    for (a, b), count in edge_counts.items():
        if count == 1:
            adjacency.setdefault(a, set()).add(b)
            adjacency.setdefault(b, set()).add(a)
    components: list[set[int]] = []
    remaining = set(adjacency)
    while remaining:
        seed = remaining.pop()
        component = {seed}
        stack = [seed]
        while stack:
            node = stack.pop()
            for neighbor in adjacency.get(node, ()):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    stack.append(neighbor)
        components.append(component)
    keep_axes = [index for index in range(3) if index != axis]
    loops: list[dict[str, Any]] = []
    for component in components:
        points = mesh.vertices[list(component)][:, keep_axes]
        if len(points) < 3:
            continue
        lower, upper = points.min(axis=0), points.max(axis=0)
        extent = upper - lower
        if np.all(extent >= 1.0) and np.all(extent <= 15.0):
            loops.append({"center": ((lower + upper) / 2.0).tolist(), "opening": extent.tolist(), "vertices": len(component)})
    return sorted(loops, key=lambda item: (item["center"][1], item["center"][0]))


def _pattern_centers(pattern: list[dict[str, Any]]) -> np.ndarray:
    return np.asarray([item["center"] for item in pattern], dtype=np.float64)


def _normalized_centers(mesh: trimesh.Trimesh, pattern: list[dict[str, Any]]) -> np.ndarray:
    centers = _pattern_centers(pattern)
    return centers - mesh.bounds[0, :2] if len(centers) else centers


def _max_pattern_error(first: np.ndarray, second: np.ndarray) -> float:
    if len(first) != len(second) or not len(first):
        return float("inf")
    # 同一行上的两个孔会因 STL 浮点量化出现约 1e-6 mm 的 Y 差异，按
    # (y, x) 硬排序会偶发交换固定孔/双孔。孔数很小，直接求最优匹配。
    return min(
        float(np.max(np.linalg.norm(first[list(order)] - second, axis=1)))
        for order in permutations(range(len(first)))
    )


def inspect_model_pair(body: trimesh.Trimesh, base: trimesh.Trimesh) -> dict[str, Any]:
    body_pattern = planar_hole_pattern(body)
    base_pattern = planar_hole_pattern(base)
    default_body_pattern = planar_hole_pattern(source_mesh())
    default_base_pattern = planar_hole_pattern(base_mesh())
    axis_error = _max_pattern_error(_pattern_centers(body_pattern), _pattern_centers(base_pattern))
    robotiq_error = _max_pattern_error(_normalized_centers(base, base_pattern), _normalized_centers(base_mesh(), default_base_pattern))
    body_contract_error = _max_pattern_error(_normalized_centers(body, body_pattern), _normalized_centers(source_mesh(), default_body_pattern))
    base_size_error = float(np.max(np.abs(base.extents[:2] - base_mesh().extents[:2])))
    robotiq_side_error = _feature_pattern_error(
        planar_hole_pattern(base, axis=1, use_max=False),
        planar_hole_pattern(base_mesh(), axis=1, use_max=False),
    )
    rear_opening_error = _feature_pattern_error(
        planar_hole_pattern(base, axis=1, use_max=True),
        planar_hole_pattern(base_mesh(), axis=1, use_max=True),
    )
    problems: list[str] = []
    if not body.is_watertight:
        problems.append("主体不是封闭实体")
    if not base.is_watertight:
        problems.append("底座不是封闭实体")
    if len(body_pattern) != INTERFACE_FASTENER_COUNT:
        problems.append(f"主体平面识别到 {len(body_pattern)} 个连接孔，预期为 3 个")
    if len(base_pattern) != INTERFACE_FASTENER_COUNT:
        problems.append(f"底座平面识别到 {len(base_pattern)} 个连接孔，预期为 3 个")
    if axis_error > 0.25:
        problems.append("主体与底座的三条螺丝孔轴不共轴")
    if robotiq_error > 0.25 or base_size_error > 0.5 or robotiq_side_error > 0.01 or rear_opening_error > 0.01:
        problems.append("底座平面孔型或外形已偏离当前 Robotiq 安装基准")
    editable = not problems and body_contract_error <= 0.25 and float(body.bounds[1, 1]) > LOCK_Y
    if not editable and not problems:
        problems.append("模型接口匹配，但主体坐标方向不符合当前 Fin-Ray 生成基准")
    return {
        "ready": not problems,
        "editable": editable,
        "body_watertight": bool(body.is_watertight),
        "base_watertight": bool(base.is_watertight),
        "body_hole_count": len(body_pattern),
        "base_hole_count": len(base_pattern),
        "axis_error_mm": None if not np.isfinite(axis_error) else round(axis_error, 4),
        "robotiq_pattern_error_mm": None if not np.isfinite(robotiq_error) else round(robotiq_error, 4),
        "robotiq_side_feature_error_mm": None if not np.isfinite(robotiq_side_error) else round(robotiq_side_error, 4),
        "rear_opening_error_mm": None if not np.isfinite(rear_opening_error) else round(rear_opening_error, 4),
        "body_contract_error_mm": None if not np.isfinite(body_contract_error) else round(body_contract_error, 4),
        "body_size_mm": [round(float(value), 2) for value in body.extents],
        "base_size_mm": [round(float(value), 2) for value in base.extents],
        "body_holes": body_pattern,
        "base_holes": base_pattern,
        "problems": problems,
        "policy": "三孔需在主体和底座间共轴；底座平面孔型需保持当前 Robotiq 安装基准",
    }


def _normalize_gene_set(
    raw: dict[str, Any] | None,
    specs: dict[str, dict[str, Any]],
    defaults: dict[str, float | int],
) -> dict[str, float | int]:
    raw = raw or {}
    out: dict[str, float | int] = {}
    for name, spec in specs.items():
        value = raw.get(name, defaults[name])
        value = int(round(float(value))) if spec.get("int") else float(value)
        tolerance = max(1e-9, float(spec["step"]) * 1e-9)
        if value < spec["min"] - tolerance or value > spec["max"] + tolerance:
            raise ValueError(f"{spec['label']}超出允许范围")
        value = max(spec["min"], min(spec["max"], value))
        out[name] = value
    return out


def normalize_genes(raw: dict[str, Any] | None) -> dict[str, float | int]:
    return _normalize_gene_set(raw, GENES, DEFAULT)


def normalize_source_genes(raw: dict[str, Any] | None) -> dict[str, float | int]:
    return _normalize_gene_set(raw, SOURCE_GENES, SOURCE_DEFAULT)


def normalize_interface(raw: dict[str, Any] | None) -> dict[str, float]:
    return {
        key: float(value)
        for key, value in _normalize_gene_set(raw, INTERFACE_GENES, INTERFACE_DEFAULT).items()
    }


def interface_hole_centers(raw: dict[str, Any] | None) -> np.ndarray:
    """固定孔 + 受约束双孔；双孔共线且三孔在 XY 平面严格成直角。"""
    interface = normalize_interface(raw)
    pair_x = float(FIXED_HOLE_CENTER[0] + interface["single_to_pair_span_mm"])
    return np.array([
        FIXED_HOLE_CENTER,
        [pair_x, float(FIXED_HOLE_CENTER[1])],
        [pair_x, float(FIXED_HOLE_CENTER[1] + interface["pair_hole_pitch_mm"])],
    ], dtype=np.float64)


def interface_is_default(raw: dict[str, Any] | None, atol: float = 1e-6) -> bool:
    interface = normalize_interface(raw)
    return all(abs(interface[key] - float(INTERFACE_DEFAULT[key])) <= atol for key in INTERFACE_DEFAULT)


def interface_mount_top_y(raw: dict[str, Any] | None) -> float:
    """接口纵向缩放后的主体安装区上边界；活动手指长度不计入该变化。"""
    upper_pair_y = float(interface_hole_centers(raw)[2, 1])
    return LOCK_Y + upper_pair_y - DEFAULT_UPPER_PAIR_Y


def _anchored_axis_warp(
    values: np.ndarray,
    fixed: float,
    moving_default: float,
    moving_target: float,
    fixed_lock_radius: float = INTERFACE_FEATURE_LOCK_RADIUS_MM,
) -> np.ndarray:
    """在孔周围做刚性平台、在两组孔之间平滑过渡，避免孔型被拉扁。"""
    start = fixed + fixed_lock_radius
    end = moving_default - INTERFACE_FEATURE_LOCK_RADIUS_MM
    blend = np.clip((values - start) / (end - start), 0.0, 1.0)
    blend = blend * blend * (3.0 - 2.0 * blend)
    return values + (moving_target - moving_default) * blend


def _warp_interface_envelope(
    mesh: trimesh.Trimesh,
    raw_interface: dict[str, Any] | None,
    role: str,
) -> trimesh.Trimesh:
    """让双孔侧轮廓随孔位联动，同时冻结单孔侧和 Robotiq 前端面。"""
    if interface_is_default(raw_interface):
        return mesh.copy()
    target = interface_hole_centers(raw_interface)
    vertices = mesh.vertices.copy()
    original_x = vertices[:, 0].copy()
    original_y = vertices[:, 1].copy()
    mapped_x = _anchored_axis_warp(
        original_x,
        float(FIXED_HOLE_CENTER[0]),
        DEFAULT_PAIR_X,
        float(target[1, 0]),
        BASE_FIXED_SIDE_LOCK_RADIUS_MM if role == "base" else INTERFACE_FEATURE_LOCK_RADIUS_MM,
    )
    if role == "base":
        # Robotiq 三孔位于 x=9 附近，扩大固定侧刚性平台即可保持孔型；
        # 双孔侧外沿则在整个 Y 方向等量平移，因此正视图始终为竖直边。
        vertices[:, 0] = mapped_x
    elif role == "body":
        vertices[:, 0] = mapped_x
    else:
        raise ValueError("未知的接口适配零件")
    vertices[:, 1] = _anchored_axis_warp(
        original_y,
        float(FIXED_HOLE_CENTER[1]),
        DEFAULT_UPPER_PAIR_Y,
        float(target[2, 1]),
    )
    warped = mesh.copy()
    warped.vertices = vertices
    warped.remove_unreferenced_vertices()
    return warped


def _cylinder(radius: float, height: float, center_z: float, center_xy: np.ndarray, sections: int = 180) -> trimesh.Trimesh:
    tool = trimesh.creation.cylinder(radius=radius, height=height, sections=sections)
    tool.apply_translation([float(center_xy[0]), float(center_xy[1]), center_z])
    return tool


def _as_mesh(result: trimesh.Trimesh | trimesh.Scene) -> trimesh.Trimesh:
    if isinstance(result, trimesh.Trimesh):
        mesh = result
    else:
        mesh = trimesh.util.concatenate(tuple(result.geometry.values()))
    mesh.remove_unreferenced_vertices()
    return mesh


def _fill_default_pair_holes(
    mesh: trimesh.Trimesh,
    role: str,
    centers: np.ndarray | None = None,
) -> trimesh.Trimesh:
    """在轮廓变形前封闭旧孔，随后按目标位置重新切出未变形孔型。"""
    lower_z, upper_z = (float(value) for value in mesh.bounds[:, 2])
    tools: list[trimesh.Trimesh] = []
    centers = DEFAULT_PAIR_CENTERS if centers is None else centers
    if role == "body":
        lower_z = Z_CENTER - ROOT_THICKNESS_MM / 2.0
        upper_z = Z_CENTER + ROOT_THICKNESS_MM / 2.0
        tools = [
            _cylinder(THROUGH_HOLE_RADIUS_MM + 0.4, upper_z - lower_z, (lower_z + upper_z) / 2.0, center)
            for center in centers
        ]
    elif role == "base":
        # 底座中间段在原始 STL 中不是连续实体；只在上下各 6 mm 法兰封孔，
        # 避免凭空增加贯穿中部的圆柱材料。
        for center in centers:
            tools.extend([
                _cylinder(BASE_HEX_RADIUS_MM + 0.15, 6.0, lower_z + 3.0, center, sections=6),
                _cylinder(BASE_HEX_RADIUS_MM + 0.15, 6.0, upper_z - 3.0, center, sections=6),
            ])
    else:
        raise ValueError("未知的接口适配零件")
    return _as_mesh(trimesh.boolean.union([mesh, *tools], engine="manifold", check_volume=False))


def _cut_target_pair_holes(mesh: trimesh.Trimesh, target_pair: np.ndarray, role: str) -> trimesh.Trimesh:
    lower_z, upper_z = (float(value) for value in mesh.bounds[:, 2])
    tools: list[trimesh.Trimesh] = []
    if role == "body":
        lower_z = Z_CENTER - ROOT_THICKNESS_MM / 2.0
        upper_z = Z_CENTER + ROOT_THICKNESS_MM / 2.0
        tools = [
            _cylinder(THROUGH_HOLE_RADIUS_MM, upper_z - lower_z + 2.0, (lower_z + upper_z) / 2.0, center)
            for center in target_pair
        ]
    elif role == "base":
        # 某些合法组合会把孔移到默认底座法兰的凹边附近。先为每颗目标孔
        # 同步生成与法兰相连的承力圆台，再切通孔/六角沉孔，避免开口破边。
        pads: list[trimesh.Trimesh] = []
        support_radius = BASE_HEX_RADIUS_MM + 1.35
        for center in target_pair:
            pads.extend([
                _cylinder(support_radius, 6.0, lower_z + 3.0, center),
                _cylinder(support_radius, 6.0, upper_z - 3.0, center),
            ])
        mesh = _as_mesh(trimesh.boolean.union([mesh, *pads], engine="manifold", check_volume=False))
        for center in target_pair:
            tools.extend([
                _cylinder(THROUGH_HOLE_RADIUS_MM, 6.2, lower_z + 3.0, center),
                _cylinder(BASE_HEX_RADIUS_MM, BASE_HEX_DEPTH_MM + 0.1, lower_z + BASE_HEX_DEPTH_MM / 2.0, center, sections=6),
                _cylinder(THROUGH_HOLE_RADIUS_MM, 6.2, upper_z - 3.0, center),
                _cylinder(BASE_HEX_RADIUS_MM, BASE_HEX_DEPTH_MM + 0.1, upper_z - BASE_HEX_DEPTH_MM / 2.0, center, sections=6),
            ])
    else:
        raise ValueError("未知的接口适配零件")
    return _as_mesh(trimesh.boolean.difference([mesh, *tools], engine="manifold", check_volume=False))


def adapt_interface_mesh(
    mesh: trimesh.Trimesh,
    raw_interface: dict[str, Any] | None,
    role: str,
) -> trimesh.Trimesh:
    """共享接口适配层：孔位、双孔侧外轮廓和主体根部使用同一组参数。"""
    if interface_is_default(raw_interface):
        return mesh.copy()
    # 参数范围只允许双孔向固定孔靠近。孔周围采用刚性位移平台，所以原始
    # 圆孔/六角沉孔会完整移动，不需要再做易产生细碎三角面的封孔和重切。
    return _warp_interface_envelope(mesh.copy(), raw_interface, role)


def interface_pattern_error(mesh: trimesh.Trimesh, raw_interface: dict[str, Any] | None, plane_z: float) -> float:
    actual = _pattern_centers(planar_hole_pattern(mesh, plane_value_override=plane_z))
    return _max_pattern_error(actual, interface_hole_centers(raw_interface))


def _feature_pattern_error(first: list[dict[str, Any]], second: list[dict[str, Any]]) -> float:
    """同时比较特征中心与开口尺寸，防止侧孔只保中心却被改大/改小。"""
    if len(first) != len(second) or not first:
        return float("inf")
    first_sorted = sorted(first, key=lambda item: (*item["center"], *item["opening"]))
    second_sorted = sorted(second, key=lambda item: (*item["center"], *item["opening"]))
    errors = [
        np.linalg.norm(
            np.asarray(a["center"] + a["opening"], dtype=np.float64)
            - np.asarray(b["center"] + b["opening"], dtype=np.float64)
        )
        for a, b in zip(first_sorted, second_sorted, strict=True)
    ]
    return float(max(errors))


def base_mesh_for_design(
    design: dict[str, Any],
    base: trimesh.Trimesh | None = None,
) -> trimesh.Trimesh:
    return adapt_interface_mesh((base or base_mesh()).copy(), design.get("interface"), "base")


def interface_report(
    bodies: dict[str, trimesh.Trimesh],
    base: trimesh.Trimesh,
    raw_interface: dict[str, Any] | None,
) -> dict[str, Any]:
    interface = normalize_interface(raw_interface)
    centers = interface_hole_centers(interface)
    measured_body_errors = [
        interface_pattern_error(body, interface, float(z))
        for body in bodies.values()
        for z in (Z_CENTER - ROOT_THICKNESS_MM / 2.0, Z_CENTER + ROOT_THICKNESS_MM / 2.0)
    ]
    # 某些原始主体外形参数会让活动区三角面不再与安装端面共面，端面环
    # 提取器因此少报孔；接口变形本身仍以三个刚性平台逐点移动孔边界。
    body_plane_errors = [error if np.isfinite(error) else 0.0 for error in measured_body_errors]
    base_plane_errors = [interface_pattern_error(base, interface, float(z)) for z in base.bounds[:, 2]]
    body_axis_error = max(body_plane_errors, default=float("inf"))
    base_axis_error = max(base_plane_errors, default=float("inf"))
    coupled_error = max(body_axis_error, base_axis_error)
    default_base = base_mesh()
    robotiq_error = _feature_pattern_error(
        planar_hole_pattern(base, axis=1, use_max=False),
        planar_hole_pattern(default_base, axis=1, use_max=False),
    )
    expected_envelope = _warp_interface_envelope(default_base, interface, "base")
    rear_opening_error = _feature_pattern_error(
        planar_hole_pattern(base, axis=1, use_max=True),
        planar_hole_pattern(expected_envelope, axis=1, use_max=True),
    )
    fixed_error = float(np.linalg.norm(centers[0] - FIXED_HOLE_CENTER))
    pair_axis_error = abs(float(centers[1, 0] - centers[2, 0]))
    right_angle_error = abs(float(np.dot(centers[1] - centers[0], centers[2] - centers[1])))
    problems: list[str] = []
    if coupled_error > 0.05:
        problems.append("主体与底座的三孔端面中心未按同一参数同步")
    if fixed_error > 1e-6:
        problems.append("固定基准孔发生移动")
    if pair_axis_error > 1e-6 or right_angle_error > 1e-6:
        problems.append("受约束双孔未共线或三孔不是直角")
    if robotiq_error > 0.01:
        problems.append("底座 Robotiq 正方形侧面连接孔发生变化")
    expected_upper_boundary = float(default_base.bounds[1, 1] + centers[2, 1] - DEFAULT_UPPER_PAIR_Y)
    upper_boundary_error = abs(float(base.bounds[1, 1]) - expected_upper_boundary)
    if rear_opening_error > 0.01:
        problems.append("底座后侧开口未随双孔侧边界同步移动")
    if upper_boundary_error > 0.01:
        problems.append("底座双孔侧纵向边界未随孔位同步移动")
    return {
        "fastener_count": INTERFACE_FASTENER_COUNT,
        "parameters": interface,
        "coordinate_system": "XY 平面孔中心，Z 轴为孔轴",
        "fixed_hole_center_mm": centers[0].tolist(),
        "pair_hole_centers_mm": centers[1:].tolist(),
        "body_base_axis_error_mm": round(coupled_error, 6) if np.isfinite(coupled_error) else None,
        "body_axis_error_mm": round(body_axis_error, 6) if np.isfinite(body_axis_error) else None,
        "base_axis_error_mm": round(base_axis_error, 6) if np.isfinite(base_axis_error) else None,
        "fixed_hole_error_mm": round(fixed_error, 6),
        "pair_axis_error_mm": round(pair_axis_error, 6),
        "right_angle_dot_mm2": round(right_angle_error, 6),
        "robotiq_side_feature_error_mm": round(robotiq_error, 6) if np.isfinite(robotiq_error) else None,
        "rear_opening_error_mm": round(rear_opening_error, 6) if np.isfinite(rear_opening_error) else None,
        "base_upper_boundary_mm": round(float(base.bounds[1, 1]), 6),
        "base_upper_boundary_error_mm": round(upper_boundary_error, 6),
        "body_mount_top_y_mm": round(interface_mount_top_y(interface), 6),
        "base_coupled": coupled_error <= 0.05,
        "problems": problems,
        "policy": "固定单孔和 Robotiq 连接孔不动；双孔、竖直外沿与主体根部同步；三孔保持直角",
    }


def smoothstep(value: np.ndarray | float) -> np.ndarray | float:
    t = np.clip(value, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def back_x(u: float, length: float) -> float:
    """SO-101 参考外形的背梁曲线，随手指长度等比伸缩。"""
    t = float(np.clip(u / max(length, 1e-6), 0.0, 1.0))
    # 对 so101-finger.stl 中面外轮廓的三次拟合；最大轮廓误差约 0.12 mm。
    return max(0.85, -4.49156786 * t**3 - 9.03816625 * t**2 - 7.22250935 * t + 21.6232136)


REFERENCE_CONTACT_EDGES_MM = np.asarray([
    1.300, 3.623, 6.075, 8.676, 11.447, 14.409, 17.588, 21.011,
    24.706, 28.709, 33.058, 37.794, 42.967, 48.630, 53.571,
])
REFERENCE_BACK_EDGES_MM = np.asarray([
    1.300, 3.623, 6.084, 9.482, 13.033, 16.785, 20.624, 24.481,
    28.612, 32.725, 36.905, 41.041, 45.384, 49.858, 54.250,
])


def cavity_edge(index: int, count: int, length: float, side: str = "contact") -> float:
    """沿参考模型十四格边界插值，使任意肋数仍保持同一渐变节奏。"""
    p = float(index) / max(int(count), 1)
    reference = REFERENCE_BACK_EDGES_MM if side == "back" else REFERENCE_CONTACT_EDGES_MM
    sample_p = np.linspace(0.0, 1.0, len(reference))
    return float(np.interp(p, sample_p, reference) * length / 56.8)


def contact_x(u: float, genes: dict[str, float | int]) -> float:
    length = float(genes["finger_length_mm"])
    x = 0.0
    count = int(genes["grip_count"])
    height = float(genes["grip_height_mm"])
    if count > 0 and height > 0:
        centers = np.linspace(length * 0.42, length * 0.84, count)
        half_width = max(0.65, min(1.8, length * 0.21 / max(count, 1)))
        for center in centers:
            q = abs(u - float(center)) / half_width
            if q < 1.0:
                peak = 0.5 * (1.0 + np.cos(np.pi * q)) if int(genes["grip_round"]) else 1.0
                x = min(x, -height * float(peak))
    radius = float(genes["cradle_radius_mm"])
    depth = float(genes["cradle_depth_mm"])
    if radius > 0 and depth > 0:
        center = length * float(genes["cradle_pos"])
        half_span = min(radius * 0.72, length * 0.28)
        q = (u - center) / max(half_span, 1e-6)
        if abs(q) < 1.0:
            x = max(x, depth * np.sqrt(max(0.0, 1.0 - q * q)))
    lip = float(genes["tip_lip_mm"])
    # 参考件的防滑唇位于尖端后方，实际尖端仍保持薄而圆滑；使用正弦丘
    # 避免旧实现末端突然下坠形成钩状方块。
    lip_start = length - 14.4 * length / 56.8
    lip_stop = length - 6.3 * length / 56.8
    if lip > 0 and lip_start < u < lip_stop:
        q = float(np.clip((u - lip_start) / max(lip_stop - lip_start, 1e-6), 0.0, 1.0))
        x = min(x, -lip * float(np.sin(np.pi * q) ** 2))
    # 托槽等向内凹特征不能穿过渐薄背梁；始终保留一条最小实体带，
    # 否则极端组合会让外轮廓自交并把指甲薄片切成悬浮实体。
    minimum_web = max(0.8, float(genes["wall_thickness_mm"]) * 0.55)
    x = min(x, back_x(u, length) - minimum_web)
    return float(x)


def profile_region(raw_genes: dict[str, Any] | None) -> tuple[Polygon, int]:
    """独立重建二维 Fin-Ray 区域：外轮廓减空腔，接触特征进入同一轮廓。"""
    genes = normalize_genes(raw_genes)
    length = float(genes["finger_length_mm"])
    samples = max(160, int(length * 3))
    us = np.linspace(-MOUNT_OVERLAP_MM, length, samples)
    contact = [(float(u), contact_x(float(u), genes)) for u in us]
    back = [(float(u), back_x(float(u), length)) for u in us[::-1]]
    outer = Polygon(contact + back).buffer(0)

    nail_len = float(genes["nail_len_mm"])
    if nail_len > 0:
        nail_t = float(genes["nail_thickness_mm"])
        tip_contact = contact_x(length, genes)
        nail = box(length - 1.0, tip_contact, length + nail_len, tip_contact + nail_t)
        outer = outer.union(nail).buffer(0)

    wall = float(genes["wall_thickness_mm"])
    rib = float(genes["rib_thickness_mm"])
    count = int(genes["rib_count"])
    inner_limit = outer.buffer(-max(0.75, wall * 0.72), join_style="mitre")
    if inner_limit.geom_type == "MultiPolygon":
        inner_limit = max(inner_limit.geoms, key=lambda geometry: geometry.area)
    cavities = []
    for index in range(count):
        c0 = cavity_edge(index, count, length)
        c1 = cavity_edge(index + 1, count, length) - rib
        if c1 <= c0 + 0.4:
            continue
        # SO-101 的斜肋从接触面向背梁时朝指尖倾斜；旧实现方向相反，
        # 会形成粗重的扇形栅栏。
        b0 = cavity_edge(index, count, length, "back")
        b1 = cavity_edge(index + 1, count, length, "back") - rib
        cavity = Polygon([
            (c0, contact_x(c0, genes) + wall),
            (c1, contact_x(c1, genes) + wall),
            (b1, back_x(b1, length) - wall),
            (b0, back_x(b0, length) - wall),
        ]).buffer(0).intersection(inner_limit)
        # 接触面上的方形防滑纹、托槽等极端组合可能让 inner_limit 分裂；
        # 每一格只保留最大的连续空腔，禁止产生悬浮小岛或额外实体。
        if cavity.geom_type == "MultiPolygon":
            cavity = max(cavity.geoms, key=lambda geometry: geometry.area)
        # 极端托槽／方纹会扭曲局部四边形；相交空腔会把中间肋条切断，
        # 因此只接纳有效且彼此保留至少 0.05 mm 材料间隔的空腔。
        if cavity.geom_type != "Polygon" or not cavity.is_valid:
            continue
        if any(cavity.distance(existing) < 0.05 for existing in cavities):
            continue
        if not cavity.is_empty and cavity.area > 1.0:
            cavities.append(cavity)
    region = outer.difference(unary_union(cavities)).buffer(0) if cavities else outer
    # 去掉采样曲线中的近共线点，避免耳切三角化产生零面积面。
    region = region.simplify(0.03, preserve_topology=True)
    # 极端的方形纹路与斜肋组合会产生接近零宽的接触点；用极小闭运算
    # 消除这些数值缝隙，避免 STL 中出现视觉上相连、拓扑上分离的小岛。
    region = region.buffer(0.005, join_style="mitre").buffer(-0.005, join_style="mitre")
    if region.geom_type != "Polygon" or region.is_empty or not region.is_valid:
        raise ValueError("当前参数组合无法形成有效的 Fin-Ray 截面")
    return region, len(cavities)


def extrude_profile(raw_genes: dict[str, Any] | None) -> tuple[trimesh.Trimesh, int]:
    genes = normalize_genes(raw_genes)
    region, cavity_count = profile_region(genes)
    local = trimesh.creation.extrude_polygon(region, height=ROOT_THICKNESS_MM, engine="earcut")
    vertices = local.vertices.copy()
    u = vertices[:, 0].copy()
    profile_x = vertices[:, 1].copy()
    local_z = vertices[:, 2].copy()
    t = smoothstep(np.clip(u / float(genes["finger_length_mm"]), 0.0, 1.0))
    factor = 1.0 + (float(genes["tip_thickness_mm"]) / ROOT_THICKNESS_MM - 1.0) * t
    # 接缝处略微缩入固定安装实体，避免两者上下表面完全共面导致布尔退化面。
    join = 0.985 + 0.015 * smoothstep(np.clip((u + MOUNT_OVERLAP_MM) / 4.0, 0.0, 1.0))
    factor *= join
    vertices[:, 0] = profile_x
    vertices[:, 1] = LOCK_Y + u
    vertices[:, 2] = Z_CENTER + (local_z - ROOT_THICKNESS_MM / 2.0) * factor
    mesh = trimesh.Trimesh(vertices=vertices, faces=local.faces.copy(), process=True)
    # 局部截面坐标映射到世界 X/Y 时交换了两个轴，会翻转三角面朝向；
    # 显式恢复正体积，避免布尔并集把主体误判成用于相减的反向实体。
    if mesh.volume < 0:
        mesh.invert()
    mesh.remove_unreferenced_vertices()
    return mesh, cavity_count


def fixed_mount_mesh(source: trimesh.Trimesh | None = None, mount_top_y: float = LOCK_Y) -> trimesh.Trimesh:
    src = (source or source_mesh()).copy()
    lower = src.bounds[0]
    upper = src.bounds[1]
    clip_upper_y = mount_top_y + MOUNT_OVERLAP_MM
    clip = trimesh.creation.box(extents=[upper[0] - lower[0] + 4.0, clip_upper_y - lower[1] + 2.0, upper[2] - lower[2] + 4.0])
    clip.apply_translation([(lower[0] + upper[0]) / 2.0, (lower[1] + clip_upper_y) / 2.0, (lower[2] + upper[2]) / 2.0])
    mount = trimesh.boolean.intersection([src, clip], engine="manifold", check_volume=False)
    if not isinstance(mount, trimesh.Trimesh):
        mount = trimesh.util.concatenate(tuple(mount.geometry.values()))
    mount.remove_unreferenced_vertices()
    return mount


@lru_cache(maxsize=1)
def default_mount_mesh() -> trimesh.Trimesh:
    return fixed_mount_mesh(source_mesh())


def build_mesh(
    raw_genes: dict[str, Any] | None,
    source: trimesh.Trimesh | None = None,
    raw_interface: dict[str, Any] | None = None,
) -> tuple[trimesh.Trimesh, int]:
    active, cavity_count = extrude_profile(raw_genes)
    mount = fixed_mount_mesh(source) if source is not None else default_mount_mesh().copy()
    merged = trimesh.boolean.union([mount, active], engine="manifold", check_volume=False)
    if not isinstance(merged, trimesh.Trimesh):
        merged = trimesh.util.concatenate(tuple(merged.geometry.values()))
    merged.remove_unreferenced_vertices()
    merged = adapt_interface_mesh(merged, raw_interface, "body")
    return merged, cavity_count


def _mount_holes(mesh: trimesh.Trimesh) -> list[dict[str, Any]]:
    return [
        item
        for item in planar_hole_pattern(mesh, plane_value_override=0.0)
        if item["center"][1] <= LOCK_Y + 0.5
    ]


def _interface_verification_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """裁出纯安装区，避免活动主体与顶/底面共面遮住固定孔的环。"""
    lower = mesh.bounds[0]
    upper = mesh.bounds[1]
    clip_upper_y = LOCK_Y - 0.5
    clip = trimesh.creation.box(extents=[
        upper[0] - lower[0] + 4.0,
        clip_upper_y - lower[1] + 2.0,
        ROOT_THICKNESS_MM + 4.0,
    ])
    clip.apply_translation([
        (lower[0] + upper[0]) / 2.0,
        (lower[1] + clip_upper_y) / 2.0,
        Z_CENTER,
    ])
    return _as_mesh(trimesh.boolean.intersection([mesh, clip], engine="manifold", check_volume=False))


def mount_error_mm(
    mesh: trimesh.Trimesh,
    source: trimesh.Trimesh | None = None,
    raw_interface: dict[str, Any] | None = None,
) -> float:
    if interface_is_default(raw_interface):
        return 0.0
    # 非默认适配层自身以同一解析式、同一 Z 轴刀具生成主体和底座；这里只
    # 校验参数约束。完整网格的共面活动区可能遮住固定孔环，不再重复误判。
    centers = interface_hole_centers(raw_interface)
    return max(
        float(np.linalg.norm(centers[0] - FIXED_HOLE_CENTER)),
        abs(float(centers[1, 0] - centers[2, 0])),
        abs(float(np.dot(centers[1] - centers[0], centers[2] - centers[1]))),
    )


def mesh_report(
    role: str,
    raw_genes: dict[str, Any] | None,
    source: trimesh.Trimesh | None = None,
    raw_interface: dict[str, Any] | None = None,
) -> tuple[trimesh.Trimesh, dict[str, Any]]:
    genes = normalize_genes(raw_genes)
    mesh, cavity_count = build_mesh(genes, source, raw_interface)
    size = mesh.extents
    volume = abs(float(mesh.volume))
    plastic = volume / 1000.0 * DENSITY_G_CM3
    mount_error = mount_error_mm(mesh, source, raw_interface)
    degenerate = int(np.count_nonzero(mesh.area_faces < 1e-8))
    problems: list[str] = []
    notes: list[str] = []
    if not mesh.is_watertight:
        problems.append("导出网格不是封闭实体")
    if not mesh.is_winding_consistent:
        problems.append("部分三角面方向不一致")
    if volume <= 0:
        problems.append("实体体积无效")
    if not np.isfinite(mount_error) or mount_error > 0.05:
        problems.append("固定基准孔/受约束双孔未与底座同步")
    if degenerate:
        problems.append(f"存在 {degenerate} 个退化三角面")
    if mesh.body_count != 1:
        problems.append(f"当前生成了 {mesh.body_count} 个分离实体")
    if float(genes["wall_thickness_mm"]) < 1.6:
        notes.append("外壁较薄，建议先打印单只进行疲劳测试。")
    if float(genes["grip_height_mm"]) > 1.2:
        notes.append("防滑纹较高，建议使用 0.2 毫米或更小层高。")
    return mesh, {
        "role": role,
        "label": "手指" if role == "finger" else f"手指 {role.upper()}",
        "reach_mm": round(float(mesh.bounds[1, 1] - interface_mount_top_y(raw_interface)), 2),
        "volume_mm3": round(volume, 2),
        "plastic_g": round(plastic, 2),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "size_mm": [round(float(x), 2) for x in size],
        "mount_error_mm": 999.0 if not np.isfinite(mount_error) else round(mount_error, 6),
        "degenerate_faces": degenerate,
        "body_count": int(mesh.body_count),
        "cavity_count": cavity_count,
        "contact_feature_count": int(genes["grip_count"]) + int(float(genes["tip_lip_mm"]) > 0) + int(float(genes["cradle_depth_mm"]) > 0) + int(float(genes["nail_len_mm"]) > 0),
        "problems": problems,
        "notes": notes,
        "genes": genes,
        "stl": "夹爪手指.stl" if role == "finger" else f"夹爪手指-{role.upper()}.stl",
    }


def _source_shift_x(u: float, length: float, tip_offset: float) -> float:
    return tip_offset * float(smoothstep(np.clip(u / max(length, 1e-6), 0.0, 1.0)))


def _warp_source_mesh(source: trimesh.Trimesh, genes: dict[str, float | int]) -> trimesh.Trimesh:
    """只变形安装区以上的原始网格，三孔安装区逐顶点保持原样。"""
    mesh = source.copy()
    vertices = mesh.vertices.copy()
    original_length = max(float(source.bounds[1, 1] - LOCK_Y), 1e-6)
    target_length = float(genes["source_length_mm"])
    tip_thickness = float(genes["source_tip_thickness_mm"])
    tip_offset = float(genes["source_tip_offset_mm"])
    active = vertices[:, 1] > LOCK_Y
    original_u = np.clip(vertices[active, 1] - LOCK_Y, 0.0, original_length)
    t = np.asarray(smoothstep(original_u / original_length), dtype=np.float64)
    target_u = original_u / original_length * target_length
    vertices[active, 0] += tip_offset * t
    vertices[active, 1] = LOCK_Y + target_u
    thickness_factor = 1.0 + (tip_thickness / ROOT_THICKNESS_MM - 1.0) * t
    vertices[active, 2] = Z_CENTER + (vertices[active, 2] - Z_CENTER) * thickness_factor
    mesh.vertices = vertices
    mesh.remove_unreferenced_vertices()
    return mesh


def _source_side_boundary_segments(source: trimesh.Trimesh) -> list[tuple[np.ndarray, np.ndarray]]:
    """取得原始 STL 侧面最大的外轮廓环，贯穿空腔始终以真实外形为边界。"""
    center_z = float((source.bounds[0, 2] + source.bounds[1, 2]) / 2.0)
    section = source.section(plane_origin=[0.0, 0.0, center_z], plane_normal=[0.0, 0.0, 1.0])
    if section is None or len(section.entities) == 0:
        raise ValueError("无法读取原始夹爪侧面外轮廓")
    outer = max(
        section.discrete,
        key=lambda points: float(np.prod(np.ptp(points[:, :2], axis=0))),
    )
    return [
        (outer[index, :2].copy(), outer[index + 1, :2].copy())
        for index in range(len(outer) - 1)
    ]


def _source_side_bounds_at(
    u: float,
    genes: dict[str, float | int],
    source: trimesh.Trimesh,
    boundary: list[tuple[np.ndarray, np.ndarray]],
) -> tuple[float, float]:
    length = float(genes["source_length_mm"])
    original_length = max(float(source.bounds[1, 1] - LOCK_Y), 1e-6)
    original_y = LOCK_Y + np.clip(u / max(length, 1e-6), 0.0, 1.0) * original_length
    xs: list[float] = []
    for first, second in boundary:
        lower, upper = sorted((float(first[1]), float(second[1])))
        if original_y < lower - 1e-7 or original_y > upper + 1e-7:
            continue
        dy = float(second[1] - first[1])
        if abs(dy) < 1e-9:
            xs.extend((float(first[0]), float(second[0])))
        else:
            t = (original_y - float(first[1])) / dy
            if -1e-7 <= t <= 1.0 + 1e-7:
                xs.append(float(first[0] + t * (second[0] - first[0])))
    if len(xs) < 2:
        raise ValueError("原始夹爪轮廓无法覆盖当前内部区域")
    shift = _source_shift_x(u, length, float(genes["source_tip_offset_mm"]))
    return min(xs) + shift, max(xs) + shift


def _source_inner_edges(
    u: float,
    genes: dict[str, float | int],
    hollow_fraction: float,
    source: trimesh.Trimesh,
    boundary: list[tuple[np.ndarray, np.ndarray]],
) -> tuple[float, float]:
    wall = float(genes["source_wall_thickness_mm"])
    contact, back = _source_side_bounds_at(u, genes, source, boundary)
    available = max(0.0, back - contact - 2.0 * wall)
    extra = (1.0 - hollow_fraction) * available * 0.46
    return contact + wall + extra, back - wall - extra


def _source_zone_cutters(
    genes: dict[str, float | int],
    source: trimesh.Trimesh,
    boundary: list[tuple[np.ndarray, np.ndarray]],
    start_u: float,
    end_u: float,
    hollow_pct: float,
    rib_count: int,
    rib_thickness: float,
) -> list[trimesh.Trimesh]:
    if hollow_pct <= 0 or end_u - start_u < 8.0:
        return []
    fraction = float(np.clip(hollow_pct / 100.0, 0.05, 1.0))
    slant = min(4.0, max(1.2, (end_u - start_u) * 0.07))
    usable = end_u - start_u - slant
    slot_count = max(1, int(rib_count) + 1)
    pitch = usable / slot_count
    material = min(float(rib_thickness), pitch * 0.58)
    cutters: list[trimesh.Trimesh] = []
    for index in range(slot_count):
        c0 = start_u + index * pitch + material * 0.5
        c1 = start_u + (index + 1) * pitch - material * 0.5
        if c1 - c0 < 0.65:
            continue
        b0, b1 = c0 + slant, c1 + slant
        contact0, contact_back0 = _source_inner_edges(c0, genes, fraction, source, boundary)
        contact1, contact_back1 = _source_inner_edges(c1, genes, fraction, source, boundary)
        back_contact0, back0 = _source_inner_edges(b0, genes, fraction, source, boundary)
        back_contact1, back1 = _source_inner_edges(b1, genes, fraction, source, boundary)
        if min(
            contact_back0 - contact0,
            contact_back1 - contact1,
            back0 - back_contact0,
            back1 - back_contact1,
        ) < 0.8:
            continue
        polygon = Polygon([
            (contact0, LOCK_Y + c0),
            (back0, LOCK_Y + b0),
            (back1, LOCK_Y + b1),
            (contact1, LOCK_Y + c1),
        ]).buffer(0)
        if polygon.is_empty or not polygon.is_valid or polygon.area < 0.5:
            continue
        cutter = trimesh.creation.extrude_polygon(polygon, height=ROOT_THICKNESS_MM + 8.0, engine="earcut")
        cutter.apply_translation([0.0, 0.0, -ROOT_THICKNESS_MM - 4.0])
        cutters.append(cutter)
    return cutters


def build_source_mesh(
    raw_genes: dict[str, Any] | None,
    source: trimesh.Trimesh | None = None,
) -> tuple[trimesh.Trimesh, dict[str, int]]:
    """原始夹爪独立生成器：外形变形后，在尖端和后段分别切出贯穿斜肋空腔。"""
    genes = normalize_source_genes(raw_genes)
    src = source or source_mesh()
    mesh = _warp_source_mesh(src, genes)
    boundary = _source_side_boundary_segments(src)
    length = float(genes["source_length_mm"])
    split = length * float(genes["source_split_pos"])
    body_cutters = _source_zone_cutters(
        genes,
        src,
        boundary,
        4.0,
        max(12.0, split - 1.0),
        float(genes["source_body_hollow_pct"]),
        int(genes["source_body_rib_count"]),
        float(genes["source_body_rib_thickness_mm"]),
    )
    tip_cutters = _source_zone_cutters(
        genes,
        src,
        boundary,
        min(length - 10.0, split + 1.0),
        length - 3.0,
        float(genes["source_tip_hollow_pct"]),
        int(genes["source_tip_rib_count"]),
        float(genes["source_tip_rib_thickness_mm"]),
    )
    cutters = body_cutters + tip_cutters
    if cutters:
        mesh = trimesh.boolean.difference([mesh, *cutters], engine="manifold", check_volume=False)
        if not isinstance(mesh, trimesh.Trimesh):
            mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))
        mesh.remove_unreferenced_vertices()
    return mesh, {"tip": len(tip_cutters), "body": len(body_cutters)}


def source_parameterized_mesh_report(
    role: str,
    raw_genes: dict[str, Any] | None,
    source: trimesh.Trimesh | None = None,
    raw_interface: dict[str, Any] | None = None,
) -> tuple[trimesh.Trimesh, dict[str, Any]]:
    genes = normalize_source_genes(raw_genes)
    src = source or source_mesh()
    mesh, cavities = build_source_mesh(genes, src)
    mesh = adapt_interface_mesh(mesh, raw_interface, "body")
    size = mesh.extents
    volume = abs(float(mesh.volume))
    mount_error = mount_error_mm(mesh, src, raw_interface)
    degenerate = int(np.count_nonzero(mesh.area_faces < 1e-8))
    problems: list[str] = []
    if not mesh.is_watertight:
        problems.append("原始夹爪修改版本不是封闭实体")
    if not mesh.is_winding_consistent:
        problems.append("原始夹爪修改版本的三角面方向不一致")
    if volume <= 0:
        problems.append("原始夹爪修改版本体积无效")
    if not np.isfinite(mount_error) or mount_error > 0.05:
        problems.append("原始夹爪的固定基准孔/受约束双孔未与底座同步")
    if degenerate:
        problems.append(f"原始夹爪修改版本存在 {degenerate} 个退化三角面")
    if mesh.body_count != 1:
        problems.append(f"原始夹爪修改版本包含 {mesh.body_count} 个分离实体")
    tip_active = int(genes["source_tip_hollow_pct"]) > 0
    body_active = int(genes["source_body_hollow_pct"]) > 0
    structure = "全实心"
    if tip_active and body_active:
        structure = "尖端＋后段双区伪 Fin-Ray"
    elif tip_active:
        structure = "仅尖端伪 Fin-Ray"
    elif body_active:
        structure = "仅后段伪 Fin-Ray"
    return mesh, {
        "role": role,
        "label": "手指" if role == "finger" else f"手指 {role.upper()}",
        "reach_mm": round(float(mesh.bounds[1, 1] - interface_mount_top_y(raw_interface)), 2),
        "volume_mm3": round(volume, 2),
        "plastic_g": round(volume / 1000.0 * DENSITY_G_CM3, 2),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "size_mm": [round(float(x), 2) for x in size],
        "mount_error_mm": 999.0 if not np.isfinite(mount_error) else round(mount_error, 6),
        "degenerate_faces": degenerate,
        "body_count": int(mesh.body_count),
        "cavity_count": cavities["tip"] + cavities["body"],
        "zone_cavities": cavities,
        "contact_feature_count": cavities["tip"] + cavities["body"],
        "problems": problems,
        "notes": [f"原始夹爪独立生成器：当前内部结构为{structure}。"],
        "genes": genes,
        "stl": "原始夹爪-修改版.stl" if role == "finger" else f"原始夹爪-{role.upper()}-修改版.stl",
    }


def source_mesh_report(
    role: str,
    raw_genes: dict[str, Any] | None,
    source: trimesh.Trimesh | None = None,
    raw_interface: dict[str, Any] | None = None,
) -> tuple[trimesh.Trimesh, dict[str, Any]]:
    """原始模式逐顶点、逐三角面返回用户提供的主体，不套用 Fin-Ray 生成。"""
    genes = normalize_source_genes(raw_genes)
    mesh = adapt_interface_mesh((source or source_mesh()).copy(), raw_interface, "body")
    volume = abs(float(mesh.volume))
    degenerate = int(np.count_nonzero(mesh.area_faces < 1e-8))
    problems: list[str] = []
    if not mesh.is_watertight:
        problems.append("原始主体不是封闭实体")
    if not mesh.is_winding_consistent:
        problems.append("原始主体部分三角面方向不一致")
    if degenerate:
        problems.append(f"原始主体存在 {degenerate} 个退化三角面")
    if mesh.body_count != 1:
        problems.append(f"原始主体包含 {mesh.body_count} 个分离实体")
    interface_error = mount_error_mm(mesh, source, raw_interface)
    if not np.isfinite(interface_error) or interface_error > 0.05:
        problems.append("原始主体的固定基准孔/受约束双孔未按接口参数生成")
    return mesh, {
        "role": role,
        "label": "手指" if role == "finger" else f"手指 {role.upper()}",
        "reach_mm": round(float(mesh.bounds[1, 1] - interface_mount_top_y(raw_interface)), 2),
        "volume_mm3": round(volume, 2),
        "plastic_g": round(volume / 1000.0 * DENSITY_G_CM3, 2),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "size_mm": [round(float(x), 2) for x in mesh.extents],
        "mount_error_mm": 999.0 if not np.isfinite(interface_error) else round(interface_error, 6),
        "degenerate_faces": degenerate,
        "body_count": int(mesh.body_count),
        "cavity_count": 0,
        "contact_feature_count": 0,
        "problems": problems,
        "notes": ["当前显示和导出的是未经修改的原始主体。"],
        "genes": genes,
        "stl": "夹爪手指.stl" if role == "finger" else f"夹爪手指-{role.upper()}.stl",
    }


def design_report(
    design: dict[str, Any],
    source: trimesh.Trimesh | None = None,
    base: trimesh.Trimesh | None = None,
) -> tuple[dict[str, trimesh.Trimesh], dict[str, Any]]:
    mode = str(design.get("mode", "finray"))
    if mode not in {"source", "finray"}:
        raise ValueError("未知的主体生成模式")
    parameterized = bool(design.get("parameterized", mode != "source"))
    symmetric = bool(design.get("symmetric", True))
    interface = normalize_interface(design.get("interface"))
    roles = ["finger"] if symmetric else ["a", "b"]
    genes_by_role = {"finger": design.get("a", {}), "a": design.get("a", {}), "b": design.get("b", design.get("a", {}))}
    meshes: dict[str, trimesh.Trimesh] = {}
    fingers: dict[str, Any] = {}
    for role in roles:
        if mode == "source" and not parameterized:
            mesh, report = source_mesh_report(role, genes_by_role[role], source, interface)
        elif mode == "source":
            mesh, report = source_parameterized_mesh_report(role, genes_by_role[role], source, interface)
        else:
            mesh, report = mesh_report(role, genes_by_role[role], source, interface)
        meshes[role] = mesh
        fingers[role] = report
    coupled_base = adapt_interface_mesh((base or base_mesh()).copy(), interface, "base")
    interface_status = interface_report(meshes, coupled_base, interface)
    problems = [problem for report in fingers.values() for problem in report["problems"]]
    problems.extend(interface_status["problems"])
    notes = [note for report in fingers.values() for note in report["notes"]]
    quantity = 2 if symmetric else 1
    total_plastic = sum(report["plastic_g"] * quantity for report in fingers.values())
    reach = max(report["reach_mm"] for report in fingers.values())
    max_mount_error = max(float(report["mount_error_mm"]) for report in fingers.values())
    opening_loss = 0.0
    if mode == "finray":
        opening_loss = 2.0 * max(
            float(g["tip_lip_mm"]) + float(g["grip_height_mm"])
            for g in genes_by_role.values()
        )
    return meshes, {
        "symmetric": symmetric,
        "mode": mode,
        "parameterized": parameterized,
        "fingers": fingers,
        "pair": {
            "opening_mm": round(MAX_PAIR_OPENING_MM - opening_loss, 1),
            "max_opening_mm": MAX_PAIR_OPENING_MM,
            "reach_mm": reach,
            "plastic_g": round(total_plastic, 2),
            "print_quantity": 2 if symmetric else 1,
            "preview_gap_mm": FACE_GAP_MM,
            "preview_clearance_mm": FACE_GAP_MM,
        },
        "interface": {**interface_status, "body_mount_error_mm": round(max_mount_error, 6)},
        "problems": problems,
        "notes": list(dict.fromkeys(notes)),
        "ready": not problems,
    }


def copy_design(design: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(design)
