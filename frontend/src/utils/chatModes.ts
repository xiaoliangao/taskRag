import type { ChatMode } from "../types/api";

/** Shared between the per-topic ChatPanel and the CrossTopicChatPage so we have
 *  one source of truth for chat-mode labels + 1-line descriptions (used in the
 *  selector tooltip).
 *
 *  Must stay in sync with `backend/app/rag/chat_modes.py`. */
export interface ChatModeMeta {
  value: ChatMode;
  label: string;
  desc: string;
}

export const CHAT_MODES: ChatModeMeta[] = [
  { value: "default", label: "默认", desc: "结构化回答:结论、关键依据、相关文档。" },
  { value: "mentor", label: "导师", desc: "挑出问题的假设/局限,反问澄清,给出下一步建议。" },
  { value: "beginner", label: "入门", desc: "用类比解释,术语带括号注解,推荐 1 篇深入阅读。" },
  { value: "debate", label: "辩论", desc: "支持/反对两栏并各自带引用,最后中性总结。" },
  { value: "reviewer", label: "审稿人", desc: "逐项评估:方法贡献、实验是否支撑、局限、改进。" },
  { value: "what_if", label: "假设", desc: "反事实推理:基线 → 如果 X → 推动 Y,标出最薄弱假设。" },
];

export const CHAT_MODE_DESC: Record<ChatMode, string> = CHAT_MODES.reduce(
  (acc, m) => {
    acc[m.value] = m.desc;
    return acc;
  },
  {} as Record<ChatMode, string>,
);
