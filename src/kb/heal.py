"""Heuristic healing for ontology drift.

When the verifier reports a missing symbol (a rename or move broke an
``implements:``/``underlying:`` reference), this module proposes a
replacement by scoring the missing local name against every currently
defined engine symbol. The scoring is intentionally deterministic and
stdlib-only — workshop attendees can reproduce it without an API key,
and the failure modes are visible from the diff alone.

Two signals contribute to a candidate's score:

* **Local-name identity** — the unqualified name after the last ``::``
  matches. Strongest possible signal: the symbol almost certainly moved
  namespaces rather than being deleted.
* **Local-name similarity** — ``difflib.SequenceMatcher`` ratio between
  the two local names. Good at catching renames like ``XWingDetector`` →
  ``XWingTechnique``.

A non-zero score requires *some* shared substring; pure Levenshtein on
short identifiers is too noisy (``XYZ`` and ``WXY`` would otherwise look
related).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from kb.verify import (
    MissingBinding,
    VerifyReport,
    collect_engine_symbols,
    resolve_symbol_roots,
    verify,
)


# Score thresholds picked from observation on this codebase. Renames in
# practice fall into two shapes:
#   * shared *prefix*, different suffix — e.g. XWingTechnique → XWingDetector.
#     Bare difflib ratio underweights these (0.5-ish) but they are exactly
#     the case we most want to catch. Detect via prefix-fraction.
#   * shared root, different surrounding text — caught by the ratio fallback.
_RATIO_KEEP_THRESHOLD = 0.70
_MIN_SHARED_LEN = 3
_MIN_PREFIX_LEN = 4
_MIN_PREFIX_FRACTION = 0.30  # of the shorter name


@dataclass
class HealCandidate:
    symbol: str
    score: float
    reason: str  # "moved" | "renamed" | "similar"


@dataclass
class HealSuggestion:
    missing: MissingBinding
    candidates: list[HealCandidate]

    @property
    def best(self) -> HealCandidate | None:
        return self.candidates[0] if self.candidates else None


def _local(symbol: str) -> str:
    return symbol.rsplit("::", 1)[-1]


def _shared_substring_len(a: str, b: str) -> int:
    # Length of the longest matching block — proxy for "is there a real
    # shared root or are we matching noise."
    match = SequenceMatcher(None, a, b).find_longest_match(0, len(a), 0, len(b))
    return match.size


def _common_prefix_len(a: str, b: str) -> int:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n


def _score_candidate(missing_local: str, candidate: str) -> tuple[float, str]:
    cand_local = _local(candidate)
    if missing_local == cand_local:
        return 0.95, "moved"
    if _shared_substring_len(missing_local, cand_local) < _MIN_SHARED_LEN:
        return 0.0, ""
    # Prefix-based detection — catches "Foo*" rename patterns that bare
    # SequenceMatcher under-scores.
    prefix_len = _common_prefix_len(missing_local, cand_local)
    shorter = min(len(missing_local), len(cand_local))
    if prefix_len >= _MIN_PREFIX_LEN and prefix_len / shorter >= _MIN_PREFIX_FRACTION:
        # Strong prefix → 0.80; full prefix coverage of the shorter name → 0.90.
        score = 0.80 + 0.10 * (prefix_len / shorter)
        return min(score, 0.92), "renamed"
    ratio = SequenceMatcher(None, missing_local, cand_local).ratio()
    if ratio >= _RATIO_KEEP_THRESHOLD:
        return ratio, "renamed" if ratio >= 0.8 else "similar"
    return 0.0, ""


def propose(
    report: VerifyReport,
    engine_symbols: Iterable[str],
    *,
    max_candidates: int = 3,
) -> list[HealSuggestion]:
    engine = list(engine_symbols)
    suggestions: list[HealSuggestion] = []
    for missing in report.missing:
        missing_local = _local(missing.symbol)
        scored: list[HealCandidate] = []
        for cand in engine:
            score, reason = _score_candidate(missing_local, cand)
            if score > 0:
                scored.append(HealCandidate(symbol=cand, score=score, reason=reason))
        scored.sort(key=lambda c: -c.score)
        suggestions.append(
            HealSuggestion(missing=missing, candidates=scored[:max_candidates])
        )
    return suggestions


def heal(
    *,
    apply: bool = False,
    min_confidence: float = 0.85,
) -> tuple[list[HealSuggestion], list[Path]]:
    """Run verify + propose. When ``apply`` is true, rewrite ontology files
    in place — replacing each missing symbol with its single best candidate
    if and only if that candidate's score clears ``min_confidence``.

    Returns ``(suggestions, written_paths)``.
    """

    repo_root, _, include_root = resolve_symbol_roots()
    report = verify()
    if report.ok:
        return [], []
    symbols = collect_engine_symbols(include_root, repo_root)
    suggestions = propose(report, symbols)
    written: list[Path] = []
    if apply:
        written = _apply(suggestions, repo_root=repo_root, min_confidence=min_confidence)
    return suggestions, written


def _apply(
    suggestions: list[HealSuggestion],
    *,
    repo_root: Path,
    min_confidence: float,
) -> list[Path]:
    """Rewrite ontology files, replacing each missing symbol with the best
    candidate when its score clears the confidence floor."""

    # Group suggestions by file so we don't read+write each file twice.
    by_file: dict[Path, list[HealSuggestion]] = {}
    for sug in suggestions:
        best = sug.best
        if best is None or best.score < min_confidence:
            continue
        path = repo_root / sug.missing.entry_path
        by_file.setdefault(path, []).append(sug)

    written: list[Path] = []
    for path, file_suggestions in by_file.items():
        text = path.read_text(encoding="utf-8")
        new_text = text
        for sug in file_suggestions:
            new_text = _replace_symbol(new_text, sug.missing.symbol, sug.best.symbol)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            written.append(path)
    return written


def _replace_symbol(text: str, old_symbol: str, new_symbol: str) -> str:
    """Replace a fully qualified symbol in YAML list lines.

    Matches the symbol exactly to avoid touching mentions in body prose,
    which the user may want to update by hand. A YAML list entry looks like
    ``  - myproject::XWingTechnique`` — we match the leading dash + spaces.
    """

    pattern = re.compile(
        r"(?m)^(\s*-\s+)" + re.escape(old_symbol) + r"\s*$"
    )
    return pattern.sub(r"\g<1>" + new_symbol, text)
