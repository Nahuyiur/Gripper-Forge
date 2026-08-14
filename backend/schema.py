from __future__ import annotations

from copy import deepcopy

from .families import ConstructionFamily, FamilyRegistry
from .geometry_families import (
    ARC_WRAP_DEFAULT,
    ARC_WRAP_GENES,
    ARC_WRAP_GROUPS,
    PRECISION_TIP_DEFAULT,
    PRECISION_TIP_GENES,
    PRECISION_TIP_GROUPS,
)


INTERFACE_GENES = {
    "pair_hole_pitch_mm": {
        "min": 20.0, "max": 35.0, "step": 0.5, "group": "interface",
        "label": "双孔纵向中心距", "unit": "毫米",
        "blurb": "两颗可调孔始终共用同一条 X 轴线；该值控制它们的 Y 向中心距。",
    },
    "single_to_pair_span_mm": {
        "min": 20.0, "max": 30.0718, "step": 0.5, "group": "interface",
        "label": "单孔到双孔轴线横距", "unit": "毫米",
        "blurb": "固定单孔保持不动；该值控制固定孔到双孔共同 X 轴线的距离。",
    },
}

INTERFACE_GROUPS = [
    {"key": "interface", "title": "三孔连接接口"},
]

# 这些数值直接来自 public/ 中两份原始 STL 的孔中心。默认值必须精确
# 复现原网格，不能为了滑块步长将 30.071797... 四舍五入成 30.0。
INTERFACE_DEFAULT = {
    "pair_hole_pitch_mm": 35.0,
    "single_to_pair_span_mm": 30.071797370910645,
}

# 两个原创紧凑构型不需要沿用原始 STL 的宽安装轮廓。双孔轴线内收后，
# 主体和底座仍由同一接口参数同步生成，固定单孔与 Robotiq 侧孔不动。
COMPACT_INTERFACE_DEFAULT = {
    **INTERFACE_DEFAULT,
    "single_to_pair_span_mm": 22.0,
}


GENES = {
    "finger_length_mm": {
        "min": 45.0, "max": 105.0, "step": 0.5, "group": "shape",
        "label": "手指有效长度", "unit": "毫米",
        "blurb": "重新构造安装区以上的可调主体；连接孔由共享接口参数层独立处理。",
    },
    "tip_thickness_mm": {
        "min": 12.0, "max": 30.0, "step": 0.5, "group": "shape",
        "label": "指尖厚度", "unit": "毫米",
        "blurb": "沿厚度方向从根部 26 毫米平滑渐缩到指尖。",
    },
    "tip_lip_mm": {
        "min": 0.0, "max": 6.0, "step": 0.25, "group": "shape",
        "label": "指尖内扣", "unit": "毫米",
        "blurb": "直接改变接触面轮廓并生成实体内扣，不再外挂方块。",
    },
    "wall_thickness_mm": {
        "min": 1.2, "max": 4.0, "step": 0.1, "group": "spring",
        "label": "外壁厚度", "unit": "毫米",
        "blurb": "控制接触侧与背梁的连续外壁，越厚越硬。",
    },
    "rib_count": {
        "min": 4, "max": 18, "step": 1, "group": "spring",
        "label": "内部肋条数量", "unit": "条", "int": True,
        "blurb": "改变内部斜肋与空腔数量，预览和 STL 同步重建。",
    },
    "rib_thickness_mm": {
        "min": 0.8, "max": 3.0, "step": 0.1, "group": "spring",
        "label": "内部肋条厚度", "unit": "毫米",
        "blurb": "控制斜肋宽度；越厚越强，也会减少形变。",
    },
    "cradle_radius_mm": {
        "min": 0.0, "max": 30.0, "step": 0.5, "group": "cradle",
        "label": "弧形托槽半径", "unit": "毫米",
        "blurb": "设为零关闭；从零调高时会自动给出可见深度。",
    },
    "cradle_pos": {
        "min": 0.15, "max": 0.85, "step": 0.01, "group": "cradle",
        "label": "托槽位置", "unit": "比例",
        "blurb": "控制托槽沿手指长度的位置；若托槽关闭，会自动启用。",
    },
    "cradle_depth_mm": {
        "min": 0.0, "max": 7.0, "step": 0.25, "group": "cradle",
        "label": "托槽深度", "unit": "毫米",
        "blurb": "控制接触面凹弧深度；从零调高时会自动给出半径。",
    },
    "grip_count": {
        "min": 0, "max": 14, "step": 1, "group": "grip",
        "label": "防滑纹数量", "unit": "条", "int": True,
        "blurb": "直接写入接触面轮廓；设为零可关闭。",
    },
    "grip_height_mm": {
        "min": 0.0, "max": 2.0, "step": 0.1, "group": "grip",
        "label": "防滑纹高度", "unit": "毫米",
        "blurb": "纹路越高越明显；与数量联动，始终生成连续实体。",
    },
    "grip_round": {
        "min": 0, "max": 1, "step": 1, "group": "grip",
        "label": "圆滑防滑纹", "unit": "", "int": True, "boolean": True,
        "blurb": "切换圆滑或方形纹路；若纹路关闭，会自动生成六条。",
    },
    "nail_len_mm": {
        "min": 0.0, "max": 14.0, "step": 0.5, "group": "nail",
        "label": "指甲延伸长度", "unit": "毫米",
        "blurb": "在指尖形成一体式薄片，用于挑起薄物。",
    },
    "nail_thickness_mm": {
        "min": 0.6, "max": 4.0, "step": 0.1, "group": "nail",
        "label": "指甲厚度", "unit": "毫米",
        "blurb": "控制指尖薄片厚度；若薄片关闭，会自动给出延伸长度。",
    },
}

GROUPS = [
    {"key": "shape", "title": "形状"},
    {"key": "spring", "title": "内部弹性结构"},
    {"key": "cradle", "title": "弧形托槽"},
    {"key": "grip", "title": "抓持表面"},
    {"key": "nail", "title": "指甲薄片"},
]

SOURCE_GENES = {
    "source_length_mm": {
        "min": 55.0, "max": 105.0, "step": 0.5, "group": "source_shape",
        "label": "原始主体有效长度", "unit": "毫米",
        "blurb": "只拉伸安装区以上的原始主体；连接孔与底座由共享接口参数同步。",
    },
    "source_tip_thickness_mm": {
        "min": 12.0, "max": 30.0, "step": 0.5, "group": "source_shape",
        "label": "原始主体指尖厚度", "unit": "毫米",
        "blurb": "沿厚度方向平滑改变指尖，根部仍保持原始 26 毫米安装厚度。",
    },
    "source_tip_offset_mm": {
        "min": -8.0, "max": 8.0, "step": 0.25, "group": "source_shape",
        "label": "原始主体指尖侧偏", "unit": "毫米",
        "blurb": "保持原始轮廓风格，让上段整体向接触侧或背侧平滑偏移。",
    },
    "source_split_pos": {
        "min": 0.45, "max": 0.72, "step": 0.01, "group": "source_partition",
        "label": "尖端／后段分界", "unit": "比例",
        "blurb": "分界以上是尖端区，分界以下是后段主体区；默认尖端占上部 35%。",
    },
    "source_wall_thickness_mm": {
        "min": 2.0, "max": 4.5, "step": 0.25, "group": "source_partition",
        "label": "贯穿空腔外壁", "unit": "毫米",
        "blurb": "控制贯穿空腔到原始外轮廓的安全距离，两区共同使用。",
    },
    "source_tip_hollow_pct": {
        "min": 0, "max": 100, "step": 5, "group": "source_tip",
        "label": "尖端中空程度", "unit": "%", "int": True,
        "blurb": "零为尖端全实心；越高，尖端侧面贯穿空腔越大。",
    },
    "source_tip_rib_count": {
        "min": 2, "max": 9, "step": 1, "group": "source_tip",
        "label": "尖端伪 Fin-Ray 条数", "unit": "条", "int": True,
        "blurb": "只改变尖端区域的内部斜条数量，不影响后段主体。",
    },
    "source_tip_rib_thickness_mm": {
        "min": 1.0, "max": 4.0, "step": 0.25, "group": "source_tip",
        "label": "尖端斜条厚度", "unit": "毫米",
        "blurb": "只改变尖端区域相邻贯穿空腔之间保留的材料厚度。",
    },
    "source_body_hollow_pct": {
        "min": 0, "max": 100, "step": 5, "group": "source_body",
        "label": "后段主体中空程度", "unit": "%", "int": True,
        "blurb": "零为后段主体全实心；与尖端中空程度完全独立。",
    },
    "source_body_rib_count": {
        "min": 2, "max": 12, "step": 1, "group": "source_body",
        "label": "后段伪 Fin-Ray 条数", "unit": "条", "int": True,
        "blurb": "只改变后段主体区域的内部斜条数量，不影响尖端。",
    },
    "source_body_rib_thickness_mm": {
        "min": 1.0, "max": 4.0, "step": 0.25, "group": "source_body",
        "label": "后段斜条厚度", "unit": "毫米",
        "blurb": "只改变后段主体区域相邻贯穿空腔之间保留的材料厚度。",
    },
}

SOURCE_GROUPS = [
    {"key": "source_shape", "title": "原始外形变形"},
    {"key": "source_partition", "title": "内部区域划分"},
    {"key": "source_tip", "title": "尖端内部结构"},
    {"key": "source_body", "title": "后段主体内部结构"},
]

SOURCE_DEFAULT = {
    "source_length_mm": 78.0,
    "source_tip_thickness_mm": 26.0,
    "source_tip_offset_mm": 0.0,
    "source_split_pos": 0.65,
    "source_wall_thickness_mm": 3.0,
    "source_tip_hollow_pct": 0,
    "source_tip_rib_count": 4,
    "source_tip_rib_thickness_mm": 1.75,
    "source_body_hollow_pct": 0,
    "source_body_rib_count": 6,
    "source_body_rib_thickness_mm": 1.75,
}

DEFAULT = {
    # 截面节奏来自 so101-finger.stl 的 Fin-Ray 主体；默认有效长度放大到
    # 与本项目 40 毫米宽 Robotiq 安装座更协调的比例。安装端仍使用三孔
    # 共享接口和独立连接孔，不沿用 SO-101 的两孔安装块。
    "finger_length_mm": 76.0,
    "tip_thickness_mm": 12.0,
    "tip_lip_mm": 2.0,
    "wall_thickness_mm": 1.6,
    "rib_count": 14,
    "rib_thickness_mm": 1.3,
    "cradle_radius_mm": 0.0,
    "cradle_pos": 0.62,
    "cradle_depth_mm": 0.0,
    "grip_count": 0,
    "grip_height_mm": 0.0,
    "grip_round": 1,
    "nail_len_mm": 0.0,
    "nail_thickness_mm": 1.2,
}


def pair(
    a: dict,
    b: dict | None = None,
    symmetric: bool = True,
    family_id: str = "finray",
    interface: dict | None = None,
) -> dict:
    design = {
        "family_id": family_id,
        "symmetric": symmetric,
        "interface": deepcopy(interface or INTERFACE_DEFAULT),
        "a": deepcopy(a),
        "b": deepcopy(b or a),
    }
    # mode is a legacy source/Fin-Ray discriminator consumed by older clients.
    # New construction families use family_id only and must not widen DesignMode.
    if family_id in {"source", "finray"}:
        design["mode"] = family_id
        design["parameterized"] = family_id != "source"
    return design


TEMPLATES = {
    "原始夹爪": {
        "title": "原始夹爪",
        "family_id": "source",
        "category": "source",
        "blurb": "独立修改原始外形；尖端与后段主体可分别保持实心或生成侧面贯穿的伪 Fin-Ray 斜条。",
        "design": pair(SOURCE_DEFAULT, family_id="source"),
    },
    "Fin-Ray 默认": {
        "title": "Fin-Ray 默认",
        "family_id": "finray",
        "category": "finray",
        "blurb": "参考 SO-101 手指的纤细弧形背梁、十四腔渐变斜肋与薄指尖；安装端仍锁定当前 Robotiq 三孔接口和独立连接孔。",
        "design": pair(DEFAULT),
    },
    "防滑纹": {
        "title": "防滑纹",
        "family_id": "finray",
        "category": "finray",
        "blurb": "接触面带七条一体式圆滑纹路，适合光滑物体。",
        "design": pair({**DEFAULT, "rib_count": 8, "grip_count": 7, "grip_height_mm": 0.9}),
    },
    "圆物托槽": {
        "title": "圆物托槽",
        "family_id": "finray",
        "category": "finray",
        "blurb": "接触面生成凹弧，用于稳定包覆圆柱或瓶状物。",
        "design": pair({**DEFAULT, "finger_length_mm": 82.0, "cradle_radius_mm": 18.0, "cradle_depth_mm": 3.0}),
    },
    "指甲薄片": {
        "title": "指甲薄片",
        "family_id": "finray",
        "category": "finray",
        "blurb": "指尖生成一体式薄片，便于挑起纸片或扁平零件。",
        "design": pair({**DEFAULT, "finger_length_mm": 70.0, "rib_count": 7, "nail_len_mm": 9.0, "nail_thickness_mm": 1.2}),
    },
    "弧面包覆": {
        "title": "弧面包覆",
        "family_id": "arc_wrap",
        "blurb": "原创宽面薄身构型，以连续弧槽和圆钝前端包覆圆柱类物体。",
        "design": pair(
            ARC_WRAP_DEFAULT,
            family_id="arc_wrap",
            interface=COMPACT_INTERFACE_DEFAULT,
        ),
    },
    "精密尖指": {
        "title": "精密尖指",
        "family_id": "precision_tip",
        "blurb": "原创紧凑楔形构型，前窄后宽并保留局部平直接触段，用于精密捏取。",
        "design": pair(
            PRECISION_TIP_DEFAULT,
            family_id="precision_tip",
            interface=COMPACT_INTERFACE_DEFAULT,
        ),
    },
}


FAMILY_REGISTRY = FamilyRegistry([
    ConstructionFamily(
        family_id="source",
        title="原始夹爪",
        description="以用户提供的主体 STL 和配套底座 STL 为几何种子，在保留安装接口的前提下修改外形与内部结构。",
        generator="warped-source-with-independent-through-cavities",
        default_template="原始夹爪",
        genes=SOURCE_GENES,
        groups=SOURCE_GROUPS,
        seed={
            "kind": "stl_pair",
            "body": "public/zhuti-2-0813-original.stl",
            "base": "public/底座-original.stl",
        },
    ),
    ConstructionFamily(
        family_id="finray",
        title="Fin-Ray",
        description="由参数轮廓生成的 Fin-Ray 构型族，共用当前 Robotiq 三孔接口与底座。",
        generator="fin-ray-profile",
        default_template="Fin-Ray 默认",
        genes=GENES,
        groups=GROUPS,
        seed={
            "kind": "procedural",
            "body": None,
            "base": "public/底座-original.stl",
        },
    ),
    ConstructionFamily(
        family_id="arc_wrap",
        title="弧面包覆",
        description="原创宽面薄身实体构型，以连续弧槽和圆钝止挡增强对圆物的包覆。",
        generator="arc-wrap-solid",
        default_template="弧面包覆",
        genes=ARC_WRAP_GENES,
        groups=ARC_WRAP_GROUPS,
        seed={
            "kind": "procedural",
            "body": None,
            "base": "public/底座-original.stl",
        },
    ),
    ConstructionFamily(
        family_id="precision_tip",
        title="精密尖指",
        description="原创紧凑实心楔形构型，以窄尖和局部平直接触段面向精密捏取。",
        generator="precision-wedge-solid",
        default_template="精密尖指",
        genes=PRECISION_TIP_GENES,
        groups=PRECISION_TIP_GROUPS,
        seed={
            "kind": "procedural",
            "body": None,
            "base": "public/底座-original.stl",
        },
    ),
])


def public_schema() -> dict:
    return {
        "lang": "zh-CN",
        "genes": GENES,
        "groups": GROUPS,
        "gene_sets": FAMILY_REGISTRY.gene_sets(),
        "group_sets": FAMILY_REGISTRY.group_sets(),
        "interface_genes": INTERFACE_GENES,
        "interface_groups": INTERFACE_GROUPS,
        "interface_default": INTERFACE_DEFAULT,
        "families": FAMILY_REGISTRY.public_catalog(),
        # 兼容早期网页；新客户端应读取 families。
        "categories": [
            {"key": family.family_id, "title": family.title, "default_template": family.default_template}
            for family in FAMILY_REGISTRY.values()
        ],
        "templates": TEMPLATES,
        "default_template": "原始夹爪",
        "roles": {"symmetric": "手指", "pair": ["a", "b"], "labels": {"a": "手指 A", "b": "手指 B"}},
        "geometry": {
            "method": "registered-construction-families",
            "generators": {
                family.family_id: family.generator for family in FAMILY_REGISTRY.values()
            },
            "mount_lock_y_mm": 55.0,
            "root_thickness_mm": 26.0,
            "material": "TPU 95A",
            "density_g_cm3": 1.21,
            "interface_coordinate_system": {
                "plane": "XY",
                "hole_axis": "Z",
                "fixed_hole_center_mm": [4.9641008377075195, 15.0],
                "pair_formula": "x=fixed_x+single_to_pair_span_mm; y=[fixed_y,fixed_y+pair_hole_pitch_mm]",
            },
        },
    }
