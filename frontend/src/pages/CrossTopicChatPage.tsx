import {
  ArrowUpOutlined,
  ClusterOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import {
  App,
  Button,
  Checkbox,
  Empty,
  Segmented,
  Skeleton,
  Tag,
  Typography,
} from "antd";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { runAgent, type AgentResponse } from "../api/agent";
import { apiErrorMessage } from "../api/client";
import { crossTopicQA, type CrossTopicCitation } from "../api/cross_topic";
import { listTopics } from "../api/topics";
import MarkdownView from "../components/MarkdownView";

const TOPIC_COLORS = [
  "#d4ff4a",
  "#3b82f6",
  "#10b981",
  "#f97316",
  "#a855f7",
  "#ec4899",
  "#06b6d4",
  "#fbbf24",
];

function topicColor(topicId: number | null) {
  if (topicId == null) return "var(--text-tertiary)";
  return TOPIC_COLORS[topicId % TOPIC_COLORS.length];
}

interface QAResult {
  question: string;
  answer: string;
  citations: CrossTopicCitation[];
  topics_searched: number[];
  topicNameById: Record<number, string>;
}

interface AgentResult {
  question: string;
  response: AgentResponse;
  topicNameById: Record<number, string>;
}

export default function CrossTopicChatPage() {
  const { message } = App.useApp();
  const [draft, setDraft] = useState("");
  const [selected, setSelected] = useState<number[]>([]);
  const [history, setHistory] = useState<QAResult[]>([]);
  const [agentHistory, setAgentHistory] = useState<AgentResult[]>([]);
  const [mode, setMode] = useState<"qa" | "agent">("qa");

  const topicsQ = useQuery({
    queryKey: ["topics-cross"],
    queryFn: () => listTopics(),
  });

  const topicNameById = useMemo(() => {
    const m: Record<number, string> = {};
    for (const t of topicsQ.data ?? []) m[t.id] = t.name;
    return m;
  }, [topicsQ.data]);

  const submitMut = useMutation({
    mutationFn: () =>
      crossTopicQA({
        topic_ids: selected,
        question: draft.trim(),
        mode: "default",
      }),
    onSuccess: (data) => {
      setHistory((h) => [
        {
          question: draft.trim(),
          answer: data.answer,
          citations: data.citations,
          topics_searched: data.topics_searched,
          topicNameById,
        },
        ...h,
      ]);
      setDraft("");
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const agentMut = useMutation({
    mutationFn: () =>
      runAgent({ topic_ids: selected, question: draft.trim(), max_steps: 5 }),
    onSuccess: (data) => {
      setAgentHistory((h) => [
        { question: draft.trim(), response: data, topicNameById },
        ...h,
      ]);
      setDraft("");
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const isPending = mode === "qa" ? submitMut.isPending : agentMut.isPending;
  const canSubmit = draft.trim().length > 0 && !isPending;
  const submit = () => (mode === "qa" ? submitMut.mutate() : agentMut.mutate());

  return (
    <div style={{ maxWidth: 1080, margin: "0 auto" }}>
      <div style={{ marginBottom: 20 }}>
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: "var(--text-secondary)",
            marginBottom: 6,
          }}
        >
          <ClusterOutlined style={{ marginRight: 6 }} />
          CROSS-TOPIC QA
        </div>
        <Typography.Title level={1} style={{ margin: 0 }}>
          跨课题问答
        </Typography.Title>
        <p style={{ color: "var(--text-secondary)", marginTop: 6 }}>
          一次提问，命中你所有（或选定）课题的语料；citation 会标注来源 topic。
        </p>
      </div>

      <div
        style={{
          border: "1px solid var(--border-default)",
          borderRadius: 10,
          padding: 14,
          marginBottom: 18,
          background: "var(--bg-surface, var(--bg-elevated))",
        }}
      >
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>
          选择搜索范围（留空 = 所有我拥有的课题）
        </div>
        {topicsQ.isLoading ? (
          <Skeleton.Input active size="small" />
        ) : (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {(topicsQ.data ?? []).map((t) => {
              const checked = selected.includes(t.id);
              return (
                <Checkbox
                  key={t.id}
                  checked={checked}
                  onChange={(e) => {
                    setSelected((prev) =>
                      e.target.checked
                        ? [...prev, t.id]
                        : prev.filter((x) => x !== t.id),
                    );
                  }}
                  style={{
                    padding: "4px 10px",
                    border: `1px solid ${checked ? topicColor(t.id) : "var(--border-default)"}`,
                    borderRadius: 999,
                    background: checked ? `${topicColor(t.id)}1a` : "transparent",
                  }}
                >
                  {t.name}
                  <span
                    style={{ marginLeft: 4, color: "var(--text-tertiary)", fontSize: 10 }}
                  >
                    {t.document_count}
                  </span>
                </Checkbox>
              );
            })}
          </div>
        )}
      </div>

      <div style={{ marginBottom: 12 }}>
        <Segmented
          value={mode}
          onChange={(v) => setMode(v as "qa" | "agent")}
          options={[
            { label: "RAG 问答", value: "qa", icon: <ClusterOutlined /> },
            { label: "Agent 模式", value: "agent", icon: <RobotOutlined /> },
          ]}
        />
        <span
          style={{ marginLeft: 12, fontSize: 11, color: "var(--text-tertiary)" }}
        >
          {mode === "qa"
            ? "一次性检索 + 生成回答"
            : "LLM 多步调用 topic_search / paper_lookup / list_methods 工具"}
        </span>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 24 }}>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={
            mode === "qa"
              ? "想跨课题问什么？例如：reranking 在 RAG 和 search 两个方向上的研究有什么交叉？"
              : "Agent 适合需要多步推理的问题，例如：找出 RAG 课题里最早提出 reranking 概念的论文，并对比与现代方法的差异"
          }
          rows={2}
          style={{
            flex: 1,
            padding: 10,
            borderRadius: 8,
            border: "1px solid var(--border-default)",
            background: "var(--bg-elevated)",
            color: "var(--text-primary)",
            fontFamily: "inherit",
            fontSize: 14,
            resize: "vertical",
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (canSubmit) submit();
            }
          }}
        />
        <Button
          type="primary"
          icon={<ArrowUpOutlined />}
          onClick={submit}
          loading={isPending}
          disabled={!canSubmit}
          style={{ height: "auto" }}
        >
          {mode === "qa" ? "提问" : "启动 Agent"}
        </Button>
      </div>

      {isPending && (
        <div style={{ color: "var(--text-secondary)", marginBottom: 12 }}>
          {mode === "qa"
            ? "正在跨课题检索 + 生成回答…（约 30 秒）"
            : "Agent 正在多步推理 + 调用工具…（30-90 秒）"}
        </div>
      )}

      {mode === "agent" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20, marginBottom: 20 }}>
          {agentHistory.length === 0 && !agentMut.isPending && (
            <Empty description="Agent 模式尚无记录" />
          )}
          {agentHistory.map((a, idx) => (
            <div
              key={idx}
              style={{
                border: "1px solid var(--border-default)",
                borderRadius: 10,
                padding: 16,
                background: "var(--bg-surface, var(--bg-elevated))",
              }}
            >
              <Typography.Text strong style={{ fontSize: 15 }}>
                <RobotOutlined style={{ marginRight: 6, color: "var(--accent)" }} />
                {a.question}
              </Typography.Text>
              {a.response.error && (
                <div
                  style={{
                    fontSize: 12,
                    color: "#fca5a5",
                    background: "rgba(220,38,38,0.10)",
                    padding: 8,
                    borderRadius: 6,
                    marginTop: 8,
                  }}
                >
                  Agent error: {a.response.error}
                </div>
              )}
              <div style={{ marginTop: 12, marginBottom: 12 }}>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  执行步骤 ({a.response.steps.length})
                </Typography.Text>
                <div
                  style={{
                    marginTop: 4,
                    fontFamily: "var(--font-mono)",
                    fontSize: 12,
                    background: "var(--bg-elevated)",
                    padding: 10,
                    borderRadius: 6,
                    maxHeight: 260,
                    overflow: "auto",
                  }}
                >
                  {a.response.steps.map((s, i) => (
                    <div key={i} style={{ marginBottom: 4, lineHeight: 1.6 }}>
                      <Tag
                        style={{
                          background:
                            s.role === "tool_call"
                              ? "rgba(168,85,247,0.15)"
                              : s.role === "observation"
                                ? "rgba(59,130,246,0.12)"
                                : s.role === "final"
                                  ? "rgba(16,185,129,0.15)"
                                  : "transparent",
                          color:
                            s.role === "tool_call"
                              ? "#c4b5fd"
                              : s.role === "observation"
                                ? "#93c5fd"
                                : s.role === "final"
                                  ? "#6ee7b7"
                                  : "var(--text-tertiary)",
                          border: "none",
                          fontSize: 10,
                          padding: "0 6px",
                        }}
                      >
                        {s.role}
                      </Tag>
                      {s.tool && (
                        <span style={{ color: "var(--accent)", marginRight: 6 }}>
                          {s.tool}({s.args ? JSON.stringify(s.args) : ""})
                        </span>
                      )}
                      <span style={{ color: "var(--text-secondary)" }}>
                        {s.content.length > 240 ? `${s.content.slice(0, 240)}…` : s.content}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
              {a.response.final_answer && (
                <div
                  style={{
                    background: "var(--accent-bg-soft)",
                    padding: 12,
                    borderRadius: 8,
                    borderLeft: "3px solid var(--accent)",
                  }}
                >
                  <MarkdownView>{a.response.final_answer}</MarkdownView>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {mode === "qa" && history.length === 0 && !submitMut.isPending ? (
        <Empty description="还没有问答记录" />
      ) : mode === "qa" ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {history.map((h, idx) => (
            <div
              key={idx}
              style={{
                border: "1px solid var(--border-default)",
                borderRadius: 10,
                padding: 16,
                background: "var(--bg-surface, var(--bg-elevated))",
              }}
            >
              <Typography.Text strong style={{ fontSize: 15 }}>
                Q: {h.question}
              </Typography.Text>
              <div
                style={{
                  fontSize: 11,
                  color: "var(--text-tertiary)",
                  marginTop: 4,
                  marginBottom: 12,
                }}
              >
                searched topics:{" "}
                {h.topics_searched
                  .map((tid) => h.topicNameById[tid] ?? `#${tid}`)
                  .join(" / ")}
              </div>
              <div style={{ marginBottom: 12 }}>
                <MarkdownView>{h.answer}</MarkdownView>
              </div>
              {h.citations.length > 0 && (
                <div
                  style={{
                    borderTop: "1px solid var(--border-subtle)",
                    paddingTop: 10,
                    fontSize: 12,
                  }}
                >
                  <div style={{ color: "var(--text-secondary)", marginBottom: 6 }}>
                    引用 ({h.citations.length})
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {h.citations.map((c, i) => (
                      <div
                        key={i}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          flexWrap: "wrap",
                        }}
                      >
                        <Tag
                          style={{
                            background: `${topicColor(c.topic_id)}1a`,
                            color: topicColor(c.topic_id),
                            border: "none",
                            margin: 0,
                          }}
                        >
                          {c.topic_name ?? "?"}
                        </Tag>
                        <a
                          href={c.url}
                          target="_blank"
                          rel="noreferrer"
                          style={{
                            color: "var(--text-primary)",
                            textDecoration: "none",
                            borderBottom: "1px dashed var(--text-tertiary)",
                            maxWidth: 600,
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {c.title || `doc ${c.document_id}`}
                        </a>
                        <span
                          style={{
                            color: "var(--text-tertiary)",
                            fontFamily: "var(--font-mono)",
                            fontSize: 10,
                          }}
                        >
                          {c.score.toFixed(2)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
