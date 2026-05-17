import { App, Button, Form, Input } from "antd";
import { useNavigate } from "react-router-dom";

import { login } from "../api/auth";
import { apiErrorMessage } from "../api/client";
import { useAuthStore } from "../stores/authStore";

interface FormValues {
  email: string;
  password: string;
}

const DEMO_EMAIL = "demo@example.com";
const DEMO_PASSWORD = "demo123";

export default function LoginPage() {
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);
  const { message } = App.useApp();
  const [form] = Form.useForm<FormValues>();

  const onFinish = async (vals: FormValues) => {
    try {
      const res = await login(vals.email, vals.password);
      setAuth({
        accessToken: res.access_token,
        refreshToken: res.refresh_token,
        user: res.user,
      });
      navigate("/topics");
    } catch (e) {
      message.error(apiErrorMessage(e));
    }
  };

  const fillDemo = () => {
    form.setFieldsValue({ email: DEMO_EMAIL, password: DEMO_PASSWORD });
  };

  return (
    <div className="auth-scene">
      <div className="auth-card entry">
        <div className="auth-brand">
          <div className="brand-glyph">/T</div>
          <div className="name">TaskRAG</div>
        </div>

        <div className="page-eyebrow" style={{ marginBottom: 8 }}>
          Research Lab · Sign in
        </div>
        <h1 className="auth-title">
          欢迎回到<br />
          你的<span style={{ color: "var(--accent)" }}>研究台</span>
        </h1>
        <p className="auth-subtitle">
          系统昨晚又帮你做了一些工作 — 让我们看看进展。
        </p>

        <Form<FormValues>
          form={form}
          layout="vertical"
          onFinish={onFinish}
          initialValues={{ email: "", password: "" }}
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
            name="password"
            label="密码"
            rules={[{ required: true, min: 6, message: "至少 6 位" }]}
          >
            <Input.Password
              size="large"
              autoComplete="current-password"
              style={{ fontFamily: "var(--font-mono)", fontSize: 13 }}
            />
          </Form.Item>

          <Button type="primary" htmlType="submit" size="large" block>
            登录
          </Button>

          <div
            style={{
              marginTop: 20,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <button type="button" className="btn-demo" onClick={fillDemo}>
              使用演示账号 →
            </button>
            <a
              onClick={() => navigate("/register")}
              style={{
                cursor: "pointer",
                fontSize: 12,
                color: "var(--text-tertiary)",
              }}
            >
              没有账号？注册
            </a>
          </div>
        </Form>
      </div>
    </div>
  );
}
