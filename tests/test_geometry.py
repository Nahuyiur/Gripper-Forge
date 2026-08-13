from __future__ import annotations

import base64
import io
import struct
import time
import zipfile
from copy import deepcopy

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

from backend.app import app
from backend.model import (
    FACE_GAP_MM,
    FIXED_HOLE_CENTER,
    base_mesh,
    base_mesh_for_design,
    back_x,
    build_mesh,
    cavity_edge,
    default_mount_mesh,
    design_report,
    inspect_model_pair,
    interface_hole_centers,
    interface_mount_top_y,
    mount_error_mm,
    planar_hole_pattern,
    profile_region,
    source_mesh,
)
from backend.schema import DEFAULT, INTERFACE_DEFAULT, INTERFACE_GENES, SOURCE_DEFAULT, SOURCE_GENES, TEMPLATES


def test_default_is_rebuilt_fin_ray_geometry() -> None:
    generated, cavity_count = build_mesh(DEFAULT)
    assert generated.is_watertight
    assert generated.is_winding_consistent
    assert generated.body_count == 1
    assert cavity_count == DEFAULT["rib_count"]
    assert generated.bounds[1, 1] == 55.0 + DEFAULT["finger_length_mm"]
    assert generated.volume != source_mesh().volume


def test_finray_default_tracks_so101_shape_without_replacing_robotiq_interface() -> None:
    region, cavity_count = profile_region(DEFAULT)
    _, report = design_report(TEMPLATES["Fin-Ray 默认"]["design"])

    assert DEFAULT["finger_length_mm"] == 57.0
    assert DEFAULT["tip_thickness_mm"] == 12.0
    assert DEFAULT["wall_thickness_mm"] == 1.6
    assert DEFAULT["rib_count"] == 14
    assert cavity_count == 14
    assert len(region.interiors) == 14
    assert back_x(0.0, 57.0) == pytest.approx(21.623, abs=0.15)
    assert back_x(28.5, 57.0) == pytest.approx(15.19, abs=0.2)
    assert back_x(57.0, 57.0) == pytest.approx(0.87, abs=0.15)
    assert cavity_edge(14, 14, 57.0) == pytest.approx(53.76, abs=0.15)

    interface = report["interface"]
    assert interface["fastener_count"] == 3
    assert interface["body_mount_error_mm"] == 0.0
    assert interface["robotiq_side_feature_error_mm"] == 0.0
    assert interface["rear_opening_error_mm"] == 0.0
    assert interface["base_coupled"] is True


def test_refresh_default_is_exact_original_body() -> None:
    design = TEMPLATES["原始夹爪"]["design"]
    meshes, report = design_report(design)
    generated = meshes["finger"]
    source = source_mesh()
    assert design["mode"] == "source"
    assert report["mode"] == "source"
    assert generated.faces.shape == source.faces.shape
    assert generated.vertices.shape == source.vertices.shape
    assert (generated.faces == source.faces).all()
    assert (generated.vertices == source.vertices).all()


def test_adjusting_source_template_keeps_source_identity_but_builds_modified_geometry() -> None:
    design = deepcopy(TEMPLATES["原始夹爪"]["design"])
    design["parameterized"] = True
    design["a"]["source_length_mm"] += 5.0
    design["b"] = deepcopy(design["a"])
    meshes, report = design_report(design)
    generated = meshes["finger"]
    assert report["mode"] == "source"
    assert report["parameterized"] is True
    assert report["ready"] is True
    assert not (generated.vertices == source_mesh().vertices).all()
    assert report["fingers"]["finger"]["genes"]["source_length_mm"] == SOURCE_DEFAULT["source_length_mm"] + 5.0


def test_mount_interface_is_locked_for_extreme_design() -> None:
    extreme = {
        **DEFAULT,
        "finger_length_mm": 105.0,
        "tip_thickness_mm": 30.0,
        "tip_lip_mm": 6.0,
        "wall_thickness_mm": 4.0,
        "rib_count": 18,
        "rib_thickness_mm": 3.0,
        "grip_count": 14,
        "grip_height_mm": 2.0,
        "nail_len_mm": 14.0,
        "nail_thickness_mm": 4.0,
    }
    generated, _ = build_mesh(extreme)
    assert mount_error_mm(generated) == 0.0
    assert default_mount_mesh().is_watertight


def test_every_template_is_a_valid_printable_mesh() -> None:
    for template in TEMPLATES.values():
        meshes, report = design_report(template["design"])
        assert report["ready"], report["problems"]
        assert report["interface"]["fastener_count"] == 3
        assert report["interface"]["base_coupled"] is True
        assert report["interface"]["body_mount_error_mm"] == 0.0
        for role, mesh in meshes.items():
            finger = report["fingers"][role]
            assert mesh.is_watertight
            assert mesh.is_winding_consistent
            assert finger["mount_error_mm"] == 0.0
            assert finger["degenerate_faces"] == 0
            assert finger["body_count"] == 1
            expected_cavities = 0 if template["design"].get("mode") == "source" else finger["genes"]["rib_count"]
            assert finger["cavity_count"] == expected_cavities
            assert finger["volume_mm3"] > 0


def test_all_contact_controls_change_the_profile_and_mesh() -> None:
    plain_region, _ = profile_region({**DEFAULT, "tip_lip_mm": 0, "grip_count": 0, "grip_height_mm": 0})
    textured_genes = {
        **DEFAULT,
        "tip_lip_mm": 4.0,
        "grip_count": 6,
        "grip_height_mm": 1.0,
    }
    textured_region, _ = profile_region(textured_genes)
    plain, _ = build_mesh({**DEFAULT, "tip_lip_mm": 0, "grip_count": 0, "grip_height_mm": 0})
    textured, _ = build_mesh(textured_genes)
    assert textured.is_watertight
    assert textured.body_count == 1
    assert textured_region.area != plain_region.area
    assert textured.volume > plain.volume
    assert textured.bounds[0, 0] < plain.bounds[0, 0] - 3.0


def test_cradle_and_nail_controls_are_real_geometry() -> None:
    plain, _ = build_mesh(DEFAULT)
    cradle, _ = build_mesh({**DEFAULT, "cradle_radius_mm": 18, "cradle_depth_mm": 3})
    nail, _ = build_mesh({**DEFAULT, "nail_len_mm": 9, "nail_thickness_mm": 1.2})
    assert cradle.volume != plain.volume
    assert nail.bounds[1, 1] >= plain.bounds[1, 1] + 8.9
    assert cradle.is_watertight and nail.is_watertight


def test_default_body_base_pair_matches_three_holes_and_robotiq_plane() -> None:
    report = inspect_model_pair(source_mesh(), base_mesh())
    assert report["ready"] is True
    assert report["editable"] is True
    assert report["body_hole_count"] == 3
    assert report["base_hole_count"] == 3
    assert report["axis_error_mm"] == 0.0
    assert report["robotiq_pattern_error_mm"] == 0.0


def test_shifted_base_is_rejected_as_mismatched_pair() -> None:
    shifted_base = base_mesh().copy()
    shifted_base.apply_translation([1.0, 0.0, 0.0])
    report = inspect_model_pair(source_mesh(), shifted_base)
    assert report["ready"] is False
    assert report["editable"] is False
    assert report["axis_error_mm"] == 1.0
    assert any("不共轴" in problem for problem in report["problems"])


def test_pair_preview_uses_explicit_face_clearance() -> None:
    _, report = design_report({"symmetric": True, "a": DEFAULT, "b": DEFAULT})
    assert report["ready"] is True
    assert report["pair"]["preview_gap_mm"] == FACE_GAP_MM
    assert report["pair"]["preview_clearance_mm"] == FACE_GAP_MM


def test_api_check_build_and_download_roundtrip() -> None:
    client = TestClient(app)
    design = TEMPLATES["指甲薄片"]["design"]
    schema = client.get("/api/schema")
    assert schema.status_code == 200
    assert schema.json()["schema"]["geometry"]["method"] == "dual-source-and-finray"
    assert schema.json()["schema"]["default_template"] == "原始夹爪"
    schema_payload = schema.json()["schema"]
    assert [item["key"] for item in schema_payload["categories"]] == ["source", "finray"]
    assert set(schema_payload["gene_sets"]["source"]) == set(SOURCE_GENES)
    assert all(TEMPLATES[name]["category"] == "finray" for name in ("防滑纹", "圆物托槽", "指甲薄片"))

    checked = client.post("/api/check", json={"design": design})
    assert checked.status_code == 200
    assert checked.json()["report"]["ready"] is True

    source_design = deepcopy(TEMPLATES["原始夹爪"]["design"])
    source_design["parameterized"] = True
    source_design["a"]["source_tip_hollow_pct"] = 65
    source_design["b"] = deepcopy(source_design["a"])
    preview = client.post("/api/preview", json={"design": source_design})
    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("model/stl")
    assert len(preview.content) > 1000

    started = client.post("/api/build", json={"design": design})
    job = started.json()["job"]
    state = {"state": "running"}
    for _ in range(50):
        state = client.get("/api/job", params={"job": job}).json()
        if state["state"] != "running":
            break
        time.sleep(0.02)
    assert state["state"] == "done"

    for role in ("finger",):
        response = client.get("/api/stl", params={"job": job, "role": role})
        assert response.status_code == 200
        mesh = trimesh.load_mesh(trimesh.util.wrap_as_stream(response.content), file_type="stl", process=True)
        assert mesh.is_watertight
        assert mesh.volume > 0

    package = client.get("/api/package", params={"job": job})
    assert package.status_code == 200
    with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
        assert "Robotiq转接底座.stl" in archive.namelist()
    assert client.get("/api/base").status_code == 200
    assert client.get("/api/mount").status_code == 200


def test_import_pair_checks_and_builds_current_mount_and_base() -> None:
    client = TestClient(app)
    imported = client.post("/api/import-pair", json={
        "body_name": "当前主体.stl",
        "body_base64": base64.b64encode(source_mesh().export(file_type="stl")).decode("ascii"),
        "base_name": "当前底座.stl",
        "base_base64": base64.b64encode(base_mesh().export(file_type="stl")).decode("ascii"),
    })
    assert imported.status_code == 200
    payload = imported.json()
    assert payload["report"]["editable"] is True
    pair_id = payload["pair_id"]
    assert client.get("/api/imported", params={"pair_id": pair_id, "part": "mount"}).status_code == 200
    checked = client.post("/api/check", json={"design": TEMPLATES["Fin-Ray 默认"]["design"], "pair_id": pair_id})
    assert checked.status_code == 200
    assert checked.json()["report"]["ready"] is True


def test_invalid_parameter_is_rejected() -> None:
    client = TestClient(app)
    design = TEMPLATES["Fin-Ray 默认"]["design"]
    bad = {**design, "a": {**design["a"], "finger_length_mm": 999}}
    response = client.post("/api/check", json={"design": bad})
    assert response.status_code == 422
    assert "超出允许范围" in response.json()["detail"]


def _feature_signature(mesh: trimesh.Trimesh, *, use_max: bool) -> list[tuple[tuple[float, ...], tuple[float, ...]]]:
    from backend.model import planar_hole_pattern

    return [
        (tuple(round(value, 4) for value in item["center"]), tuple(round(value, 4) for value in item["opening"]))
        for item in planar_hole_pattern(mesh, axis=1, use_max=use_max)
    ]


def test_interface_schema_defaults_reproduce_original_stl_holes() -> None:
    client = TestClient(app)
    payload = client.get("/api/schema").json()["schema"]
    assert payload["interface_genes"] == INTERFACE_GENES
    assert payload["interface_default"] == INTERFACE_DEFAULT
    centers = interface_hole_centers(payload["interface_default"])
    assert np.allclose(centers[0], FIXED_HOLE_CENTER)
    assert np.allclose(centers[1:], [[35.035898208618164, 15.0], [35.035898208618164, 50.0]])
    # 默认 source 模式保持原始网格逐点/逐面身份。
    meshes, report = design_report(TEMPLATES["原始夹爪"]["design"])
    assert report["ready"]
    assert np.array_equal(meshes["finger"].vertices, source_mesh().vertices)
    assert np.array_equal(base_mesh_for_design(TEMPLATES["原始夹爪"]["design"]).vertices, base_mesh().vertices)


@pytest.mark.parametrize("pitch", [20.0, 27.5, 35.0])
@pytest.mark.parametrize("span", [20.0, 25.0, INTERFACE_DEFAULT["single_to_pair_span_mm"]])
def test_interface_adapter_couples_body_and_base_and_freezes_robotiq_features(pitch: float, span: float) -> None:
    design = deepcopy(TEMPLATES["原始夹爪"]["design"])
    design["interface"] = {"pair_hole_pitch_mm": pitch, "single_to_pair_span_mm": span}
    meshes, report = design_report(design)
    adjusted_base = base_mesh_for_design(design)
    interface = report["interface"]
    expected = interface_hole_centers(design["interface"])
    assert report["ready"], report["problems"]
    assert np.allclose(interface["fixed_hole_center_mm"], expected[0])
    assert np.allclose(interface["pair_hole_centers_mm"], expected[1:])
    assert interface["body_base_axis_error_mm"] <= 0.000002
    assert interface["pair_axis_error_mm"] == 0.0
    assert interface["right_angle_dot_mm2"] == 0.0
    assert meshes["finger"].is_watertight and adjusted_base.is_watertight
    assert _feature_signature(adjusted_base, use_max=False) == _feature_signature(base_mesh(), use_max=False)
    # 双孔侧原始外沿的全部顶点必须等量横移，不能随 Y 形成梯形斜边。
    default_base = base_mesh()
    delta_x = span - float(INTERFACE_DEFAULT["single_to_pair_span_mm"])
    pair_side = np.isclose(default_base.vertices[:, 0], default_base.bounds[1, 0], atol=1e-6)
    expected_pair_side_x = float(default_base.bounds[1, 0] + delta_x)
    assert np.allclose(adjusted_base.vertices[pair_side, 0], expected_pair_side_x, atol=1e-6)
    assert adjusted_base.bounds[1, 0] == pytest.approx(expected_pair_side_x, abs=1e-6)
    # Robotiq 前端三孔冻结；相反一侧的两个矩形开口随双孔侧外轮廓刚性移动。
    expected_rear = [
        ((round(center[0] + delta_x, 4), center[1]), opening)
        for center, opening in _feature_signature(base_mesh(), use_max=True)
    ]
    assert _feature_signature(adjusted_base, use_max=True) == expected_rear

    # 纵向边界保持与上排孔相同的默认余量，主体有效长度不被接口压缩吞掉。
    delta_y = pitch - float(INTERFACE_DEFAULT["pair_hole_pitch_mm"])
    assert adjusted_base.bounds[1, 1] == pytest.approx(base_mesh().bounds[1, 1] + delta_y, abs=1e-6)
    assert interface["base_upper_boundary_error_mm"] == 0.0
    assert interface["body_mount_top_y_mm"] == pytest.approx(interface_mount_top_y(design["interface"]), abs=1e-6)
    assert report["fingers"]["finger"]["reach_mm"] == pytest.approx(
        source_mesh().bounds[1, 1] - 55.0,
        abs=0.01,
    )

    # 主体和底座外端面上的真实孔型都必须保持尺寸并落在同一组目标中心。
    body_pattern = planar_hole_pattern(meshes["finger"], plane_value_override=float(meshes["finger"].bounds[1, 2]))
    base_pattern = planar_hole_pattern(adjusted_base, plane_value_override=float(adjusted_base.bounds[1, 2]))
    assert np.allclose([item["center"] for item in body_pattern], expected, atol=2e-6)
    assert np.allclose([item["center"] for item in base_pattern], expected, atol=2e-6)
    assert np.allclose([item["opening"] for item in body_pattern], [[3.6, 3.6]] * 3, atol=2e-5)
    assert np.allclose([item["opening"] for item in base_pattern], [[6.928203, 6.0]] * 3, atol=2e-5)


def test_interface_combines_with_existing_source_and_finray_parameters() -> None:
    for interface in (
        {"pair_hole_pitch_mm": 20.0, "single_to_pair_span_mm": 20.0},
        {"pair_hole_pitch_mm": 35.0, "single_to_pair_span_mm": 25.0},
    ):
        source_design = deepcopy(TEMPLATES["原始夹爪"]["design"])
        source_design.update({"parameterized": True, "interface": interface})
        source_design["a"].update({
            "source_length_mm": 90.0,
            "source_tip_thickness_mm": 30.0,
            "source_tip_hollow_pct": 65,
        })
        source_design["b"] = deepcopy(source_design["a"])
        finray_design = deepcopy(TEMPLATES["Fin-Ray 默认"]["design"])
        finray_design["interface"] = interface
        finray_design["a"].update({
            "finger_length_mm": 96.0,
            "tip_thickness_mm": 30.0,
            "grip_count": 7,
            "grip_height_mm": 0.9,
        })
        finray_design["b"] = deepcopy(finray_design["a"])
        for design in (source_design, finray_design):
            _, report = design_report(design)
            assert report["ready"], report["problems"]
            assert report["interface"]["body_base_axis_error_mm"] <= 0.000002


def test_preview_parts_and_export_package_use_same_adjusted_base() -> None:
    client = TestClient(app)
    design = deepcopy(TEMPLATES["原始夹爪"]["design"])
    design["interface"] = {"pair_hole_pitch_mm": 25.0, "single_to_pair_span_mm": 24.0}
    previews = {}
    for part in ("body", "mount", "base"):
        response = client.post(f"/api/preview?part={part}", json={"design": design})
        assert response.status_code == 200, response.text
        assert response.headers["x-gripper-part"] == part
        previews[part] = response.content
    assert previews["body"] != previews["mount"] != previews["base"]
    started = client.post("/api/build", json={"design": design})
    job = started.json()["job"]
    state = client.get("/api/job", params={"job": job}).json()
    assert state["state"] == "done"
    package = client.get("/api/package", params={"job": job})
    with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
        packaged_base = archive.read("Robotiq转接底座.stl")
    preview_base = trimesh.load_mesh(trimesh.util.wrap_as_stream(previews["base"]), file_type="stl", process=True)
    export_base = trimesh.load_mesh(trimesh.util.wrap_as_stream(packaged_base), file_type="stl", process=True)
    assert np.allclose(preview_base.extents, export_base.extents)
    assert np.isclose(preview_base.volume, export_base.volume, rtol=1e-6)


def test_live_preview_returns_exact_body_and_base_in_one_binary_response() -> None:
    client = TestClient(app)
    design = deepcopy(TEMPLATES["原始夹爪"]["design"])
    design["interface"] = {"pair_hole_pitch_mm": 20.0, "single_to_pair_span_mm": 21.0}
    response = client.post("/api/preview-live", json={"design": design})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/vnd.gripper.live-preview")
    magic, body_length, base_length = struct.unpack("<4sII", response.content[:12])
    assert magic == b"GRIP"
    assert len(response.content) == 12 + body_length + base_length
    body_bytes = response.content[12:12 + body_length]
    base_bytes = response.content[12 + body_length:]
    body = trimesh.load_mesh(trimesh.util.wrap_as_stream(body_bytes), file_type="stl", process=True)
    base = trimesh.load_mesh(trimesh.util.wrap_as_stream(base_bytes), file_type="stl", process=True)
    expected_body = design_report(design)[0]["finger"]
    expected_base = base_mesh_for_design(design)
    assert body.is_watertight and base.is_watertight
    assert np.allclose(body.extents, expected_body.extents, atol=1e-5)
    assert np.allclose(base.extents, expected_base.extents, atol=1e-5)
    assert np.isclose(body.volume, expected_body.volume, rtol=1e-6)
    assert np.isclose(base.volume, expected_base.volume, rtol=1e-6)


def test_imported_pair_fails_closed_for_nondefault_interface() -> None:
    client = TestClient(app)
    imported = client.post("/api/import-pair", json={
        "body_name": "主体.stl",
        "body_base64": base64.b64encode(source_mesh().export(file_type="stl")).decode("ascii"),
        "base_name": "底座.stl",
        "base_base64": base64.b64encode(base_mesh().export(file_type="stl")).decode("ascii"),
    }).json()
    design = deepcopy(TEMPLATES["原始夹爪"]["design"])
    design["interface"]["pair_hole_pitch_mm"] = 25.0
    response = client.post("/api/check", json={"pair_id": imported["pair_id"], "design": design})
    assert response.status_code == 422
    assert "缺少可重建接口的特征语义" in response.json()["detail"]
