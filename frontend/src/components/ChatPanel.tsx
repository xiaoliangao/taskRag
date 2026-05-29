import {
  ArrowUpOutlined,
  HistoryOutlined,
  PlusOutlined,
  PushpinOutlined,
  StopOutlined,
} from "@ant-design/icons";
import { App, Button, Segmented, Tooltip } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useEffect, useMemo, useRef, useState } from "react";
import { apiErrorMessage } from "../api/client";
import MarkdownView from "./MarkdownView";
import { pinChatMessage } from "../api/intel";
import {
  createSession,
  listChatMemory,
  listMessages,
  listSessions,
  streamUrl,
  updateSession,
} from "../api/qa";
import type { ChatMessage, ChatMode, Citation } from "../types/api";
import { CHAT_MODES, CHAT_MODE_DESC } from "../utils/chatModes";
import { consumeStream } from "../utils/sse";
import ChatMemoryDrawer from "./ChatMemoryDrawer";
import CitationPanel from "./CitationPanel";

const CHAT_MODE_OPTIONS = CHAT_MODES.map((m) => ({ label: m.label, value: m.value }));

interface Props {
  topicId: number;
  /** Open a source document (optionally at a page) — wired to the PDF drawer. */
  onOpenSource?: (documentId: number, page?: number) => void;
  /** "问这段" from the PDF reader: prefill the composer with this question.
   *  nonce changes on each ask so the same text can be re-sent. Not auto-sent —
   *  the user reviews/edits then presses send. */
  pendingQuestion?: { text: string; nonce: number } | null;
}

export default function ChatPanel({ topicId, onOpenSource, pendingQuestion }: Props) {
  const qc = useQueryClient();
  const { message: msg } = App.useApp();
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamBuffer, setStreamBuffer] = useState("");
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [streamCitations, setStreamCitations] = useState<Citation[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  // Set right before we abort on purpose so the catch/onError paths don't
  // surface a spurious "stream error" toast for a user-initiated stop.
  const stoppedRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const sessionsQ = useQuery({
    queryKey: ["chat-sessions", topicId],
    queryFn: () => listSessions(topicId),
  });

  // Latest memory summary across topic — used to render "已记忆 N 轮" badge.
  // refetch every 20s so the badge ticks after Celery summarization lands.
  const memoryQ = useQuery({
    queryKey: ["chat-memory", topicId],
    queryFn: () => listChatMemory(topicId, 1),
    refetchInterval: 20_000,
  });
  const latestMemory = memoryQ.data?.[0];
  const memoryCount = latestMemory?.message_count_at_gen ?? 0;

  useEffect(() => {
    if (!activeSessionId && sessionsQ.data && sessionsQ.data.length > 0) {
      setActiveSessionId(sessionsQ.data[0].id);
    }
  }, [activeSessionId, sessionsQ.data]);

  const activeSession = useMemo(
    () => (sessionsQ.data || []).find((s) => s.id === activeSessionId),
    [sessionsQ.data, activeSessionId],
  );
  const currentMode: ChatMode = (activeSession?.mode as ChatMode) || "default";

  const modeMut = useMutation({
    mutationFn: async (mode: ChatMode) => {
      if (!activeSessionId) return null;
      return updateSession(topicId, activeSessionId, { mode });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["chat-sessions", topicId] });
    },
    onError: (e) => msg.error(apiErrorMessage(e)),
  });

  const messagesQ = useQuery({
    queryKey: ["chat-messages", topicId, activeSessionId],
    queryFn: () => listMessages(topicId, activeSessionId!),
    enabled: !!activeSessionId,
  });

  const newSession = useMutation({
    mutationFn: () => createSession(topicId, "新会话"),
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ["chat-sessions", topicId] });
      setActiveSessionId(s.id);
    },
  });

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messagesQ.data, streamBuffer]);

  // "问这段": prefill the composer (don't auto-send) and focus it.
  useEffect(() => {
    if (!pendingQuestion?.text) return;
    setDraft(pendingQuestion.text);
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (!el) return;
      el.focus();
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 140) + "px";
      el.scrollIntoView({ block: "nearest" });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingQuestion?.nonce]);

  const send = async () => {
    const content = draft.trim();
    if (!content || streaming) return;
    let sid = activeSessionId;
    if (!sid) {
      try {
        const s = await createSession(topicId, content.slice(0, 30));
        qc.invalidateQueries({ queryKey: ["chat-sessions", topicId] });
        sid = s.id;
        setActiveSessionId(sid);
      } catch (e) {
        msg.error(apiErrorMessage(e));
        return;
      }
    }
    setDraft("");
    setStreaming(true);
    setStreamBuffer("");
    setStreamCitations([]);
    stoppedRef.current = false;
    const url = streamUrl(topicId, sid!, content);
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      qc.setQueryData<ChatMessage[]>(["chat-messages", topicId, sid], (prev) => [
        ...(prev || []),
        {
          id: -Date.now(),
          session_id: sid!,
          role: "user",
          content,
          citations: [],
          created_at: new Date().toISOString(),
        },
      ]);

      await consumeStream(
        url,
        {
          onCitations: (items) => setStreamCitations(items as Citation[]),
          onToken: (t) => setStreamBuffer((prev) => prev + t),
          onDone: () => {
            setStreaming(false);
            qc.invalidateQueries({ queryKey: ["chat-messages", topicId, sid] });
            setStreamBuffer("");
          },
          onError: (m) => {
            if (stoppedRef.current) return; // user-initiated stop, not an error
            msg.error(m);
            setStreaming(false);
          },
        },
        ctrl.signal
      );
    } catch (e) {
      setStreaming(false);
      if (stoppedRef.current) {
        stoppedRef.current = false;
        return; // aborted on purpose — swallow the AbortError
      }
      msg.error(apiErrorMessage(e));
    }
  };

  const stop = () => {
    stoppedRef.current = true;
    abortRef.current?.abort();
    setStreaming(false);
    setStreamBuffer("");
    // Refetch so the (persisted) user turn shows even though we cut the answer.
    if (activeSessionId) {
      qc.invalidateQueries({ queryKey: ["chat-messages", topicId, activeSessionId] });
    }
  };

  const allMessages = useMemo(() => messagesQ.data || [], [messagesQ.data]);
  const lastAssistantCitations = streaming
    ? streamCitations
    : allMessages.filter((m) => m.role === "assistant").slice(-1)[0]?.citations || [];

  return (
    <div className="chat-shell">
      {/* Sessions sidebar */}
      <div className="chat-sidebar">
        <div className="chat-sidebar-head">
          <span>会话</span>
          <Button
            size="small"
            type="text"
            icon={<PlusOutlined />}
            onClick={() => newSession.mutate()}
          />
        </div>
        <div className="chat-sidebar-list">
          {(sessionsQ.data || []).map((s) => (
            <div
              key={s.id}
              className={`chat-session-item ${s.id === activeSessionId ? "active" : ""}`}
              onClick={() => setActiveSessionId(s.id)}
            >
              {s.title}
            </div>
          ))}
          {sessionsQ.data && sessionsQ.data.length === 0 && (
            <div
              style={{
                color: "var(--text-muted)",
                fontSize: 12,
                padding: "20px 12px",
                textAlign: "center",
                fontStyle: "italic",
              }}
            >
              暂无会话
            </div>
          )}
        </div>
      </div>

      {/* Main chat thread */}
      <div className="chat-main">
        <div className="chat-thread" ref={scrollRef}>
          {allMessages.length === 0 && !streaming ? (
            <div className="chat-empty">
              <div>
                <div className="hint">问点什么？</div>
                <div style={{ fontSize: 12.5, color: "var(--text-muted)" }}>
                  系统会基于当前课题的语料 + 你的研究笔记回答。
                </div>
              </div>
            </div>
          ) : (
            <>
              {allMessages.map((m) => (
                <MessageBubble key={m.id} message={m} topicId={topicId} />
              ))}
              {streaming && (
                <MessageBubble
                  message={{
                    id: -1,
                    session_id: activeSessionId!,
                    role: "assistant",
                    content: streamBuffer || "",
                    citations: streamCitations,
                    created_at: new Date().toISOString(),
                  }}
                  topicId={topicId}
                  streaming
                />
              )}
            </>
          )}
        </div>

        <div
          style={{
            padding: "0 12px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 4,
            gap: 8,
          }}
        >
          <Tooltip title={CHAT_MODE_DESC[currentMode as ChatMode] ?? CHAT_MODE_DESC.default}>
            <Segmented
              size="small"
              options={CHAT_MODE_OPTIONS}
              value={currentMode}
              onChange={(v) => modeMut.mutate(v as ChatMode)}
              disabled={!activeSessionId || streaming}
              data-testid="chat-mode-selector"
            />
          </Tooltip>
          <Tooltip
            title={
              memoryCount > 0
                ? `已基于最近 ${memoryCount} 条消息生成长期记忆`
                : "暂未生成长期记忆 — 多聊几轮后会自动总结"
            }
          >
            <Button
              size="small"
              type="text"
              icon={<HistoryOutlined />}
              onClick={() => setMemoryOpen(true)}
              data-testid="chat-memory-btn"
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 11,
                letterSpacing: "0.05em",
                color: memoryCount > 0 ? "var(--accent)" : "var(--text-tertiary)",
              }}
            >
              {memoryCount > 0 ? `🧠 已记忆 ${memoryCount} 轮` : "🧠 记忆"}
            </Button>
          </Tooltip>
        </div>
        <div className="chat-input">
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="问点什么…  ⏎ 发送 · Shift+⏎ 换行"
            rows={1}
            onInput={(e) => {
              const el = e.currentTarget;
              el.style.height = "auto";
              el.style.height = Math.min(el.scrollHeight, 140) + "px";
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            disabled={streaming}
          />
          {streaming ? (
            <Tooltip title="停止生成">
              <Button
                danger
                type="primary"
                icon={<StopOutlined />}
                onClick={stop}
                style={{ width: 36, height: 36, padding: 0, borderRadius: 999 }}
              />
            </Tooltip>
          ) : (
            <Button
              type="primary"
              icon={<ArrowUpOutlined />}
              onClick={send}
              disabled={!draft.trim()}
              style={{ width: 36, height: 36, padding: 0, borderRadius: 999 }}
            />
          )}
        </div>
      </div>

      {/* Citations sidebar */}
      <div className="chat-aside">
        <div className="chat-aside-head">引用来源</div>
        <div className="chat-aside-body">
          <CitationPanel items={lastAssistantCitations} onOpenSource={onOpenSource} />
        </div>
      </div>

      <ChatMemoryDrawer
        topicId={topicId}
        open={memoryOpen}
        onClose={() => setMemoryOpen(false)}
      />
    </div>
  );
}

function MessageBubble({
  message,
  topicId,
  streaming = false,
}: {
  message: ChatMessage;
  topicId: number;
  streaming?: boolean;
}) {
  const isUser = message.role === "user";
  const { message: msg } = App.useApp();
  const canPin = !isUser && message.id > 0;
  const pin = useMutation({
    mutationFn: () => pinChatMessage(topicId, message.id),
    onSuccess: () => msg.success("已 Pin 到研究笔记"),
    onError: (e) => msg.error(apiErrorMessage(e)),
  });

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: isUser ? "flex-end" : "flex-start",
        gap: 4,
      }}
    >
      <div
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 10.5,
          color: "var(--text-muted)",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          padding: "0 4px",
        }}
      >
        {isUser ? "you" : "assistant"} · {dayjs(message.created_at).format("HH:mm:ss")}
      </div>
      <div className={`chat-bubble ${isUser ? "user" : "assistant"}`}>
        {isUser ? (
          message.content
        ) : (
          <>
            <MarkdownView>{message.content || "正在思考…"}</MarkdownView>
            {streaming && <span className="caret" />}
          </>
        )}
        {canPin && (
          <div className="bubble-actions">
            <Button
              size="small"
              type="text"
              icon={<PushpinOutlined />}
              loading={pin.isPending}
              onClick={() => pin.mutate()}
            >
              Pin
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
