# Gripper Forge 架构说明

这份说明只描述模块边界。几何公式、默认 STL 与三孔接口不变量仍以自动化测试为最终准绳。

## 数据流

```text
参数控件
  └─ Design JSON
       ├─ /api/check ──────────────── 几何报告
       ├─ /api/preview-live ───────── 主体 STL + 底座 STL
       └─ /api/build ── 后台任务 ─── 手指 STL + 配套底座 ZIP
```

检查、实时预览和最终导出全部经过 `backend/service.py` 的同一条求值路径，避免“预览是一套几何、下载又是另一套几何”。

## 前端

| 模块 | 职责 |
|---|---|
| `app/components/GripperDesigner.tsx` | 页面级状态与业务编排，不直接管理 Three.js 场景 |
| `app/features/gripper/types.ts` | 设计、模板、报告和导入检查的数据契约 |
| `app/features/gripper/config.ts` | 几何服务地址与共享三孔控件定义 |
| `app/features/gripper/design.ts` | 设计复制、默认接口合并和显示格式 |
| `app/features/gripper/api.ts` | JSON API 与 STL 文件读取 |
| `app/features/gripper/useLivePreview.ts` | 连续拖动时的最新请求队列、Blob URL 生命周期 |
| `app/features/gripper/GripperViewer.tsx` | Three.js 场景、相机保持、STL 热替换 |
| `app/features/gripper/PreviewStage.tsx` | 零件显示模式与标准视角 |
| `app/features/gripper/ResultPanel.tsx` | 几何闸门、下载与打印提示 |

## 后端

| 模块 | 职责 |
|---|---|
| `backend/app.py` | HTTP 路由和响应格式 |
| `backend/contracts.py` | 请求数据模型 |
| `backend/storage.py` | 导入模型、构建任务与输出目录 |
| `backend/service.py` | 检查、预览、导出共用的设计求值服务 |
| `backend/builds.py` | 异步 STL 构建任务 |
| `backend/schema.py` | 参数范围、分组、默认值与模板 |
| `backend/model.py` | 几何领域内核：网格生成、接口联动和质量报告 |

## 修改原则

1. 新参数先加入 `backend/schema.py`，再实现真实网格变化，最后补参数极值与组合测试。
2. 三孔参数必须位于顶层 `design.interface`，不能放入左右手指各自的参数中。
3. 主体与底座必须由同一个 `Design` 求值；固定单孔与 Robotiq 连接特征不得漂移。
4. 前端预览只能展示后端返回的真实 STL，不能用视觉缩放冒充参数化结果。
5. 只有 `npm test` 全部通过的版本才进入稳定分支。
