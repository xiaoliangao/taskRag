import {
  App,
  Button,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Select,
  Switch,
  TimePicker,
} from "antd";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useNavigate } from "react-router-dom";

import { apiErrorMessage } from "../api/client";
import { deleteTopic, updateTopic, type TopicUpdateBody } from "../api/topics";
import type { Topic } from "../types/api";

interface Props {
  topic: Topic;
}

export default function TopicSettingsForm({ topic }: Props) {
  const [form] = Form.useForm();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { message } = App.useApp();

  const updateMut = useMutation({
    mutationFn: (body: TopicUpdateBody) => updateTopic(topic.id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["topic", topic.id] });
      qc.invalidateQueries({ queryKey: ["topics"] });
      message.success("已保存");
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const deleteMut = useMutation({
    mutationFn: () => deleteTopic(topic.id),
    onSuccess: () => {
      message.success("课题已删除");
      qc.invalidateQueries({ queryKey: ["topics"] });
      navigate("/topics");
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const onSave = async () => {
    const v = await form.validateFields();
    updateMut.mutate({
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
      enabled: v.enabled,
    });
  };

  return (
    <div style={{ maxWidth: 720 }}>
      <Form
        form={form}
        layout="vertical"
        requiredMark={false}
        initialValues={{
          name: topic.name,
          description: topic.description,
          keywords: topic.keywords.join(", "),
          sources: topic.sources,
          schedule_type: topic.schedule_type,
          schedule_time: dayjs(topic.schedule_time, "HH:mm"),
          max_results: topic.max_results_per_source_per_run,
          enabled: topic.enabled,
        }}
      >
        <div className="settings-section">
          <h3>课题信息</h3>
          <p>基本元数据 — 调整名称、描述、关键词。</p>

          <Form.Item
            name="name"
            label="课题名称"
            rules={[{ required: true, max: 80 }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item
            name="keywords"
            label="关键词（英文逗号分隔）"
            rules={[{ required: true }]}
          >
            <Input />
          </Form.Item>
        </div>

        <div className="settings-section">
          <h3>采集</h3>
          <p>决定从哪些源、什么时间、每次拉多少。</p>

          <Form.Item name="sources" label="数据源" rules={[{ required: true }]}>
            <Select
              mode="multiple"
              options={[
                { value: "arxiv", label: "arXiv（直连）" },
                { value: "openalex", label: "OpenAlex（最稳）" },
                { value: "semantic_scholar", label: "Semantic Scholar" },
                { value: "huggingface", label: "HuggingFace（占位）", disabled: true },
                { value: "github", label: "GitHub（占位）", disabled: true },
              ]}
            />
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
              <TimePicker format="HH:mm" minuteStep={5} style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item name="max_results" label="每源最多采集">
              <InputNumber min={1} max={50} style={{ width: "100%" }} />
            </Form.Item>
          </div>

          <Form.Item
            name="enabled"
            label="启用自动调度"
            valuePropName="checked"
            style={{ marginBottom: 0 }}
          >
            <Switch />
          </Form.Item>
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginTop: 16,
          }}
        >
          <Popconfirm
            title="确定删除该课题？"
            description="将清理关联，但不删除全局文档与向量"
            onConfirm={() => deleteMut.mutate()}
            okText="删除"
            cancelText="取消"
          >
            <Button danger loading={deleteMut.isPending}>
              删除课题
            </Button>
          </Popconfirm>
          <Button type="primary" onClick={onSave} loading={updateMut.isPending}>
            保存修改
          </Button>
        </div>
      </Form>
    </div>
  );
}
