import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ReactNode } from "react";

interface Props {
  children: string;
  className?: string;
}

/**
 * Shared markdown renderer:
 *  - GFM (tables, strikethrough, task lists, autolinks)
 *  - Wraps tables in a horizontally scrollable container
 *  - Forces external links into new tab
 *  - Styling lives in globals.css under .markdown-body
 */
export default function MarkdownView({ children, className }: Props): ReactNode {
  return (
    <div className={`markdown-body ${className ?? ""}`.trim()}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          table: ({ children: c, ...props }) => (
            <div className="markdown-table-wrap">
              <table {...props}>{c}</table>
            </div>
          ),
          a: ({ children: c, ...props }) => (
            <a {...props} target="_blank" rel="noreferrer noopener">
              {c}
            </a>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
