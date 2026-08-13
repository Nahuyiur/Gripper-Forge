from copy import deepcopy
from pathlib import Path

import pytest

from backend.families import ConstructionFamily, FamilyRegistry
from backend.model import ROOT, design_report
from backend.schema import FAMILY_REGISTRY, TEMPLATES, public_schema


def test_public_catalog_describes_every_registered_family() -> None:
    schema = public_schema()
    assert [family["id"] for family in schema["families"]] == [
        "source", "finray", "arc_wrap", "precision_tip",
    ]
    assert schema["gene_sets"] == FAMILY_REGISTRY.gene_sets()
    assert schema["group_sets"] == FAMILY_REGISTRY.group_sets()
    for family in schema["families"]:
        assert family["default_template"] in TEMPLATES
        assert family["generator"]
        assert family["version"] >= 1
        for asset in (family["seed"].get("body"), family["seed"].get("base")):
            if asset:
                assert (ROOT / Path(asset)).is_file()


def test_every_template_and_design_belongs_to_one_family() -> None:
    known = {family.family_id for family in FAMILY_REGISTRY.values()}
    for template in TEMPLATES.values():
        family_id = template["family_id"]
        assert family_id in known
        assert template["design"]["family_id"] == family_id


def test_family_id_drives_geometry_and_legacy_mode_still_loads() -> None:
    current = deepcopy(TEMPLATES["原始夹爪"]["design"])
    _, current_report = design_report(current)
    assert current_report["family_id"] == "source"

    legacy = deepcopy(current)
    legacy.pop("family_id")
    _, legacy_report = design_report(legacy)
    assert legacy_report["family_id"] == "source"


def test_unknown_family_fails_closed() -> None:
    design = deepcopy(TEMPLATES["原始夹爪"]["design"])
    design["family_id"] = "not-registered"
    with pytest.raises(ValueError, match="未知的基本构型"):
        design_report(design)


def test_registry_rejects_duplicate_family_ids() -> None:
    family = ConstructionFamily(
        family_id="example",
        title="示例",
        description="测试构型",
        generator="example-generator",
        default_template="示例",
        genes={},
        groups=[],
        seed={"kind": "procedural", "body": None, "base": None},
    )
    registry = FamilyRegistry([family])
    with pytest.raises(ValueError, match="构型 ID 重复"):
        registry.register(family)
