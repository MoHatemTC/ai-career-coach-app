# CV Parsing & Job Matching — End-to-End Quality Testing Report

**Tester:** Ramez Emad
**Task:** Run the full CV → parsing → job matching flow across multiple CVs, monitor parsing quality and retrieved job relevance.
**Database status:** Seeded via `seed_qdrant.py` (Arbeitnow + Wuzzuf sources), ~180 jobs at time of testing.
**Test period:** August 2026
**Trials logged:** 20

---

## Summary Table

| # | CV Name | Category | Years Exp. | Parsed Correctly? | Jobs Returned Relevant? | Key Issue |
|---|---|---|---|---|---|---|
| 1 | Ahmed Mostafa | Backend Dev | 4y | Yes | Partial | 1 strong match, 1 vague, 1 off-domain (Sales required) |
| 2 | Sara Hassan | Frontend Dev | 3y | Yes | Partial | 1 good match, 2 off-domain (DSP, grad role) |
| 3 | Yasmin Adly | Marketing Coordinator (rambling CV) | ~1y | Yes | No | Rambling text parsed fine; matches are senior/student/wrong-field roles |
| 4 | Peter Nabil | HR Specialist | ~2y | Yes | No | No semantic matching; over-qualification not filtered |
| 5 | Omar Khaled | Full Stack Dev | 6y | Yes | Partial | Broken/mismatched URL on one result |
| 6 | Ahmed Zaki | Sales Executive (rambling CV) | ~1y | Yes | No | No semantic match (cold calling not recognized as sales); exp. years ignored |
| 7 | Mona Adel | DevOps Engineer | 7y | Yes | No | Wrong country matches; no semantic match on "Engineering"; 1 job is Pre-Sales, not DevOps |
| 8 | Farida Kamal | Graphic Designer (rambling CV) | ~1.5y | Yes | No | Exp. years not qualified; false missing skills; no semantic match |
| 9 | Youssef Ibrahim | Data Engineer | 3y | Yes | No | Same recurring issues as above |
| 10 | Mariam Fathy | Junior Accountant (rambling CV) | ~1y | Yes | No | False missing skills (MS Office vs Excel treated as gap); wrong location/domain |
| 11 | Nadia Cherkaoui | Data Engineering Lead (Morocco, senior) | 14y | Yes | No | No semantic match |
| 12 | Faisal Al-Otaibi | Principal Backend Eng. (Saudi, senior) | 15y | Yes | Partial | 1 strong (95%+) match, 2 same-company duplicate-style listings |
| 13 | Daniel Whitfield | VP of Engineering (UK, senior) | 15y | Partial | No | Seniority mismatch — VP matched to Engineering Manager / IC roles; title field blank |
| 14 | Ines Bouazizi | Senior Cloud/DevOps Architect (Tunisia) | 13y | Partial | No | Same "Engineering"/"Tech" generic-skill mismatch pattern; title truncated |
| 15 | Rami Haddad | Senior Software Architect (Lebanon) | 16y | Yes | No | Matched to Sales-oriented / generic "Tech" roles, no seniority match |
| 16 | Hoda El-Sayed | Senior Marketing Manager (rambling CV) | 18y | Yes | Partial | 1 reasonable match, false "0 matched skills" despite clear overlap |
| 17 | Tarek Moussa | HR Director (rambling CV) | 19y | Partial | No | Same false-missing-skill pattern; title field blank |
| 18 | Samir Georges | Finance Manager (rambling CV) | 17y | Yes | Partial | High scores (72-78%) despite 0 matched skills reported — score/explanation inconsistency |
| 19 | Nermeen Adel | Operations Manager (rambling CV) | 20y | Partial | No | Same false-missing-skill pattern; title field blank |
| 20 | Mahmoud El-Gendy | Senior School Principal (rambling CV) | 21y | Yes | No | Education-sector CV matched to HR/corporate/biotech roles — no domain match at all |

**Parsing:** 20/20 trials extracted name, skills, experience, and education correctly — including from deliberately messy/rambling CVs. Three trials (#13, #17, #19) showed a specific, repeatable gap: the "Current/target title" field came back blank for senior/director-level titles.

**Matching:** Only about 4 of 20 trials returned a genuinely strong, relevant top match. The rest show a consistent, repeatable set of problems (detailed below).

---

## Trial Detail

### Trial 1 — Ahmed Mostafa (Backend Developer, Cairo, Egypt, 4y exp, grad 2019)

**Parsing:** Correct — name, skills, experience, education all extracted with no issues.

**Jobs matched:**
1. Backend Software Engineer @ Desert AI (Dubai, UAE) — 95.0% — strong, all required skills matched
2. Senior Software Engineer @ Nmi (Remote) — 85.0% — required skill "Product Engineering", vague/unmatched
3. Staff Solutions Architect (EMEA) @ Docker (England) — 58% — required skill "Sales", clear domain mismatch for a backend dev

**Problems:** Job #3 required "Sales" as its core skill — a Solutions Architect/pre-sales role, not a fit for a pure backend developer, yet still surfaced at 58%.

---

### Trial 2 — Sara Hassan (Frontend Developer, Dubai, UAE, 3y exp, grad 2020)

**Parsing:** Correct.

**Jobs matched:**
1. Senior Frontend Developer @ TechMena Hub (Cairo) — 61.0% — good match, skills aligned
2. Senior DSP Consultant @ Cambridge Consultants — 46.0% — required "Signal Processing", zero overlap
3. Graduate Cloud Software Engineer (2026 start) @ Cambridge Consultants — 43.0% — grad-level role vs. a 3-year mid-level candidate; required "Digital Services", unmatched

**Problems:** 2 of 3 results are off-domain (signal processing hardware, cloud grad scheme) despite candidate being a pure frontend developer.

---

### Trial 3 — Yasmin Adly (Marketing Coordinator, Cairo, Egypt, rambling CV, recent grad)

**Parsing:** Correct — rambling/informal text was cleaned into structured skills and experience without issue.

**Jobs matched:**
1. Performance Marketing Manager – Solar Lead Gen @ Confidential (Irvine, US) — 51.57% — senior US role, wrong seniority and location
2. Working Student Marketing and Communications @ vaeridion (Munich) — 45.76% — a student role for someone already 1y+ into a full-time job
3. Graphic Design Team Leader @ MY WAY (Cairo) — 44.75% — wrong field entirely (design, not marketing)

**Problems:** None of the 3 matches are a sensible fit — wrong seniority (senior US manager vs. entry-level coordinator), wrong employment type (working student), and wrong field (graphic design).

---

### Trial 4 — Peter Nabil (HR Specialist, Alexandria, Egypt, ~2y exp, grad 2022)

**Parsing:** Correct.

**Jobs matched:** HR and Admin Specialist (67%), Talent Acquisition Specialist (61%), Export Sales Specialist (47%)

**Problems (as observed during testing):**
- No semantic matching — several of the candidate's actual skills are reported as "missing" even when conceptually present
- Over-qualification not handled: one job's stated experience band (0-3 years) should exclude/flag a candidate outside that range, but the pipeline does not check this
- Job #3 (Export Sales Specialist) is a pure sales/logistics role with zero HR relevance, yet still surfaced

---

### Trial 5 — Omar Khaled (Full Stack Developer, Riyadh, Saudi Arabia, 6y exp, grad 2018)

**Parsing:** Correct.

**Jobs matched:** Backend Software Engineer @ Desert AI (53%), Senior Frontend Developer @ TechMena Hub (44%), Senior DSP Consultant (44%)

**Problems:** Job #2's posting URL points to the Wuzzuf domain but the underlying content/company matches an Arbeitnow-sourced listing — a data integrity issue between the retrieved payload and its source link.

---

### Trial 6 — Ahmed Zaki (Sales Executive, Giza, Egypt, rambling CV, ~1y exp, grad 2024)

**Parsing:** Correct.

**Jobs matched:** Projects Sales Manager (49.65%), Route To Market Manager (48.34%), Export Sales Specialist (42.85%)

**Problems (all 3 jobs):**
- No semantic understanding: "cold calling" and general sales experience are not recognized as equivalent to formal "Sales" / "Sales/Retail" skill tags, so every required skill shows as "missing" despite the candidate being an actual sales executive
- None of the 3 postings check the candidate's actual years of experience against role seniority (these are manager-level roles for a ~1-year candidate)

---

### Trial 7 — Mona Adel (DevOps Engineer, Amman, Jordan, 7y exp, grad 2017)

**Parsing:** Correct.

**Jobs matched:** DevOps Engineer @ RobCo (Munich, 85%), Senior DevOps & Platform Engineer @ vaeridion (Munich, 82%), Director, Solutions Engineering @ Docker (65%)

**Problems:**
- Job #1: located in Germany while candidate is Jordan-based — plausibly the only "DevOps" title in the Wuzzuf/Arbeitnow pool at seed time, so location filtering isn't applied at all; also the "missing skill" flagged is a generic "Engineering" tag, not semantically meaningful
- Job #3: candidate is a hands-on DevOps engineer, but the retrieved role is a Director, Solutions Engineering (pre-sales/architecture leadership) — no semantic/domain match, purely a keyword-adjacent hit

---

### Trial 8 — Farida Kamal (Graphic Designer, Mansoura, Egypt, rambling CV, ~1.5y exp, grad 2023)

**Parsing:** Correct.

**Problems (across all 3 results):**
- Experience-years qualification not enforced (senior-leaning postings surfaced for a ~1.5 year candidate)
- Keyword matching, not semantic matching — design-adjacent terms don't map to the job's literal skill tags
- False "missing skills" reported despite CV clearly listing Adobe Illustrator/Photoshop/InDesign

---

### Trial 9 — Youssef Ibrahim (Data Engineer, Cairo, Egypt, 3y exp, grad 2021)

**Parsing:** Correct.

**Jobs matched:** Backend Software Engineer @ Desert AI (43%), DevOps Engineer @ RobCo (42%), Graduate Cloud Software Engineer (41%)

**Problems:** Same recurring issues as prior trials — none of the 3 results is actually a Data Engineering role; low scores across the board reflect the pool lacking data-specific postings, but the pipeline doesn't communicate "no good match found" — it still presents these as a ranked "top 3."

---

### Trial 10 — Mariam Fathy (Junior Accountant, Tanta, Egypt, rambling CV, ~1y exp, grad 2024)

**Parsing:** Correct.

**Jobs matched:** Senior Accounts Manager (54.65%), (Senior) Controller @ YAZIO — Berlin (50.18%), Senior Validation Specialist @ Royal Herbs (42.36%)

**Problems:**
- False missing skills: "Microsoft Office" flagged as missing despite CV explicitly listing advanced Excel (pivot tables, VLOOKUPs) — these should be recognized as equivalent/overlapping
- Experience-level mismatch: all 3 results are Senior-level roles for a candidate with ~1 year of experience
- Location mismatch: one result is in Berlin for an Egypt-based junior candidate
- Job #3 (Senior Validation Specialist, pharma/quality) has zero relevance to accounting

---

### Trial 11 — Nadia Cherkaoui (Data Engineering Lead, Casablanca, Morocco, 14y exp, grad 2010)

**Parsing:** Correct, including 4 nested experience entries and full education/cert details.

**Jobs matched:** Senior Data Practice Lead @ Yld (London, 47.18%), Platform Engineer @ Omnea (London, 47%), Backend Software Engineer @ Desert AI (47.5%)

**Problems:** No semantic match across all 3 — required skills are generic single-word tags ("Engineering", "Tech") that don't correspond meaningfully to the candidate's actual (strong) data engineering background.

---

### Trial 12 — Faisal Al-Otaibi (Principal Backend Engineer, Riyadh, Saudi Arabia, 15y exp, grad 2009)

**Parsing:** Correct, all 4 roles and full history captured.

**Jobs matched:** Backend Software Engineer @ Desert AI (strong/full match, all required skills met), Senior Software Engineer @ Nmi (55%), Engineering Manager @ Nmi (51%)

**Problems:** Jobs #2 and #3 are the same company (Nmi) with the same generic "Product Engineering" gap — looks like limited job pool diversity rather than a ranking failure. No major parsing issues.

---

### Trial 13 — Daniel Whitfield (VP of Engineering, London, UK, 15y exp, grad 2009)

**Parsing:** Mostly correct — all 4 roles captured, but the "Current/target title" field came back blank even though "VP of Engineering" was clearly the CV title.

**Jobs matched:** Engineering Manager @ Nmi (50.13%), Senior DevOps & Platform Engineer @ vaeridion (52.3%), Backend Software Engineer @ Desert AI (50.5%)

**Problems:** Seniority mismatch — a VP-level candidate (managing 45 engineers) is matched to an individual-contributor DevOps role and a single Engineering Manager posting; nothing at director/VP level was retrieved, most likely because the job pool doesn't contain postings at that seniority.

---

### Trial 14 — Ines Bouazizi (Senior Cloud & DevOps Architect, Tunis, Tunisia, 13y exp, grad 2011)

**Parsing:** Mostly correct — one deviation: CV title is "Senior Cloud & DevOps Architect" but the parser normalized it to "Senior Cloud Architect" in the "Current/target title" field, dropping "& DevOps."

**Jobs matched:** Senior DevOps Engineer @ Ostrom (50.4%), DevOps Engineer @ RobCo (50.6%), Senior DevOps & Platform Engineer @ vaeridion (44.3%)

**Problems:** All 3 flag a single generic "Tech" or "Engineering" required skill as "missing" despite the candidate having deep, explicit DevOps tooling experience (Kubernetes, Terraform, Ansible, etc.) — a clear semantic-matching gap rather than a genuine skill gap.

---

### Trial 15 — Rami Haddad (Senior Software Architect, Beirut, Lebanon, 16y exp, grad 2008)

**Parsing:** Correct.

**Jobs matched:** Platform Engineer @ Omnea (53.79%), Senior Technical Account Manager (EMEA) @ Docker (51.72%), Product Engineer @ Omnea (52.2%)

**Problems:** None of the 3 matches an actual Software Architect role; one is a client-facing Sales/Account Manager position with zero technical-architecture overlap — a 16-year senior architect should not be matched to a commercial/sales role.

---

### Trial 16 — Hoda El-Sayed (Senior Marketing Manager, Cairo, Egypt, rambling CV, 18y exp, grad 2006)

**Parsing:** Correct — long, informal narrative-style bullets parsed into clean structured experience entries.

**Jobs matched:** Marketing Manager (62%), Senior Specialist [Trade Marketing] (63%), Senior Product Marketing Manager (56%)

**Problems:** Job #1 reports "0 matched skills" despite the candidate's CV literally containing "Brand strategy, campaign management... market research" against a job requiring "Marketing/PR/Advertising, Market Research, Marketing" — a clear case of exact-keyword mismatch (e.g., "Marketing" as a CV skill word isn't present verbatim, but the semantic content clearly is).

---

### Trial 17 — Tarek Moussa (HR Director, Cairo, Egypt, rambling CV, 19y exp, grad 2005)

**Parsing:** Mostly correct — "Current/target title" came back blank despite "HR Director" being the clear CV title (same gap seen in Trial 13).

**Jobs matched:** HR and Admin Specialist (57%), Talent Acquisition Lead (56%), Talent Acquisition Specialist (54%)

**Problems:** Same false-missing-skill pattern — "Human Resources," "Recruitment," etc. flagged as missing despite 19 years of direct HR leadership experience. Also a seniority mismatch: a Director-level candidate matched to Specialist/Lead-level individual contributor roles.

---

### Trial 18 — Samir Georges (Finance Manager, Cairo, Egypt, rambling CV, 17y exp, grad 2007)

**Parsing:** Correct, including two separate education entries (degree + CMA certification) captured cleanly.

**Jobs matched:** Chief Financial Officer @ Cambridge Consultants (qualitative "solid alignment," no % shown), Senior Accounts Manager (78%), Cost Accountant @ Dabur (72%)

**Problems:** Scoring inconsistency — jobs #2 and #3 report relatively high match scores (78% and 72%) while simultaneously stating "none of the candidate's listed skills currently align" — the score and the explanation contradict each other, suggesting the numeric score and the skill-gap explanation are computed somewhat independently and can disagree.

---

### Trial 19 — Nermeen Adel (Operations Manager, Alexandria, Egypt, rambling CV, 20y exp, grad 2004)

**Parsing:** "Current/target title" blank again despite "Operations Manager" clearly stated (3rd occurrence of this pattern — Trials 13, 17, 19).

**Jobs matched:** Operations Manager @ Medexera (47.7%, call center context), Operations Specialist @ ITTI (47%, logistics/procurement), Workplace and Company Operations Manager @ RobCo (43.56%, "People & Culture" focus)

**Problems:** All 3 flag every required skill as "missing" despite the candidate literally holding the title "Operations Manager" for 10+ years — same false-missing-skill/no-semantic-match pattern seen throughout. None of the 3 is an industrial/manufacturing operations role matching her actual background (call center, procurement, and workplace/HR-adjacent operations instead).

---

### Trial 20 — Mahmoud El-Gendy (Senior School Principal, Cairo, Egypt, rambling CV, 21y exp, grad 2003)

**Parsing:** Correct, including both degrees (B.Ed. + M.Ed.) split into separate entries correctly.

**Jobs matched:** Learning & Development Manager @ GOLD ERA (55%), Talent Acquisition Lead @ GOLD ERA (45%), Director/Project Team Lead, Early Research @ Flagship Pioneering (38%)

**Problems:** Zero relevant matches — no education-sector postings exist in the job pool at all, so the pipeline defaults to the closest keyword-adjacent corporate roles (L&D, Talent Acquisition, biotech research director). This is less a matching-algorithm failure and more a job-pool coverage gap — worth flagging to Omar Zahran that the 150+ job dataset appears to skew heavily tech/corporate with no education, healthcare, or public-sector postings.

---

## Known Issues Encountered During Testing

| Issue | First seen | Root cause (suspected) | Frequency |
|---|---|---|---|
| No semantic/synonym matching (e.g. "cold calling" not recognized as "Sales", "Excel" not recognized as "Microsoft Office") | Trial 4 | Skill-gap matcher appears to do literal/exact tag matching rather than semantic similarity for `SEMANTIC_MATCH_THRESHOLD` | 14+/20 trials |
| Experience-level / seniority not filtered | Trial 4 | No years-of-experience or seniority constraint applied during retrieval or ranking | 10+/20 trials |
| Job pool lacks domain coverage (education, healthcare, DSP/hardware, etc.) | Trial 20 | Only ~180 jobs seeded from Arbeitnow + Wuzzuf, skewed tech/corporate | Affects any non-mainstream-tech CV |
| Score vs. explanation inconsistency (high % score, but explanation says 0 skills matched) | Trial 18 | Numeric fit_score (from re-ranker) and skill-gap explanation (from attach_explanations) appear computed independently and can disagree | Trials 16, 18 |
| "Current/target title" field returned blank despite clear CV title | Trial 13 | Parser inconsistency — occurs specifically on senior/director-level titles (VP, Director, Manager) | Trials 13, 17, 19 |
| Posting URL/domain mismatch with underlying content | Trial 5 | Possible Qdrant/SQLite drift or cross-source payload mixing | Trial 5 |
| Location not filtered/considered in ranking | Trial 7 | No geographic constraint applied | Trials 7, 10 |
| Collection job_postings not found (infrastructure, not a trial itself) | Pre-testing | Qdrant local storage path mismatch between seeding session and backend session | Resolved via re-seed |
| RerankError: Gemini call returned nothing (infrastructure) | Pre-testing | Free-tier Gemini key daily quota (20 requests/day, about 5 pipeline runs) exhausted | Resolved by switching provider/key |

---

## Category Breakdown

### Tech CVs — varied roles & seniority (Trials 1, 2, 5, 6, 9)
Parsing was flawless. Matching quality was mixed: strong when an exact-domain posting existed in the pool (e.g. Trial 1's 95% FastAPI match), poor when it didn't — the pipeline then surfaces the "least bad" option rather than signaling low confidence.

### Tech CVs — senior, international, older grad years (Trials 7, 11, 12, 13, 14, 15)
Parsing handled international formats, older dates, and longer job histories with no errors, aside from the recurring blank "Current/target title" issue on senior titles. Matching consistently failed to respect seniority — Director/VP/Principal-level candidates were repeatedly matched to individual-contributor or even unrelated commercial roles.

### Non-tech CVs — recent graduates, rambling text (Trials 3, 4, 6, 8, 10)
Parsing successfully extracted clean structured data from deliberately informal, run-on, filler-heavy text — this is a genuine strength of the pipeline. Matching was the weakest here: near-zero relevant results, largely because the seeded job pool is tech-heavy and has very few marketing/HR/sales/design/accounting postings to draw from.

### Non-tech CVs — experienced, rambling text (Trials 16, 17, 18, 19, 20)
Same parsing strength held for long, narrative-heavy senior CVs. Matching showed the same false-missing-skill and seniority-mismatch patterns as the tech-senior group, compounded by the job pool's lack of non-tech postings — Trial 20 in particular returned zero domain-relevant results.

---

## Conclusions & Recommendations

- **Parsing quality:** Very strong across all 20 trials, including messy/informal writing styles, multiple degrees, nested experience objects, and non-Egyptian formats. This stage of the pipeline is close to production-ready, aside from the blank "Current/target title" field on certain senior titles.
- **Matching relevance:** The weakest link. Two independent problems compound each other: (1) the skill-gap matcher does literal/keyword matching instead of semantic matching, producing false "missing skill" flags even for clearly-qualified candidates, and (2) the ~180-job seed pool is heavily tech-skewed, so non-tech and senior/leadership CVs have few or no genuinely relevant postings to match against regardless of matching quality.
- **Reliability / infrastructure:** Two blocking issues were hit during setup (Qdrant collection path mismatch, Gemini free-tier daily quota) — both are documented above with their resolutions, and are worth flagging so future testers don't lose time on the same issues.
- **Suggested next steps:**
  1. Coordinate with Omar Zahran to diversify the job pool across domains (marketing, HR, education, finance, sales, design) and seniority levels, not just tech roles.
  2. Investigate whether `SEMANTIC_MATCH_THRESHOLD` / the skill-gap matcher can be moved from exact-tag matching to embedding-based similarity, since this is the single most repeated failure across trials.
  3. Add an experience-years and location filter/penalty to the ranking step, since neither is currently considered.
  4. Investigate the parser's blank "Current/target title" field specifically for senior/director-level CV titles (Trials 13, 17, 19).
  5. Investigate the score-vs-explanation inconsistency seen in Trial 18 (high fit_score alongside "0 skills matched").
