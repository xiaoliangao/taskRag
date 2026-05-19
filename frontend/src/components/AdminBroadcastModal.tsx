import { App, Button, Input, Modal, Radio, Space, Typography } from "antd";
import { useState } from "react";

import { adminBroadcast } from "../api/admin";
import { apiErrorMessage } from "../api/client";

interface Props {
  open: boolean;
  selectedUserIds: number[];
  onClose: () => void;
}

export default function AdminBroadcastModal({ open, selectedUserIds, onClose }: Props) {
  const { message } = App.useApp();
  const [target, setTarget] = useState<"all" | "selected">(
    selectedUserIds.length > 0 ? "selected" : "all"
  );
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);

  const handleSend = async () => {
    if (!subject.trim() || !body.trim()) {
      message.warning("标题和内容都要填");
      return;
    }
    setSending(true);
    try {
      const res = await adminBroadcast({
        subject: subject.trim(),
        body: body.trim(),
        target,
        user_ids: target === "selected" ? selectedUserIds : [],
      });
      if (res.delivery === "log") {
        message.warning(`SMTP 未配置,${res.skipped} 条记录到后端日志`);
      } else {
        message.success(`已派发 ${res.queued} 封,跳过 ${res.skipped} 封`);
      }
      onClose();
      setSubject("");
      setBody("");
    } catch (e) {
      message.error(apiErrorMessage(e));
    } finally {
      setSending(false);
    }
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      title={
        <div>
          <div className="page-eyebrow" style={{ marginBottom: 4 }}>
            Admin · Broadcast
          </div>
          <div
            style={{
              fontFamily: "var(--font-display)",
              fontStyle: "italic",
              fontSize: 22,
              fontWeight: 400,
              color: "var(--text-primary)",
              lineHeight: 1.2,
            }}
          >
            给用户群发邮件
          </div>
        </div>
      }
      footer={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" onClick={handleSend} loading={sending}>
            发送
          </Button>
        </Space>
      }
      width={640}
      destroyOnClose
    >
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <div>
          <div className="eyebrow" style={{ marginBottom: 6 }}>
            收件人
          </div>
          <Radio.Group value={target} onChange={(e) => setTarget(e.target.value)}>
            <Radio.Button value="all">全体活跃用户</Radio.Button>
            <Radio.Button
              value="selected"
              disabled={selectedUserIds.length === 0}
            >
              已选用户 ({selectedUserIds.length})
            </Radio.Button>
          </Radio.Group>
          <Typography.Paragraph
            type="secondary"
            style={{ fontSize: 12, marginTop: 6, marginBottom: 0 }}
          >
            被禁用、关闭邮件通知的用户会自动跳过。
          </Typography.Paragraph>
        </div>

        <div>
          <div className="eyebrow" style={{ marginBottom: 6 }}>
            标题
          </div>
          <Input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="例如:本周 TaskRAG 更新摘要"
            maxLength={200}
          />
        </div>

        <div>
          <div className="eyebrow" style={{ marginBottom: 6 }}>
            正文
          </div>
          <Input.TextArea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={8}
            placeholder="纯文本,换行会保留。最多 2 万字。"
            maxLength={20_000}
            showCount
          />
        </div>
      </Space>
    </Modal>
  );
}
