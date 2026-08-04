import { Markdown } from "@/components/Markdown";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody } from "@/components/ui/Card";
import type { MatchResult } from "@/services/types";

/** Long descriptions are trimmed on the card. The full text is one click away
 *  on the posting itself, and an untrimmed paragraph pushes the explanation,
 *  which is the part worth reading, below the fold. */
const DESCRIPTION_LIMIT = 400;

function trim(text: string, max: number): string {
  const clean = text.trim();
  if (clean.length <= max) return clean;
  return `${clean.slice(0, max).replace(/\s+\S*$/, "")}…`;
}

function Bullets({ label, items, tone }: { label: string; items?: string[] | null; tone: "teal" | "amber" | "brand" }) {
  // Every list on MatchExplanation defaults to empty, so a partially populated
  // response has to render cleanly instead of showing empty headings.
  if (!items || items.length === 0) return null;

  return (
    <div>
      <Badge tone={tone}>{label}</Badge>
      <ul className="mt-2 ml-4 list-disc space-y-1 text-sm leading-relaxed text-ink-muted">
        {items.map((item, index) => (
          <li key={`${label}-${index}`}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export function MatchCard({ result, rank }: { result: MatchResult; rank?: number }) {
  const explanation = result.explanation ?? {};
  const fit = result.fit_score;

  return (
    <Card accent="brand" className="animate-fade-rise">
      <CardBody className="space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h3 className="text-lg font-bold leading-snug text-ink">
              {rank !== undefined && <span className="tabular mr-2 text-ink-muted">{rank}.</span>}
              {result.job_title}
            </h3>
            <p className="mt-0.5 text-sm text-ink-muted">{result.company}</p>
          </div>

          {fit != null && (
            // The fit score is the re-ranker's own number, passed through and
            // never recomputed here.
            <div className="shrink-0 text-right">
              <div className="tabular text-xl font-bold text-brand">{Math.round(fit * 100)}</div>
              <div className="text-[0.6875rem] uppercase tracking-wide text-ink-muted">fit</div>
            </div>
          )}
        </div>

        <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-muted">
          {result.location && <span>{result.location}</span>}
          {result.date_posted && <span className="tabular">{result.date_posted}</span>}
        </div>

        {result.description && (
          <p className="text-sm leading-relaxed text-ink-muted">
            {trim(result.description, DESCRIPTION_LIMIT)}
          </p>
        )}

        {result.required_skills && result.required_skills.length > 0 && (
          <div>
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
              Required skills
            </p>
            <div className="flex flex-wrap gap-1.5">
              {result.required_skills.map((skill) => (
                <Badge key={skill} tone="neutral">
                  {skill}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {explanation.overall_alignment_summary && (
          <Markdown className="text-ink-muted">{explanation.overall_alignment_summary}</Markdown>
        )}

        <div className="space-y-3 border-t border-line pt-4">
          {/* Teal is matched, amber is a gap: categorical, following the brand's
              own use of these two hues. Blue is never a status. */}
          <Bullets label="Strengths" items={explanation.strengths} tone="teal" />
          <Bullets
            label="Gaps and missing requirements"
            items={explanation.gaps_or_missing_requirements}
            tone="amber"
          />
          <Bullets label="Recommendations" items={explanation.recommendations} tone="brand" />
          <Bullets label="Next steps" items={explanation.next_steps} tone="brand" />
        </div>

        {result.url && (
          <div className="border-t border-line pt-4">
            <a
              href={result.url}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex h-10 items-center rounded-control bg-brand px-4 text-sm font-semibold text-white shadow-raised transition-colors duration-state ease-enter hover:bg-brand-deep"
            >
              Open job posting
            </a>
            <p className="mt-2 truncate text-xs text-ink-muted" title={result.url}>
              {result.url}
            </p>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
