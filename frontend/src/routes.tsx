import { createBrowserRouter, Navigate } from "react-router-dom";

import AppLayout from "./components/AppLayout";
import RequireAuth from "./components/RequireAuth";
import CrossTopicChatPage from "./pages/CrossTopicChatPage";
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
      { path: "topics", element: <TopicListPage /> },
      { path: "topics/:topicId", element: <TopicDetailPage /> },
      { path: "topics/:topicId/:tab", element: <TopicDetailPage /> },
      { path: "qa/cross-topic", element: <CrossTopicChatPage /> },
      { path: "notifications", element: <NotificationsPage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },
]);
