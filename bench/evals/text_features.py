"""Pure text feature extractors and two-sample distances for corpus metrics.

The routines here deliberately avoid heavyweight NLP dependencies.  They turn
decoded text into coherence-sensitive lexical trajectories and entity/discourse
summary vectors, then expose standard distributional distances on those
features.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Callable, Iterable

import numpy as np


WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9']*|\d+")
CAP_WORD_RE = re.compile(r"\b[A-Z][a-z][A-Za-z']+\b")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

EPS = 1e-12

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an",
    "and", "any", "are", "as", "at", "be", "because", "been", "before",
    "being", "below", "between", "both", "but", "by", "can", "did", "do",
    "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here", "hers",
    "herself", "him", "himself", "his", "how", "i", "if", "in", "into",
    "is", "it", "its", "itself", "just", "me", "more", "most", "my",
    "myself", "no", "nor", "not", "now", "of", "off", "on", "once",
    "only", "or", "other", "our", "ours", "ourselves", "out", "over",
    "own", "same", "she", "should", "so", "some", "such", "than", "that",
    "the", "their", "theirs", "them", "themselves", "then", "there",
    "these", "they", "this", "those", "through", "to", "too", "under",
    "until", "up", "very", "was", "we", "were", "what", "when", "where",
    "which", "while", "who", "whom", "why", "with", "you", "your",
    "yours", "yourself", "yourselves",
}

PRONOUNS = {
    "he", "him", "his", "she", "her", "hers", "they", "them", "their",
    "theirs", "it", "its", "we", "us", "our", "ours", "i", "me", "my",
    "mine", "you", "your", "yours",
}

DISCOURSE_MARKERS: dict[str, tuple[str, ...]] = {
    "contrast": (
        "however", "but", "although", "though", "yet", "nevertheless",
        "nonetheless", "instead", "whereas", "despite",
    ),
    "cause": (
        "because", "therefore", "thus", "hence", "so", "since",
        "consequently", "as a result", "due to",
    ),
    "temporal": (
        "then", "next", "after", "before", "meanwhile", "later", "finally",
        "previously", "subsequently", "during",
    ),
    "addition": (
        "also", "moreover", "furthermore", "additionally", "besides",
        "indeed", "in addition",
    ),
    "condition": (
        "if", "unless", "provided", "whether", "otherwise", "assuming",
    ),
    "example": (
        "for example", "for instance", "such as", "including", "namely",
    ),
    "conclusion": (
        "overall", "therefore", "in conclusion", "ultimately", "in short",
    ),
}

DISCOURSE_CATEGORIES = tuple(DISCOURSE_MARKERS.keys())

TRAJECTORY_FEATURE_NAMES = [
    "log_words",
    "n_segments",
    "mean_segment_len",
    "std_segment_len",
    "min_segment_len",
    "max_segment_len",
    "punct_rate",
    "adj_cos_mean",
    "adj_cos_std",
    "adj_cos_min",
    "adj_cos_p05",
    "adj_cos_max",
    "lag2_cos_mean",
    "first_last_cos",
    "step_mean",
    "step_std",
    "step_max",
    "path_length",
    "net_displacement",
    "tortuosity",
    "centroid_dist_mean",
    "centroid_dist_max",
    "similarity_slope",
]

ENTITY_DISCOURSE_FEATURE_NAMES = [
    "log_words",
    "n_segments",
    "mean_sentence_len",
    "std_sentence_len",
    "content_rate",
    "unique_content_ratio",
    "repeated_content_ratio",
    "max_chain_frac",
    "repeated_segment_coverage",
    "adj_entity_overlap_mean",
    "adj_entity_overlap_std",
    "adj_entity_overlap_min",
    "first_last_entity_overlap",
    "capitalized_rate",
    "repeated_capitalized_ratio",
    "pronoun_rate",
    "pronoun_to_entity_ratio",
    "unresolved_pronoun_proxy",
    "discourse_total_rate",
    "discourse_entropy",
    "discourse_transition_entropy",
    "discourse_coverage",
    "connective_start_rate",
    "quote_rate",
    "comma_rate",
    "semicolon_colon_rate",
    "paragraph_break_rate",
    *[f"marker_{cat}_rate" for cat in DISCOURSE_CATEGORIES],
]

TAIL_FEATURE_NAMES = [
    "max_topic_jump",
    "p95_topic_jump",
    "low_adj_similarity",
    "trajectory_tortuosity",
    "centroid_outlier_max",
    "top_word_rate",
    "repeat_bigram_rate",
    "repeat_trigram_rate",
    "max_repeated_bigram_frac",
    "distinct_word_deficit",
    "adjacent_length_jump_max",
    "short_segment_rate",
    "entity_overlap_deficit_max",
    "entity_dropout_rate",
    "pronoun_without_entity_rate",
    "discourse_marker_gap_frac",
    "eot_token_rate",
    "nonalpha_token_rate",
]


def split_segments(text: str, target_words: int = 24, max_segments: int = 32) -> list[str]:
    text = text.replace("<|endoftext|>", "\n")
    raw = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]
    segments: list[str] = []
    for sent in raw:
        words = word_tokens(sent)
        if not words:
            continue
        if len(words) > target_words * 2:
            for i in range(0, len(words), target_words):
                chunk = words[i: i + target_words]
                if chunk:
                    segments.append(" ".join(chunk))
        else:
            segments.append(sent)

    if len(segments) < 2:
        words = word_tokens(text)
        if words:
            n_parts = min(max_segments, max(2, math.ceil(len(words) / max(target_words, 1))))
            size = max(1, math.ceil(len(words) / n_parts))
            segments = [" ".join(words[i: i + size]) for i in range(0, len(words), size)]

    if not segments:
        return [""]
    return segments[:max_segments]


def word_tokens(text: str) -> list[str]:
    return [m.group(0) for m in WORD_RE.finditer(text)]


def lower_words(text: str) -> list[str]:
    return [w.lower() for w in word_tokens(text)]


_HASH_CACHE: dict[tuple[str, int], tuple[int, float]] = {}


def hashed_segment_vector(text: str, dim: int = 256) -> np.ndarray:
    vec = np.zeros(dim, dtype=np.float64)
    for word in lower_words(text):
        if not word or word in STOPWORDS:
            continue
        key = (word, dim)
        hit = _HASH_CACHE.get(key)
        if hit is None:
            digest = hashlib.blake2b(word.encode("utf-8", "ignore"), digest_size=8).digest()
            value = int.from_bytes(digest, "little", signed=False)
            hit = (value % dim, 1.0 if ((value >> 32) & 1) == 0 else -1.0)
            _HASH_CACHE[key] = hit
        idx, sign = hit
        vec[idx] += sign
    norm = float(np.linalg.norm(vec))
    if norm > 0.0:
        vec /= norm
    return vec


def _safe_stats(values: Iterable[float], default: float = 0.0) -> tuple[float, float, float, float, float]:
    arr = np.asarray(list(values), dtype=np.float64)
    if arr.size == 0:
        return default, 0.0, default, default, default
    return (
        float(arr.mean()),
        float(arr.std(ddof=0)),
        float(arr.min()),
        float(np.percentile(arr, 5)),
        float(arr.max()),
    )


def _entropy_from_counts(counts: Iterable[int]) -> float:
    arr = np.asarray([c for c in counts if c > 0], dtype=np.float64)
    if arr.size == 0:
        return 0.0
    p = arr / arr.sum()
    return float(-(p * np.log(p + EPS)).sum())


def trajectory_features(text: str, dim: int = 256) -> np.ndarray:
    segments = split_segments(text)
    words = word_tokens(text)
    seg_lens = np.asarray([len(word_tokens(s)) for s in segments], dtype=np.float64)
    vecs = np.vstack([hashed_segment_vector(s, dim=dim) for s in segments])
    nseg = vecs.shape[0]

    if nseg >= 2:
        adj_cos = np.sum(vecs[:-1] * vecs[1:], axis=1)
        steps = np.linalg.norm(vecs[1:] - vecs[:-1], axis=1)
        positions = np.arange(adj_cos.size, dtype=np.float64)
        slope = float(np.polyfit(positions, adj_cos, 1)[0]) if adj_cos.size >= 2 else 0.0
    else:
        adj_cos = np.asarray([1.0], dtype=np.float64)
        steps = np.asarray([0.0], dtype=np.float64)
        slope = 0.0

    if nseg >= 3:
        lag2 = np.sum(vecs[:-2] * vecs[2:], axis=1)
        lag2_mean = float(lag2.mean())
    else:
        lag2_mean = float(adj_cos.mean())

    centroid = vecs.mean(axis=0)
    c_norm = float(np.linalg.norm(centroid))
    if c_norm > 0:
        centroid = centroid / c_norm
        centroid_dist = 1.0 - np.sum(vecs * centroid[None, :], axis=1)
    else:
        centroid_dist = np.zeros(nseg, dtype=np.float64)

    adj_mean, adj_std, adj_min, adj_p05, adj_max = _safe_stats(adj_cos)
    step_mean, step_std, _step_min, _step_p05, step_max = _safe_stats(steps)
    path_len = float(steps.sum())
    net_disp = float(np.linalg.norm(vecs[-1] - vecs[0])) if nseg >= 2 else 0.0
    tort = min(path_len / max(net_disp, 1e-3), 100.0)
    punct_rate = sum(text.count(ch) for ch in ".,;:!?") / max(len(words), 1)

    return np.asarray(
        [
            math.log1p(len(words)),
            float(nseg),
            float(seg_lens.mean()) if seg_lens.size else 0.0,
            float(seg_lens.std(ddof=0)) if seg_lens.size else 0.0,
            float(seg_lens.min()) if seg_lens.size else 0.0,
            float(seg_lens.max()) if seg_lens.size else 0.0,
            float(punct_rate),
            adj_mean,
            adj_std,
            adj_min,
            adj_p05,
            adj_max,
            lag2_mean,
            float(np.sum(vecs[0] * vecs[-1])) if nseg >= 2 else 1.0,
            step_mean,
            step_std,
            step_max,
            path_len,
            net_disp,
            tort,
            float(centroid_dist.mean()),
            float(centroid_dist.max()),
            slope,
        ],
        dtype=np.float64,
    )


def _content_terms(words: list[str]) -> list[str]:
    return [
        w.lower()
        for w in words
        if len(w) >= 4 and not w.isdigit() and w.lower() not in STOPWORDS
    ]


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    union = len(a | b)
    return float(len(a & b) / union) if union else 0.0


def _discourse_counts(text: str) -> dict[str, int]:
    lowered = text.lower()
    counts: dict[str, int] = {}
    for cat, markers in DISCOURSE_MARKERS.items():
        total = 0
        for marker in markers:
            total += len(re.findall(r"\b" + re.escape(marker) + r"\b", lowered))
        counts[cat] = total
    return counts


def _dominant_discourse_category(text: str) -> str:
    counts = _discourse_counts(text)
    if not counts or max(counts.values()) == 0:
        return "none"
    return max(counts, key=counts.get)


def entity_discourse_features(text: str) -> np.ndarray:
    segments = split_segments(text)
    words_raw = word_tokens(text)
    words = [w.lower() for w in words_raw]
    n_words = max(len(words), 1)
    seg_word_lists = [word_tokens(s) for s in segments]
    seg_lens = np.asarray([len(ws) for ws in seg_word_lists], dtype=np.float64)
    seg_terms = [set(_content_terms(ws)) for ws in seg_word_lists]
    all_terms = _content_terms(words_raw)

    term_counts: dict[str, int] = {}
    term_seg_counts: dict[str, int] = {}
    for term in all_terms:
        term_counts[term] = term_counts.get(term, 0) + 1
    for terms in seg_terms:
        for term in terms:
            term_seg_counts[term] = term_seg_counts.get(term, 0) + 1

    repeated_terms = {t for t, c in term_seg_counts.items() if c >= 2}
    chain_max = max(term_seg_counts.values(), default=0)
    adj_overlaps = [_jaccard(seg_terms[i], seg_terms[i + 1]) for i in range(len(seg_terms) - 1)]
    adj_mean, adj_std, adj_min, _adj_p05, _adj_max = _safe_stats(adj_overlaps, default=1.0)
    repeated_coverage = (
        sum(1 for terms in seg_terms if terms & repeated_terms) / max(len(seg_terms), 1)
    )

    caps = [m.group(0).lower() for m in CAP_WORD_RE.finditer(text)]
    cap_unique = set(caps)
    cap_repeated = {c for c in cap_unique if caps.count(c) >= 2}
    pronouns = [w for w in words if w in PRONOUNS]
    discourse_counts = _discourse_counts(text)
    marker_total = sum(discourse_counts.values())
    seg_discourse = [_dominant_discourse_category(s) for s in segments]
    discourse_coverage = sum(1 for c in seg_discourse if c != "none") / max(len(seg_discourse), 1)
    transition_counts: dict[tuple[str, str], int] = {}
    for a, b in zip(seg_discourse[:-1], seg_discourse[1:]):
        transition_counts[(a, b)] = transition_counts.get((a, b), 0) + 1

    unresolved_proxy = 0
    seen_entity = False
    for terms, ws in zip(seg_terms, seg_word_lists):
        if terms:
            seen_entity = True
        if not seen_entity and any(w.lower() in PRONOUNS for w in ws):
            unresolved_proxy += 1

    connective_starts = 0
    start_markers = {m for markers in DISCOURSE_MARKERS.values() for m in markers}
    for seg in segments:
        lowered = seg.lower().strip()
        if any(lowered.startswith(marker + " ") for marker in start_markers):
            connective_starts += 1

    marker_rates = [discourse_counts[cat] / n_words for cat in DISCOURSE_CATEGORIES]

    return np.asarray(
        [
            math.log1p(len(words)),
            float(len(segments)),
            float(seg_lens.mean()) if seg_lens.size else 0.0,
            float(seg_lens.std(ddof=0)) if seg_lens.size else 0.0,
            len(all_terms) / n_words,
            len(set(all_terms)) / max(len(all_terms), 1),
            len(repeated_terms) / max(len(set(all_terms)), 1),
            chain_max / max(len(segments), 1),
            repeated_coverage,
            adj_mean,
            adj_std,
            adj_min,
            _jaccard(seg_terms[0], seg_terms[-1]) if seg_terms else 1.0,
            len(caps) / n_words,
            len(cap_repeated) / max(len(cap_unique), 1),
            len(pronouns) / n_words,
            len(pronouns) / max(len(set(all_terms)) + len(cap_unique), 1),
            unresolved_proxy / max(len(segments), 1),
            marker_total / n_words,
            _entropy_from_counts(discourse_counts.values()),
            _entropy_from_counts(transition_counts.values()),
            discourse_coverage,
            connective_starts / max(len(segments), 1),
            text.count('"') / max(len(text), 1),
            text.count(",") / n_words,
            (text.count(";") + text.count(":")) / n_words,
            text.count("\n\n") / max(len(segments), 1),
            *marker_rates,
        ],
        dtype=np.float64,
    )


def _ngram_repeat_rate(words: list[str], n: int) -> tuple[float, float]:
    if len(words) < n:
        return 0.0, 0.0
    grams = [tuple(words[i: i + n]) for i in range(len(words) - n + 1)]
    counts: dict[tuple[str, ...], int] = {}
    for gram in grams:
        counts[gram] = counts.get(gram, 0) + 1
    total = len(grams)
    distinct = len(counts)
    max_frac = max(counts.values()) / total if counts else 0.0
    return 1.0 - distinct / max(total, 1), max_frac


def tail_failure_features(text: str, dim: int = 256) -> np.ndarray:
    segments = split_segments(text)
    words_raw = word_tokens(text)
    words = [w.lower() for w in words_raw]
    n_words = max(len(words), 1)
    vecs = np.vstack([hashed_segment_vector(s, dim=dim) for s in segments])

    if len(segments) >= 2:
        adj_cos = np.sum(vecs[:-1] * vecs[1:], axis=1)
        jumps = 1.0 - adj_cos
    else:
        adj_cos = np.asarray([1.0], dtype=np.float64)
        jumps = np.asarray([0.0], dtype=np.float64)

    centroid = vecs.mean(axis=0)
    c_norm = float(np.linalg.norm(centroid))
    if c_norm > 0:
        centroid = centroid / c_norm
        centroid_dist = 1.0 - np.sum(vecs * centroid[None, :], axis=1)
    else:
        centroid_dist = np.zeros(len(segments), dtype=np.float64)

    steps = np.linalg.norm(vecs[1:] - vecs[:-1], axis=1) if len(segments) >= 2 else np.asarray([0.0])
    path_len = float(steps.sum())
    net_disp = float(np.linalg.norm(vecs[-1] - vecs[0])) if len(segments) >= 2 else 0.0
    tort = min(path_len / max(net_disp, 1e-3), 100.0)

    unigram_counts: dict[str, int] = {}
    for word in words:
        unigram_counts[word] = unigram_counts.get(word, 0) + 1
    top_word_rate = max(unigram_counts.values(), default=0) / n_words
    bigram_repeat, max_bigram_frac = _ngram_repeat_rate(words, 2)
    trigram_repeat, _max_trigram_frac = _ngram_repeat_rate(words, 3)
    distinct_deficit = 1.0 - len(set(words)) / n_words

    seg_lens = np.asarray([len(word_tokens(s)) for s in segments], dtype=np.float64)
    if seg_lens.size >= 2:
        len_jumps = np.abs(np.diff(seg_lens)) / (float(seg_lens.mean()) + 1.0)
        max_len_jump = float(len_jumps.max())
    else:
        max_len_jump = 0.0
    short_seg_rate = float(np.mean(seg_lens <= 4)) if seg_lens.size else 0.0

    seg_terms = [set(_content_terms(word_tokens(s))) for s in segments]
    adj_overlaps = [_jaccard(seg_terms[i], seg_terms[i + 1]) for i in range(len(seg_terms) - 1)]
    overlap_deficit = 1.0 - min(adj_overlaps, default=1.0)
    dropouts = 0
    for prev_terms, cur_terms in zip(seg_terms[:-1], seg_terms[1:]):
        if prev_terms and not (prev_terms & cur_terms):
            dropouts += 1
    entity_dropout = dropouts / max(len(seg_terms) - 1, 1)

    pronoun_without_entity = 0
    for terms, seg in zip(seg_terms, segments):
        seg_words = lower_words(seg)
        if any(w in PRONOUNS for w in seg_words) and not terms:
            pronoun_without_entity += 1

    marker_flags = [1 if _dominant_discourse_category(s) != "none" else 0 for s in segments]
    max_gap = 0
    cur_gap = 0
    for flag in marker_flags:
        if flag:
            max_gap = max(max_gap, cur_gap)
            cur_gap = 0
        else:
            cur_gap += 1
    max_gap = max(max_gap, cur_gap)

    nonalpha = sum(1 for w in words_raw if not any(ch.isalpha() for ch in w)) / n_words

    return np.asarray(
        [
            float(jumps.max()),
            float(np.percentile(jumps, 95)),
            1.0 - float(np.percentile(adj_cos, 5)),
            tort,
            float(centroid_dist.max()),
            top_word_rate,
            bigram_repeat,
            trigram_repeat,
            max_bigram_frac,
            distinct_deficit,
            max_len_jump,
            short_seg_rate,
            overlap_deficit,
            entity_dropout,
            pronoun_without_entity / max(len(segments), 1),
            max_gap / max(len(segments), 1),
            text.count("<|endoftext|>") / n_words,
            nonalpha,
        ],
        dtype=np.float64,
    )


def feature_matrix(
    texts: list[str],
    fn: Callable[[str], np.ndarray],
    log_every: int = 0,
    label: str = "features",
) -> np.ndarray:
    rows = []
    for i, text in enumerate(texts, 1):
        rows.append(fn(text))
        if log_every and (i % log_every == 0 or i == len(texts)):
            print(f"  [{label}] {i}/{len(texts)}")
    mat = np.vstack(rows).astype(np.float64, copy=False)
    return np.nan_to_num(mat, nan=0.0, posinf=1e6, neginf=-1e6)


def standardize_from_ref(ref: np.ndarray, other: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mu = ref.mean(axis=0, keepdims=True)
    sigma = ref.std(axis=0, ddof=0, keepdims=True)
    sigma = np.where(sigma < 1e-8, 1.0, sigma)
    return (ref - mu) / sigma, (other - mu) / sigma


def pairwise_distances(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    x2 = np.sum(x * x, axis=1, keepdims=True)
    y2 = np.sum(y * y, axis=1, keepdims=True).T
    d2 = np.maximum(x2 + y2 - 2.0 * (x @ y.T), 0.0)
    return np.sqrt(d2).astype(np.float64, copy=False)


def energy_distance(x: np.ndarray, y: np.ndarray) -> float:
    dxy = pairwise_distances(x, y).mean()
    dxx = pairwise_distances(x, x).mean()
    dyy = pairwise_distances(y, y).mean()
    return float(max(0.0, 2.0 * dxy - dxx - dyy))


def median_bandwidth(x: np.ndarray, y: np.ndarray, seed: int, max_points: int = 512) -> float:
    pooled = np.vstack([x, y])
    rng = np.random.default_rng(seed)
    if pooled.shape[0] > max_points:
        pooled = pooled[rng.choice(pooled.shape[0], size=max_points, replace=False)]
    d = pairwise_distances(pooled, pooled)
    vals = d[np.triu_indices_from(d, k=1)]
    vals = vals[vals > 1e-8]
    if vals.size == 0:
        return 1.0
    return float(np.median(vals))


def rbf_mmd2(x: np.ndarray, y: np.ndarray, sigma: float) -> float:
    gamma = 1.0 / (2.0 * sigma * sigma + EPS)
    dxx = pairwise_distances(x, x)
    dyy = pairwise_distances(y, y)
    dxy = pairwise_distances(x, y)
    kxx = np.exp(-(dxx * dxx) * gamma).mean()
    kyy = np.exp(-(dyy * dyy) * gamma).mean()
    kxy = np.exp(-(dxy * dxy) * gamma).mean()
    return float(max(0.0, kxx + kyy - 2.0 * kxy))


def multi_rbf_mmd2(x: np.ndarray, y: np.ndarray, seed: int) -> tuple[float, float, list[dict[str, float]]]:
    base = median_bandwidth(x, y, seed=seed)
    rows = []
    vals = []
    for scale in (0.5, 1.0, 2.0):
        sigma = max(base * scale, 1e-6)
        value = rbf_mmd2(x, y, sigma)
        rows.append({"sigma": sigma, "mmd2": value})
        vals.append(value)
    return float(np.mean(vals)), base, rows


