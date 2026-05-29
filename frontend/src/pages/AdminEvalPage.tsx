import { PlayCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  App,
  Button,
  Checkbox,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Skeleton,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { useMemo, useState } from "react";

import { apiErrorMessage } from "../api/client";
import {
  type EvalQuestion,
  type EvalRunDetail,
  type EvalRunSummary,
  type PerQuestionRow,
  getEvalRun,
  listEvalQuestions,
  listEvalRuns,
  triggerEvalRun,
} from "../api/adminEval";

const ACCENT = "var(--accent)";
const DIM = "var(--text-tertiary)";

/** Inline SVG sparkline of `recall@5` across recent runs. Renders newest-on-right. */
function MiniTrend({ values, height = 28, width = 160 }: { values: (number | null)[]; height?: number; width?: number }) {
  const valid = values.filter((v): v is number => typeof v === "number");
  if (valid.length < 2) return <span style={{ color: DIM, fontSize: 11 }}>—</span>;
  const min = Math.min(...valid);
  const max = Math.max(...valid);
  const span = Math.max(0.01, max - min);
  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * (width - 4) + 2;
      if (typeof v !== "number") return null;
      const y = height - 2 - ((v - min) / span) * (height - 4);
      return `${x},${y}`;
    })
    .filter(Boolean)
    .join(" ");
  return (
    <svg width={width} height={height} style={{ overflow: "visible" }}>
      <polyline
        fill="none"
        stroke={ACCENT}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
        points={points}
      />
    </svg>
  );
}

function RunDetailDrawer({
  runId,
  open,
  onClose,
}: {
  runId: number | null;
  open: boolean;
  onClose: () => void;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["admin-eval-run", runId],
    queryFn: () => getEvalRun(runId!),
    enabled: open && runId != null,
  });

  const perQ: PerQuestionRow[] = data?.metrics_json?.per_question ?? [];
  const perTag = data?.metrics_json?.per_tag ?? {};
  const faith = data?.metrics_json?.faithfulness;

  const columns: ColumnsType<PerQuestionRow> = [
    { title: "#", dataIndex: "question_id", width: 60 },
    { title: "tag", dataIndex: "tag", width: 100, render: (v) => v ? <Tag>{v}</Tag> : "—" },
    { title: "question", dataIndex: "question", ellipsis: true },
    {
      title: "recall@5",
      dataIndex: "recall@5",
      width: 100,
      render: (v: number) => (
        <span style={{ color: v >= 0.5 ? "var(--success)" : v > 0 ? "var(--warning)" : "var(--danger)" }}>
          {v.toFixed(2)}
        </span>
      ),
    },
    {
      title: "recall@20",
      dataIndex: "recall@20",
      width: 110,
      render: (v: number) =>
        typeof v === "number" ? (
          <span style={{ color: v >= 0.7 ? "var(--success)" : v > 0 ? "var(--warning)" : "var(--danger)" }}>
            {v.toFixed(2)}
          </span>
        ) : "—",
    },
    { title: "MRR", dataIndex: "rr", width: 80, render: (v: number) => (typeof v === "number" ? v.toFixed(2) : "—") },
    // Only present when the run was triggered with generation/judge enabled.
    ...(faith
      ? ([
          {
            title: "忠实度",
            dataIndex: "faithfulness",
            width: 90,
            render: (v: number | null | undefined) =>
              typeof v === "number" ? (
                <span
                  style={{
                    color: v >= 0.7 ? "var(--success)" : v >= 0.5 ? "var(--warning)" : "var(--danger)",
                  }}
                >
                  {v.toFixed(2)}
                </span>
              ) : (
                <span style={{ color: DIM }}>—</span>
              ),
          },
        ] as ColumnsType<PerQuestionRow>)
      : []),
  ];

  return (
    <Drawer open={open} onClose={onClose} width={920} title={data ? `Run #${data.id} · ${data.label}` : "Run"}>
      {isLoading || !data ? (
        <Skeleton active />
      ) : (
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
            {[
              ["recall@5", data.recall_at_5],
              ["recall@20", data.recall_at_20],
              ["MRR", data.mrr],
              ["n", data.n_questions],
            ].map(([k, v]) => (
              <div key={String(k)} className="metric">
                <span className="value" style={{ fontSize: 22 }}>
                  {typeof v === "number" ? (v < 10 ? v.toFixed(3) : v) : "—"}
                </span>
                <span style={{ color: DIM, fontFamily: "var(--font-mono)", fontSize: 11, textTransform: "uppercase" }}>
                  {String(k)}
                </span>
              </div>
            ))}
          </div>

          {faith && (
            <div
              style={{
                padding: "12px 16px",
                background: "var(--bg-surface)",
                border: "1px solid var(--border-default)",
                borderRadius: "var(--radius-md)",
              }}
            >
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 10,
                  color: DIM,
                  marginBottom: 8,
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                }}
              >
                faithfulness · 生成质量 (opt-in · 现跑生成 + LLM judge)
              </div>
              <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                {[
                  ["mean", faith.mean],
                  ["unfaithful", faith.unfaithful_count],
                  ["failed", faith.failed],
                  ["n_judged", faith.n_judged],
                  ["gen_top_n", faith.gen_top_n],
                ].map(([k, v]) => (
                  <div key={String(k)} className="metric">
                    <span
                      className="value"
                      style={{
                        fontSize: 22,
                        color:
                          k === "mean" && typeof v === "number"
                            ? v >= 0.7
                              ? "var(--success)"
                              : v >= 0.5
                                ? "var(--warning)"
                                : "var(--danger)"
                            : undefined,
                      }}
                    >
                      {typeof v === "number" ? (v < 10 ? v.toFixed(3) : v) : "—"}
                    </span>
                    <span
                      style={{
                        color: DIM,
                        fontFamily: "var(--font-mono)",
                        fontSize: 11,
                        textTransform: "uppercase",
                      }}
                    >
                      {String(k)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {Object.keys(perTag).length > 0 && (
            <div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: DIM, marginBottom: 6, letterSpacing: "0.12em", textTransform: "uppercase" }}>
                per-tag
              </div>
              <Space wrap>
                {Object.entries(perTag).map(([tag, m]) => (
                  <Tag key={tag} style={{ padding: "4px 10px" }}>
                    <b>{tag}</b> · n={(m as Record<string, number>).n} · r@5={(m as Record<string, number>)["recall@5"]?.toFixed(2)}
                  </Tag>
                ))}
              </Space>
            </div>
          )}

          <Table<PerQuestionRow>
            size="small"
            rowKey="question_id"
            dataSource={perQ}
            columns={columns}
            pagination={{ pageSize: 30 }}
          />
        </Space>
      )}
    </Drawer>
  );
}

export default function AdminEvalPage() {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const [topicFilter, setTopicFilter] = useState<number | undefined>(undefined);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const runs = useQuery({
    queryKey: ["admin-eval-runs", topicFilter],
    queryFn: () => listEvalRuns(topicFilter),
  });
  const questions = useQuery({
    queryKey: ["admin-eval-questions", topicFilter],
    queryFn: () => listEvalQuestions(topicFilter),
  });

  // Sparkline data: recent 12 runs of the current topic filter, oldest-first.
  const trendValues = useMemo(() => {
    const items = (runs.data ?? []).slice(0, 12).reverse();
    return items.map((r) => r.recall_at_5);
  }, [runs.data]);

  const [form] = Form.useForm<{
    topic_id: number;
    label: string;
    notes?: string;
    run_generation?: boolean;
  }>();
  const trigger = useMutation({
    mutationFn: triggerEvalRun,
    onSuccess: (r) => {
      message.success(`Run #${r.run_id} 完成`);
      qc.invalidateQueries({ queryKey: ["admin-eval-runs"] });
      setSelectedRunId(r.run_id);
      setDrawerOpen(true);
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const runColumns: ColumnsType<EvalRunSummary> = [
    { title: "ID", dataIndex: "id", width: 60 },
    { title: "label", dataIndex: "label", ellipsis: true },
    { title: "topic", dataIndex: "topic_id", width: 70 },
    {
      title: "commit",
      dataIndex: "commit_sha",
      width: 90,
      render: (v: string | null) => v ? <span style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>{v}</span> : "—",
    },
    {
      title: "n",
      dataIndex: "n_questions",
      width: 60,
      render: (v: number) => (v > 0 ? v : <span style={{ color: DIM }}>0</span>),
    },
    {
      title: "recall@5",
      dataIndex: "recall_at_5",
      width: 100,
      render: (v: number | null) =>
        typeof v === "number" ? <b>{v.toFixed(3)}</b> : <span style={{ color: DIM }}>—</span>,
    },
    {
      title: "recall@20",
      dataIndex: "recall_at_20",
      width: 110,
      render: (v: number | null) => (typeof v === "number" ? v.toFixed(3) : "—"),
    },
    {
      title: "MRR",
      dataIndex: "mrr",
      width: 90,
      render: (v: number | null) => (typeof v === "number" ? v.toFixed(3) : "—"),
    },
    {
      title: "when",
      dataIndex: "created_at",
      width: 150,
      render: (v: string) => (
        <Tooltip title={dayjs(v).format("YYYY-MM-DD HH:mm:ss")}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: DIM }}>
            {dayjs(v).fromNow ? dayjs(v).format("MM-DD HH:mm") : v}
          </span>
        </Tooltip>
      ),
    },
  ];

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div>
          <div className="page-eyebrow">Admin · Eval</div>
          <h1 className="page-title">
            评估<span style={{ fontStyle: "italic", color: ACCENT }}>闭环</span>
          </h1>
          <p className="page-subtitle">
            RAGAS-style 检索指标。每次 RAG 改动后跑一次,对比基线。CLI: <code>python -m app.eval.run_eval</code>
          </p>
        </div>
        <Space>
          <InputNumber
            placeholder="按 topic 过滤"
            value={topicFilter}
            onChange={(v) => setTopicFilter(v ? Number(v) : undefined)}
            style={{ width: 140 }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => runs.refetch()}>
            刷新
          </Button>
        </Space>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(320px, 1fr) 320px",
          gap: 18,
          marginBottom: 24,
        }}
      >
        <div
          className="entry"
          style={{
            padding: 18,
            background: "var(--bg-surface)",
            border: "1px solid var(--border-default)",
            borderRadius: "var(--radius-md)",
          }}
        >
          <div className="page-eyebrow" style={{ marginBottom: 8, color: DIM }}>
            recall@5 trend
          </div>
          <MiniTrend values={trendValues} height={48} width={360} />
          <div style={{ marginTop: 8, fontFamily: "var(--font-mono)", fontSize: 11, color: DIM }}>
            最新 12 个 run,从左到右越新 · 当前 topic filter: {topicFilter ?? "全部"}
          </div>
        </div>

        <div
          className="entry"
          style={{
            padding: 18,
            background: "var(--bg-surface)",
            border: "1px solid var(--border-default)",
            borderRadius: "var(--radius-md)",
          }}
        >
          <div className="page-eyebrow" style={{ marginBottom: 12, color: DIM }}>
            触发新 run
          </div>
          <Form
            form={form}
            layout="vertical"
            onFinish={(v) => trigger.mutate(v)}
            initialValues={{ topic_id: topicFilter ?? 2, label: "manual" }}
          >
            <Form.Item label="topic_id" name="topic_id" rules={[{ required: true }]}>
              <InputNumber min={1} style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item label="label" name="label" rules={[{ required: true, max: 120 }]}>
              <Input placeholder="如:after-self-rag" />
            </Form.Item>
            <Form.Item name="run_generation" valuePropName="checked" style={{ marginBottom: 12 }}>
              <Checkbox>
                同时评估生成质量（忠实度）
                <Tooltip title="对每题现跑一次生成 + LLM judge，结果写入 faithfulness 区块。会产生额外 LLM 调用与耗时。">
                  <span style={{ color: DIM, marginLeft: 6, cursor: "help" }}>ⓘ</span>
                </Tooltip>
              </Checkbox>
            </Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              icon={<PlayCircleOutlined />}
              loading={trigger.isPending}
              block
            >
              开始
            </Button>
          </Form>
          <Typography.Paragraph type="secondary" style={{ fontSize: 11, marginTop: 8, marginBottom: 0 }}>
            可能耗时几十秒到几分钟,取决于 golden set 大小。勾选忠实度评估会更慢且产生 LLM 费用。
          </Typography.Paragraph>
        </div>
      </div>

      <Table<EvalRunSummary>
        rowKey="id"
        size="small"
        loading={runs.isLoading}
        dataSource={runs.data ?? []}
        columns={runColumns}
        onRow={(row) => ({
          onClick: () => {
            setSelectedRunId(row.id);
            setDrawerOpen(true);
          },
          style: { cursor: "pointer" },
        })}
        pagination={{ pageSize: 20 }}
      />

      <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginTop: 18 }}>
        Golden set: {questions.data?.length ?? 0} 题
        {questions.data?.length === 0 && (
          <>
            {" · "}
            <code>python -m app.eval.seed_from_chunks --topic 2 --n 30</code> 一键反向生成 30 题
          </>
        )}
      </Typography.Paragraph>

      <RunDetailDrawer
        runId={selectedRunId}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />
    </div>
  );
}
