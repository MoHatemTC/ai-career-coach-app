"""
Temporary placeholder for the vector store.

This file exists so the application can import the matching
module until the real vector store implementation is merged.
"""


COLLECTION_NAME = "job_postings"


def get_qdrant_client():
    """
    Placeholder implementation.

    Replace this with the real Qdrant client once the matching
    branch is merged.
    """
    raise NotImplementedError(
        "Vector store implementation has not been merged yet."
    )