import { DeleteOutlined, PlusOutlined, PushpinFilled, PushpinOutlined } from "@ant-design/icons";
import { App, Button, Empty, Input, Modal, Skeleton } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useState } from "react";
import ReactMarkdown from "react-markdown";

import { apiErrorMessage } from "../api/client";
import { createNote, deleteNote, listNotes, updateNote } from "../api/intel";

interface Props {
  topicId: number;
}

export default function NotesView({ topicId }: Props) {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const [openCreate, setOpenCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["notes", topicId],
    queryFn: () => listNotes(topicId),
  });

  const create = useMutation({
    mutationFn: () =>
      createNote(topicId, {
        title: title.trim() || undefined,
        content_md: content.trim(),
        pinned: true,
      }),
    onSuccess: () => {
      message.success("已保存");
      setOpenCreate(false);
      setTitle("");
      setContent("");
      qc.invalidateQueries({ queryKey: ["notes", topicId] });
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const del = useMutation({
    mutationFn: (id: number) => deleteNote(topicId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notes", topicId] }),
  });

  const togglePin = useMutation({
    mutationFn: ({ id, pinned }: { id: number; pinned: boolean }) =>
      updateNote(topicId, id, { pinned }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notes", topicId] }),
  });

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-end",
          marginBottom: 20,
        }}
      >
        <div>
          <div className="page-eyebrow" style={{ marginBottom: 6 }}>
            Research Notes · Memory
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
            研究笔记
          </h3>
          <div style={{ fontSize: 12.5, color: "var(--text-tertiary)" }}>
            Pin 后的笔记会作为长期记忆参与该课题的问答。
          </div>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setOpenCreate(true)}
        >
          新建笔记
        </Button>
      </div>

      {isLoading ? (
        <Skeleton active />
      ) : !data || data.length === 0 ? (
        <Empty description="还没有笔记" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        data.map((n, idx) => (
          <div
            key={n.id}
            className={`note-card entry entry-${Math.min(idx + 1, 6)} ${
              n.pinned ? "pinned" : ""
            }`}
          >
            <div className="note-card-head">
              <div className="note-card-meta">
                {n.pinned && (
                  <span
                    className="pill accent"
                    style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
                  >
                    <PushpinFilled style={{ fontSize: 9 }} /> pinned
                  </span>
                )}
                <span className="pill ghost">{n.source_type}</span>
                {n.title && <span className="note-card-title">{n.title}</span>}
                <span className="note-card-time">
                  {dayjs(n.created_at).format("MM-DD HH:mm")}
                </span>
              </div>
              <div style={{ display: "flex", gap: 4 }}>
                <button
                  className="icon-btn"
                  style={{ width: 26, height: 26 }}
                  onClick={() =>
                    togglePin.mutate({ id: n.id, pinned: !n.pinned })
                  }
                  title={n.pinned ? "取消 Pin" : "Pin"}
                >
                  {n.pinned ? <PushpinFilled /> : <PushpinOutlined />}
                </button>
                <button
                  className="icon-btn"
                  style={{
                    width: 26,
                    height: 26,
                    color: "var(--text-tertiary)",
                  }}
                  onClick={() => del.mutate(n.id)}
                  title="删除"
                >
                  <DeleteOutlined />
                </button>
              </div>
            </div>
            <div className="note-card-body">
              <ReactMarkdown>{n.content_md}</ReactMarkdown>
            </div>
          </div>
        ))
      )}

      <Modal
        title="新建笔记"
        open={openCreate}
        onCancel={() => setOpenCreate(false)}
        onOk={() => create.mutate()}
        confirmLoading={create.isPending}
        okText="保存为 Pin"
        cancelText="取消"
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <Input
            placeholder="标题（可选）"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <Input.TextArea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="支持 Markdown"
            autoSize={{ minRows: 6, maxRows: 16 }}
          />
        </div>
      </Modal>
    </div>
  );
}
