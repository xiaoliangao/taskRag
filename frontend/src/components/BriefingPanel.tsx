import { ReloadOutlined, StarFilled, StarOutlined } from "@ant-design/icons";
import { App, Alert, Button, Segmented, Skeleton } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { generateBriefing, getBriefing, patchDocState } from "../api/briefings";
import { apiErrorMessage } from "../api/client";

interface Props {
  topicId: number;
  documentId: number;
}

export default function BriefingPanel({ topicId, documentId }: Props) {
  const qc = useQueryClient();
  const { message } = App.useApp();

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["briefing", topicId, documentId],
    queryFn: () => getBriefing(topicId, documentId),
    refetchInterval: (q) => {
      const d = q.state.data;
      if (!d?.briefing) return 5000;
      return d.briefing.status === "success" || d.briefing.status === "failed" ? false : 5000;
    },
  });

  const genMut = useMutation({
    mutationFn: () => generateBriefing(topicId, documentId),
    onSuccess: (r) => {
      if (r.status === "queued") message.info("已派发分析任务");
      else if (r.status === "success") message.success("已有结果");
      qc.invalidateQueries({ queryKey: ["briefing", topicId, documentId] });
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const stateMut = useMutation({
    mutationFn: (body: Partial<{ status: string; favorite: boolean }>) =>
      patchDocState(topicId, documentId, body as any),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["briefing", topicId, documentId] }),
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  if (isLoading) return <Skeleton active />;

  const b = data?.briefing;
  const i = data?.topic_insight;
  const s = data?.user_state;

  const priorityPill =
    i?.reading_priority === "high"
      ? "danger"
      : i?.reading_priority === "medium"
      ? "warning"
      : "ghost";

  return (
    <div>
      {/* User state row */}
      <div
        style={{
          display: "flex",
          gap: 12,
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <Segmented
          value={s?.status || "unread"}
          options={[
            { label: "未读", value: "unread" },
            { label: "在读", value: "reading" },
            { label: "已读", value: "read" },
            { label: "归档", value: "archived" },
          ]}
          onChange={(v) => stateMut.mutate({ status: String(v) })}
          size="small"
        />
        <button
          className="icon-btn"
          onClick={() => stateMut.mutate({ favorite: !s?.favorite })}
          style={{
            color: s?.favorite ? "var(--warning)" : "var(--text-tertiary)",
            width: 28,
            height: 28,
          }}
          title={s?.favorite ? "已收藏" : "收藏"}
        >
          {s?.favorite ? <StarFilled /> : <StarOutlined />}
        </button>
      </div>

      {/* Topic insight (why read) */}
      {i && (i.why_read || i.relevance_score != null) && (
        <div className="why-read-card">
          <h6>为什么和当前课题相关</h6>
          <div className="text">{i.why_read || i.relevance_reason}</div>
          <div className="why-read-meta">
            {i.reading_priority && (
              <span className={`pill ${priorityPill}`}>
                {i.reading_priority === "high"
                  ? "高优先级"
                  : i.reading_priority === "medium"
                  ? "中优先级"
                  : "低优先级"}
              </span>
            )}
            {i.relevance_score != null && (
              <span className="pill ghost">
                相关度 {i.relevance_score.toFixed(2)}
              </span>
            )}
            {(i.tags || []).slice(0, 4).map((t) => (
              <span key={t} className="pill ghost">
                {t}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Briefing body */}
      {!b || b.status === "pending" || b.status === "running" ? (
        <Alert
          type="info"
          showIcon
          message="正在生成结构化解读"
          description="新文档自动入队分析；如未启动，可手动派发。"
          action={
            <Button
              icon={<ReloadOutlined />}
              loading={genMut.isPending}
              onClick={() => genMut.mutate()}
            >
              派发
            </Button>
          }
        />
      ) : b.status === "failed" ? (
        <Alert
          type="error"
          showIcon
          message="分析失败"
          description="可点击重新派发，或检查后端日志。"
          action={
            <Button
              icon={<ReloadOutlined />}
              loading={genMut.isPending}
              onClick={() => genMut.mutate()}
            >
              重试
            </Button>
          }
        />
      ) : (
        <>
          {b.one_sentence_summary && (
            <div
              style={{
                fontFamily: "var(--font-display)",
                fontStyle: "italic",
                fontSize: 22,
                lineHeight: 1.4,
                color: "var(--text-primary)",
                marginBottom: 22,
                padding: "16px 18px",
                background: "var(--bg-canvas)",
                borderLeft: "2px solid var(--accent)",
                borderRadius: "0 var(--radius-sm) var(--radius-sm) 0",
              }}
            >
              "{b.one_sentence_summary}"
            </div>
          )}

          {b.problem && (
            <div className="brief-section">
              <h5>问题</h5>
              <div className="body">{b.problem}</div>
            </div>
          )}
          {b.method && (
            <div className="brief-section">
              <h5>方法</h5>
              <div className="body">{b.method}</div>
            </div>
          )}
          {b.contributions?.length > 0 && (
            <div className="brief-section">
              <h5>主要贡献</h5>
              <ul>
                {b.contributions.map((c, idx) => (
                  <li key={idx}>{c}</li>
                ))}
              </ul>
            </div>
          )}
          {b.experiments?.length > 0 && (
            <div className="brief-section">
              <h5>实验结论</h5>
              <ul>
                {b.experiments.map((c, idx) => (
                  <li key={idx}>{c}</li>
                ))}
              </ul>
            </div>
          )}
          {b.limitations?.length > 0 && (
            <div className="brief-section">
              <h5>局限性</h5>
              <ul>
                {b.limitations.map((c, idx) => (
                  <li key={idx}>{c}</li>
                ))}
              </ul>
            </div>
          )}

          {(b.datasets?.length || b.metrics?.length || b.reading_time_minutes) && (
            <div className="brief-section">
              <h5>实验设置</h5>
              <div className="brief-tag-row">
                {b.reading_time_minutes && (
                  <span className="pill ghost">
                    阅读 ~{b.reading_time_minutes} 分钟
                  </span>
                )}
                {b.code_available && (
                  <span className="pill success">
                    {b.code_url ? (
                      <a
                        href={b.code_url}
                        target="_blank"
                        rel="noreferrer"
                        style={{ color: "inherit" }}
                      >
                        有代码 ↗
                      </a>
                    ) : (
                      "有代码"
                    )}
                  </span>
                )}
                {b.datasets?.map((d) => (
                  <span key={`ds-${d}`} className="pill">
                    数据集 · {d}
                  </span>
                ))}
                {b.metrics?.map((m) => (
                  <span key={`m-${m}`} className="pill">
                    指标 · {m}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => genMut.mutate()}
              loading={genMut.isPending}
            >
              重新分析
            </Button>
            <Button size="small" onClick={() => refetch()}>
              刷新
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
