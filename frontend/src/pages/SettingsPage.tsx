import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { SelectField, SliderField, TextField } from "@/components/ui/Field";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/ui/States";
import {
  buildRecommendations,
  getNotificationSettings,
  runMatchPipeline,
  saveNotificationSettings,
  triggerIngestion,
  waitForIngestion,
} from "@/services/api";
import { useSession } from "@/state/SessionContext";
import type { IngestionRun } from "@/services/types";

/** Contract 6's enumerable fields. Kept as fixed lists rather than free text so
 *  the stored values stay ones the notifications lane can branch on. */
const CHANNELS = ["email", "whatsapp"] as const;
const FREQUENCIES = ["daily", "weekly"] as const;

export function SettingsPage() {
  const { profile, setMatches, digest, setDigest } = useSession();

  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [channels, setChannels] = useState<string[]>(["email"]);
  const [frequency, setFrequency] = useState<string>("daily");
  const [threshold, setThreshold] = useState(0.75);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);

  const [triggering, setTriggering] = useState(false);
  const [ingestLimit, setIngestLimit] = useState(10);
  const [run, setRun] = useState<IngestionRun | null>(null);
  const [triggerError, setTriggerError] = useState<string | null>(null);

  // Prefill from whatever is already stored. The API nests contact under
  // Contract 6, so this reads through `contact` rather than the top level.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const existing = await getNotificationSettings();
        if (cancelled || !existing) return;
        setEmail(existing.contact?.email ?? "");
        setPhone(existing.contact?.phone_whatsapp ?? "");
        if (existing.notification_channels?.length) {
          setChannels(existing.notification_channels);
        }
        if (existing.frequency) setFrequency(existing.frequency);
        if (existing.relevance_threshold != null) setThreshold(existing.relevance_threshold);
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : String(caught));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function toggleChannel(channel: string) {
    setChannels((prev) =>
      prev.includes(channel) ? prev.filter((item) => item !== channel) : [...prev, channel],
    );
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const result = await saveNotificationSettings({
        email,
        phone,
        channels,
        frequency,
        relevanceThreshold: threshold,
      });
      setSaved(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSaving(false);
    }
  }

  /** Trigger Now: ingest first so the digest can surface postings that did not
   *  exist last time, rather than re-ranking a frozen pool. */
  async function triggerNow() {
    if (!profile) return;
    setTriggering(true);
    setTriggerError(null);
    setRun(null);
    try {
      const runId = await triggerIngestion(ingestLimit);
      const finished = await waitForIngestion(runId, setRun);
      setRun(finished);

      const matches = await runMatchPipeline(profile);
      setMatches(matches);
      setDigest(buildRecommendations(matches));
    } catch (caught) {
      setDigest(null);
      setTriggerError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setTriggering(false);
    }
  }

  return (
    <div className="space-y-10">
      <section className="space-y-4">
        <header>
          <h1 className="text-title font-extrabold text-ink">Notifications</h1>
          <p className="mt-2 max-w-prose text-ink-muted">
            Where to reach you, and how often. Saved on the server, so these
            stick around between visits.
          </p>
        </header>

        {loading ? (
          <LoadingBlock label="Loading saved settings" />
        ) : (
          <Card>
            <CardBody>
              <form onSubmit={save} className="space-y-5">
                <div className="grid gap-5 sm:grid-cols-2">
                  <TextField
                    label="Email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    hint="Where the daily digest goes."
                  />
                  <TextField
                    label="Phone (WhatsApp)"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="+20…"
                    hint="For WhatsApp, if you enable it below."
                  />
                </div>

                <fieldset>
                  <legend className="mb-1.5 text-sm font-semibold text-ink">Channels</legend>
                  <p className="mb-2 text-xs text-ink-muted">
                    Pick where a digest should reach you.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {CHANNELS.map((channel) => {
                      const active = channels.includes(channel);
                      return (
                        <button
                          key={channel}
                          type="button"
                          onClick={() => toggleChannel(channel)}
                          aria-pressed={active}
                          className={
                            "rounded-chip border px-3.5 py-1.5 text-sm font-semibold capitalize transition-colors duration-state ease-enter " +
                            (active
                              ? "border-brand bg-brand/[0.08] text-brand"
                              : "border-line bg-surface text-ink-muted hover:border-brand/40")
                          }
                        >
                          {channel}
                        </button>
                      );
                    })}
                  </div>
                </fieldset>

                <div className="grid gap-5 sm:grid-cols-2">
                  <SelectField
                    label="Frequency"
                    options={FREQUENCIES}
                    value={frequency}
                    onChange={(e) => setFrequency(e.target.value)}
                  />
                  <SliderField
                    label="Relevance threshold"
                    hint="Only notify about matches scoring at least this well."
                    min={0}
                    max={1}
                    step={0.05}
                    value={threshold}
                    onChange={(e) => setThreshold(Number(e.target.value))}
                  />
                </div>

                <Button type="submit" loading={saving}>
                  Save settings
                </Button>
              </form>

              {error && (
                <div className="mt-4">
                  <ErrorState message={error} />
                </div>
              )}

              {saved != null && (
                <div className="mt-5 rounded-card border border-teal/30 bg-teal/[0.06] p-4">
                  <div className="flex items-center gap-2">
                    <Badge tone="teal">Saved</Badge>
                    <span className="text-sm text-ink-muted">
                      Your preferences are stored and will survive a restart.
                    </span>
                  </div>
                  {/* The raw payload is genuinely useful when wiring the
                      notifications lane, and clutter for everyone else. Behind
                      a disclosure it is available without being on display. */}
                  <details className="group mt-3">
                    <summary className="cursor-pointer select-none text-sm font-semibold text-ink-muted transition-colors duration-state hover:text-brand">
                      View the stored payload
                    </summary>
                    <pre className="mt-2 overflow-x-auto rounded-control bg-surface p-3 font-mono text-xs leading-relaxed text-ink-muted">
                      {JSON.stringify(saved, null, 2)}
                    </pre>
                  </details>
                </div>
              )}
            </CardBody>
          </Card>
        )}
      </section>

      <section className="space-y-4">
        <header>
          <h2 className="text-subtitle font-bold text-ink">Job match digest</h2>
          <p className="mt-2 max-w-prose text-ink-muted">
            Pull in new postings and preview the digest you would be sent.
            Nothing is delivered from here yet.
          </p>
        </header>

        <Card>
          <CardBody className="space-y-4">
            <div className="max-w-xs">
              <TextField
                label="Postings per source"
                type="number"
                min={1}
                max={50}
                value={ingestLimit}
                onChange={(e) => setIngestLimit(Number(e.target.value))}
                hint="How many to pull from each job board."
              />
            </div>

            <Button onClick={triggerNow} loading={triggering} disabled={!profile}>
              Trigger now
            </Button>

            {!profile && (
              <p className="text-sm text-ink-muted">
                No profile yet. Upload a CV first: the digest is built from it.
              </p>
            )}

            {run && (
              <p className="text-sm text-ink-muted">
                Ingestion run {run.id}: {run.jobs_inserted ?? 0} new,{" "}
                {run.jobs_updated ?? 0} updated, status {run.status}.
                {run.error_message && (
                  <span className="text-[#8A6206]"> Some sources failed: {run.error_message}</span>
                )}
              </p>
            )}

            {triggerError && <ErrorState message={triggerError} />}

            {digest !== null && digest.length > 0 && (
              <div className="space-y-3">
                <Badge tone="teal">
                  {digest.length} recommendation{digest.length === 1 ? "" : "s"} ready
                </Badge>
                {digest.map((item, index) => (
                  <div
                    key={`${item.job_title}-${index}`}
                    className="animate-fade-rise rounded-card border border-line bg-surface p-4"
                  >
                    <p className="font-semibold text-ink">
                      {index + 1}. {item.job_title}
                    </p>
                    <p className="text-sm text-ink-muted">{item.company}</p>
                    {item.url && (
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="mt-2 inline-block text-sm font-semibold text-brand underline underline-offset-2 transition-colors duration-state hover:text-brand-deep"
                      >
                        Open job posting
                      </a>
                    )}
                  </div>
                ))}
              </div>
            )}

            {digest !== null && digest.length === 0 && (
              <EmptyState title="No recommendations to send">
                The job collection may be empty. Run an ingestion first.
              </EmptyState>
            )}
          </CardBody>
        </Card>
      </section>
    </div>
  );
}
