"""
Agent 1: Material Analyzer — from-scratch NLP pipeline.

No external API calls. Every concept in the knowledge map is extracted,
scored, and typed using classical NLP + linear algebra only.

Pipeline
--------
1.  Sentence segmentation + lowercasing
2.  Tokenization, stop-word removal, lightweight suffix stripping (pseudo-stem)
3.  Candidate concept extraction: TF-IDF weighted unigrams + bigrams
4.  LSA (Latent Semantic Analysis): TruncatedSVD on the TF-IDF term-doc matrix
    → each concept embedded as a latent topic vector
5.  TextRank: build concept-similarity graph, run PageRank power iteration
    → centrality score = conceptual importance to this text
6.  Difficulty scoring: position in document + term rarity + average token length
7.  Concept type classification: regex heuristics (factual / conceptual / procedural)
8.  Related concepts: cosine similarity in LSA space (top 3 neighbours)
9.  Study order: topological sort — foundational → intermediate → advanced,
    with TextRank centrality breaking ties within each tier

Mathematical notes
------------------
TF-IDF:
    tf(t, d)  = count(t, d) / |d|
    idf(t)    = log((1 + N) / (1 + df(t))) + 1          (sklearn-style smooth)
    tfidf(t,d) = tf(t,d) × idf(t)

SVD / LSA:
    Decompose M ∈ ℝ^{T×D} (terms × docs) as U Σ Vᵀ
    Truncate to k=min(20, rank) components
    Concept vector = row of U[concept_term_idx, :k]

PageRank (power iteration):
    r ← d M r + (1-d)/n 1             d = 0.85 damping
    M[i,j] = cos(c_i, c_j) / Σ_k cos(c_i, c_k)   (column-stochastic)
    Converges in ≤ 100 iterations for n < 200 concepts
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Optional

import numpy as np

from schemas.session import KnowledgeConcept, KnowledgeMap

# ── Stop-word list ─────────────────────────────────────────────────────────────

_STOPWORDS = frozenset("""
a about above across after again against all also am an and any are aren't as at
be because been before being below between both but by can't cannot could couldn't
did didn't do does doesn't doing don't down during each few for from further get
got had hadn't has hasn't have haven't having he he'd he'll he's hence her here
here's hers herself him himself his how how's i i'd i'll i'm i've if in into is
isn't it it's its itself let's me more most mustn't my myself no nor not of off on
once only or other ought our ours ourselves out over own same shan't she she'd
she'll she's should shouldn't so some such than that that's the their theirs them
themselves then there there's therefore these they they'd they'll they're they've
this those through to too under until up very was wasn't we we'd we'll we're we've
were weren't what what's when when's where where's which while who who's whom why
why's will with won't would wouldn't you you'd you'll you're you've your yours
yourself yourselves also just however therefore thus hence moreover furthermore
although though even still yet already often always usually typically generally
eg e.g. i.e. etc see note also another one two three four five can may might
will shall could would should must need want use used using uses make made makes
makes making given based using since because hence where whose within without
across around along through throughout between among upon after before into onto
toward towards below above beside next near here there when where how what
""".split())

# ── Regex patterns for concept-type classification ─────────────────────────────

_PROCEDURAL_VERBS = re.compile(
    r"\b(calculat|comput|deriv|solv|apply|implement|perform|execut|run|"
    r"measur|estimat|optimiz|minimiz|maximiz|iterat|simulat|train|fit|"
    r"evaluat|validat|test|build|construct|design|creat|generat|produc|"
    r"classif|predict|detect|segment|cluster|rank|sort|filter|transform|"
    r"normaliz|standardiz|regulariz|penaliz|weight|aggregat|integrat)\w*\b",
    re.IGNORECASE,
)

_FACTUAL_PATTERNS = re.compile(
    r"\b(\d{4}|\d+\s*%|\d+\.\d+|[A-Z][a-z]+\s+[A-Z][a-z]+|"  # dates, numbers, proper names
    r"theorem|lemma|axiom|corollary|definition|equation|formula|constant|"
    r"law of|principle of|rule of)\b",
    re.IGNORECASE,
)

_CONCEPTUAL_MARKERS = re.compile(
    r"\b(is defined as|refers to|means|represents|describes|denotes|"
    r"characterize[sd]|understanding|framework|concept|theory|model|"
    r"approach|assumption|property|notion|abstraction|paradigm|perspective)\b",
    re.IGNORECASE,
)

# ── Lightweight suffix stripper (no external library required) ────────────────

_SUFFIXES = [
    "ational", "tional", "enci", "anci", "izer", "iser", "ation", "ness",
    "ment", "ness", "ful", "ous", "ive", "ize", "ise", "ify", "ing",
    "tion", "sion", "ies", "ed", "ly", "er", "es", "s",
]

def _stem(word: str) -> str:
    """
    Very lightweight suffix stripping — not Porter, just removes common
    English inflections so "learning" and "learned" map to "learn".
    """
    w = word.lower()
    if len(w) <= 4:
        return w
    for sfx in _SUFFIXES:
        if w.endswith(sfx) and len(w) - len(sfx) >= 3:
            return w[: -len(sfx)]
    return w


def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, split on whitespace."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s\-]", " ", text)
    return [t.strip("-") for t in text.split() if len(t.strip("-")) > 1]


def _sentences(text: str) -> list[str]:
    """
    Split on:
      (a) sentence-ending punctuation (.!?) followed by whitespace + uppercase
      (b) paragraph breaks (one or more blank lines)

    This prevents cross-paragraph bigram artifacts like title + first sentence.
    """
    # First split on paragraph breaks
    paragraphs = re.split(r"\n\s*\n", text)
    parts: list[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # Within each paragraph, split on sentence boundaries
        sents = re.split(r"(?<=[.!?])\s+(?=[A-Z])", para)
        parts.extend(s.strip() for s in sents if s.strip())
    return parts


# ── TF-IDF ─────────────────────────────────────────────────────────────────────

def _compute_tfidf(
    docs: list[list[str]],
) -> tuple[dict[str, np.ndarray], list[str]]:
    """
    Compute TF-IDF vectors for a list of token-lists (one per sentence/doc).

    Returns
    -------
    tfidf_vectors : dict[term → np.ndarray of shape (n_docs,)]
    vocab         : sorted list of all terms (used to build the term-doc matrix)
    """
    n_docs = len(docs)
    tf: list[Counter] = [Counter(d) for d in docs]
    df: Counter = Counter()
    for doc in docs:
        df.update(set(doc))

    vocab = sorted(df.keys())
    term_idx = {t: i for i, t in enumerate(vocab)}
    n_terms = len(vocab)

    # Build term-doc matrix (terms × docs)
    M = np.zeros((n_terms, n_docs), dtype=float)
    for j, (doc, tf_j) in enumerate(zip(docs, tf)):
        for t, cnt in tf_j.items():
            i = term_idx[t]
            raw_tf = cnt / len(doc) if doc else 0.0
            idf    = math.log((1 + n_docs) / (1 + df[t])) + 1.0
            M[i, j] = raw_tf * idf

    # L2-normalise each document vector (column)
    norms = np.linalg.norm(M, axis=0, keepdims=True)
    norms[norms == 0] = 1.0
    M /= norms

    tfidf_vectors = {t: M[i] for t, i in term_idx.items()}
    return tfidf_vectors, vocab, M


# ── LSA: truncated SVD ──────────────────────────────────────────────────────────

def _lsa(M: np.ndarray, k: Optional[int] = None) -> np.ndarray:
    """
    Latent Semantic Analysis via numpy's full SVD, retaining the top k
    singular vectors.

    Parameters
    ----------
    M : term-doc matrix (n_terms × n_docs)
    k : number of latent components (default: min(20, min(M.shape)-1))

    Returns
    -------
    U_k : (n_terms × k) matrix — each row is the latent embedding of one term
    """
    n_terms, n_docs = M.shape
    k = k or min(20, min(n_terms, n_docs) - 1)
    k = max(1, k)

    U, s, Vt = np.linalg.svd(M, full_matrices=False)
    return U[:, :k] * s[:k]  # shape (n_terms, k)


# ── TextRank ────────────────────────────────────────────────────────────────────

def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _textrank(
    concept_embeddings: list[np.ndarray],
    damping: float = 0.85,
    max_iter: int = 100,
    tol: float = 1e-6,
) -> np.ndarray:
    """
    PageRank power iteration on the concept-similarity graph.

    Nodes: concepts (n total)
    Edge weight w[i,j] = max(0, cos(embed_i, embed_j))    (non-negative)

    Returns
    -------
    scores : np.ndarray of shape (n,) — centrality scores, sum = 1
    """
    n = len(concept_embeddings)
    if n == 0:
        return np.array([], dtype=float)
    if n == 1:
        return np.array([1.0])

    # Build similarity matrix
    W = np.zeros((n, n), dtype=float)
    for i in range(n):
        for j in range(n):
            if i != j:
                W[i, j] = max(0.0, _cosine_sim(concept_embeddings[i], concept_embeddings[j]))

    # Column-stochastic (handle zero columns)
    col_sums = W.sum(axis=0)
    col_sums[col_sums == 0] = 1.0
    W /= col_sums

    # Power iteration
    r = np.ones(n, dtype=float) / n
    uniform = np.ones(n, dtype=float) / n
    for _ in range(max_iter):
        r_new = damping * W @ r + (1.0 - damping) * uniform
        if np.linalg.norm(r_new - r) < tol:
            break
        r = r_new

    return r_new / r_new.sum()


# ── Surface-form recovery ──────────────────────────────────────────────────────

def _build_stem_surface_map(text: str) -> dict[str, str]:
    """
    Map each stem to its most frequently occurring original (unstemmed, lowercase)
    form in the text.  This lets us display 'active_recall' instead of 'activ recall'.
    """
    words = _tokenize(text)   # lowercase, no stemming
    stem_counts: dict[str, Counter] = defaultdict(Counter)
    for w in words:
        if len(w) >= 3:
            stem_counts[_stem(w)][w] += 1
    return {stem: counts.most_common(1)[0][0] for stem, counts in stem_counts.items()}


# ── Concept extraction ─────────────────────────────────────────────────────────

# Generic high-frequency words that look informative but aren't real concepts
_CONCEPT_BLACKLIST = frozenset({
    # Too generic / functional
    "learn", "study", "information", "process", "type", "term", "form", "way",
    "effect", "result", "level", "number", "approach", "method", "technique",
    "practice", "data", "time", "day", "week", "year", "system", "human",
    "brain", "memory", "recall", "review", "session", "material", "concept",
    "knowledge", "skill", "task", "item", "group", "subject", "student",
    "research", "example", "case", "test", "exam", "question", "answer",
    "score", "rate", "model", "based", "using", "used", "exp", "function",
    "value", "variable", "parameter", "output", "input",
    # Action verbs that are not concepts
    "improve", "increase", "decrease", "show", "find", "make", "help",
    "allow", "include", "involve", "involves", "require", "suggest", "note",
    "refer", "compare", "describe", "describes", "explain", "define", "represent",
    "apply", "perform", "produce", "stimulate", "stimulating", "strengthen",
    "strengthens", "attempt", "force", "switch", "switching", "improve",
    # Too short / noise words after stemming
    "passive", "active", "rapid", "simple", "specific", "different",
    "effective", "long-term", "short-term", "higher", "lower", "better",
    "attempt", "beyond", "during", "rapid", "among", "most", "first", "next",
})


def _extract_concepts(
    text: str,
    tfidf_vecs: dict[str, np.ndarray],
    term_lsa: dict[str, np.ndarray],
    vocab: list[str],
    stem_surface: dict[str, str],
    max_concepts: int = 25,
) -> list[dict]:
    """
    Extract top concepts as TF-IDF-scored n-grams (unigrams + bigrams).

    Unigrams use the stem-to-surface map so display forms are readable.
    Bigrams are extracted from the original (unstemmed) tokenised text.

    Returns list of dicts: {term: canonical_key, surface: display_name, tfidf_score: float}
    """
    # --- Unigrams: score by sum of TF-IDF over all sentences ---
    unigram_scores: dict[str, float] = {}   # stem → score
    for stem, vec in tfidf_vecs.items():
        surface = stem_surface.get(stem, stem)
        if surface in _STOPWORDS or stem in _STOPWORDS:
            continue
        if len(surface) <= 4:              # short words are nearly always noise
            continue
        if surface in _CONCEPT_BLACKLIST or stem in _CONCEPT_BLACKLIST:
            continue
        unigram_scores[stem] = float(np.sum(vec))

    # --- Bigrams: consecutive non-stopword pairs within the SAME sentence ---
    # (tokenizing per sentence prevents cross-sentence boundary artifacts)
    bigram_scores: dict[str, float] = {}    # "word1 word2" surface → score
    for sent in _sentences(text):
        words_in_sent = _tokenize(sent)
        for i in range(len(words_in_sent) - 1):
            w1, w2 = words_in_sent[i], words_in_sent[i + 1]
            if w1 in _STOPWORDS or w2 in _STOPWORDS:
                continue
            if len(w1) <= 3 or len(w2) <= 3:
                continue
            if w1 in _CONCEPT_BLACKLIST or w2 in _CONCEPT_BLACKLIST:
                continue
            bigram_surface = f"{w1} {w2}"
            s1 = unigram_scores.get(_stem(w1), 0.0)
            s2 = unigram_scores.get(_stem(w2), 0.0)
            if s1 == 0 and s2 == 0:
                continue   # both components have zero TF-IDF — skip
            bigram_scores[bigram_surface] = (s1 + s2) * 0.75  # slight bigram discount

    # Merge: bigrams can supersede constituent unigrams
    # Build score dict keyed by surface form
    combined: dict[str, tuple[str, float]] = {}   # surface → (canonical_key, score)
    for stem, score in unigram_scores.items():
        surface = stem_surface.get(stem, stem)
        combined[surface] = (stem, score)
    for surface, score in bigram_scores.items():
        combined[surface] = (surface, score)

    # Rank and deduplicate
    ranked = sorted(combined.items(), key=lambda x: x[1][1], reverse=True)

    selected: list[dict] = []
    covered_surfaces: set[str] = set()
    for surface, (canonical, score) in ranked:
        parts = surface.split()
        # Skip if any constituent is already covered by a selected bigram
        if any(p in covered_surfaces for p in parts):
            continue
        covered_surfaces.update(parts)
        selected.append({"term": canonical, "surface": surface, "tfidf_score": score})
        if len(selected) >= max_concepts:
            break

    return selected


# ── Difficulty scoring ─────────────────────────────────────────────────────────

def _difficulty_score(
    term: str,
    text: str,
    tfidf_score: float,
    all_scores: list[float],
) -> str:
    """
    Heuristic difficulty classification:
      - avg_score_rank: where does this term rank in the overall importance distribution?
      - document_position: first occurrence as fraction of total text length
      - term complexity: average token length (longer = more technical)

    Difficulty tiers:
      foundational : top 40% by TF-IDF AND first half of document
      intermediate : middle band
      advanced     : low TF-IDF (niche/specialised) OR second half of document
    """
    tokens = term.split()
    avg_token_len = sum(len(t) for t in tokens) / max(len(tokens), 1)

    # Rank (0 = least important, 1 = most important)
    if all_scores:
        score_pct = sum(1 for s in all_scores if s <= tfidf_score) / len(all_scores)
    else:
        score_pct = 0.5

    # First occurrence position (0 = beginning, 1 = end)
    lower_text = text.lower()
    idx = lower_text.find(term.lower().split()[0])
    pos = idx / max(len(lower_text), 1)

    # Composite: high score + early position + short token → foundational
    if score_pct >= 0.65 and pos < 0.55 and avg_token_len <= 8:
        return "foundational"
    elif score_pct < 0.35 or pos > 0.65 or avg_token_len > 10:
        return "advanced"
    else:
        return "intermediate"


# ── Concept-type classification ────────────────────────────────────────────────

def _classify_type(term: str, text: str) -> str:
    """
    Classify each concept as factual / conceptual / procedural using
    regex patterns on the surrounding context.
    """
    # Find all sentences containing the term
    sents = [
        s for s in _sentences(text)
        if term.lower().split()[0] in s.lower()
    ]
    context = " ".join(sents[:5])  # look at up to 5 sentences

    n_procedural = len(_PROCEDURAL_VERBS.findall(context))
    n_factual    = len(_FACTUAL_PATTERNS.findall(context))
    n_conceptual = len(_CONCEPTUAL_MARKERS.findall(context))

    # Tie-break: procedural > factual > conceptual
    if n_procedural >= max(n_factual, n_conceptual) and n_procedural > 0:
        return "procedural"
    if n_factual >= n_conceptual and n_factual > 0:
        return "factual"
    return "conceptual"  # default for abstract topics


# ── Related concepts ───────────────────────────────────────────────────────────

def _find_related(
    term: str,
    concept_embeddings: dict[str, np.ndarray],
    top_k: int = 3,
) -> list[str]:
    """
    Find the top_k most semantically similar concepts using cosine similarity
    in LSA embedding space.
    """
    if term not in concept_embeddings:
        return []
    target = concept_embeddings[term]
    sims = {
        other: _cosine_sim(target, emb)
        for other, emb in concept_embeddings.items()
        if other != term
    }
    return [k for k, _ in sorted(sims.items(), key=lambda x: x[1], reverse=True)[:top_k]]


# ── Study order ────────────────────────────────────────────────────────────────

_DIFFICULTY_ORDER = {"foundational": 0, "intermediate": 1, "advanced": 2}

def _study_order(
    concepts: list[KnowledgeConcept],
    pagerank_scores: dict[str, float],
) -> list[str]:
    """
    Compute the suggested study order:
      1. Sort by difficulty tier (foundational → intermediate → advanced)
      2. Within each tier, sort by PageRank centrality (higher = study first,
         because central concepts appear in more other concepts' definitions)
    """
    def sort_key(c: KnowledgeConcept) -> tuple[int, float]:
        tier = _DIFFICULTY_ORDER.get(c.difficulty, 1)
        centrality = pagerank_scores.get(c.concept, 0.0)
        return (tier, -centrality)  # ascending tier, descending centrality

    return [c.concept for c in sorted(concepts, key=sort_key)]


# ── LSA embedding for a concept term ──────────────────────────────────────────

def _concept_embedding(
    term: str,
    term_lsa: np.ndarray,
    vocab: list[str],
    vocab_idx: dict[str, int],
) -> np.ndarray:
    """
    Embed a concept (possibly multi-word) as the mean of its constituent
    term vectors in LSA space.
    """
    tokens = term.split()
    vecs = []
    for t in tokens:
        t_stem = _stem(t)
        if t_stem in vocab_idx:
            vecs.append(term_lsa[vocab_idx[t_stem]])
        elif t in vocab_idx:
            vecs.append(term_lsa[vocab_idx[t]])
    if not vecs:
        # fallback: zero vector (will be excluded from related-concept lookup)
        return np.zeros(term_lsa.shape[1] if term_lsa.ndim > 1 else 1)
    return np.mean(vecs, axis=0)


# ── Main analyzer class ────────────────────────────────────────────────────────

class MaterialAnalyzer:
    """
    From-scratch NLP material analyzer.

    Replaces the Claude API with a classical NLP pipeline:
      TF-IDF → LSA (SVD) → TextRank → heuristic type/difficulty classification.
    """

    def analyze(self, title: str, raw_text: str) -> KnowledgeMap:
        """
        Analyze a piece of learning material and return a structured KnowledgeMap.

        Parameters
        ----------
        title    : title of the material (prepended to text for context)
        raw_text : the full text of the material

        Returns
        -------
        KnowledgeMap with concepts, difficulties, types, relations, and study order
        """
        text = f"{title}\n\n{raw_text}"

        # 1. Sentence segmentation
        sents = _sentences(text)
        if not sents:
            sents = [text]

        # 2. Tokenize each sentence; apply stemming
        docs: list[list[str]] = []
        for s in sents:
            tokens = [_stem(t) for t in _tokenize(s) if t not in _STOPWORDS and len(t) > 2]
            if tokens:
                docs.append(tokens)

        if not docs:
            return KnowledgeMap(title=title, total_concepts=0, concepts=[], suggested_study_order=[])

        # 3. TF-IDF
        tfidf_vecs, vocab, M = _compute_tfidf(docs)
        vocab_idx = {t: i for i, t in enumerate(vocab)}

        # 4. LSA
        if M.shape[0] >= 2 and M.shape[1] >= 2:
            term_lsa = _lsa(M)                           # shape (n_terms, k)
        else:
            term_lsa = M                                 # degenerate case

        # 4b. Build stem → surface form map (for readable concept names)
        stem_surface = _build_stem_surface_map(text)

        # 5. Extract candidate concepts (surface forms are now proper English words)
        raw_concepts = _extract_concepts(text, tfidf_vecs, term_lsa, vocab, stem_surface)
        if not raw_concepts:
            return KnowledgeMap(title=title, total_concepts=0, concepts=[], suggested_study_order=[])

        all_tfidf_scores = [c["tfidf_score"] for c in raw_concepts]

        # 6. Embed each concept in LSA space (use canonical stem key for lookup)
        concept_embeddings: dict[str, np.ndarray] = {}
        for c in raw_concepts:
            concept_embeddings[c["surface"]] = _concept_embedding(
                c["term"], term_lsa, vocab, vocab_idx
            )

        # 7. TextRank — run on surface-form keyed embeddings
        emb_list = [concept_embeddings[c["surface"]] for c in raw_concepts]
        pr_scores = _textrank(emb_list)
        pagerank_map = {
            raw_concepts[i]["surface"]: float(pr_scores[i])
            for i in range(len(raw_concepts))
        }

        # 8. Build KnowledgeConcept objects
        concepts: list[KnowledgeConcept] = []

        for c in raw_concepts:
            surface = c["surface"]
            # Display form: title-case the original surface
            display = surface.title()

            difficulty = _difficulty_score(surface, text, c["tfidf_score"], all_tfidf_scores)
            ctype      = _classify_type(surface, text)
            related    = _find_related(surface, concept_embeddings, top_k=3)

            concepts.append(KnowledgeConcept(
                concept          = display,
                difficulty       = difficulty,
                concept_type     = ctype,
                related_concepts = [r.title() for r in related],
            ))

        # 9. Suggested study order (uses display names)
        display_to_pr = {c["surface"].title(): pagerank_map[c["surface"]] for c in raw_concepts}
        order = _study_order(concepts, display_to_pr)

        return KnowledgeMap(
            title                 = title,
            total_concepts        = len(concepts),
            concepts              = concepts,
            suggested_study_order = order,
        )
