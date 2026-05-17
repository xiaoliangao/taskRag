import { App, Form, Input, InputNumber, Modal, Select, TimePicker } from "antd";
import dayjs from "dayjs";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiErrorMessage } from "../api/client";
import { createTopic, type TopicCreateBody } from "../api/topics";

interface Props {
  open: boolean;
  onClose: () => void;
}

const SOURCE_OPTIONS = [
  { value: "arxiv", label: "arXiv（直连）" },
  { value: "openalex", label: "OpenAlex（240M+ 论文，含 arXiv，最稳）" },
  { value: "semantic_scholar", label: "Semantic Scholar" },
  { value: "huggingface", label: "HuggingFace（占位）", disabled: true },
  { value: "github", label: "GitHub（占位）", disabled: true },
];

export default function TopicCreateModal({ open, onClose }: Props) {
  const [form] = Form.useForm();
  const qc = useQueryClient();
  const { message } = App.useApp();

  const mutation = useMutation({
    mutationFn: (body: TopicCreateBody) => createTopic(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["topics"] });
      message.success("课题已创建，正在后台执行 30 天回填");
      form.resetFields();
      onClose();
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const onSubmit = async () => {
    const v = await form.validateFields();
    mutation.mutate({
      name: v.name,
      description: v.description,
      keywords: (v.keywords || "")
        .split(",")
        .map((s: string) => s.trim())
        .filter(Boolean),
      sources: v.sources,
      schedule_type: v.schedule_type,
      schedule_time: dayjs(v.schedule_time).format("HH:mm"),
      max_results_per_source_per_run: v.max_results,
      enabled: true,
    });
  };

  return (
    <Modal
      title={
        <div>
          <div className="page-eyebrow" style={{ marginBottom: 4 }}>
            New Research Topic
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
            开辟一个新的研究方向
          </div>
        </div>
      }
      open={open}
      onCancel={onClose}
      onOk={onSubmit}
      okText="创建并开始回填"
      cancelText="取消"
      width={560}
      confirmLoading={mutation.isPending}
      destroyOnClose
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          sources: ["arxiv"],
          schedule_type: "daily",
          schedule_time: dayjs("09:00", "HH:mm"),
          max_results: 3,
        }}
        requiredMark={false}
      >
        <Form.Item
          name="name"
          label="课题名称"
          rules={[{ required: true, max: 80 }]}
        >
          <Input placeholder="如：Stereo Matching" />
        </Form.Item>

        <Form.Item name="description" label="描述">
          <Input.TextArea
            rows={2}
            maxLength={1000}
            placeholder="可选，让助手更理解你的关注点"
          />
        </Form.Item>

        <Form.Item
          name="keywords"
          label={
            <span>
              关键词
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 10.5,
                  color: "var(--text-muted)",
                  marginLeft: 6,
                  letterSpacing: "0.05em",
                  textTransform: "uppercase",
                }}
              >
                · 英文逗号分隔 · 1-10 个
              </span>
            </span>
          }
          rules={[
            { required: true, message: "至少一个关键词" },
            {
              validator: (_, v) => {
                const arr = (v || "")
                  .split(",")
                  .map((s: string) => s.trim())
                  .filter(Boolean);
                if (arr.length < 1) return Promise.reject(new Error("至少 1 个"));
                if (arr.length > 10) return Promise.reject(new Error("最多 10 个"));
                if (arr.some((k: string) => k.length > 80))
                  return Promise.reject(new Error("每个关键词最多 80 字符"));
                return Promise.resolve();
              },
            },
          ]}
        >
          <Input placeholder="stereo matching, transformer stereo, depth estimation" />
        </Form.Item>

        <Form.Item name="sources" label="数据源" rules={[{ required: true }]}>
          <Select mode="multiple" options={SOURCE_OPTIONS} />
        </Form.Item>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
          <Form.Item name="schedule_type" label="调度">
            <Select
              options={[
                { value: "daily", label: "每天" },
                { value: "weekly", label: "每周" },
              ]}
            />
          </Form.Item>
          <Form.Item name="schedule_time" label="时间">
            <TimePicker
              format="HH:mm"
              minuteStep={5}
              style={{ width: "100%" }}
            />
          </Form.Item>
          <Form.Item name="max_results" label="每源最多采集">
            <InputNumber min={1} max={50} style={{ width: "100%" }} />
          </Form.Item>
        </div>
      </Form>
    </Modal>
  );
}
