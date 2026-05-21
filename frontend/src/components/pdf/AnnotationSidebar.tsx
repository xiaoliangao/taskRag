import { DeleteOutlined } from "@ant-design/icons";
import { Button, Empty, Popconfirm, Tag, Tooltip } from "antd";

import type { Annotation } from "../../api/annotations";

const KIND_TONE: Record<string, { color: string; label: string }> = {
  highlight: { color: "var(--accent)", label: "高亮" },
  comment: { color: "var(--info)", label: "批注" },
  note: { color: "#c19bff", label: "笔记" },
};

export default function AnnotationSidebar({
  annotations,
  onJump,
  onDelete,
}: {
  annotations: Annotation[];
  onJump: (a: Annotation) => void;
  onDelete: (a: Annotation) => void;
}) {
  return (
    <div
      style={{
        width: 280,
        borderLeft: "1px solid var(--border-subtle)",
        background: "var(--bg-canvas)",
        overflowY: "auto",
        padding: "12px 12px",
      }}
    >
      <div
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          letterSpacing: "0.12em",
          textTransform: "uppercase",
          color: "var(--text-tertiary)",
          marginBottom: 10,
        }}
      >
        我的标注 ({annotations.length})
      </div>

      {annotations.length === 0 ? (
        <Empty
          description="选中正文文字 → 在弹出工具栏选择高亮/批注/笔记"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      ) : (
        annotations.map((a) => {
          const tone = KIND_TONE[a.kind] ?? KIND_TONE.highlight;
          return (
            <div
              key={a.id}
              onClick={() => onJump(a)}
              style={{
                padding: "10px 12px",
                borderLeft: `3px solid ${tone.color}`,
                background: "var(--bg-surface)",
                borderRadius: 4,
                marginBottom: 8,
                cursor: "pointer",
                transition: "background var(--d-fast) var(--ease-out)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 4,
                }}
              >
                <Tag style={{ margin: 0 }}>
                  <span style={{ color: tone.color }}>{tone.label}</span>
                  <span
                    style={{ marginLeft: 6, color: "var(--text-tertiary)" }}
                  >
                    p.{a.page_number}
                  </span>
                </Tag>
                <Popconfirm
                  title="删除这条标注?"
                  okText="删除"
                  okType="danger"
                  cancelText="取消"
                  onConfirm={(e) => {
                    e?.stopPropagation();
                    onDelete(a);
                  }}
                >
                  <Tooltip title="删除">
                    <Button
                      type="text"
                      size="small"
                      icon={<DeleteOutlined />}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </Tooltip>
                </Popconfirm>
              </div>
              <div
                style={{
                  fontSize: 12.5,
                  color: "var(--text-secondary)",
                  lineHeight: 1.5,
                  display: "-webkit-box",
                  WebkitLineClamp: 3,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                }}
              >
                {a.selected_text}
              </div>
              {a.comment_md && (
                <div
                  style={{
                    marginTop: 6,
                    paddingTop: 6,
                    borderTop: "1px dashed var(--border-subtle)",
                    fontSize: 12,
                    color: "var(--text-tertiary)",
                    fontStyle: "italic",
                  }}
                >
                  {a.comment_md}
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}
