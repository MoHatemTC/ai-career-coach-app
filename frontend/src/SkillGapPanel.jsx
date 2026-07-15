/**
 * SkillGapPanel
 *
 * Purpose (PRD Section 7.6, docs/architecture.md "Frontend ... Showing
 * skill gaps"): renders the result of a skill-gap analysis - matched
 * skills, and a prioritized list of missing skills with the reason for
 * each (Responsible AI - Transparency, PRD Section 9: never show an
 * opaque score/list without an explanation).
 *
 * Notes on tech choices (Sprint 1):
 * - Plain .jsx, not .tsx: this repo has no TypeScript build configured
 *   yet (no tsconfig.json, no @types packages in this scaffold). The
 *   task brief asked for a .tsx file, but introducing TypeScript
 *   tooling is a repo-wide/frontend-infra decision, not something a
 *   single feature lane should do unilaterally (CONTRIBUTING.md: "Do
 *   not modify shared core", and there is no shared frontend build
 *   config to extend here yet). If/when the team adopts TypeScript,
 *   this file can be renamed/typed with no logic changes since props
 *   are already documented via PropTypes-style comments below.
 * - No UI framework assumed (no shared design system exists yet in
 *   this scaffold) - plain semantic HTML + minimal inline-friendly
 *   class names so this drops into whatever the frontend lane sets up.
 * - Data fetching is injected via a `fetchSkillGap` prop (defaulting to
 *   a real fetch call against `/skill-gap/analyze`) so this component
 *   is testable without a running backend and doesn't hard-code API
 *   base URLs (those belong in `frontend/src/api/`, per
 *   docs/architecture.md).
 *
 * Props:
 *   userId          (string, required) - profile owner.
 *   targetRole       (string) - role label shown in the header.
 *   skills           (string[]) - raw skills held by the user.
 *   jobPostingsSkills (string[][]) - optional, raw skills per job
 *                      posting used as the demand signal.
 *   requiredSkills   (string[]) - optional explicit override, used
 *                      instead of jobPostingsSkills.
 *   fetchSkillGap    (function) - optional override for the API call,
 *                      mainly for tests/storybook. Defaults to calling
 *                      POST /skill-gap/analyze.
 */

import { useEffect, useState } from "react";

async function defaultFetchSkillGap({
  userId,
  targetRole,
  skills,
  jobPostingsSkills,
  requiredSkills,
}) {
  const response = await fetch("/skill-gap/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      target_role: targetRole,
      skills,
      job_postings_skills: jobPostingsSkills ?? null,
      required_skills: requiredSkills ?? null,
    }),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Skill gap request failed (${response.status}): ${detail}`);
  }

  return response.json();
}

export default function SkillGapPanel({
  userId,
  targetRole,
  skills = [],
  jobPostingsSkills = null,
  requiredSkills = null,
  fetchSkillGap = defaultFetchSkillGap,
}) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;

    if (!userId || (!jobPostingsSkills && !requiredSkills)) {
      // Nothing to analyze yet (e.g. onboarding not finished, or no
      // matched jobs yet) - render the empty state instead of calling
      // the API with an incomplete request.
      setResult(null);
      setError(null);
      return undefined;
    }

    setLoading(true);
    setError(null);

    fetchSkillGap({ userId, targetRole, skills, jobPostingsSkills, requiredSkills })
      .then((data) => {
        if (!cancelled) setResult(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "Failed to load skill gap.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [userId, targetRole, skills, jobPostingsSkills, requiredSkills, fetchSkillGap]);

  if (loading) {
    return (
      <section className="skill-gap-panel" aria-busy="true">
        <p>Analyzing skill gap...</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="skill-gap-panel skill-gap-panel--error" role="alert">
        <p>Couldn&apos;t load your skill gap analysis: {error}</p>
      </section>
    );
  }

  if (!result) {
    return (
      <section className="skill-gap-panel skill-gap-panel--empty">
        <p>Add a target role and at least one matched job to see your skill gap.</p>
      </section>
    );
  }

  const { matched_skills: matchedSkills, gaps } = result;

  return (
    <section className="skill-gap-panel">
      <h2>Skill Gap: {result.target_role || "Target role"}</h2>

      <div className="skill-gap-panel__matched">
        <h3>Skills you already have that match</h3>
        {matchedSkills.length === 0 ? (
          <p>No overlapping skills found yet.</p>
        ) : (
          <ul>
            {matchedSkills.map((skill) => (
              <li key={skill}>{skill}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="skill-gap-panel__gaps">
        <h3>Missing / underdeveloped skills, in priority order</h3>
        {gaps.length === 0 ? (
          <p>No gaps found - your profile covers the required skills.</p>
        ) : (
          <ol>
            {gaps.map((gap) => (
              <li key={gap.skill}>
                <strong>{gap.skill}</strong>
                {gap.category ? <span className="skill-gap-panel__category"> ({gap.category})</span> : null}
                <p className="skill-gap-panel__reason">{gap.reason}</p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
