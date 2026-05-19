import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider, App as AntApp, theme as antTheme } from "antd";
import zhCN from "antd/locale/zh_CN";
import "antd/dist/reset.css";
import "./styles/globals.css";
import React, { useEffect, useMemo } from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router-dom";

import { router } from "./routes";
import { applyThemeAttribute, useThemeStore } from "./stores/themeStore";

const qc = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, retry: 1 },
  },
});

// ─── Night palette (Quiet Intelligence) ───
const NIGHT = {
  bgBase: "#0a0a0c",
  bgContainer: "#101013",
  bgElevated: "#15151a",
  bgLayout: "#0a0a0c",
  bgSpotlight: "#15151a",
  border: "#26262e",
  borderSecondary: "#1c1c22",
  text: "#ededee",
  textSecondary: "#a4a4ac",
  textTertiary: "#74747c",
  textQuaternary: "#50505a",
  inputBg: "#15151a",
  inputBorderHover: "#3a3a45",
  segmentedTrack: "#15151a",
  segmentedSelectedBg: "#1c1c22",
  segmentedSelectedColor: "#ededee",
  segmentedColor: "#a4a4ac",
  tagBg: "#1c1c22",
  tagColor: "#a4a4ac",
  tableHeaderBg: "#08080a",
  tableHeaderColor: "#74747c",
  tableRowHover: "#1c1c22",
  drawerBg: "#08080a",
  defaultBtnBg: "#15151a",
  defaultBtnBorder: "#26262e",
  defaultBtnColor: "#ededee",
  skeletonFrom: "#15151a",
  skeletonTo: "#1c1c22",
};

// ─── Day palette (Atelier) ───
const DAY = {
  bgBase: "#f3ede0",
  bgContainer: "#faf6ea",
  bgElevated: "#ffffff",
  bgLayout: "#f3ede0",
  bgSpotlight: "#ffffff",
  border: "#cdc2a4",
  borderSecondary: "#e1d8bf",
  text: "#16160f",
  textSecondary: "#46453a",
  textTertiary: "#75725f",
  textQuaternary: "#a39e87",
  inputBg: "#fbf7ec",
  inputBorderHover: "#ada088",
  segmentedTrack: "#ebe3cd",
  segmentedSelectedBg: "#ffffff",
  segmentedSelectedColor: "#16160f",
  segmentedColor: "#46453a",
  tagBg: "#ebe3cd",
  tagColor: "#46453a",
  tableHeaderBg: "#ece5d3",
  tableHeaderColor: "#75725f",
  tableRowHover: "#ebe3cd",
  drawerBg: "#faf6ea",
  defaultBtnBg: "#fbf7ec",
  defaultBtnBorder: "#cdc2a4",
  defaultBtnColor: "#16160f",
  skeletonFrom: "#ebe3cd",
  skeletonTo: "#e1d8bf",
};

function buildAntdTheme(mode: "night" | "day") {
  const p = mode === "night" ? NIGHT : DAY;
  // Accent: chartreuse on night, deep olive on day (deeper for legibility on paper)
  const primary = mode === "night" ? "#d4ff4a" : "#5d7220";
  const primaryHover = mode === "night" ? "#e2ff66" : "#6e8628";
  const inverse = mode === "night" ? "#0a0a0c" : "#faf6ea";

  return {
    algorithm: mode === "night" ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm,
    token: {
      colorPrimary: primary,
      colorInfo: mode === "night" ? "#6bb6ff" : "#2a6dba",
      colorSuccess: mode === "night" ? "#5ed993" : "#2f7a4e",
      colorWarning: mode === "night" ? "#ffb84a" : "#c47900",
      colorError: mode === "night" ? "#ff7a6b" : "#b7332c",

      colorBgBase: p.bgBase,
      colorBgContainer: p.bgContainer,
      colorBgElevated: p.bgElevated,
      colorBgLayout: p.bgLayout,
      colorBgSpotlight: p.bgSpotlight,

      colorBorder: p.border,
      colorBorderSecondary: p.borderSecondary,

      colorText: p.text,
      colorTextSecondary: p.textSecondary,
      colorTextTertiary: p.textTertiary,
      colorTextQuaternary: p.textQuaternary,
      colorTextPlaceholder: p.textQuaternary,

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
        defaultBg: p.defaultBtnBg,
        defaultBorderColor: p.defaultBtnBorder,
        defaultColor: p.defaultBtnColor,
        primaryShadow: "none",
        paddingInline: 14,
      },
      Tabs: {
        itemColor: p.textTertiary,
        itemHoverColor: p.textSecondary,
        itemSelectedColor: p.text,
        itemActiveColor: p.text,
        inkBarColor: primary,
        titleFontSize: 13,
      },
      Card: {
        colorBgContainer: p.bgContainer,
        colorBorderSecondary: p.borderSecondary,
        headerBg: "transparent",
        headerHeight: 44,
        headerHeightSM: 36,
      },
      Input: {
        colorBgContainer: p.inputBg,
        colorBorder: p.border,
        hoverBorderColor: p.inputBorderHover,
        activeBorderColor: primary,
        activeShadow:
          mode === "night"
            ? "0 0 0 3px rgba(212,255,74,0.08)"
            : "0 0 0 3px rgba(93,114,32,0.12)",
      },
      Select: {
        colorBgContainer: p.inputBg,
        colorBgElevated: p.bgElevated,
        optionSelectedBg:
          mode === "night" ? "rgba(212,255,74,0.14)" : "rgba(212,255,74,0.30)",
        optionSelectedColor: mode === "night" ? primary : "#3d4c14",
      },
      Drawer: { colorBgElevated: p.drawerBg },
      Modal: {
        contentBg: p.bgContainer,
        headerBg: p.bgContainer,
        titleColor: p.text,
      },
      Notification: { colorBgElevated: p.bgElevated },
      Message: { colorBgElevated: p.bgElevated },
      Form: { labelColor: p.textSecondary },
      Tag: { defaultBg: p.tagBg, defaultColor: p.tagColor },
      Segmented: {
        itemSelectedBg: p.segmentedSelectedBg,
        itemSelectedColor: p.segmentedSelectedColor,
        itemColor: p.segmentedColor,
        trackBg: p.segmentedTrack,
      },
      Switch: {
        handleBg: mode === "night" ? "#ededee" : "#faf6ea",
        colorPrimary: primary,
        colorPrimaryHover: primaryHover,
      },
      Empty: { colorTextDescription: p.textTertiary },
      Skeleton: {
        gradientFromColor: p.skeletonFrom,
        gradientToColor: p.skeletonTo,
      },
      Popover: { colorBgElevated: p.bgElevated },
      Pagination: {
        itemBg: p.bgElevated,
        itemActiveBg: primary,
        itemActiveColorDisabled: inverse,
      },
      Table: {
        headerBg: p.tableHeaderBg,
        headerColor: p.tableHeaderColor,
        colorBgContainer: "transparent",
        rowHoverBg: p.tableRowHover,
        borderColor: p.borderSecondary,
      },
    },
  };
}

function AppProviders() {
  const mode = useThemeStore((s) => s.mode);

  // Reflect mode onto <html> so CSS variables and grain swap in unison.
  useEffect(() => {
    applyThemeAttribute(mode);
  }, [mode]);

  const themeConfig = useMemo(() => buildAntdTheme(mode), [mode]);

  return (
    <ConfigProvider locale={zhCN} theme={themeConfig}>
      <AntApp>
        <QueryClientProvider client={qc}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>
  );
}

// Set the attribute before first paint so we don't flash the wrong theme.
applyThemeAttribute(useThemeStore.getState().mode);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppProviders />
  </React.StrictMode>
);
