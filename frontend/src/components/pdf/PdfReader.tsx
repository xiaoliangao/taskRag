import {
  CompressOutlined,
  ExpandOutlined,
  MinusOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { App, Button, Tooltip } from "antd";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import type { PDFDocumentProxy } from "pdfjs-dist";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

import {
  type Annotation,
  type AnnotationKind,
  createAnnotation,
  deleteAnnotation,
  listAnnotations,
} from "../../api/annotations";
import { apiErrorMessage } from "../../api/client";
import AnnotationSidebar from "./AnnotationSidebar";
import SelectionToolbar from "./SelectionToolbar";

// Wire pdfjs worker through Vite. The `new URL(...)` form is Vite-native and
// produces a hashed worker bundle at build time without runtime CDN lookups.
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

interface Props {
  topicId: number;
  documentId: number;
  pdfUrl: string;
}

interface PendingSelection {
  page: number;
  rects: { x: number; y: number; w: number; h: number }[];
  selected_text: string;
  toolbar: { left: number; top: number; width: number };
}

/** PDF reader with text-selection highlighting that persists across reloads.
 *
 *  Geometry: rects are stored as fractional page coordinates (each x/y/w/h ∈
 *  [0,1] relative to the page's DOM width/height at render time). Re-rendering
 *  at any zoom level just multiplies by the current page DOM size, so the
 *  highlight never drifts.
 *
 *  Selection capture: `mouseup` reads `window.getSelection()`, walks its
 *  `getClientRects()`, and subtracts each rect's origin from the page's
 *  `getBoundingClientRect()`. Multi-line / multi-column selections become
 *  multiple `rects` entries — we never collapse to a bounding box, which
 *  would cover whitespace between columns.
 */
export default function PdfReader({ topicId, documentId, pdfUrl }: Props) {
  const { message } = App.useApp();
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [numPages, setNumPages] = useState(0);
  const [pending, setPending] = useState<PendingSelection | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const pagesContainerRef = useRef<HTMLDivElement>(null);
  // page_number → DOM node, used for jump-to-page from sidebar.
  const pageNodes = useRef<Record<number, HTMLDivElement>>({});

  // Zoom factor applied on top of the fit-to-width base width. 1.0 = "as wide
  // as the scroll container can hold". Range 0.6–2.0 keeps things sane.
  const [zoom, setZoom] = useState(1.0);
  // Measured width of the scroll container (minus its horizontal padding),
  // recalculated on resize so the page tracks the drawer size.
  const [containerWidth, setContainerWidth] = useState<number>(900);

  useLayoutEffect(() => {
    const el = pagesContainerRef.current;
    if (!el) return;
    const compute = () => {
      // Subtract the container's own horizontal padding so the page doesn't
      // overflow into the gutter.
      const cs = window.getComputedStyle(el);
      const pad =
        parseFloat(cs.paddingLeft || "0") + parseFloat(cs.paddingRight || "0");
      setContainerWidth(Math.max(320, el.clientWidth - pad - 8));
    };
    compute();
    const ro = new ResizeObserver(compute);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const pageWidth = Math.round(containerWidth * zoom);

  // Initial load + when document changes.
  useEffect(() => {
    listAnnotations(topicId, documentId)
      .then(setAnnotations)
      .catch(() => setAnnotations([]));
  }, [topicId, documentId]);

  const onDocLoad = ({ numPages: n }: PDFDocumentProxy) => setNumPages(n);

  // Selection finalizer — converts viewport coords → page-relative ratios.
  const captureSelection = (pageNumber: number, pageEl: HTMLDivElement) => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) {
      setPending(null);
      return;
    }
    const text = sel.toString().trim();
    if (!text) {
      setPending(null);
      return;
    }
    const range = sel.getRangeAt(0);
    const pageRect = pageEl.getBoundingClientRect();
    const clientRects = Array.from(range.getClientRects()).filter(
      (r) => r.width > 0 && r.height > 1,
    );
    if (clientRects.length === 0) {
      setPending(null);
      return;
    }
    const rects = clientRects.map((r) => ({
      x: (r.left - pageRect.left) / pageRect.width,
      y: (r.top - pageRect.top) / pageRect.height,
      w: r.width / pageRect.width,
      h: r.height / pageRect.height,
    }));
    // Anchor the toolbar over the first line of the selection.
    const first = clientRects[0];
    setPending({
      page: pageNumber,
      rects,
      selected_text: text,
      toolbar: {
        left: first.left + first.width / 2,
        top: first.top,
        width: first.width,
      },
    });
  };

  const cancelPending = () => {
    setPending(null);
    window.getSelection()?.removeAllRanges();
  };

  const handlePick = async (kind: AnnotationKind) => {
    if (!pending) return;
    setSubmitting(true);
    try {
      const created = await createAnnotation(topicId, documentId, {
        page_number: pending.page,
        kind,
        selected_text: pending.selected_text,
        rects: pending.rects,
        // Notes get auto-forwarded to the research_notes table on the backend.
        save_as_note: kind === "note",
        color: kind === "comment" ? "#a7d8ff" : "#fff59d",
      });
      setAnnotations((prev) => [...prev, created]);
      const verb =
        kind === "highlight" ? "已高亮" : kind === "comment" ? "已批注" : "已存为笔记";
      message.success(verb);
    } catch (e) {
      message.error(apiErrorMessage(e));
    } finally {
      setSubmitting(false);
      cancelPending();
    }
  };

  const handleDelete = async (a: Annotation) => {
    try {
      await deleteAnnotation(topicId, documentId, a.id);
      setAnnotations((prev) => prev.filter((x) => x.id !== a.id));
    } catch (e) {
      message.error(apiErrorMessage(e));
    }
  };

  const handleJump = (a: Annotation) => {
    const node = pageNodes.current[a.page_number];
    if (node) node.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const annotationsByPage = useMemo(() => {
    const m: Record<number, Annotation[]> = {};
    for (const a of annotations) {
      (m[a.page_number] ||= []).push(a);
    }
    return m;
  }, [annotations]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "6px 12px",
          borderBottom: "1px solid var(--border-subtle)",
          background: "var(--bg-surface)",
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          color: "var(--text-tertiary)",
        }}
      >
        <Tooltip title="缩小">
          <Button
            size="small"
            type="text"
            icon={<MinusOutlined />}
            disabled={zoom <= 0.6}
            onClick={() => setZoom((z) => Math.max(0.6, +(z - 0.1).toFixed(2)))}
          />
        </Tooltip>
        <span style={{ minWidth: 44, textAlign: "center" }}>
          {Math.round(zoom * 100)}%
        </span>
        <Tooltip title="放大">
          <Button
            size="small"
            type="text"
            icon={<PlusOutlined />}
            disabled={zoom >= 2.0}
            onClick={() => setZoom((z) => Math.min(2.0, +(z + 0.1).toFixed(2)))}
          />
        </Tooltip>
        <Tooltip title="贴合宽度">
          <Button
            size="small"
            type="text"
            icon={<CompressOutlined />}
            onClick={() => setZoom(1.0)}
          />
        </Tooltip>
        <Tooltip title="放大到 130%">
          <Button
            size="small"
            type="text"
            icon={<ExpandOutlined />}
            onClick={() => setZoom(1.3)}
          />
        </Tooltip>
        <span style={{ marginLeft: "auto" }}>
          共 {numPages || "—"} 页 · 选中正文文字即可标注
        </span>
      </div>

      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
      <div
        ref={pagesContainerRef}
        style={{
          flex: 1,
          overflowY: "auto",
          background: "var(--bg-canvas)",
          padding: "16px 0",
        }}
        onClickCapture={(e) => {
          // Click outside selection clears it.
          if (pending && (e.target as HTMLElement).closest(".pdf-page") === null) {
            cancelPending();
          }
        }}
      >
        <Document
          file={pdfUrl}
          onLoadSuccess={onDocLoad}
          loading={<div style={{ padding: 24 }}>PDF 加载中…</div>}
          error={<div style={{ padding: 24 }}>PDF 加载失败</div>}
        >
          {Array.from({ length: numPages }, (_, i) => i + 1).map((pn) => (
            <div
              key={pn}
              ref={(el) => {
                if (el) pageNodes.current[pn] = el;
              }}
              data-page={pn}
              className="pdf-page"
              style={{
                position: "relative",
                margin: "0 auto 14px",
                width: "fit-content",
                background: "white",
                boxShadow: "var(--shadow-2)",
              }}
              onMouseUp={(e) => captureSelection(pn, e.currentTarget)}
            >
              <Page
                pageNumber={pn}
                renderTextLayer
                renderAnnotationLayer={false}
                width={pageWidth}
              />
              {(annotationsByPage[pn] || []).map((a) =>
                a.rects.map((r, i) => (
                  <div
                    key={`${a.id}-${i}`}
                    style={{
                      position: "absolute",
                      left: `${(r.x as number) * 100}%`,
                      top: `${(r.y as number) * 100}%`,
                      width: `${(r.w as number) * 100}%`,
                      height: `${(r.h as number) * 100}%`,
                      background: a.color,
                      mixBlendMode: "multiply",
                      pointerEvents: "none",
                      borderRadius: 1.5,
                    }}
                  />
                )),
              )}
            </div>
          ))}
        </Document>
      </div>

      <SelectionToolbar
        visible={!!pending}
        anchorRect={pending?.toolbar ?? null}
        onPick={handlePick}
        busy={submitting}
      />

      <AnnotationSidebar
        annotations={annotations}
        onJump={handleJump}
        onDelete={handleDelete}
      />
      </div>
    </div>
  );
}
