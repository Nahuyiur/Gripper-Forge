import { GripperViewer } from "./GripperViewer";
import { familyIdOf } from "./design";
import type { Design, DisplayMode } from "./types";

type PreviewStageProps = {
  design: Design;
  familyTitle: string;
  view: string;
  onViewChange: (view: string) => void;
  displayMode: DisplayMode;
  onDisplayModeChange: (mode: DisplayMode) => void;
  bodyUrl: string;
  mountUrl: string;
  baseUrl: string;
  previewRevision: number;
};

const DISPLAY_MODES: Array<{ id: DisplayMode; text: string }> = [
  { id: "body", text: "仅主体" },
  { id: "base", text: "仅底座" },
  { id: "both", text: "主体＋底座" },
];

const VIEWS = [
  { id: "iso", text: "默认" },
  { id: "front", text: "正视" },
  { id: "side", text: "侧视" },
  { id: "top", text: "顶视" },
];

export function PreviewStage(props: PreviewStageProps) {
  const { design, familyTitle, view, onViewChange, displayMode, onDisplayModeChange, bodyUrl, mountUrl, baseUrl, previewRevision } = props;
  return (
    <section className="stage">
      <div className="stagebar">
        <span className="preview-pill">STL 实时重建</span>
        <span className="stage-note">三孔直角关系固定，主体、安装区与底座同步预览</span>
        <div className="spacer" />
        <div className="object-tabs" aria-label="零件显示模式">
          {DISPLAY_MODES.map((item) => (
            <button
              key={item.id}
              className={displayMode === item.id ? "on" : ""}
              aria-pressed={displayMode === item.id}
              onClick={() => onDisplayModeChange(item.id)}
            >{item.text}</button>
          ))}
        </div>
        <div className="view-tabs">
          {VIEWS.map((item) => (
            <button key={item.id} className={view === item.id ? "on" : ""} onClick={() => onViewChange(item.id)}>
              {item.text}
            </button>
          ))}
        </div>
      </div>
      <div className="canvas-wrap">
        <GripperViewer
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
          familyIdOf(design) === "source"
            ? design.parameterized ? "原始夹爪 · 已参数化修改" : "原始 STL 基准"
            : `${familyTitle} · 参数化主体`
        }</div>
      </div>
    </section>
  );
}
