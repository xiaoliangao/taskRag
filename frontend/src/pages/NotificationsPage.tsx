import { CheckCircleOutlined } from "@ant-design/icons";
import { App, Button, Empty, Skeleton } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";

import { listNotifications, markAllRead, markRead } from "../api/notifications";
import type { NotificationItem } from "../types/api";

const TYPE_GLYPH: Record<string, string> = {
  task_done: "✓",
  task_failed: "!",
  system: "i",
};

export default function NotificationsPage() {
  const qc = useQueryClient();
  const { message } = App.useApp();

  const { data, isLoading } = useQuery({
    queryKey: ["notifications-page"],
    queryFn: () => listNotifications({ page_size: 50 }),
    refetchInterval: 15_000,
  });

  const readMut = useMutation({
    mutationFn: (id: number) => markRead(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications-page"] }),
  });

  const allMut = useMutation({
    mutationFn: () => markAllRead(),
    onSuccess: (r) => {
      message.success(`已全部标记为已读（${r.updated_count}）`);
      qc.invalidateQueries({ queryKey: ["notifications-page"] });
      qc.invalidateQueries({ queryKey: ["notifications-bell"] });
    },
  });

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
          marginBottom: 28,
        }}
      >
        <div>
          <div className="page-eyebrow">Notifications · {data?.unread_count ?? 0} unread</div>
          <h1 className="page-title">
            来自<span style={{ color: "var(--accent)", fontStyle: "italic" }}>系统</span>的消息
          </h1>
        </div>
        <Button
          icon={<CheckCircleOutlined />}
          loading={allMut.isPending}
          onClick={() => allMut.mutate()}
        >
          全部标记已读
        </Button>
      </div>

      <div
        style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-md)",
          overflow: "hidden",
        }}
      >
        {isLoading ? (
          <div style={{ padding: 24 }}>
            <Skeleton active />
          </div>
        ) : !data || data.items.length === 0 ? (
          <div style={{ padding: 60 }}>
            <Empty description="暂无通知" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          </div>
        ) : (
          data.items.map((n: NotificationItem, idx) => {
            const isUnread = n.read_at == null;
            return (
              <div
                key={n.id}
                className={`notif-row ${isUnread ? "unread" : ""} entry entry-${Math.min(
                  idx + 1,
                  6
                )}`}
              >
                <div className={`notif-icon ${n.type}`}>{TYPE_GLYPH[n.type] || "·"}</div>
                <div>
                  <div className="notif-title">{n.title}</div>
                  <div className="notif-body">{n.body}</div>
                  <div className="notif-time">
                    {dayjs(n.created_at).format("YYYY-MM-DD HH:mm:ss")}
                  </div>
                </div>
                <div>
                  {isUnread ? (
                    <button
                      className="icon-btn"
                      onClick={() => readMut.mutate(n.id)}
                      title="标记已读"
                      style={{ width: 28, height: 28 }}
                    >
                      <CheckCircleOutlined />
                    </button>
                  ) : (
                    <div className="notif-actions">
                      read · {dayjs(n.read_at!).format("MM-DD HH:mm")}
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
