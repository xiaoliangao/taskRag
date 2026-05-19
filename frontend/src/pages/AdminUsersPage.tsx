import {
  CrownOutlined,
  DeleteOutlined,
  KeyOutlined,
  LockOutlined,
  SearchOutlined,
  SendOutlined,
  UnlockOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  App,
  Button,
  Input,
  Popconfirm,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { useState } from "react";

import {
  type AdminUserRow,
  deleteAdminUser,
  listAdminUsers,
  patchAdminUser,
  resetUserPassword,
} from "../api/admin";
import { apiErrorMessage } from "../api/client";
import AdminBroadcastModal from "../components/AdminBroadcastModal";
import { useAuthStore } from "../stores/authStore";

export default function AdminUsersPage() {
  const qc = useQueryClient();
  const { message, modal } = App.useApp();
  const me = useAuthStore((s) => s.user);

  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selected, setSelected] = useState<number[]>([]);
  const [broadcastOpen, setBroadcastOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["admin-users", q, page, pageSize],
    queryFn: () => listAdminUsers({ q: q || undefined, page, page_size: pageSize }),
  });

  const patch = useMutation({
    mutationFn: ({ id, ...body }: { id: number } & Parameters<typeof patchAdminUser>[1]) =>
      patchAdminUser(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
    onError: (e) => message.error(apiErrorMessage(e)),
  });
  const del = useMutation({
    mutationFn: (id: number) => deleteAdminUser(id),
    onSuccess: () => {
      message.success("已删除");
      qc.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });
  const reset = useMutation({
    mutationFn: (id: number) => resetUserPassword(id),
    onSuccess: (r) => {
      if (r.delivery === "email") {
        message.success("临时密码已发送到该用户邮箱");
      } else {
        modal.info({
          title: "SMTP 未配置 — 临时密码",
          width: 480,
          content: (
            <div>
              <p>请把这串临时密码手动发给用户:</p>
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 18,
                  letterSpacing: "0.1em",
                  padding: "12px 16px",
                  background: "var(--bg-inset)",
                  border: "1px solid var(--border-default)",
                  borderRadius: 6,
                  marginTop: 8,
                  userSelect: "all",
                }}
              >
                {r.new_password_preview}
              </div>
            </div>
          ),
        });
      }
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const columns: ColumnsType<AdminUserRow> = [
    {
      title: "ID",
      dataIndex: "id",
      width: 64,
      render: (v) => (
        <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-tertiary)" }}>
          #{v}
        </span>
      ),
    },
    {
      title: "邮箱",
      dataIndex: "email",
      render: (v: string, row) => (
        <div>
          <div style={{ fontWeight: 500 }}>
            {v}
            {row.id === me?.id && (
              <Tag color="processing" style={{ marginLeft: 8 }}>
                你
              </Tag>
            )}
          </div>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              color: "var(--text-tertiary)",
            }}
          >
            {dayjs(row.created_at).format("YYYY-MM-DD HH:mm")}
          </div>
        </div>
      ),
    },
    {
      title: "角色",
      dataIndex: "is_admin",
      width: 100,
      render: (v: boolean) =>
        v ? (
          <Tag icon={<CrownOutlined />} color="var(--accent-deep)" style={{ color: "var(--accent)" }}>
            ADMIN
          </Tag>
        ) : (
          <Tag>user</Tag>
        ),
    },
    {
      title: "状态",
      dataIndex: "disabled_at",
      width: 100,
      render: (v: string | null) =>
        v ? (
          <Tag color="error">已禁用</Tag>
        ) : (
          <Tag color="success">活跃</Tag>
        ),
    },
    {
      title: "资源",
      width: 140,
      render: (_: unknown, row) => (
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            color: "var(--text-secondary)",
          }}
        >
          {row.topic_count} 课题 · {row.document_count} 文档
        </span>
      ),
    },
    {
      title: "操作",
      width: 320,
      align: "right",
      render: (_: unknown, row) => {
        const isSelf = row.id === me?.id;
        return (
          <Space size={4}>
            <Tooltip title={row.is_admin ? "取消管理员" : "升为管理员"}>
              <Button
                size="small"
                type="text"
                disabled={isSelf && row.is_admin}
                icon={<CrownOutlined />}
                style={{ color: row.is_admin ? "var(--accent)" : undefined }}
                onClick={() => patch.mutate({ id: row.id, is_admin: !row.is_admin })}
              />
            </Tooltip>
            <Tooltip title={row.disabled_at ? "启用" : "禁用"}>
              <Button
                size="small"
                type="text"
                disabled={isSelf}
                icon={row.disabled_at ? <UnlockOutlined /> : <LockOutlined />}
                onClick={() => patch.mutate({ id: row.id, disabled: !row.disabled_at })}
              />
            </Tooltip>
            <Tooltip title="重置密码">
              <Popconfirm
                title="重置该用户密码?"
                description="将生成 12 位临时密码,发送到其邮箱。"
                onConfirm={() => reset.mutate(row.id)}
                okText="确认重置"
                cancelText="取消"
              >
                <Button size="small" type="text" icon={<KeyOutlined />} />
              </Popconfirm>
            </Tooltip>
            <Tooltip title={isSelf ? "不能删除自己" : "删除账号"}>
              <Popconfirm
                title="删除账号?"
                description="该用户的所有课题/文档/聊天记录都会被级联删除,不可恢复。"
                onConfirm={() => del.mutate(row.id)}
                okText="确认删除"
                okType="danger"
                cancelText="取消"
                disabled={isSelf}
              >
                <Button
                  size="small"
                  type="text"
                  danger
                  disabled={isSelf}
                  icon={<DeleteOutlined />}
                />
              </Popconfirm>
            </Tooltip>
          </Space>
        );
      },
    },
  ];

  return (
    <div className="page-wrap">
      <div className="page-header">
        <div>
          <div className="page-eyebrow">Admin · Users</div>
          <h1 className="page-title">
            用户<span style={{ fontStyle: "italic", color: "var(--accent)" }}>账号</span>管理
          </h1>
          <p className="page-subtitle">
            搜索、禁用、提升管理员、重置密码、群发邮件。
          </p>
        </div>
        <Space>
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={() => setBroadcastOpen(true)}
          >
            广播邮件
          </Button>
        </Space>
      </div>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginBottom: 16,
          gap: 12,
          alignItems: "center",
        }}
      >
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="按邮箱搜索"
          style={{ maxWidth: 320 }}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
        />
        <Typography.Text type="secondary" style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
          {data?.total ?? 0} 用户 · 已选 {selected.length}
        </Typography.Text>
      </div>

      <Table<AdminUserRow>
        rowKey="id"
        loading={isLoading}
        dataSource={data?.items || []}
        columns={columns}
        rowSelection={{
          selectedRowKeys: selected,
          onChange: (keys) => setSelected(keys as number[]),
        }}
        pagination={{
          current: page,
          pageSize,
          total: data?.total ?? 0,
          showSizeChanger: true,
          pageSizeOptions: [10, 20, 50, 100],
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          },
        }}
      />

      <AdminBroadcastModal
        open={broadcastOpen}
        selectedUserIds={selected}
        onClose={() => setBroadcastOpen(false)}
      />
    </div>
  );
}
