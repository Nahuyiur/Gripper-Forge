from __future__ import annotations

import hashlib
import random

import numpy as np
import pytest

from backend.model import design_report, mesh_report
from backend.schema import DEFAULT, GENES, SOURCE_DEFAULT, SOURCE_GENES


ACTIVE_CONTEXT = {
    "cradle_radius_mm": {"cradle_depth_mm": 3.0},
    "cradle_pos": {"cradle_radius_mm": 18.0, "cradle_depth_mm": 3.0},
    "cradle_depth_mm": {"cradle_radius_mm": 18.0},
    "grip_count": {"grip_height_mm": 0.9},
    "grip_height_mm": {"grip_count": 7},
    "grip_round": {"grip_count": 7, "grip_height_mm": 0.9},
    "nail_thickness_mm": {"nail_len_mm": 9.0},
}


def mesh_digest(mesh) -> str:
    vertices = np.round(mesh.vertices, 5)
    payload = vertices.tobytes() + mesh.faces.tobytes()
    return hashlib.sha256(payload).hexdigest()


def assert_printable(genes: dict) -> str:
    mesh, report = mesh_report("finger", genes)
    assert not report["problems"], report["problems"]
    assert report["watertight"] is True
    assert report["winding_consistent"] is True
    assert report["degenerate_faces"] == 0
    assert report["body_count"] == 1
    assert report["mount_error_mm"] == 0.0
    assert np.isfinite(mesh.vertices).all()
    return mesh_digest(mesh)


@pytest.mark.parametrize("name", list(GENES))
def test_every_adjustable_parameter_changes_real_stl_geometry(name: str) -> None:
    spec = GENES[name]
    context = ACTIVE_CONTEXT.get(name, {})
    low = {**DEFAULT, **context, name: spec["min"]}
    high = {**DEFAULT, **context, name: spec["max"]}
    assert assert_printable(low) != assert_printable(high), f"{name} 调到上下限后 STL 没有变化"


@pytest.mark.parametrize("name", list(GENES))
def test_every_parameter_accepts_minimum_default_and_maximum(name: str) -> None:
    spec = GENES[name]
    context = ACTIVE_CONTEXT.get(name, {})
    for value in (spec["min"], DEFAULT[name], spec["max"]):
        assert_printable({**DEFAULT, **context, name: value})


def test_deterministic_full_range_parameter_samples_are_printable() -> None:
    random.seed(8132026)
    for _ in range(160):
        genes = {}
        for name, spec in GENES.items():
            steps = int(round((spec["max"] - spec["min"]) / spec["step"]))
            index = random.randint(0, steps)
            value = spec["min"] + index * spec["step"]
            genes[name] = int(round(value)) if spec.get("int") else value
        assert_printable(genes)


def test_extreme_and_alternating_parameter_combinations_are_printable() -> None:
    low = {name: spec["min"] for name, spec in GENES.items()}
    high = {name: spec["max"] for name, spec in GENES.items()}
    alternating_a = {
        name: spec["min"] if index % 2 == 0 else spec["max"]
        for index, (name, spec) in enumerate(GENES.items())
    }
    alternating_b = {
        name: spec["max"] if index % 2 == 0 else spec["min"]
        for index, (name, spec) in enumerate(GENES.items())
    }
    for genes in (low, high, alternating_a, alternating_b):
        assert_printable(genes)


def test_left_and_right_can_use_independent_full_range_designs() -> None:
    left = {
        name: spec["min"] if index % 2 == 0 else spec["max"]
        for index, (name, spec) in enumerate(GENES.items())
    }
    right = {
        name: spec["max"] if index % 2 == 0 else spec["min"]
        for index, (name, spec) in enumerate(GENES.items())
    }
    meshes, report = design_report({"mode": "finray", "symmetric": False, "a": left, "b": right})
    assert report["ready"], report["problems"]
    assert set(meshes) == {"a", "b"}
    assert mesh_digest(meshes["a"]) != mesh_digest(meshes["b"])
    assert report["fingers"]["a"]["mount_error_mm"] == 0.0
    assert report["fingers"]["b"]["mount_error_mm"] == 0.0


SOURCE_ACTIVE_CONTEXT = {
    "source_split_pos": {"source_tip_hollow_pct": 65, "source_body_hollow_pct": 65},
    "source_wall_thickness_mm": {"source_tip_hollow_pct": 65, "source_body_hollow_pct": 65},
    "source_tip_rib_count": {"source_tip_hollow_pct": 65},
    "source_tip_rib_thickness_mm": {"source_tip_hollow_pct": 65},
    "source_body_rib_count": {"source_body_hollow_pct": 65},
    "source_body_rib_thickness_mm": {"source_body_hollow_pct": 65},
}


def assert_source_printable(genes: dict) -> str:
    meshes, report = design_report({
        "mode": "source", "parameterized": True, "symmetric": True, "a": genes, "b": genes,
    })
    mesh = meshes["finger"]
    assert report["mode"] == "source"
    assert report["ready"], report["problems"]
    finger = report["fingers"]["finger"]
    assert finger["watertight"] is True
    assert finger["winding_consistent"] is True
    assert finger["degenerate_faces"] == 0
    assert finger["body_count"] == 1
    assert finger["mount_error_mm"] == 0.0
    return mesh_digest(mesh)


@pytest.mark.parametrize("name", list(SOURCE_GENES))
def test_every_source_parameter_changes_source_geometry(name: str) -> None:
    spec = SOURCE_GENES[name]
    context = SOURCE_ACTIVE_CONTEXT.get(name, {})
    low = {**SOURCE_DEFAULT, **context, name: spec["min"]}
    high = {**SOURCE_DEFAULT, **context, name: spec["max"]}
    assert assert_source_printable(low) != assert_source_printable(high)


def test_source_solid_tip_body_and_dual_zone_modes_are_independent() -> None:
    digests = []
    for tip, body in ((0, 0), (65, 0), (0, 65), (65, 65)):
        genes = {**SOURCE_DEFAULT, "source_tip_hollow_pct": tip, "source_body_hollow_pct": body}
        digests.append(assert_source_printable(genes))
    assert len(set(digests)) == 4


def test_source_random_full_range_combinations_are_printable() -> None:
    random.seed(13082026)
    for _ in range(160):
        genes = {}
        for name, spec in SOURCE_GENES.items():
            steps = int(round((spec["max"] - spec["min"]) / spec["step"]))
            value = spec["min"] + random.randint(0, steps) * spec["step"]
            genes[name] = int(round(value)) if spec.get("int") else value
        assert_source_printable(genes)


def test_source_full_low_high_and_alternating_extremes_are_printable() -> None:
    low = {name: spec["min"] for name, spec in SOURCE_GENES.items()}
    high = {name: spec["max"] for name, spec in SOURCE_GENES.items()}
    alternating_a = {
        name: spec["min"] if index % 2 == 0 else spec["max"]
        for index, (name, spec) in enumerate(SOURCE_GENES.items())
    }
    alternating_b = {
        name: spec["max"] if index % 2 == 0 else spec["min"]
        for index, (name, spec) in enumerate(SOURCE_GENES.items())
    }
    for genes in (low, high, alternating_a, alternating_b):
        assert_source_printable(genes)


def test_source_left_and_right_keep_independent_internal_structures() -> None:
    left = {**SOURCE_DEFAULT, "source_tip_hollow_pct": 80, "source_body_hollow_pct": 0}
    right = {**SOURCE_DEFAULT, "source_tip_hollow_pct": 0, "source_body_hollow_pct": 80}
    low_meshes, low_report = design_report({
        "mode": "source", "parameterized": True, "symmetric": False, "a": left, "b": right,
    })
    assert low_report["ready"], low_report["problems"]
    assert mesh_digest(low_meshes["a"]) != mesh_digest(low_meshes["b"])
    assert low_report["fingers"]["a"]["zone_cavities"]["tip"] > 0
    assert low_report["fingers"]["a"]["zone_cavities"]["body"] == 0
    assert low_report["fingers"]["b"]["zone_cavities"]["tip"] == 0
    assert low_report["fingers"]["b"]["zone_cavities"]["body"] > 0
