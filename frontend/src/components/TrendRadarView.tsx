import { LineChartOutlined, ReloadOutlined, RightOutlined } from "@ant-design/icons";
import {
  App,
  Button,
  Drawer,
  Empty,
  Skeleton,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import MarkdownView from "./MarkdownView";
import { useMemo, useState } from "react";

import { apiErrorMessage } from "../api/client";
import {
  generateTrend,
  getLatestTrend,
  listDocumentsForTerm,
} from "../api/trends";
import type { TrendItem, TrendItemStatus } from "../types/api";

interface Props {
  topicId: number;
  onJumpDocument?: (docId: number) => void;
}

type StatusTone = {
  label: string;
  color: string;
};

const STATUS_TONE: Record<string, StatusTone> = {
  emerging: { label: "新兴", color: "#10b981" },
  rising: { label: "升温", color: "#3b82f6" },
  stable: { label: "稳定", color: "#94a3b8" },
  declining: { label: "降温", color: "#f97316" },
};

const TYPE_LABEL: Record<string, string> = {
  method: "方法",
  dataset: "数据集",
  metric: "指标",
  model: "模型",
  task: "任务",
  keyword: "关键词",
};

const WINDOW_DAYS = 60;

function fmtStatus(s: string): StatusTone {
  return STATUS_TONE[s] ?? { label: s, color: "#94a3b8" };
}

function fmtGrowth(g: number): string {
  if (g >= 1) return `+${(g * 100).toFixed(0)}%`;
  if (g <= -1) return `${(g * 100).toFixed(0)}%`;
  return `${(g * 100).toFixed(0)}%`;
}

function Heatmap({
  buckets,
  terms,
  values,
}: {
  buckets: string[];
  terms: string[];
  values: number[][];
}) {
  const max = useMemo(() => {
    let m = 0;
    for (const row of values) for (const v of row) if (v > m) m = v;
    return Math.max(1, m);
  }, [values]);

  if (!buckets.length || !terms.length) {
    return <Empty description="暂无热力数据" />;
  }

  return (
    <div
      style={{
        overflowX: "auto",
        border: "1px solid var(--border-default)",
        borderRadius: 8,
        padding: 12,
      }}
    >
      <table
        style={{
          borderCollapse: "separate",
          borderSpacing: 2,
          fontFamily: "var(--font-mono, monospace)",
          fontSize: 11,
        }}
      >
        <thead>
          <tr>
            <th
              style={{
                textAlign: "left",
                padding: "4px 8px",
                color: "var(--text-secondary)",
                fontWeight: 400,
              }}
            />
            {buckets.map((b) => (
              <th
                key={b}
                style={{
                  padding: "4px 6px",
                  color: "var(--text-secondary)",
                  fontWeight: 400,
                  textAlign: "center",
                  minWidth: 56,
                }}
              >
                {b}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {terms.map((t, rowIdx) => (
            <tr key={t}>
              <th
                style={{
                  textAlign: "left",
                  padding: "4px 8px",
                  color: "var(--text-primary)",
                  fontWeight: 500,
                  whiteSpace: "nowrap",
                }}
                title={t}
              >
                {t.length > 28 ? `${t.slice(0, 26)}…` : t}
              </th>
              {(values[rowIdx] ?? []).map((v, i) => {
                const intensity = v / max;
                const bg = v === 0
                  ? "rgba(148,163,184,0.08)"
                  : `rgba(59,130,246,${0.15 + 0.65 * intensity})`;
                return (
                  <td
                    key={`${t}-${buckets[i]}`}
                    title={`${t} · ${buckets[i]} · ${v}`}
                    style={{
                      background: bg,
                      color: v === 0 ? "var(--text-tertiary)" : "#fff",
                      textAlign: "center",
                      padding: "4px 0",
                      borderRadius: 4,
                      minWidth: 40,
                    }}
                  >
                    {v || ""}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TrendCard({
  item,
  onOpen,
}: {
  item: TrendItem;
  onOpen: (i: TrendItem) => void;
}) {
  const tone = fmtStatus(item.status);
  return (
    <div
      onClick={() => onOpen(item)}
      data-testid={`trend-item-${item.id}`}
      style={{
        padding: 14,
        border: "1px solid var(--border-default)",
        borderRadius: 10,
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
        background: "var(--bg-surface, var(--bg-elevated))",
        transition: "transform 0.08s ease",
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLDivElement).style.transform = "translateY(-1px)";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.transform = "translateY(0)";
      }}
    >
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <Typography.Text
            strong
            style={{
              fontSize: 14,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
              maxWidth: 360,
            }}
            title={item.term}
          >
            {item.term}
          </Typography.Text>
          <Tag
            style={{
              background: `${tone.color}1a`,
              color: tone.color,
              borderColor: "transparent",
              fontSize: 11,
            }}
          >
            {tone.label}
          </Tag>
          <Tag
            style={{
              background: "var(--bg-elevated)",
              borderColor: "transparent",
              fontSize: 11,
              color: "var(--text-secondary)",
            }}
          >
            {TYPE_LABEL[item.term_type] ?? item.term_type}
          </Tag>
        </div>
        <div
          style={{
            fontSize: 12,
            color: "var(--text-secondary)",
          }}
        >
          {item.explanation ??
            `近窗 ${item.frequency_recent} · 基线 ${item.frequency_baseline}`}
        </div>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 14,
          fontFamily: "var(--font-mono, monospace)",
          fontSize: 11,
        }}
      >
        <div style={{ textAlign: "right" }}>
          <div style={{ color: "var(--text-secondary)" }}>近窗</div>
          <div style={{ fontSize: 16, fontWeight: 500 }}>{item.frequency_recent}</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ color: "var(--text-secondary)" }}>增长</div>
          <div
            style={{
              fontSize: 16,
              fontWeight: 500,
              color: item.growth_rate >= 0 ? "#10b981" : "#f97316",
            }}
          >
            {fmtGrowth(item.growth_rate)}
          </div>
        </div>
        <Tooltip title={`置信度 ${(item.confidence * 100).toFixed(0)}%`}>
          <div style={{ textAlign: "right" }}>
            <div style={{ color: "var(--text-secondary)" }}>conf</div>
            <div style={{ fontSize: 16, fontWeight: 500 }}>
              {(item.confidence * 100).toFixed(0)}
            </div>
          </div>
        </Tooltip>
        <RightOutlined style={{ color: "var(--text-tertiary)" }} />
      </div>
    </div>
  );
}

export default function TrendRadarView({ topicId, onJumpDocument }: Props) {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const [active, setActive] = useState<TrendItem | null>(null);

  const { data: run, isLoading } = useQuery({
    queryKey: ["trend-latest", topicId, WINDOW_DAYS],
    queryFn: () => getLatestTrend(topicId, WINDOW_DAYS),
    refetchInterval: (q) => {
      const d = q.state.data;
      if (!d) return 5_000;
      if (d.status === "running" || d.status === "pending") return 4_000;
      return 60_000;
    },
  });

  const { data: termDocs } = useQuery({
    queryKey: ["trend-term-docs", topicId, active?.id],
    queryFn: () =>
      active ? listDocumentsForTerm(topicId, active.id) : Promise.resolve([]),
    enabled: !!active,
  });

  const mut = useMutation({
    mutationFn: () => generateTrend(topicId, WINDOW_DAYS),
    onSuccess: () => {
      message.info("趋势正在生成，几秒后自动刷新");
      qc.invalidateQueries({ queryKey: ["trend-latest", topicId, WINDOW_DAYS] });
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  if (isLoading) {
    return <Skeleton active paragraph={{ rows: 8 }} />;
  }

  const heatmap = (run?.heatmap ?? {}) as {
    buckets?: string[];
    terms?: string[];
    values?: number[][];
  };

  return (
    <div data-testid="trend-radar-view">
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 16,
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
              marginBottom: 4,
            }}
          >
            <LineChartOutlined style={{ marginRight: 6 }} />
            Research Radar · 近 {WINDOW_DAYS} 天
          </div>
          {run?.generated_at && (
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
              更新于 {dayjs(run.generated_at).format("YYYY-MM-DD HH:mm")}
            </div>
          )}
        </div>
        <Button
          type={run ? "default" : "primary"}
          icon={<ReloadOutlined />}
          loading={mut.isPending}
          onClick={() => mut.mutate()}
          data-testid="trend-generate-btn"
        >
          {run ? "重新生成" : "生成趋势"}
        </Button>
      </div>

      {!run && (
        <div
          style={{
            border: "1px dashed var(--border-default)",
            borderRadius: 10,
            padding: 28,
            textAlign: "center",
            color: "var(--text-secondary)",
          }}
        >
          还没有趋势快照。点击右上角"生成趋势"开始。
          <div style={{ marginTop: 6, fontSize: 12 }}>
            建议 Topic 内已有 ≥ 5 篇文档时再生成，否则趋势信号不显著。
          </div>
        </div>
      )}

      {run && run.status === "failed" && (
        <div
          style={{
            background: "rgba(249,115,22,0.08)",
            color: "#fdba74",
            borderRadius: 8,
            padding: 12,
            marginBottom: 16,
            fontSize: 13,
          }}
        >
          生成失败：{run.error_message ?? "未知错误"}
        </div>
      )}

      {run && run.summary_md && (
        <div
          style={{
            padding: 16,
            background: "var(--bg-elevated)",
            borderRadius: 10,
            marginBottom: 16,
            border: "1px solid var(--border-default)",
          }}
          data-testid="trend-summary"
        >
          <MarkdownView>{run.summary_md}</MarkdownView>
        </div>
      )}

      {run && (
        <>
          <div style={{ marginBottom: 16 }}>
            <Typography.Title level={5} style={{ margin: "0 0 8px" }}>
              热力图
            </Typography.Title>
            <Heatmap
              buckets={heatmap.buckets ?? []}
              terms={heatmap.terms ?? []}
              values={heatmap.values ?? []}
            />
          </div>

          <div>
            <Typography.Title level={5} style={{ margin: "0 0 8px" }}>
              趋势条目 · {run.items.length}
            </Typography.Title>
            {run.items.length === 0 ? (
              <Empty description="尚无趋势条目，可能是 Topic 文档过少" />
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {run.items.map((it) => (
                  <TrendCard key={it.id} item={it} onOpen={setActive} />
                ))}
              </div>
            )}
          </div>
        </>
      )}

      <Drawer
        title={active?.term ?? ""}
        open={!!active}
        onClose={() => setActive(null)}
        width={Math.min(520, window.innerWidth - 80)}
        data-testid="trend-term-drawer"
      >
        {active && (
          <>
            <div style={{ marginBottom: 12 }}>
              <Tag color={fmtStatus(active.status).color}>
                {fmtStatus(active.status).label}
              </Tag>
              <Tag>{TYPE_LABEL[active.term_type] ?? active.term_type}</Tag>
              <Tag>
                conf {(active.confidence * 100).toFixed(0)}%
              </Tag>
            </div>
            <div
              style={{
                fontSize: 13,
                color: "var(--text-secondary)",
                marginBottom: 16,
              }}
            >
              {active.explanation}
            </div>

            <Typography.Title level={5} style={{ margin: "0 0 8px" }}>
              证据论文 · {termDocs?.length ?? 0}
            </Typography.Title>
            {(termDocs ?? []).length === 0 && (
              <Empty description="暂无相关论文" />
            )}
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {(termDocs ?? []).map((d) => (
                <div
                  key={d.document_id}
                  onClick={() => onJumpDocument?.(d.document_id)}
                  style={{
                    padding: "10px 12px",
                    border: "1px solid var(--border-default)",
                    borderRadius: 8,
                    cursor: "pointer",
                  }}
                >
                  <div style={{ fontWeight: 500 }} title={d.title ?? ""}>
                    {d.title ?? `Document #${d.document_id}`}
                  </div>
                  <div
                    style={{
                      fontSize: 11,
                      color: "var(--text-secondary)",
                      marginTop: 4,
                    }}
                  >
                    {d.source ?? "—"} ·{" "}
                    {d.published_at
                      ? dayjs(d.published_at).format("YYYY-MM-DD")
                      : "未知日期"}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </Drawer>
    </div>
  );
}

// Silence unused for the StatusTone export type
export type { TrendItemStatus };
