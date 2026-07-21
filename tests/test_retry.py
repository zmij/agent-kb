"""Retry-with-backoff and graceful per-batch failure handling."""

from pathlib import Path

import pytest

from kb.runner import _looks_transient, _with_retry, run_index
from kb.util import file_content_hash


def test_looks_transient_recognises_timeout():
    class _FakeRpcError(Exception):
        def __str__(self):
            return "Timeout expired"

    assert _looks_transient(_FakeRpcError("Timeout expired")) is True


def test_looks_transient_recognises_cancelled():
    err = Exception("status: CANCELLED, details: Timeout expired")
    assert _looks_transient(err) is True


def test_looks_transient_passes_through_other_errors():
    err = ValueError("bad payload")
    assert _looks_transient(err) is False


def test_with_retry_succeeds_on_first_attempt():
    calls = [0]

    def op():
        calls[0] += 1
        return "ok"

    assert _with_retry(op, op_name="test") == "ok"
    assert calls[0] == 1


def test_with_retry_recovers_on_transient(capsys):
    calls = [0]

    def op():
        calls[0] += 1
        if calls[0] < 3:
            raise Exception("Timeout expired")
        return "eventual ok"

    result = _with_retry(op, op_name="test", attempts=3, base_backoff=0.001)
    assert result == "eventual ok"
    assert calls[0] == 3
    captured = capsys.readouterr()
    assert "attempt 1/3" in captured.err
    assert "attempt 2/3" in captured.err


def test_with_retry_gives_up_after_attempts():
    calls = [0]

    def op():
        calls[0] += 1
        raise Exception("Timeout expired")

    with pytest.raises(Exception, match="Timeout expired"):
        _with_retry(op, op_name="test", attempts=3, base_backoff=0.001)
    assert calls[0] == 3


def test_with_retry_does_not_retry_non_transient():
    calls = [0]

    def op():
        calls[0] += 1
        raise ValueError("bad input")

    with pytest.raises(ValueError, match="bad input"):
        _with_retry(op, op_name="test", attempts=3, base_backoff=0.001)
    assert calls[0] == 1


# ---------------------------------------------------------------------------
# Per-batch failure isolation
# ---------------------------------------------------------------------------


class _FlakyStore:
    """Fake store that fails the upsert N times, then succeeds.

    The runner should retry within _with_retry; if N exceeds the retry
    budget, the batch is logged as failed and the run continues.
    """

    def __init__(self, *, fail_upserts: int = 0):
        self.fail_upserts = fail_upserts
        self.upserted_payloads: list[dict] = []
        self.deleted_paths: list[str] = []

    def ensure_collection(self, *a, **kw): pass

    def delete_by_source(self, *a, **kw):
        pass

    def enumerate_file_hashes(self, *a, **kw):
        return {}

    def delete_by_path(self, collection, source, path):
        self.deleted_paths.append(path)

    def upsert(self, collection, ids, vectors, payloads):
        if self.fail_upserts > 0:
            self.fail_upserts -= 1
            raise Exception("Timeout expired")
        self.upserted_payloads.extend(payloads)


class _FakeProvider:
    name = "fake"
    dim = 4

    def embed_texts(self, texts):
        return [[0.0, 0.0, 0.0, 0.0] for _ in texts]


@pytest.fixture
def fast_retry(monkeypatch):
    """Stub time.sleep so retry tests don't actually wait."""
    monkeypatch.setattr("kb.runner.time.sleep", lambda _: None)


def _scoped_ontology_indexer(ontology_root, tmp_path):
    from kb.indexers.ontology import OntologyIndexer

    class _Scoped(OntologyIndexer):
        def __init__(self):
            super().__init__(root=ontology_root)
            self._repo_root = tmp_path

    return _Scoped


def test_runner_recovers_from_transient_then_continues(tmp_path, monkeypatch, fast_retry):
    """A flaky upsert that recovers within retry budget produces a
    fully successful IndexResult."""
    from kb.indexers import REGISTRY

    ontology_root = tmp_path / "ontology"
    ontology_root.mkdir()
    (ontology_root / "x.md").write_text(
        "---\nconcept: x\ntitle: X\nkind: type\nimplements:\n  - sudoku::X\n---\nBody.\n"
    )

    monkeypatch.setitem(REGISTRY, "ontology", _scoped_ontology_indexer(ontology_root, tmp_path))

    store = _FlakyStore(fail_upserts=2)  # Fails twice, succeeds on third try

    result = run_index("ontology", provider=_FakeProvider(), store=store)
    assert result.ok
    assert result.upserted == 1
    assert result.failed_batches == 0


def test_runner_records_failed_batch_without_crashing(
    tmp_path, monkeypatch, capsys, fast_retry
):
    """An upsert that never recovers is recorded in the result rather
    than crashing the whole run."""
    from kb.indexers import REGISTRY

    ontology_root = tmp_path / "ontology"
    ontology_root.mkdir()
    (ontology_root / "x.md").write_text(
        "---\nconcept: x\ntitle: X\nkind: type\nimplements:\n  - sudoku::X\n---\nBody.\n"
    )

    monkeypatch.setitem(REGISTRY, "ontology", _scoped_ontology_indexer(ontology_root, tmp_path))

    # 10 failures exceeds the 3-attempt retry budget.
    store = _FlakyStore(fail_upserts=10)

    result = run_index("ontology", provider=_FakeProvider(), store=store)
    assert not result.ok
    assert result.upserted == 0
    assert result.failed_batches == 1
    assert "ontology/x.md" in result.failed_paths

    # User-visible message is on stderr, no traceback dumped.
    captured = capsys.readouterr()
    assert "batch failed" in captured.err
