import { ArrowRightOutlined, FilePdfOutlined } from "@ant-design/icons";
import dayjs from "dayjs";

import type { Citation } from "../types/api";

export default function CitationPanel({
  items,
  onOpenSource,
}: {
  items: Citation[];
  /** Open the cited document in the in-app PDF reader at its source page. */
  onOpenSource?: (documentId: number, page?: number) => void;
}) {
  if (!items || items.length === 0) {
    return (
      <div
        style={{
          color: "var(--text-muted)",
          fontStyle: "italic",
          textAlign: "center",
          padding: "32px 12px",
          fontFamily: "var(--font-display)",
          fontSize: 16,
        }}
      >
        提问后引用会出现在这里
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {items.map((c, i) => {
        // The number here mirrors the inline [n] markers the model is asked to
        // emit in its answer, so the reader can map a claim → its source.
        const canLocate = !!onOpenSource && c.document_id != null;
        const locate = () => onOpenSource?.(c.document_id, c.page_start ?? undefined);
        return (
          <div
            key={`${c.document_id}-${c.chunk_id ?? i}`}
            className="citation-chip"
            onClick={canLocate ? locate : undefined}
            style={canLocate ? { cursor: "pointer" } : undefined}
            title={canLocate ? "在站内 PDF 中定位到该来源" : undefined}
          >
            <div className="citation-chip-title">
              <span className="citation-chip-num">[{String(i + 1).padStart(2, "0")}]</span>
              {c.title}
            </div>
            <div className="citation-chip-meta">
              <span style={{ color: "var(--accent)" }}>{c.source}</span>
              {c.published_at && <span>· {dayjs(c.published_at).format("YYYY-MM-DD")}</span>}
              {c.section_title && (
                <span style={{ color: "var(--text-secondary)" }}>· {c.section_title}</span>
              )}
              {c.page_start != null && (
                <span style={{ color: "var(--text-secondary)" }}>· p.{c.page_start}</span>
              )}
              <span style={{ marginLeft: "auto" }}>{c.score.toFixed(2)}</span>
            </div>
            <div
              style={{
                marginTop: 8,
                display: "flex",
                gap: 14,
                alignItems: "center",
              }}
            >
              {canLocate && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    locate();
                  }}
                  style={{
                    border: "none",
                    background: "none",
                    padding: 0,
                    cursor: "pointer",
                    fontSize: 11,
                    color: "var(--accent)",
                    fontFamily: "var(--font-mono)",
                    letterSpacing: "0.05em",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                  }}
                >
                  <FilePdfOutlined style={{ fontSize: 11 }} /> 原文定位
                </button>
              )}
              <a
                href={c.url}
                target="_blank"
                rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
                style={{
                  fontSize: 11,
                  color: "var(--text-tertiary)",
                  fontFamily: "var(--font-mono)",
                  letterSpacing: "0.05em",
                }}
              >
                查看原文 <ArrowRightOutlined style={{ fontSize: 10 }} />
              </a>
            </div>
          </div>
        );
      })}
    </div>
  );
}
