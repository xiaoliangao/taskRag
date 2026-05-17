import { CheckCircleFilled, ReloadOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { Alert, App, Button, Checkbox, Empty, Modal, Skeleton } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useEffect, useMemo, useState } from "react";

import { apiErrorMessage } from "../api/client";
import {
  collectSelected,
  searchPreview,
  type PreviewItem,
} from "../api/topics";

interface Props {
  topicId: number;
  open: boolean;
  onClose: () => void;
}

const SOURCE_COLOR: Record<string, string> = {
  arxiv: "var(--accent)",
  openalex: "var(--info)",
  semantic_scholar: "#c19bff",
};

export default function SearchPickerModal({ topicId, open, onClose }: Props) {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const [picked, setPicked] = useState<Set<string>>(new Set());

  const preview = useQuery({
    queryKey: ["search-preview", topicId],
    queryFn: () => searchPreview(topicId, { limit: 20 }),
    enabled: open,
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: "always",
  });

  // Auto-select all non-existing items when results land
  useEffect(() => {
    if (preview.data) {
      const next = new Set<string>();
      for (const it of preview.data.items) {
        if (!it.already_in_topic) {
          next.add(itemKey(it));
        }
      }
      setPicked(next);
    }
  }, [preview.data]);

  const ingestMut = useMutation({
    mutationFn: (items: PreviewItem[]) => collectSelected(topicId, items),
    onSuccess: (r) => {
      message.success(`已派发入库 ${r.count} 篇 — 任务记录里可看进度`);
      qc.invalidateQueries({ queryKey: ["tasks", topicId] });
      qc.invalidateQueries({ queryKey: ["documents", topicId] });
      onClose();
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const items = preview.data?.items ?? [];
  const selectedList = useMemo(
    () => items.filter((it) => picked.has(itemKey(it))),
    [items, picked]
  );

  const toggle = (it: PreviewItem) => {
    const k = itemKey(it);
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  };

  const toggleAll = (select: boolean) => {
    if (select) {
      setPicked(
        new Set(items.filter((it) => !it.already_in_topic).map(itemKey))
      );
    } else {
      setPicked(new Set());
    }
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      width={920}
      destroyOnClose
      title={
        <div>
          <div className="page-eyebrow" style={{ marginBottom: 4 }}>
            Manual Collect · Search & Pick
          </div>
          <div
            style={{
              fontFamily: "var(--font-display)",
              fontStyle: "italic",
              fontSize: 22,
              fontWeight: 400,
              color: "var(--text-primary)",
              lineHeight: 1.2,
            }}
          >
            从搜索结果中挑选要入库的论文
          </div>
        </div>
      }
      footer={
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              color: "var(--text-tertiary)",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
            }}
          >
            已选 {selectedList.length} / {items.length}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Button onClick={onClose}>取消</Button>
            <Button onClick={() => toggleAll(false)} disabled={items.length === 0}>
              清空
            </Button>
            <Button onClick={() => toggleAll(true)} disabled={items.length === 0}>
              全选
            </Button>
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              disabled={selectedList.length === 0}
              loading={ingestMut.isPending}
              onClick={() => ingestMut.mutate(selectedList)}
            >
              入库 ({selectedList.length})
            </Button>
          </div>
        </div>
      }
    >
      {preview.isLoading ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : preview.isError ? (
        <Alert
          type="error"
          showIcon
          message="搜索失败"
          description={apiErrorMessage(preview.error)}
          action={
            <Button
              icon={<ReloadOutlined />}
              onClick={() => preview.refetch()}
            >
              重试
            </Button>
          }
        />
      ) : (
        <>
          {preview.data?.rate_limited_sources?.length ? (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 12 }}
              message={`部分源被限流：${preview.data.rate_limited_sources.join(", ")}`}
              description="已自动 fallback 到可用源。如果结果偏少，可稍后重试。"
            />
          ) : null}

          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              color: "var(--text-muted)",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              marginBottom: 12,
            }}
          >
            {items.length} 条搜索结果 · 已查询：
            {(preview.data?.sources_queried || []).join(" · ")}
          </div>

          {items.length === 0 ? (
            <Empty
              description="没有找到任何匹配论文"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          ) : (
            <div
              style={{
                maxHeight: "calc(100vh - 360px)",
                overflowY: "auto",
                paddingRight: 4,
              }}
            >
              {items.map((it) => {
                const k = itemKey(it);
                const isPicked = picked.has(k);
                const dim = it.already_in_topic;
                return (
                  <div
                    key={k}
                    onClick={() => !dim && toggle(it)}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "24px 1fr",
                      gap: 12,
                      padding: "12px 14px",
                      border: `1px solid ${
                        isPicked
                          ? "var(--accent-deep)"
                          : "var(--border-subtle)"
                      }`,
                      background: isPicked
                        ? "var(--accent-bg-soft)"
                        : "var(--bg-surface)",
                      borderRadius: "var(--radius-sm)",
                      marginBottom: 8,
                      cursor: dim ? "default" : "pointer",
                      opacity: dim ? 0.55 : 1,
                      transition: "all var(--d-fast) var(--ease-out)",
                    }}
                  >
                    <div style={{ paddingTop: 2 }}>
                      {dim ? (
                        <CheckCircleFilled
                          style={{ color: "var(--text-muted)" }}
                          title="已在本课题中"
                        />
                      ) : (
                        <Checkbox checked={isPicked} />
                      )}
                    </div>
                    <div>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "flex-start",
                          justifyContent: "space-between",
                          gap: 12,
                        }}
                      >
                        <div
                          style={{
                            fontWeight: 600,
                            fontSize: 13.5,
                            color: "var(--text-primary)",
                            lineHeight: 1.4,
                          }}
                        >
                          {it.title}
                        </div>
                        {dim && (
                          <span className="pill ghost" style={{ flexShrink: 0 }}>
                            已入库
                          </span>
                        )}
                      </div>
                      <div
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: 11,
                          color: "var(--text-tertiary)",
                          marginTop: 4,
                          display: "flex",
                          gap: 8,
                          flexWrap: "wrap",
                          alignItems: "center",
                        }}
                      >
                        <span style={{ color: SOURCE_COLOR[it.source] || "var(--text-secondary)" }}>
                          {it.source}
                        </span>
                        {it.published_at && (
                          <span>· {dayjs(it.published_at).format("YYYY-MM-DD")}</span>
                        )}
                        {it.authors?.length > 0 && (
                          <span>
                            · {it.authors.slice(0, 3).join(", ")}
                            {it.authors.length > 3 ? " 等" : ""}
                          </span>
                        )}
                        {it.matched_keyword && (
                          <span className="pill ghost">{it.matched_keyword}</span>
                        )}
                        <a
                          href={it.url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          style={{
                            marginLeft: "auto",
                            color: "var(--text-tertiary)",
                          }}
                        >
                          原文 ↗
                        </a>
                      </div>
                      {it.abstract && (
                        <div
                          style={{
                            fontSize: 12.5,
                            color: "var(--text-tertiary)",
                            marginTop: 8,
                            lineHeight: 1.5,
                            display: "-webkit-box",
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: "vertical",
                            overflow: "hidden",
                          }}
                        >
                          {it.abstract}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </Modal>
  );
}

function itemKey(it: PreviewItem): string {
  return `${it.source}|${it.external_id}`;
}
