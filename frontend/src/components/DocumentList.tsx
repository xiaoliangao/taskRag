import { EyeInvisibleOutlined, EyeOutlined, SearchOutlined, UploadOutlined } from "@ant-design/icons";
import { App, Empty, Input, Pagination, Skeleton, Tooltip, Upload } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useMemo, useState } from "react";

import { apiErrorMessage } from "../api/client";
import { listDocuments, uploadDocumentPdf } from "../api/documents";
import type { DocumentSummary } from "../types/api";
import DocumentDetailDrawer from "./DocumentDetailDrawer";

interface Props {
  topicId: number;
  /** "问这段" from a doc's PDF — prefilled question handed up to the chat. */
  onAsk?: (question: string) => void;
}

const PRIORITY_PILL: Record<string, string> = {
  high: "danger",
  medium: "warning",
  low: "ghost",
};
const PRIORITY_LABEL: Record<string, string> = {
  high: "高优先级",
  medium: "中优先级",
  low: "低优先级",
};

export default function DocumentList({ topicId, onAsk }: Props) {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [showLow, setShowLow] = useState(false);
  const [activeDocId, setActiveDocId] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["documents", topicId, page, q],
    queryFn: () =>
      listDocuments(topicId, { page, page_size: 20, q: q || undefined }),
  });

  const uploadMut = useMutation({
    mutationFn: (file: File) => uploadDocumentPdf(topicId, file),
    onSuccess: (res) => {
      message.success(`已入库 (${res.status})`);
      qc.invalidateQueries({ queryKey: ["documents", topicId] });
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const visibleItems = useMemo(() => {
    const items = data?.items || [];
    if (showLow) return items;
    return items.filter((d) => d.reading_priority !== "low");
  }, [data, showLow]);

  const lowCount = useMemo(
    () =>
      (data?.items || []).filter((d) => d.reading_priority === "low").length,
    [data]
  );

  return (
    <div>
      <div className="filter-bar">
        <SearchOutlined style={{ color: "var(--text-tertiary)" }} />
        <Input
          variant="borderless"
          placeholder="按标题搜索…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
          style={{ background: "transparent" }}
        />
        <Tooltip
          title={
            showLow
              ? `点击隐藏 ${lowCount} 篇低优先级`
              : `点击显示 ${lowCount} 篇低优先级`
          }
        >
          <button
            className="icon-btn"
            style={{
              color: showLow ? "var(--accent)" : "var(--text-tertiary)",
              width: 28,
              height: 28,
            }}
            onClick={() => setShowLow((v) => !v)}
          >
            {showLow ? <EyeOutlined /> : <EyeInvisibleOutlined />}
          </button>
        </Tooltip>
        {data && (
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              color: "var(--text-muted)",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
            }}
          >
            {visibleItems.length}
            {!showLow && lowCount > 0 && (
              <span style={{ color: "var(--text-muted)" }}>
                {" "}
                · {lowCount} hidden
              </span>
            )}
            <span style={{ color: "var(--text-muted)" }}> · {data.total} total</span>
          </div>
        )}
        <Upload
          accept=".pdf,application/pdf"
          showUploadList={false}
          maxCount={1}
          customRequest={({ file, onSuccess, onError }) => {
            uploadMut.mutate(file as File, {
              onSuccess: (r) => onSuccess?.(r),
              onError: (e) => onError?.(e as Error),
            });
          }}
        >
          <Tooltip title="上传本地 PDF 入库（≤ 20 MB）">
            <button
              className="icon-btn"
              style={{
                color: uploadMut.isPending ? "var(--accent)" : "var(--text-tertiary)",
                width: 28,
                height: 28,
              }}
              data-testid="doc-upload-btn"
            >
              <UploadOutlined />
            </button>
          </Tooltip>
        </Upload>
      </div>

      {isLoading ? (
        <Skeleton active paragraph={{ rows: 5 }} />
      ) : !data || data.items.length === 0 ? (
        <Empty
          description="还没有采集到文档，去任务记录页点击立即采集试试"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      ) : visibleItems.length === 0 ? (
        <Empty
          description={
            <span>
              所有文档都被判定为低优先级。
              <a
                style={{ color: "var(--accent)", marginLeft: 6 }}
                onClick={() => setShowLow(true)}
              >
                仍然显示
              </a>
            </span>
          }
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      ) : (
        <>
          <div>
            {visibleItems.map((d: DocumentSummary, i) => (
              <div
                key={d.id}
                className={`doc-row entry entry-${Math.min(i + 1, 6)}`}
                onClick={() => setActiveDocId(d.id)}
              >
                <div className="doc-row-head">
                  <div className="doc-row-title">{d.title}</div>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      flexShrink: 0,
                    }}
                  >
                    {d.reading_priority && (
                      <span className={`pill ${PRIORITY_PILL[d.reading_priority]}`}>
                        {PRIORITY_LABEL[d.reading_priority] || d.reading_priority}
                      </span>
                    )}
                    {d.abstract_only && (
                      <Tooltip title="未抓到全文 PDF,仅基于摘要建立索引;RAG/问答效果会比全文索引浅">
                        <span
                          style={{
                            fontFamily: "var(--font-mono)",
                            fontSize: 10,
                            letterSpacing: "0.05em",
                            padding: "1px 7px",
                            border: "1px solid var(--border-default)",
                            background: "var(--bg-inset)",
                            borderRadius: 999,
                            color: "var(--text-tertiary)",
                          }}
                        >
                          仅摘要
                        </span>
                      </Tooltip>
                    )}
                    <span
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: 10.5,
                        color: "var(--text-muted)",
                        paddingTop: 2,
                      }}
                    >
                      #{String(d.id).padStart(4, "0")}
                    </span>
                  </div>
                </div>
                <div className="doc-row-meta">
                  <span style={{ color: "var(--accent)" }}>{d.source}</span>
                  {d.published_at && (
                    <span>· 发布 {dayjs(d.published_at).format("YYYY-MM-DD")}</span>
                  )}
                  {d.authors && d.authors.length > 0 && (
                    <span>
                      · {d.authors.slice(0, 3).join(", ")}
                      {d.authors.length > 3 ? " 等" : ""}
                    </span>
                  )}
                  {d.matched_keyword && (
                    <span className="pill ghost" style={{ marginLeft: 4 }}>
                      {d.matched_keyword}
                    </span>
                  )}
                  {d.relevance_score != null && (
                    <span
                      style={{ marginLeft: "auto", color: "var(--text-muted)" }}
                    >
                      相关度 {d.relevance_score.toFixed(2)}
                    </span>
                  )}
                </div>
                {d.abstract && <div className="doc-row-abstract">{d.abstract}</div>}
              </div>
            ))}
          </div>

          <div style={{ marginTop: 20, textAlign: "right" }}>
            <Pagination
              current={page}
              total={data.total}
              pageSize={20}
              showSizeChanger={false}
              onChange={setPage}
              size="small"
            />
          </div>
        </>
      )}

      <DocumentDetailDrawer
        topicId={topicId}
        documentId={activeDocId}
        open={activeDocId != null}
        onClose={() => setActiveDocId(null)}
        onAsk={
          onAsk
            ? (q) => {
                setActiveDocId(null); // close this drawer; parent switches to chat
                onAsk(q);
              }
            : undefined
        }
      />
    </div>
  );
}
