# Job Matching Engine Architecture & Design

## Overview
The job matching engine evaluates candidate profiles against ingested job postings using semantic similarity embeddings powered by `SentenceTransformer` and cosine similarity.

## Scoring Metric & Design Trade-offs
We use **SentenceTransformer** embeddings combined with **Cosine Similarity** as our core scoring metric.

* **Advantages:**
  * Captures semantic meaning and context rather than just exact keyword matching.
  * Runs locally, avoiding external API costs, rate limits, and latency issues.
* **Trade-offs / Alternatives Considered:**
  * *TF-IDF / BM25:* Faster and lighter, but fails to capture semantic synonyms and contextual nuances.
  * *OpenAI Embeddings API:* High accuracy, but introduces network dependency, latency, and recurring API costs. 
  * *Decision:* SentenceTransformer provides the best balance of semantic accuracy, privacy, and zero-cost local execution.

## Deterministic Ranking
To ensure ranking is completely deterministic (preventing unstable sorting when multiple jobs share the exact same match score), a secondary sort key (`job_id`) is applied alongside the match score.

## Future Integration Plan (Experience & Location)
To scale the scoring formula beyond text/skills similarity, we plan to incorporate structured fields:
1. **Experience Weighting:** Compare candidate's years of experience against the job's minimum requirement, applying a multiplier penalty if the candidate is under-qualified or a bonus if they match closely.
2. **Location Matching:** Add a binary or distance-based score component for remote-friendly vs. on-site location preferences.
3. **Combined Formula:** Final Score = (Semantic Similarity * 0.6) + (Experience Match * 0.3) + (Location Preference * 0.1).