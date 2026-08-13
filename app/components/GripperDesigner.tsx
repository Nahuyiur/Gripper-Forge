"use client";

import { useEffect, useRef, useState } from "react";
import { applyGeneChange } from "../lib/design-state";
import { fileToBase64, geometryApi } from "../features/gripper/api";
import { GEOMETRY_API, INTERFACE_CONTROLS } from "../features/gripper/config";
import { cloneDesign, withInterface } from "../features/gripper/design";
import { PreviewStage } from "../features/gripper/PreviewStage";
import { ResultPanel } from "../features/gripper/ResultPanel";
import { useLivePreview } from "../features/gripper/useLivePreview";
import type {
  Design,
  DisplayMode,
  ImportReport,
  InterfaceDesign,
  JobState,
  Report,
  Schema,
} from "../features/gripper/types";

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
  const [pairId, setPairId] = useState<string | null>(null);
  const [pairReport, setPairReport] = useState<ImportReport | null>(null);
  const [bodyFile, setBodyFile] = useState<File | null>(null);
  const [baseFile, setBaseFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const { previewUrls, previewRevision, error: livePreviewError } = useLivePreview(
    design,
    pairId,
    pairReport?.editable !== false,
  );

  useEffect(() => {
    geometryApi<{ schema: Schema }>("/api/schema")
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

  useEffect(() => {
    if (!design) return;
    if (pairReport && !pairReport.editable) {
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setStatus("正在检查实体…");
      setStatusType("busy");
      geometryApi<{ report: Report }>("/api/check", {
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
  const originalBodyUrl = pairId ? `${GEOMETRY_API}/api/imported?pair_id=${encodeURIComponent(pairId)}&part=body` : "/zhuti-2-0813-original.stl";
  const bodyUrl = previewUrls.body || originalBodyUrl;
  const mountUrl = pairId ? `${GEOMETRY_API}/api/imported?pair_id=${encodeURIComponent(pairId)}&part=mount` : `${GEOMETRY_API}/api/mount`;
  const baseUrl = previewUrls.base || (pairId ? `${GEOMETRY_API}/api/imported?pair_id=${encodeURIComponent(pairId)}&part=base` : "/底座-original.stl");
  const visibleStatus = livePreviewError || status;
  const visibleStatusType = livePreviewError ? "bad" : statusType;

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
      const result = await geometryApi<{ pair_id: string; report: ImportReport }>("/api/import-pair", {
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
      const started = await geometryApi<{ job: string }>("/api/build", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ design, pair_id: pairId }),
      });
      let state: JobState = { state: "running" };
      while (state.state === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 260));
        state = await geometryApi<JobState>(`/api/job?job=${encodeURIComponent(started.job)}`);
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

  if (!schema || !design || !genes) {
    return (
      <main className="loading-screen">
        <div className="loading-mark" />
        <h1>夹爪设计器</h1>
        <p className={visibleStatusType === "bad" ? "loading-error" : ""}>{visibleStatus}</p>
        {visibleStatusType === "bad" && <button onClick={() => window.location.reload()}>重新连接</button>}
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
        <div className={`status ${visibleStatusType}`}>{visibleStatus}</div>
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

        <PreviewStage
          design={design}
          view={view}
          onViewChange={setView}
          displayMode={displayMode}
          onDisplayModeChange={setDisplayMode}
          bodyUrl={bodyUrl}
          mountUrl={mountUrl}
          baseUrl={baseUrl}
          previewRevision={previewRevision}
        />
        <ResultPanel
          report={report}
          job={job}
          building={building}
          onBuild={build}
          pairId={pairId}
          bodyUrl={bodyUrl}
          baseUrl={baseUrl}
        />
      </main>
    </div>
  );
}
