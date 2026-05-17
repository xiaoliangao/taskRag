import { LinkOutlined, FilePdfOutlined, DownloadOutlined } from "@ant-design/icons";
import { Alert, Button, Drawer, Skeleton, Tabs } from "antd";
import { useQuery } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useEffect, useState } from "react";

import { getDocument, getDocumentPdfBlobUrl } from "../api/documents";
import BriefingPanel from "./BriefingPanel";

interface Props {
  topicId: number;
  documentId: number | null;
  open: boolean;
  onClose: () => void;
}

export default function DocumentDetailDrawer({ topicId, documentId, open, onClose }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["document", topicId, documentId],
    queryFn: () => getDocument(topicId, documentId!),
    enabled: open && documentId != null,
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
      width={1080}
      destroyOnClose
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
        pdfUrl && (
          <div style={{ display: "flex", gap: 8 }}>
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
          </div>
        )
      }
    >
      {isLoading || !data ? (
        <Skeleton active />
      ) : (
        <>
          {/* Metadata */}
          <div
            style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-md)",
              padding: "16px 20px",
              marginBottom: 18,
            }}
          >
            <div className="doc-meta-row">
              <div className="doc-meta-label">authors</div>
              <div style={{ color: "var(--text-primary)" }}>
                {(data.authors || []).join(", ") || "—"}
              </div>
            </div>
            <div className="doc-meta-row">
              <div className="doc-meta-label">published</div>
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 12.5,
                  color: "var(--text-secondary)",
                }}
              >
                {data.published_at
                  ? dayjs(data.published_at).format("YYYY-MM-DD")
                  : "—"}
              </div>
            </div>
            <div className="doc-meta-row">
              <div className="doc-meta-label">source</div>
              <div>
                <a
                  href={data.url}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: "var(--accent)", fontFamily: "var(--font-mono)", fontSize: 12 }}
                >
                  <LinkOutlined /> 跳转原文
                </a>
              </div>
            </div>
          </div>

          <Tabs
            defaultActiveKey="briefing"
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
                      height: "calc(100vh - 360px)",
                      minHeight: 520,
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "var(--radius-md)",
                      overflow: "hidden",
                      background: "var(--bg-canvas)",
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
                    ) : pdfUrl ? (
                      <iframe
                        title={data.title}
                        src={pdfUrl}
                        style={{
                          width: "100%",
                          height: "100%",
                          border: 0,
                          background: "white",
                        }}
                      />
                    ) : null}
                  </div>
                ),
              },
            ]}
          />
        </>
      )}
    </Drawer>
  );
}
