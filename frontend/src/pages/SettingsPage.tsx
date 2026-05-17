import { App, Button, Form, Select, Skeleton, Switch } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { apiErrorMessage } from "../api/client";
import { getSettings, patchSettings } from "../api/settings";
import { useAuthStore } from "../stores/authStore";

const PROVIDER_OPTIONS = [
  { value: "deepseek", label: "DeepSeek" },
  { value: "qwen", label: "通义千问 Qwen" },
  { value: "siliconflow", label: "SiliconFlow（Qwen2.5）" },
  { value: "openai", label: "OpenAI" },
];

const MODEL_HINTS: Record<string, string[]> = {
  deepseek: ["deepseek-chat", "deepseek-reasoner"],
  qwen: ["qwen-plus", "qwen-max", "qwen-turbo"],
  siliconflow: ["Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-14B-Instruct"],
  openai: ["gpt-4o-mini", "gpt-4o"],
};

export default function SettingsPage() {
  const qc = useQueryClient();
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const user = useAuthStore((s) => s.user);

  const { data, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
  });

  useEffect(() => {
    if (data) {
      form.setFieldsValue({
        ...data,
        preferred_llm_model: data.preferred_llm_model ? [data.preferred_llm_model] : [],
      });
    }
  }, [data, form]);

  const mut = useMutation({
    mutationFn: (body: any) => patchSettings(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      message.success("已保存");
    },
    onError: (e) => message.error(apiErrorMessage(e)),
  });

  const watchedProvider = Form.useWatch("preferred_llm_provider", form);
  const provider =
    watchedProvider || data?.preferred_llm_provider || "deepseek";

  const onFinish = (vals: any) => {
    const llmModel = Array.isArray(vals.preferred_llm_model)
      ? vals.preferred_llm_model[0]
      : vals.preferred_llm_model;
    mut.mutate({ ...vals, preferred_llm_model: llmModel });
  };

  return (
    <div style={{ maxWidth: 760 }}>
      <div style={{ marginBottom: 28 }}>
        <div className="page-eyebrow">Workspace · Settings</div>
        <h1 className="page-title">
          个人<span style={{ color: "var(--accent)", fontStyle: "italic" }}>偏好</span>
        </h1>
        <p className="page-subtitle">
          调整你与助手协作的方式 — 模型、通知、显示偏好。
        </p>
      </div>

      {/* Account section */}
      <div className="settings-section">
        <h3>账号</h3>
        <p>登录信息只读 — 演示阶段不开放修改邮箱。</p>
        <div className="settings-row">
          <div>
            <div className="label">邮箱</div>
            <div className="hint">登录账号</div>
          </div>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 13,
              color: "var(--text-primary)",
            }}
          >
            {user?.email}
          </div>
        </div>
      </div>

      {isLoading ? (
        <Skeleton active />
      ) : (
        <Form form={form} layout="vertical" onFinish={onFinish}>
          <div className="settings-section">
            <h3>大模型</h3>
            <p>
              切换 LLM provider 需要 backend 的 .env 中已配置对应 API Key。
            </p>

            <div className="settings-row">
              <div>
                <div className="label">Provider</div>
                <div className="hint">问答时使用的模型提供商</div>
              </div>
              <Form.Item
                name="preferred_llm_provider"
                style={{ margin: 0, width: 240 }}
              >
                <Select options={PROVIDER_OPTIONS} />
              </Form.Item>
            </div>

            <div className="settings-row">
              <div>
                <div className="label">Model</div>
                <div className="hint">具体模型名（可输入自定义）</div>
              </div>
              <Form.Item
                name="preferred_llm_model"
                style={{ margin: 0, width: 240 }}
              >
                <Select
                  options={(MODEL_HINTS[provider] || []).map((m) => ({
                    value: m,
                    label: m,
                  }))}
                  allowClear
                  showSearch
                  mode="tags"
                  maxTagCount={1}
                  placeholder="选择或输入"
                />
              </Form.Item>
            </div>
          </div>

          <div className="settings-section">
            <h3>通知</h3>
            <p>采集完成、任务失败、研究脉搏等会通过这些渠道发出。</p>

            <div className="settings-row">
              <div>
                <div className="label">邮件通知</div>
                <div className="hint">通过 Gmail SMTP 发送</div>
              </div>
              <Form.Item
                name="email_notifications_enabled"
                valuePropName="checked"
                style={{ margin: 0 }}
              >
                <Switch />
              </Form.Item>
            </div>
          </div>

          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              gap: 10,
              marginTop: 16,
            }}
          >
            <Button type="primary" htmlType="submit" loading={mut.isPending}>
              保存设置
            </Button>
          </div>
        </Form>
      )}
    </div>
  );
}
