import { useState, type ChangeEvent } from "react";
import { useNavigate } from "react-router-dom";

import { ChatPanel } from "@/components/chat/ChatPanel";
import { SidePanel } from "@/components/layout/SidePanel";
import { ProfileForm } from "@/components/profile/ProfileForm";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { summariseParsedProfile } from "@/lib/profile";
import { useConversation } from "@/lib/useConversation";
import { runMatchPipeline, uploadCv } from "@/services/api";
import { useSession } from "@/state/SessionContext";
import type { Profile } from "@/services/types";

const ACCEPTED = ".pdf,.docx";

/**
 * The conversation is the page; the CV and the parsed profile live in a drawer
 * behind the tab on the right.
 *
 * The parser's output is a draft, and the fastest way to correct a draft is to
 * say what is wrong. The form is still there for anyone who would rather edit
 * fields directly: it sits under the uploader in the same drawer, so parsing a
 * CV drops the parsed profile directly below the button that produced it.
 */
export function UploadPage() {
  const navigate = useNavigate();
  const { profile, setProfile, setMatches, appendChat } = useSession();
  const { history, busy: chatBusy, send } = useConversation();

  const [file, setFile] = useState<File | null>(null);
  const [parsing, setParsing] = useState(false);
  const [matching, setMatching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);

  function onPick(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
    setError(null);
  }

  /** The chat entry point parses immediately rather than asking for a second
   *  confirmation. In the drawer a two-step flow makes sense — you are staging
   *  a document beside a form. In the conversation, choosing the file IS the
   *  turn, and a "now press Parse" step would be a second click for a decision
   *  the user already made in the file dialog. */
  function onChatPick(event: ChangeEvent<HTMLInputElement>) {
    const chosen = event.target.files?.[0];
    // Reset so re-choosing the same file still fires a change event.
    event.target.value = "";
    if (!chosen) return;
    setFile(chosen);
    void parseFile(chosen, true);
  }

  /** Upload one file and fold the result into the conversation.
   *
   *  Takes the file as an argument rather than reading the `file` state,
   *  because the chat entry point parses the moment you choose a document —
   *  and `setFile` has not committed by the time that handler runs. The drawer
   *  keeps its two-step flow by passing the already-selected file in.
   *
   *  `fromChat` records the upload as a real user turn. The assistant's reply
   *  reads the parsed profile back either way, so the parser's mistakes surface
   *  where they can be corrected in plain language rather than only in the form.
   */
  async function parseFile(chosen: File, fromChat = false) {
    setParsing(true);
    setError(null);

    // The user's turn is posted BEFORE the request, not after it. Uploading and
    // parsing is the slow part of this page, and appending only on success left
    // a hole: the upload bubble disappeared the moment it was pressed and
    // nothing took its place until the parse finished, so the honest reading of
    // the screen was "that did nothing". Posting first means the transcript
    // confirms the file landed, and the spinner below it says what is happening
    // to it.
    if (fromChat) {
      appendChat({
        role: "user",
        content: `Uploaded ${chosen.name} (${Math.max(1, Math.round(chosen.size / 1024))} KB)`,
      });
    }

    try {
      const parsed = await uploadCv(chosen);
      setProfile(parsed);
      appendChat({ role: "assistant", content: summariseParsedProfile(parsed) });
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : String(caught);
      setError(message);
      // A user turn with no reply is a broken conversation, and `error` renders
      // inside the drawer — which is very likely closed when the upload came
      // from the chat. The failure has to answer where the question was asked.
      if (fromChat) {
        appendChat({
          role: "assistant",
          content: `I could not read that file.\n\n${message}`,
        });
      }
    } finally {
      setParsing(false);
    }
  }

  async function parse() {
    if (!file) return;
    await parseFile(file);
  }

  async function confirm(next: Profile) {
    setProfile(next);
    setMatching(true);
    setError(null);
    try {
      const matches = await runMatchPipeline(next);
      setMatches(matches);
      navigate("/app/matches");
    } catch (caught) {
      setMatches(null);
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setMatching(false);
    }
  }

  return (
    // The shell runs to 1560px, but a transcript is prose: at full width the
    // bubbles reach roughly 1250px and the eye loses the line. 52rem keeps a
    // bubble near 70 characters, which is the Measure Rule applied to a
    // conversation rather than to an article.
    <div className="mx-auto w-full max-w-[52rem] space-y-5 sm:space-y-6">
      <header>
        <h1 className="text-title font-extrabold text-ink">Your career coach</h1>
        {/* Two wrappers, both load-bearing: the outer one is the grid whose
            row track animates from 0fr to 1fr, the inner one is the clipping
            box that lets it. Collapsing the <p> directly is not possible —
            a grid item needs `overflow: hidden` and `min-height: 0` to be
            allowed to shrink below its content height. */}
        <div className="coach-intro">
          <div className="coach-intro-clip">
            <p className="mt-2 max-w-prose text-ink-muted">
              <span>
                Ask for matches, or say what the parser got wrong and it will
                update your profile.
              </span>
              <span>Your CV and the parsed details are in the panel on the right.</span>
            </p>
          </div>
        </div>
      </header>

      {/* The upload used to be an amber banner above the conversation, telling
          the user to go somewhere else — a drawer — to do the one thing this
          page needs from them. It now sits in the transcript, shaped like the
          turn they are about to take.

          Outlined rather than filled, deliberately. The filled brand bubbles in
          this transcript mean "this was said"; a pending action drawn the same
          way would claim a turn that has not happened. Pressing it produces the
          real one — `parseFile` appends "Uploaded <name>" as a user message.

          A real <label> wrapping a real file input, so it is keyboard reachable
          and announces as a file control. A styled <div> with an onClick would
          look identical and be unusable without a mouse. */}
      <ChatPanel
        messages={history}
        onSend={send}
        // Parsing is the page's other slow call, and it belongs on the same
        // indicator: the user is watching the transcript either way.
        busy={chatBusy || parsing}
        busyLabel={parsing ? "Reading your CV. This takes a moment." : undefined}
        // Tracks the viewport rather than a fixed height, so a short window or
        // a zoomed-in page gives the transcript less room instead of pushing
        // the input off-screen.
        transcriptHeight="h-[min(52vh,22rem)] sm:h-[min(58vh,30rem)] lg:h-[min(62vh,38rem)]"
        pendingAction={
          !profile && !parsing ? (
            <div className="flex animate-fade-rise justify-end">
              <label className="group max-w-[88%] cursor-pointer rounded-card outline-brand has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 sm:max-w-[80%]">
                <span className="block rounded-card border border-dashed border-brand/50 bg-surface px-4 py-3 text-body font-semibold text-brand transition-colors duration-state ease-enter group-hover:border-brand">
                  Upload my CV
                  <span className="mt-0.5 block text-label font-normal text-ink-muted">
                    PDF or DOCX, not a scan
                  </span>
                </span>
                <input type="file" accept={ACCEPTED} onChange={onChatPick} className="sr-only" />
              </label>
            </div>
          ) : null
        }
      />

      <SidePanel
        label="CV and profile"
        title="CV and profile"
        description="Everything the parser read, ready to correct."
        open={panelOpen}
        onOpenChange={setPanelOpen}
      >
        <div className="space-y-6">
          <div className="space-y-4">
            <label
              htmlFor="cv-file"
              className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-card border-2 border-dashed border-line px-6 py-10 text-center transition-colors duration-state ease-enter hover:border-brand hover:bg-surface-hero/40"
            >
              <span className="font-semibold text-ink">
                {file ? file.name : "Choose a PDF or DOCX"}
              </span>
              <span className="text-body-sm text-ink-muted">
                {file ? `${(file.size / 1024).toFixed(0)} KB` : "Click to browse"}
              </span>
              <input
                id="cv-file"
                type="file"
                accept={ACCEPTED}
                onChange={onPick}
                className="sr-only"
              />
            </label>

            <p className="text-label leading-relaxed text-ink-muted">
              It needs to be a real text document rather than a scan, since a
              photo of a CV has no text to read.
            </p>

            <Button onClick={parse} disabled={!file} loading={parsing} className="w-full">
              {parsing ? "Reading your CV" : "Parse CV"}
            </Button>

            {error && <ErrorState message={error} />}
          </div>

          <div className="border-t border-line pt-6">
            <h3 className="text-body-sm font-semibold text-ink">Your profile</h3>
            <p className="mb-4 mt-1 text-body-sm text-ink-muted">
              Fix anything that came out wrong before matching.
            </p>

            {profile ? (
              <ProfileForm profile={profile} onSubmit={confirm} busy={matching} />
            ) : (
              <EmptyState title="Nothing here yet">
                Parse a CV and your details appear here, ready to edit.
              </EmptyState>
            )}
          </div>
        </div>
      </SidePanel>
    </div>
  );
}
