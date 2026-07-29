"""AgentContext data model and pluggable context storage.

Purpose:
After the Match Explanation Agent generates an explanation once, that
result plus the inputs it was generated from are packaged into an
`AgentContext` object. A later follow-up-question flow (the chatbot)
reads this context instead of re-running the Skill Gap Analyzer, the
matching engine, or the explanation generation itself - see
`backend/services/match_explanation_agent.py::answer_followup_question`.

Why the explanation is cached at all:
Generating an explanation means calling Gemini, which costs latency
and money and can return slightly different wording on every call.
Once an explanation has been generated for a given (candidate_id,
job_id) pair, it should be treated as a stable, reusable fact - not
regenerated every time the candidate looks at the same match or asks a
follow-up question. `ContextStore` is what makes that reuse possible.

Why `ContextStore` is an abstraction (not a concrete class):
The Match Explanation Agent should depend on the *idea* of "somewhere
to save/load a context", not on any one storage technology. Today
that's an in-memory dict (`InMemoryContextStore`), fine for a single
process. Production deployments will want a shared, persistent store
(Redis, a database, ...) so contexts survive restarts and are visible
across multiple app instances. Because the agent only ever depends on
the `ContextStore` interface, swapping `InMemoryContextStore` for a
`RedisContextStore` later requires zero changes to the agent - see the
TODO on `InMemoryContextStore` below.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

# Current shape version of `AgentContext`. Bump this whenever a
# backward-incompatible change is made to the fields this dataclass
# carries (e.g. renaming/removing a field, changing a field's meaning).
# `context_version` lets `match_explanation_agent._is_valid_cached_context`
# reject a cached context written by an older, incompatible version of
# this schema (treating it as a cache miss and regenerating) instead of
# trying to use fields that may no longer mean the same thing.
CURRENT_CONTEXT_VERSION = 1


@dataclass
class AgentContext:
    """Reusable context for one candidate-job explanation.

    Attributes:
        candidate_id: Identifier of the candidate/profile owner.
        job_id: Identifier of the job the explanation was generated for.
        match_score: The (already-computed, unmodified) match score.
        matched_skills: Canonical skills the candidate already has.
        missing_skills: Canonical required skills the candidate lacks.
        explanation: The validated explanation JSON (see
            `match_explanation_agent.MatchExplanation.model_dump()`),
            stored as a plain dict so this model has no Pydantic
            dependency of its own.
        context_version: Schema version this context was built with.
            Defaults to `CURRENT_CONTEXT_VERSION` for newly-created
            contexts. Lets future schema changes evolve this dataclass
            without silently misinterpreting an older cached record -
            see `CURRENT_CONTEXT_VERSION` and
            `match_explanation_agent._is_valid_cached_context`.
    """

    candidate_id: str
    job_id: str
    match_score: float
    matched_skills: List[str] = field(default_factory=list)
    missing_skills: List[str] = field(default_factory=list)
    explanation: Dict[str, Any] = field(default_factory=dict)
    context_version: int = CURRENT_CONTEXT_VERSION

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain JSON-compatible dict."""
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "AgentContext":
        """Rebuild an AgentContext from a plain dict (e.g. loaded from storage).

        `context_version` defaults to `1` if absent, so records written
        before this field existed still load instead of raising - they
        are then subject to the same version-support check as any other
        context (see `_is_valid_cached_context`), not silently trusted.
        """
        return AgentContext(
            candidate_id=data["candidate_id"],
            job_id=data["job_id"],
            match_score=data["match_score"],
            matched_skills=list(data.get("matched_skills", [])),
            missing_skills=list(data.get("missing_skills", [])),
            explanation=dict(data.get("explanation", {})),
            context_version=data.get("context_version", 1),
        )


class ContextStore(ABC):
    """Abstraction over where `AgentContext` objects are persisted.

    Why this is an interface, not a concrete class:
    The storage backend for `AgentContext` is intentionally abstracted
    away from the Match Explanation Agent
    (`backend.services.match_explanation_agent`, both the module-level
    functions and the `MatchExplanationAgent` class). Every place that
    needs to save/load/check/delete a context - `get_or_create_explanation`,
    `load_context`, `invalidate_context`, `MatchExplanationAgent` - talks
    only to this four-method interface (`save` / `load` / `exists` /
    `delete`), never to a concrete storage technology.

    Current implementation:
    Today the only implementation is `InMemoryContextStore`, a plain
    in-process dict guarded by a lock. That is enough for a single
    process/instance, but it does not survive restarts and is not
    shared across multiple app instances or workers.

    Swapping in a distributed backend later:
    Because callers depend only on this interface, a `RedisContextStore`
    (or any other distributed cache / database-backed store) can replace
    `InMemoryContextStore` purely by implementing these same four
    methods - `save`, `load`, `exists`, `delete` - with the same
    signatures and semantics (see each method's docstring below). No
    changes are required in `match_explanation_agent.py`: swapping the
    store is a one-line change at the call site (pass the new store
    into `MatchExplanationAgent(store=...)`, or as the `store=` argument
    to the module-level functions), not a code change to the agent
    itself. This is the whole reason the interface exists - it is the
    seam where "single process, in-memory" becomes "distributed,
    persistent" without the agent's logic needing to know or care.
    """

    @abstractmethod
    def save(self, context: AgentContext) -> None:
        """Store (or overwrite) `context`, keyed by its candidate/job pair."""
        raise NotImplementedError

    @abstractmethod
    def load(self, candidate_id: str, job_id: str) -> Optional[AgentContext]:
        """Return the stored context for this pair, or `None` if absent."""
        raise NotImplementedError

    @abstractmethod
    def exists(self, candidate_id: str, job_id: str) -> bool:
        """Return whether a context is already stored for this pair."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, candidate_id: str, job_id: str) -> None:
        """Remove any stored context for this pair, if present.

        Used when a candidate uploads a new CV, or starts a completely
        new matching session for a pair that previously had a cached
        explanation - the old explanation no longer describes the
        current profile/job data and must not be reused. Implementations
        should be a no-op (not an error) if nothing is stored for the
        pair.
        """
        raise NotImplementedError


class InMemoryContextStore(ContextStore):
    """`ContextStore` implementation backed by an in-process dict.

    Keyed by `(candidate_id, job_id)`. Thread-safe via a simple lock,
    which is sufficient for a single process but NOT for multiple
    processes/instances - see the TODO below.

    TODO:
    Replace `InMemoryContextStore` with a `RedisContextStore` (or
    equivalent distributed cache / database-backed store) for
    production deployments. In-memory storage does not survive process
    restarts and is not shared across multiple app instances/workers -
    every instance would generate (and pay for) its own explanation for
    the same candidate/job pair. A `RedisContextStore` implementing the
    same `ContextStore` interface (`save`/`load`/`exists`/`delete`) can
    replace this class with no changes required in
    `match_explanation_agent.py`, since the agent only ever depends on
    `ContextStore`.
    """

    def __init__(self) -> None:
        self._contexts: Dict[Tuple[str, str], AgentContext] = {}
        self._lock = threading.Lock()

    def save(self, context: AgentContext) -> None:
        """Store (or overwrite) the context for its candidate/job pair."""
        with self._lock:
            self._contexts[(context.candidate_id, context.job_id)] = context

    def load(self, candidate_id: str, job_id: str) -> Optional[AgentContext]:
        """Return the stored context for this pair, or None if absent."""
        with self._lock:
            return self._contexts.get((candidate_id, job_id))

    def exists(self, candidate_id: str, job_id: str) -> bool:
        """Return whether a context is already stored for this pair."""
        with self._lock:
            return (candidate_id, job_id) in self._contexts

    def delete(self, candidate_id: str, job_id: str) -> None:
        """Remove any stored context for this pair, if present.

        A no-op (not an error) if nothing is stored for the pair -
        callers shouldn't need to check `exists()` first just to call
        `delete()` safely.
        """
        with self._lock:
            self._contexts.pop((candidate_id, job_id), None)

    def clear(self) -> None:
        """Remove all stored contexts (mainly for tests)."""
        with self._lock:
            self._contexts.clear()

    # ------------------------------------------------------------------
    # Backward-compatible aliases.
    #
    # Earlier versions of this module exposed `get`/`set` directly (before
    # the `ContextStore` interface existed). Kept as thin aliases over
    # `load`/`save` so existing callers/tests using those names keep
    # working unchanged - the public API has not changed, only gained
    # the new `ContextStore`-shaped names alongside it.
    # ------------------------------------------------------------------

    def get(self, candidate_id: str, job_id: str) -> Optional[AgentContext]:
        """Deprecated alias for `load()`. Kept for backward compatibility."""
        return self.load(candidate_id, job_id)

    def set(self, context: AgentContext) -> None:
        """Deprecated alias for `save()`. Kept for backward compatibility."""
        self.save(context)


# Backward-compatible alias: earlier versions of this module exposed
# `AgentContextStore` as the (only, concrete) store class. Existing
# imports of `AgentContextStore` keep working unchanged.
AgentContextStore = InMemoryContextStore


# Process-local default store, kept ONLY for backward compatibility with
# the free functions in `match_explanation_agent.py` (e.g.
# `get_or_create_explanation(..., store=None)`), which fall back to this
# module-level singleton when no store is explicitly passed. This is a
# convenience for existing call sites, not a recommendation: for new
# code, prefer constructing a `MatchExplanationAgent` with an explicit
# `ContextStore` (dependency injection) rather than relying on this
# global - see `match_explanation_agent.MatchExplanationAgent`.
default_store = InMemoryContextStore()
