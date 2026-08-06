import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { SelectField, SliderField, TextField } from "@/components/ui/Field";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/ui/States";
import {
  getNotificationLogs,
  getNotificationSettings,
  getProviderStatus,
  getSchedulerStatus,
  previewDigest,
  saveNotificationSettings,
  saveProfileSnapshot,
  sendTestDigest,
  triggerIngestion,
  waitForIngestion,
} from "@/services/api";
import { useSession } from "@/state/SessionContext";
import type {
  IngestionRun,
  NotificationLog,
  ProviderStatus,
  SchedulerStatus,
  TopJobMatch,
} from "@/services/types";

/** Contract 6's enumerable fields. Kept as fixed lists rather than free text so
 *  the stored values stay ones the notifications lane can branch on. */
const CHANNELS = ["email", "whatsapp"] as const;
const FREQUENCIES = ["daily", "weekly"] as const;

/** A short list rather than the full IANA database. The backend accepts any
 *  zone `ZoneInfo` can load and 422s the rest, so this is a convenience, not
 *  the validation. */
const TIMEZONES = [
  "Africa/Cairo",
  "Africa/Lagos",
  "Asia/Dubai",
  "Asia/Riyadh",
  "Europe/London",
  "Europe/Berlin",
  "America/New_York",
  "UTC",
] as const;

const SEND_HOURS = Array.from({ length: 24 }, (_, hour) =>
  `${String(hour).padStart(2, "0")}:00`,
);

/** Which long-running action owns the buttons right now. `dry` and `send` are
 *  separate so only the button you pressed shows a spinner. */
type Busy = "preview" | "send" | "dry" | "ingest" | null;

/** What the user is told when a send finishes. The outcomes come from the
 *  dispatcher; spelling them out here keeps the wording in one place. */
const OUTCOME_COPY: Record<string, string> = {
  notified: "Sent.",
  no_contact:
    "Nothing was sent: no channel is selected, or the selected one has no address.",
  already_sent: "Already sent today.",
  no_profile:
    "Nothing was sent: no profile is stored to match against. Upload a CV, then save these settings again — the scheduled digest has no browser session to read one from, so it has to be persisted here.",
  no_matches:
    "Nothing was sent: no job cleared your relevance threshold. Try lowering it, or fetch more postings.",
  no_new_matches:
    "Nothing was sent: every job that cleared your threshold was already sent in the last 7 days, so the digest had nothing new to say. Fetch more postings — lowering the threshold will not help here.",
  all_failed: "Every channel failed. Check the delivery log below.",
};

export function SettingsPage() {
  const { profile } = useSession();

  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [fullName, setFullName] = useState("");
  const [channels, setChannels] = useState<string[]>(["email"]);
  const [frequency, setFrequency] = useState<string>("daily");
  const [threshold, setThreshold] = useState(0.75);
  const [sendHour, setSendHour] = useState("08:00");
  const [timezone, setTimezone] = useState<string>("Africa/Cairo");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [hasSettings, setHasSettings] = useState(false);

  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [logs, setLogs] = useState<NotificationLog[]>([]);

  const [busy, setBusy] = useState<Busy>(null);
  const [ingestLimit, setIngestLimit] = useState(10);
  const [run, setRun] = useState<IngestionRun | null>(null);
  const [preview, setPreview] = useState<TopJobMatch[] | null>(null);
  const [sendNote, setSendNote] = useState<string | null>(null);
  const [digestError, setDigestError] = useState<string | null>(null);

  const refreshDiagnostics = useCallback(async () => {
    // Diagnostics are best-effort: a failure here should not make the settings
    // form look broken, since the form works without them.
    const [providerList, schedulerState, logRows] = await Promise.all([
      getProviderStatus().catch(() => []),
      getSchedulerStatus().catch(() => null),
      getNotificationLogs().catch(() => []),
    ]);
    setProviders(providerList);
    setScheduler(schedulerState);
    setLogs(logRows);
  }, []);

  // Prefill from whatever is already stored. The API nests contact under
  // Contract 6, so this reads through `contact` rather than the top level.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const existing = await getNotificationSettings();
        if (cancelled) return;
        if (existing) {
          setHasSettings(true);
          setEmail(existing.contact?.email ?? "");
          setPhone(existing.contact?.phone_whatsapp ?? "");
          setFullName(existing.full_name ?? "");
          if (existing.notification_channels?.length) {
            setChannels(existing.notification_channels);
          }
          if (existing.frequency) setFrequency(existing.frequency);
          if (existing.relevance_threshold != null) {
            setThreshold(existing.relevance_threshold);
          }
          if (existing.send_hour_local != null) {
            setSendHour(`${String(existing.send_hour_local).padStart(2, "0")}:00`);
          }
          if (existing.timezone) setTimezone(existing.timezone);
        }
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : String(caught));
      } finally {
        if (!cancelled) setLoading(false);
      }
      if (!cancelled) await refreshDiagnostics();
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshDiagnostics]);

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
        fullName,
        sendHourLocal: Number(sendHour.slice(0, 2)),
        timezone,
      });
      setSaved(result);
      setHasSettings(true);

      // The scheduled digest has no browser session to read a profile from, so
      // the one held in this tab is pushed to the server alongside the contact
      // details. Without it a saved schedule would fire and find nothing to
      // match against.
      if (profile) await saveProfileSnapshot(profile);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSaving(false);
    }
  }

  /** Run one digest action against whatever is already in the job pool.
   *
   *  Deliberately does NOT ingest first. Sending used to be chained behind a
   *  fresh scrape, which meant a job board being slow, rate-limited or down
   *  failed the whole thing and the email never went — the one path you most
   *  need working when you are testing delivery. Fetching new postings is now
   *  its own button, for when you want the digest to reflect new jobs rather
   *  than to prove the mail works.
   */
  async function withBusy(kind: Busy, action: () => Promise<void>) {
    setBusy(kind);
    setDigestError(null);
    setSendNote(null);
    try {
      await action();
    } catch (caught) {
      setDigestError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(null);
      await refreshDiagnostics();
    }
  }

  async function runPreview() {
    setPreview(null);
    await withBusy("preview", async () => {
      const matches = await previewDigest();
      if (matches === null) {
        setDigestError("Save your notification settings first — there is nothing to preview against.");
        return;
      }
      setPreview(matches);
    });
  }

  /** `dryRun` renders the digest and picks a channel but transmits nothing —
   *  the cheap way to confirm the address and channel resolve before you put a
   *  real message through. */
  async function runSend(dryRun: boolean) {
    await withBusy(dryRun ? "dry" : "send", async () => {
      const result = await sendTestDigest("default", dryRun);
      if (result === null) {
        setDigestError("Save your notification settings first.");
        return;
      }
      const base = OUTCOME_COPY[result.outcome] ?? result.outcome;
      const via = result.results
        ?.map((entry) => `${entry.channel} via ${entry.provider}`)
        .join(", ");
      setSendNote(
        dryRun
          ? `Dry run — nothing was transmitted. ${base}`
          : via
            ? `${base} (${via})`
            : base,
      );
    });
  }

  /** Pull fresh postings into the pool. Separate from sending on purpose;
   *  see `run` above. */
  async function runIngest() {
    setBusy("ingest");
    setDigestError(null);
    setRun(null);
    // Both describe the pool as it was a moment ago. Leaving "Sent." sitting
    // above a fresh ingestion reads as though this run sent something, and a
    // preview built before new postings landed is stale by definition.
    setSendNote(null);
    setPreview(null);
    try {
      const runId = await triggerIngestion(ingestLimit);
      setRun(await waitForIngestion(runId, setRun));
    } catch (caught) {
      setDigestError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(null);
    }
  }

  const configuredChannels = providers.filter((entry) => entry.configured);
  const selectedButUnconfigured = channels.filter(
    (channel) => !configuredChannels.some((entry) => entry.channel === channel),
  );

  return (
    <div className="space-y-10">
      <section className="space-y-4">
        <header>
          <h1 className="text-title font-extrabold text-ink">Notifications</h1>
          <p className="mt-2 max-w-prose text-ink-muted">
            Where to reach you, and when. Saved on the server, so a digest can go
            out on schedule whether or not this tab is open.
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
                    hint="Where the digest goes."
                  />
                  <TextField
                    label="Phone (WhatsApp)"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="+20…"
                    hint="International format. Normalised before sending."
                  />
                </div>

                <div className="max-w-sm">
                  <TextField
                    label="Your name"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="Optional"
                    hint="How the digest greets you."
                  />
                </div>

                <fieldset>
                  <legend className="mb-1.5 text-body-sm font-semibold text-ink">Channels</legend>
                  <p className="mb-2 text-label text-ink-muted">
                    WhatsApp is tried first; email is the fallback. You get one
                    message, not one per channel.
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
                            "rounded-chip border px-3.5 py-1.5 text-body-sm font-semibold capitalize transition-colors duration-state ease-enter " +
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
                  {selectedButUnconfigured.length > 0 && (
                    <p className="mt-2 text-label text-amber-ink">
                      {selectedButUnconfigured.join(" and ")}{" "}
                      {selectedButUnconfigured.length === 1 ? "is" : "are"} selected but
                      not configured on the server, so {selectedButUnconfigured.length === 1 ? "it" : "they"}{" "}
                      will be skipped.
                    </p>
                  )}
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

                <div className="grid gap-5 sm:grid-cols-2">
                  <SelectField
                    label="Delivery time"
                    hint="Your local time."
                    options={SEND_HOURS}
                    value={sendHour}
                    onChange={(e) => setSendHour(e.target.value)}
                  />
                  <SelectField
                    label="Timezone"
                    options={TIMEZONES}
                    value={timezone}
                    onChange={(e) => setTimezone(e.target.value)}
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
                    <span className="text-body-sm text-ink-muted">
                      {profile
                        ? "Preferences and your parsed profile are stored on the server."
                        : "Preferences stored. Upload a CV so the scheduled digest has a profile to match against."}
                    </span>
                  </div>
                  {/* The raw payload is genuinely useful when wiring the
                      notifications lane, and clutter for everyone else. Behind
                      a disclosure it is available without being on display. */}
                  <details className="group mt-3">
                    <summary className="cursor-pointer select-none text-body-sm font-semibold text-ink-muted transition-colors duration-state hover:text-brand">
                      View the stored payload
                    </summary>
                    <pre className="mt-2 overflow-x-auto rounded-control bg-surface p-3 font-mono text-label leading-relaxed text-ink-muted">
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
            Send a digest on demand, without waiting for the schedule. Preview
            and send run the same selection code, so what you see here is what
            arrives.
          </p>
        </header>

        <Card>
          <CardBody className="space-y-5">
            <div className="flex flex-wrap gap-3">
              <Button
                onClick={() => runSend(false)}
                loading={busy === "send"}
                disabled={busy !== null || !hasSettings}
              >
                Send test email
              </Button>
              <Button
                variant="secondary"
                onClick={() => runSend(true)}
                loading={busy === "dry"}
                disabled={busy !== null || !hasSettings}
              >
                Dry run
              </Button>
              <Button
                variant="secondary"
                onClick={runPreview}
                loading={busy === "preview"}
                disabled={busy !== null || !hasSettings}
              >
                Preview digest
              </Button>
            </div>

            <p className="max-w-prose text-body-sm text-ink-muted">
              Send bypasses the once-a-day guard, so you can fire it repeatedly.
              Dry run picks the channel and renders the message without
              transmitting. With no SMTP host configured the digest prints to
              the API console instead of sending.
            </p>

            {!hasSettings && (
              <p className="text-body-sm text-ink-muted">
                Save your notification settings first — the digest is built from them.
              </p>
            )}

            {/* Ingestion is its own step, not a prerequisite of sending. It was
                chained in front of the send, which meant a slow or failing job
                board took the email down with it — the exact path you need
                working when you are testing delivery. */}
            <div className="space-y-3 border-t border-line pt-5">
              <p className="max-w-prose text-body-sm text-ink-muted">
                The digest ranks whatever is already in the job pool. Pull in
                fresh postings first if you want it to reflect new listings.
              </p>
              <div className="flex flex-wrap items-end gap-3">
                <div className="w-40">
                  <TextField
                    label="Postings per source"
                    type="number"
                    min={1}
                    max={50}
                    value={ingestLimit}
                    onChange={(e) => setIngestLimit(Number(e.target.value))}
                  />
                </div>
                <Button
                  variant="secondary"
                  onClick={runIngest}
                  loading={busy === "ingest"}
                  disabled={busy !== null}
                >
                  Fetch new postings
                </Button>
              </div>
            </div>

            {run && (
              <p className="text-body-sm text-ink-muted">
                Ingestion run {run.id}: {run.jobs_inserted ?? 0} new,{" "}
                {run.jobs_updated ?? 0} updated, status {run.status}.
                {run.error_message && (
                  <span className="text-amber-ink"> Some sources failed: {run.error_message}</span>
                )}
              </p>
            )}

            {sendNote && (
              <div className="rounded-card border border-line bg-surface-sunken p-4 text-body-sm text-ink">
                {sendNote}
              </div>
            )}

            {digestError && <ErrorState message={digestError} />}

            {preview !== null && preview.length > 0 && (
              <div className="space-y-3">
                <Badge tone="teal">
                  {preview.length} match{preview.length === 1 ? "" : "es"} in the next digest
                </Badge>
                {preview.map((match, index) => (
                  <div
                    key={match.job.job_id}
                    className="animate-fade-rise rounded-card border border-line bg-surface p-4"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <p className="font-semibold text-ink">
                        {index + 1}. {match.job.title}
                      </p>
                      <Badge tone="teal">{Math.round(match.match_score)}%</Badge>
                    </div>
                    <p className="text-body-sm text-ink-muted">
                      {match.job.company}
                      {match.job.location ? ` · ${match.job.location}` : ""}
                    </p>
                    {/* Tint, not an accent bar — same treatment as the email
                        template, so the preview reads like what arrives. */}
                    {match.reason && (
                      <p className="mt-2 rounded-control bg-surface-sunken px-3 py-2 text-body-sm text-ink-muted">
                        {match.reason}
                      </p>
                    )}
                    <a
                      href={match.job.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="mt-2 inline-block text-body-sm font-semibold text-brand underline underline-offset-2 transition-colors duration-state hover:text-brand-deep"
                    >
                      Open job posting
                    </a>
                  </div>
                ))}
              </div>
            )}

            {preview !== null && preview.length === 0 && (
              <EmptyState title="Nothing would be sent">
                No posting cleared your relevance threshold. Lower it, or ingest
                more jobs.
              </EmptyState>
            )}
          </CardBody>
        </Card>
      </section>

      <section className="space-y-4">
        <header>
          <h2 className="text-subtitle font-bold text-ink">Delivery status</h2>
          <p className="mt-2 max-w-prose text-ink-muted">
            The first place to look when a digest does not arrive.
          </p>
        </header>

        <Card>
          <CardBody className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              {providers.map((entry) => (
                <Badge
                  key={entry.channel}
                  // Amber, not teal, for a channel that runs but does not
                  // transmit: "email: console" reading as a healthy green is
                  // how you conclude delivery works when nothing has been sent.
                  tone={entry.delivers ? "teal" : entry.configured ? "amber" : "neutral"}
                >
                  {entry.channel}: {entry.configured ? entry.name : "not configured"}
                </Badge>
              ))}
              <Badge tone={scheduler?.running ? "teal" : "neutral"}>
                schedule: {scheduler?.running ? "running" : "off"}
              </Badge>
            </div>

            {providers.filter((entry) => entry.note).map((entry) => (
              <p key={entry.channel} className="text-label text-amber-ink">
                {entry.note}
              </p>
            ))}

            <p className="text-label text-ink-muted">
              {scheduler?.running
                ? `Next check ${scheduler.next_run_at ?? "shortly"}. Digests go out at each user's chosen local hour.`
                : "The scheduler is off, so nothing sends on its own. Use Send now, or set NOTIFICATIONS_SCHEDULER_ENABLED=true on the server."}
            </p>

            {logs.length === 0 ? (
              <EmptyState title="No delivery attempts yet">
                Sends and failures both show up here once something has been tried.
              </EmptyState>
            ) : (
              <ul className="space-y-2">
                {logs.map((log) => (
                  <li
                    key={log.id}
                    className="flex flex-wrap items-center gap-2 rounded-control border border-line bg-surface px-3 py-2 text-body-sm"
                  >
                    <Badge tone={log.status === "sent" ? "teal" : "amber"}>{log.status}</Badge>
                    <span className="text-ink">
                      {log.channel}
                      {log.provider ? ` · ${log.provider}` : ""}
                    </span>
                    <span className="text-ink-muted">{log.sent_on_local_date}</span>
                    <span className="text-ink-muted">
                      {log.job_ids.length} job{log.job_ids.length === 1 ? "" : "s"}
                    </span>
                    {log.error_message && (
                      <span className="text-amber-ink">{log.error_message}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </section>
    </div>
  );
}
