import type { GeneSpec, InterfaceDesign } from "./types";

export const GEOMETRY_API = process.env.NEXT_PUBLIC_GEOMETRY_API || "http://localhost:8787";

export const DEFAULT_INTERFACE: InterfaceDesign = {
  pair_hole_pitch_mm: 35,
  single_to_pair_span_mm: 30.0718,
};

export const INTERFACE_CONTROLS: Array<{ name: keyof InterfaceDesign; spec: GeneSpec }> = [
  {
    name: "pair_hole_pitch_mm",
    spec: {
      min: 20,
      max: 35,
      step: 0.5,
      group: "three_hole_interface",
      label: "双孔中心距",
      unit: "毫米",
      blurb: "调节双孔纵向中心距；上侧底座边界和主体根部同步移动，固定单孔不动。",
    },
  },
  {
    name: "single_to_pair_span_mm",
    spec: {
      min: 20,
      max: 30.0718,
      step: 0.5,
      group: "three_hole_interface",
      label: "单孔至双孔轴线距离",
      unit: "毫米",
      blurb: "调节横向轴距；双孔侧底座外沿保持竖直并整体内收，主体根部同步跟随。",
    },
  },
];
