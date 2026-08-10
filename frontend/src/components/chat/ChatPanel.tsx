import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

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
          "grid h-8 w-8 shrink-0 place-items-center rounded-full text-body-sm font-bold",
          isUser ? "bg-brand text-white" : "bg-surface-hero text-brand",
        )}
      >
        {isUser ? "You" : "AI"}
      </div>
      <div
        className={cn(
          // Wider share of a narrow screen: at 80% of a phone the bubble wastes
          // more to the gutter than it gains in shape.
          "max-w-[88%] rounded-card px-4 py-3 sm:max-w-[80%]",
          // Incoming bubbles carry the tint the panel gave up when it went to
          // paper — white on white would have left them holding a hairline and
          // nothing else.
          isUser ? "bg-brand text-white" : "border border-line bg-surface-sunken text-ink",
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap text-body">{message.content}</p>
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
  transcriptHeight = TRANSCRIPT_HEIGHT,
  pendingAction,
  busyLabel = "Working on it. Finding matches takes a minute.",
}: {
  messages: ChatMessage[];
  onSend: (text: string) => void;
  busy: boolean;
  placeholder?: string;
  /** What the spinner is waiting on. The default describes a matching run,
   *  which is the usual case; a caller doing something else — parsing an
   *  uploaded CV, say — must say so instead. A spinner that names the wrong
   *  work is worse than a bare one, because it is confidently wrong. */
  busyLabel?: string;
  /** Overridden where the transcript is the page's main piece rather than one
   *  section among several. */
  transcriptHeight?: string;
  /** An action the user can take as their next turn, rendered at the tail of
   *  the transcript. Exists so a caller can put something like "upload my CV"
   *  *in* the conversation instead of in a banner above it — the transcript is
   *  where the user is already looking, and an affordance that lives beside the
   *  messages reads as the obvious next thing to say rather than as chrome. */
  pendingAction?: ReactNode;
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
    // Paper, not sunken. This panel used to carry the page's own tone —
    // #F4F7FE on #F4F7FE with a hairline between them — so it was not a
    // distinct surface at all, which is what made the chat read flat. It now
    // sits as a card like every other card, per DESIGN.md's "sunken page,
    // paper card" model.
    <div className="overflow-hidden rounded-card border border-line bg-surface">
      <div className={cn("space-y-4 overflow-y-auto p-4 sm:p-5", transcriptHeight)}>
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
          <div
            role="status"
            aria-live="polite"
            className="flex items-center gap-3 text-body-sm text-ink-muted"
          >
            <Spinner className="h-4 w-4" />
            {busyLabel}
          </div>
        )}
        {pendingAction}
        <div ref={endRef} />
      </div>

      {/* The composer used to sit in a bar of its own — a top rule, a second
          background and its own padding — wrapped around an input that already
          had a border and a button that cast a raised shadow onto it. Three
          chrome treatments stacked in one 44px strip, for one job.

          The bar is gone. The composer sits directly on the panel, separated by
          space rather than a rule, which leaves the input as the only bordered
          object in the region and the button as the only filled one. Nothing
          functional went with it: the label, the disabled and loading states,
          the accessible name, the placeholder and the 44px target are intact. */}
      <form onSubmit={submit} className="flex gap-2 px-2.5 pb-2.5 pt-1 sm:px-3 sm:pb-3">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={placeholder}
          aria-label="Message"
          className="min-w-0 flex-1 rounded-control border border-line bg-surface px-3.5 py-2.5 text-body text-ink outline-none transition-colors duration-state ease-enter placeholder:text-ink-muted/60 focus:border-brand"
        />
        {/* No raised shadow: it was there to lift the button off a bar that no
            longer exists, and a shadow with nothing to sit on reads as grime. */}
        <Button
          type="submit"
          loading={busy}
          disabled={!draft.trim()}
          className="shrink-0 shadow-none"
        >
          Send
        </Button>
      </form>
    </div>
  );
}
