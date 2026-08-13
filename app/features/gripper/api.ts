import { GEOMETRY_API } from "./config";

export async function geometryApi<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${GEOMETRY_API}${path}`, options);
  const json = await response.json().catch(() => ({})) as { detail?: string };
  if (!response.ok) throw new Error(json.detail || "几何服务暂时不可用");
  return json as T;
}

export function fileToBase64(file: File): Promise<string> {
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
