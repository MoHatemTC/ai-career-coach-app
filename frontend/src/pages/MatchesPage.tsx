import { useState } from "react";
import { Link } from "react-router-dom";

import { MatchCard } from "@/components/match/MatchCard";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/ui/States";
import { runMatchPipeline } from "@/services/api";
import { useSession } from "@/state/SessionContext";

export function MatchesPage() {
  const { profile, matches, setMatches } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function rerun() {
    if (!profile) return;
    setBusy(true);
    setError(null);
    try {
      setMatches(await runMatchPipeline(profile));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-ink">Your matches</h1>
          <p className="mt-1 text-ink-muted">
            Vector retrieval, then LLM re-ranking, then a written explanation per
            job. Fit scores are the re-ranker's own numbers, passed through.
          </p>
        </div>
        {profile && (
          <Button variant="secondary" onClick={rerun} loading={busy}>
            Run again
          </Button>
        )}
      </header>

      {error && <ErrorState message={error} onRetry={rerun} />}
      {busy && <LoadingBlock label="Retrieving, re-ranking and explaining. Four model calls, so give it a minute." />}

      {!busy && !profile && (
        <EmptyState
          title="No profile yet"
          action={
            <Link
              to="/app/upload"
              className="inline-flex h-10 items-center rounded-control bg-brand px-4 text-sm font-semibold text-white transition-colors duration-state hover:bg-brand-deep"
            >
              Upload a CV
            </Link>
          }
        >
          Matching needs a profile to rank against. Upload a CV and the results
          land here.
        </EmptyState>
      )}

      {!busy && profile && matches === null && (
        <EmptyState
          title="Nothing matched yet"
          action={
            <Button onClick={rerun} loading={busy}>
              Find matches
            </Button>
          }
        >
          Your profile is loaded. Run the pipeline to see ranked jobs.
        </EmptyState>
      )}

      {!busy && matches !== null && matches.length === 0 && (
        <EmptyState
          title="No matches came back"
          action={
            <Link
              to="/app/ingestion"
              className="inline-flex h-10 items-center rounded-control border border-line px-4 text-sm font-semibold text-ink transition-colors duration-state hover:border-brand hover:text-brand"
            >
              Run an ingestion
            </Link>
          }
        >
          The job collection is probably empty, which is not the same as nothing
          suiting you. Ingest some postings and try again.
        </EmptyState>
      )}

      {!busy && matches !== null && matches.length > 0 && (
        <div className="space-y-5">
          {matches.map((match, index) => (
            <MatchCard key={match.job_id ?? index} result={match} rank={index + 1} />
          ))}
        </div>
      )}
    </div>
  );
}
