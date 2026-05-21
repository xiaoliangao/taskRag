import { HighlightOutlined, MessageOutlined, StarOutlined } from "@ant-design/icons";
import { Button, Space, Tooltip } from "antd";

import type { AnnotationKind } from "../../api/annotations";

/** Floating popover that appears anchored to a text selection. Three actions
 *  map to the three annotation kinds the backend supports. */
export default function SelectionToolbar({
  visible,
  anchorRect,
  onPick,
  busy,
}: {
  visible: boolean;
  anchorRect: { left: number; top: number; width: number } | null;
  onPick: (kind: AnnotationKind) => void;
  busy?: boolean;
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
      </Space>
    </div>
  );
}
