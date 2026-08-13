export type GeneValue = number;
export type Genes = Record<string, GeneValue>;

export type InterfaceDesign = {
  pair_hole_pitch_mm: number;
  single_to_pair_span_mm: number;
};

export type DesignMode = "source" | "finray";

export type Design = {
  family_id?: string;
  /** 兼容旧设计文件；新数据使用 family_id。 */
  mode?: DesignMode;
  parameterized?: boolean;
  symmetric: boolean;
  interface: InterfaceDesign;
  a: Genes;
  b: Genes;
};

export type GeneSpec = {
  min: number;
  max: number;
  step: number;
  group: string;
  label: string;
  unit: string;
  blurb: string;
  int?: boolean;
  boolean?: boolean;
};

export type Template = {
  title: string;
  family_id: string;
  /** 兼容旧 schema。 */
  category?: DesignMode;
  blurb: string;
  design: Design;
};

export type ConstructionFamily = {
  id: string;
  title: string;
  description: string;
  generator: string;
  default_template: string;
  genes: Record<string, GeneSpec>;
  groups: Array<{ key: string; title: string }>;
  seed: { kind: "stl_pair" | "procedural"; body: string | null; base: string | null };
  version: number;
};

export type Schema = {
  genes: Record<string, GeneSpec>;
  groups: Array<{ key: string; title: string }>;
  gene_sets: Record<string, Record<string, GeneSpec>>;
  group_sets: Record<string, Array<{ key: string; title: string }>>;
  families: ConstructionFamily[];
  categories: Array<{ key: string; title: string; default_template: string }>;
  templates: Record<string, Template>;
  default_template: string;
  roles: { labels: Record<string, string> };
};

export type FingerReport = {
  role: string;
  label: string;
  reach_mm: number;
  volume_mm3: number;
  plastic_g: number;
  watertight: boolean;
  winding_consistent: boolean;
  size_mm: number[];
  mount_error_mm: number;
  degenerate_faces: number;
  body_count: number;
  contact_feature_count: number;
  problems: string[];
  notes: string[];
  genes: Genes;
  stl: string;
};

export type Report = {
  family_id?: string;
  mode?: string;
  parameterized?: boolean;
  symmetric: boolean;
  fingers: Record<string, FingerReport>;
  pair: {
    opening_mm: number;
    max_opening_mm: number;
    reach_mm: number;
    plastic_g: number;
    print_quantity: number;
    preview_gap_mm: number;
    preview_clearance_mm: number;
  };
  interface: {
    fastener_count: number;
    body_mount_error_mm: number;
    base_coupled: boolean;
    policy: string;
  };
  problems: string[];
  notes: string[];
  ready: boolean;
};

export type JobState = {
  state: "running" | "done" | "failed";
  report?: Report;
  error?: string;
};

export type ImportReport = {
  ready: boolean;
  editable: boolean;
  body_watertight: boolean;
  base_watertight: boolean;
  body_hole_count: number;
  base_hole_count: number;
  axis_error_mm: number | null;
  robotiq_pattern_error_mm: number | null;
  body_contract_error_mm: number | null;
  body_size_mm: number[];
  base_size_mm: number[];
  problems: string[];
  policy: string;
};

export type DisplayMode = "body" | "base" | "both";
export type PreviewPart = "body" | "base";
export type LivePreviewRequest = { design: Design; pairId: string | null };
