import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ChatPanel } from "@/components/chat/ChatPanel";
import { Card, CardBody } from "@/components/ui/Card";
import { looksLikeMatchRequest } from "@/lib/profile";
import { chat, runMatchPipeline } from "@/services/api";
import { ChatUnavailable } from "@/services/http";
import { useSession } from "@/state/SessionContext";
import type { Profile } from "@/services/types";

export function ChatPage() {
  const navigate = useNavigate();
  const { profile, chat: history, appendChat, setProfile, setMatches } = useSession();
  const [busy, setBusy] = useState(false);

  /** Run the pipeline and describe the outcome, the way the Streamlit version
   *  did: the failure text has to say what to check, because "no matches" and
   *  "the backend is misconfigured" look identical otherwise. */
  async function runPipelineAndReport(current: Profile): Promise<string> {
    try {
      const matches = await runMatchPipeline(current);
      setMatches(matches);
      if (matches.length === 0) {
        return (
          "No matches came back. The job collection is probably empty. Run an " +
          "ingestion from the Ingestion tab, then ask me again."
        );
      }
      // Navigate only on success, so a failure leaves the user in the
      // conversation where the explanation is.
      navigate("/app/matches");
      return `Found and ranked **${matches.length}** match${matches.length === 1 ? "" : "es"}. They are on the Matches tab.`;
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught);
      return `I could not run the matching pipeline.\n\n${message}`;
    }
  }

  /** FALLBACK, used only when the conversational agent is not deployed.
   *  Deliberately dumb so it cannot be mistaken for intent classification. */
  async function routeByKeyword(text: string): Promise<string> {
    if (!looksLikeMatchRequest(text)) {
      return (
        "I can only do one thing on this backend: **find and rank job matches**. " +
        "Try asking me to *find matching jobs*.\n\n" +
        "The conversational agent is not deployed here, so I am matching on keywords only."
      );
    }
    if (!profile) {
      return "I need your profile first. Upload a CV on the Upload tab, then ask me again.";
    }
    return runPipelineAndReport(profile);
  }

  async function send(text: string) {
    appendChat({ role: "user", content: text });
    setBusy(true);

    try {
      let reply: string;
      try {
        const result = await chat(text, profile ?? {}, [...history, { role: "user", content: text }]);

        // The agent returns the complete profile, so this is a replace and not
        // a merge. Only a non-empty one is accepted, so a degraded response
        // cannot wipe a profile the user has already corrected by hand.
        const updated = result.updated_profile;
        if (updated && typeof updated === "object" && Object.keys(updated).length > 0) {
          setProfile(updated as Profile);
        }

        reply = result.reply || "(no reply)";
        const shouldRun = Boolean(result.run_pipeline) || result.intent === "confirm_run_pipeline";

        if (shouldRun) {
          const current = (updated as Profile | undefined) ?? profile;
          reply = current
            ? `${reply}\n\n${await runPipelineAndReport(current)}`
            : `${reply}\n\nI need your profile first though. Upload a CV on the Upload tab.`;
        }
      } catch (caught) {
        if (caught instanceof ChatUnavailable) {
          reply = await routeByKeyword(text);
        } else {
          const message = caught instanceof Error ? caught.message : String(caught);
          reply = `I could not reach the assistant.\n\n${message}`;
        }
      }
      appendChat({ role: "assistant", content: reply });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-ink">Chat</h1>
        <p className="mt-1 text-ink-muted">
          Ask for matches, or correct your profile in plain language. The whole
          chain is real: retrieval, re-ranking and the written explanations.
        </p>
      </header>

      {!profile && (
        <Card accent="amber">
          <CardBody className="text-sm text-ink-muted">
            No profile loaded yet. The assistant can still talk, but it needs a
            parsed CV before it can match anything.
          </CardBody>
        </Card>
      )}

      <ChatPanel messages={history} onSend={send} busy={busy} />
    </div>
  );
}
