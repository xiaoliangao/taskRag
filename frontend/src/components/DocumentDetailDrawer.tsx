import {
  DownloadOutlined,
  FilePdfOutlined,
  LinkOutlined,
  StarFilled,
  StarOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, Drawer, Skeleton, Tabs } from "antd";
import dayjs from "dayjs";
import { useEffect, useState } from "react";

import {
  favoriteDocument,
  getDocument,
  getDocumentPdfBlobUrl,
  unfavoriteDocument,
} from "../api/documents";
import BriefingPanel from "./BriefingPanel";
import PdfReader from "./pdf/PdfReader";

interface Props {
  topicId: number;
  documentId: number | null;
  open: boolean;
  onClose: () => void;
}

export default function DocumentDetailDrawer({ topicId, documentId, open, onClose }: Props) {
  const { message } = App.useApp();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["document", topicId, documentId],
    queryFn: () => getDocument(topicId, documentId!),
    enabled: open && documentId != null,
  });

  const favoriteMut = useMutation({
    mutationFn: (next: boolean) =>
      next ? favoriteDocument(documentId!) : unfavoriteDocument(documentId!),
    onMutate: async (next) => {
      // Optimistic flip — the star is a noisy interaction; the server round-trip
      // shouldn't make it feel laggy. Roll back on error.
      await qc.cancelQueries({ queryKey: ["document", topicId, documentId] });
      const prev = qc.getQueryData<typeof data>(["document", topicId, documentId]);
      if (prev) {
        qc.setQueryData(["document", topicId, documentId], { ...prev, favorite: next });
      }
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(["document", topicId, documentId], ctx.prev);
      message.error("收藏操作失败,已回退");
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["my-favorites"] });
      qc.invalidateQueries({ queryKey: ["my-recommendations"] });
    },
  });

  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);

  useEffect(() => {
    if (!open || documentId == null) {
      setPdfUrl(null);
      setPdfError(null);
      return;
    }
    let createdUrl: string | null = null;
    let cancelled = false;
    setPdfLoading(true);
    setPdfError(null);
    setPdfUrl(null);
    getDocumentPdfBlobUrl(topicId, documentId)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        createdUrl = url;
        setPdfUrl(url);
      })
      .catch((e) => {
        if (!cancelled) {
          setPdfError(
            e?.response?.status === 404
              ? "该文档暂无 PDF（仅有摘要）"
              : "PDF 加载失败"
          );
        }
      })
      .finally(() => {
        if (!cancelled) setPdfLoading(false);
      });
    return () => {
      cancelled = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [open, topicId, documentId]);

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width="92vw"
      destroyOnClose
      styles={{
        // Flex column so the Tabs panel can stretch to fill the remaining
        // height — gives the PDF tab room to breathe instead of the previous
        // calc(100vh - 360px) cap.
        body: {
          padding: 16,
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
        },
      }}
      title={
        data ? (
          <div>
            <div
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 10.5,
                color: "var(--text-tertiary)",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                marginBottom: 4,
              }}
            >
              <span style={{ color: "var(--accent)" }}>{data.source}</span> ·
              #{String(data.id).padStart(4, "0")}
            </div>
            <div
              style={{
                fontFamily: "var(--font-display)",
                fontStyle: "italic",
                fontSize: 22,
                color: "var(--text-primary)",
                fontWeight: 400,
                lineHeight: 1.2,
              }}
            >
              {data.title}
            </div>
          </div>
        ) : (
          "文档详情"
        )
      }
      extra={
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {data && documentId != null && (
            <Button
              size="small"
              icon={
                data.favorite ? (
                  <StarFilled style={{ color: "#f5c518" }} />
                ) : (
                  <StarOutlined />
                )
              }
              onClick={() => favoriteMut.mutate(!data.favorite)}
              loading={favoriteMut.isPending}
              title={data.favorite ? "取消收藏" : "收藏到「我的收藏」"}
            >
              {data.favorite ? "已收藏" : "收藏"}
            </Button>
          )}
          {pdfUrl && (
            <>
              <Button
                size="small"
                icon={<DownloadOutlined />}
                href={pdfUrl}
                download={`${data?.source}_${documentId}.pdf`}
              >
                下载
              </Button>
              <Button
                size="small"
                icon={<FilePdfOutlined />}
                href={pdfUrl}
                target="_blank"
              >
                新窗口
              </Button>
            </>
          )}
        </div>
      }
    >
      {isLoading || !data ? (
        <Skeleton active />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
          {/* Metadata — compact one-line layout so it doesn't steal PDF height */}
          <div
            style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-md)",
              padding: "8px 14px",
              marginBottom: 8,
              display: "flex",
              flexWrap: "wrap",
              gap: 18,
              alignItems: "center",
              fontSize: 12,
            }}
          >
            <span className="doc-meta-label">authors</span>
            <span style={{ color: "var(--text-primary)", flex: 1, minWidth: 200 }}>
              {(data.authors || []).slice(0, 4).join(", ") || "—"}
              {(data.authors || []).length > 4 ? " 等" : ""}
            </span>
            <span className="doc-meta-label">published</span>
            <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>
              {data.published_at ? dayjs(data.published_at).format("YYYY-MM-DD") : "—"}
            </span>
            <a
              href={data.url}
              target="_blank"
              rel="noreferrer"
              style={{ color: "var(--accent)", fontFamily: "var(--font-mono)" }}
            >
              <LinkOutlined /> 跳转原文
            </a>
            {data.abstract_only && (
              <span
                title="未抓到全文 PDF,仅基于摘要建立索引"
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 10,
                  letterSpacing: "0.05em",
                  padding: "2px 8px",
                  border: "1px solid var(--warning)",
                  background: "var(--warning-bg)",
                  borderRadius: 999,
                  color: "var(--warning)",
                }}
              >
                仅摘要 · RAG 浅
              </span>
            )}
          </div>

          <Tabs
            defaultActiveKey="briefing"
            style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}
            tabBarStyle={{ marginBottom: 8 }}
            items={[
              {
                key: "briefing",
                label: "结构化解读",
                children: documentId ? (
                  <BriefingPanel topicId={topicId} documentId={documentId} />
                ) : null,
              },
              {
                key: "pdf",
                label: "PDF 预览",
                children: (
                  <div
                    style={{
                      // Fills the remaining tab-panel height. With the Drawer
                      // body laid out as a flex column above, this means the
                      // PDF takes ~100vh − (header + metadata + tab bar) ≈
                      // 100vh − 200px on a typical viewport.
                      flex: 1,
                      minHeight: 520,
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "var(--radius-md)",
                      overflow: "hidden",
                      background: "var(--bg-canvas)",
                      display: "flex",
                      flexDirection: "column",
                    }}
                  >
                    {pdfLoading ? (
                      <div style={{ padding: 24 }}>
                        <Skeleton active />
                      </div>
                    ) : pdfError ? (
                      <Alert
                        type="info"
                        showIcon
                        message={pdfError}
                        description={
                          data.abstract || "可点击右上角跳转到原始页面阅读。"
                        }
                        style={{ margin: 16 }}
                      />
                    ) : pdfUrl && documentId != null ? (
                      <PdfReader
                        topicId={topicId}
                        documentId={documentId}
                        pdfUrl={pdfUrl}
                      />
                    ) : null}
                  </div>
                ),
              },
            ]}
          />
        </div>
      )}
    </Drawer>
  );
}
