"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { applyGeneChange } from "../lib/design-state";
import { safePreviewGap } from "../lib/finray-preview";
import { decodeLivePreviewBundle } from "../lib/live-preview";

type GeneValue = number;
type Genes = Record<string, GeneValue>;
type InterfaceDesign = {
  pair_hole_pitch_mm: number;
  single_to_pair_span_mm: number;
};
type Design = {
  mode?: "source" | "finray";
  parameterized?: boolean;
  symmetric: boolean;
  interface: InterfaceDesign;
  a: Genes;
  b: Genes;
};

type GeneSpec = {
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

type Template = { title: string; category: "source" | "finray"; blurb: string; design: Design };
type Schema = {
  genes: Record<string, GeneSpec>;
  groups: Array<{ key: string; title: string }>;
  gene_sets: Record<"source" | "finray", Record<string, GeneSpec>>;
  group_sets: Record<"source" | "finray", Array<{ key: string; title: string }>>;
  categories: Array<{ key: "source" | "finray"; title: string; default_template: string }>;
  templates: Record<string, Template>;
  default_template: string;
  roles: { labels: Record<string, string> };
};

type FingerReport = {
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

type Report = {
  mode?: "source" | "finray";
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

type JobState = { state: "running" | "done" | "failed"; report?: Report; error?: string };

type ImportReport = {
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

const API = process.env.NEXT_PUBLIC_GEOMETRY_API || "http://localhost:8787";
const COLORS = [0xff5e57, 0x00b9b6];
const DEFAULT_INTERFACE: InterfaceDesign = {
  pair_hole_pitch_mm: 35,
  single_to_pair_span_mm: 30.0718,
};
const INTERFACE_CONTROLS: Array<{ name: keyof InterfaceDesign; spec: GeneSpec }> = [
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

function cloneDesign(design: Design): Design {
  return JSON.parse(JSON.stringify(design)) as Design;
}

function withInterface(design: Omit<Design, "interface"> & { interface?: Partial<InterfaceDesign> }, shared?: InterfaceDesign): Design {
  return {
    ...cloneDesign(design as Design),
    interface: { ...DEFAULT_INTERFACE, ...design.interface, ...shared },
  };
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`无法读取 ${file.name}`));
    reader.onload = () => {
      const result = String(reader.result || "");
      resolve(result.includes(",") ? result.split(",", 2)[1] : result);
    };
    reader.readAsDataURL(file);
  });
}

type DisplayMode = "body" | "base" | "both";
type PreviewPart = "body" | "base";
type LivePreviewRequest = { design: Design; pairId: string | null };

function Viewer({
  design,
  viewRequest,
  displayMode,
  bodyUrl,
  mountUrl,
  baseUrl,
  previewRevision,
}: {
  design: Design;
  viewRequest: string;
  displayMode: DisplayMode;
  bodyUrl: string;
  mountUrl: string;
  baseUrl: string;
  previewRevision: number;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const currentView = useRef(viewRequest);
  const latestDesign = useRef(design);
  const latestDisplayMode = useRef(displayMode);
  const runtime = useRef<{
    scene: THREE.Scene;
    camera: THREE.PerspectiveCamera;
    renderer: THREE.WebGLRenderer;
    controls: OrbitControls;
    group: THREE.Group;
    source: THREE.BufferGeometry;
    mountSource: THREE.BufferGeometry;
    baseSource: THREE.BufferGeometry;
    observer: ResizeObserver;
  } | null>(null);

  const resetView = useCallback((view: string) => {
    const rt = runtime.current;
    if (!rt) return;
    const target = new THREE.Vector3(0, 78, -13);
    const positions: Record<string, THREE.Vector3> = {
      iso: new THREE.Vector3(190, -145, 155),
      front: new THREE.Vector3(0, 82, 255),
      side: new THREE.Vector3(255, 82, -13),
      top: new THREE.Vector3(0, 285, -13),
    };
    rt.camera.position.copy(positions[view] || positions.iso);
    rt.camera.up.set(0, 1, 0);
    if (view === "top") rt.camera.up.set(0, 0, -1);
    rt.controls.target.copy(target);
    rt.controls.update();
  }, []);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let animation = 0;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf7f8f8);
    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 2000);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 80;
    controls.maxDistance = 600;
    const writeCameraState = () => {
      host.dataset.cameraState = [
        ...camera.position.toArray(),
        ...controls.target.toArray(),
      ].map((value) => value.toFixed(5)).join(",");
    };
    controls.addEventListener("change", writeCameraState);
    const group = new THREE.Group();
    scene.add(group);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x9ba4a6, 2.2));
    const key = new THREE.DirectionalLight(0xffffff, 3.2);
    key.position.set(130, -80, 190);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xc9ffff, 1.6);
    fill.position.set(-160, 180, 70);
    scene.add(fill);

    const observer = new ResizeObserver(() => {
      const { width, height } = host.getBoundingClientRect();
      if (!width || !height) return;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    });
    observer.observe(host);
    runtime.current = {
      scene,
      camera,
      renderer,
      controls,
      group,
      source: new THREE.BufferGeometry(),
      mountSource: new THREE.BufferGeometry(),
      baseSource: new THREE.BufferGeometry(),
      observer,
    };
    resetView(currentView.current);
    writeCameraState();

    const animate = () => {
      controls.update();
      renderer.render(scene, camera);
      animation = requestAnimationFrame(animate);
    };
    animate();

    const doubleClick = () => resetView("iso");
    renderer.domElement.addEventListener("dblclick", doubleClick);
    return () => {
      cancelAnimationFrame(animation);
      observer.disconnect();
      renderer.domElement.removeEventListener("dblclick", doubleClick);
      controls.removeEventListener("change", writeCameraState);
      controls.dispose();
      renderer.dispose();
      group.traverse((obj) => {
        if (obj instanceof THREE.Mesh) {
          obj.geometry.dispose();
          (obj.material as THREE.Material).dispose();
        }
      });
      sourceCleanup(runtime.current?.source);
      sourceCleanup(runtime.current?.mountSource);
      sourceCleanup(runtime.current?.baseSource);
      runtime.current = null;
      if (renderer.domElement.parentNode === host) host.removeChild(renderer.domElement);
    };
  }, [resetView]);

  useEffect(() => {
    latestDesign.current = design;
    latestDisplayMode.current = displayMode;
    const rt = runtime.current;
    if (rt) renderDesign(rt, design, displayMode);
  }, [design, displayMode]);

  const loadRuntimeGeometry = useCallback((url: string, key: "source" | "mountSource" | "baseSource") => {
    let cancelled = false;
    const loader = new STLLoader();
    loader.loadAsync(url).then((geometry) => {
      const rt = runtime.current;
      if (cancelled || !rt) {
        geometry.dispose();
        return;
      }
      geometry.computeVertexNormals();
      sourceCleanup(rt[key]);
      rt[key] = geometry;
      renderDesign(rt, latestDesign.current, latestDisplayMode.current);
    }).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => loadRuntimeGeometry(bodyUrl, "source"), [bodyUrl, loadRuntimeGeometry]);
  useEffect(() => loadRuntimeGeometry(mountUrl, "mountSource"), [mountUrl, loadRuntimeGeometry]);
  useEffect(() => loadRuntimeGeometry(baseUrl, "baseSource"), [baseUrl, loadRuntimeGeometry]);

  useEffect(() => {
    currentView.current = viewRequest;
    resetView(viewRequest);
  }, [resetView, viewRequest]);

  return (
    <div
      className="viewer"
      ref={hostRef}
      aria-label="夹爪三维预览"
      data-live-revision={previewRevision}
    />
  );
}

function sourceCleanup(source?: THREE.BufferGeometry) {
  source?.dispose();
}

function renderDesign(
  rt: {
    group: THREE.Group;
    source: THREE.BufferGeometry;
    mountSource: THREE.BufferGeometry;
    baseSource: THREE.BufferGeometry;
  },
  design: Design,
  displayMode: DisplayMode,
) {
  while (rt.group.children.length) {
    const child = rt.group.children.pop();
    child?.traverse((object) => {
      if (object instanceof THREE.Mesh) {
        object.geometry.dispose();
        (object.material as THREE.Material).dispose();
      }
    });
  }
  const gap = safePreviewGap();
  [design.a, design.symmetric ? design.a : design.b].forEach((_, index) => {
    const fingerGroup = new THREE.Group();
    const material = new THREE.MeshStandardMaterial({
      color: COLORS[index],
      roughness: 0.72,
      metalness: 0.02,
      side: THREE.DoubleSide,
    });
    if (displayMode !== "base") {
      const bodyMesh = new THREE.Mesh(rt.source.clone(), material);
      bodyMesh.userData.kind = design.mode === "source" ? "原始主体" : "Fin-Ray 参数化主体";
      fingerGroup.add(bodyMesh);
    }

    if (displayMode !== "body") {
      const baseMaterial = new THREE.MeshStandardMaterial({ color: 0xaeb6b8, roughness: 0.88, metalness: 0.01 });
      const baseMesh = new THREE.Mesh(rt.baseSource.clone(), baseMaterial);
      fingerGroup.add(baseMesh);
    }

    fingerGroup.position.x = index === 0 ? gap / 2 : -gap / 2;
    if (index === 1) fingerGroup.scale.x = -1;
    rt.group.add(fingerGroup);
  });
}

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, options);
  const json = await response.json().catch(() => ({})) as { detail?: string };
  if (!response.ok) throw new Error(json.detail || "几何服务暂时不可用");
  return json as T;
}

function format(value: number, digits = 0) {
  return Number(value).toFixed(digits);
}

export function GripperDesigner() {
  const [schema, setSchema] = useState<Schema | null>(null);
  const [templateName, setTemplateName] = useState("");
  const [design, setDesign] = useState<Design | null>(null);
  const designCache = useRef<Partial<Record<"source" | "finray", Design>>>({});
  const finrayTemplate = useRef("Fin-Ray 默认");
  const [editing, setEditing] = useState<"a" | "b">("a");
  const [report, setReport] = useState<Report | null>(null);
  const [status, setStatus] = useState("正在连接几何服务…");
  const [statusType, setStatusType] = useState<"" | "busy" | "bad">("busy");
  const [building, setBuilding] = useState(false);
  const [job, setJob] = useState<string | null>(null);
  const [view, setView] = useState("iso");
  const [displayMode, setDisplayMode] = useState<DisplayMode>("both");
  const [editedModes, setEditedModes] = useState<Record<"source" | "finray", boolean>>({ source: false, finray: false });
  const [previewUrls, setPreviewUrls] = useState<Partial<Record<PreviewPart, string>>>({});
  const [previewRevision, setPreviewRevision] = useState(0);
  const previewUrlsRef = useRef<Partial<Record<PreviewPart, string>>>({});
  const livePreviewPending = useRef<LivePreviewRequest | null>(null);
  const livePreviewRunning = useRef(false);
  const livePreviewAlive = useRef(true);
  const [pairId, setPairId] = useState<string | null>(null);
  const [pairReport, setPairReport] = useState<ImportReport | null>(null);
  const [bodyFile, setBodyFile] = useState<File | null>(null);
  const [baseFile, setBaseFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);

  useEffect(() => {
    api<{ schema: Schema }>("/api/schema")
      .then(({ schema: received }) => {
        const initialName = received.default_template;
        setSchema(received);
        setTemplateName(initialName);
        const initialDesign = withInterface(received.templates[initialName].design);
        const finrayDesign = withInterface(received.templates["Fin-Ray 默认"].design, initialDesign.interface);
        designCache.current = {
          source: initialDesign,
          finray: finrayDesign,
        };
        setDesign(initialDesign);
        setStatus("");
        setStatusType("");
      })
      .catch((error: Error) => {
        setStatus(`无法连接几何服务：${error.message}`);
        setStatusType("bad");
      });
  }, []);

  const pumpLivePreview = useCallback(async () => {
    if (livePreviewRunning.current) return;
    livePreviewRunning.current = true;
    try {
      while (livePreviewPending.current && livePreviewAlive.current) {
        const request = livePreviewPending.current;
        livePreviewPending.current = null;
        const response = await fetch(`${API}/api/preview-live`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ design: request.design, pair_id: request.pairId }),
        });
        if (!response.ok) throw new Error("几何服务没有返回实时 STL");
        const parts = decodeLivePreviewBundle(await response.arrayBuffer());
        if (!livePreviewAlive.current) return;
        const nextUrls: Record<PreviewPart, string> = {
          body: URL.createObjectURL(new Blob([parts.body], { type: "model/stl" })),
          base: URL.createObjectURL(new Blob([parts.base], { type: "model/stl" })),
        };
        Object.values(previewUrlsRef.current).forEach((url) => URL.revokeObjectURL(url));
        previewUrlsRef.current = nextUrls;
        setPreviewUrls(nextUrls);
        setPreviewRevision((current) => current + 1);
      }
    } catch {
      if (livePreviewAlive.current) {
        setStatus("实时 STL 暂时无法同步更新");
        setStatusType("bad");
      }
    } finally {
      livePreviewRunning.current = false;
    }
  }, []);

  useEffect(() => {
    if (!design) return;
    if (pairReport && !pairReport.editable) {
      livePreviewPending.current = null;
      const timer = window.setTimeout(() => {
        Object.values(previewUrlsRef.current).forEach((url) => URL.revokeObjectURL(url));
        previewUrlsRef.current = {};
        setPreviewUrls({});
      }, 0);
      return () => window.clearTimeout(timer);
    }
    livePreviewPending.current = { design: cloneDesign(design), pairId };
    void pumpLivePreview();
  }, [design, pairId, pairReport, pumpLivePreview]);

  useEffect(() => {
    livePreviewAlive.current = true;
    return () => {
      livePreviewAlive.current = false;
      livePreviewPending.current = null;
      Object.values(previewUrlsRef.current).forEach((url) => URL.revokeObjectURL(url));
    };
  }, []);

  useEffect(() => {
    if (!design) return;
    if (pairReport && !pairReport.editable) {
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setStatus("正在检查实体…");
      setStatusType("busy");
      api<{ report: Report }>("/api/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ design, pair_id: pairId }),
        signal: controller.signal,
      })
        .then(({ report: checked }) => {
          setReport(checked);
          setStatus("");
          setStatusType("");
        })
        .catch((error: Error) => {
          if (error.name === "AbortError") return;
          setStatus(error.message);
          setStatusType("bad");
        });
    }, 420);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [design, pairId, pairReport]);

  const activeMode = design?.mode === "finray" ? "finray" : "source";
  const activeGeneSpecs = schema?.gene_sets?.[activeMode] || schema?.genes || {};
  const activeGroups = schema?.group_sets?.[activeMode] || schema?.groups || [];
  const genes = design?.[editing];
  const editingAllowed = pairReport?.editable !== false;
  const interfaceEditingAllowed = editingAllowed && !pairId;
  const originalBodyUrl = pairId ? `${API}/api/imported?pair_id=${encodeURIComponent(pairId)}&part=body` : "/zhuti-2-0813-original.stl";
  const bodyUrl = previewUrls.body || originalBodyUrl;
  const mountUrl = pairId ? `${API}/api/imported?pair_id=${encodeURIComponent(pairId)}&part=mount` : `${API}/api/mount`;
  const baseUrl = previewUrls.base || (pairId ? `${API}/api/imported?pair_id=${encodeURIComponent(pairId)}&part=base` : "/底座-original.stl");

  const applyTemplate = (name: string) => {
    if (!schema || !design) return;
    const next = withInterface(schema.templates[name].design, design.interface);
    const mode = next.mode === "source" ? "source" : "finray";
    designCache.current[mode] = next;
    if (mode === "finray") finrayTemplate.current = name;
    setTemplateName(name);
    setDesign(next);
    setJob(null);
    setEditing("a");
    setEditedModes((current) => ({ ...current, [mode]: false }));
  };

  const applyCategory = (mode: "source" | "finray") => {
    if (!schema || !design) return;
    const currentMode = design.mode === "source" ? "source" : "finray";
    designCache.current[currentMode] = cloneDesign(design);
    const fallback = schema.templates[mode === "source" ? "原始夹爪" : "Fin-Ray 默认"].design;
    const next = withInterface(designCache.current[mode] || fallback, design.interface);
    setTemplateName(mode === "source" ? "原始夹爪" : finrayTemplate.current);
    setDesign(next);
    setJob(null);
    setEditing("a");
  };

  const setGene = (name: string, value: number) => {
    if (!design || !editingAllowed) return;
    const next = cloneDesign(design);
    if (next.mode === "source") {
      next.parameterized = true;
    }
    next[editing] = next.mode === "source"
      ? { ...next[editing], [name]: value }
      : applyGeneChange(next[editing], name, value);
    if (next.symmetric) next.b = { ...next.a };
    const mode = next.mode === "source" ? "source" : "finray";
    designCache.current[mode] = cloneDesign(next);
    setDesign(next);
    setJob(null);
    setEditedModes((current) => ({ ...current, [mode]: true }));
  };

  const setInterfaceGene = (name: keyof InterfaceDesign, value: number) => {
    if (!design || !interfaceEditingAllowed) return;
    const next = cloneDesign(design);
    next.parameterized = true;
    next.interface = { ...next.interface, [name]: value };
    (["source", "finray"] as const).forEach((mode) => {
      const cached = designCache.current[mode];
      if (cached) designCache.current[mode] = withInterface(cached, next.interface);
    });
    const mode = next.mode === "source" ? "source" : "finray";
    designCache.current[mode] = cloneDesign(next);
    setDesign(next);
    setJob(null);
    setEditedModes((current) => ({ ...current, [mode]: true }));
  };

  const applySourceStructure = (kind: "solid" | "tip" | "body" | "both") => {
    if (!design || design.mode !== "source") return;
    const next = cloneDesign(design);
    next.parameterized = true;
    const tip = kind === "tip" || kind === "both" ? 65 : 0;
    const body = kind === "body" || kind === "both" ? 65 : 0;
    next.a = { ...next.a, source_tip_hollow_pct: tip, source_body_hollow_pct: body };
    if (next.symmetric) next.b = { ...next.a };
    designCache.current.source = cloneDesign(next);
    setDesign(next);
    setJob(null);
    setEditedModes((current) => ({ ...current, source: true }));
  };

  const restoreDefaultPair = () => {
    if (!schema) return;
    setPairId(null);
    setPairReport(null);
    setBodyFile(null);
    setBaseFile(null);
    setTemplateName(schema.default_template);
    const sourceDefault = withInterface(schema.templates[schema.default_template].design);
    designCache.current = {
      source: sourceDefault,
      finray: withInterface(schema.templates["Fin-Ray 默认"].design, sourceDefault.interface),
    };
    finrayTemplate.current = "Fin-Ray 默认";
    setDesign(sourceDefault);
    setEditedModes({ source: false, finray: false });
    setStatus("已恢复当前默认主体和 Robotiq 转接底座");
    setStatusType("");
    window.setTimeout(() => setStatus(""), 1800);
  };

  const importModelPair = async () => {
    if (!bodyFile || !baseFile || importing) return;
    setImporting(true);
    setStatus("正在检查主体、底座和 Robotiq 平面孔型…");
    setStatusType("busy");
    try {
      const [bodyBase64, baseBase64] = await Promise.all([fileToBase64(bodyFile), fileToBase64(baseFile)]);
      const result = await api<{ pair_id: string; report: ImportReport }>("/api/import-pair", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          body_name: bodyFile.name,
          body_base64: bodyBase64,
          base_name: baseFile.name,
          base_base64: baseBase64,
        }),
      });
      setPairId(result.pair_id);
      setPairReport(result.report);
      setJob(null);
      if (!result.report.editable) setReport(null);
      setDisplayMode("both");
      setStatus(result.report.editable ? "导入成功，接口匹配并可参数化编辑" : "已导入用于检查，但接口或坐标基准未通过");
      setStatusType(result.report.editable ? "" : "bad");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "导入失败");
      setStatusType("bad");
    } finally {
      setImporting(false);
    }
  };

  const setSymmetric = (symmetric: boolean) => {
    if (!design) return;
    const next = cloneDesign(design);
    next.symmetric = symmetric;
    if (symmetric) next.b = { ...next.a };
    const mode = next.mode === "source" ? "source" : "finray";
    designCache.current[mode] = cloneDesign(next);
    setDesign(next);
    setJob(null);
    setEditing("a");
    setEditedModes((current) => ({ ...current, [mode]: true }));
  };

  const build = async () => {
    if (!design || building) return;
    setBuilding(true);
    setStatus("正在生成可下载的 STL…");
    setStatusType("busy");
    try {
      const started = await api<{ job: string }>("/api/build", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ design, pair_id: pairId }),
      });
      let state: JobState = { state: "running" };
      while (state.state === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 260));
        state = await api<JobState>(`/api/job?job=${encodeURIComponent(started.job)}`);
      }
      if (state.state === "failed") throw new Error(state.error || "STL 生成失败");
      setReport(state.report || report);
      setJob(started.job);
      setStatus("STL 已生成");
      setStatusType("");
      window.setTimeout(() => setStatus(""), 1800);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "STL 生成失败");
      setStatusType("bad");
    } finally {
      setBuilding(false);
    }
  };

  const downloadRoles = useMemo(() => {
    if (!report) return [];
    return Object.keys(report.fingers);
  }, [report]);

  if (!schema || !design || !genes) {
    return (
      <main className="loading-screen">
        <div className="loading-mark" />
        <h1>夹爪设计器</h1>
        <p className={statusType === "bad" ? "loading-error" : ""}>{status}</p>
        {statusType === "bad" && <button onClick={() => window.location.reload()}>重新连接</button>}
      </main>
    );
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">夹爪设计器</div>
        <div className="tagline">默认加载当前主体与 Robotiq 转接底座</div>
        <span className="lock-pill">主体／底座接口同步适配</span>
        <div className="spacer" />
        <div className={`status ${statusType}`}>{status}</div>
      </header>

      <main className="workspace">
        <aside className="panel controls-panel">
          <section className="block">
            <h2>夹爪大类</h2>
            <div className="template-list template-categories">
              {schema.categories.map((category) => (
                <button
                  key={category.key}
                  className={`template-chip category-chip ${activeMode === category.key ? "on" : ""} ${activeMode === category.key && editedModes[category.key] ? "edited" : ""}`}
                  onClick={() => applyCategory(category.key)}
                >
                  {category.title}
                </button>
              ))}
            </div>
            {activeMode === "finray" && (
              <div className="template-subtypes">
                <span>Fin-Ray 小类</span>
                <div className="template-list">
                  {Object.entries(schema.templates)
                    .filter(([name, template]) => template.category === "finray" && name !== "Fin-Ray 默认")
                    .map(([name, template]) => (
                      <button
                        key={name}
                        className={`template-chip subtype-chip ${name === templateName ? "on" : ""}`}
                        onClick={() => applyTemplate(name)}
                      >
                        {template.title}
                      </button>
                    ))}
                </div>
              </div>
            )}
            <p className="template-blurb">{schema.templates[templateName].blurb}</p>
            {activeMode === "source" && (
              <div className="source-structure-presets">
                <span>原始夹爪内部结构</span>
                <div>
                  <button onClick={() => applySourceStructure("solid")}>全实心</button>
                  <button onClick={() => applySourceStructure("tip")}>仅尖端伪 Fin-Ray</button>
                  <button onClick={() => applySourceStructure("body")}>仅后段伪 Fin-Ray</button>
                  <button onClick={() => applySourceStructure("both")}>尖端＋后段</button>
                </div>
              </div>
            )}
          </section>

          <section className="block import-block">
            <div className="block-title-row">
              <h2>模型来源</h2>
              <button className="text-button" onClick={restoreDefaultPair} disabled={!pairId}>恢复默认</button>
            </div>
            <div className={`source-state ${pairId ? "imported" : "default"}`}>
              <b>{pairId ? "当前：导入模型对" : "当前：默认模型对"}</b>
              <span>{pairId ? `${bodyFile?.name} ＋ ${baseFile?.name}` : "zhuti-2-0813.stl ＋ 底座.stl"}</span>
            </div>
            <div className="file-pair">
              <label className={bodyFile ? "selected" : ""}>
                <span>① 选择主体 STL</span>
                <b>{bodyFile?.name || "未选择"}</b>
                <input type="file" accept=".stl,model/stl" aria-label="选择主体 STL" onChange={(event) => setBodyFile(event.target.files?.[0] || null)} />
              </label>
              <label className={baseFile ? "selected" : ""}>
                <span>② 选择底座 STL</span>
                <b>{baseFile?.name || "未选择"}</b>
                <input type="file" accept=".stl,model/stl" aria-label="选择底座 STL" onChange={(event) => setBaseFile(event.target.files?.[0] || null)} />
              </label>
            </div>
            <button className="import-button" onClick={importModelPair} disabled={!bodyFile || !baseFile || importing}>
              {importing ? "正在检查…" : "检查并导入这一对模型"}
            </button>
            <p className="import-help">必须同时选择主体和底座。检查三孔共轴、封闭实体，以及底座平面孔型是否保持 Robotiq 安装基准。</p>
            {pairReport && (
              <div className={`pair-check ${pairReport.editable ? "good" : "bad"}`}>
                <b>{pairReport.editable ? "接口匹配，可继续编辑" : "仅供检查，暂不可编辑"}</b>
                <span>主体孔 {pairReport.body_hole_count} 个 · 底座孔 {pairReport.base_hole_count} 个</span>
                <span>三孔轴最大偏差 {pairReport.axis_error_mm == null ? "无法计算" : `${pairReport.axis_error_mm.toFixed(4)} 毫米`}</span>
                <span>Robotiq 平面孔型偏差 {pairReport.robotiq_pattern_error_mm == null ? "无法计算" : `${pairReport.robotiq_pattern_error_mm.toFixed(4)} 毫米`}</span>
                {pairReport.problems.map((problem) => <em key={problem}>{problem}</em>)}
              </div>
            )}
          </section>

          <section className="block gene-group interface-controls" aria-labelledby="three-hole-interface-title">
            <h2 id="three-hole-interface-title">三孔接口适配 · 主体／底座共享</h2>
            <p className="interface-contract">
              可与所有原始主体和 Fin-Ray 参数组合。双孔移动时，同侧底座竖直外沿和主体根部自动跟随；固定单孔与 Robotiq 连接孔不动，三孔始终保持直角布局。
              {pairId && <strong>导入模型对缺少可靠的孔位语义，暂不开放这两个参数。</strong>}
            </p>
            {INTERFACE_CONTROLS.map(({ name, spec }) => {
              const value = design.interface[name];
              const percentage = ((value - spec.min) / (spec.max - spec.min)) * 100;
              const commitRange = (element: HTMLInputElement) => setInterfaceGene(name, Number(element.value));
              return (
                <label className="control" key={name}>
                  <span className="control-head">
                    <span className="control-icon interface-control-icon" aria-hidden="true" />
                    <span>{spec.label}</span>
                    <span className="control-value">
                      <input
                        aria-label={`${spec.label}数值`}
                        type="number"
                        min={spec.min}
                        max={spec.max}
                        step={spec.step}
                        value={Number(value.toFixed(4))}
                        disabled={!interfaceEditingAllowed}
                        onChange={(event) => commitRange(event.currentTarget)}
                      />
                      <small>{spec.unit}</small>
                    </span>
                  </span>
                  <input
                    aria-label={spec.label}
                    type="range"
                    min={spec.min}
                    max={spec.max}
                    step={spec.step}
                    value={value}
                    disabled={!interfaceEditingAllowed}
                    style={{ "--fill": `${percentage}%` } as React.CSSProperties}
                    onInput={(event) => commitRange(event.currentTarget)}
                    onChange={(event) => commitRange(event.currentTarget)}
                    onPointerUp={(event) => commitRange(event.currentTarget)}
                    onKeyUp={(event) => commitRange(event.currentTarget)}
                  />
                  <span className="control-blurb">{spec.blurb}</span>
                </label>
              );
            })}
          </section>

          <section className="block symmetry-block">
            <label className="switch-row">
              <input type="checkbox" checked={design.symmetric} onChange={(event) => setSymmetric(event.target.checked)} />
              <span className="switch-track"><span className="switch-knob" /></span>
              <b>左右对称</b>
            </label>
            {!design.symmetric && (
              <div className="finger-tabs">
                {(["a", "b"] as const).map((role, index) => (
                  <button key={role} className={editing === role ? "on" : ""} onClick={() => setEditing(role)}>
                    <span className={`finger-dot dot-${index}`} />手指 {role.toUpperCase()}
                  </button>
                ))}
              </div>
            )}
          </section>

          <details
            className={`parameter-cluster ${activeMode === "finray" ? "finray-parameter-cluster" : "source-parameter-cluster"}`}
            open={activeMode === "source" ? true : undefined}
            key={activeMode}
          >
            {activeMode === "finray" && (
              <summary>
                <span>
                  <b>Fin-Ray 详细参数</b>
                  <small>{Object.keys(activeGeneSpecs).length} 项低频设置，按需展开</small>
                </span>
                <em aria-hidden="true" />
              </summary>
            )}
            <div className="parameter-groups">
              {activeGroups.map((group) => {
                const entries = Object.entries(activeGeneSpecs).filter(([, spec]) => spec.group === group.key);
                return (
                  <section className="block gene-group" key={group.key}>
                <h2>{group.title}</h2>
                {entries.map(([name, spec]) => {
                  const value = genes[name];
                  const percentage = ((value - spec.min) / (spec.max - spec.min)) * 100;
                  const commitRange = (element: HTMLInputElement) => {
                    const nextValue = Number(element.value);
                    setGene(name, spec.int ? Math.round(nextValue) : nextValue);
                  };
                  if (spec.boolean) {
                    return (
                      <label className="control boolean-control" key={name}>
                        <span className="control-head">
                          <span className="control-icon" aria-hidden="true" />
                          <span>{spec.label}</span>
                          <input
                            aria-label={spec.label}
                            type="checkbox"
                            checked={Boolean(value)}
                            disabled={!editingAllowed}
                            onChange={(event) => setGene(name, event.currentTarget.checked ? 1 : 0)}
                          />
                        </span>
                        {spec.blurb && <span className="control-blurb">{spec.blurb}</span>}
                      </label>
                    );
                  }
                  return (
                    <label className="control" key={name}>
                      <span className="control-head">
                        <span className="control-icon" aria-hidden="true" />
                        <span>{spec.label}</span>
                        <span className="control-value">
                          <input
                            aria-label={`${spec.label}数值`}
                            type="number"
                            min={spec.min}
                            max={spec.max}
                            step={spec.step}
                            value={spec.int ? Math.round(value) : value}
                            disabled={!editingAllowed}
                            onChange={(event) => commitRange(event.currentTarget)}
                          />
                          <small>{spec.unit}</small>
                        </span>
                      </span>
                      <input
                        aria-label={spec.label}
                        type="range"
                        min={spec.min}
                        max={spec.max}
                        step={spec.step}
                        value={value}
                        disabled={!editingAllowed}
                        style={{ "--fill": `${percentage}%` } as React.CSSProperties}
                        onInput={(event) => commitRange(event.currentTarget)}
                        onChange={(event) => commitRange(event.currentTarget)}
                        onPointerUp={(event) => commitRange(event.currentTarget)}
                        onKeyUp={(event) => commitRange(event.currentTarget)}
                      />
                      {spec.blurb && <span className="control-blurb">{spec.blurb}</span>}
                    </label>
                  );
                })}
                  </section>
                );
              })}
            </div>
          </details>
        </aside>

        <section className="stage">
          <div className="stagebar">
            <span className="preview-pill">STL 实时重建</span>
            <span className="stage-note">三孔直角关系固定，主体、安装区与底座同步预览</span>
            <div className="spacer" />
            <div className="object-tabs" aria-label="零件显示模式">
              {[
                { id: "body", text: "仅主体" },
                { id: "base", text: "仅底座" },
                { id: "both", text: "主体＋底座" },
              ].map((item) => (
                <button
                  key={item.id}
                  className={displayMode === item.id ? "on" : ""}
                  aria-pressed={displayMode === item.id}
                  onClick={() => setDisplayMode(item.id as DisplayMode)}
                >{item.text}</button>
              ))}
            </div>
            <div className="view-tabs">
              {[{ id: "iso", text: "默认" }, { id: "front", text: "正视" }, { id: "side", text: "侧视" }, { id: "top", text: "顶视" }].map((item) => (
                <button key={item.id} className={view === item.id ? "on" : ""} onClick={() => setView(item.id)}>{item.text}</button>
              ))}
            </div>
          </div>
          <div className="canvas-wrap">
            <Viewer
              design={design}
              viewRequest={view}
              displayMode={displayMode}
              bodyUrl={bodyUrl}
              mountUrl={mountUrl}
              baseUrl={baseUrl}
              previewRevision={previewRevision}
            />
            <div className="interface-badge">
              <b>{displayMode === "body" ? "仅主体" : displayMode === "base" ? "仅底座" : "主体＋底座"}</b>
              <span>{displayMode === "both" ? "三螺丝连接关系可见" : "切换到主体＋底座检查连接"}</span>
            </div>
            <div className="viewer-hint">拖动旋转 · 滚轮缩放 · 双击复位</div>
            <div className="axis-note"><span /> {
              design.mode === "source"
                ? design.parameterized ? "原始夹爪 · 已参数化修改" : "原始 STL 基准"
                : "Fin-Ray 参数化区域"
            }</div>
          </div>
        </section>

        <aside className="panel result-panel">
          {!report ? (
            <div className="report-skeleton">
              <i /><i /><i /><b /><em />
            </div>
          ) : (
            <>
              <section className="facts">
                <div><dt>有效开口</dt><dd>{format(report.pair.opening_mm)} 毫米</dd></div>
                <div><dt>最长伸出</dt><dd>{format(report.pair.reach_mm)} 毫米</dd></div>
                <div><dt>预计材料</dt><dd>{format(report.pair.plastic_g)} 克</dd></div>
                <div><dt>预览双指间距</dt><dd>{format(report.pair.preview_gap_mm ?? safePreviewGap())} 毫米</dd></div>
              </section>

              <section className={`verdict ${report.ready ? "good" : "bad"}`}>
                <b><span className="verdict-icon">{report.ready ? "✓" : "!"}</span>{report.ready ? "通过全部几何检查" : `${report.problems.length} 项问题需要修复`}</b>
                {!report.ready && <ul>{report.problems.map((problem) => <li key={problem}>{problem}</li>)}</ul>}
              </section>

              <section className="validation-grid">
                <h3>实体检查</h3>
                <div><span>封闭实体</span><b className={Object.values(report.fingers).every((f) => f.watertight) ? "pass" : "fail"}>{Object.values(report.fingers).every((f) => f.watertight) ? "通过" : "失败"}</b></div>
                <div><span>三角面方向</span><b className={Object.values(report.fingers).every((f) => f.winding_consistent) ? "pass" : "fail"}>{Object.values(report.fingers).every((f) => f.winding_consistent) ? "通过" : "失败"}</b></div>
                <div><span>安装区域漂移</span><b className={Object.values(report.fingers).every((f) => f.mount_error_mm === 0) ? "pass" : "fail"}>{Math.max(...Object.values(report.fingers).map((f) => f.mount_error_mm)).toFixed(6)} 毫米</b></div>
                <div><span>退化三角面</span><b className={Object.values(report.fingers).every((f) => f.degenerate_faces === 0) ? "pass" : "fail"}>{Object.values(report.fingers).reduce((sum, f) => sum + f.degenerate_faces, 0)} 个</b></div>
                <div><span>单一实体</span><b className={Object.values(report.fingers).every((f) => (f.body_count ?? 1) === 1) ? "pass" : "fail"}>{Object.values(report.fingers).every((f) => (f.body_count ?? 1) === 1) ? "通过" : "失败"}</b></div>
                <div><span>双指最小净距</span><b className={(report.pair.preview_clearance_mm ?? 0) >= 5 ? "pass" : "fail"}>{(report.pair.preview_clearance_mm ?? 0).toFixed(1)} 毫米</b></div>
                <div><span>连接螺丝数量</span><b className="pass">{report.interface?.fastener_count ?? 3} 颗</b></div>
                <div><span>固定单孔／Robotiq 侧面孔</span><b className={report.interface?.base_coupled !== false ? "pass" : "fail"}>{report.interface?.base_coupled !== false ? "基准保持" : "基准漂移"}</b></div>
                <div><span>三孔直角约束</span><b className={report.interface?.base_coupled !== false ? "pass" : "fail"}>{report.interface?.base_coupled !== false ? "主体底座同步" : "必须重新同步"}</b></div>
                <div><span>主体／底座接口</span><b className={report.interface?.base_coupled !== false ? "pass" : "fail"}>{report.interface?.base_coupled !== false ? "位置一致" : "必须同步调整"}</b></div>
              </section>

              {job && (
                <section className="files">
                  <h3>文件</h3>
                  {downloadRoles.map((role) => (
                    <a className="download-row" key={role} href={`${API}/api/stl?job=${encodeURIComponent(job)}&role=${role}`} download>
                      <span className="download-icon">↓</span>
                      <span>{report.fingers[role].stl}</span>
                      <em>{format(report.fingers[role].plastic_g)} 克{report.symmetric ? " × 2" : ""}</em>
                    </a>
                  ))}
                  <a className="download-row package" href={`${API}/api/package?job=${encodeURIComponent(job)}`} download>
                    <span className="download-icon">↓</span><span>全部文件包</span><em>ZIP</em>
                  </a>
                </section>
              )}

              <section className="action-block">
                <button className="build-button" onClick={build} disabled={building || !report.ready}>
                  {building ? "正在生成…" : job ? "重新生成 STL" : "生成 STL"}
                </button>
                <a className="original-link" href={pairId ? bodyUrl : `${API}/api/original`} download>下载当前主体原始 STL</a>
                <a className="original-link" href={pairId ? baseUrl : `${API}/api/base`} download>下载当前配套底座 STL</a>
              </section>

              {report.notes.length > 0 && <section className="notes">{report.notes.map((note) => <p key={note}>{note}</p>)}</section>}

              <section className="howto">
                <h3>打印与验证</h3>
                <div className="step"><b>1 · 手指</b><p>建议先使用 TPU 95A 打印单只，层高不高于 0.2 毫米。</p></div>
                <div className="step"><b>2 · 三孔接口</b><p>固定单孔不移动，双孔中心距与横向轴距可调；三孔保持直角，主体与底座必须同步生成并重新检查。</p></div>
                <div className="step"><b>3 · Robotiq 安装面</b><p>Robotiq 侧面孔保持原始基准，导入模型不具备可靠孔位语义时不开放接口调节。</p></div>
                <div className="step"><b>4 · 双指测试</b><p>低速闭合，检查左右干涉、目标物滑移和材料疲劳后再上机器人。</p></div>
              </section>
            </>
          )}
        </aside>
      </main>
    </div>
  );
}
