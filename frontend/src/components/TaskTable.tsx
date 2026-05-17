import {
  CaretDownOutlined,
  CaretRightOutlined,
  RedoOutlined,
  ReloadOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { App, Button, Skeleton } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";

import { apiErrorMessage } from "../api/client";
import { listTasks, retryTask } from "../api/tasks";
import type { TaskItem } from "../types/api";
import SearchPickerModal from "./SearchPickerModal";

interface Props {
  topicId: number;
}

const STATUS_PILL: Record<string, string> = {
  pending: "ghost",
  running: "info",
  retrying: "warning",
  success: "success",
  failed: "danger",
  cancelled: "ghost",
};

const STEP_LABEL: Record<string, string> = {
  searching: "搜索中",
  ingesting: "解析入库中",
  done: "完成",
};

export default function TaskTable({ topicId }: Props) {
  const qc = useQueryClient();
  const { message: _msg } = App.useApp();
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [pickerOpen, setPickerOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["tasks", topicId],
    queryFn: () => listTasks(topicId),
    refetchInterval: 3000,
  });

  const retryMut = useMutation({
    mutationFn: (id: number) => retryTask(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks", topicId] }),
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const toggle = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <div className="page-eyebrow">Collection log · {data?.total ?? 0} runs</div>
        <div style={{ display: "flex", gap: 8 }}>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => qc.invalidateQueries({ queryKey: ["tasks", topicId] })}
          >
            刷新
          </Button>
          <Button
            type="primary"
            icon={<SearchOutlined />}
            onClick={() => setPickerOpen(true)}
          >
            手动采集
          </Button>
        </div>
      </div>

      <div
        style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-md)",
          overflow: "hidden",
        }}
      >
        <div className="task-row head">
          <span>ID</span>
          <span>SOURCE</span>
          <span>TRIGGER</span>
          <span>STATUS</span>
          <span>RESULT / PROGRESS</span>
          <span>STARTED</span>
          <span>FINISHED</span>
          <span></span>
        </div>
        {isLoading ? (
          <div style={{ padding: 16 }}>
            <Skeleton active paragraph={{ rows: 3 }} />
          </div>
        ) : !data || data.items.length === 0 ? (
          <div
            style={{
              padding: 40,
              textAlign: "center",
              color: "var(--text-muted)",
              fontFamily: "var(--font-display)",
              fontStyle: "italic",
            }}
          >
            还没有任务记录
          </div>
        ) : (
          data.items.map((t: TaskItem) => {
            const isOpen = expanded.has(t.id);
            const p = t.progress;
            const isRunning = t.status === "running" || t.status === "pending";
            const pct =
              p && p.total
                ? Math.min(100, Math.round(((p.processed ?? 0) / p.total) * 100))
                : null;

            return (
              <div key={t.id}>
                <div
                  className="task-row"
                  onClick={() => toggle(t.id)}
                  style={{ cursor: "pointer" }}
                >
                  <span className="num">
                    {isOpen ? <CaretDownOutlined /> : <CaretRightOutlined />} #{t.id}
                  </span>
                  <span style={{ color: "var(--accent)" }}>{t.source}</span>
                  <span>{t.trigger}</span>
                  <span>
                    <span className={`pill ${STATUS_PILL[t.status] || "ghost"}`}>
                      {t.status}
                    </span>
                  </span>
                  <span>
                    {isRunning && p ? (
                      <span
                        style={{ display: "flex", alignItems: "center", gap: 8 }}
                      >
                        <span
                          style={{
                            flex: 1,
                            height: 4,
                            background: "var(--bg-hover)",
                            borderRadius: 999,
                            overflow: "hidden",
                            minWidth: 60,
                            maxWidth: 140,
                          }}
                        >
                          <span
                            style={{
                              display: "block",
                              height: "100%",
                              width: `${pct ?? 0}%`,
                              background: "var(--accent)",
                              transition: "width var(--d-slow) var(--ease-out)",
                            }}
                          />
                        </span>
                        <span
                          style={{
                            color: "var(--text-secondary)",
                            fontSize: 11,
                          }}
                        >
                          {p.processed ?? 0}/{p.total ?? "?"}
                          {pct != null ? ` · ${pct}%` : ""}
                        </span>
                      </span>
                    ) : (
                      <span style={{ color: "var(--text-tertiary)" }}>
                        +{t.new_docs_count}
                        <span style={{ color: "var(--text-muted)" }}>
                          {" "}
                          · ↻{t.reused_docs_count} · –{t.skipped_docs_count}
                        </span>
                      </span>
                    )}
                  </span>
                  <span>
                    {t.started_at
                      ? dayjs(t.started_at).format("MM-DD HH:mm:ss")
                      : "—"}
                  </span>
                  <span>
                    {t.finished_at
                      ? dayjs(t.finished_at).format("MM-DD HH:mm:ss")
                      : "—"}
                  </span>
                  <span onClick={(e) => e.stopPropagation()}>
                    {t.status === "failed" && (
                      <Button
                        size="small"
                        icon={<RedoOutlined />}
                        onClick={() => retryMut.mutate(t.id)}
                        loading={retryMut.isPending}
                      />
                    )}
                  </span>
                </div>

                {isOpen && <TaskDetail task={t} />}
              </div>
            );
          })
        )}
      </div>

      <SearchPickerModal
        topicId={topicId}
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
      />
    </div>
  );
}

function TaskDetail({ task }: { task: TaskItem }) {
  const p = task.progress;
  return (
    <div
      style={{
        background: "var(--bg-canvas)",
        borderBottom: "1px solid var(--border-subtle)",
        borderTop: "1px solid var(--border-subtle)",
        padding: "14px 20px",
        fontSize: 12.5,
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 24,
        }}
      >
        <div>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 10.5,
              color: "var(--text-muted)",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              marginBottom: 8,
            }}
          >
            progress
          </div>
          {p?.step ? (
            <div style={{ color: "var(--text-secondary)" }}>
              <div style={{ marginBottom: 6 }}>
                当前阶段：
                <span style={{ color: "var(--accent)", fontWeight: 500 }}>
                  {STEP_LABEL[p.step] || p.step}
                </span>
              </div>
              {p.total != null && (
                <div style={{ marginBottom: 4 }}>
                  已处理 <b>{p.processed ?? 0}</b> / 共 <b>{p.total}</b>
                  {p.new != null &&
                    `（新 ${p.new} · 复用 ${p.reused ?? 0} · 跳过 ${p.skipped ?? 0}）`}
                </div>
              )}
              {p.current_title && (
                <div
                  style={{
                    color: "var(--text-tertiary)",
                    fontFamily: "var(--font-mono)",
                    fontSize: 11.5,
                    marginTop: 6,
                  }}
                >
                  正在处理：{p.current_title}
                </div>
              )}
              {p.last_error && (
                <div
                  style={{
                    color: "var(--warning)",
                    fontSize: 11.5,
                    marginTop: 6,
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  最近一次跳过：{p.last_error}
                </div>
              )}
            </div>
          ) : (
            <div style={{ color: "var(--text-muted)", fontStyle: "italic" }}>
              暂无进度数据（旧任务或刚启动）
            </div>
          )}
        </div>

        <div>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 10.5,
              color: "var(--text-muted)",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              marginBottom: 8,
            }}
          >
            outcome
          </div>
          {task.error_msg ? (
            <div
              style={{
                background: "var(--danger-bg)",
                border: "1px solid rgba(255,122,107,0.2)",
                borderRadius: 4,
                padding: "10px 12px",
                color: "var(--danger)",
                fontSize: 12.5,
                lineHeight: 1.5,
                whiteSpace: "pre-wrap",
              }}
            >
              {task.error_msg}
            </div>
          ) : task.status === "success" ? (
            <div style={{ color: "var(--text-secondary)" }}>
              新增 <b style={{ color: "var(--success)" }}>{task.new_docs_count}</b> ·
              复用 <b>{task.reused_docs_count}</b> · 跳过{" "}
              <b style={{ color: "var(--warning)" }}>{task.skipped_docs_count}</b>
              {task.started_at && task.finished_at && (
                <div
                  style={{
                    color: "var(--text-muted)",
                    fontFamily: "var(--font-mono)",
                    fontSize: 11,
                    marginTop: 4,
                  }}
                >
                  用时{" "}
                  {Math.round(
                    (dayjs(task.finished_at).valueOf() -
                      dayjs(task.started_at).valueOf()) /
                      1000
                  )}{" "}
                  秒
                </div>
              )}
            </div>
          ) : (
            <div style={{ color: "var(--text-muted)", fontStyle: "italic" }}>
              任务尚未结束
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
