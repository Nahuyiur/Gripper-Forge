import * as THREE from "three";

export type PreviewGenes = Record<string, number>;
type Point2 = [number, number];

const LOCK_Y = 55;
const ROOT_THICKNESS = 26;
const Z_CENTER = -13;
const MOUNT_OVERLAP = 1;

function smoothstep(t: number) {
  const x = Math.max(0, Math.min(1, t));
  return x * x * (3 - 2 * x);
}

function orientation(a: Point2, b: Point2, c: Point2) {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
}

function segmentsCross(a: Point2, b: Point2, c: Point2, d: Point2) {
  const abC = orientation(a, b, c);
  const abD = orientation(a, b, d);
  const cdA = orientation(c, d, a);
  const cdB = orientation(c, d, b);
  return abC * abD < -1e-8 && cdA * cdB < -1e-8;
}

function pointInside(point: Point2, polygon: Point2[]) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    const a = polygon[i];
    const b = polygon[j];
    if ((a[1] > point[1]) !== (b[1] > point[1])
      && point[0] < (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
  }
  return inside;
}

function polygonsOverlap(first: Point2[], second: Point2[]) {
  for (let i = 0; i < first.length; i += 1) {
    const a = first[i];
    const b = first[(i + 1) % first.length];
    for (let j = 0; j < second.length; j += 1) {
      if (segmentsCross(a, b, second[j], second[(j + 1) % second.length])) return true;
    }
  }
  return pointInside(first[0], second) || pointInside(second[0], first);
}

export function backX(u: number, length: number) {
  const t = Math.max(0, Math.min(1, u / Math.max(length, 0.001)));
  return Math.max(0.85, -4.49156786 * t ** 3 - 9.03816625 * t ** 2 - 7.22250935 * t + 21.6232136);
}

const REFERENCE_CONTACT_EDGES = [
  1.3, 3.623, 6.075, 8.676, 11.447, 14.409, 17.588, 21.011,
  24.706, 28.709, 33.058, 37.794, 42.967, 48.63, 53.571,
];
const REFERENCE_BACK_EDGES = [
  1.3, 3.623, 6.084, 9.482, 13.033, 16.785, 20.624, 24.481,
  28.612, 32.725, 36.905, 41.041, 45.384, 49.858, 54.25,
];

export function cavityEdge(index: number, count: number, length: number, side: "contact" | "back" = "contact") {
  const p = index / Math.max(Math.round(count), 1);
  const reference = side === "back" ? REFERENCE_BACK_EDGES : REFERENCE_CONTACT_EDGES;
  const scaled = p * (reference.length - 1);
  const lower = Math.max(0, Math.min(reference.length - 1, Math.floor(scaled)));
  const upper = Math.max(0, Math.min(reference.length - 1, Math.ceil(scaled)));
  const mix = scaled - lower;
  return length / 56.8 * (reference[lower] * (1 - mix) + reference[upper] * mix);
}

export function contactX(u: number, genes: PreviewGenes) {
  const length = genes.finger_length_mm;
  let x = 0;
  const count = Math.round(genes.grip_count);
  if (count > 0 && genes.grip_height_mm > 0) {
    const halfWidth = Math.max(0.65, Math.min(1.8, length * 0.21 / count));
    for (let index = 0; index < count; index += 1) {
      const center = count === 1 ? length * 0.63 : length * (0.42 + 0.42 * index / (count - 1));
      const q = Math.abs(u - center) / halfWidth;
      if (q < 1) {
        const peak = genes.grip_round ? 0.5 * (1 + Math.cos(Math.PI * q)) : 1;
        x = Math.min(x, -genes.grip_height_mm * peak);
      }
    }
  }
  if (genes.cradle_radius_mm > 0 && genes.cradle_depth_mm > 0) {
    const center = length * genes.cradle_pos;
    const halfSpan = Math.min(genes.cradle_radius_mm * 0.72, length * 0.28);
    const q = (u - center) / Math.max(halfSpan, 0.001);
    if (Math.abs(q) < 1) x = Math.max(x, genes.cradle_depth_mm * Math.sqrt(Math.max(0, 1 - q * q)));
  }
  const lipStart = length - 14.4 * length / 56.8;
  const lipStop = length - 6.3 * length / 56.8;
  if (genes.tip_lip_mm > 0 && u > lipStart && u < lipStop) {
    const q = Math.max(0, Math.min(1, (u - lipStart) / Math.max(lipStop - lipStart, 0.001)));
    x = Math.min(x, -genes.tip_lip_mm * Math.sin(Math.PI * q) ** 2);
  }
  const minimumWeb = Math.max(0.8, genes.wall_thickness_mm * 0.55);
  x = Math.min(x, backX(u, length) - minimumWeb);
  return x;
}

export function buildFinRayGeometry(genes: PreviewGenes) {
  const length = genes.finger_length_mm;
  const shape = new THREE.Shape();
  const samples = Math.max(100, Math.round(length * 2));
  for (let index = 0; index < samples; index += 1) {
    const u = -MOUNT_OVERLAP + (length + MOUNT_OVERLAP) * index / (samples - 1);
    const x = contactX(u, genes);
    if (index === 0) shape.moveTo(u, x);
    else shape.lineTo(u, x);
  }
  if (genes.nail_len_mm > 0) {
    const tip = contactX(length, genes);
    shape.lineTo(length + genes.nail_len_mm, tip);
    shape.lineTo(length + genes.nail_len_mm, tip + genes.nail_thickness_mm);
    shape.lineTo(length, tip + genes.nail_thickness_mm);
  }
  for (let index = samples - 1; index >= 0; index -= 1) {
    const u = -MOUNT_OVERLAP + (length + MOUNT_OVERLAP) * index / (samples - 1);
    shape.lineTo(u, backX(u, length));
  }
  shape.closePath();

  const count = Math.round(genes.rib_count);
  const acceptedHoles: Point2[][] = [];
  for (let index = 0; index < count; index += 1) {
    const c0 = cavityEdge(index, count, length);
    const c1 = cavityEdge(index + 1, count, length) - genes.rib_thickness_mm;
    if (c1 <= c0 + 0.4) continue;
    const b0 = cavityEdge(index, count, length, "back");
    const b1 = cavityEdge(index + 1, count, length, "back") - genes.rib_thickness_mm;
    if (b1 <= b0 + 0.4) continue;
    const c0x = contactX(c0, genes) + genes.wall_thickness_mm;
    const c1x = contactX(c1, genes) + genes.wall_thickness_mm;
    const b0x = backX(b0, length) - genes.wall_thickness_mm;
    const b1x = backX(b1, length) - genes.wall_thickness_mm;
    const safelyInside = [
      [c0, c0x], [c1, c1x], [b0, b0x], [b1, b1x],
    ].every(([u, x]) => x > contactX(u, genes) + 0.05 && x < backX(u, length) - 0.05);
    if (!safelyInside) continue;
    const points: Point2[] = [[c0, c0x], [b0, b0x], [b1, b1x], [c1, c1x]];
    const selfCrossing = segmentsCross(points[0], points[1], points[2], points[3])
      || segmentsCross(points[1], points[2], points[3], points[0]);
    if (selfCrossing || acceptedHoles.some((other) => polygonsOverlap(points, other))) continue;
    acceptedHoles.push(points);
    const hole = new THREE.Path();
    hole.moveTo(points[0][0], points[0][1]);
    points.slice(1).forEach(([u, x]) => hole.lineTo(u, x));
    hole.closePath();
    shape.holes.push(hole);
  }

  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth: ROOT_THICKNESS,
    bevelEnabled: false,
    steps: 1,
    curveSegments: 4,
  });
  const positions = geometry.getAttribute("position") as THREE.BufferAttribute;
  for (let index = 0; index < positions.count; index += 1) {
    const u = positions.getX(index);
    const profileX = positions.getY(index);
    const localZ = positions.getZ(index);
    const t = smoothstep(Math.max(0, Math.min(1, u / length)));
    let factor = 1 + (genes.tip_thickness_mm / ROOT_THICKNESS - 1) * t;
    factor *= 0.985 + 0.015 * smoothstep(Math.max(0, Math.min(1, (u + MOUNT_OVERLAP) / 4)));
    positions.setXYZ(index, profileX, LOCK_Y + u, Z_CENTER + (localZ - ROOT_THICKNESS / 2) * factor);
  }
  positions.needsUpdate = true;
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  return geometry;
}

export function previewGeometrySignature(genes: PreviewGenes) {
  const geometry = buildFinRayGeometry(genes);
  const positions = geometry.getAttribute("position") as THREE.BufferAttribute;
  let weighted = 0;
  let finite = true;
  for (let index = 0; index < positions.count; index += 1) {
    const x = positions.getX(index);
    const y = positions.getY(index);
    const z = positions.getZ(index);
    finite &&= Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z);
    weighted += (index + 1) * (x * 0.17 + y * 0.31 + z * 0.53);
  }
  const signature = {
    finite,
    vertices: positions.count,
    min: geometry.boundingBox?.min.toArray() ?? [],
    max: geometry.boundingBox?.max.toArray() ?? [],
    weighted: Number(weighted.toFixed(5)),
  };
  geometry.dispose();
  return signature;
}

export function safePreviewGap() {
  return 28;
}
