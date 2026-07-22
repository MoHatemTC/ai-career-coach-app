# Product Requirements Document (PRD)
## AI-Powered Career Coach

| | |
|---|---|
| **Product (working title)** | Sprints Career Coach |
| **Document type** | Product Requirements Document (PRD) |
| **Version** | v1.0 (Draft) |
| **Owner** | Program / Product Lead |
| **Builders** | Internship cohort (fresh graduates & junior professionals) |
| **Status** | Draft for review |

---

## 1. Overview

### 1.1 Summary
The Sprints Career Coach is an AI-powered assistant that helps job seekers — primarily learners completing their Sprints journey — move from *"I finished my training"* to *"I got a relevant job."* The user uploads their CV and career preferences; the system analyzes their profile, pulls relevant job postings from one or two sources, ranks the best matches, explains why each job fits (or doesn't), highlights missing skills, and helps prepare tailored application materials (an optimized CV summary, skills highlights, and a cover letter). It notifies users of new relevant openings by email and monitors similar jobs daily so learners stay aligned with what the market is actually asking for.

### 1.2 Vision
Bridge the gap between finishing a learning program and landing a role by giving every learner a personal, always-on career assistant that (a) surfaces the right jobs fast, (b) shows exactly where their profile is strong or weak, and (c) keeps their skills current with live market demand.

### 1.3 Why now
Job seekers — especially fresh graduates, junior professionals, and career shifters — spend enormous effort finding relevant jobs, judging fit, identifying skill gaps, and rewriting their CV and cover letter for each application. AI and lightweight automation can collapse hours of manual work into minutes, while continuous market monitoring keeps the learner's skill roadmap honest.

---

## 2. Problem Statement

Job seekers consistently struggle to:
- Find relevant jobs quickly across scattered sources.
- Understand which jobs actually match their profile.
- Know which skills they are missing for a target role.
- Tailor their CV for each specific job.
- Write strong, role-specific cover letters.
- Track which jobs they have already reviewed or applied to.
- Keep up with shifting market trends and in-demand skills.

The result is wasted effort, low application quality, missed opportunities, and skill roadmaps that drift out of sync with what employers want.

---

## 3. Goals & Objectives

### 3.1 Product goals
1. **Reduce time-to-relevant-jobs** — surface a ranked shortlist instead of forcing manual searching.
2. **Improve match quality** — recommend jobs that genuinely fit the user's profile and goals.
3. **Make fit transparent** — explain *why* each job is a strong or weak match.
4. **Close skill gaps** — identify missing skills and keep the user aligned with market demand.
5. **Accelerate applications** — generate tailored CV summaries, skills highlights, and cover letters with human verification.
6. **Keep users engaged** — notify them of new relevant jobs automatically.

### 3.2 Learning objectives (for the internship team)
Build a working AI product while practicing: Python, APIs, JSON, and file handling; LLM APIs (OpenAI / Gemini); prompt engineering for profile analysis and job matching; CV and job-data processing; a simple automation workflow; email notifications; responsible AI with human verification; and professional engineering practices (GitHub, documentation, modular code, team collaboration), culminating in a final demo.

### 3.3 Success is *not*
- Auto-applying to jobs on the user's behalf.
- Replacing human judgment — all AI-generated materials require user review before use.

---

## 4. Target Users & Personas

| Persona | Profile | Primary need |
|---|---|---|
| **Fresh graduate** | Just completed a degree or bootcamp; little to no professional experience. | Find entry-level roles and understand what they lack. |
| **Junior professional** | 0–2 years of experience; wants to level up or find a better-fit role. | Filter noise; target roles that match their growing skills. |
| **Career shifter** | Transitioning into a new field (e.g., marketing → data). | Understand transferable skills and the gap to the new field. |

All three are supported by the same core flows; differences show up mainly in skill-gap analysis and match explanations.

---

## 5. Scope

### 5.1 In scope (v1)
- CV upload and parsing (PDF / DOCX).
- Structured profile intake (target roles, locations, experience level, skills, salary expectations, work type, career goals).
- Job ingestion from **one or two** job-posting sources via API (or a provided dataset).
- AI-powered matching and ranking of jobs to the profile.
- Match explanations (strong/weak fit reasoning).
- Skill-gap analysis against target roles and live market data.
- Application material generation: optimized CV summary, skills highlights, cover letter.
- Email notifications for new relevant jobs.
- Application tracking (reviewed / saved / applied status).
- Daily monitoring of similar jobs for market-trend awareness.

### 5.2 Out of scope (v1)
- Automatically submitting applications.
- Interview preparation / mock interviews.
- Salary negotiation coaching.
- Native mobile app.
- Scraping sources whose Terms of Service prohibit it (e.g., LinkedIn scraping).
- Payments / subscriptions.
- Multi-language generation beyond the primary language (stretch goal only).

---

## 6. User Flows

### 6.1 Onboarding
1. User uploads CV → system parses it into structured fields.
2. User completes/edits their profile (roles, location, experience, skills, salary, work type, goals).
3. System confirms the profile and shows an initial skill snapshot.

### 6.2 Job matching (on-demand + daily)
1. System pulls fresh postings from the configured source(s).
2. Matching engine scores and ranks jobs against the profile.
3. User sees a ranked shortlist, each with a fit score and a short explanation.

### 6.3 Application preparation
1. User selects a job.
2. System generates a tailored CV summary, skills highlights, and a cover letter.
3. User reviews, edits, and approves the materials before use.

### 6.4 Notification
1. Daily job (scheduler / automation) runs matching for each active user.
2. New relevant jobs above a threshold trigger an email digest.
3. User opens the email and reviews new matches.

---

## 7. Functional Requirements

Requirements use **MoSCoW** priority: (M) Must, (S) Should, (C) Could.

### 7.1 Profile & Onboarding
- (M) Capture target roles, preferred locations, experience level, skills, salary expectations, work type, and career goals.
- (M) Allow the user to edit any field parsed from the CV.
- (S) Store multiple target roles per user.

### 7.2 CV Processing
- (M) Accept PDF and DOCX uploads and extract text.
- (M) Extract structured fields: skills, experience, education, job titles.
- (S) Flag low-quality or unparseable CVs and ask the user to fix input.
- (C) Support plain-text paste as an alternative to file upload.

### 7.3 Job Ingestion
- (M) Pull postings from **one or two** approved, ToS-compliant sources via API (or a provided dataset for development).
- (M) Normalize each posting into a consistent JSON schema (title, company, location, description, skills, salary if available, source, URL, date).
- (S) De-duplicate postings across runs.
- (C) Cache raw responses to reduce API cost and rate-limit pressure.

### 7.4 Matching & Ranking Engine
- (M) Score each job against the profile and produce a ranked shortlist.
- (M) Combine structured signals (skills overlap, location, experience, work type, salary) with LLM-based semantic matching.
- (S) Expose a configurable relevance threshold for notifications.
- (C) Let users give feedback (thumbs up/down) to improve future ranking heuristics.

### 7.5 Match Explanation
- (M) For each recommended job, explain in plain language why it is a strong or weak match.
- (M) Reference specific profile elements (e.g., "strong on Python, missing SQL").

### 7.6 Skill-Gap Analysis
- (M) Compare the user's skills against target roles and current matched jobs.
- (M) Produce a prioritized list of missing / underdeveloped skills.
- (S) Aggregate demand across daily-monitored jobs to show trending skills for the user's target roles.

### 7.7 Application Material Generation
- (M) Generate an optimized CV summary tailored to a selected job.
- (M) Generate skills highlights relevant to the selected job.
- (M) Generate a tailored cover letter.
- (M) Require explicit user review/approval; never present AI output as final without human verification.
- (S) Allow regeneration with user-provided guidance.

### 7.8 Notifications
- (M) Send an email digest of new relevant jobs.
- (S) Let the user set frequency (e.g., daily / weekly) and relevance threshold.
- (C) Include a one-line reason per job in the email.

### 7.9 Application Tracking
- (M) Track job status per user: reviewed, saved, applied.
- (S) Prevent re-notifying about jobs already reviewed or applied to.

### 7.10 Market Monitoring
- (M) Run a daily job that fetches and analyzes similar jobs for each active user's target roles.
- (S) Surface trending in-demand skills and how the user's profile compares over time.

---

## 8. AI & Prompt Engineering Requirements

| AI capability | Purpose | Output |
|---|---|---|
| Profile analysis | Interpret CV + inputs into a structured profile | JSON profile |
| Job matching | Semantic fit between profile and postings | Score + rationale |
| Match explanation | Human-readable fit reasoning | Short text per job |
| Skill-gap analysis | Identify missing/weak skills | Prioritized skill list |
| Material generation | CV summary, skills highlights, cover letter | Draft text (for review) |

Requirements:
- (M) Prompts must request **structured JSON** where the output feeds the UI or downstream logic.
- (M) Responses must be safely parsed with error handling and fallbacks.
- (M) Prompts must instruct the model **not to fabricate** experience, skills, or achievements the user does not have.
- (S) Keep prompts modular and versioned so they can be iterated without touching application code.
- (S) Track token usage / cost per call.

---

## 9. Responsible AI Requirements

- (M) **Human-in-the-loop**: all generated application materials require user review and approval before use.
- (M) **No fabrication**: the assistant must not invent qualifications, dates, or achievements.
- (M) **Transparency**: match scores must come with explanations, not opaque numbers.
- (M) **Fairness**: matching and recommendations must not discriminate on protected characteristics (gender, age, nationality, etc.); avoid signals that could encode bias.
- (M) **Privacy & PII**: CVs contain sensitive personal data — store securely, limit retention, and obtain user consent for processing.
- (S) **Hallucination guards**: validate that generated skills/claims trace back to the user's actual profile.
- (S) **User control**: allow users to delete their data and stored materials.

---

## 10. Technical Requirements & Architecture

### 10.1 Suggested stack
- **Language**: Python.
- **LLM API**: OpenAI or Gemini (pick one; keep the interface abstracted).
- **Job data**: one or two ToS-compliant job APIs (e.g., a public jobs API with a free tier (Wuzzuf)). For MENA-focused learners, prioritize sources with regional coverage plus remote roles.
- **Data handling**: JSON as the interchange format; PostgreSQL for database.
- **File handling**: PDF/DOCX parsing libraries for CV extraction.
- **Automation**: a scheduler (cron / APScheduler).
- **Email**: SMTP or a transactional email API (e.g., SendGrid).
- **Frontend**: a lightweight UI (Streamlit / Flask) or a CLI for v1 — (Bonus: build a React frontend app and connect it with FastAPI).
- **Version control & collaboration**: GitHub with modular code and documentation.

### 10.2 High-level components
1. **Ingestion service** — fetches and normalizes job postings.
2. **Profile service** — parses CVs and manages user profiles.
3. **AI/matching service** — scoring, explanations, skill gaps, material generation.
4. **Automation & notification service** — scheduled matching + email digests.
5. **Storage layer** — users, profiles, jobs, matches, applications, notifications.
6. **UI layer** — profile intake, shortlist, application prep, tracking.

### 10.3 Core data entities
`User`, `Profile`, `CV`, `JobPosting`, `Match` (job + score + explanation), `Application` (status), `Notification`, `Skill`.

---

## 11. Non-Functional Requirements

- **Reliability**: graceful handling of API failures, empty results, and rate limits.
- **Cost control**: cache job data; batch LLM calls where possible; monitor token spend.
- **Performance**: on-demand matching returns a shortlist within a reasonable interactive time.
- **Security**: protect PII; no secrets in the repo; use environment variables for API keys.
- **Maintainability**: modular code, clear separation of concerns, meaningful commits.
- **Documentation**: README, setup guide, architecture notes, and prompt documentation.

---

## 12. Success Metrics

### 12.1 Product metrics
| Metric | What it measures |
|---|---|
| Match relevance rating | User-rated quality of recommended jobs |
| Time-to-shortlist | How fast a user gets relevant matches |
| Skill gaps surfaced | Coverage and usefulness of gap analysis |
| Materials generated & used | Adoption of AI-drafted CV/cover letters |
| Notification engagement | Email open / click-through on job digests |
| Applications tracked | Jobs moved to "applied" |

### 12.2 Internship success criteria
Working end-to-end app; clean GitHub repo with documentation; demonstrated use of Python, APIs, JSON, file handling, LLM prompting, automation, and email notifications; responsible AI practices applied; and a polished final demo.

---

## 13. Milestones (Sprint Plan)

The whole project runs across **four sprints**, with setup folded into Sprint 1.

| Sprint | Focus | Key outputs |
|---|---|---|
| **Sprint 1** | Setup, Profile & CV | Repo, roles, stack decisions, API keys, data source chosen; CV upload/parsing; profile intake; profile JSON |
| **Sprint 2** | Ingestion & Matching | Job ingestion, normalized schema, matching & ranking engine, ranked shortlist, match explanations |
| **Sprint 3** | Intelligence & Materials | Skill-gap analysis; application material generation (CV summary, skills highlights, cover letter — with review) |
| **Sprint 4** | Automation, Polish & Demo | Scheduler workflow, email digests, application tracking, testing, documentation, responsible-AI review, final demo |

---

## 14. Team Roles (Internship)

Every team member is an **AI Engineer**. The team shares full ownership of the AI product; the areas below indicate primary ownership so nothing falls through the cracks — not separate job titles. Ownership can rotate across sprints.

- **AI Engineer — Product & Delivery (rotating)** — owns the PRD, backlog, and demo narrative.
- **AI Engineer — Matching & Generation** — matching, explanations, material generation, prompt iteration.
- **AI Engineer — Backend & Integration** — job APIs, data normalization, storage, automation.
- **AI Engineer — CV & Data Processing** — parsing, profile extraction, skill mapping.
- **AI Engineer — Frontend & UX** — intake, shortlist, application-prep, tracking UI.
- **AI Engineer — QA & Documentation** — testing, README, responsible-AI checklist.

On a small team these areas overlap; the point is clear ownership per area while everyone contributes as an AI Engineer across the codebase.

---

## 15. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Job-source ToS / scraping legality | Use only API-based or approved dataset sources; document the source. |
| LLM hallucination in materials | Human review required; prompts forbid fabrication; validate claims against profile. |
| API cost / rate limits | Cache data, batch calls, monitor usage, use free tiers during development. |
| PII / data privacy | Secure storage, consent, retention limits, deletion support. |
| Poor CV parsing | Validate parsed output; let users correct fields. |
| Scope creep | Enforce v1 scope; defer stretch goals to a backlog. |

---

## 16. Assumptions & Dependencies

- Users can provide a CV in PDF or DOCX and basic career inputs.
- At least one ToS-compliant job source (API or dataset) is available.
- LLM API access (OpenAI / Gemini) is provisioned.
- Email sending is available (SMTP or a transactional email provider).
