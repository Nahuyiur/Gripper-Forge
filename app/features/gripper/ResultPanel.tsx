import { safePreviewGap } from "../../lib/finray-preview";
import { GEOMETRY_API } from "./config";
import { formatMillimeter } from "./design";
import type { Report } from "./types";

type ResultPanelProps = {
  report: Report | null;
  job: string | null;
  building: boolean;
  onBuild: () => void;
  bodyUrl: string;
  baseUrl: string;
};

export function ResultPanel({ report, job, building, onBuild, bodyUrl, baseUrl }: ResultPanelProps) {
  if (!report) {
    return (
      <aside className="panel result-panel">
        <div className="report-skeleton"><i /><i /><i /><b /><em /></div>
      </aside>
    );
  }

  const fingers = Object.values(report.fingers);
  const downloadRoles = Object.keys(report.fingers);
  const baseCoupled = report.interface?.base_coupled !== false;
  return (
    <aside className="panel result-panel">
      <section className="facts">
        <div><dt>有效开口</dt><dd>{formatMillimeter(report.pair.opening_mm)} 毫米</dd></div>
        <div><dt>最长伸出</dt><dd>{formatMillimeter(report.pair.reach_mm)} 毫米</dd></div>
        <div><dt>预计材料</dt><dd>{formatMillimeter(report.pair.plastic_g)} 克</dd></div>
        <div><dt>预览双指间距</dt><dd>{formatMillimeter(report.pair.preview_gap_mm ?? safePreviewGap())} 毫米</dd></div>
      </section>

      <section className={`verdict ${report.ready ? "good" : "bad"}`}>
        <b><span className="verdict-icon">{report.ready ? "✓" : "!"}</span>{report.ready ? "通过全部几何检查" : `${report.problems.length} 项问题需要修复`}</b>
        {!report.ready && <ul>{report.problems.map((problem) => <li key={problem}>{problem}</li>)}</ul>}
      </section>

      <section className="validation-grid">
        <h3>实体检查</h3>
        <div><span>封闭实体</span><b className={fingers.every((finger) => finger.watertight) ? "pass" : "fail"}>{fingers.every((finger) => finger.watertight) ? "通过" : "失败"}</b></div>
        <div><span>三角面方向</span><b className={fingers.every((finger) => finger.winding_consistent) ? "pass" : "fail"}>{fingers.every((finger) => finger.winding_consistent) ? "通过" : "失败"}</b></div>
        <div><span>安装区域漂移</span><b className={fingers.every((finger) => finger.mount_error_mm === 0) ? "pass" : "fail"}>{Math.max(...fingers.map((finger) => finger.mount_error_mm)).toFixed(6)} 毫米</b></div>
        <div><span>退化三角面</span><b className={fingers.every((finger) => finger.degenerate_faces === 0) ? "pass" : "fail"}>{fingers.reduce((sum, finger) => sum + finger.degenerate_faces, 0)} 个</b></div>
        <div><span>单一实体</span><b className={fingers.every((finger) => (finger.body_count ?? 1) === 1) ? "pass" : "fail"}>{fingers.every((finger) => (finger.body_count ?? 1) === 1) ? "通过" : "失败"}</b></div>
        <div><span>双指最小净距</span><b className={(report.pair.preview_clearance_mm ?? 0) >= 5 ? "pass" : "fail"}>{(report.pair.preview_clearance_mm ?? 0).toFixed(1)} 毫米</b></div>
        <div><span>连接螺丝数量</span><b className="pass">{report.interface?.fastener_count ?? 3} 颗</b></div>
        <div><span>固定单孔／Robotiq 侧面孔</span><b className={baseCoupled ? "pass" : "fail"}>{baseCoupled ? "基准保持" : "基准漂移"}</b></div>
        <div><span>三孔直角约束</span><b className={baseCoupled ? "pass" : "fail"}>{baseCoupled ? "主体底座同步" : "必须重新同步"}</b></div>
        <div><span>主体／底座接口</span><b className={baseCoupled ? "pass" : "fail"}>{baseCoupled ? "位置一致" : "必须同步调整"}</b></div>
      </section>

      {job && (
        <section className="files">
          <h3>文件</h3>
          {downloadRoles.map((role) => (
            <a className="download-row" key={role} href={`${GEOMETRY_API}/api/stl?job=${encodeURIComponent(job)}&role=${role}`} download>
              <span className="download-icon">↓</span>
              <span>{report.fingers[role].stl}</span>
              <em>{formatMillimeter(report.fingers[role].plastic_g)} 克{report.symmetric ? " × 2" : ""}</em>
            </a>
          ))}
          <a className="download-row package" href={`${GEOMETRY_API}/api/package?job=${encodeURIComponent(job)}`} download>
            <span className="download-icon">↓</span><span>全部文件包</span><em>ZIP</em>
          </a>
        </section>
      )}

      <section className="action-block">
        <button className="build-button" onClick={onBuild} disabled={building || !report.ready}>
          {building ? "正在生成…" : job ? "重新生成 STL" : "生成 STL"}
        </button>
        <a className="original-link" href={bodyUrl} download>下载当前预览主体 STL</a>
        <a className="original-link" href={baseUrl} download>下载当前预览底座 STL</a>
      </section>

      {report.notes.length > 0 && <section className="notes">{report.notes.map((note) => <p key={note}>{note}</p>)}</section>}
      <section className="howto">
        <h3>打印与验证</h3>
        <div className="step"><b>1 · 手指</b><p>建议先使用 TPU 95A 打印单只，层高不高于 0.2 毫米。</p></div>
        <div className="step"><b>2 · 三孔接口</b><p>固定单孔不移动，双孔中心距与横向轴距可调；三孔保持直角，主体与底座必须同步生成并重新检查。</p></div>
        <div className="step"><b>3 · Robotiq 安装面</b><p>Robotiq 侧面孔保持原始基准，导入模型不具备可靠孔位语义时不开放接口调节。</p></div>
        <div className="step"><b>4 · 双指测试</b><p>低速闭合，检查左右干涉、目标物滑移和材料疲劳后再上机器人。</p></div>
      </section>
    </aside>
  );
}
