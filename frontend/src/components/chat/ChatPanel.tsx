import { useEffect, useRef, useState, type FormEvent } from "react";

import { Markdown } from "@/components/Markdown";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/States";
import { cn } from "@/lib/cn";
import type { ChatMessage } from "@/services/types";

/**
 * The transcript is a fixed-height scroll area, so the input keeps its
 * position no matter how long the conversation gets. Letting the list grow
 * pushed the input down the page, which is why the box appeared to jump
 * between sends in the Streamlit version.
 */
const TRANSCRIPT_HEIGHT = "h-[26rem]";

function Bubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex gap-3 animate-fade-rise", isUser && "flex-row-reverse")}>
      <div
        aria-hidden="true"
        className={cn(
          "grid h-8 w-8 shrink-0 place-items-center rounded-full text-sm font-bold",
          isUser ? "bg-brand text-white" : "bg-surface-hero text-brand",
        )}
      >
        {isUser ? "You" : "AI"}
      </div>
      <div
        className={cn(
          "max-w-[80%] rounded-card px-4 py-3",
          isUser ? "bg-brand text-white" : "border border-line bg-surface text-ink",
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap text-[0.9375rem] leading-relaxed">{message.content}</p>
        ) : (
          <Markdown>{message.content}</Markdown>
        )}
      </div>
    </div>
  );
}

export function ChatPanel({
  messages,
  onSend,
  busy,
  placeholder = "Ask me to find matching jobs",
}: {
  messages: ChatMessage[];
  onSend: (text: string) => void;
  busy: boolean;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  // Scroll the newest turn into view. `block: "end"` rather than scrollIntoView
  // on the container avoids yanking the whole page down on first paint.
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, busy]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;
    setDraft("");
    onSend(text);
  }

  return (
    <div className="overflow-hidden rounded-card border border-line bg-surface-sunken">
      <div className={cn("space-y-4 overflow-y-auto p-5", TRANSCRIPT_HEIGHT)}>
        {messages.length === 0 && (
          <Bubble
            message={{
              role: "assistant",
              content:
                "Hi. Upload your CV, then ask me to find matches. You can also correct anything the parser got wrong just by telling me.",
            }}
          />
        )}
        {messages.map((message, index) => (
          <Bubble key={index} message={message} />
        ))}
        {busy && (
          <div className="flex items-center gap-3 text-sm text-ink-muted">
            <Spinner className="h-4 w-4" />
            Working on it. Matching runs four model calls, so this can take a minute.
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form onSubmit={submit} className="flex gap-2 border-t border-line bg-surface p-3">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={placeholder}
          aria-label="Message"
          className="flex-1 rounded-control border border-line bg-surface px-3.5 py-2.5 text-[0.9375rem] text-ink outline-none transition-colors duration-state ease-enter placeholder:text-ink-muted/60 focus:border-brand"
        />
        <Button type="submit" loading={busy} disabled={!draft.trim()}>
          Send
        </Button>
      </form>
    </div>
  );
}
