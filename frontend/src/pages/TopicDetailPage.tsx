import { ArrowLeftOutlined } from "@ant-design/icons";
import { Skeleton, Tabs } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { getTopic } from "../api/topics";
import ChatPanel from "../components/ChatPanel";
import CitationGraphView from "../components/CitationGraphView";
import DocumentDetailDrawer from "../components/DocumentDetailDrawer";
import DocumentList from "../components/DocumentList";
import InsightsView from "../components/InsightsView";
import NotesView from "../components/NotesView";
import PulseCard from "../components/PulseCard";
import ReadingPathView from "../components/ReadingPathView";
import TaskTable from "../components/TaskTable";
import TopicMapTab from "../components/TopicMapTab";
import TopicRadarTab from "../components/TopicRadarTab";
import TopicSettingsForm from "../components/TopicSettingsForm";
import TopicStudioTab from "../components/TopicStudioTab";

export default function TopicDetailPage() {
  const navigate = useNavigate();
  const { topicId, tab } = useParams<{ topicId: string; tab?: string }>();
  const tid = Number(topicId);

  const { data: topic, isLoading } = useQuery({
    queryKey: ["topic", tid],
    queryFn: () => getTopic(tid),
    enabled: !!tid,
  });

  const [searchParams, setSearchParams] = useSearchParams();
  const docParam = searchParams.get("doc");

  const [drawerDocId, setDrawerDocId] = useState<number | null>(null);
  const [drawerPage, setDrawerPage] = useState<number | undefined>(undefined);
  // "问这段": a question framed from a PDF selection, handed to ChatPanel.
  // nonce lets the same text be re-asked and re-triggers the prefill effect.
  const [pendingQuestion, setPendingQuestion] = useState<{ text: string; nonce: number } | null>(
    null,
  );

  // Deep-link: /topics/:id/documents?doc=123 opens the document drawer.
  // (Library favorites / recommendations link here.)
  useEffect(() => {
    if (docParam) {
      setDrawerDocId(Number(docParam));
      setDrawerPage(undefined);
    }
  }, [docParam]);

  if (isLoading || !topic) return <Skeleton active />;

  const activeTab = tab || "overview";
  const openDoc = (docId: number, page?: number) => {
    setDrawerDocId(docId);
    setDrawerPage(page);
  };
  const jump = (docId: number) => openDoc(docId);
  const closeDrawer = () => {
    setDrawerDocId(null);
    setDrawerPage(undefined);
    // Drop ?doc= so the drawer doesn't immediately re-open on re-render.
    if (docParam) {
      searchParams.delete("doc");
      setSearchParams(searchParams, { replace: true });
    }
  };
  const askFromSource = (question: string) => {
    setPendingQuestion((p) => ({ text: question, nonce: (p?.nonce ?? 0) + 1 }));
    setDrawerDocId(null);
    setDrawerPage(undefined);
    // navigate drops ?doc= naturally; ChatPanel mounts (if needed) with the question.
    navigate(`/topics/${tid}/chat`);
  };

  return (
    <div>
      <div className="topic-detail-back" onClick={() => navigate("/topics")}>
        <ArrowLeftOutlined />
        所有课题
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          marginBottom: 24,
          gap: 24,
        }}
      >
        <div>
          <div className="page-eyebrow">
            <span
              className={`dot ${topic.enabled ? "live" : ""}`}
              style={{
                background: topic.enabled
                  ? "var(--accent)"
                  : "var(--text-muted)",
                marginRight: 8,
                verticalAlign: "middle",
              }}
            />
            {topic.enabled ? "Active topic" : "Paused"} · #{String(topic.id).padStart(3, "0")}
          </div>
          <h1 className="page-title" style={{ marginTop: 4 }}>
            {topic.name}
          </h1>
          {topic.description && (
            <p className="page-subtitle" style={{ marginTop: 6 }}>
              {topic.description}
            </p>
          )}
        </div>

        <div
          style={{
            display: "flex",
            gap: 24,
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            color: "var(--text-tertiary)",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
          }}
        >
          <div>
            <div style={{ color: "var(--text-muted)", marginBottom: 2 }}>papers</div>
            <div
              style={{
                fontSize: 22,
                color: "var(--text-primary)",
                fontWeight: 500,
                letterSpacing: "-0.04em",
              }}
            >
              {topic.document_count}
            </div>
          </div>
          <div>
            <div style={{ color: "var(--text-muted)", marginBottom: 2 }}>keywords</div>
            <div
              style={{
                fontSize: 22,
                color: "var(--text-primary)",
                fontWeight: 500,
                letterSpacing: "-0.04em",
              }}
            >
              {topic.keywords.length}
            </div>
          </div>
        </div>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={(k) => navigate(`/topics/${tid}/${k}`)}
        items={[
          { key: "overview", label: "概览", children: <PulseCard topicId={tid} onJumpDocument={jump} /> },
          {
            key: "chat",
            label: "问答",
            children: (
              <ChatPanel topicId={tid} onOpenSource={openDoc} pendingQuestion={pendingQuestion} />
            ),
          },
          { key: "documents", label: "知识浏览", children: <DocumentList topicId={tid} /> },
          {
            key: "reading-path",
            label: "阅读路径",
            children: <ReadingPathView topicId={tid} onJumpDocument={jump} />,
          },
          {
            key: "radar",
            label: "研究雷达",
            children: <TopicRadarTab topicId={tid} onJumpDocument={jump} />,
          },
          {
            key: "studio",
            label: "写作工作台",
            children: <TopicStudioTab topicId={tid} onJumpDocument={jump} />,
          },
          {
            key: "map",
            label: "知识图谱",
            children: <TopicMapTab topicId={tid} onJumpDocument={jump} />,
          },
          {
            key: "citations",
            label: "引用网络",
            children: <CitationGraphView topicId={tid} onJumpDocument={jump} />,
          },
          { key: "insights", label: "研究洞察", children: <InsightsView topicId={tid} /> },
          { key: "notes", label: "研究笔记", children: <NotesView topicId={tid} /> },
          { key: "tasks", label: "任务记录", children: <TaskTable topicId={tid} /> },
          { key: "settings", label: "课题设置", children: <TopicSettingsForm topic={topic} /> },
        ]}
      />

      <DocumentDetailDrawer
        topicId={tid}
        documentId={drawerDocId}
        open={drawerDocId != null}
        initialPage={drawerPage}
        onClose={closeDrawer}
        onAsk={askFromSource}
      />
    </div>
  );
}
