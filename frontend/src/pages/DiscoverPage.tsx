import {
  CheckCircleFilled,
  CompassOutlined,
  PlusOutlined,
  SearchOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Checkbox,
  Dropdown,
  Empty,
  Input,
  InputNumber,
  Modal,
  Select,
  Skeleton,
  Space,
  Tag,
  Typography,
} from "antd";
import dayjs from "dayjs";
import { useMemo, useState } from "react";

import { apiErrorMessage } from "../api/client";
import {
  discoverIngest,
  discoverSearch,
  type DiscoverSearchResponse,
} from "../api/discover";
import { listTopics, type PreviewItem } from "../api/topics";

const SOURCE_OPTIONS = [
  { label: "arXiv", value: "arxiv" },
  { label: "OpenAlex", value: "openalex" },
  { label: "Semantic Scholar", value: "semantic_scholar" },
];

const SOURCE_COLOR: Record<string, string> = {
  arxiv: "var(--accent)",
  openalex: "var(--info)",
  semantic_scholar: "#c19bff",
};

function itemKey(it: PreviewItem): string {
  return `${it.source}|${it.external_id}`;
}

export default function DiscoverPage() {
  const { message, modal } = App.useApp();
  const qc = useQueryClient();

  const [query, setQuery] = useState("");
  const [sources, setSources] = useState<string[]>([]);
  const [days, setDays] = useState<number>(365);
  const [limit, setLimit] = useState<number>(20);

  const [results, setResults] = useState<DiscoverSearchResponse | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [newTopicOpen, setNewTopicOpen] = useState(false);
  const [newTopicName, setNewTopicName] = useState("");

  const topicsQ = useQuery({
    queryKey: ["topics"],
    queryFn: listTopics,
  });

  const searchMut = useMutation({
    mutationFn: () => discoverSearch({ query: query.trim(), sources, limit, days }),
    onSuccess: (data) => {
      setResults(data);
      setPicked(new Set());
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const ingestMut = useMutation({
    mutationFn: (vars: { topicId?: number; newTopicName?: string }) =>
      discoverIngest({
        picks: selectedItems,
        topic_id: vars.topicId,
        new_topic_name: vars.newTopicName,
      }),
    onSuccess: (r) => {
      const verb = r.created_topic ? "新建并派发到" : "已派发到";
      message.success(`${verb} 「${r.topic_name}」 (${r.count} 篇)`);
      qc.invalidateQueries({ queryKey: ["topics"] });
      setPicked(new Set());
      setNewTopicOpen(false);
      setNewTopicName("");
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const items = results?.items ?? [];
  const selectedItems = useMemo(
    () => items.filter((it) => picked.has(itemKey(it))),
    [items, picked],
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
    if (select) setPicked(new Set(items.map(itemKey)));
    else setPicked(new Set());
  };

  const submitSearch = () => {
    if (!query.trim()) {
      message.warning("先输入想搜什么");
      return;
    }
    searchMut.mutate();
  };

  const ingestTarget = (topicId?: number) => {
    if (!selectedItems.length) {
      message.warning("先勾选至少 1 篇论文");
      return;
    }
    if (topicId) ingestMut.mutate({ topicId });
    else setNewTopicOpen(true);
  };

  const topicMenu = {
    items: [
      ...(topicsQ.data ?? []).map((t) => ({
        key: `t-${t.id}`,
        label: (
          <span>
            {t.name}
            <span
              style={{
                marginLeft: 8,
                color: "var(--text-tertiary)",
                fontFamily: "var(--font-mono)",
                fontSize: 11,
              }}
            >
              {t.document_count}
            </span>
          </span>
        ),
        onClick: () => ingestTarget(t.id),
      })),
      { type: "divider" as const },
      {
        key: "new",
        icon: <PlusOutlined />,
        label: "新建临时课题…",
        onClick: () => ingestTarget(undefined),
      },
    ],
  };

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div>
          <div className="page-eyebrow">
            <CompassOutlined style={{ marginRight: 6 }} />
            Global Discover
          </div>
          <h1 className="page-title">
            全网<span style={{ fontStyle: "italic", color: "var(--accent)" }}>检索</span>论文
          </h1>
          <p className="page-subtitle">
            一次性搜索 arXiv / OpenAlex / Semantic Scholar,选中后入库到任意课题或新建一个。
          </p>
        </div>
      </div>

      <div
        style={{
          border: "1px solid var(--border-default)",
          borderRadius: "var(--radius-md)",
          background: "var(--bg-surface)",
          padding: 16,
          marginBottom: 16,
        }}
      >
        <Input
          size="large"
          allowClear
          prefix={<SearchOutlined />}
          placeholder="输入主题、论文名片段、关键词。多个关键词用英文逗号分隔。"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onPressEnter={submitSearch}
          style={{ fontFamily: "var(--font-mono)", fontSize: 14, marginBottom: 12 }}
        />
        <Space wrap size={12} align="center">
          <Select
            mode="multiple"
            placeholder="所有数据源"
            value={sources}
            onChange={setSources}
            options={SOURCE_OPTIONS}
            style={{ minWidth: 240 }}
            allowClear
          />
          <Space size={6}>
            <span style={{ fontSize: 12, color: "var(--text-tertiary)" }}>近</span>
            <InputNumber
              min={1}
              max={3650}
              value={days}
              onChange={(v) => setDays(Number(v) || 365)}
              style={{ width: 86 }}
              addonAfter="天"
            />
          </Space>
          <Space size={6}>
            <span style={{ fontSize: 12, color: "var(--text-tertiary)" }}>最多</span>
            <InputNumber
              min={1}
              max={50}
              value={limit}
              onChange={(v) => setLimit(Number(v) || 20)}
              style={{ width: 78 }}
              addonAfter="篇"
            />
          </Space>
          <Button
            type="primary"
            icon={<SearchOutlined />}
            onClick={submitSearch}
            loading={searchMut.isPending}
            style={{ marginLeft: "auto" }}
          >
            搜索
          </Button>
        </Space>
      </div>

      {searchMut.isPending ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : results ? (
        <>
          {results.rate_limited_sources.length > 0 && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 12 }}
              message={`部分源被限流:${results.rate_limited_sources.join(", ")} — 已自动 fallback`}
            />
          )}

          {results.expanded_keywords.length > 1 && (
            <div
              style={{
                marginBottom: 12,
                padding: "8px 12px",
                background: "var(--accent-bg-soft)",
                border: "1px solid var(--border-default)",
                borderRadius: "var(--radius-sm)",
                fontSize: 12,
                color: "var(--text-secondary)",
                display: "flex",
                flexWrap: "wrap",
                gap: 6,
                alignItems: "center",
              }}
            >
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 10,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  color: "var(--text-tertiary)",
                }}
              >
                已扩展为
              </span>
              {results.expanded_keywords.map((kw) => (
                <Tag
                  key={kw}
                  style={{
                    background: "var(--bg-surface)",
                    border: "1px solid var(--border-default)",
                    color: "var(--text-primary)",
                    fontFamily: "var(--font-mono)",
                    fontSize: 11,
                    margin: 0,
                  }}
                >
                  {kw}
                </Tag>
              ))}
              <span
                style={{
                  marginLeft: "auto",
                  fontSize: 10,
                  color: "var(--text-tertiary)",
                }}
              >
                结果已按相关度重排
              </span>
            </div>
          )}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 12,
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
              {items.length} 条结果 · 已选 {selectedItems.length} · 查询源:{" "}
              {results.sources_queried.join(" · ")}
            </div>
            <Space>
              <Button
                size="small"
                onClick={() => toggleAll(false)}
                disabled={items.length === 0}
              >
                清空
              </Button>
              <Button
                size="small"
                onClick={() => toggleAll(true)}
                disabled={items.length === 0}
              >
                全选
              </Button>
              <Dropdown
                menu={topicMenu}
                placement="bottomRight"
                trigger={["click"]}
                disabled={selectedItems.length === 0}
              >
                <Button
                  type="primary"
                  icon={<ThunderboltOutlined />}
                  loading={ingestMut.isPending}
                  disabled={selectedItems.length === 0}
                >
                  入库到 ↓ ({selectedItems.length})
                </Button>
              </Dropdown>
            </Space>
          </div>

          {items.length === 0 ? (
            <Empty description="没有找到匹配的论文 — 换个词或扩大时间窗试试" />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {items.map((it) => {
                const k = itemKey(it);
                const isPicked = picked.has(k);
                return (
                  <div
                    key={k}
                    onClick={() => toggle(it)}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "24px 1fr",
                      gap: 12,
                      padding: "12px 14px",
                      border: `1px solid ${
                        isPicked ? "var(--accent-deep)" : "var(--border-subtle)"
                      }`,
                      background: isPicked
                        ? "var(--accent-bg-soft)"
                        : "var(--bg-surface)",
                      borderRadius: "var(--radius-sm)",
                      cursor: "pointer",
                      transition: "all var(--d-fast) var(--ease-out)",
                    }}
                  >
                    <div style={{ paddingTop: 2 }}>
                      <Checkbox checked={isPicked} />
                    </div>
                    <div>
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
                        <span
                          style={{
                            color: SOURCE_COLOR[it.source] || "var(--text-secondary)",
                          }}
                        >
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
                          <Tag style={{ marginInlineEnd: 0 }}>{it.matched_keyword}</Tag>
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
      ) : (
        <div
          style={{
            padding: "60px 0",
            textAlign: "center",
            color: "var(--text-tertiary)",
          }}
        >
          <CompassOutlined style={{ fontSize: 32, color: "var(--accent)" }} />
          <Typography.Paragraph style={{ marginTop: 12, fontSize: 13 }}>
            从一个关键词开始 — 不需要先建课题。
          </Typography.Paragraph>
        </div>
      )}

      <Modal
        open={newTopicOpen}
        onCancel={() => setNewTopicOpen(false)}
        onOk={() => {
          if (!newTopicName.trim()) {
            message.warning("先给新课题起个名字");
            return;
          }
          ingestMut.mutate({ newTopicName: newTopicName.trim() });
        }}
        confirmLoading={ingestMut.isPending}
        title="新建临时课题"
        okText="建立并入库"
      >
        <Typography.Paragraph type="secondary" style={{ fontSize: 13 }}>
          课题默认 <b>不自动追踪</b>(enabled=false) — 仅入库你选中的 {selectedItems.length} 篇。
          之后可在课题详情页打开调度。
        </Typography.Paragraph>
        <Input
          autoFocus
          placeholder="例如:Diffusion 综述合集"
          value={newTopicName}
          onChange={(e) => setNewTopicName(e.target.value)}
          onPressEnter={() => {
            if (newTopicName.trim()) ingestMut.mutate({ newTopicName: newTopicName.trim() });
          }}
        />
      </Modal>
    </div>
  );
}
