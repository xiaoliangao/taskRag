import { DeleteOutlined, ReloadOutlined } from "@ant-design/icons";
import { App, Button, Drawer, Empty, Skeleton, Tag, Typography } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";

import { apiErrorMessage } from "../api/client";
import { deleteChatMemory, listChatMemory } from "../api/qa";
import MarkdownView from "./MarkdownView";

interface Props {
  topicId: number;
  open: boolean;
  onClose: () => void;
}

const MEMORY_TYPE_TONE: Record<string, string> = {
  user_goal: "#10b981",
  excluded_direction: "#f97316",
  finding: "#3b82f6",
  open_question: "#a855f7",
  preference: "#94a3b8",
};

export default function ChatMemoryDrawer({ topicId, open, onClose }: Props) {
  const qc = useQueryClient();
  const { message } = App.useApp();

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["chat-memory", topicId],
    queryFn: () => listChatMemory(topicId, 30),
    enabled: open,
  });

  const delMut = useMutation({
    mutationFn: (id: number) => deleteChatMemory(topicId, id),
    onSuccess: () => {
      message.success("已删除");
      qc.invalidateQueries({ queryKey: ["chat-memory", topicId] });
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  return (
    <Drawer
      title="对话长期记忆"
      width={Math.min(560, window.innerWidth - 80)}
      open={open}
      onClose={onClose}
      extra={
        <Button
          size="small"
          icon={<ReloadOutlined />}
          loading={isFetching}
          onClick={() => refetch()}
        >
          刷新
        </Button>
      }
    >
      <div
        style={{
          fontSize: 12,
          color: "var(--text-secondary)",
          marginBottom: 12,
        }}
      >
        会话累计 ≥ 6 条消息后系统自动总结成长期记忆并注入下次问答。
      </div>
      {isLoading ? (
        <Skeleton active paragraph={{ rows: 4 }} />
      ) : (data ?? []).length === 0 ? (
        <Empty description="还没有累积长期记忆" />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {data!.map((s) => (
            <div
              key={s.id}
              style={{
                padding: 12,
                border: "1px solid var(--border-default)",
                borderRadius: 8,
                background: "var(--bg-surface, var(--bg-elevated))",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 6,
                  gap: 8,
                }}
              >
                <div>
                  <Typography.Text strong>
                    Session #{s.chat_session_id}
                  </Typography.Text>
                  <span
                    style={{
                      marginLeft: 8,
                      fontSize: 11,
                      color: "var(--text-secondary)",
                    }}
                  >
                    {dayjs(s.generated_at).format("YYYY-MM-DD HH:mm")} ·{" "}
                    {s.message_count_at_gen} 条消息
                  </span>
                </div>
                <Button
                  size="small"
                  type="text"
                  icon={<DeleteOutlined />}
                  loading={delMut.isPending}
                  onClick={() => delMut.mutate(s.id)}
                />
              </div>
              <div style={{ fontSize: 13, marginBottom: 8 }}>
                <MarkdownView>{s.summary_md}</MarkdownView>
              </div>
              {(s.memory_items ?? []).length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {s.memory_items.map((item, idx) => (
                    <div
                      key={idx}
                      style={{
                        fontSize: 12,
                        padding: "4px 6px",
                        background: "var(--bg-elevated)",
                        borderRadius: 4,
                        borderLeft: `3px solid ${
                          MEMORY_TYPE_TONE[item.memory_type ?? "preference"] ??
                          "var(--text-tertiary)"
                        }`,
                      }}
                    >
                      <Tag
                        style={{
                          background: "transparent",
                          border: "none",
                          color:
                            MEMORY_TYPE_TONE[item.memory_type ?? "preference"] ??
                            "var(--text-tertiary)",
                          padding: 0,
                          marginRight: 6,
                          fontSize: 10,
                          textTransform: "uppercase",
                          fontFamily: "var(--font-mono)",
                        }}
                      >
                        {item.memory_type ?? "note"}
                      </Tag>
                      {item.content}
                      {typeof item.confidence === "number" && (
                        <span
                          style={{
                            marginLeft: 6,
                            color: "var(--text-tertiary)",
                            fontSize: 10,
                          }}
                        >
                          conf {(item.confidence * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Drawer>
  );
}
