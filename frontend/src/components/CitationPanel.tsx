import { ArrowRightOutlined } from "@ant-design/icons";
import dayjs from "dayjs";

import type { Citation } from "../types/api";

export default function CitationPanel({ items }: { items: Citation[] }) {
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
      {items.map((c, i) => (
        <div key={`${c.document_id}-${c.chunk_id ?? i}`} className="citation-chip">
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
            <span style={{ marginLeft: "auto" }}>{c.score.toFixed(2)}</span>
          </div>
          <div style={{ marginTop: 8 }}>
            <a
              href={c.url}
              target="_blank"
              rel="noreferrer"
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
      ))}
    </div>
  );
}
