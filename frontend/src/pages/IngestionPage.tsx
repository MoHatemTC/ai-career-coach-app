import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { TextField } from "@/components/ui/Field";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/ui/States";
import { listIngestionRuns, listJobs, triggerIngestion, waitForIngestion } from "@/services/api";
import type { IngestionRun } from "@/services/types";

const SOURCES = ["arbeitnow", "wuzzuf", "mock_mena"] as const;

function statusTone(status: string | null | undefined) {
  if (status === "success") return "teal" as const;
  if (status === "failed") return "amber" as const;
  return "neutral" as const;
}

export function IngestionPage() {
  const queryClient = useQueryClient();
  const [limit, setLimit] = useState(10);
  const [selected, setSelected] = useState<string[]>([...SOURCES]);
  const [running, setRunning] = useState(false);
  const [current, setCurrent] = useState<IngestionRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobsPage, setJobsPage] = useState(0);

  const runs = useQuery({ queryKey: ["ingestion-runs"], queryFn: listIngestionRuns });
  const jobs = useQuery({
    queryKey: ["ingestion-jobs", jobsPage],
    queryFn: () => listJobs(20, jobsPage * 20),
  });

  function toggleSource(source: string) {
    setSelected((prev) =>
      prev.includes(source) ? prev.filter((item) => item !== source) : [...prev, source],
    );
  }

  async function run() {
    setRunning(true);
    setError(null);
    setCurrent(null);
    try {
      const runId = await triggerIngestion(limit, selected.length ? selected : null);
      const finished = await waitForIngestion(runId, setCurrent);
      setCurrent(finished);
      await queryClient.invalidateQueries({ queryKey: ["ingestion-runs"] });
      await queryClient.invalidateQueries({ queryKey: ["ingestion-jobs"] });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-2xl font-bold text-ink">Ingestion</h1>
        <p className="mt-1 text-ink-muted">
          Fetch postings from the sources, normalise them, dedupe on a
          deterministic job id, persist to SQLite and embed into Qdrant. Runs in
          the background; this polls until it settles.
        </p>
      </header>

      <Card>
        <CardBody className="space-y-4">
          <fieldset>
            <legend className="mb-2 text-sm font-semibold text-ink">Sources</legend>
            <div className="flex flex-wrap gap-2">
              {SOURCES.map((source) => {
                const active = selected.includes(source);
                return (
                  <button
                    key={source}
                    type="button"
                    onClick={() => toggleSource(source)}
                    aria-pressed={active}
                    className={
                      "rounded-chip border px-3.5 py-1.5 text-sm font-semibold transition-colors duration-state ease-enter " +
                      (active
                        ? "border-brand bg-brand/[0.08] text-brand"
                        : "border-line bg-surface text-ink-muted hover:border-brand/40")
                    }
                  >
                    {source}
                  </button>
                );
              })}
            </div>
          </fieldset>

          <div className="max-w-xs">
            <TextField
              label="Limit per source"
              type="number"
              min={1}
              max={50}
              value={limit}
              onChange={(event) => setLimit(Number(event.target.value))}
            />
          </div>

          <Button onClick={run} loading={running}>
            Run ingestion
          </Button>

          {current && (
            <div className="rounded-card border border-line bg-surface-sunken p-4 text-sm">
              <div className="flex items-center gap-2">
                <Badge tone={statusTone(current.status)}>{current.status}</Badge>
                <span className="text-ink-muted">Run {current.id}</span>
              </div>
              <p className="mt-2 text-ink-muted">
                fetched {current.jobs_fetched ?? 0}, inserted {current.jobs_inserted ?? 0}, updated{" "}
                {current.jobs_updated ?? 0}, skipped {current.jobs_skipped ?? 0}
              </p>
              {current.error_message && (
                <p className="mt-1 text-[#8A6206]">{current.error_message}</p>
              )}
            </div>
          )}

          {error && <ErrorState message={error} onRetry={run} />}
        </CardBody>
      </Card>

      <section className="space-y-3">
        <h2 className="text-xl font-bold text-ink">Recent runs</h2>
        {runs.isLoading && <LoadingBlock label="Loading runs" />}
        {runs.isError && <ErrorState message={String(runs.error)} onRetry={() => runs.refetch()} />}
        {runs.data && runs.data.length === 0 && (
          <EmptyState title="No runs yet">Trigger one above and it appears here.</EmptyState>
        )}
        {runs.data && runs.data.length > 0 && (
          <Card>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-line text-xs uppercase tracking-wide text-ink-muted">
                  <tr>
                    <th className="px-4 py-3">Run</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Source</th>
                    <th className="px-4 py-3 text-right">Fetched</th>
                    <th className="px-4 py-3 text-right">New</th>
                    <th className="px-4 py-3 text-right">Updated</th>
                    <th className="px-4 py-3">Started</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.data.map((item) => (
                    <tr key={item.id} className="border-b border-line/60 last:border-0">
                      <td className="tabular px-4 py-3">{item.id}</td>
                      <td className="px-4 py-3">
                        <Badge tone={statusTone(item.status)}>{item.status}</Badge>
                      </td>
                      <td className="px-4 py-3 text-ink-muted">{item.source}</td>
                      <td className="tabular px-4 py-3 text-right">{item.jobs_fetched ?? 0}</td>
                      <td className="tabular px-4 py-3 text-right">{item.jobs_inserted ?? 0}</td>
                      <td className="tabular px-4 py-3 text-right">{item.jobs_updated ?? 0}</td>
                      <td className="tabular px-4 py-3 text-ink-muted">
                        {item.started_at ? String(item.started_at).replace("T", " ").slice(0, 19) : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold text-ink">Persisted jobs</h2>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setJobsPage((page) => Math.max(0, page - 1))}
              disabled={jobsPage === 0}
            >
              Previous
            </Button>
            <span className="tabular text-sm text-ink-muted">page {jobsPage + 1}</span>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setJobsPage((page) => page + 1)}
              disabled={!jobs.data || jobs.data.length < 20}
            >
              Next
            </Button>
          </div>
        </div>

        {jobs.isLoading && <LoadingBlock label="Loading jobs" />}
        {jobs.isError && <ErrorState message={String(jobs.error)} onRetry={() => jobs.refetch()} />}
        {jobs.data && jobs.data.length === 0 && (
          <EmptyState title="No postings stored">
            Run an ingestion to fill the database.
          </EmptyState>
        )}
        {jobs.data && jobs.data.length > 0 && (
          <Card>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-line text-xs uppercase tracking-wide text-ink-muted">
                  <tr>
                    <th className="px-4 py-3">Title</th>
                    <th className="px-4 py-3">Company</th>
                    <th className="px-4 py-3">Location</th>
                    <th className="px-4 py-3">Source</th>
                    <th className="px-4 py-3">Link</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.data.map((job) => (
                    <tr key={job.job_id} className="border-b border-line/60 last:border-0">
                      <td className="px-4 py-3 font-medium text-ink">{job.title}</td>
                      <td className="px-4 py-3 text-ink-muted">{job.company}</td>
                      <td className="px-4 py-3 text-ink-muted">{job.location}</td>
                      <td className="px-4 py-3 text-ink-muted">{job.source}</td>
                      <td className="px-4 py-3">
                        {job.url && (
                          <a
                            href={job.url}
                            target="_blank"
                            rel="noreferrer noopener"
                            className="font-semibold text-brand underline underline-offset-2 transition-colors duration-state hover:text-brand-deep"
                          >
                            Open
                          </a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </section>
    </div>
  );
}
