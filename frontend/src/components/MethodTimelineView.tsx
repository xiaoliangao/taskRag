import { ClockCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import { App, Button, Empty, Skeleton, Tag, Typography } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useMemo } from "react";

import { apiErrorMessage } from "../api/client";
import { getMethodTimeline, rebuildMethodTimeline } from "../api/methods";

interface Props {
  topicId: number;
  onJumpDocument?: (docId: number) => void;
}

const RELATION_LABEL: Record<string, { label: string; color: string }> = {
  improves: { label: "改进", color: "#10b981" },
  extends: { label: "扩展", color: "#3b82f6" },
  replaces: { label: "取代", color: "#f97316" },
  combines: { label: "融合", color: "#a855f7" },
  evaluates: { label: "评估", color: "#94a3b8" },
  compares_with: { label: "对比", color: "#fbbf24" },
};

export default function MethodTimelineView({ topicId, onJumpDocument }: Props) {
  const qc = useQueryClient();
  const { message } = App.useApp();

  const { data, isLoading } = useQuery({
    queryKey: ["method-timeline", topicId],
    queryFn: () => getMethodTimeline(topicId),
  });

  const rebuild = useMutation({
    mutationFn: () => rebuildMethodTimeline(topicId, true),
    onSuccess: () => {
      message.info("时间线重建已加入队列，约 30 秒…");
      // poll a few times
      setTimeout(
        () => qc.invalidateQueries({ queryKey: ["method-timeline", topicId] }),
        15_000,
      );
      setTimeout(
        () => qc.invalidateQueries({ queryKey: ["method-timeline", topicId] }),
        35_000,
      );
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  // Group methods by year for the timeline visualization
  const groupedByYear = useMemo(() => {
    const groups = new Map<string, typeof data.methods>();
    if (!data) return groups;
    for (const m of data.methods) {
      const year = m.first_seen_at
        ? dayjs(m.first_seen_at).format("YYYY")
        : "未知";
      if (!groups.has(year)) groups.set(year, []);
      groups.get(year)!.push(m);
    }
    return groups;
  }, [data]);

  const methodById = useMemo(() => {
    const m = new Map<number, string>();
    for (const x of data?.methods ?? []) m.set(x.id, x.name);
    return m;
  }, [data]);

  return (
    <div data-testid="method-timeline-view">
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
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--text-secondary)",
            }}
          >
            <ClockCircleOutlined style={{ marginRight: 6 }} />
            METHOD TIMELINE
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4 }}>
            方法实体按"首次出现年份"分桶；演化关系由 LLM 基于通用领域知识推断（标 confidence）。
          </div>
        </div>
        <Button
          icon={<ReloadOutlined />}
          loading={rebuild.isPending}
          onClick={() => rebuild.mutate()}
          data-testid="rebuild-timeline-btn"
        >
          重建时间线
        </Button>
      </div>

      {isLoading ? (
        <Skeleton active />
      ) : !data || data.methods.length === 0 ? (
        <Empty description="还没有方法时间线 — 先建 Trend Radar 然后点重建" />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <Typography.Title level={5} style={{ margin: "0 0 8px" }}>
              方法演化轴
            </Typography.Title>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 12,
                paddingLeft: 12,
                borderLeft: "2px solid var(--accent-dim)",
              }}
            >
              {Array.from(groupedByYear.entries())
                .sort((a, b) => a[0].localeCompare(b[0]))
                .map(([year, ms]) => (
                  <div key={year} style={{ display: "flex", gap: 14 }}>
                    <div
                      style={{
                        minWidth: 56,
                        fontFamily: "var(--font-mono)",
                        fontWeight: 600,
                        color: "var(--accent)",
                      }}
                    >
                      {year}
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {ms.map((m) => (
                        <span
                          key={m.id}
                          onClick={() =>
                            m.first_seen_document_id &&
                            onJumpDocument?.(m.first_seen_document_id)
                          }
                          style={{
                            padding: "4px 10px",
                            borderRadius: 999,
                            border: "1px solid var(--border-default)",
                            background: "var(--bg-elevated)",
                            cursor: m.first_seen_document_id ? "pointer" : "default",
                            fontSize: 12,
                          }}
                          title={`docs: ${m.document_count}`}
                        >
                          {m.name}
                          <span
                            style={{
                              marginLeft: 6,
                              color: "var(--text-tertiary)",
                              fontFamily: "var(--font-mono)",
                              fontSize: 10,
                            }}
                          >
                            {m.document_count}
                          </span>
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
            </div>
          </div>

          <div>
            <Typography.Title level={5} style={{ margin: "0 0 8px" }}>
              演化关系 ({data.edges.length})
            </Typography.Title>
            {data.edges.length === 0 ? (
              <Empty image={null} description="尚无演化关系;点“重建时间线”让 LLM 推断" />
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {data.edges.map((e) => {
                  const tone =
                    RELATION_LABEL[e.relation_type] ?? {
                      label: e.relation_type,
                      color: "var(--text-secondary)",
                    };
                  return (
                    <div
                      key={e.id}
                      style={{
                        padding: "8px 12px",
                        border: "1px solid var(--border-default)",
                        borderLeft: `3px solid ${tone.color}`,
                        borderRadius: 6,
                        background: "var(--bg-surface, var(--bg-elevated))",
                        fontSize: 13,
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          flexWrap: "wrap",
                        }}
                      >
                        <span style={{ fontWeight: 500 }}>
                          {methodById.get(e.from_method_id) ?? "?"}
                        </span>
                        <Tag
                          style={{
                            background: `${tone.color}1a`,
                            color: tone.color,
                            border: "none",
                            fontSize: 11,
                          }}
                        >
                          {tone.label}
                        </Tag>
                        <span style={{ fontWeight: 500 }}>
                          {methodById.get(e.to_method_id) ?? "?"}
                        </span>
                        <span
                          style={{
                            color: "var(--text-tertiary)",
                            fontFamily: "var(--font-mono)",
                            fontSize: 11,
                          }}
                        >
                          conf {(e.confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                      {e.explanation && (
                        <div
                          style={{
                            fontSize: 12,
                            color: "var(--text-secondary)",
                            marginTop: 4,
                          }}
                        >
                          {e.explanation}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
