import { useEffect, useState } from "react";

import { getPoolStats } from "@/services/api";
import type { PoolStats } from "@/services/types";

/**
 * The landing hero's visual: a live snapshot of the job pool this instance has
 * actually ingested.
 *
 * This replaced a radar of invented candidate scores. That version was a
 * gimmick — five made-up percentages with sliders attached, which demonstrated
 * nothing except that the numbers were fake. Everything here is counted from
 * `job_postings` at request time by `GET /ingestion/stats`.
 *
 * WHAT THE TAGS ARE, AND ARE NOT
 * ------------------------------
 * `top_tags` are the *source's own category tags*, not extracted skills.
 * Arbeitnow publishes values like "engineering" and "marketing" that describe a
 * job family rather than a competency, and they dominate the counts. The copy
 * therefore says "categories", never "skills in demand" — the latter would
 * claim an analysis the number does not support, and the gap analysis this
 * product sells runs on a different field entirely.
 *
 * RENDERING WITHOUT A BACKEND
 * ---------------------------
 * The landing page is a static bundle and must paint on its own; a first-time
 * visitor should never meet a spinner or a connection error in the hero. So the
 * card renders its resting state immediately, fetches in the background, and
 * keeps the resting state if the call fails. Nothing here is ever invented to
 * fill the gap — when there is no data, it says so.
 */

const SECTORS = [
  "M140,140 L83.57,62.34 A96,96 0 0,1 196.43,62.34 Z",
  "M140,140 L196.43,62.34 A96,96 0 0,1 231.31,169.66 Z",
  "M140,140 L231.31,169.66 A96,96 0 0,1 140,236 Z",
  "M140,140 L140,236 A96,96 0 0,1 48.69,169.66 Z",
  "M140,140 L48.69,169.66 A96,96 0 0,1 83.57,62.34 Z",
] as const;

function relativeAge(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  const minutes = Math.round((Date.now() - then) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

/** How far out a category reaches, as a fraction of the full radius.
 *
 *  Raw counts here are brutally long-tailed — the leader routinely holds five
 *  or six times the runner-up — so an area-true radius, sqrt(count / peak),
 *  is correct and nearly unreadable at the same time: the four trailing
 *  categories collapse into a band too tight to tell apart.
 *
 *  So the area-true value is pulled toward the outer edge by a fixed amount.
 *  At 0.6 the pool's real spread — 63 postings against 10, a 6.3x range —
 *  draws as a 1.7x range in area. That is a deliberate understatement, and it
 *  is only defensible because the exact figure is never inferred from the
 *  drawing: every count is printed in the row beside it and again in the hover
 *  line. The chart is here to show that the pool is lopsided and which way; the
 *  numbers are there to say by how much.
 */
const UNDERSTATEMENT = 0.6;

function radiusFactor(count: number, peak: number): number {
  // A missing category stays at zero: an empty pool should collapse to
  // nothing, which is the honest picture of an empty pool.
  if (!count || peak <= 0) return 0;

  const area = Math.sqrt(count / peak);
  // 0.14 floor so a present-but-rare category still reads as present.
  return Math.max(0.14, area + (1 - area) * UNDERSTATEMENT);
}

type Tag = { label: string; count: number };

/** The rosette.
 *
 *  WHAT THE RADIUS ENCODES
 *  -----------------------
 *  A sector's perceived weight is its AREA, and area grows with the square of
 *  the radius, so putting the count straight into the radius squares every
 *  disparity: engineering (63) against finance (10) is 6.3x by count but would
 *  render at 40x the area. That is not a skewed chart, it is a false one, and
 *  it crushed the four trailing categories into unreadable nubs besides.
 *
 *  sqrt(count / peak) fixes the falsehood but not the readability — area-true,
 *  the four trailing wedges still land within a hair of each other. So the
 *  area-true value is understated toward the outer edge (see `radiusFactor`),
 *  which trades proportional honesty for the ability to tell five categories
 *  apart. That trade is only payable because the chart is not the source of
 *  the numbers: every count is printed in the row beside it and again on hover,
 *  so nothing here depends on measuring a radius by eye.
 */
function JpChart({
  tags,
  peak,
  active,
  setActive,
  total,
}: {
  tags: readonly Tag[];
  peak: number;
  active: number | null;
  setActive: (index: number | null) => void;
  total: number;
}) {
  return (
    <svg
      viewBox="0 0 280 280"
      className="mx-auto h-32 w-32 shrink-0 sm:mx-0"
      role="img"
      aria-label={
        tags.length
          ? `Category spread across ${total} ingested postings: ${tags
              .map((tag) => `${tag.label} ${tag.count}`)
              .join(", ")}.`
          : "Job pool category chart, awaiting data."
      }
    >
      {/* Two rings, not a quantitative grid.
          ------------------------------------------------------------------
          There were rings at 25 / 50 / 75% of the leading count, placed at
          sqrt(share) so each sat where a category holding that share would
          actually reach. Under the understated scale they no longer do: a
          category at a quarter of the leader now reaches 0.8R, so the ring
          marked "a quarter" would sit well inside the wedge it was measuring.
          Rings that misplace the value are worse than no rings, and rings
          re-placed correctly would bunch into the outer fifth of the radius
          and read as noise.

          So the chart keeps only the two radii that are true by construction:
          the floor every present category clears, and the edge the leader
          reaches. Everything drawn lives in the band between them, which is
          the honest statement of what this scale can and cannot show. */}
      <circle
        cx="140"
        cy="140"
        r={96 * UNDERSTATEMENT}
        fill="none"
        stroke="#E3E8F5"
        strokeWidth="1"
      />
      <circle cx="140" cy="140" r="96" fill="none" stroke="#DCE4F4" strokeWidth="1.5" />

      {/* Wireframe sectors: a wash of fill under a full-strength outline.
          ------------------------------------------------------------------
          This replaced a gradient-filled plate punched out by a mask, and it
          is both simpler and more honest. The gradient made colour a second
          encoding of reach, which meant a short wedge was drawn faintly as
          well as briefly — rarity read as absence. An outline does not fade:
          the smallest category gets exactly the same crisp edge as the
          largest, so reach is left to say the thing reach is supposed to say.

          `vector-effect="non-scaling-stroke"` is what makes that work. The
          sectors are sized by a transform, and without it the stroke would
          scale too — a wedge at 30% would be drawn with a 30% thinner line,
          reintroducing exactly the fading it is here to prevent.

          No mask, no gradient, no clip path: the gaps come from each sector
          being its own shape, so there is nothing left to carve. */}
      {SECTORS.map((d, i) => {
        const count = tags[i]?.count ?? 0;
        const dimmed = active !== null && active !== i;
        const focused = active === i;
        return (
          <path
            key={`fill-${d}`}
            d={d}
            fill="#1A5FEE"
            stroke="#1A5FEE"
            strokeWidth="1.5"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
            fillOpacity={focused ? 0.22 : dimmed ? 0.04 : 0.1}
            strokeOpacity={dimmed ? 0.25 : 1}
            style={{
              transformBox: "view-box",
              transformOrigin: "140px 140px",
              transform: `scale(${radiusFactor(count, peak)})`,
              transition:
                "transform 520ms cubic-bezier(0.16, 1, 0.3, 1), fill-opacity 180ms ease, stroke-opacity 180ms ease",
              // A small cascade so the five arrive as a set rather than
              // snapping together. Capped well under half a second total.
              transitionDelay: `${i * 70}ms, 0ms, 0ms`,
              pointerEvents: "none",
            }}
          />
        );
      })}

      {SECTORS.map((d, i) => (
        <path
          key={d}
          d={d}
          fill="transparent"
          onMouseEnter={() => tags[i] && setActive(i)}
          onMouseLeave={() => setActive(null)}
        />
      ))}
    </svg>
  );
}

function JpRows({
  tags,
  settled,
  setActive,
}: {
  tags: readonly Tag[];
  settled: boolean;
  setActive: (index: number | null) => void;
}) {
  if (tags.length === 0) {
    // Only while the request is in flight; see the note on the four states.
    return !settled ? (
      <ul className="space-y-1.5" aria-hidden="true">
        {Array.from({ length: 5 }, (_, index) => (
          <li key={index} className="grid grid-cols-[1fr,2.75rem] gap-2">
            <span className="h-3 animate-pulse rounded-chip bg-line/70" />
            <span className="h-3 animate-pulse rounded-chip bg-line/40" />
          </li>
        ))}
      </ul>
    ) : null;
  }

  return (
    <ul className="space-y-1.5">
      {tags.map((tag, index) => (
        <li
          key={tag.label}
          className="grid grid-cols-[1fr,2.75rem] items-center gap-2"
          onMouseEnter={() => setActive(index)}
          onMouseLeave={() => setActive(null)}
        >
          <span className="truncate text-label font-medium capitalize text-ink">{tag.label}</span>
          <span className="tabular text-right text-label text-ink-muted">{tag.count}</span>
        </li>
      ))}
    </ul>
  );
}

function JpStatus({
  tags,
  active,
  total,
  restingLine,
  lastRun,
}: {
  tags: readonly Tag[];
  active: number | null;
  total: number;
  restingLine: string;
  lastRun: string | null;
}) {
  return (
    <div className="relative h-10">
      <p
        role="status"
        aria-live="polite"
        className="absolute inset-x-0 top-0 text-label leading-relaxed text-ink-muted"
      >
        {active !== null && tags[active] ? (
          <>
            <span className="font-semibold text-ink">{tags[active]!.count}</span> of {total}{" "}
            postings are tagged <span className="capitalize">{tags[active]!.label}</span>.
          </>
        ) : (
          <>
            {restingLine}
            {lastRun && (
              <>
                {" · last run "}
                {relativeAge(lastRun)}
              </>
            )}
          </>
        )}
      </p>
    </div>
  );
}

export function JobPoolVisual() {
  const [stats, setStats] = useState<PoolStats | null>(null);
  const [settled, setSettled] = useState(false);
  const [active, setActive] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPoolStats().then((result) => {
      if (cancelled) return;
      setStats(result);
      setSettled(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const tags = stats?.top_tags ?? [];
  // Wedges are scaled against the biggest tag, not against the total. One
  // category holding a third of the pool would otherwise flatten every other
  // wedge to a sliver and the chart would read as broken rather than skewed.
  const peak = Math.max(1, ...tags.map((tag) => tag.count));
  const total = stats?.total_postings ?? 0;

  /* Four distinct states, deliberately worded so none can be mistaken for
     another. An empty pool used to render the same skeleton rows as the
     loading state, which said "still fetching" about a database that simply
     had nothing in it. */
  const restingLine = !settled
    ? "Reading the job pool…"
    : !stats
      ? "Pool snapshot unavailable — the API is not reachable from here."
      : total === 0
        ? "No postings ingested yet. Run the pipeline and this fills in."
        : `${total} postings · ${stats.sources.length} source${
            stats.sources.length === 1 ? "" : "s"
          } · ${stats.distinct_tags} categories`;

  return (
    <div className="space-y-3">
      <div className="grid items-center gap-5 sm:grid-cols-[8rem,1fr]">
        <JpChart tags={tags} peak={peak} active={active} setActive={setActive} total={total} />
        <JpRows tags={tags} settled={settled} setActive={setActive} />
      </div>
      <JpStatus
        tags={tags}
        active={active}
        total={total}
        restingLine={restingLine}
        lastRun={stats?.last_ingested_at ?? null}
      />
    </div>
  );
}
