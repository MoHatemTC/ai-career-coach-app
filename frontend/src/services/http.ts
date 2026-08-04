/**
 * The one place that talks to the network.
 *
 * Ported from `streamlit_app/api_client.py`, deliberately keeping two things
 * that file learned the hard way:
 *
 * 1. FastAPI puts the real cause in the JSON body's `detail`, but a bare
 *    status check throws away everything except the status line. A 503 then
 *    surfaces as "Service Unavailable" while the body said which environment
 *    variable was wrong. `BackendError` digs the detail back out.
 *
 * 2. Timeouts have to be sized to the work being waited on. `/matching/pipeline`
 *    is four sequential model calls, not one, and a budget sized for one
 *    reports a failure that has not happened.
 */

/** Base URL for the API. In dev, Vite proxies /api to FastAPI (see
 *  vite.config.ts), so same-origin and no CORS round trip. In a built
 *  deployment set VITE_API_BASE_URL, or let nginx proxy /api the same way. */
export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

/** One model call's ceiling backend-side, mirroring LLM_TIMEOUT_SECONDS. */
const LLM_TIMEOUT_MS = 45_000;

/** `/matching/pipeline` makes a ranking call plus one explanation per returned
 *  job. Sized from that, not guessed, so the two cannot drift apart. */
export const PIPELINE_MODEL_CALLS = 4;
export const PIPELINE_TIMEOUT_MS = PIPELINE_MODEL_CALLS * LLM_TIMEOUT_MS + 30_000;

/** The conversational agent is a single call. */
export const CHAT_TIMEOUT_MS = LLM_TIMEOUT_MS + 15_000;

/** Everything else: parsing a CV is the slowest of them. */
export const DEFAULT_TIMEOUT_MS = 60_000;

export class BackendError extends Error {
  readonly status: number | undefined;
  readonly detail: string | undefined;

  constructor(message: string, status?: number, detail?: string) {
    super(message);
    this.name = "BackendError";
    this.status = status;
    this.detail = detail;
  }
}

/** Neither /chat nor /conversation exists on this backend. The only case where
 *  the caller should drop to keyword routing. */
export class ChatUnavailable extends BackendError {
  constructor(message: string) {
    super(message);
    this.name = "ChatUnavailable";
  }
}

async function readDetail(response: Response): Promise<string | undefined> {
  try {
    const body: unknown = await response.clone().json();
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      // 422 from FastAPI is a list of per-field errors; flatten it into
      // something a person can act on rather than showing [object Object].
      if (Array.isArray(detail)) {
        return detail
          .map((item) => {
            if (item && typeof item === "object" && "msg" in item) {
              const loc =
                "loc" in item && Array.isArray((item as { loc: unknown[] }).loc)
                  ? (item as { loc: unknown[] }).loc.join(".")
                  : "";
              return loc ? `${loc}: ${String((item as { msg: unknown }).msg)}` : String((item as { msg: unknown }).msg);
            }
            return JSON.stringify(item);
          })
          .join("; ");
      }
      return JSON.stringify(detail);
    }
  } catch {
    // Not JSON. Fall through to the text body.
  }
  try {
    const text = (await response.clone().text()).trim();
    return text || undefined;
  } catch {
    return undefined;
  }
}

interface RequestOptions {
  method?: string;
  body?: BodyInit | null;
  headers?: Record<string, string>;
  timeoutMs?: number;
  /** Status codes to return as null rather than throwing. Used for the 404
   *  that means "no settings saved yet", which is not an error. */
  nullOn?: number[];
  signal?: AbortSignal;
}

export async function request<T>(
  path: string,
  { method = "GET", body = null, headers = {}, timeoutMs = DEFAULT_TIMEOUT_MS, nullOn = [], signal }: RequestOptions = {},
): Promise<T | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  // Honour a caller's own cancellation (React StrictMode, unmount) as well as
  // the timeout, without losing either.
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", () => controller.abort(), { once: true });
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      body,
      headers,
      signal: controller.signal,
    });
  } catch (error) {
    clearTimeout(timer);
    if (controller.signal.aborted) {
      throw new BackendError(
        `The request to ${path} timed out after ${Math.round(timeoutMs / 1000)}s. ` +
          `If this was a matching run the backend may still be working; the model ` +
          `calls are slow.`,
      );
    }
    throw new BackendError(
      `Could not reach the backend at ${API_BASE}. Is it running? ` +
        `Start it with: uvicorn backend.main:app --reload`,
    );
  }
  clearTimeout(timer);

  if (nullOn.includes(response.status)) return null;

  if (!response.ok) {
    const detail = await readDetail(response);
    throw new BackendError(
      detail ?? `${response.status} ${response.statusText}`,
      response.status,
      detail,
    );
  }

  if (response.status === 204) return null;
  return (await response.json()) as T;
}

export function postJson<T>(path: string, payload: unknown, timeoutMs?: number): Promise<T | null> {
  return request<T>(path, {
    method: "POST",
    body: JSON.stringify(payload),
    headers: { "Content-Type": "application/json" },
    ...(timeoutMs === undefined ? {} : { timeoutMs }),
  });
}
