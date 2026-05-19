import {
  ClockCircleOutlined,
  CloudDownloadOutlined,
  ClusterOutlined,
  CopyOutlined,
  ReadOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import {
  App,
  Button,
  Empty,
  List,
  Segmented,
  Skeleton,
  Tag,
  Typography,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { apiErrorMessage } from "../api/client";
import { exportBibtex, exportMarkdown } from "../api/exports";
import { generateGlossary, listGlossary } from "../api/glossary";
import { getGraph, rebuildGraph } from "../api/graph";
import type { GraphEdge, GraphNode } from "../types/api";
import MethodTimelineView from "./MethodTimelineView";

interface Props {
  topicId: number;
  onJumpDocument?: (docId: number) => void;
}

const RELATION_OPTIONS = [
  { label: "全部", value: "" },
  { label: "同方法", value: "same_method" },
  { label: "同数据集", value: "same_dataset" },
  { label: "同指标", value: "same_metric" },
  { label: "同术语", value: "same_term" },
  { label: "同作者", value: "same_author" },
];

function GraphView({
  topicId,
  onJump,
}: {
  topicId: number;
  onJump?: (id: number) => void;
}) {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const [rt, setRt] = useState<string>("");

  const { data, isLoading } = useQuery({
    queryKey: ["graph", topicId, rt],
    queryFn: () => getGraph(topicId, { relation_types: rt || undefined, limit_nodes: 80 }),
  });
  const rebuildMut = useMutation({
    mutationFn: () => rebuildGraph(topicId),
    onSuccess: (s) => {
      message.success(`已重建：${s.edges} 条边 / ${s.nodes} 个节点`);
      qc.invalidateQueries({ queryKey: ["graph", topicId] });
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const adjacency = useMemo(() => {
    const map = new Map<number, GraphEdge[]>();
    for (const e of data?.edges ?? []) {
      const arr1 = map.get(e.source) ?? [];
      arr1.push(e);
      map.set(e.source, arr1);
      const arr2 = map.get(e.target) ?? [];
      arr2.push(e);
      map.set(e.target, arr2);
    }
    return map;
  }, [data]);

  const topNodes = useMemo(
    () =>
      (data?.nodes ?? [])
        .map((n) => ({ ...n, deg: (adjacency.get(n.id) ?? []).length }))
        .sort((a, b) => b.deg - a.deg)
        .slice(0, 30),
    [data, adjacency],
  );

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 10,
        }}
      >
        <Segmented
          size="small"
          value={rt}
          onChange={(v) => setRt(String(v))}
          options={RELATION_OPTIONS}
        />
        <Button
          size="small"
          icon={<ReloadOutlined />}
          loading={rebuildMut.isPending}
          onClick={() => rebuildMut.mutate()}
          data-testid="graph-rebuild-btn"
        >
          重建图谱
        </Button>
      </div>

      {isLoading ? (
        <Skeleton active />
      ) : (data?.nodes ?? []).length === 0 ? (
        <Empty description="还没有图谱数据，先点击重建" />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <Typography.Title level={5} style={{ margin: "0 0 8px" }}>
              高连接论文 (top {topNodes.length})
            </Typography.Title>
            <List
              size="small"
              dataSource={topNodes}
              renderItem={(n) => (
                <List.Item
                  onClick={() => onJump?.(n.id)}
                  style={{ cursor: "pointer", padding: "8px 10px" }}
                >
                  <List.Item.Meta
                    title={
                      <div
                        style={{
                          fontSize: 13,
                          fontWeight: 500,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          maxWidth: 360,
                        }}
                        title={n.title ?? ""}
                      >
                        {n.title ?? `Doc #${n.id}`}
                      </div>
                    }
                    description={
                      <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                        {n.year ?? "n.d."} · {n.source ?? "—"} · 度数 {n.deg}
                      </div>
                    }
                  />
                </List.Item>
              )}
            />
          </div>
          <div>
            <Typography.Title level={5} style={{ margin: "0 0 8px" }}>
              边样本 (按类型 / 权重)
            </Typography.Title>
            <List
              size="small"
              dataSource={(data?.edges ?? []).slice(0, 40)}
              renderItem={(e) => (
                <List.Item style={{ padding: "6px 10px" }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
                    #{e.source} ↔ #{e.target}
                  </span>
                  <Tag style={{ marginLeft: 8 }}>{e.type}</Tag>
                  <span style={{ marginLeft: 6, fontSize: 11, color: "var(--text-secondary)" }}>
                    w={e.weight.toFixed(2)}
                  </span>
                </List.Item>
              )}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function GlossaryView({ topicId }: { topicId: number }) {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const { data, isLoading } = useQuery({
    queryKey: ["glossary", topicId],
    queryFn: () => listGlossary(topicId),
  });
  const genMut = useMutation({
    mutationFn: () => generateGlossary(topicId, 15),
    onSuccess: (s) => {
      message.success(`已生成 ${s.generated} 个 / 跳过 ${s.skipped} 个`);
      qc.invalidateQueries({ queryKey: ["glossary", topicId] });
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
          marginBottom: 10,
        }}
      >
        <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          为 Topic 内 top 术语生成简短中文定义（基于本地证据，禁止外部知识）。
        </div>
        <Button
          icon={<ReloadOutlined />}
          loading={genMut.isPending}
          size="small"
          onClick={() => genMut.mutate()}
          data-testid="glossary-gen-btn"
        >
          生成 / 刷新
        </Button>
      </div>
      {isLoading ? (
        <Skeleton active />
      ) : (data ?? []).length === 0 ? (
        <Empty description="尚无词典条目" />
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
            gap: 10,
          }}
        >
          {data!.map((g) => (
            <div
              key={g.id}
              style={{
                padding: 12,
                border: "1px solid var(--border-default)",
                borderRadius: 8,
                background: "var(--bg-surface, var(--bg-elevated))",
              }}
            >
              <div style={{ fontWeight: 500, marginBottom: 4 }}>{g.term}</div>
              <div style={{ fontSize: 12, color: "var(--text-primary)" }}>{g.definition}</div>
              <div
                style={{
                  fontSize: 11,
                  color: "var(--text-secondary)",
                  marginTop: 6,
                }}
              >
                来自 {g.representative_document_ids.length} 篇 · conf{" "}
                {(g.confidence * 100).toFixed(0)}%
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ExportView({ topicId }: { topicId: number }) {
  const { message } = App.useApp();
  const [content, setContent] = useState<string>("");
  const [fmt, setFmt] = useState<string>("");
  const bibMut = useMutation({
    mutationFn: () => exportBibtex(topicId),
    onSuccess: (r) => {
      setContent(r.content);
      setFmt(r.export_type);
      message.success(`BibTeX 已生成 (${r.char_count} 字符)`);
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });
  const mdMut = useMutation({
    mutationFn: () => exportMarkdown(topicId),
    onSuccess: (r) => {
      setContent(r.content);
      setFmt(r.export_type);
      message.success(`Markdown 已生成 (${r.char_count} 字符)`);
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const copy = async () => {
    if (!content) return;
    try {
      await navigator.clipboard.writeText(content);
      message.success("已复制");
    } catch {
      message.warning("复制失败，请手动复制");
    }
  };

  return (
    <div>
      <div style={{ marginBottom: 12, display: "flex", gap: 8 }}>
        <Button
          icon={<CloudDownloadOutlined />}
          loading={bibMut.isPending}
          onClick={() => bibMut.mutate()}
          data-testid="export-bibtex-btn"
        >
          导出 BibTeX
        </Button>
        <Button
          icon={<CloudDownloadOutlined />}
          loading={mdMut.isPending}
          onClick={() => mdMut.mutate()}
          data-testid="export-markdown-btn"
        >
          导出 Markdown
        </Button>
        {content && (
          <Button icon={<CopyOutlined />} onClick={copy}>
            复制 ({fmt})
          </Button>
        )}
      </div>
      {!content ? (
        <Empty description="尚未生成导出" />
      ) : (
        <pre
          style={{
            background: "var(--bg-elevated)",
            padding: 12,
            borderRadius: 8,
            maxHeight: 360,
            overflow: "auto",
            fontSize: 12,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {content.slice(0, 4000)}
          {content.length > 4000 ? "\n…（已截断显示）" : ""}
        </pre>
      )}
    </div>
  );
}

export default function TopicMapTab({ topicId, onJumpDocument }: Props) {
  const [sub, setSub] = useState<"graph" | "timeline" | "glossary" | "export">("graph");
  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Segmented
          value={sub}
          onChange={(v) => setSub(v as any)}
          options={[
            { label: "知识图谱", value: "graph", icon: <ClusterOutlined /> },
            { label: "方法时间线", value: "timeline", icon: <ClockCircleOutlined /> },
            { label: "术语词典", value: "glossary", icon: <ReadOutlined /> },
            { label: "Export Hub", value: "export", icon: <CloudDownloadOutlined /> },
          ]}
        />
      </div>
      {sub === "graph" && <GraphView topicId={topicId} onJump={onJumpDocument} />}
      {sub === "timeline" && (
        <MethodTimelineView topicId={topicId} onJumpDocument={onJumpDocument} />
      )}
      {sub === "glossary" && <GlossaryView topicId={topicId} />}
      {sub === "export" && <ExportView topicId={topicId} />}
    </div>
  );
}
