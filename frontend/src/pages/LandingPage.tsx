import { Link } from "react-router-dom";

import { Logo } from "@/components/brand/Logo";
import { MatchVisual } from "@/components/landing/MatchVisual";

/**
 * The public entry point.
 *
 * Marketing register: wide, generous, one idea per band. The product register
 * at /app/* is deliberately denser, because ranked lists are the product and
 * whitespace there costs the user scrolling.
 *
 * The CTA goes to /app/upload rather than a dashboard: landing a first-time
 * visitor on an empty dashboard is an empty state pretending to be a product.
 *
 * Setup instructions deliberately live in README.md, not here. A landing page
 * carrying pip commands reads as a scaffold rather than a product.
 */

const STAGES = [
  {
    title: "Ingest",
    body: "Postings pulled from multiple boards, normalised to one schema and deduplicated on a deterministic id, so the same job never lands twice.",
  },
  {
    title: "Embed",
    body: "Each posting becomes a vector. Embeddings whose posting is gone are pruned on every run, so the index and the database cannot drift apart.",
  },
  {
    title: "Retrieve",
    body: "Your profile is embedded the same way and used to pull the closest postings, across the whole collection rather than a filtered slice.",
  },
  {
    title: "Re-rank",
    body: "A language model re-reads that shortlist and reorders it on reasoning a vector cannot capture: seniority fit, whether one skill substitutes for another.",
  },
  {
    title: "Explain",
    body: "Every job returned carries matched skills and real gaps, scored against the requirements actually written in the posting.",
  },
];

export function LandingPage() {
  return (
    <div className="min-h-dvh bg-surface">
      <header className="sticky top-0 z-20 border-b border-line/60 bg-surface/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-content items-center justify-between px-6 py-4 lg:px-10">
          <Logo />
          <Link
            to="/app/upload"
            className="inline-flex h-10 items-center rounded-control bg-brand px-5 text-sm font-semibold text-white transition-all duration-state ease-enter hover:bg-brand-deep hover:shadow-lifted"
          >
            Get started
          </Link>
        </div>
      </header>

      {/* Hero. Asymmetric on purpose: a 50/50 split with a card on the right is
          the layout every template ships with. */}
      <section className="relative overflow-hidden border-b border-line/60 bg-surface-hero">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-40 -top-40 h-[36rem] w-[36rem] rounded-full bg-brand/[0.07] blur-3xl"
        />
        <div className="relative mx-auto max-w-content px-6 py-20 lg:px-10 lg:py-28">
          <div className="grid items-center gap-16 lg:grid-cols-12">
            <div className="lg:col-span-7">
              <h1 className="text-display font-extrabold text-ink">
                Find the jobs you
                <br />
                actually fit,{" "}
                <span className="bg-gradient-to-r from-brand to-brand-bright bg-clip-text text-transparent">
                  and why.
                </span>
              </h1>
              <p className="mt-7 max-w-prose text-lead text-ink-muted">
                Upload your CV once. Every match comes back ranked, with the
                skills you have, the ones you are missing, and what to do about
                them, drawn from the requirements in the posting itself.
              </p>
              <div className="mt-10 flex flex-wrap items-center gap-4">
                <Link
                  to="/app/upload"
                  className="inline-flex h-13 items-center rounded-control bg-brand px-7 text-base font-semibold text-white shadow-raised transition-all duration-state ease-enter hover:bg-brand-deep hover:shadow-lifted"
                  style={{ height: "3.25rem" }}
                >
                  Upload your CV
                </Link>
                <a
                  href="#pipeline"
                  className="text-base font-semibold text-ink-muted underline-offset-4 transition-colors duration-state hover:text-brand hover:underline"
                >
                  See how it works
                </a>
              </div>
            </div>

            {/* The signature: the same visualization the match screen uses. One
                element serves both registers, which avoids the big-number-and-
                a-gradient hero every AI-assisted landing page converges on. */}
            <div className="lg:col-span-5">
              <div className="rounded-card border border-line/70 bg-surface/80 p-8 shadow-lifted backdrop-blur-sm">
                <MatchVisual />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Value, as prose rather than three identical cards. */}
      <section className="mx-auto max-w-content px-6 py-24 lg:px-10">
        <div className="grid gap-x-16 gap-y-14 md:grid-cols-3">
          {[
            [
              "It reads your actual CV",
              "A PDF or DOCX becomes a structured profile. Correct anything the parser got wrong in the form, or just tell the assistant in plain language and it updates.",
            ],
            [
              "It explains the ranking",
              "Not a similarity score in isolation. Each match carries strengths, gaps and next steps, so you can tell a near miss from a real fit before applying.",
            ],
            [
              "It keeps finding new work",
              "Each run ingests fresh postings before matching, so the pool grows. Results change when the sources publish something better, not because they were shuffled.",
            ],
          ].map(([title, body]) => (
            <div key={title}>
              <div className="mb-5 h-px w-12 bg-brand" />
              <h2 className="text-subtitle font-bold text-ink">{title}</h2>
              <p className="mt-3 leading-relaxed text-ink-muted">{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Pipeline, as a horizontal progression rather than a card grid. */}
      <section id="pipeline" className="border-y border-line/60 bg-surface-sunken">
        <div className="mx-auto max-w-content px-6 py-24 lg:px-10">
          <h2 className="max-w-prose text-title font-extrabold text-ink">
            Five stages between a CV and a shortlist you can trust.
          </h2>

          <ol className="mt-14 grid gap-px overflow-hidden rounded-card border border-line/70 bg-line/70 md:grid-cols-5">
            {STAGES.map((stage, index) => (
              <li key={stage.title} className="bg-surface p-7">
                <span className="tabular text-sm font-bold text-brand">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <h3 className="mt-2 text-lg font-bold text-ink">{stage.title}</h3>
                <p className="mt-2.5 text-sm leading-relaxed text-ink-muted">{stage.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Close */}
      <section className="mx-auto max-w-content px-6 py-28 text-center lg:px-10">
        <h2 className="mx-auto max-w-prose text-title font-extrabold text-ink">
          Stop guessing which roles are worth the application.
        </h2>
        <Link
          to="/app/upload"
          className="mt-10 inline-flex items-center rounded-control bg-brand px-8 text-base font-semibold text-white shadow-raised transition-all duration-state ease-enter hover:bg-brand-deep hover:shadow-lifted"
          style={{ height: "3.25rem" }}
        >
          Upload your CV
        </Link>
      </section>

      <footer className="border-t border-line/60">
        <div className="mx-auto flex max-w-content flex-wrap items-center justify-between gap-4 px-6 py-10 lg:px-10">
          <Logo className="h-6" />
          <p className="text-sm text-ink-muted">AI Career Coach</p>
        </div>
      </footer>
    </div>
  );
}
