const HEADER_BYTES = 12;

export type LivePreviewParts = {
  body: Uint8Array;
  base: Uint8Array;
};

export function decodeLivePreviewBundle(buffer: ArrayBuffer): LivePreviewParts {
  if (buffer.byteLength < HEADER_BYTES) throw new Error("实时 STL 数据不完整");
  const bytes = new Uint8Array(buffer);
  if (String.fromCharCode(...bytes.slice(0, 4)) !== "GRIP") {
    throw new Error("实时 STL 数据格式无效");
  }
  const view = new DataView(buffer);
  const bodyLength = view.getUint32(4, true);
  const baseLength = view.getUint32(8, true);
  if (HEADER_BYTES + bodyLength + baseLength !== buffer.byteLength) {
    throw new Error("实时 STL 数据长度不匹配");
  }
  return {
    body: bytes.slice(HEADER_BYTES, HEADER_BYTES + bodyLength),
    base: bytes.slice(HEADER_BYTES + bodyLength),
  };
}
