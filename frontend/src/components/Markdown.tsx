import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/cn";

/**
 * Renders the markdown the backend sends.
 *
 * Chat replies, the parsed-profile summary and the explanation summaries are
 * all markdown, exactly as `st.markdown` rendered them in Streamlit. Losing
 * that would flatten every bulleted list into a run-on line.
 *
 * Links open in a new tab with `noreferrer`: they point at third-party job
 * boards, and a posting should not be able to reach back into the app.
 */
export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("space-y-2 text-body", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="leading-relaxed">{children}</p>,
          ul: ({ children }) => <ul className="ml-4 list-disc space-y-1">{children}</ul>,
          ol: ({ children }) => <ol className="ml-4 list-decimal space-y-1">{children}</ol>,
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
          code: ({ children }) => (
            <code className="rounded bg-surface-sunken px-1.5 py-0.5 font-mono text-[0.85em]">
              {children}
            </code>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer noopener"
              className="font-medium text-brand underline underline-offset-2 transition-colors duration-state hover:text-brand-deep"
            >
              {children}
            </a>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
