import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "夹爪设计器",
  description: "基于 zhuti-2-0813.stl 的参数化夹爪手指设计器。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
