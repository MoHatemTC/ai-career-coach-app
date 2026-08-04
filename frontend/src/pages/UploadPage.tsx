import { useState, type ChangeEvent } from "react";
import { useNavigate } from "react-router-dom";

import { ProfileForm } from "@/components/profile/ProfileForm";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { summariseParsedProfile } from "@/lib/profile";
import { runMatchPipeline, uploadCv } from "@/services/api";
import { useSession } from "@/state/SessionContext";
import type { Profile } from "@/services/types";

const ACCEPTED = ".pdf,.docx";

export function UploadPage() {
  const navigate = useNavigate();
  const { profile, setProfile, setMatches, appendChat } = useSession();

  const [file, setFile] = useState<File | null>(null);
  const [parsing, setParsing] = useState(false);
  const [matching, setMatching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function onPick(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
    setError(null);
  }

  async function parse() {
    if (!file) return;
    setParsing(true);
    setError(null);
    try {
      const parsed = await uploadCv(file);
      setProfile(parsed);
      // Open the conversation by reading the profile back, so the parser's
      // mistakes surface where they can be corrected in plain language rather
      // than only in the form.
      appendChat({ role: "assistant", content: summariseParsedProfile(parsed) });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setParsing(false);
    }
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
    <div className="space-y-8">
      <header>
        <h1 className="text-title font-extrabold text-ink">Upload your CV</h1>
        <p className="mt-2 max-w-prose text-ink-muted">
          PDF or DOCX. It needs to be a real text document rather than a
          scan, since a photo of a CV has no text to read.
        </p>
      </header>

      {/* Two columns from lg: the uploader is a small, fixed task and the form
          is the long one. Stacking them wasted the right half of the screen and
          pushed the form below the fold on every laptop. */}
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,22rem),minmax(0,1fr)]">
        <Card className="lg:sticky lg:top-24">
          <CardBody className="space-y-4">
            <label
              htmlFor="cv-file"
              className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-card border-2 border-dashed border-line px-6 py-12 text-center transition-colors duration-state ease-enter hover:border-brand hover:bg-surface-hero/40"
            >
              <span className="font-semibold text-ink">
                {file ? file.name : "Choose a PDF or DOCX"}
              </span>
              <span className="text-sm text-ink-muted">
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

            <Button onClick={parse} disabled={!file} loading={parsing} className="w-full">
              {parsing ? "Reading your CV" : "Parse CV"}
            </Button>

            {error && <ErrorState message={error} />}
          </CardBody>
        </Card>

        <section className="space-y-4">
          <div>
            <h2 className="text-subtitle font-bold text-ink">Your profile</h2>
            <p className="mt-2 max-w-prose text-ink-muted">
              Fix anything that came out wrong before matching. You can also just
              tell the assistant what to change.
            </p>
          </div>

          {profile ? (
            <Card>
              <CardBody>
                <ProfileForm profile={profile} onSubmit={confirm} busy={matching} />
              </CardBody>
            </Card>
          ) : (
            <EmptyState title="Nothing here yet">
              Upload a CV and your details appear here, ready to edit.
            </EmptyState>
          )}
        </section>
      </div>
    </div>
  );
}
