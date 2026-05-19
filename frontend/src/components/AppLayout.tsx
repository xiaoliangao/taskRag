import {
  AppstoreOutlined,
  BellOutlined,
  ClusterOutlined,
  CrownOutlined,
  HeartOutlined,
  LogoutOutlined,
  PlusOutlined,
  SettingOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { Badge, Dropdown, Tooltip } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { fetchMe, logout } from "../api/auth";
import { listNotifications } from "../api/notifications";
import { listTopics } from "../api/topics";
import { useAuthStore } from "../stores/authStore";
import PageTransition from "./PageTransition";
import ThemeToggle from "./ThemeToggle";
import TopicCreateModal from "./TopicCreateModal";

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, refreshToken, clear } = useAuthStore();
  const [createOpen, setCreateOpen] = useState(false);

  // Refresh `is_admin` on mount — persisted user from older sessions may not
  // have it set, and admin elevation needs to take effect without re-login.
  useEffect(() => {
    if (!user) return;
    fetchMe()
      .then((me) => {
        if ((me.is_admin ?? false) !== (user.is_admin ?? false)) {
          useAuthStore.setState({
            user: { ...user, is_admin: me.is_admin ?? false },
          });
        }
      })
      .catch(() => {
        /* token refresh interceptor handles 401 */
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { data: notif } = useQuery({
    queryKey: ["notifications-bell"],
    queryFn: () => listNotifications({ unread_only: true, page_size: 1 }),
    refetchInterval: 15_000,
    enabled: !!user,
  });

  const { data: topics } = useQuery({
    queryKey: ["topics"],
    queryFn: listTopics,
    enabled: !!user,
    refetchInterval: 60_000,
  });

  const handleLogout = async () => {
    if (refreshToken) {
      try {
        await logout(refreshToken);
      } catch {
        /* ignore */
      }
    }
    clear();
    navigate("/login");
  };

  const isTopicListActive = location.pathname === "/topics" || location.pathname === "/";
  const isCrossTopicActive = location.pathname.startsWith("/qa/cross-topic");
  const isNotificationsActive = location.pathname.startsWith("/notifications");
  const isSettingsActive = location.pathname.startsWith("/settings");
  const isAdminUsersActive = location.pathname.startsWith("/admin/users");
  const isAdminHealthActive = location.pathname.startsWith("/admin/health");
  const activeTopicId = (() => {
    const m = location.pathname.match(/^\/topics\/(\d+)/);
    return m ? Number(m[1]) : null;
  })();

  const initial = (user?.email || "?")[0].toUpperCase();

  const userMenu = {
    items: [
      {
        key: "settings",
        icon: <SettingOutlined />,
        label: "设置",
        onClick: () => navigate("/settings"),
      },
      { type: "divider" as const },
      {
        key: "logout",
        icon: <LogoutOutlined />,
        label: "退出登录",
        onClick: handleLogout,
      },
    ],
  };

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="brand">
          <div className="brand-glyph">/T</div>
          <div>TaskRAG</div>
        </div>

        <div className="nav-section">
          <div className="nav-label">主菜单</div>
          <div
            className={`nav-item ${isTopicListActive ? "active" : ""}`}
            onClick={() => navigate("/topics")}
          >
            <AppstoreOutlined />
            <span>所有课题</span>
            <span className="count">{topics?.length ?? 0}</span>
          </div>
          <div
            className={`nav-item ${isCrossTopicActive ? "active" : ""}`}
            onClick={() => navigate("/qa/cross-topic")}
          >
            <ClusterOutlined />
            <span>跨课题问答</span>
          </div>
          <div
            className={`nav-item ${isNotificationsActive ? "active" : ""}`}
            onClick={() => navigate("/notifications")}
          >
            <BellOutlined />
            <span>通知</span>
            {notif?.unread_count ? (
              <span className="count" style={{ color: "var(--accent)" }}>
                {notif.unread_count}
              </span>
            ) : null}
          </div>
          <div
            className={`nav-item ${isSettingsActive ? "active" : ""}`}
            onClick={() => navigate("/settings")}
          >
            <SettingOutlined />
            <span>设置</span>
          </div>
        </div>

        {user?.is_admin && (
          <div className="nav-section">
            <div className="nav-label" style={{ color: "var(--accent)" }}>
              管理员
            </div>
            <div
              className={`nav-item ${isAdminUsersActive ? "active" : ""}`}
              onClick={() => navigate("/admin/users")}
            >
              <CrownOutlined />
              <span>用户管理</span>
            </div>
            <div
              className={`nav-item ${isAdminHealthActive ? "active" : ""}`}
              onClick={() => navigate("/admin/health")}
            >
              <HeartOutlined />
              <span>服务体征</span>
            </div>
          </div>
        )}

        <div className="nav-section" style={{ flex: 1, overflow: "auto" }}>
          <div
            className="nav-label"
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span>我的课题</span>
            <Tooltip title="新建课题" placement="right">
              <span
                onClick={(e) => {
                  e.stopPropagation();
                  setCreateOpen(true);
                }}
                style={{
                  cursor: "pointer",
                  color: "var(--text-tertiary)",
                  padding: "0 6px",
                }}
              >
                <PlusOutlined style={{ fontSize: 11 }} />
              </span>
            </Tooltip>
          </div>
          {(topics ?? []).map((t) => (
            <div
              key={t.id}
              className={`nav-item ${activeTopicId === t.id ? "active" : ""}`}
              onClick={() => navigate(`/topics/${t.id}`)}
            >
              <span
                className={`dot ${t.enabled ? "live" : ""}`}
                style={{
                  background: t.enabled ? "var(--accent)" : "var(--text-muted)",
                }}
              />
              <span
                style={{
                  flex: 1,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {t.name}
              </span>
              <span className="count">{t.document_count}</span>
            </div>
          ))}
          {topics && topics.length === 0 && (
            <div
              style={{
                padding: "8px 10px",
                color: "var(--text-muted)",
                fontSize: 12,
                fontStyle: "italic",
              }}
            >
              暂无课题
            </div>
          )}
        </div>

        <div className="sidebar-footer">
          <Dropdown menu={userMenu} placement="topRight" trigger={["click"]}>
            <div className="user-chip">
              <div className="avatar">{initial}</div>
              <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                  {user?.email}
                </div>
              </div>
            </div>
          </Dropdown>
        </div>
      </aside>

      <main className="app-main">
        <header className="app-topbar">
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              color: "var(--text-tertiary)",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
            }}
          >
            <span className="dot live" />
            <span>System online</span>
            <span style={{ opacity: 0.4 }}>·</span>
            <span style={{ color: "var(--text-muted)" }}>
              {new Date().toLocaleDateString("zh-CN", {
                year: "numeric",
                month: "2-digit",
                day: "2-digit",
              })}
            </span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <ThemeToggle />
            <Tooltip title="通知">
              <button className="icon-btn" onClick={() => navigate("/notifications")}>
                <Badge count={notif?.unread_count ?? 0} size="small" offset={[2, -2]}>
                  <BellOutlined style={{ fontSize: 14 }} />
                </Badge>
              </button>
            </Tooltip>
            <Tooltip title="新建课题">
              <button
                className="icon-btn"
                onClick={() => setCreateOpen(true)}
                style={{ color: "var(--accent)" }}
              >
                <ThunderboltOutlined style={{ fontSize: 14 }} />
              </button>
            </Tooltip>
          </div>
        </header>

        <div className="app-content">
          <PageTransition>
            <Outlet />
          </PageTransition>
        </div>
      </main>

      <TopicCreateModal open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}
