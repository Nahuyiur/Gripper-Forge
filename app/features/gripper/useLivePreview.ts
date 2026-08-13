"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { decodeLivePreviewBundle } from "../../lib/live-preview";
import { GEOMETRY_API } from "./config";
import { cloneDesign } from "./design";
import type { Design, LivePreviewRequest, PreviewPart } from "./types";

export function useLivePreview(design: Design | null, pairId: string | null, editable: boolean) {
  const [previewUrls, setPreviewUrls] = useState<Partial<Record<PreviewPart, string>>>({});
  const [previewRevision, setPreviewRevision] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const previewUrlsRef = useRef<Partial<Record<PreviewPart, string>>>({});
  const livePreviewPending = useRef<LivePreviewRequest | null>(null);
  const livePreviewRunning = useRef(false);
  const livePreviewAlive = useRef(true);

  const revokePreviewUrls = useCallback(() => {
    Object.values(previewUrlsRef.current).forEach((url) => URL.revokeObjectURL(url));
    previewUrlsRef.current = {};
  }, []);

  const pumpLivePreview = useCallback(async () => {
    if (livePreviewRunning.current) return;
    livePreviewRunning.current = true;
    try {
      while (livePreviewPending.current && livePreviewAlive.current) {
        const request = livePreviewPending.current;
        livePreviewPending.current = null;
        const response = await fetch(`${GEOMETRY_API}/api/preview-live`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ design: request.design, pair_id: request.pairId }),
        });
        if (!response.ok) throw new Error("几何服务没有返回实时 STL");
        const parts = decodeLivePreviewBundle(await response.arrayBuffer());
        if (!livePreviewAlive.current) return;
        const nextUrls: Record<PreviewPart, string> = {
          body: URL.createObjectURL(new Blob([parts.body], { type: "model/stl" })),
          base: URL.createObjectURL(new Blob([parts.base], { type: "model/stl" })),
        };
        revokePreviewUrls();
        previewUrlsRef.current = nextUrls;
        setPreviewUrls(nextUrls);
        setPreviewRevision((current) => current + 1);
        setError(null);
      }
    } catch {
      if (livePreviewAlive.current) setError("实时 STL 暂时无法同步更新");
    } finally {
      livePreviewRunning.current = false;
    }
  }, [revokePreviewUrls]);

  useEffect(() => {
    if (!design) return;
    if (!editable) {
      livePreviewPending.current = null;
      const timer = window.setTimeout(() => {
        revokePreviewUrls();
        setPreviewUrls({});
      }, 0);
      return () => window.clearTimeout(timer);
    }
    livePreviewPending.current = { design: cloneDesign(design), pairId };
    void pumpLivePreview();
  }, [design, editable, pairId, pumpLivePreview, revokePreviewUrls]);

  useEffect(() => {
    livePreviewAlive.current = true;
    return () => {
      livePreviewAlive.current = false;
      livePreviewPending.current = null;
      revokePreviewUrls();
    };
  }, [revokePreviewUrls]);

  return { previewUrls, previewRevision, error };
}
