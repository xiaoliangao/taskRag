import { BookOutlined, ReloadOutlined } from "@ant-design/icons";
import { App, Button, Empty, Skeleton } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { patchDocState } from "../api/briefings";
import { apiErrorMessage } from "../api/client";
import { generateReadingPath, getLatestReadingPath } from "../api/intel";

const STAGE_LABELS: Record<string, string> = {
  foundation: "奠基 · Foundation",
  core: "核心 · Core",
  advanced: "进阶 · Advanced",
  latest: "最新 · Latest",
  optional: "可选 · Optional",
};

interface Props {
  topicId: number;
  onJumpDocument?: (docId: number) => void;
}

export default function ReadingPathView({ topicId, onJumpDocument }: Props) {
  const qc = useQueryClient();
  const { message } = App.useApp();

  const { data, isLoading } = useQuery({
    queryKey: ["reading-path", topicId],
    queryFn: () => getLatestReadingPath(topicId),
    refetchInterval: 20_000,
  });

  const gen = useMutation({
    mutationFn: () => generateReadingPath(topicId),
    onSuccess: () => {
      message.info("已派发阅读路径生成");
      qc.invalidateQueries({ queryKey: ["reading-path", topicId] });
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const readMut = useMutation({
    mutationFn: ({ docId, status }: { docId: number; status: string }) =>
      patchDocState(topicId, docId, { status: status as any }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reading-path", topicId] }),
  });

  if (isLoading) return <Skeleton active paragraph={{ rows: 6 }} />;

  if (!data) {
    return (
      <div
        style={{
          padding: 60,
          textAlign: "center",
          background: "var(--bg-surface)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-md)",
        }}
      >
        <Empty
          description="还没有阅读路径"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        >
          <Button
            type="primary"
            icon={<BookOutlined />}
            loading={gen.isPending}
            onClick={() => gen.mutate()}
          >
            生成阅读路径
          </Button>
        </Empty>
      </div>
    );
  }

  const total = data.items.length;
  const readCount = data.items.filter((it) => it.user_status === "read").length;
  const pct = total ? Math.round((readCount / total) * 100) : 0;
  const grouped = data.items.reduce<Record<string, typeof data.items>>((acc, it) => {
    const s = it.stage || "optional";
    (acc[s] ||= []).push(it);
    return acc;
  }, {});
  const stageOrder = ["foundation", "core", "advanced", "latest", "optional"];

  return (
    <div>
      {/* Header card */}
      <div
        className="tr-card entry"
        style={{
          padding: "24px 28px",
          marginBottom: 20,
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
            <div className="page-eyebrow" style={{ marginBottom: 6 }}>
              Reading Path · {readCount} / {total} 已读
            </div>
            <h3
              style={{
                fontFamily: "var(--font-display)",
                fontStyle: "italic",
                fontSize: 26,
                fontWeight: 400,
                color: "var(--text-primary)",
                margin: 0,
                marginBottom: 4,
              }}
            >
              {data.title}
            </h3>
            <div style={{ fontSize: 12.5, color: "var(--text-tertiary)" }}>
              {data.description}
            </div>
          </div>
          <Button
            icon={<ReloadOutlined />}
            loading={gen.isPending}
            onClick={() => gen.mutate()}
          >
            重新生成
          </Button>
        </div>

        {/* Progress bar */}
        <div style={{ marginTop: 20 }}>
          <div
            style={{
              height: 4,
              background: "var(--bg-hover)",
              borderRadius: 999,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${pct}%`,
                height: "100%",
                background: "var(--accent)",
                transition: "width var(--d-slow) var(--ease-out)",
              }}
            />
          </div>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              color: "var(--text-tertiary)",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              marginTop: 8,
              display: "flex",
              justifyContent: "space-between",
            }}
          >
            <span>{pct}% complete</span>
            <span>{total - readCount} remaining</span>
          </div>
        </div>
      </div>

      {stageOrder
        .filter((s) => grouped[s]?.length)
        .map((stage, sidx) => {
          const items = grouped[stage];
          const stageRead = items.filter((it) => it.user_status === "read").length;
          const stageAllDone = stageRead === items.length;
          return (
            <div key={stage} className={`stage-block entry entry-${Math.min(sidx + 2, 6)}`}>
              <div className="stage-head">
                <div className={`stage-num ${stageAllDone ? "active" : ""}`}>
                  {sidx + 1}
                </div>
                <div className="stage-label">{STAGE_LABELS[stage] || stage}</div>
                <div className="stage-count">
                  {stageRead} / {items.length}
                </div>
              </div>
              {items.map((it) => {
                const done = it.user_status === "read";
                return (
                  <div key={it.id} className={`reading-item ${done ? "done" : ""}`}>
                    <div
                      className={`reading-check ${done ? "done" : ""}`}
                      onClick={() =>
                        readMut.mutate({
                          docId: it.document_id,
                          status: done ? "unread" : "read",
                        })
                      }
                    >
                      {done ? "✓" : ""}
                    </div>
                    <div>
                      <div
                        className="reading-title"
                        onClick={() => onJumpDocument?.(it.document_id)}
                      >
                        {it.document_title}
                      </div>
                      {it.reason && <div className="reading-reason">{it.reason}</div>}
                    </div>
                    <div className="reading-time">~{it.expected_minutes ?? 15} min</div>
                  </div>
                );
              })}
            </div>
          );
        })}

      {data.items.length === 0 && (
        <Empty description="路径暂无条目（可能文档过少）" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}
    </div>
  );
}
