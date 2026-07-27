# Job Matching & Ranking Engine - Technical Documentation

## Overview
The Job Matching and Ranking Engine is a core backend component designed to connect candidate profiles with the most suitable job listings based on rule-based filtering and skill-matching algorithms.

## Matching Methodology & Algorithm
1. **Rule-Based Pre-filtering / Experience Check:** - The engine validates whether the candidate's years of experience (`experience_years`) meet or exceed the minimum requirement (`min_experience`) specified by the job posting.

2. **Skill Intersection & Scoring:**
   - Candidate skills and job required skills are normalized to lowercase sets to ensure case-insensitive matching.
   - The scoring algorithm calculates the ratio of matched skills relative to the total required skills for a given job posting.
   - If a job has no specific required skills, a default optimal score is assigned.

3. **Ranking Methodology:**
   - After computing scores for all available job postings in the database, the engine sorts the results in descending order based on the final match score, generating a cleanly ordered ranked list for the recommendation pipeline.