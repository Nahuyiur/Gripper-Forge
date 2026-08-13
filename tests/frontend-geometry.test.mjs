import assert from "node:assert/strict";
import test from "node:test";

import { applyGeneChange } from "../app/lib/design-state.ts";
import { buildFinRayGeometry, previewGeometrySignature } from "../app/lib/finray-preview.ts";
import { decodeLivePreviewBundle } from "../app/lib/live-preview.ts";

const DEFAULT = {
  finger_length_mm: 57,
  tip_thickness_mm: 12,
  tip_lip_mm: 2,
  wall_thickness_mm: 1.6,
  rib_count: 14,
  rib_thickness_mm: 1.3,
  cradle_radius_mm: 0,
  cradle_pos: 0.62,
  cradle_depth_mm: 0,
  grip_count: 0,
  grip_height_mm: 0,
  grip_round: 1,
  nail_len_mm: 0,
  nail_thickness_mm: 1.2,
};

const SPECS = {
  finger_length_mm: [45, 105, 0.5],
  tip_thickness_mm: [12, 30, 0.5],
  tip_lip_mm: [0, 6, 0.25],
  wall_thickness_mm: [1.2, 4, 0.1],
  rib_count: [4, 18, 1],
  rib_thickness_mm: [0.8, 3, 0.1],
  cradle_radius_mm: [0, 30, 0.5],
  cradle_pos: [0.15, 0.85, 0.01],
  cradle_depth_mm: [0, 7, 0.25],
  grip_count: [0, 14, 1],
  grip_height_mm: [0, 2, 0.1],
  grip_round: [0, 1, 1],
  nail_len_mm: [0, 14, 0.5],
  nail_thickness_mm: [0.6, 4, 0.1],
};

const ACTIVE = {
  cradle_radius_mm: { cradle_depth_mm: 3 },
  cradle_pos: { cradle_radius_mm: 18, cradle_depth_mm: 3 },
  cradle_depth_mm: { cradle_radius_mm: 18 },
  grip_count: { grip_height_mm: 0.9 },
  grip_height_mm: { grip_count: 7 },
  grip_round: { grip_count: 7, grip_height_mm: 0.9 },
  nail_thickness_mm: { nail_len_mm: 9 },
};

function signature(genes) {
  const result = previewGeometrySignature(genes);
  assert.equal(result.finite, true);
  assert.ok(result.vertices > 0);
  assert.ok(result.min.every(Number.isFinite));
  assert.ok(result.max.every(Number.isFinite));
  return JSON.stringify(result);
}

function connectedComponents(genes) {
  const geometry = buildFinRayGeometry(genes);
  const values = geometry.getAttribute("position").array;
  const faceCount = values.length / 9;
  const parent = Array.from({ length: faceCount }, (_, index) => index);
  const firstFace = new Map();
  const root = (value) => {
    while (parent[value] !== value) {
      parent[value] = parent[parent[value]];
      value = parent[value];
    }
    return value;
  };
  for (let face = 0; face < faceCount; face += 1) {
    for (let vertex = 0; vertex < 3; vertex += 1) {
      const offset = face * 9 + vertex * 3;
      const key = [values[offset], values[offset + 1], values[offset + 2]]
        .map((value) => Math.round(value * 1e4))
        .join(",");
      const previous = firstFace.get(key);
      if (previous === undefined) {
        firstFace.set(key, face);
      } else {
        const a = root(face);
        const b = root(previous);
        if (a !== b) parent[b] = a;
      }
    }
  }
  const components = new Set(parent.map((_, index) => root(index))).size;
  geometry.dispose();
  return components;
}

test("全部 14 个控件都会改变浏览器预览几何", () => {
  for (const [name, [min, max]] of Object.entries(SPECS)) {
    const context = ACTIVE[name] || {};
    const low = signature({ ...DEFAULT, ...context, [name]: min });
    const high = signature({ ...DEFAULT, ...context, [name]: max });
    assert.notEqual(low, high, `${name} 调节后预览几何未变化`);
    assert.equal(connectedComponents({ ...DEFAULT, ...context, [name]: min }), 1);
    assert.equal(connectedComponents({ ...DEFAULT, ...context, [name]: max }), 1);
  }
});

test("浏览器预览覆盖全部参数极值和 160 组确定性组合", () => {
  const low = {};
  const high = {};
  for (const [name, [min, max]] of Object.entries(SPECS)) {
    low[name] = min;
    high[name] = max;
  }
  signature(low);
  signature(high);
  assert.equal(connectedComponents(low), 1);
  assert.equal(connectedComponents(high), 1);

  let state = 8132026;
  const random = () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 2 ** 32;
  };
  for (let sample = 0; sample < 160; sample += 1) {
    const genes = {};
    for (const [name, [min, max, step]] of Object.entries(SPECS)) {
      const steps = Math.round((max - min) / step);
      const index = Math.floor(random() * (steps + 1));
      genes[name] = min + index * step;
    }
    signature(genes);
    assert.equal(connectedComponents(genes), 1, `第 ${sample + 1} 组预览出现分离几何`);
  }
});

test("依赖型控件单独调整时会自动生成可见配套特征", () => {
  assert.equal(applyGeneChange(DEFAULT, "cradle_radius_mm", 20).cradle_depth_mm, 2.5);
  assert.equal(applyGeneChange(DEFAULT, "cradle_depth_mm", 4).cradle_radius_mm, 18);
  const positioned = applyGeneChange(DEFAULT, "cradle_pos", 0.7);
  assert.equal(positioned.cradle_radius_mm, 18);
  assert.equal(positioned.cradle_depth_mm, 2.5);
  const rounded = applyGeneChange(DEFAULT, "grip_round", 0);
  assert.equal(rounded.grip_count, 6);
  assert.equal(rounded.grip_height_mm, 0.8);
  assert.equal(applyGeneChange(DEFAULT, "nail_thickness_mm", 3).nail_len_mm, 8);
});

test("实时 STL 二进制包会严格拆分主体与底座", () => {
  const body = new Uint8Array([1, 2, 3, 4]);
  const base = new Uint8Array([5, 6, 7]);
  const buffer = new ArrayBuffer(12 + body.length + base.length);
  const bytes = new Uint8Array(buffer);
  bytes.set([71, 82, 73, 80], 0);
  const view = new DataView(buffer);
  view.setUint32(4, body.length, true);
  view.setUint32(8, base.length, true);
  bytes.set(body, 12);
  bytes.set(base, 12 + body.length);
  const decoded = decodeLivePreviewBundle(buffer);
  assert.deepEqual([...decoded.body], [...body]);
  assert.deepEqual([...decoded.base], [...base]);
});
