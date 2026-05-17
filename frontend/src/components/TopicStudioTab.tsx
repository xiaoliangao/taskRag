import {
  CopyOutlined,
  DownloadOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  TableOutlined,
} from "@ant-design/icons";
import {
  App,
  Button,
  Empty,
  Input,
  List,
  Modal,
  Segmented,
  Select,
  Skeleton,
  Tag,
  Typography,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";

import { apiErrorMessage } from "../api/client";
import {
  createComparison,
  exportComparison,
  generateComparison,
  getComparison,
  listComparisons,
} from "../api/comparisons";
import { listDocuments } from "../api/documents";
import {
  createWritingProject,
  generateDraft,
  generateOutline,
  getWritingProject,
  listWritingProjects,
} from "../api/writing";

interface Props {
  topicId: number;
  onJumpDocument?: (docId: number) => void;
}

function DocPicker({
  topicId,
  value,
  onChange,
  max = 8,
}: {
  topicId: number;
  value: number[];
  onChange: (ids: number[]) => void;
  max?: number;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["docs-list-studio", topicId],
    queryFn: () => listDocuments(topicId, { page: 1, page_size: 50 }),
  });
  const options = useMemo(
    () =>
      (data?.items ?? []).map((d) => ({
        label: d.title || `Doc #${d.id}`,
        value: d.id,
      })),
    [data],
  );
  return (
    <Select
      mode="multiple"
      style={{ width: "100%" }}
      placeholder={`选择 2-${max} 篇论文`}
      value={value}
      onChange={(v) => onChange(v.slice(0, max))}
      loading={isLoading}
      options={options}
      maxTagCount="responsive"
      data-testid="studio-doc-picker"
    />
  );
}

function ComparisonView({ topicId }: { topicId: number }) {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const [createOpen, setCreateOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [docIds, setDocIds] = useState<number[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);

  const { data: list } = useQuery({
    queryKey: ["comparisons", topicId],
    queryFn: () => listComparisons(topicId),
  });
  const { data: detail, isFetching } = useQuery({
    queryKey: ["comparison", topicId, activeId],
    queryFn: () => (activeId ? getComparison(topicId, activeId) : Promise.resolve(null)),
    enabled: !!activeId,
  });

  const createMut = useMutation({
    mutationFn: () => createComparison(topicId, title || "Comparison", docIds),
    onSuccess: async (s) => {
      setCreateOpen(false);
      setTitle("");
      setDocIds([]);
      setActiveId(s.id);
      qc.invalidateQueries({ queryKey: ["comparisons", topicId] });
      message.info("已创建，正在生成对比矩阵…");
      try {
        await generateComparison(topicId, s.id);
        qc.invalidateQueries({ queryKey: ["comparison", topicId, s.id] });
      } catch (e) {
        message.error(apiErrorMessage(e));
      }
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const regenMut = useMutation({
    mutationFn: () => generateComparison(topicId, activeId!),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["comparison", topicId, activeId] }),
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const exportMut = useMutation({
    mutationFn: (fmt: "markdown" | "latex") =>
      exportComparison(topicId, activeId!, fmt),
    onSuccess: async (data, fmt) => {
      try {
        await navigator.clipboard.writeText(data.content);
        message.success(`${fmt} 已复制到剪贴板`);
      } catch {
        message.info(`${fmt} 已生成，复制失败请手动`);
      }
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 12,
        }}
      >
        <div>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--text-muted)",
              marginBottom: 4,
            }}
          >
            <TableOutlined style={{ marginRight: 6 }} />
            Method Comparison
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
            选择 Topic 内 2-8 篇论文，生成对比矩阵。先用 briefing 填充，缺失字段用 LLM 补齐。
          </div>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setCreateOpen(true)}
          data-testid="comparison-create-btn"
        >
          新建对比
        </Button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 16 }}>
        <div>
          <Typography.Title level={5} style={{ margin: "0 0 6px" }}>
            历史
          </Typography.Title>
          {(list ?? []).length === 0 ? (
            <Empty image={null} description="无" />
          ) : (
            <List
              size="small"
              dataSource={list ?? []}
              renderItem={(c) => (
                <List.Item
                  onClick={() => setActiveId(c.id)}
                  style={{
                    cursor: "pointer",
                    background: activeId === c.id ? "var(--bg-muted)" : undefined,
                    borderRadius: 6,
                  }}
                >
                  <List.Item.Meta
                    title={
                      <div style={{ fontSize: 13, fontWeight: 500 }}>{c.title}</div>
                    }
                    description={
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        {c.document_ids.length} 篇 · {c.status} ·{" "}
                        {dayjs(c.created_at).format("MM-DD HH:mm")}
                      </div>
                    }
                  />
                </List.Item>
              )}
            />
          )}
        </div>
        <div>
          {!activeId ? (
            <Empty description="新建或选择一份对比" />
          ) : isFetching || !detail ? (
            <Skeleton active />
          ) : (
            <ComparisonDetail
              detail={detail}
              onRegen={() => regenMut.mutate()}
              onExport={(fmt) => exportMut.mutate(fmt)}
              regenLoading={regenMut.isPending}
              exportLoading={exportMut.isPending}
            />
          )}
        </div>
      </div>

      <Modal
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => {
          if (docIds.length < 2) {
            message.warning("至少选择 2 篇");
            return;
          }
          createMut.mutate();
        }}
        confirmLoading={createMut.isPending}
        title="新建方法对比"
        okText="生成"
        cancelText="取消"
      >
        <div style={{ marginBottom: 10 }}>
          <Input
            placeholder="对比标题（可选）"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={100}
          />
        </div>
        <DocPicker topicId={topicId} value={docIds} onChange={setDocIds} max={8} />
      </Modal>
    </div>
  );
}

function ComparisonDetail({
  detail,
  onRegen,
  onExport,
  regenLoading,
  exportLoading,
}: {
  detail: any;
  onRegen: () => void;
  onExport: (fmt: "markdown" | "latex") => void;
  regenLoading: boolean;
  exportLoading: boolean;
}) {
  const cols: string[] = detail.result_json?.columns ?? [];
  const rows: Array<Record<string, string | number>> = detail.result_json?.rows ?? [];
  return (
    <div>
      <div
        style={{
          display: "flex",
          gap: 8,
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 10,
        }}
      >
        <div>
          <Typography.Text strong style={{ fontSize: 15 }}>
            {detail.title}
          </Typography.Text>
          <Tag style={{ marginLeft: 8 }}>{detail.status}</Tag>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <Button icon={<ReloadOutlined />} loading={regenLoading} onClick={onRegen} size="small">
            重新生成
          </Button>
          <Button
            icon={<CopyOutlined />}
            size="small"
            loading={exportLoading}
            onClick={() => onExport("markdown")}
          >
            复制 Markdown
          </Button>
          <Button
            icon={<DownloadOutlined />}
            size="small"
            loading={exportLoading}
            onClick={() => onExport("latex")}
          >
            复制 LaTeX
          </Button>
        </div>
      </div>
      {!cols.length || !rows.length ? (
        <Empty description="尚未生成结果" />
      ) : (
        <div style={{ overflow: "auto" }}>
          <table
            style={{
              borderCollapse: "collapse",
              fontSize: 12,
              width: "100%",
            }}
          >
            <thead>
              <tr style={{ background: "var(--bg-muted)" }}>
                {cols.map((c) => (
                  <th
                    key={c}
                    style={{
                      border: "1px solid var(--border, #e5e7eb)",
                      padding: 8,
                      textAlign: "left",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  {cols.map((c) => (
                    <td
                      key={c}
                      style={{
                        border: "1px solid var(--border, #e5e7eb)",
                        padding: 8,
                        verticalAlign: "top",
                        maxWidth: 220,
                      }}
                    >
                      {String(r[c] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function WritingView({ topicId }: { topicId: number }) {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const [createOpen, setCreateOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [intent, setIntent] = useState("");
  const [docIds, setDocIds] = useState<number[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);

  const { data: list } = useQuery({
    queryKey: ["writing-list", topicId],
    queryFn: () => listWritingProjects(topicId),
  });
  const { data: detail, isFetching } = useQuery({
    queryKey: ["writing", topicId, activeId],
    queryFn: () => (activeId ? getWritingProject(topicId, activeId) : Promise.resolve(null)),
    enabled: !!activeId,
  });

  const createMut = useMutation({
    mutationFn: () =>
      createWritingProject(topicId, {
        title: title || "Related Work",
        user_intent: intent,
        document_ids: docIds,
      }),
    onSuccess: (p) => {
      setCreateOpen(false);
      setTitle("");
      setIntent("");
      setDocIds([]);
      setActiveId(p.id);
      qc.invalidateQueries({ queryKey: ["writing-list", topicId] });
      message.success("已创建写作项目，点击生成大纲开始");
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const outlineMut = useMutation({
    mutationFn: () => generateOutline(topicId, activeId!),
    onSuccess: () => {
      message.success("大纲已生成");
      qc.invalidateQueries({ queryKey: ["writing", topicId, activeId] });
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const draftMut = useMutation({
    mutationFn: () => generateDraft(topicId, activeId!),
    onSuccess: () => {
      message.success("草稿已生成");
      qc.invalidateQueries({ queryKey: ["writing", topicId, activeId] });
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 12,
        }}
      >
        <div>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--text-muted)",
              marginBottom: 4,
            }}
          >
            <EditOutlined style={{ marginRight: 6 }} />
            Related Work Studio
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
            输入研究问题 + 选择若干篇论文，生成带引用的 Related Work 草稿。
          </div>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          新建写作
        </Button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 16 }}>
        <div>
          <Typography.Title level={5} style={{ margin: "0 0 6px" }}>
            历史
          </Typography.Title>
          {(list ?? []).length === 0 ? (
            <Empty image={null} description="无" />
          ) : (
            <List
              size="small"
              dataSource={list ?? []}
              renderItem={(p) => (
                <List.Item
                  onClick={() => setActiveId(p.id)}
                  style={{
                    cursor: "pointer",
                    background: activeId === p.id ? "var(--bg-muted)" : undefined,
                  }}
                >
                  <List.Item.Meta
                    title={<div style={{ fontSize: 13 }}>{p.title}</div>}
                    description={
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        {p.status} · {dayjs(p.updated_at).format("MM-DD HH:mm")}
                      </div>
                    }
                  />
                </List.Item>
              )}
            />
          )}
        </div>
        <div>
          {!activeId ? (
            <Empty description="新建或选择一个写作项目" />
          ) : isFetching || !detail ? (
            <Skeleton active />
          ) : (
            <WritingDetail
              detail={detail}
              onOutline={() => outlineMut.mutate()}
              onDraft={() => draftMut.mutate()}
              outlineLoading={outlineMut.isPending}
              draftLoading={draftMut.isPending}
            />
          )}
        </div>
      </div>

      <Modal
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => {
          if (!intent.trim()) {
            message.warning("请输入研究问题/方法描述");
            return;
          }
          if (docIds.length < 1) {
            message.warning("至少选择 1 篇论文");
            return;
          }
          createMut.mutate();
        }}
        confirmLoading={createMut.isPending}
        title="新建 Related Work"
        okText="创建"
        cancelText="取消"
      >
        <Input
          placeholder="项目标题"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          style={{ marginBottom: 10 }}
        />
        <Input.TextArea
          rows={3}
          placeholder="你的研究问题 / 方法描述"
          value={intent}
          onChange={(e) => setIntent(e.target.value)}
          style={{ marginBottom: 10 }}
        />
        <DocPicker topicId={topicId} value={docIds} onChange={setDocIds} max={12} />
      </Modal>
    </div>
  );
}

function WritingDetail({
  detail,
  onOutline,
  onDraft,
  outlineLoading,
  draftLoading,
}: {
  detail: any;
  onOutline: () => void;
  onDraft: () => void;
  outlineLoading: boolean;
  draftLoading: boolean;
}) {
  const outlineSections: any[] = detail.outline_json?.sections ?? [];
  return (
    <div>
      <div
        style={{
          display: "flex",
          gap: 8,
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 10,
        }}
      >
        <div>
          <Typography.Text strong style={{ fontSize: 15 }}>
            {detail.title}
          </Typography.Text>
          <Tag style={{ marginLeft: 8 }}>{detail.status}</Tag>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <Button
            size="small"
            loading={outlineLoading}
            onClick={onOutline}
            icon={<ReloadOutlined />}
          >
            生成大纲
          </Button>
          <Button
            size="small"
            type="primary"
            loading={draftLoading}
            onClick={onDraft}
          >
            生成草稿
          </Button>
        </div>
      </div>

      {detail.error_message && (
        <div
          style={{
            color: "#b91c1c",
            background: "rgba(220,38,38,0.08)",
            padding: 8,
            borderRadius: 6,
            marginBottom: 8,
            fontSize: 12,
          }}
        >
          {detail.error_message}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 240px", gap: 12 }}>
        <div>
          {outlineSections.length > 0 && (
            <div
              style={{
                background: "var(--bg-muted)",
                padding: 10,
                borderRadius: 8,
                marginBottom: 10,
                fontSize: 12,
              }}
            >
              <div style={{ fontWeight: 500, marginBottom: 4 }}>大纲</div>
              {outlineSections.map((s, i) => (
                <div key={i} style={{ marginBottom: 6 }}>
                  <div>{s.section_title}</div>
                  <ul style={{ margin: "4px 0 0 16px", padding: 0 }}>
                    {(s.paragraphs || []).map((p: any, j: number) => (
                      <li key={j} style={{ color: "var(--text-muted)" }}>
                        {p.intent}
                        {p.document_ids?.length ? (
                          <span style={{ marginLeft: 4 }}>
                            [{p.document_ids.join(", ")}]
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
          {detail.draft_md ? (
            <div
              style={{
                padding: 12,
                border: "1px solid var(--border, #e5e7eb)",
                borderRadius: 8,
                fontSize: 13,
                lineHeight: 1.7,
              }}
            >
              <ReactMarkdown>{detail.draft_md}</ReactMarkdown>
            </div>
          ) : (
            <Empty description="尚无草稿" />
          )}
        </div>
        <div>
          <div style={{ fontWeight: 500, fontSize: 12, marginBottom: 4 }}>引用</div>
          {(detail.citation_json ?? []).length === 0 ? (
            <Empty image={null} description="无引用" />
          ) : (
            (detail.citation_json ?? []).map((c: any) => (
              <div
                key={c.label}
                style={{
                  fontSize: 11,
                  padding: 6,
                  marginBottom: 4,
                  border: "1px solid var(--border)",
                  borderRadius: 6,
                }}
              >
                <div style={{ fontFamily: "var(--font-mono)" }}>{c.label}</div>
                <div style={{ color: "var(--text-muted)" }} title={c.title}>
                  {c.title}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export default function TopicStudioTab({ topicId, onJumpDocument: _ }: Props) {
  const [sub, setSub] = useState<"comparison" | "writing">("comparison");
  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Segmented
          value={sub}
          onChange={(v) => setSub(v as any)}
          options={[
            { label: "方法对比", value: "comparison" },
            { label: "Related Work", value: "writing" },
          ]}
        />
      </div>
      {sub === "comparison" ? (
        <ComparisonView topicId={topicId} />
      ) : (
        <WritingView topicId={topicId} />
      )}
    </div>
  );
}
