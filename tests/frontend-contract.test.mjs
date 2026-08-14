import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const designer = readFileSync(new URL("../app/components/GripperDesigner.tsx", import.meta.url), "utf8");
const config = readFileSync(new URL("../app/features/gripper/config.ts", import.meta.url), "utf8");
const viewer = readFileSync(new URL("../app/features/gripper/GripperViewer.tsx", import.meta.url), "utf8");
const previewStage = readFileSync(new URL("../app/features/gripper/PreviewStage.tsx", import.meta.url), "utf8");
const resultPanel = readFileSync(new URL("../app/features/gripper/ResultPanel.tsx", import.meta.url), "utf8");
const livePreview = readFileSync(new URL("../app/features/gripper/useLivePreview.ts", import.meta.url), "utf8");
const api = readFileSync(new URL("../app/features/gripper/api.ts", import.meta.url), "utf8");
const designState = readFileSync(new URL("../app/lib/design-state.ts", import.meta.url), "utf8");
const page = [designer, config, viewer, previewStage, resultPanel, livePreview, api, designState].join("\n");
const layout = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

test("网页使用中文并已移除临时预览内容", () => {
  assert.match(layout, /lang="zh-CN"/);
  assert.match(page, /夹爪设计器/);
  assert.match(page, /原始 STL 基准/);
  assert.match(page, /主体／底座接口同步适配/);
  assert.doesNotMatch(page + layout, /codex-preview|SkeletonPreview/);
});

test("交互和导出能力完整存在", () => {
  for (const text of ["左右对称", "STL 实时重建", "生成 STL", "实体检查", "下载当前预览主体 STL", "仅主体", "仅底座", "主体＋底座", "主体／底座接口同步适配", "选择主体 STL", "选择底座 STL", "检查并导入这一对模型", "Robotiq 平面孔型", "基本构型", "构型预设", "全实心", "仅尖端伪 Fin-Ray", "仅后段伪 Fin-Ray", "尖端＋后段"]) {
    assert.match(page, new RegExp(text));
  }
  for (const endpoint of ["/api/schema", "/api/check", "/api/preview-live", "/api/build", "/api/job", "/api/stl", "/api/package", "/api/import-pair", "/api/imported"]) {
    assert.match(page, new RegExp(endpoint.replaceAll("/", "\\/")));
  }
  assert.match(resultPanel, /href=\{bodyUrl\}/);
  assert.match(resultPanel, /href=\{baseUrl\}/);
});

test("依赖型控件会自动启用配套几何，不会出现拖动无效果", () => {
  assert.match(page, /applyFamilyGeneChange/);
  assert.match(page, /next\.parameterized = true/);
  assert.doesNotMatch(page, /setTemplateName\("Fin-Ray 默认"\)/);
  assert.match(page, /designCache/);
  assert.match(page, /gene_sets/);
  assert.match(page, /group_sets/);
  assert.match(page, /latestDesign/);
  assert.match(page, /rt\[key\] = geometry/);
  assert.match(page, /cameraState/);
  assert.match(page, /loadRuntimeGeometry/);
  assert.match(page, /while \(livePreviewPending\.current/);
  assert.match(page, /decodeLivePreviewBundle/);
  assert.doesNotMatch(page, /\}, 180\)/);
  assert.doesNotMatch(page, /\[resetView, bodyUrl, mountUrl, baseUrl\]/);
});

test("构型注册表驱动界面，并隔离各构型的缓存和参数联动", () => {
  assert.match(page, /schema\.families\.map/);
  assert.match(page, /familyIdOf/);
  assert.match(page, /selectedTemplateByFamily/);
  assert.match(page, /family\?\.generator/);
  assert.match(page, /generator === "fin-ray-profile"/);
  assert.doesNotMatch(page, /const finrayTemplate/);
  assert.match(page, /familyTitle/);
  assert.doesNotMatch(page, /Fin-Ray 参数化区域/);
});

test("三孔接口只有两个共享参数，并由真实后端同步预览三类零件", () => {
  const interfaceSpecs = config.slice(config.indexOf("const INTERFACE_CONTROLS"));
  assert.equal([...interfaceSpecs.matchAll(/\n\s+name: /g)].length, 2);
  for (const text of ["三孔接口适配 · 主体／底座共享", "可与所有基本构型及其参数组合", "双孔中心距", "单孔至双孔轴线距离", "同侧底座竖直外沿和主体根部自动跟随", "固定单孔与 Robotiq 连接孔不动", "三孔始终保持直角布局"]) {
    assert.match(page, new RegExp(text));
  }
  assert.match(page, /pair_hole_pitch_mm/);
  assert.match(page, /single_to_pair_span_mm/);
  assert.match(interfaceSpecs, /min: 20,\n\s+max: 35,\n\s+step: 0\.5/);
  assert.match(interfaceSpecs, /min: 20,\n\s+max: 30\.0718,\n\s+step: 0\.5/);
  assert.match(page, /next\.interface =/);
  assert.doesNotMatch(page, /Object\.keys\(designCache\.current\)/);
  assert.match(designer, /withInterface\(received\.templates\[family\.default_template\]\.design\)/);
  assert.match(designer, /withInterface\(designCache\.current\[familyId\] \|\| fallback\)/);
  assert.match(page, /\/api\/preview-live/);
  assert.match(page, /data-live-revision/);
  assert.match(page, /setInterfaceGene\(name, Number\(element\.value\)\)/);
  assert.match(page, /interfaceEditingAllowed = editingAllowed && !pairId/);
  assert.match(page, /导入模型对缺少可靠的孔位语义，暂不开放这两个参数/);
  assert.match(page, /固定单孔／Robotiq 侧面孔/);
  assert.match(page, /三孔直角约束/);
  assert.doesNotMatch(page, /fingerGroup\.add\(mountMesh\)/);
  assert.doesNotMatch(page, /next\[editing\].*pair_hole_pitch_mm/);
});

test("参数化构型低频参数默认折叠，原始夹爪参数保持直接可见", () => {
  for (const text of ["详细参数", "项低频设置，按需展开", "parameter-cluster", "finray-parameter-cluster", "source-parameter-cluster"]) {
    assert.match(page + css, new RegExp(text));
  }
  assert.match(page, /open=\{activeFamilyId === "source" \? true : undefined\}/);
  assert.match(page, /Object\.keys\(activeGeneSpecs\)\.length/);
  assert.match(css, /finray-parameter-cluster\[open\]/);
});

test("桌面和移动布局均有明确规则", () => {
  assert.match(css, /grid-template-columns: 330px minmax\(0, 1fr\) 320px/);
  assert.match(css, /@media \(max-width: 860px\)/);
  assert.match(css, /position: sticky/);
});
