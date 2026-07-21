"""Run an indexer end-to-end: chunk → embed → upsert.

Kept separate from indexers so they stay free of any model/Qdrant coupling.
"""

from __future__ import annotations

import itertools
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator

from kb.embedding import EmbeddingProvider, get_provider
from kb.indexers import Indexer, build
from kb.indexers.base import ChunkRecord
from kb.qdrant_client import KBStore


@dataclass
class IndexResult:
    source: str
    collection: str
    upserted: int
    skipped_files: int
    deleted_orphans: int
    embedding_provider: str
    failed_batches: int = 0
    failed_paths: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.failed_batches == 0


def _batched(it: Iterable[ChunkRecord], size: int) -> Iterator[list[ChunkRecord]]:
    iterator = iter(it)
    while True:
        batch = list(itertools.islice(iterator, size))
        if not batch:
            return
        yield batch


_TRANSIENT_HINTS = (
    "Timeout expired",
    "Deadline Exceeded",
    "UNAVAILABLE",
    "CANCELLED",
    "Connection reset",
    "ConnectionResetError",
)


def _looks_transient(exc: BaseException) -> bool:
    """Heuristic for whether a Qdrant exception is worth retrying.

    Covers gRPC timeouts/cancellations, HTTP timeouts, and connection
    resets. Falls back to substring matching on the exception text so we
    don't have to import the specific exception classes from every
    transport qdrant-client might use.
    """

    text = f"{type(exc).__name__}: {exc}"
    return any(hint in text for hint in _TRANSIENT_HINTS)


def _with_retry(
    op: Callable[[], Any],
    *,
    op_name: str,
    attempts: int = 3,
    base_backoff: float = 1.0,
) -> Any:
    """Retry a Qdrant operation with exponential backoff on transient errors.

    Raises the last exception if all attempts fail. Non-transient
    exceptions (validation errors, bad payloads, etc.) are raised
    immediately without retry.
    """

    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return op()
        except BaseException as exc:
            if not _looks_transient(exc) or attempt == attempts:
                raise
            last_exc = exc
            delay = base_backoff * (2 ** (attempt - 1))
            print(
                f"  ⚠ {op_name} attempt {attempt}/{attempts} failed "
                f"({type(exc).__name__}); retrying in {delay:.1f}s",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)
    if last_exc is not None:
        raise last_exc


def run_index(
    source: str,
    *,
    provider: EmbeddingProvider | None = None,
    store: KBStore | None = None,
    batch_size: int = 64,
    incremental: bool = True,
) -> IndexResult:
    """Run an indexer end-to-end.

    Two modes:

    * ``incremental=True`` (default) — query Qdrant for the
      ``{path: content_hash}`` map of files already indexed for this source,
      and skip every file whose content hash matches. Only changed files are
      re-embedded and upserted; chunks for files that have been deleted
      from the source corpus are cleaned up at the end. Embeddings dominate
      indexing time, so this is much faster when only a handful of files
      have changed.
    * ``incremental=False`` — delete every existing chunk for this source
      first, then re-embed everything. Useful when the chunker or embedding
      model has changed and the hash check would falsely think the data is
      fresh.

    Failed batches (after retries) are recorded in ``IndexResult.failed_*``
    rather than raised, so an isolated Qdrant hiccup doesn't blow away an
    otherwise-successful run. The CLI surfaces the failures and exits
    non-zero if anything failed.
    """

    indexer: Indexer = build(source)
    provider = provider or get_provider()
    store = store or KBStore()

    _with_retry(
        lambda: store.ensure_collection(indexer.collection, provider.dim),
        op_name=f"ensure_collection({indexer.collection})",
    )

    if not incremental:
        # Full rebuild: start from scratch.
        _with_retry(
            lambda: store.delete_by_source(indexer.collection, indexer.name),
            op_name=f"delete_by_source({indexer.name})",
        )
        callback = None
        seen_paths: set[str] | None = None
        existing_paths: set[str] = set()
        skipped_counter = [0]
    else:
        existing = _with_retry(
            lambda: store.enumerate_file_hashes(indexer.collection, indexer.name),
            op_name=f"enumerate_file_hashes({indexer.name})",
        )
        existing_paths = set(existing.keys())
        seen_paths = set()
        skipped_counter = [0]

        def callback(path: str, content_hash: str) -> bool:
            seen_paths.add(path)
            if existing.get(path) == content_hash:
                skipped_counter[0] += 1
                return False
            return True

    total = 0
    failed_batches = 0
    failed_paths: list[str] = []
    paths_evicted: set[str] = set()

    for batch in _batched(indexer.iter_chunks(should_index=callback), batch_size):
        batch_paths = {c.payload.get("path") for c in batch if c.payload.get("path")}
        try:
            if incremental:
                # Delete the previous chunks for any file appearing in this batch
                # before upserting the new ones. The hash check guarantees this
                # file is changed/new, so old chunks (if any) are stale.
                for path in batch_paths:
                    if path in paths_evicted:
                        continue
                    _with_retry(
                        lambda p=path: store.delete_by_path(
                            indexer.collection, indexer.name, p
                        ),
                        op_name=f"delete_by_path({path})",
                    )
                    paths_evicted.add(path)

            vectors = provider.embed_texts([c.text for c in batch])
            _with_retry(
                lambda: store.upsert(
                    collection=indexer.collection,
                    ids=[c.id for c in batch],
                    vectors=vectors,
                    payloads=[c.payload for c in batch],
                ),
                op_name=f"upsert({len(batch)} chunks)",
            )
            total += len(batch)
        except BaseException as exc:
            # Retries exhausted (or non-transient). Record the failure and
            # keep going so a single bad batch doesn't lose the rest of the
            # run's progress.
            failed_batches += 1
            failed_paths.extend(p for p in batch_paths if p not in failed_paths)
            print(
                f"  ✗ batch failed after retries ({type(exc).__name__}): {exc}",
                file=sys.stderr,
                flush=True,
            )

    # Orphan cleanup: paths that were in Qdrant but the indexer didn't yield
    # this run — the source file has been deleted or moved.
    deleted_orphans = 0
    if incremental and seen_paths is not None:
        orphans = existing_paths - seen_paths
        for path in orphans:
            try:
                _with_retry(
                    lambda p=path: store.delete_by_path(
                        indexer.collection, indexer.name, p
                    ),
                    op_name=f"orphan delete_by_path({path})",
                )
                deleted_orphans += 1
            except BaseException as exc:
                # Don't crash the whole run just because an orphan can't
                # be evicted; it'll be retried next time.
                print(
                    f"  ✗ orphan cleanup failed for {path} ({type(exc).__name__})",
                    file=sys.stderr,
                    flush=True,
                )

    return IndexResult(
        source=indexer.name,
        collection=indexer.collection,
        upserted=total,
        skipped_files=skipped_counter[0],
        deleted_orphans=deleted_orphans,
        embedding_provider=provider.name,
        failed_batches=failed_batches,
        failed_paths=failed_paths,
    )
