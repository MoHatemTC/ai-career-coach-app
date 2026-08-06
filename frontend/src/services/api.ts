/**
 * Every backend call the app makes, one function each.
 *
 * This is the direct port of `streamlit_app/api_client.py` plus the flattening
 * `streamlit_app/pipeline_stub.py` did. Nothing here is mocked: the same
 * endpoints Streamlit uses, so if both clients break it is the backend.
 */
import {
  BackendError,
  CHAT_TIMEOUT_MS,
  ChatUnavailable,
  PIPELINE_TIMEOUT_MS,
  postJson,
  request,
} from "./http";
import type {
  ChatMessage,
  ConversationResponse,
  IngestionRun,
  JobPosting,
  MatchExplanation,
  MatchResult,
  NotificationLog,
  NotificationSettings,
  PipelineResponse,
  PoolStats,
  Profile,
  ProviderStatus,
  RunIngestionResponse,
  SchedulerStatus,
  SendResult,
  TopJobMatch,
  UploadResponse,
} from "./types";

/* ------------------------------------------------------------------ health */

export async function healthCheck(): Promise<{ ok: boolean; message: string }> {
  try {
    await request("/", { timeoutMs: 5_000 });
    return { ok: true, message: "Backend is up." };
  } catch (error) {
    return {
      ok: false,
      message: error instanceof Error ? error.message : "Cannot reach the backend.",
    };
  }
}

/* --------------------------------------------------------------- CV upload */

export async function uploadCv(file: File): Promise<Profile> {
  const form = new FormData();
  form.append("file", file, file.name);

  // No Content-Type header: the browser sets it with the multipart boundary,
  // and setting it by hand produces a request the server cannot parse.
  const payload = await request<UploadResponse>("/upload", {
    method: "POST",
    body: form,
  });

  const profile = payload?.profile ?? {};
  // Some model paths return the profile as a JSON string rather than an object.
  if (typeof profile === "string") {
    try {
      return JSON.parse(profile) as Profile;
    } catch {
      return { summary: profile } as Profile;
    }
  }
  return profile as Profile;
}

/* --------------------------------------------------------------- matching */

/** Flatten the pipeline's ranked entries into what a card needs.
 *
 *  The backend attaches a real MatchExplanation. `placeholderExplanation` is
 *  the fallback for the one case it cannot explain: a ranked job missing from
 *  SQLite, where inventing requirements would be the only alternative. It
 *  reports only numbers the pipeline actually produced. */
function placeholderExplanation(entry: Record<string, unknown>): MatchExplanation {
  const job = (entry["job_data"] ?? {}) as Record<string, unknown>;
  const fit = entry["fit_score"];
  const similarity = job["match_score"];

  const measured: string[] = [];
  if (fit != null) measured.push(`re-ranker fit score ${String(fit)}`);
  if (similarity != null) measured.push(`vector similarity ${Number(similarity).toFixed(3)}`);

  return {
    overall_alignment_summary:
      `Retrieved and ranked (${measured.join(", ") || "no scores reported"}). ` +
      `No written explanation is available for this one, which means the posting ` +
      `is missing from the database and its requirements could not be read.`,
    strengths: [],
    gaps_or_missing_requirements: [],
    recommendations: [],
    next_steps: [],
  };
}

export async function runMatchPipeline(profile: Profile, topK = 10): Promise<MatchResult[]> {
  const payload = await postJson<PipelineResponse>(
    "/matching/pipeline",
    { profile, top_k: topK },
    PIPELINE_TIMEOUT_MS,
  );

  const ranked = (payload?.ranked ?? []) as unknown as Record<string, unknown>[];
  return ranked.map((entry) => {
    const job = (entry["job_data"] ?? {}) as Record<string, unknown>;
    const explanation =
      (entry["explanation"] as MatchExplanation | undefined) ?? placeholderExplanation(entry);

    return {
      job_id: (entry["job_id"] as string | undefined) ?? (job["job_id"] as string | undefined),
      job_title: (job["title"] as string) || "Untitled role",
      company: (job["company"] as string) || "Unknown company",
      location: (job["location"] as string | null) ?? null,
      description: (job["description"] as string | null) ?? null,
      required_skills: (job["required_skills"] as string[] | null) ?? [],
      url: (job["url"] as string | null) ?? null,
      fit_score: (entry["fit_score"] as number | null) ?? null,
      match_score: (job["match_score"] as number | null) ?? null,
      date_posted: (job["date_posted"] as string | null) ?? null,
      explanation,
    };
  });
}

/* ------------------------------------------------------------------- chat */

/**
 * Send a message to the conversational agent.
 *
 * Tries POST /chat first, which is the CV lane's agent, falling back to
 * POST /conversation, which serves the same contract. Preferring /chat means
 * that lane takes over automatically once deployed, with no change here.
 *
 * Throws ChatUnavailable only if neither exists, which is the one case where
 * the caller should drop to keyword routing.
 */
export async function chat(
  message: string,
  profile: Profile,
  history: ChatMessage[] = [],
): Promise<ConversationResponse> {
  const base = { message, profile: profile ?? {} };
  const attempts: Array<[string, unknown]> = [
    ["/chat", base],
    ["/conversation", { ...base, history }],
  ];

  for (const [path, body] of attempts) {
    try {
      const result = await postJson<ConversationResponse>(path, body, CHAT_TIMEOUT_MS);
      if (result) return result;
    } catch (error) {
      // 404 means this backend does not have that endpoint; try the next.
      if (error instanceof BackendError && error.status === 404) continue;
      throw error;
    }
  }

  throw new ChatUnavailable("Neither /chat nor /conversation is available on this backend.");
}

/* -------------------------------------------------------------- ingestion */

export async function triggerIngestion(limit = 10, sources: string[] | null = null): Promise<number> {
  const payload = await postJson<RunIngestionResponse>("/ingestion/run", { sources, limit });
  if (!payload) throw new BackendError("Ingestion did not return a run id.");
  return payload.run_id;
}

export async function getIngestionRun(runId: number): Promise<IngestionRun> {
  const payload = await request<IngestionRun>(`/ingestion/runs/${runId}`);
  if (!payload) throw new BackendError(`Ingestion run ${runId} was not found.`);
  return payload;
}

export async function listIngestionRuns(): Promise<IngestionRun[]> {
  return (await request<IngestionRun[]>("/ingestion/runs")) ?? [];
}

export async function listJobs(limit = 20, offset = 0): Promise<JobPosting[]> {
  return (await request<JobPosting[]>(`/ingestion/jobs?limit=${limit}&offset=${offset}`)) ?? [];
}

/** How long to wait on a background run before giving up and using whatever it
 *  has already committed. A poll budget, not a request timeout: ingestion
 *  commits per source, so jobs already written are usable and the caller should
 *  get on with matching rather than failing outright. */
export const INGESTION_POLL_BUDGET_MS = 90_000;
const POLL_INTERVAL_MS = 1_000;

export async function waitForIngestion(
  runId: number,
  onTick?: (run: IngestionRun) => void,
  budgetMs = INGESTION_POLL_BUDGET_MS,
): Promise<IngestionRun> {
  const deadline = Date.now() + budgetMs;
  let run = await getIngestionRun(runId);
  onTick?.(run);

  while (run.status === "running" && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    run = await getIngestionRun(runId);
    onTick?.(run);
  }
  return run;
}

/** A live snapshot of the ingested job pool, for the landing page.
 *
 *  Returns null rather than throwing when the backend is unreachable: the
 *  landing page is a static bundle that has to render on its own, and a
 *  marketing hero is the last place that should surface a connection error.
 *  The caller shows its resting state instead.
 */
export async function getPoolStats(): Promise<PoolStats | null> {
  try {
    return await request<PoolStats>("/ingestion/stats?top=5", { timeoutMs: 6_000 });
  } catch {
    return null;
  }
}

/* ---------------------------------------------------------- notifications */

/**
 * WHERE EMAIL AND PHONE ARE PERSISTED.
 *
 * These two functions are the only place the app writes or reads the user's
 * contact details. See docs/notification-parameters.md for the full contract
 * the notifications lane consumes.
 */
export async function getNotificationSettings(
  userId = "default",
): Promise<NotificationSettings | null> {
  // 404 means nothing saved yet, which is a normal first-run state, not an error.
  return await request<NotificationSettings>(`/notifications/settings/${userId}`, {
    nullOn: [404],
  });
}

export interface SaveSettingsInput {
  email: string;
  phone: string;
  userId?: string;
  channels?: string[];
  frequency?: string;
  relevanceThreshold?: number;
  fullName?: string;
  sendHourLocal?: number;
  timezone?: string;
}

export async function saveNotificationSettings(
  input: SaveSettingsInput,
): Promise<NotificationSettings> {
  // Contract 6 shape: contact is nested. Omitted preferences are left as the
  // backend already has them rather than blanked.
  const payload: Record<string, unknown> = {
    user_id: input.userId ?? "default",
    contact: { email: input.email, phone_whatsapp: input.phone },
  };
  if (input.channels !== undefined) payload["notification_channels"] = input.channels;
  if (input.frequency !== undefined) payload["frequency"] = input.frequency;
  if (input.relevanceThreshold !== undefined) {
    payload["relevance_threshold"] = input.relevanceThreshold;
  }
  if (input.fullName !== undefined) payload["full_name"] = input.fullName;
  if (input.sendHourLocal !== undefined) payload["send_hour_local"] = input.sendHourLocal;
  if (input.timezone !== undefined) payload["timezone"] = input.timezone;

  const saved = await postJson<NotificationSettings>("/notifications/settings", payload);
  if (!saved) throw new BackendError("Saving settings returned nothing.");
  return saved;
}

/**
 * Persist the profile the *scheduled* digest scores against.
 *
 * The profile otherwise lives only in this tab's session state, which a 9am
 * cron job on the server cannot reach — so without this call the daily digest
 * can only ever run for someone who happens to have the app open. Saved
 * alongside the contact details, on the same settings row.
 *
 * 404 means no settings row exists yet; save contact details first.
 */
export async function saveProfileSnapshot(
  profile: Profile,
  userId = "default",
): Promise<boolean> {
  const saved = await request<unknown>(`/notifications/settings/${userId}/profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile }),
    nullOn: [404],
  });
  return saved !== null;
}

/* ------------------------------------------------------- digest delivery -- */

/** What the next digest would contain, without sending anything.
 *
 *  Server-side, and produced by the same selection code that builds the real
 *  message — so what is previewed here and what arrives cannot drift. */
export async function previewDigest(
  userId = "default",
  topN = RECOMMENDATION_LIMIT,
): Promise<TopJobMatch[] | null> {
  return await request<TopJobMatch[]>(
    `/notifications/preview/${userId}?top_n=${topN}`,
    // 404 = no settings saved yet, which is a normal first-run state.
    { nullOn: [404], timeoutMs: PIPELINE_TIMEOUT_MS },
  );
}

/** Send this user's digest now, bypassing the once-per-day guard. */
export async function sendTestDigest(
  userId = "default",
  dryRun = false,
): Promise<SendResult | null> {
  return await request<SendResult>(
    `/notifications/send-test/${userId}?dry_run=${dryRun}`,
    { method: "POST", nullOn: [404], timeoutMs: PIPELINE_TIMEOUT_MS },
  );
}

/** Which channels are actually usable right now — the first thing to check
 *  when a digest does not arrive. */
export async function getProviderStatus(): Promise<ProviderStatus[]> {
  return (await request<ProviderStatus[]>("/notifications/providers")) ?? [];
}

export async function getSchedulerStatus(): Promise<SchedulerStatus | null> {
  return await request<SchedulerStatus>("/notifications/scheduler");
}

/** Recent delivery attempts, newest first. Failures included. */
export async function getNotificationLogs(
  userId = "default",
  limit = 10,
): Promise<NotificationLog[]> {
  return (
    (await request<NotificationLog[]>(
      `/notifications/logs?user_id=${userId}&limit=${limit}`,
    )) ?? []
  );
}

/* ------------------------------------------------------------ digest ----- */

/** How many jobs one digest carries. Matches `DEFAULT_TOP_N` in
 *  `backend/features/notifications/matching_bridge.py`, which is what actually
 *  decides — this is only the default the preview asks for.
 *
 *  The client-side `buildRecommendations` that used to live here was removed
 *  when delivery landed: selection is now `GET /notifications/preview/{id}`,
 *  server-side, so the preview and the sent message are produced by one piece
 *  of code rather than two that can drift. */
export const RECOMMENDATION_LIMIT = 3;
