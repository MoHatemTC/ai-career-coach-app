import numpy as np
from sqlalchemy.orm import Session
from backend.features.matching.scorer import get_model
from backend.features.matching.vector_store import get_qdrant_client, COLLECTION_NAME

def retrieve_top_jobs(cv_text: str, top_k: int = 10) -> list[dict]:

    model = get_model()

    cv_embedding = model.encode(cv_text)
    cv_embedding_list = cv_embedding.tolist() if hasattr(cv_embedding, "tolist") else list(cv_embedding)

    client = get_qdrant_client()
    search_results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=cv_embedding_list,
        limit=top_k
    ).points

    clean_json_output = []
    for point in search_results:
        payload = point.payload or {}
        score = point.score

        clean_json_output.append({
            "job_id": payload.get("job_id"),
            "title": payload.get("title"),
            "company": payload.get("company"),
            "location": payload.get("location"),
            "url": payload.get("url"),
            "source": payload.get("source"),
            "match_score": float(score)
        })

    return clean_json_outputs