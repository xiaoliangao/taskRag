import { createBrowserRouter, Navigate } from "react-router-dom";

import AppLayout from "./components/AppLayout";
import RequireAdmin from "./components/RequireAdmin";
import RequireAuth from "./components/RequireAuth";
import AdminEvalPage from "./pages/AdminEvalPage";
import AdminHealthPage from "./pages/AdminHealthPage";
import AdminUsersPage from "./pages/AdminUsersPage";
import CrossTopicChatPage from "./pages/CrossTopicChatPage";
import DiscoverPage from "./pages/DiscoverPage";
import LibraryPage from "./pages/LibraryPage";
import LoginPage from "./pages/LoginPage";
import NotificationsPage from "./pages/NotificationsPage";
import RegisterPage from "./pages/RegisterPage";
import SettingsPage from "./pages/SettingsPage";
import TopicDetailPage from "./pages/TopicDetailPage";
import TopicListPage from "./pages/TopicListPage";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  {
    path: "/",
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Navigate to="/topics" replace /> },
      { path: "discover", element: <DiscoverPage /> },
      { path: "library", element: <LibraryPage /> },
      { path: "topics", element: <TopicListPage /> },
      { path: "topics/:topicId", element: <TopicDetailPage /> },
      { path: "topics/:topicId/:tab", element: <TopicDetailPage /> },
      { path: "qa/cross-topic", element: <CrossTopicChatPage /> },
      { path: "notifications", element: <NotificationsPage /> },
      { path: "settings", element: <SettingsPage /> },
      {
        path: "admin/users",
        element: (
          <RequireAdmin>
            <AdminUsersPage />
          </RequireAdmin>
        ),
      },
      {
        path: "admin/health",
        element: (
          <RequireAdmin>
            <AdminHealthPage />
          </RequireAdmin>
        ),
      },
      {
        path: "admin/eval",
        element: (
          <RequireAdmin>
            <AdminEvalPage />
          </RequireAdmin>
        ),
      },
    ],
  },
]);
