import { ReloadOutlined } from "@ant-design/icons";
import { App, Button, Empty, Skeleton } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";

import { apiErrorMessage } from "../api/client";
import { generateGaps, listInsights } from "../api/intel";

interface Props {
  topicId: number;
}

function confLabel(c: number | null): { label: string; pill: string } {
  if (c == null) return { label: "未评估", pill: "ghost" };
  if (c >= 0.75) return { label: "置信 · 高", pill: "danger" };
  if (c >= 0.5) return { label: "置信 · 中", pill: "warning" };
  return { label: "置信 · 低", pill: "info" };
}

export default function InsightsView({ topicId }: Props) {
  const qc = useQueryClient();
  const { message } = App.useApp();

  const { data, isLoading } = useQuery({
    queryKey: ["insights", topicId, "gap"],
    queryFn: () => listInsights(topicId, "gap"),
    refetchInterval: 20_000,
  });

  const gen = useMutation({
    mutationFn: () => generateGaps(topicId),
    onSuccess: () => {
      message.info("已派发研究空白分析");
      qc.invalidateQueries({ queryKey: ["insights", topicId, "gap"] });
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  return (
    <div>
      <div
        className="tr-card entry"
        style={{
          padding: "22px 26px",
          marginBottom: 18,
          background:
            "linear-gradient(135deg, rgba(107,182,255,0.06), transparent 70%), var(--bg-surface)",
          borderColor: "var(--border-default)",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: 24,
          }}
        >
          <div>
            <div className="page-eyebrow" style={{ color: "var(--info)", marginBottom: 6 }}>
              Research Gap Finder
            </div>
            <h3
              style={{
                fontFamily: "var(--font-display)",
                fontStyle: "italic",
                fontSize: 26,
                fontWeight: 400,
                color: "var(--text-primary)",
                margin: 0,
                marginBottom: 6,
              }}
            >
              研究空白与机会点
            </h3>
            <div style={{ fontSize: 12.5, color: "var(--text-tertiary)", maxWidth: 640 }}>
              系统会从当前课题语料中识别 3–5 个潜在研究方向，所有结论附带不确定性说明，仅作研究灵感参考。
            </div>
          </div>
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            loading={gen.isPending}
            onClick={() => gen.mutate()}
          >
            生成 Gap
          </Button>
        </div>
      </div>

      {isLoading ? (
        <Skeleton active paragraph={{ rows: 5 }} />
      ) : !data || data.length === 0 ? (
        <Empty description="还没有研究洞察" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        data.map((it, idx) => {
          const cf = confLabel(it.confidence);
          return (
            <div key={it.id} className={`gap-card entry entry-${Math.min(idx + 1, 6)}`}>
              <div className="gap-card-head">
                <div className="gap-card-title">{it.title}</div>
                <div className="gap-card-meta">
                  <span className={`pill ${cf.pill}`}>{cf.label}</span>
                  <span className="pill ghost">
                    {it.evidence_document_ids.length} 篇证据
                  </span>
                </div>
              </div>
              {it.summary && <div className="gap-card-summary">{it.summary}</div>}
              {it.detail_md && (
                <div className="gap-card-detail">
                  <ReactMarkdown>{it.detail_md}</ReactMarkdown>
                </div>
              )}
              {it.suggested_questions.length > 0 && (
                <div className="gap-card-section">
                  <h6>可追问的问题</h6>
                  <ul>
                    {it.suggested_questions.map((q, i) => (
                      <li key={i}>{q}</li>
                    ))}
                  </ul>
                </div>
              )}
              {it.suggested_experiments.length > 0 && (
                <div className="gap-card-section">
                  <h6>可尝试的实验方向</h6>
                  <ul>
                    {it.suggested_experiments.map((q, i) => (
                      <li key={i}>{q}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}
