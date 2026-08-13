export type GeneValues = Record<string, number>;

export function applyGeneChange(current: GeneValues, name: string, value: number): GeneValues {
  const next = { ...current, [name]: value };
  if (name === "grip_count" && value > 0 && next.grip_height_mm === 0) {
    next.grip_height_mm = 0.8;
  }
  if (name === "grip_height_mm" && value > 0 && next.grip_count === 0) {
    next.grip_count = 6;
  }
  if (name === "grip_round" && next.grip_count === 0) {
    next.grip_count = 6;
    next.grip_height_mm = 0.8;
  }
  if (name === "cradle_radius_mm" && value > 0 && next.cradle_depth_mm === 0) {
    next.cradle_depth_mm = 2.5;
  }
  if (name === "cradle_depth_mm" && value > 0 && next.cradle_radius_mm === 0) {
    next.cradle_radius_mm = 18;
  }
  if (name === "cradle_pos" && (next.cradle_radius_mm === 0 || next.cradle_depth_mm === 0)) {
    next.cradle_radius_mm = 18;
    next.cradle_depth_mm = 2.5;
  }
  if (name === "nail_thickness_mm" && next.nail_len_mm === 0) {
    next.nail_len_mm = 8;
  }
  return next;
}
