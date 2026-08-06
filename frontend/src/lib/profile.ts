/**
 * Coercion helpers for the parsed profile.
 *
 * The parser returns whatever JSON the model produced, and models are not
 * consistent about it: `skills` comes back as a list from one and a
 * comma-separated string from another, `experience` as a paragraph or as an
 * array of roles. These mirror `_as_list` / `_as_text` in
 * `streamlit_app/chatbot_ui.py` so both clients read a given response the same
 * way.
 */
import type { Profile } from "@/services/types";

/**
 * The parse prompt asks for `"experience": []` and `"education": []` without
 * specifying what an item looks like, so the model answers with objects whose
 * keys it chooses per CV: {title, company, dates}, {position, employer, period},
 * {degree, institution, year}. These are preference lists, not a schema —
 * anything unrecognised still gets rendered rather than dropped.
 */
const HEAD_KEYS = ["title", "role", "position", "jobtitle", "degree", "qualification"];
const ORG_KEYS = [
  "company",
  "employer",
  "organisation",
  "organization",
  "institution",
  "school",
  "university",
];
const WHEN_KEYS = ["dates", "date", "duration", "period", "years", "year", "graduationyear"];

function normaliseKey(key: string): string {
  return key.toLowerCase().replace(/[\s_-]/g, "");
}

/** A single readable value. Nested objects are deliberately not flattened
 *  here; `formatEntry` owns that so the recursion stays in one place. */
function scalar(value: unknown): string {
  if (value == null) return "";
  if (Array.isArray(value)) return value.map(scalar).filter(Boolean).join(", ");
  if (typeof value === "object") return "";
  return String(value).trim();
}

/**
 * One CV entry as text a person can read and edit.
 *
 * Falls back to the raw JSON rather than "[object Object]": if the model
 * returned a shape nothing here recognises, showing it is honest and lets the
 * user fix it by hand, which is the whole point of the form.
 */
export function formatEntry(value: unknown): string {
  if (value == null) return "";
  if (Array.isArray(value)) return value.map(formatEntry).filter(Boolean).join("\n\n");
  if (typeof value !== "object") return String(value).trim();

  const record = value as Record<string, unknown>;
  const used = new Set<string>();

  function take(candidates: string[]): string {
    for (const key of Object.keys(record)) {
      if (!candidates.includes(normaliseKey(key))) continue;
      const text = scalar(record[key]);
      if (text) {
        used.add(key);
        return text;
      }
    }
    return "";
  }

  const head = take(HEAD_KEYS);
  const org = take(ORG_KEYS);
  const when = take(WHEN_KEYS);

  const lead = [head, org].filter(Boolean).join(" — ");
  const headline = when ? (lead ? `${lead} (${when})` : when) : lead;

  const rest = Object.keys(record)
    .filter((key) => !used.has(key))
    .map((key) => {
      const nested = record[key];
      if (nested != null && typeof nested === "object" && !Array.isArray(nested)) {
        return formatEntry(nested);
      }
      return scalar(nested);
    })
    .filter(Boolean);

  const lines = [headline, ...rest].filter(Boolean);
  return lines.length > 0 ? lines.join("\n") : JSON.stringify(record);
}

export function asList(value: unknown): string[] {
  if (value == null) return [];
  if (Array.isArray(value)) return value.map(formatEntry).filter(Boolean);
  if (typeof value === "string") {
    return value
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
  }
  return [formatEntry(value)].filter(Boolean);
}

export function asText(value: unknown): string {
  if (value == null) return "";
  if (Array.isArray(value)) return value.map(formatEntry).filter(Boolean).join("\n\n");
  return formatEntry(value);
}

/** The target role, which the parser labels inconsistently. */
export function profileTitle(profile: Profile): string {
  return asText(profile.title ?? profile.current_title);
}

function trim(value: string, max: number): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max).replace(/\s+\S*$/, "")}…`;
}

/**
 * What the assistant says after a CV is parsed.
 *
 * Reading the profile back opens the conversation where the parser's mistakes
 * are correctable in plain language, rather than only in the form below.
 */
export function summariseParsedProfile(profile: Profile): string {
  const fields: Array<[string, string]> = [
    ["Name", asText(profile.name)],
    ["Target role", profileTitle(profile)],
    ["Skills", asList(profile.skills).join(", ")],
    ["Education", asText(profile.education)],
    ["Experience", asText(profile.experience)],
  ];

  const lines = fields
    .filter(([, value]) => value)
    .map(([label, value]) => `- **${label}:** ${trim(value, 200)}`);

  if (lines.length === 0) {
    return (
      "I could not read anything useful out of that CV. If it is a scanned image " +
      "the parser cannot extract text from it, since there is no OCR step. Try a " +
      "text-based PDF, or fill the form in by hand."
    );
  }

  return [
    "Thanks. Here is what I found in your CV:",
    "",
    ...lines,
    "",
    "Want to change anything? Tell me in your own words, or ask me to find matching jobs.",
  ].join("\n");
}

/**
 * FALLBACK routing, used only when the conversational agent is not deployed.
 * Deliberately dumb so it cannot be mistaken for real intent classification.
 */
const MATCH_INTENT_WORDS = ["match", "job", "find", "search", "opportunit", "role"];

export function looksLikeMatchRequest(text: string): boolean {
  const lower = text.toLowerCase();
  return MATCH_INTENT_WORDS.some((word) => lower.includes(word));
}

/** Does this profile carry enough to run the pipeline at all? */
export function profileIsUsable(profile: Profile | null): profile is Profile {
  if (!profile) return false;
  return Boolean(
    asText(profile.name) ||
      profileTitle(profile) ||
      asList(profile.skills).length ||
      asText(profile.experience),
  );
}
