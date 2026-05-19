import { ReloadOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Button, Space, Spin, Tag, Tooltip, Typography } from "antd";
import dayjs from "dayjs";

import { adminHealth, type AdminHealthComponent } from "../api/admin";

const STATUS_TONE: Record<string, { color: string; label: string }> = {
  ok: { color: "var(--success)", label: "OK" },
  warn: { color: "var(--warning)", label: "WARN" },
  fail: { color: "var(--danger)", label: "FAIL" },
  skipped: { color: "var(--text-tertiary)", label: "SKIPPED" },
};

function ComponentCard({ c }: { c: AdminHealthComponent }) {
  const tone = STATUS_TONE[c.status] ?? STATUS_TONE.skipped;
  return (
    <div
      style={{
        position: "relative",
        padding: "18px 20px",
        border: "1px solid var(--border-default)",
        borderLeft: `3px solid ${tone.color}`,
        borderRadius: "var(--radius-md)",
        background: "var(--bg-surface)",
        minHeight: 110,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
        }}
      >
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "var(--text-tertiary)",
          }}
        >
          {c.name}
        </div>
        <Tag color={tone.color === "var(--success)" ? "success" : tone.color === "var(--warning)" ? "warning" : tone.color === "var(--danger)" ? "error" : "default"}>
          {tone.label}
        </Tag>
      </div>
      <div
        style={{
          fontFamily: "var(--font-display)",
          fontStyle: "italic",
          fontSize: 22,
          marginTop: 6,
          color: "var(--text-primary)",
        }}
      >
        {c.latency_ms != null ? `${c.latency_ms.toFixed(0)} ms` : "—"}
      </div>
      {c.detail && (
        <div
          style={{
            marginTop: 8,
            fontSize: 12,
            color: "var(--text-tertiary)",
            wordBreak: "break-all",
          }}
        >
          {c.detail}
        </div>
      )}
    </div>
  );
}

export default function AdminHealthPage() {
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["admin-health"],
    queryFn: adminHealth,
    refetchInterval: 30_000,
  });

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div>
          <div className="page-eyebrow">Admin · Health</div>
          <h1 className="page-title">
            服务<span style={{ fontStyle: "italic", color: "var(--accent)" }}>体征</span>
          </h1>
          <p className="page-subtitle">
            Postgres / Redis / Qdrant / SMTP / Celery — 每 30 秒自动刷新。
          </p>
        </div>
        <Space>
          <Tooltip title={data?.checked_at ? `上次刷新 ${dayjs(data.checked_at).format("HH:mm:ss")}` : ""}>
            <Button
              icon={<ReloadOutlined spin={isFetching} />}
              onClick={() => refetch()}
            >
              立即刷新
            </Button>
          </Tooltip>
        </Space>
      </div>

      {isLoading ? (
        <div style={{ textAlign: "center", padding: 60 }}>
          <Spin />
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
            gap: 12,
          }}
        >
          {data?.components.map((c) => (
            <ComponentCard key={c.name} c={c} />
          ))}
        </div>
      )}

      <Typography.Paragraph
        type="secondary"
        style={{ fontSize: 11, fontFamily: "var(--font-mono)", marginTop: 24 }}
      >
        SMTP 显示 "SKIPPED" 是因为 .env 没填 GMAIL_USERNAME / GMAIL_APP_PASSWORD / EMAIL_FROM。
      </Typography.Paragraph>
    </div>
  );
}
