import { ReloadOutlined } from "@ant-design/icons";
import { App, Button, Empty, Skeleton } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import ReactMarkdown from "react-markdown";

import { generatePulse, getLatestPulse } from "../api/intel";
import { apiErrorMessage } from "../api/client";

interface Props {
  topicId: number;
  onJumpDocument?: (docId: number) => void;
}

export default function PulseCard({ topicId, onJumpDocument }: Props) {
  const qc = useQueryClient();
  const { message } = App.useApp();

  const { data, isLoading } = useQuery({
    queryKey: ["pulse-latest", topicId],
    queryFn: () => getLatestPulse(topicId),
    refetchInterval: 30_000,
  });

  const mut = useMutation({
    mutationFn: () => generatePulse(topicId),
    onSuccess: () => {
      message.info("简报正在生成");
      qc.invalidateQueries({ queryKey: ["pulse-latest", topicId] });
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  if (isLoading) return <Skeleton active paragraph={{ rows: 6 }} />;

  if (!data) {
    return (
      <div className="pulse-hero entry">
        <div className="pulse-eyebrow">
          <span className="dot" />
          Research Pulse · 今日
        </div>
        <h2 className="pulse-title">
          今天还没有<span style={{ color: "var(--accent)" }}>简报</span>
        </h2>
        <div style={{ marginTop: 12 }}>
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            loading={mut.isPending}
            onClick={() => mut.mutate()}
          >
            生成今日简报
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="entry">
      <div className="pulse-hero">
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 14,
          }}
        >
          <div className="pulse-eyebrow">
            <span className={`dot ${data.status === "success" ? "live" : ""}`} />
            Research Pulse · {dayjs(data.pulse_date).format("YYYY-MM-DD")}
          </div>
          <Button
            icon={<ReloadOutlined />}
            loading={mut.isPending}
            onClick={() => mut.mutate()}
          >
            重新生成
          </Button>
        </div>

        {data.title && <h2 className="pulse-title">{data.title}</h2>}

        {data.status !== "success" ? (
          <Empty
            description={`简报状态：${data.status}`}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <>
            {data.summary_md && (
              <div className="pulse-summary">
                <ReactMarkdown>{data.summary_md}</ReactMarkdown>
              </div>
            )}

            <div className="pulse-grid">
              <div className="pulse-block">
                <h5>必读论文</h5>
                {data.important_documents.length === 0 ? (
                  <div
                    style={{
                      fontFamily: "var(--font-display)",
                      fontStyle: "italic",
                      color: "var(--text-muted)",
                      fontSize: 14,
                    }}
                  >
                    今日无必读
                  </div>
                ) : (
                  data.important_documents.map((d, i) => (
                    <div key={i} className="pulse-doc-row">
                      <div className="pulse-doc-num">
                        {String(i + 1).padStart(2, "0")}
                      </div>
                      <div>
                        <div
                          className="pulse-doc-title"
                          onClick={() => d.document_id && onJumpDocument?.(d.document_id)}
                        >
                          {d.title}
                        </div>
                        {d.reason && <div className="pulse-doc-reason">{d.reason}</div>}
                      </div>
                    </div>
                  ))
                )}
              </div>

              <div className="pulse-block">
                <h5>升温关键词</h5>
                <div style={{ marginBottom: 18 }}>
                  {data.emerging_keywords.length === 0 ? (
                    <div
                      style={{
                        fontFamily: "var(--font-display)",
                        fontStyle: "italic",
                        color: "var(--text-muted)",
                        fontSize: 14,
                      }}
                    >
                      暂无明显升温
                    </div>
                  ) : (
                    data.emerging_keywords.map((k) => (
                      <span key={k.term} className="keyword-tag hot">
                        {k.term}
                      </span>
                    ))
                  )}
                </div>

                <h5 style={{ marginTop: 12 }}>建议下一步</h5>
                {data.suggested_actions.length === 0 ? (
                  <div
                    style={{
                      fontFamily: "var(--font-display)",
                      fontStyle: "italic",
                      color: "var(--text-muted)",
                      fontSize: 14,
                    }}
                  >
                    暂无建议
                  </div>
                ) : (
                  data.suggested_actions.map((a, i) => (
                    <div
                      key={i}
                      style={{
                        padding: "8px 0",
                        borderBottom:
                          i < data.suggested_actions.length - 1
                            ? "1px solid var(--border-subtle)"
                            : "none",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          marginBottom: 2,
                        }}
                      >
                        <span
                          className={`pill ${a.action === "read" ? "info" : "accent"}`}
                        >
                          {a.action}
                        </span>
                      </div>
                      <div style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>
                        {a.question || a.reason || ""}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </>
        )}
      </div>

      {data.new_documents.length > 0 && (
        <div className="tr-card entry entry-2" style={{ marginTop: 20 }}>
          <div className="tr-card-header">
            <div className="tr-card-title">
              <span className="dot live" />
              今日新增 ({data.new_documents.length})
            </div>
          </div>
          <div>
            {data.new_documents.slice(0, 8).map((d, i) => (
              <div
                key={i}
                onClick={() => d.document_id && onJumpDocument?.(d.document_id)}
                style={{
                  padding: "10px 0",
                  borderBottom:
                    i < Math.min(data.new_documents.length, 8) - 1
                      ? "1px solid var(--border-subtle)"
                      : "none",
                  cursor: "pointer",
                  display: "grid",
                  gridTemplateColumns: "32px 1fr",
                  gap: 12,
                }}
              >
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 11,
                    color: "var(--text-muted)",
                  }}
                >
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span
                  style={{
                    fontSize: 13,
                    color: "var(--text-secondary)",
                    transition: "color var(--d-fast) var(--ease-out)",
                  }}
                  onMouseEnter={(e) =>
                    (e.currentTarget.style.color = "var(--accent)")
                  }
                  onMouseLeave={(e) =>
                    (e.currentTarget.style.color = "var(--text-secondary)")
                  }
                >
                  {d.title}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
