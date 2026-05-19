import { App, Button, Form, Input } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { login, register, sendVerificationCode } from "../api/auth";
import { apiErrorMessage } from "../api/client";
import { useAuthStore } from "../stores/authStore";

interface FormValues {
  email: string;
  password: string;
  code: string;
}

export default function RegisterPage() {
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);
  const { message } = App.useApp();
  const [form] = Form.useForm<FormValues>();

  const [cooldown, setCooldown] = useState(0);
  const [sending, setSending] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Countdown ticker — drives the "重新发送 (Ns)" pill on the send button.
  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setInterval(() => setCooldown((c) => Math.max(0, c - 1)), 1000);
    return () => clearInterval(t);
  }, [cooldown]);

  const handleSendCode = async () => {
    try {
      const email = form.getFieldValue("email");
      await form.validateFields(["email"]);
      if (!email) return;
      setSending(true);
      const res = await sendVerificationCode(email);
      setCooldown(res.cooldown_s || 60);
      if (res.delivery === "email") {
        message.success("验证码已发送,请查收邮箱");
      } else {
        message.warning("SMTP 未配置,验证码已打印到后端日志(开发模式)");
      }
    } catch (e) {
      // validateFields throws ErrorInfo; only show toast for real API errors
      if (e && typeof e === "object" && "response" in (e as any)) {
        message.error(apiErrorMessage(e));
      }
    } finally {
      setSending(false);
    }
  };

  const onFinish = async (vals: FormValues) => {
    try {
      setSubmitting(true);
      await register(vals.email, vals.password, vals.code);
      const res = await login(vals.email, vals.password);
      setAuth({
        accessToken: res.access_token,
        refreshToken: res.refresh_token,
        user: res.user,
      });
      message.success("欢迎加入");
      navigate("/topics");
    } catch (e) {
      message.error(apiErrorMessage(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-scene">
      <div className="auth-card entry">
        <div className="auth-brand">
          <div className="brand-glyph">/T</div>
          <div className="name">TaskRAG</div>
        </div>

        <div className="page-eyebrow" style={{ marginBottom: 8 }}>
          Research Lab · Create account
        </div>
        <h1 className="auth-title">
          搭一个<br />
          属于你的<span style={{ color: "var(--accent)" }}>研究台</span>
        </h1>
        <p className="auth-subtitle">
          下一秒起 — 系统将为你追踪整个领域的进展。
        </p>

        <Form<FormValues>
          form={form}
          layout="vertical"
          onFinish={onFinish}
          requiredMark={false}
        >
          <Form.Item
            name="email"
            label="邮箱"
            rules={[{ required: true, type: "email", message: "请输入有效邮箱" }]}
          >
            <Input
              size="large"
              placeholder="you@research.lab"
              autoComplete="email"
              style={{ fontFamily: "var(--font-mono)", fontSize: 13 }}
            />
          </Form.Item>

          <Form.Item
            name="code"
            label="邮箱验证码"
            rules={[
              { required: true, message: "请输入收到的 6 位验证码" },
              { pattern: /^\d{6}$/, message: "验证码是 6 位数字" },
            ]}
          >
            <Input
              size="large"
              maxLength={6}
              placeholder="6 位数字"
              autoComplete="one-time-code"
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 16,
                letterSpacing: "0.35em",
              }}
              suffix={
                <Button
                  size="small"
                  type="text"
                  disabled={cooldown > 0 || sending}
                  loading={sending}
                  onClick={handleSendCode}
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 11,
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                    color: cooldown > 0 ? "var(--text-tertiary)" : "var(--accent)",
                  }}
                >
                  {cooldown > 0 ? `重新发送 ${cooldown}s` : "发送验证码"}
                </Button>
              }
            />
          </Form.Item>

          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: true, min: 6, message: "至少 6 位" }]}
          >
            <Input.Password
              size="large"
              autoComplete="new-password"
              style={{ fontFamily: "var(--font-mono)", fontSize: 13 }}
            />
          </Form.Item>

          <Button
            type="primary"
            htmlType="submit"
            size="large"
            block
            loading={submitting}
          >
            创建账号
          </Button>

          <div style={{ textAlign: "center", marginTop: 20 }}>
            <a
              onClick={() => navigate("/login")}
              style={{
                cursor: "pointer",
                fontSize: 12,
                color: "var(--text-tertiary)",
              }}
            >
              已有账号？返回登录
            </a>
          </div>
        </Form>
      </div>
    </div>
  );
}
