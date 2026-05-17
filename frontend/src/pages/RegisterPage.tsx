import { App, Button, Form, Input } from "antd";
import { useNavigate } from "react-router-dom";

import { login, register } from "../api/auth";
import { apiErrorMessage } from "../api/client";
import { useAuthStore } from "../stores/authStore";

interface FormValues {
  email: string;
  password: string;
}

export default function RegisterPage() {
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);
  const { message } = App.useApp();

  const onFinish = async (vals: FormValues) => {
    try {
      await register(vals.email, vals.password);
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

        <Form<FormValues> layout="vertical" onFinish={onFinish} requiredMark={false}>
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

          <Button type="primary" htmlType="submit" size="large" block>
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
