import { Link } from "react-router-dom";

import { Logo } from "@/components/brand/Logo";
import { MatchVisual } from "@/components/landing/MatchVisual";
import { Card, CardBody } from "@/components/ui/Card";

/**
 * The public entry point.
 *
 * Marketing register: generous spacing, one idea per section. The product
 * register at /app/* is deliberately denser, because ranked lists are the
 * product and whitespace there costs the user scrolling.
 *
 * The CTA goes to /app/upload rather than a dashboard: landing a first-time
 * visitor on an empty dashboard is an empty state pretending to be a product.
 */

const PIPELINE = [
  {
    step: "01",
    title: "Ingest",
    body: "Postings are pulled from Arbeitnow, Wuzzuf and a MENA source, normalised to one schema and deduplicated on a deterministic id, so the same job never lands twice.",
  },
  {
    step: "02",
    title: "Embed",
    body: "Each posting becomes a vector in Qdrant. Embeddings whose posting has been deleted are pruned on every run, so the index and the database cannot drift apart.",
  },
  {
    step: "03",
    title: "Retrieve",
    body: "Your profile is embedded the same way and used to pull the closest postings. Cheap, fast, and it happens over the whole collection rather than a filtered slice.",
  },
  {
    step: "04",
    title: "Re-rank",
    body: "An LLM re-reads that shortlist and reorders it on reasoning an embedding cannot capture: seniority fit, whether one skill substitutes for another.",
  },
  {
    step: "05",
    title: "Explain",
    body: "Every returned job gets a written explanation with matched skills and real gaps, scored against the requirements actually in the posting.",
  },
];

const CAPABILITIES = [
  {
    title: "Reads your actual CV",
    body: "Upload a PDF or DOCX and the parser extracts a structured profile. Correct anything it gets wrong in the form, or just tell the assistant in plain language.",
    accent: "brand" as const,
  },
  {
    title: "Explains its ranking",
    body: "Not a similarity score in isolation. Each match carries strengths, gaps and next steps, so you can tell a near miss from a real fit.",
    accent: "teal" as const,
  },
  {
    title: "Finds new postings",
    body: "Triggering a run ingests fresh jobs before matching, so the pool grows. Results change when the sources publish something better, not because they were shuffled.",
    accent: "amber" as const,
  },
];

export function LandingPage() {
  return (
    <div className="min-h-dvh bg-surface">
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-content items-center justify-between px-4 py-4 sm:px-6">
          <Logo />
          <Link
            to="/app/upload"
            className="inline-flex h-10 items-center rounded-control bg-brand px-4 text-sm font-semibold text-white shadow-raised transition-colors duration-state ease-enter hover:bg-brand-deep"
          >
            Get started
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section className="bg-surface-hero">
        <div className="mx-auto grid max-w-content gap-12 px-4 py-16 sm:px-6 lg:grid-cols-2 lg:items-center lg:py-24">
          <div className="animate-fade-rise">
            <span className="inline-flex items-center rounded-chip bg-surface px-3 py-1 text-sm font-semibold text-brand shadow-raised">
              AI Career Coach
            </span>
            <h1 className="mt-5 text-4xl font-extrabold leading-[1.1] tracking-tight text-ink sm:text-5xl">
              Find the jobs you actually fit,{" "}
              <span className="text-brand-bright">and why.</span>
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-ink-muted">
              Upload your CV once. Every match comes back ranked, with the
              matched skills, the real gaps and what to do about them, drawn from
              the requirements in the posting itself.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                to="/app/upload"
                className="inline-flex h-12 items-center rounded-control bg-brand px-6 font-semibold text-white shadow-raised transition-colors duration-state ease-enter hover:bg-brand-deep"
              >
                Upload your CV
              </Link>
              <a
                href="#how-it-works"
                className="inline-flex h-12 items-center rounded-control border border-line bg-surface px-6 font-semibold text-ink transition-colors duration-state ease-enter hover:border-brand hover:text-brand"
              >
                How it works
              </a>
            </div>
          </div>

          {/* The signature: the same visualization the match screen uses. One
              element serves both registers, which avoids the big-number-and-a-
              gradient hero that every AI-assisted landing page converges on. */}
          <Card className="animate-fade-rise">
            <CardBody>
              <p className="mb-5 text-sm font-semibold uppercase tracking-wide text-ink-muted">
                Sample fit profile
              </p>
              <MatchVisual />
            </CardBody>
          </Card>
        </div>
      </section>

      {/* Capabilities */}
      <section className="mx-auto max-w-content px-4 py-16 sm:px-6">
        <div className="grid gap-5 md:grid-cols-3">
          {CAPABILITIES.map((item) => (
            <Card key={item.title} accent={item.accent}>
              <CardBody>
                <h2 className="text-lg font-bold text-ink">{item.title}</h2>
                <p className="mt-2 text-sm leading-relaxed text-ink-muted">{item.body}</p>
              </CardBody>
            </Card>
          ))}
        </div>
      </section>

      {/* Pipeline */}
      <section id="how-it-works" className="bg-surface-sunken">
        <div className="mx-auto max-w-content px-4 py-16 sm:px-6">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-3xl font-extrabold tracking-tight text-ink">
              How the pipeline works
            </h2>
            <p className="mt-3 text-ink-muted">
              Five stages, each one doing a job the next depends on. Nothing here
              is a mock.
            </p>
          </div>

          <ol className="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {PIPELINE.map((stage) => (
              <li key={stage.step}>
                <Card className="h-full">
                  <CardBody>
                    <span className="tabular text-sm font-bold text-brand">{stage.step}</span>
                    <h3 className="mt-1 text-lg font-bold text-ink">{stage.title}</h3>
                    <p className="mt-2 text-sm leading-relaxed text-ink-muted">{stage.body}</p>
                  </CardBody>
                </Card>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Docs */}
      <section className="mx-auto max-w-content px-4 py-16 sm:px-6">
        <div className="mx-auto max-w-3xl">
          <h2 className="text-2xl font-extrabold tracking-tight text-ink">Running it locally</h2>
          <p className="mt-3 text-ink-muted">
            Both databases are local. SQLite is created on startup and Qdrant
            runs embedded by default, so neither needs setting up.
          </p>

          <ol className="mt-6 space-y-4">
            {[
              ["Install", "pip install -r requirements.txt"],
              ["Configure", "cp .env.example .env, then paste the group LiteLLM key into .env"],
              ["Start the API", "uvicorn backend.main:app --reload"],
              ["Start the UI", "cd frontend && npm install && npm run dev"],
            ].map(([label, command], index) => (
              <li key={label} className="flex gap-4">
                <span className="tabular grid h-8 w-8 shrink-0 place-items-center rounded-full bg-brand/[0.08] text-sm font-bold text-brand">
                  {index + 1}
                </span>
                <div className="min-w-0">
                  <p className="font-semibold text-ink">{label}</p>
                  <code className="mt-1 block overflow-x-auto rounded-control bg-surface-sunken px-3 py-2 font-mono text-sm text-ink-muted">
                    {command}
                  </code>
                </div>
              </li>
            ))}
          </ol>

          <p className="mt-6 text-sm text-ink-muted">
            One constraint worth knowing: embedded Qdrant takes an exclusive
            single-process lock, so stop the backend before running the seed or
            verify scripts. Set <code className="font-mono">QDRANT_MODE=server</code> and run{" "}
            <code className="font-mono">docker compose up -d qdrant</code> if that gets annoying.
          </p>
        </div>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-content flex-wrap items-center justify-between gap-4 px-4 py-8 sm:px-6">
          <Logo className="h-6" />
          <p className="text-sm text-ink-muted">
            Built during the Sprints virtual internship.
          </p>
        </div>
      </footer>
    </div>
  );
}
