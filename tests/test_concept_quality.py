"""
Concept-label quality.

A concept becomes the answer on a flashcard, so a fragment like "Chlorophyll
Absorbs" is not a cosmetic problem — it is a card the learner is asked to
recall. Labels must read as noun phrases, which means they must not span a
finite verb.

These tests pin the rule and its known edge cases, so the heuristic can be
tuned later without silently regressing.
"""

from agents.material_analyzer import MaterialAnalyzer, _is_verbal

BIOLOGY = (
    "Photosynthesis converts light energy into chemical energy. "
    "The Calvin cycle fixes carbon dioxide into glucose. "
    "Chlorophyll absorbs light in the thylakoid membrane."
)

HISTORY = (
    "The French Revolution began in 1789. The storming of the Bastille became "
    "a turning point. The Declaration of the Rights of Man proclaimed universal "
    "liberty. The National Assembly abolished feudal privileges."
)


def _concepts(title, text):
    return [c.concept for c in MaterialAnalyzer().analyze(title, text).concepts]


# ── the verb detector ─────────────────────────────────────────────────────────

def test_present_tense_verbs_are_detected():
    for word in ("converts", "absorbs", "fixes", "provides", "increases"):
        assert _is_verbal(word), word


def test_past_tense_and_participles_are_detected():
    for word in ("abolished", "proclaimed", "published", "measured"):
        assert _is_verbal(word), word


def test_irregular_pasts_are_detected():
    for word in ("became", "began", "brought", "wrote", "understood"):
        assert _is_verbal(word), word


def test_nouns_are_not_mistaken_for_verbs():
    """The -ed rule is morphological, so its false positives are the risk."""
    for word in ("speed", "breed", "method", "hundred", "sacred", "membrane",
                 "glucose", "revolution", "assembly"):
        assert not _is_verbal(word), word


# ── the effect on extracted labels ────────────────────────────────────────────

def test_no_concept_label_spans_a_verb():
    for title, text in (("Photosynthesis", BIOLOGY), ("French Revolution", HISTORY)):
        for concept in _concepts(title, text):
            for token in concept.split():
                assert not _is_verbal(token), f"{concept!r} contains the verb {token!r}"


def test_known_bad_labels_are_gone():
    """Each of these was produced before the rule existed."""
    labels = {c.lower() for c in _concepts("Photosynthesis", BIOLOGY)}
    for bad in ("chlorophyll absorbs", "fixes carbon", "converts"):
        assert bad not in labels

    hist = {c.lower() for c in _concepts("French Revolution", HISTORY)}
    for bad in ("bastille became", "abolished feudal", "proclaimed universal", "began"):
        assert bad not in hist


def test_real_concepts_survive():
    """Precision must not have been bought by dropping everything."""
    bio = {c.lower() for c in _concepts("Photosynthesis", BIOLOGY)}
    assert {"calvin cycle", "thylakoid membrane", "chlorophyll"} <= bio

    hist = {c.lower() for c in _concepts("French Revolution", HISTORY)}
    assert {"french revolution", "national assembly"} <= hist


def test_dropping_a_verb_bigram_lets_the_real_phrase_form():
    """'fixes carbon' used to consume 'carbon', leaving the orphan 'dioxide'.
    Removing the fragment lets the actual noun phrase appear instead."""
    bio = {c.lower() for c in _concepts("Photosynthesis", BIOLOGY)}
    assert "carbon dioxide" in bio
