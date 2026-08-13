export type GeneValue = number;
export type Genes = Record<string, GeneValue>;

export type InterfaceDesign = {
  pair_hole_pitch_mm: number;
  single_to_pair_span_mm: number;
};

export type DesignMode = "source" | "finray";

export type Design = {
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
  category: DesignMode;
  blurb: string;
  design: Design;
};

export type Schema = {
  genes: Record<string, GeneSpec>;
  groups: Array<{ key: string; title: string }>;
  gene_sets: Record<DesignMode, Record<string, GeneSpec>>;
  group_sets: Record<DesignMode, Array<{ key: string; title: string }>>;
  categories: Array<{ key: DesignMode; title: string; default_template: string }>;
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
  mode?: DesignMode;
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
