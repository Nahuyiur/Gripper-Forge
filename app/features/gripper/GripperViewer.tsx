"use client";

import { useCallback, useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { safePreviewGap } from "../../lib/finray-preview";
import type { Design, DisplayMode } from "./types";

const FINGER_COLORS = [0xff5e57, 0x00b9b6];

type Runtime = {
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  renderer: THREE.WebGLRenderer;
  controls: OrbitControls;
  group: THREE.Group;
  source: THREE.BufferGeometry;
  mountSource: THREE.BufferGeometry;
  baseSource: THREE.BufferGeometry;
  observer: ResizeObserver;
};

type ViewerProps = {
  design: Design;
  viewRequest: string;
  displayMode: DisplayMode;
  bodyUrl: string;
  mountUrl: string;
  baseUrl: string;
  previewRevision: number;
};

function disposeGeometry(source?: THREE.BufferGeometry) {
  source?.dispose();
}

function renderDesign(rt: Pick<Runtime, "group" | "source" | "mountSource" | "baseSource">, design: Design, displayMode: DisplayMode) {
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
      color: FINGER_COLORS[index],
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
      fingerGroup.add(new THREE.Mesh(rt.baseSource.clone(), baseMaterial));
    }
    fingerGroup.position.x = index === 0 ? gap / 2 : -gap / 2;
    if (index === 1) fingerGroup.scale.x = -1;
    rt.group.add(fingerGroup);
  });
}

export function GripperViewer({
  design,
  viewRequest,
  displayMode,
  bodyUrl,
  mountUrl,
  baseUrl,
  previewRevision,
}: ViewerProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const currentView = useRef(viewRequest);
  const latestDesign = useRef(design);
  const latestDisplayMode = useRef(displayMode);
  const runtime = useRef<Runtime | null>(null);

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
      host.dataset.cameraState = [...camera.position.toArray(), ...controls.target.toArray()]
        .map((value) => value.toFixed(5))
        .join(",");
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
      group.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.geometry.dispose();
          (object.material as THREE.Material).dispose();
        }
      });
      disposeGeometry(runtime.current?.source);
      disposeGeometry(runtime.current?.mountSource);
      disposeGeometry(runtime.current?.baseSource);
      runtime.current = null;
      if (renderer.domElement.parentNode === host) host.removeChild(renderer.domElement);
    };
  }, [resetView]);

  useEffect(() => {
    latestDesign.current = design;
    latestDisplayMode.current = displayMode;
    if (runtime.current) renderDesign(runtime.current, design, displayMode);
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
      disposeGeometry(rt[key]);
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

  return <div className="viewer" ref={hostRef} aria-label="夹爪三维预览" data-live-revision={previewRevision} />;
}
