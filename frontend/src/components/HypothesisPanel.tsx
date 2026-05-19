import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DeleteOutlined,
  ExclamationCircleOutlined,
  ExperimentOutlined,
  MinusCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import {
  App,
  Button,
  Empty,
  Input,
  List,
  Skeleton,
  Tag,
  Typography,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import MarkdownView from "./MarkdownView";
import { useState } from "react";

import { apiErrorMessage } from "../api/client";
import {
  deleteHypothesis,
  getHypothesis,
  listHypotheses,
  runHypothesis,
} from "../api/hypotheses";
import type {
  HypothesisCheckPublic,
  HypothesisEvidencePublic,
} from "../types/api";

interface Props {
  topicId: number;
  onJumpDocument?: (docId: number) => void;
}

const VERDICT_LABEL: Record<string, { label: string; color: string; icon: any }> = {
  supported: { label: "支持", color: "#10b981", icon: <CheckCircleOutlined /> },
  refuted: { label: "反对", color: "#dc2626", icon: <CloseCircleOutlined /> },
  mixed: { label: "存在分歧", color: "#f59e0b", icon: <ExclamationCircleOutlined /> },
  qualified: { label: "条件限定", color: "#f59e0b", icon: <ExclamationCircleOutlined /> },
  insufficient: { label: "证据不足", color: "#94a3b8", icon: <MinusCircleOutlined /> },
};

const STANCE_LABEL: Record<string, { label: string; color: string }> = {
  support: { label: "支持", color: "#10b981" },
  oppose: { label: "反对", color: "#dc2626" },
  qualify: { label: "限定", color: "#f59e0b" },
  neutral: { label: "中性", color: "#94a3b8" },
};

function EvidenceItem({
  e,
  onJump,
}: {
  e: HypothesisEvidencePublic;
  onJump?: (id: number) => void;
}) {
  const tone = STANCE_LABEL[e.stance] ?? { label: e.stance, color: "#94a3b8" };
  return (
    <div
      style={{
        padding: 10,
        border: `1px solid ${tone.color}33`,
        borderLeft: `3px solid ${tone.color}`,
        borderRadius: 6,
        marginBottom: 8,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <Tag style={{ background: `${tone.color}1a`, border: "none", color: tone.color }}>
          {tone.label}
        </Tag>
        <a
          onClick={(e2) => {
            e2.preventDefault();
            onJump?.(e.document_id);
          }}
          href="#"
          style={{
            fontSize: 12,
            color: "var(--text-secondary)",
            maxWidth: 240,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={e.document_title ?? ""}
        >
          {e.document_title ?? `Doc #${e.document_id}`}
        </a>
      </div>
      {e.quote && (
        <div style={{ fontSize: 13, fontStyle: "italic", color: "var(--text-secondary)", marginBottom: 4 }}>
          “{e.quote}”
        </div>
      )}
      {e.explanation && (
        <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{e.explanation}</div>
      )}
    </div>
  );
}

function CheckDetail({
  check,
  onJump,
}: {
  check: HypothesisCheckPublic;
  onJump?: (id: number) => void;
}) {
  const verdict = VERDICT_LABEL[check.verdict ?? "insufficient"] ?? VERDICT_LABEL.insufficient;
  const support = check.evidence.filter((e) => e.stance === "support");
  const oppose = check.evidence.filter((e) => e.stance === "oppose");
  const qualify = check.evidence.filter((e) => e.stance === "qualify");
  return (
    <div data-testid={`hypothesis-detail-${check.id}`}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          marginBottom: 12,
          padding: 12,
          borderRadius: 10,
          background: `${verdict.color}1a`,
        }}
      >
        <span style={{ color: verdict.color, fontSize: 18 }}>{verdict.icon}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 500 }}>{verdict.label}</div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
            置信度 {(check.confidence * 100).toFixed(0)}% · 证据 {check.evidence.length} 条
          </div>
        </div>
      </div>

      {check.result_md && (
        <div
          style={{
            background: "var(--bg-elevated)",
            padding: 12,
            borderRadius: 8,
            marginBottom: 16,
            fontSize: 13,
          }}
        >
          <MarkdownView>{check.result_md}</MarkdownView>
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 12,
        }}
      >
        <div>
          <Typography.Title level={5} style={{ margin: "0 0 8px", fontSize: 13 }}>
            支持 ({support.length})
          </Typography.Title>
          {support.length === 0 && <Empty image={null} description="无" />}
          {support.map((e) => (
            <EvidenceItem key={e.id} e={e} onJump={onJump} />
          ))}
        </div>
        <div>
          <Typography.Title level={5} style={{ margin: "0 0 8px", fontSize: 13 }}>
            反对 ({oppose.length})
          </Typography.Title>
          {oppose.length === 0 && <Empty image={null} description="无" />}
          {oppose.map((e) => (
            <EvidenceItem key={e.id} e={e} onJump={onJump} />
          ))}
        </div>
        <div>
          <Typography.Title level={5} style={{ margin: "0 0 8px", fontSize: 13 }}>
            限定条件 ({qualify.length})
          </Typography.Title>
          {qualify.length === 0 && <Empty image={null} description="无" />}
          {qualify.map((e) => (
            <EvidenceItem key={e.id} e={e} onJump={onJump} />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function HypothesisPanel({ topicId, onJumpDocument }: Props) {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const [hypothesis, setHypothesis] = useState("");
  const [activeId, setActiveId] = useState<number | null>(null);

  const { data: history } = useQuery({
    queryKey: ["hypotheses", topicId],
    queryFn: () => listHypotheses(topicId, 20),
    refetchInterval: 30_000,
  });

  const { data: detail, isFetching: detailLoading } = useQuery({
    queryKey: ["hypothesis", topicId, activeId],
    queryFn: () => (activeId ? getHypothesis(topicId, activeId) : Promise.resolve(null)),
    enabled: !!activeId,
    // Auto-poll while the check is still being processed by Celery.
    refetchInterval: (q) => {
      const d = q.state.data;
      if (!d) return 3_000;
      if (d.status === "pending" || d.status === "running") return 3_000;
      return false;
    },
  });

  const runMut = useMutation({
    mutationFn: () => runHypothesis(topicId, hypothesis),
    onSuccess: (data) => {
      setActiveId(data.id);
      setHypothesis("");
      message.info("已加入队列，正在跟 LLM 沟通…");
      qc.invalidateQueries({ queryKey: ["hypotheses", topicId] });
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const delMut = useMutation({
    mutationFn: (id: number) => deleteHypothesis(topicId, id),
    onSuccess: () => {
      message.success("已删除");
      setActiveId(null);
      qc.invalidateQueries({ queryKey: ["hypotheses", topicId] });
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  return (
    <div data-testid="hypothesis-panel">
      <div style={{ marginBottom: 16 }}>
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
          <ExperimentOutlined style={{ marginRight: 6 }} />
          Hypothesis Verification
        </div>
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8 }}>
          输入一个研究假设，系统在 Topic 内检索证据并给出 支持 / 反对 / 限定条件 三栏。
        </div>
        <Input.TextArea
          rows={3}
          value={hypothesis}
          onChange={(e) => setHypothesis(e.target.value)}
          placeholder="例如：基于迭代优化的方法在稠密场景下优于端到端方法"
          maxLength={500}
          data-testid="hypothesis-input"
        />
        <div style={{ marginTop: 8, textAlign: "right" }}>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={runMut.isPending}
            disabled={!hypothesis.trim()}
            onClick={() => runMut.mutate()}
            data-testid="hypothesis-run-btn"
          >
            开始验证
          </Button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 16 }}>
        <div>
          <Typography.Title level={5} style={{ margin: "0 0 8px" }}>
            历史
          </Typography.Title>
          {(history ?? []).length === 0 ? (
            <Empty description="尚无验证记录" />
          ) : (
            <List
              size="small"
              dataSource={history ?? []}
              renderItem={(h) => (
                <List.Item
                  onClick={() => setActiveId(h.id)}
                  style={{
                    cursor: "pointer",
                    background: activeId === h.id ? "var(--bg-elevated)" : undefined,
                    borderRadius: 6,
                    padding: "8px 10px",
                  }}
                  actions={[
                    <Button
                      key="del"
                      size="small"
                      type="text"
                      icon={<DeleteOutlined />}
                      onClick={(e) => {
                        e.stopPropagation();
                        delMut.mutate(h.id);
                      }}
                    />,
                  ]}
                >
                  <List.Item.Meta
                    title={
                      <div style={{ fontSize: 13, fontWeight: 500 }} title={h.hypothesis}>
                        {h.hypothesis.length > 40 ? `${h.hypothesis.slice(0, 38)}…` : h.hypothesis}
                      </div>
                    }
                    description={
                      <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                        <Tag
                          color={
                            (VERDICT_LABEL[h.verdict ?? "insufficient"] ?? VERDICT_LABEL.insufficient)
                              .color
                          }
                          style={{ marginRight: 6 }}
                        >
                          {(VERDICT_LABEL[h.verdict ?? "insufficient"] ?? VERDICT_LABEL.insufficient).label}
                        </Tag>
                        {dayjs(h.created_at).format("MM-DD HH:mm")}
                      </div>
                    }
                  />
                </List.Item>
              )}
            />
          )}
        </div>
        <div>
          {!activeId ? (
            <Empty description="选择一条历史记录或新建一个验证" />
          ) : detailLoading ? (
            <Skeleton active />
          ) : detail ? (
            <CheckDetail check={detail} onJump={onJumpDocument} />
          ) : (
            <Empty description="未找到详情" />
          )}
        </div>
      </div>
    </div>
  );
}
