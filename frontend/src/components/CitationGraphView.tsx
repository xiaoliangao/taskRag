import { ReloadOutlined } from "@ant-design/icons";
import { App, Button, Empty, List, Skeleton, Typography } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";

import { apiErrorMessage } from "../api/client";
import {
  type CitationEdge,
  type CitationNode,
  getCitationGraph,
  rebuildCitationGraph,
} from "../api/citations";

interface Props {
  topicId: number;
  onJumpDocument?: (docId: number) => void;
}

const ACCENT = "var(--accent)";
const DIM = "var(--text-tertiary)";

interface Placed {
  x: number;
  y: number;
  r: number;
  n: CitationNode;
}
interface Line {
  key: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}
interface Layout {
  width: number;
  height: number;
  placed: Placed[];
  lines: Line[];
  columns: { x: number; label: string }[];
  maxIn: number;
}

// Deterministic year-layered layout (no force sim, no graph lib): x = publication
// year, nodes stacked within a year column, radius ∝ √(total citations), edges
// drawn citing→cited and clipped to the node boundary so the arrow is visible.
function buildLayout(nodes: CitationNode[], edges: CitationEdge[]): Layout | null {
  const LEFT = 24;
  const TOP = 26;
  const COL_W = 140;
  const ROW_H = 46;
  const BOTTOM = 34;

  const display = [...nodes]
    .sort((a, b) => (b.cited_by_count ?? 0) - (a.cited_by_count ?? 0))
    .slice(0, 60);
  if (display.length === 0) return null;

  const maxCited = Math.max(1, ...display.map((n) => n.cited_by_count ?? 0));
  const maxIn = Math.max(1, ...display.map((n) => n.in_degree));

  const colKeys = Array.from(new Set(display.map((n) => n.year ?? 0))).sort((a, b) => a - b);
  const colIndex = new Map(colKeys.map((k, i) => [k, i] as const));

  const byCol = new Map<number, CitationNode[]>();
  for (const n of display) {
    const k = n.year ?? 0;
    const arr = byCol.get(k) ?? [];
    arr.push(n);
    byCol.set(k, arr);
  }

  let maxRows = 0;
  const placedMap = new Map<number, Placed>();
  for (const [k, arr] of byCol) {
    arr.sort((a, b) => (b.cited_by_count ?? 0) - (a.cited_by_count ?? 0));
    maxRows = Math.max(maxRows, arr.length);
    const ci = colIndex.get(k)!;
    arr.forEach((n, row) => {
      const r = 5 + 17 * Math.sqrt((n.cited_by_count ?? 0) / maxCited);
      placedMap.set(n.id, { x: LEFT + ci * COL_W + COL_W / 2, y: TOP + row * ROW_H + 22, r, n });
    });
  }

  const width = LEFT * 2 + colKeys.length * COL_W;
  const height = TOP + maxRows * ROW_H + BOTTOM;

  const lines: Line[] = [];
  for (const e of edges) {
    const s = placedMap.get(e.source);
    const t = placedMap.get(e.target);
    if (!s || !t) continue;
    const dx = t.x - s.x;
    const dy = t.y - s.y;
    const len = Math.hypot(dx, dy) || 1;
    lines.push({
      key: `${e.source}-${e.target}`,
      x1: s.x + (dx / len) * s.r,
      y1: s.y + (dy / len) * s.r,
      x2: t.x - (dx / len) * (t.r + 3),
      y2: t.y - (dy / len) * (t.r + 3),
    });
  }

  const columns = colKeys.map((k) => ({
    x: LEFT + colIndex.get(k)! * COL_W + COL_W / 2,
    label: k === 0 ? "n.d." : String(k),
  }));

  return { width, height, placed: [...placedMap.values()], lines, columns, maxIn };
}

function RankList({
  title,
  nodes,
  metric,
  onJump,
}: {
  title: string;
  nodes: CitationNode[];
  metric: (n: CitationNode) => string;
  onJump?: (id: number) => void;
}) {
  return (
    <div>
      <Typography.Title level={5} style={{ margin: "0 0 8px" }}>
        {title}
      </Typography.Title>
      {nodes.length === 0 ? (
        <div style={{ color: DIM, fontSize: 12, fontStyle: "italic", padding: "8px 4px" }}>
          暂无数据
        </div>
      ) : (
        <List
          size="small"
          dataSource={nodes}
          renderItem={(n) => (
            <List.Item
              onClick={() => onJump?.(n.id)}
              style={{ cursor: "pointer", padding: "6px 8px" }}
            >
              <List.Item.Meta
                title={
                  <div
                    title={n.title ?? ""}
                    style={{
                      fontSize: 12.5,
                      fontWeight: 500,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      maxWidth: 280,
                    }}
                  >
                    {n.title ?? `Doc #${n.id}`}
                  </div>
                }
                description={
                  <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                    {(n.year ?? "n.d.") + " · " + metric(n)}
                  </span>
                }
              />
            </List.Item>
          )}
        />
      )}
    </div>
  );
}

export default function CitationGraphView({ topicId, onJumpDocument }: Props) {
  const qc = useQueryClient();
  const { message } = App.useApp();

  const { data, isLoading } = useQuery({
    queryKey: ["citation-graph", topicId],
    queryFn: () => getCitationGraph(topicId),
  });
  const rebuild = useMutation({
    mutationFn: () => rebuildCitationGraph(topicId),
    onSuccess: (r) => {
      message.success(
        `已拉取 ${r.enriched} 篇引用数据 · ${r.edges} 条引用边` +
          (r.remaining > 0 ? ` · 还有 ${r.remaining} 篇待拉取(再点一次继续)` : ""),
      );
      qc.invalidateQueries({ queryKey: ["citation-graph", topicId] });
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const nodes = useMemo(() => data?.nodes ?? [], [data]);
  const edges = useMemo(() => data?.edges ?? [], [data]);
  const stats = data?.stats;
  const layout = useMemo(() => buildLayout(nodes, edges), [nodes, edges]);

  const mostCited = useMemo(
    () =>
      [...nodes]
        .filter((n) => n.cited_by_count != null)
        .sort((a, b) => (b.cited_by_count ?? 0) - (a.cited_by_count ?? 0))
        .slice(0, 8),
    [nodes],
  );
  const rising = useMemo(
    () =>
      [...nodes]
        .filter((n) => n.recent_citations > 0)
        .sort((a, b) => b.recent_citations - a.recent_citations)
        .slice(0, 8),
    [nodes],
  );
  const seminal = useMemo(
    () =>
      [...nodes]
        .filter((n) => n.in_degree > 0)
        .sort((a, b) => b.in_degree - a.in_degree)
        .slice(0, 8),
    [nodes],
  );

  const rebuildBtn = (
    <Button
      size="small"
      icon={<ReloadOutlined />}
      loading={rebuild.isPending}
      onClick={() => rebuild.mutate()}
      data-testid="citation-rebuild-btn"
    >
      拉取 / 重建引用数据
    </Button>
  );

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 10,
          gap: 12,
        }}
      >
        <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          基于 OpenAlex 的真实「A 引用 B」网络 · 节点大小=总被引 · 颜色深浅=课题内被引 · 箭头 A→B 表示 A 引用 B
          {stats ? ` · 已拉取 ${stats.enriched}/${stats.total} 篇 · ${stats.edges} 条边` : ""}
        </div>
        {rebuildBtn}
      </div>

      {isLoading ? (
        <Skeleton active />
      ) : nodes.length === 0 ? (
        <Empty description="课题暂无文档" />
      ) : !stats || stats.enriched === 0 ? (
        <div
          style={{
            border: "1px dashed var(--border-default)",
            borderRadius: 8,
            padding: "32px 16px",
            textAlign: "center",
            color: "var(--text-secondary)",
          }}
        >
          <div style={{ marginBottom: 12 }}>
            尚未拉取引用数据。点击「拉取 / 重建引用数据」从 OpenAlex 获取每篇的被引数与引用关系。
          </div>
          {rebuildBtn}
        </div>
      ) : (
        <>
          <div
            style={{
              border: "1px solid var(--border-subtle)",
              borderRadius: 8,
              background: "var(--bg-canvas)",
              overflow: "auto",
              maxHeight: 460,
              marginBottom: 16,
            }}
          >
            {layout ? (
              <svg
                width={layout.width}
                height={layout.height}
                style={{ minWidth: "100%", display: "block" }}
              >
                <defs>
                  <marker
                    id="cite-arrow"
                    markerWidth="7"
                    markerHeight="7"
                    refX="5.5"
                    refY="3"
                    orient="auto"
                  >
                    <path d="M0,0 L6,3 L0,6 Z" fill={ACCENT} opacity={0.55} />
                  </marker>
                </defs>
                {layout.lines.map((l) => (
                  <line
                    key={l.key}
                    x1={l.x1}
                    y1={l.y1}
                    x2={l.x2}
                    y2={l.y2}
                    stroke={ACCENT}
                    strokeWidth={1}
                    opacity={0.18}
                    markerEnd="url(#cite-arrow)"
                  />
                ))}
                {layout.columns.map((c) => (
                  <text
                    key={`col-${c.label}`}
                    x={c.x}
                    y={layout.height - 12}
                    textAnchor="middle"
                    fontSize={10}
                    fill={DIM}
                    fontFamily="var(--font-mono)"
                  >
                    {c.label}
                  </text>
                ))}
                {layout.placed.map((p) => (
                  <g
                    key={p.n.id}
                    style={{ cursor: "pointer" }}
                    onClick={() => onJumpDocument?.(p.n.id)}
                  >
                    <circle
                      cx={p.x}
                      cy={p.y}
                      r={p.r}
                      fill={ACCENT}
                      fillOpacity={0.16 + 0.62 * Math.min(1, p.n.in_degree / layout.maxIn)}
                      stroke={ACCENT}
                      strokeOpacity={0.7}
                      strokeWidth={1}
                    />
                    <title>
                      {`${p.n.title ?? "Doc #" + p.n.id}\n被引 ${
                        p.n.cited_by_count ?? "?"
                      } · 近2年 ${p.n.recent_citations} · 课题内被引 ${p.n.in_degree}`}
                    </title>
                  </g>
                ))}
              </svg>
            ) : null}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
            <RankList
              title="最被引 (全网)"
              nodes={mostCited}
              metric={(n) => `被引 ${n.cited_by_count ?? 0}`}
              onJump={onJumpDocument}
            />
            <RankList
              title="上升最快 (近2年)"
              nodes={rising}
              metric={(n) => `近2年 ${n.recent_citations}`}
              onJump={onJumpDocument}
            />
            <RankList
              title="课题内被引最多"
              nodes={seminal}
              metric={(n) => `课题内被引 ${n.in_degree}`}
              onJump={onJumpDocument}
            />
          </div>
        </>
      )}
    </div>
  );
}
