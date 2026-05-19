import {
  AlertOutlined,
  CheckOutlined,
  CloseOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { App, Button, Empty, Skeleton, Segmented, Tag, Typography } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import MarkdownView from "./MarkdownView";

import { apiErrorMessage } from "../api/client";
import {
  detectConflicts,
  listConflicts,
  sendConflictFeedback,
} from "../api/conflicts";
import { listSignals, refreshSignals } from "../api/signals";
import type {
  ConflictRelationPublic,
  DocumentSignalPublic,
} from "../types/api";

interface Props {
  topicId: number;
  onJumpDocument?: (docId: number) => void;
}

const RELATION_LABEL: Record<string, { label: string; color: string }> = {
  conflicts: { label: "疑似冲突", color: "#dc2626" },
  qualifies: { label: "条件不同", color: "#f59e0b" },
  supports: { label: "互相支持", color: "#10b981" },
  insufficient_info: { label: "证据不足", color: "#94a3b8" },
};

const RELATION_OPTIONS = [
  { label: "全部", value: "" },
  { label: "疑似冲突", value: "conflicts" },
  { label: "条件不同", value: "qualifies" },
  { label: "互相支持", value: "supports" },
];

function relTone(rt: string) {
  return RELATION_LABEL[rt] ?? { label: rt, color: "#94a3b8" };
}

function ClaimBlock({
  doc,
  claim,
  letter,
  onJump,
}: {
  doc: { document_id: number; title: string | null };
  claim: ConflictRelationPublic["claim_a"];
  letter: "A" | "B";
  onJump?: (id: number) => void;
}) {
  return (
    <div
      style={{
        border: "1px solid var(--border-default)",
        borderRadius: 8,
        padding: "10px 12px",
        background: "var(--bg-surface, var(--bg-elevated))",
        flex: 1,
        minWidth: 0,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          marginBottom: 6,
        }}
      >
        <Tag style={{ background: "var(--bg-elevated)", border: "none" }}>
          Claim {letter}
        </Tag>
        <a
          onClick={(e) => {
            e.preventDefault();
            onJump?.(doc.document_id);
          }}
          href="#"
          style={{
            fontSize: 12,
            color: "var(--text-secondary)",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            overflow: "hidden",
            maxWidth: 220,
          }}
          title={doc.title ?? ""}
        >
          {doc.title ?? `Doc #${doc.document_id}`}
        </a>
      </div>
      <div style={{ fontSize: 13, lineHeight: 1.55, marginBottom: 6 }}>
        {claim.claim_text}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
        <Tag style={{ background: "rgba(59,130,246,0.08)", border: "none", color: "#93c5fd" }}>
          {claim.claim_type}
        </Tag>
        {claim.dataset && <Tag style={{ border: "none" }}>{claim.dataset}</Tag>}
        {claim.metric && <Tag style={{ border: "none" }}>{claim.metric}</Tag>}
        {claim.method && <Tag style={{ border: "none" }}>{claim.method}</Tag>}
      </div>
      {claim.evidence_text && (
        <div
          style={{
            marginTop: 8,
            fontSize: 12,
            color: "var(--text-secondary)",
            fontStyle: "italic",
            background: "var(--bg-elevated)",
            padding: "6px 8px",
            borderRadius: 6,
          }}
        >
          “{claim.evidence_text}”
        </div>
      )}
    </div>
  );
}

function ConflictCard({
  rel,
  onJump,
  onFeedback,
  pendingFeedback,
}: {
  rel: ConflictRelationPublic;
  onJump?: (id: number) => void;
  onFeedback: (rid: number, fb: "useful" | "dismissed") => void;
  pendingFeedback: number | null;
}) {
  const tone = relTone(rel.relation_type);
  return (
    <div
      data-testid={`conflict-card-${rel.id}`}
      style={{
        border: `1px solid ${tone.color}33`,
        borderRadius: 12,
        padding: 14,
        background: "var(--bg-surface, var(--bg-elevated))",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          marginBottom: 10,
          flexWrap: "wrap",
        }}
      >
        <Tag style={{ background: `${tone.color}1a`, color: tone.color, border: "none", fontWeight: 500 }}>
          {tone.label}
        </Tag>
        <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          置信度 {(rel.confidence * 100).toFixed(0)}%
        </span>
        {rel.reviewed_by_user && (
          <Tag color="default" style={{ border: "none" }}>
            已确认 / 已标注
          </Tag>
        )}
      </div>

      <div
        style={{
          display: "flex",
          gap: 12,
          marginBottom: 10,
          flexWrap: "wrap",
        }}
      >
        <ClaimBlock doc={rel.document_a} claim={rel.claim_a} letter="A" onJump={onJump} />
        <ClaimBlock doc={rel.document_b} claim={rel.claim_b} letter="B" onJump={onJump} />
      </div>

      {rel.reason_md && (
        <div
          style={{
            background: "var(--bg-elevated)",
            padding: "10px 12px",
            borderRadius: 8,
            fontSize: 13,
            color: "var(--text-primary)",
            marginBottom: 10,
          }}
        >
          <MarkdownView>{rel.reason_md}</MarkdownView>
        </div>
      )}

      <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
        <Button
          size="small"
          icon={<CheckOutlined />}
          loading={pendingFeedback === rel.id}
          onClick={() => onFeedback(rel.id, "useful")}
        >
          标记为有用
        </Button>
        <Button
          size="small"
          icon={<CloseOutlined />}
          loading={pendingFeedback === rel.id}
          onClick={() => onFeedback(rel.id, "dismissed")}
        >
          不成立
        </Button>
      </div>
    </div>
  );
}

function SignalsPanel({
  topicId,
  onJump,
}: {
  topicId: number;
  onJump?: (id: number) => void;
}) {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const [type, setType] = useState<string>("");
  const { data, isLoading } = useQuery({
    queryKey: ["signals", topicId, type],
    queryFn: () => listSignals(topicId, { signal_type: type || undefined, limit: 30 }),
    refetchInterval: 30_000,
  });
  const mut = useMutation({
    mutationFn: () => refreshSignals(topicId),
    onSuccess: () => {
      message.info("信号刷新已加入队列");
      qc.invalidateQueries({ queryKey: ["signals", topicId] });
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 12,
        }}
      >
        <Segmented
          size="small"
          value={type}
          onChange={(v) => setType(String(v))}
          options={[
            { label: "全部", value: "" },
            { label: "突破候选", value: "breakthrough_candidate" },
            { label: "高相关", value: "high_relevance" },
          ]}
        />
        <Button
          size="small"
          icon={<ReloadOutlined />}
          loading={mut.isPending}
          onClick={() => mut.mutate()}
          data-testid="signal-refresh-btn"
        >
          刷新信号
        </Button>
      </div>
      {isLoading ? (
        <Skeleton active />
      ) : (data ?? []).length === 0 ? (
        <Empty description="还没有信号，点击右上角“刷新信号”" />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {data!.map((s: DocumentSignalPublic) => (
            <div
              key={s.id}
              style={{
                padding: 12,
                border: "1px solid var(--border-default)",
                borderRadius: 10,
                background: "var(--bg-surface, var(--bg-elevated))",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 12,
                  marginBottom: 6,
                }}
              >
                <a
                  onClick={(e) => {
                    e.preventDefault();
                    onJump?.(s.document_id);
                  }}
                  href="#"
                  style={{ fontWeight: 500 }}
                >
                  {s.document_title ?? `Doc #${s.document_id}`}
                </a>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <Tag
                    style={{
                      background:
                        s.signal_type === "breakthrough_candidate"
                          ? "rgba(220,38,38,0.10)"
                          : "rgba(59,130,246,0.08)",
                      color:
                        s.signal_type === "breakthrough_candidate" ? "#fca5a5" : "#93c5fd",
                      border: "none",
                    }}
                  >
                    {s.signal_type === "breakthrough_candidate" ? "🔥 突破候选" : "高相关"}
                  </Tag>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>
                    {(s.score * 100).toFixed(0)}
                  </span>
                </div>
              </div>
              <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                {s.reason_md}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ConflictExplorerView({ topicId, onJumpDocument }: Props) {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const [relationType, setRelationType] = useState<string>("conflicts");
  const [pendingFb, setPendingFb] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["conflicts", topicId, relationType],
    queryFn: () =>
      listConflicts(topicId, {
        relation_type: relationType || undefined,
        min_confidence: 0.0,
        limit: 50,
      }),
    refetchInterval: 30_000,
  });

  const detectMut = useMutation({
    mutationFn: () => detectConflicts(topicId, true),
    onSuccess: () => {
      message.info("已开始扫描争议，预计 1-3 分钟，自动刷新");
      qc.invalidateQueries({ queryKey: ["conflicts", topicId] });
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const fbMut = useMutation({
    mutationFn: (vars: { rid: number; fb: "useful" | "dismissed" }) =>
      sendConflictFeedback(topicId, vars.rid, vars.fb),
    onMutate: (v) => setPendingFb(v.rid),
    onSettled: () => setPendingFb(null),
    onSuccess: () => {
      message.success("已记录反馈");
      qc.invalidateQueries({ queryKey: ["conflicts", topicId] });
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  return (
    <div data-testid="conflict-explorer-view">
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 12,
        }}
      >
        <div>
          <div
            style={{
              fontFamily: "var(--font-mono, monospace)",
              fontSize: 11,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--text-secondary)",
            }}
          >
            <AlertOutlined style={{ marginRight: 6 }} />
            Claim Conflict Explorer
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4 }}>
            UI 中所有"冲突"均为疑似信号，需要人工确认。
          </div>
        </div>
        <Button
          type="primary"
          icon={<ReloadOutlined />}
          loading={detectMut.isPending}
          onClick={() => detectMut.mutate()}
          data-testid="detect-conflicts-btn"
        >
          扫描争议
        </Button>
      </div>

      <div style={{ marginBottom: 14 }}>
        <Segmented
          options={RELATION_OPTIONS}
          value={relationType}
          onChange={(v) => setRelationType(String(v))}
          size="small"
        />
      </div>

      {isLoading ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : (data ?? []).length === 0 ? (
        <Empty
          description={
            relationType === "conflicts"
              ? "未发现高置信度疑似冲突。可点击扫描争议生成新的判断。"
              : "暂无该类别的关系数据"
          }
        />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {data!.map((r) => (
            <ConflictCard
              key={r.id}
              rel={r}
              onJump={onJumpDocument}
              onFeedback={(rid, fb) => fbMut.mutate({ rid, fb })}
              pendingFeedback={pendingFb}
            />
          ))}
        </div>
      )}

      <div style={{ marginTop: 28 }}>
        <Typography.Title level={5} style={{ margin: 0 }}>
          突破候选 / 高相关信号
        </Typography.Title>
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 10 }}>
          基于近期度 + 收藏 + 趋势词重叠的本地信号（外部引用数据不可用时降级）。
        </div>
        <SignalsPanel topicId={topicId} onJump={onJumpDocument} />
      </div>
    </div>
  );
}
