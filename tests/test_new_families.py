from __future__ import annotations

import hashlib
import struct
import time
from copy import deepcopy

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient

from backend.app import app
from backend.geometry_families import ARC_WRAP_GENES, PRECISION_TIP_GENES
from backend.model import (
    ROOT_THICKNESS_MM,
    Z_CENTER,
    base_mesh_for_design,
    design_report,
    interface_hole_centers,
    planar_hole_pattern,
)
from backend.schema import INTERFACE_DEFAULT, INTERFACE_GENES, TEMPLATES


FAMILIES = (
    ("弧面包覆", "arc_wrap", ARC_WRAP_GENES),
    ("精密尖指", "precision_tip", PRECISION_TIP_GENES),
)


def _mesh_digest(mesh: trimesh.Trimesh) -> str:
    return hashlib.sha256(mesh.export(file_type="stl")).hexdigest()


def _assert_printable(mesh: trimesh.Trimesh) -> None:
    assert mesh.is_watertight
    assert mesh.is_winding_consistent
    assert mesh.body_count == 1
    assert mesh.volume > 0
    assert np.count_nonzero(mesh.area_faces < 1e-8) == 0


def _assert_real_body_interface(mesh: trimesh.Trimesh, design: dict) -> None:
    expected = interface_hole_centers(design.get("interface"))
    for z in (Z_CENTER - ROOT_THICKNESS_MM / 2.0, Z_CENTER + ROOT_THICKNESS_MM / 2.0):
        pattern = planar_hole_pattern(mesh, plane_value_override=float(z))
        assert len(pattern) == 3
        actual = np.asarray(sorted((item["center"] for item in pattern)), dtype=np.float64)
        target = np.asarray(sorted(expected.tolist()), dtype=np.float64)
        assert np.allclose(actual, target, atol=2e-6)
        for feature in pattern:
            assert np.allclose(feature["opening"], [3.6, 3.6], atol=2e-6)


@pytest.mark.parametrize("template_name,family_id,_genes", FAMILIES)
def test_new_family_default_is_a_real_printable_three_hole_body(
    template_name: str,
    family_id: str,
    _genes: dict,
) -> None:
    design = deepcopy(TEMPLATES[template_name]["design"])
    meshes, report = design_report(design)
    mesh = meshes["finger"]

    assert design["family_id"] == family_id
    assert "mode" not in design
    assert report["family_id"] == family_id
    assert report["ready"], report["problems"]
    assert report["fingers"]["finger"]["cavity_count"] == 0
    assert report["interface"]["fastener_count"] == 3
    assert report["interface"]["base_coupled"] is True
    assert report["interface"]["body_mount_error_mm"] <= 0.000002
    _assert_printable(mesh)
    _assert_real_body_interface(mesh, design)


@pytest.mark.parametrize("template_name,_family_id,genes", FAMILIES)
def test_every_new_family_control_changes_the_exported_stl(
    template_name: str,
    _family_id: str,
    genes: dict,
) -> None:
    for name, spec in genes.items():
        low = deepcopy(TEMPLATES[template_name]["design"])
        high = deepcopy(TEMPLATES[template_name]["design"])
        low["a"][name] = spec["min"]
        high["a"][name] = spec["max"]

        low_meshes, low_report = design_report(low)
        high_meshes, high_report = design_report(high)
        assert low_report["ready"], (name, low_report["problems"])
        assert high_report["ready"], (name, high_report["problems"])
        assert _mesh_digest(low_meshes["finger"]) != _mesh_digest(high_meshes["finger"]), name


@pytest.mark.parametrize("template_name,_family_id,genes", FAMILIES)
@pytest.mark.parametrize("edge", ("min", "max"))
def test_new_family_all_parameter_edges_remain_printable(
    template_name: str,
    _family_id: str,
    genes: dict,
    edge: str,
) -> None:
    design = deepcopy(TEMPLATES[template_name]["design"])
    design["a"] = {name: spec[edge] for name, spec in genes.items()}
    meshes, report = design_report(design)
    assert report["ready"], report["problems"]
    _assert_printable(meshes["finger"])
    _assert_real_body_interface(meshes["finger"], design)


@pytest.mark.parametrize("template_name,_family_id,_genes", FAMILIES)
@pytest.mark.parametrize(
    "pitch,span",
    (
        (INTERFACE_DEFAULT["pair_hole_pitch_mm"], INTERFACE_DEFAULT["single_to_pair_span_mm"]),
        (INTERFACE_GENES["pair_hole_pitch_mm"]["min"], INTERFACE_GENES["single_to_pair_span_mm"]["min"]),
        (INTERFACE_GENES["pair_hole_pitch_mm"]["min"], INTERFACE_GENES["single_to_pair_span_mm"]["max"]),
        (INTERFACE_GENES["pair_hole_pitch_mm"]["max"], INTERFACE_GENES["single_to_pair_span_mm"]["min"]),
        (INTERFACE_GENES["pair_hole_pitch_mm"]["max"], INTERFACE_GENES["single_to_pair_span_mm"]["max"]),
    ),
)
def test_new_family_interface_matrix_keeps_body_base_and_robotiq_features_coupled(
    template_name: str,
    _family_id: str,
    _genes: dict,
    pitch: float,
    span: float,
) -> None:
    design = deepcopy(TEMPLATES[template_name]["design"])
    design["interface"] = {
        "pair_hole_pitch_mm": pitch,
        "single_to_pair_span_mm": span,
    }
    meshes, report = design_report(design)
    base = base_mesh_for_design(design)

    assert report["ready"], report["problems"]
    assert report["interface"]["body_base_axis_error_mm"] <= 0.000002
    assert report["interface"]["robotiq_side_feature_error_mm"] == 0.0
    assert report["interface"]["rear_opening_error_mm"] == 0.0
    assert report["interface"]["base_upper_boundary_error_mm"] == 0.0
    _assert_printable(meshes["finger"])
    _assert_printable(base)
    _assert_real_body_interface(meshes["finger"], design)


@pytest.mark.parametrize("template_name,_family_id,_genes", FAMILIES)
def test_new_family_live_preview_and_build_use_the_same_geometry(
    template_name: str,
    _family_id: str,
    _genes: dict,
) -> None:
    client = TestClient(app)
    design = deepcopy(TEMPLATES[template_name]["design"])
    design["interface"] = {"pair_hole_pitch_mm": 25.0, "single_to_pair_span_mm": 24.0}

    live = client.post("/api/preview-live", json={"design": design})
    assert live.status_code == 200, live.text
    magic, body_length, base_length = struct.unpack("<4sII", live.content[:12])
    assert magic == b"GRIP"
    assert len(live.content) == 12 + body_length + base_length
    live_body = trimesh.load_mesh(
        trimesh.util.wrap_as_stream(live.content[12:12 + body_length]),
        file_type="stl",
        process=True,
    )

    started = client.post("/api/build", json={"design": design})
    assert started.status_code == 200, started.text
    job = started.json()["job"]
    state = {"state": "running"}
    for _ in range(100):
        state = client.get("/api/job", params={"job": job}).json()
        if state["state"] != "running":
            break
        time.sleep(0.01)
    assert state["state"] == "done", state
    exported = client.get("/api/stl", params={"job": job, "role": "finger"})
    assert exported.status_code == 200
    export_body = trimesh.load_mesh(
        trimesh.util.wrap_as_stream(exported.content),
        file_type="stl",
        process=True,
    )

    assert np.allclose(live_body.extents, export_body.extents, atol=1e-5)
    assert np.isclose(live_body.volume, export_body.volume, rtol=1e-6)
    _assert_real_body_interface(export_body, design)
