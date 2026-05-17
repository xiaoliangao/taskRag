import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider, App as AntApp, theme as antTheme } from "antd";
import zhCN from "antd/locale/zh_CN";
import "antd/dist/reset.css";
import "./styles/globals.css";
import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router-dom";

import { router } from "./routes";

const qc = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, retry: 1 },
  },
});

// Bridge our design tokens into AntD so the dark surfaces match.
const themeConfig = {
  algorithm: antTheme.darkAlgorithm,
  token: {
    colorPrimary: "#d4ff4a",
    colorInfo: "#6bb6ff",
    colorSuccess: "#5ed993",
    colorWarning: "#ffb84a",
    colorError: "#ff7a6b",

    colorBgBase: "#0a0a0c",
    colorBgContainer: "#101013",
    colorBgElevated: "#15151a",
    colorBgLayout: "#0a0a0c",
    colorBgSpotlight: "#15151a",

    colorBorder: "#26262e",
    colorBorderSecondary: "#1c1c22",

    colorText: "#ededee",
    colorTextSecondary: "#a4a4ac",
    colorTextTertiary: "#74747c",
    colorTextQuaternary: "#50505a",
    colorTextPlaceholder: "#50505a",

    fontFamily:
      'Inter, -apple-system, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
    fontSize: 13,
    fontSizeHeading1: 32,
    fontSizeHeading2: 24,
    fontSizeHeading3: 18,

    borderRadius: 6,
    borderRadiusLG: 10,
    borderRadiusSM: 4,

    controlHeight: 32,
    controlHeightLG: 40,
    controlHeightSM: 26,

    wireframe: false,
    motion: true,
    motionDurationMid: "200ms",
    motionEaseOut: "cubic-bezier(0.16, 1, 0.3, 1)",
  },
  components: {
    Button: {
      defaultBg: "#15151a",
      defaultBorderColor: "#26262e",
      defaultColor: "#ededee",
      primaryShadow: "none",
      paddingInline: 14,
    },
    Tabs: {
      itemColor: "#74747c",
      itemHoverColor: "#a4a4ac",
      itemSelectedColor: "#ededee",
      itemActiveColor: "#ededee",
      inkBarColor: "#d4ff4a",
      titleFontSize: 13,
    },
    Card: {
      colorBgContainer: "#101013",
      colorBorderSecondary: "#1c1c22",
      headerBg: "transparent",
      headerHeight: 44,
      headerHeightSM: 36,
    },
    Input: {
      colorBgContainer: "#15151a",
      colorBorder: "#26262e",
      hoverBorderColor: "#3a3a45",
      activeBorderColor: "#d4ff4a",
      activeShadow: "0 0 0 3px rgba(212,255,74,0.08)",
    },
    Select: {
      colorBgContainer: "#15151a",
      colorBgElevated: "#15151a",
      optionSelectedBg: "rgba(212,255,74,0.14)",
      optionSelectedColor: "#d4ff4a",
    },
    Drawer: {
      colorBgElevated: "#08080a",
    },
    Modal: {
      contentBg: "#101013",
      headerBg: "#101013",
      titleColor: "#ededee",
    },
    Notification: {
      colorBgElevated: "#15151a",
    },
    Message: {
      colorBgElevated: "#15151a",
    },
    Form: {
      labelColor: "#a4a4ac",
    },
    Tag: {
      defaultBg: "#1c1c22",
      defaultColor: "#a4a4ac",
    },
    Segmented: {
      itemSelectedBg: "#1c1c22",
      itemSelectedColor: "#ededee",
      itemColor: "#a4a4ac",
      trackBg: "#15151a",
    },
    Switch: {
      handleBg: "#ededee",
      colorPrimary: "#d4ff4a",
      colorPrimaryHover: "#e2ff66",
    },
    Empty: {
      colorTextDescription: "#74747c",
    },
    Skeleton: {
      gradientFromColor: "#15151a",
      gradientToColor: "#1c1c22",
    },
    Popover: {
      colorBgElevated: "#15151a",
    },
    Pagination: {
      itemBg: "#15151a",
      itemActiveBg: "#d4ff4a",
      itemActiveColorDisabled: "#0a0a0c",
    },
    Table: {
      headerBg: "#08080a",
      headerColor: "#74747c",
      colorBgContainer: "transparent",
      rowHoverBg: "#1c1c22",
      borderColor: "#1c1c22",
    },
  },
};

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={themeConfig}>
      <AntApp>
        <QueryClientProvider client={qc}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>
);
