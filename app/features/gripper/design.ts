import { DEFAULT_INTERFACE } from "./config";
import type { Design, InterfaceDesign } from "./types";

export function cloneDesign(design: Design): Design {
  return structuredClone(design);
}

export function withInterface(
  design: Omit<Design, "interface"> & { interface?: Partial<InterfaceDesign> },
  shared?: InterfaceDesign,
): Design {
  return {
    ...cloneDesign(design as Design),
    interface: { ...DEFAULT_INTERFACE, ...design.interface, ...shared },
  };
}

export function formatMillimeter(value: number, digits = 0): string {
  return Number(value).toFixed(digits);
}
