import { GripperDesigner } from "./components/GripperDesigner";

export const metadata = {
  title: "夹爪设计器",
  description: "基于真实 STL 模板的参数化夹爪手指设计、检查和导出工具。",
};

export default function Home() {
  return <GripperDesigner />;
}
