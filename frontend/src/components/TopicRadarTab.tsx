import { Segmented } from "antd";
import { useState } from "react";

import ConflictExplorerView from "./ConflictExplorerView";
import HypothesisPanel from "./HypothesisPanel";
import TrendRadarView from "./TrendRadarView";

interface Props {
  topicId: number;
  onJumpDocument?: (docId: number) => void;
}

type Sub = "trend" | "conflict" | "hypothesis";

export default function TopicRadarTab({ topicId, onJumpDocument }: Props) {
  const [sub, setSub] = useState<Sub>("trend");

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Segmented
          value={sub}
          onChange={(v) => setSub(v as Sub)}
          options={[
            { label: "趋势雷达", value: "trend" },
            { label: "争议探索", value: "conflict" },
            { label: "假设验证", value: "hypothesis" },
          ]}
        />
      </div>
      {sub === "trend" && (
        <TrendRadarView topicId={topicId} onJumpDocument={onJumpDocument} />
      )}
      {sub === "conflict" && (
        <ConflictExplorerView topicId={topicId} onJumpDocument={onJumpDocument} />
      )}
      {sub === "hypothesis" && (
        <HypothesisPanel topicId={topicId} onJumpDocument={onJumpDocument} />
      )}
    </div>
  );
}
