import {
  BookOutlined,
  LinkOutlined,
  ReloadOutlined,
  StarFilled,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { App, Button, Empty, Skeleton, Tabs, Tag, Tooltip } from "antd";
import dayjs from "dayjs";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { apiErrorMessage } from "../api/client";
import {
  listMyFavorites,
  unfavoriteDocument,
  type FavoriteItem,
} from "../api/documents";
import {
  getMyRecommendations,
  type RecommendedItem,
} from "../api/recommendations";

const SOURCE_COLOR: Record<string, string> = {
  arxiv: "var(--accent)",
  openalex: "var(--info)",
  semantic_scholar: "#c19bff",
  upload: "var(--text-tertiary)",
};

function FavoriteCard({
  it,
  onJump,
  onUnfavorite,
}: {
  it: FavoriteItem;
  onJump: (topicId: number, documentId: number) => void;
  onUnfavorite: (documentId: number) => void;
}) {
  const firstTopic = it.topic_ids[0];
  return (
    <div
      style={{
        border: "1px solid var(--border-subtle)",
        background: "var(--bg-surface)",
        borderRadius: "var(--radius-sm)",
        padding: "12px 14px",
        display: "grid",
        gridTemplateColumns: "20px 1fr auto",
        gap: 12,
      }}
    >
      <div style={{ paddingTop: 3 }}>
        <StarFilled style={{ color: "#f5c518" }} />
      </div>
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontWeight: 600,
            fontSize: 13.5,
            color: "var(--text-primary)",
            lineHeight: 1.4,
            cursor: firstTopic ? "pointer" : "default",
          }}
          onClick={() => firstTopic && onJump(firstTopic, it.document_id)}
        >
          {it.title}
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
          {it.published_at && <span>· {dayjs(it.published_at).format("YYYY-MM-DD")}</span>}
          {it.authors.length > 0 && (
            <span>
              · {it.authors.slice(0, 3).join(", ")}
              {it.authors.length > 3 ? " 等" : ""}
            </span>
          )}
          {it.abstract_only && (
            <Tag color="warning" style={{ marginInlineEnd: 0 }}>
              仅摘要
            </Tag>
          )}
        </div>
        {it.abstract && (
          <div
            style={{
              fontSize: 12.5,
              color: "var(--text-tertiary)",
              marginTop: 6,
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
      <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end" }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
          {it.topic_ids.map((tid) => (
            <Tag
              key={tid}
              style={{ cursor: "pointer", marginInlineEnd: 0 }}
              onClick={() => onJump(tid, it.document_id)}
            >
              Topic #{tid}
            </Tag>
          ))}
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {it.url && (
            <Tooltip title="跳转原文">
              <Button size="small" icon={<LinkOutlined />} href={it.url} target="_blank" />
            </Tooltip>
          )}
          <Tooltip title="取消收藏">
            <Button size="small" onClick={() => onUnfavorite(it.document_id)}>
              移除
            </Button>
          </Tooltip>
        </div>
      </div>
    </div>
  );
}

function FavoritesTab() {
  const { message } = App.useApp();
  const qc = useQueryClient();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["my-favorites"],
    queryFn: () => listMyFavorites(50, 0),
  });

  const unfavMut = useMutation({
    mutationFn: (documentId: number) => unfavoriteDocument(documentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["my-favorites"] });
      qc.invalidateQueries({ queryKey: ["my-recommendations"] });
      message.success("已移除收藏");
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  if (isLoading) return <Skeleton active paragraph={{ rows: 6 }} />;
  if (!data || data.items.length === 0) {
    return (
      <Empty description="还没有收藏。在任何文档详情里点⭐就会出现在这里。" />
    );
  }
  return (
    <>
      <div
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          color: "var(--text-muted)",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          marginBottom: 10,
        }}
      >
        共 {data.total} 篇 · 按最近打开时间倒序
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {data.items.map((it) => (
          <FavoriteCard
            key={it.document_id}
            it={it}
            onJump={(topicId, documentId) =>
              navigate(`/topics/${topicId}/documents?doc=${documentId}`)
            }
            onUnfavorite={(id) => unfavMut.mutate(id)}
          />
        ))}
      </div>
    </>
  );
}

function RecommendCard({
  it,
  onPick,
}: {
  it: RecommendedItem;
  onPick: (it: RecommendedItem) => void;
}) {
  return (
    <div
      style={{
        border: "1px solid var(--border-subtle)",
        background: "var(--bg-surface)",
        borderRadius: "var(--radius-sm)",
        padding: "12px 14px",
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div style={{ fontWeight: 600, fontSize: 13.5, color: "var(--text-primary)", lineHeight: 1.4 }}>
        {it.title}
      </div>
      <div
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          color: "var(--text-tertiary)",
          display: "flex",
          gap: 8,
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <span style={{ color: SOURCE_COLOR[it.source] || "var(--text-secondary)" }}>{it.source}</span>
        {it.published_at && <span>· {dayjs(it.published_at).format("YYYY-MM-DD")}</span>}
        {it.authors.length > 0 && (
          <span>
            · {it.authors.slice(0, 3).join(", ")}
            {it.authors.length > 3 ? " 等" : ""}
          </span>
        )}
        <Tag color={it.in_corpus ? "blue" : "purple"} style={{ marginInlineEnd: 0 }}>
          {it.in_corpus ? "已在库内" : "在线发现"}
        </Tag>
        {it.score != null && (
          <span style={{ color: "var(--text-muted)" }}>· score {it.score.toFixed(3)}</span>
        )}
      </div>
      {it.rationale && (
        <div
          style={{
            fontSize: 12.5,
            color: "var(--text-secondary)",
            background: "var(--accent-bg-soft)",
            borderLeft: "3px solid var(--accent)",
            padding: "8px 10px",
            borderRadius: "var(--radius-sm)",
            lineHeight: 1.55,
          }}
        >
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 10,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--text-tertiary)",
              marginRight: 6,
            }}
          >
            为什么推荐
          </span>
          {it.rationale}
        </div>
      )}
      {it.abstract && (
        <div
          style={{
            fontSize: 12.5,
            color: "var(--text-tertiary)",
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
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        {it.url && (
          <Button size="small" icon={<LinkOutlined />} href={it.url} target="_blank">
            原文
          </Button>
        )}
        {it.in_corpus && it.topic_ids.length > 0 ? (
          it.topic_ids.map((tid) => (
            <a key={tid} href={`/topics/${tid}/documents?doc=${it.document_id}`}>
              <Button size="small" type="primary">
                查看 (Topic #{tid})
              </Button>
            </a>
          ))
        ) : (
          <Button size="small" type="primary" onClick={() => onPick(it)}>
            加入课题
          </Button>
        )}
      </div>
    </div>
  );
}

function RecommendationsTab() {
  const { message } = App.useApp();
  const [refresh, setRefresh] = useState(false);
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["my-recommendations", refresh],
    queryFn: () => getMyRecommendations(10, refresh),
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) return <Skeleton active paragraph={{ rows: 8 }} />;
  if (!data) return <Empty description="无推荐数据" />;

  if (data.items.length === 0) {
    return (
      <Empty
        description={
          data.favorites_count === 0
            ? "先去收藏几篇感兴趣的论文,AI 才能基于你的口味做推荐。"
            : "暂无推荐 — 试试 ↻ 强制刷新,或多收藏几篇再来。"
        }
      />
    );
  }

  return (
    <>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 10,
        }}
      >
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            color: "var(--text-muted)",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
          }}
        >
          基于 {data.favorites_count} 篇收藏 · {data.items.length} 篇推荐 ·
          {data.cached ? " 缓存命中" : " 实时生成"}
        </div>
        <Button
          size="small"
          icon={<ReloadOutlined />}
          loading={isFetching}
          onClick={() => {
            setRefresh(true);
            refetch().finally(() => setRefresh(false));
          }}
        >
          重新生成
        </Button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {data.items.map((it) => (
          <RecommendCard
            key={`${it.source}|${it.external_id}`}
            it={it}
            onPick={() => message.info("加入课题:请在「全局检索」搜该标题后用入库按钮(下一版会做一键加入)")}
          />
        ))}
      </div>
    </>
  );
}

export default function LibraryPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "favorites";

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div>
          <div className="page-eyebrow">
            <BookOutlined style={{ marginRight: 6 }} />
            My Library
          </div>
          <h1 className="page-title">
            我的<span style={{ fontStyle: "italic", color: "var(--accent)" }}>收藏</span>与推荐
          </h1>
          <p className="page-subtitle">
            收藏值得回头的论文 · AI 基于你的收藏推荐相邻方向
          </p>
        </div>
      </div>

      <Tabs
        activeKey={tab}
        onChange={(k) => setParams({ tab: k })}
        items={[
          { key: "favorites", label: "我的收藏", children: <FavoritesTab /> },
          { key: "recommendations", label: "为你推荐", children: <RecommendationsTab /> },
        ]}
      />
    </div>
  );
}
