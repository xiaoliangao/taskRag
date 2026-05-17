import { PlusOutlined } from "@ant-design/icons";
import { Skeleton } from "antd";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { listTopics } from "../api/topics";
import TopicCreateModal from "../components/TopicCreateModal";

export default function TopicListPage() {
  const navigate = useNavigate();
  const [createOpen, setCreateOpen] = useState(false);
  const { data: topics, isLoading } = useQuery({ queryKey: ["topics"], queryFn: listTopics });

  const used = topics?.length ?? 0;
  const cap = 5;
  const remaining = cap - used;

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
          marginBottom: 36,
        }}
      >
        <div>
          <div className="page-eyebrow">Workspace · Topics</div>
          <h1 className="page-title">
            你的
            <span style={{ color: "var(--accent)", fontStyle: "italic" }}>研究方向</span>
          </h1>
          <p className="page-subtitle">
            每个课题是一个独立的研究宇宙 — 自己的语料、自己的脉搏、自己的阅读路径。
          </p>
        </div>

        <div
          style={{
            textAlign: "right",
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            color: "var(--text-tertiary)",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
          }}
        >
          <div>{used} / {cap} active</div>
          <div style={{ color: "var(--text-muted)", marginTop: 2 }}>
            {remaining > 0 ? `${remaining} slots remaining` : "limit reached"}
          </div>
        </div>
      </div>

      {isLoading ? (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
            gap: 16,
          }}
        >
          {[0, 1, 2].map((i) => (
            <div key={i} className="tr-card">
              <Skeleton active paragraph={{ rows: 3 }} />
            </div>
          ))}
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
            gap: 16,
          }}
        >
          {(topics ?? []).map((t, idx) => (
            <div
              key={t.id}
              className={`topic-card entry entry-${Math.min(idx + 1, 6)} ${
                !t.enabled ? "paused" : ""
              }`}
              onClick={() => navigate(`/topics/${t.id}`)}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 12,
                }}
              >
                <span
                  className="eyebrow"
                  style={{
                    color: t.enabled ? "var(--accent)" : "var(--text-muted)",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  <span className={`dot ${t.enabled ? "live" : ""}`} />
                  {t.enabled ? "Active" : "Paused"}
                </span>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 10,
                    color: "var(--text-muted)",
                    letterSpacing: "0.1em",
                  }}
                >
                  #{String(t.id).padStart(3, "0")}
                </span>
              </div>

              <div className="topic-card-title">{t.name}</div>
              <div className="topic-card-desc">{t.description || "—"}</div>

              <div className="topic-card-tags">
                {t.keywords.slice(0, 3).map((k) => (
                  <span key={k} className="keyword-tag">
                    {k}
                  </span>
                ))}
                {t.keywords.length > 3 && (
                  <span className="keyword-tag">+{t.keywords.length - 3}</span>
                )}
              </div>

              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-end",
                  paddingTop: 12,
                  borderTop: "1px solid var(--border-subtle)",
                }}
              >
                <div className="topic-card-stats">
                  <div className="topic-card-stat">
                    <div className="v">{t.document_count}</div>
                    <div className="l">papers</div>
                  </div>
                  <div className="topic-card-stat">
                    <div className="v">{t.keywords.length}</div>
                    <div className="l">keywords</div>
                  </div>
                </div>
                <div className="topic-card-footer">
                  {t.last_collected_at
                    ? `${dayjs(t.last_collected_at).format("MM-DD HH:mm")}`
                    : "尚未采集"}
                </div>
              </div>
            </div>
          ))}

          {remaining > 0 && (
            <div
              className={`topic-card add entry entry-${Math.min(used + 1, 6)}`}
              onClick={() => setCreateOpen(true)}
            >
              <div>
                <div className="add-icon">
                  <PlusOutlined />
                </div>
                <div
                  style={{
                    fontFamily: "var(--font-display)",
                    fontStyle: "italic",
                    fontSize: 18,
                    color: "var(--text-secondary)",
                    marginBottom: 4,
                  }}
                >
                  开辟新方向
                </div>
                <div
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 11,
                    color: "var(--text-muted)",
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                  }}
                >
                  + new topic
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      <TopicCreateModal open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}
