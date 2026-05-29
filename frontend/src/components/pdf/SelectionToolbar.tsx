import {
  HighlightOutlined,
  MessageOutlined,
  RobotOutlined,
  StarOutlined,
  TranslationOutlined,
} from "@ant-design/icons";
import { Button, Space, Tooltip } from "antd";

import type { AnnotationKind } from "../../api/annotations";

export type ToolbarAction = AnnotationKind | "translate" | "ask";

/** Floating popover anchored to a text selection. Four actions: three create
 *  annotations of the corresponding `kind`, the fourth fires translation. */
export default function SelectionToolbar({
  visible,
  anchorRect,
  onPick,
  busy,
  translateEnabled,
  askEnabled,
}: {
  visible: boolean;
  anchorRect: { left: number; top: number; width: number } | null;
  onPick: (action: ToolbarAction) => void;
  busy?: boolean;
  translateEnabled?: boolean;
  askEnabled?: boolean;
}) {
  if (!visible || !anchorRect) return null;
  return (
    <div
      style={{
        position: "fixed",
        // Anchor centered above the selection's top, offset a bit so the arrow
        // doesn't cover the highlighted text.
        left: anchorRect.left + anchorRect.width / 2,
        top: anchorRect.top - 44,
        transform: "translateX(-50%)",
        padding: "4px 6px",
        background: "var(--bg-elevated)",
        border: "1px solid var(--border-default)",
        borderRadius: 999,
        boxShadow: "var(--shadow-2)",
        zIndex: 2000,
      }}
      // Don't let mousedown clear the selection before the click fires.
      onMouseDown={(e) => e.preventDefault()}
    >
      <Space size={2}>
        <Tooltip title="高亮">
          <Button
            type="text"
            size="small"
            disabled={busy}
            icon={<HighlightOutlined style={{ color: "var(--accent)" }} />}
            onClick={() => onPick("highlight")}
          />
        </Tooltip>
        <Tooltip title="批注">
          <Button
            type="text"
            size="small"
            disabled={busy}
            icon={<MessageOutlined />}
            onClick={() => onPick("comment")}
          />
        </Tooltip>
        <Tooltip title="存为笔记">
          <Button
            type="text"
            size="small"
            disabled={busy}
            icon={<StarOutlined />}
            onClick={() => onPick("note")}
          />
        </Tooltip>
        {askEnabled && (
          <Tooltip title="问这段(带到问答)">
            <Button
              type="text"
              size="small"
              disabled={busy}
              icon={<RobotOutlined style={{ color: "var(--accent)" }} />}
              onClick={() => onPick("ask")}
            />
          </Tooltip>
        )}
        {translateEnabled && (
          <Tooltip title="翻译(中↔英)">
            <Button
              type="text"
              size="small"
              disabled={busy}
              icon={<TranslationOutlined style={{ color: "var(--info)" }} />}
              onClick={() => onPick("translate")}
            />
          </Tooltip>
        )}
      </Space>
    </div>
  );
}
