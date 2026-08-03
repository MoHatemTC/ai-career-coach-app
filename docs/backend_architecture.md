# Backend Architecture - Career Coach Project

## 1. System Overview & Data Flow
The Career Coach backend is built as a sequential processing pipeline that matches user resumes/queries with relevant job postings using semantic search and advanced ranking models.

* **Input Stage:** The user submits a request containing their CV text or query parameters.
* **Retrieval Stage (Vector Search):** The query is embedded and matched against job postings stored in a Qdrant vector database using Cosine Similarity, entirely replacing legacy SQL filtering to ensure semantic accuracy.
* **Ranking Stage:** The top retrieved items are processed through downstream ranking/LLM stages to provide the final curated output.

## 2. API Endpoints & Request/Response Contracts

### A. Job Retrieval Endpoint
* **Path / Function:** `retrieve_top_jobs` (located in `backend/features/matching/retriever.py`)
* **Purpose:** Fetches the top 10 most relevant jobs using semantic vector search.
* **Request Payload (JSON):**
```json
{
  "query": "string (Encoded CV text or user skill set)",
  "top_k": 10
}
Response JSON Schema:

JSON
{
  "status": "success",
  "count": 10,
  "results": [
    {
      "job_id": "string",
      "title": "string",
      "company": "string",
      "location": "string",
      "url": "string",
      "source": "string",
      "match_score": 0.95
    }
  ]
}
3. Core Components & Dependencies
Vector Database: Qdrant (utilized via client.query_points).

Embeddings Model: SentenceTransformer (all-MiniLM-L6-v2) ensuring consistent vector dimensions across the pipeline.

Output Contract Enforcement: Strict JSON structuring implemented to guarantee seamless integration for downstream ranking services