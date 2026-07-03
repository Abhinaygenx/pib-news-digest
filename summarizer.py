"""
summarizer.py — Lightweight extractive summarization with no external API
and no heavyweight NLP downloads (works offline, works in CI out of the box).

Approach: frequency-based sentence scoring (a simplified Luhn/TextRank-style
method). Common words are down-weighted using a small stopword list, each
sentence is scored by the sum of its significant-word frequencies (normalized
by sentence length), the lead sentence gets a small boost (press releases
front-load the key fact), and the top-N scoring sentences are returned in
their original order so the summary still reads coherently.

This is lower quality than an LLM-based summary, but it's free, fast, and
has zero moving parts to break in an automated pipeline.
"""

import re

STOPWORDS = set("""
a an the and or but if while of to in on for with as by is are was were be
been being this that these those it its it's from at into about which who
whom will shall would could should can may might not no nor so than then
there here also more most such only own same too very s t can will just don
should now over under again further once here there when where why how all
any both each few other some such our ours you your yours he him his she her
hers they them their theirs we us
""".split())

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\u2018\u201c])")
WORD_RE = re.compile(r"[A-Za-z]+")


def _split_sentences(text):
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    sentences = SENTENCE_SPLIT_RE.split(text)
    return [s.strip() for s in sentences if len(s.strip()) > 15]


def summarize(text, num_sentences=3):
    """Return a short extractive summary of `text` as a single string."""
    sentences = _split_sentences(text)
    if not sentences:
        return text.strip()[:280]
    if len(sentences) <= num_sentences:
        return " ".join(sentences)

    words = [w.lower() for w in WORD_RE.findall(text)]
    freq = {}
    for w in words:
        if w in STOPWORDS or len(w) <= 2:
            continue
        freq[w] = freq.get(w, 0) + 1

    if not freq:
        return " ".join(sentences[:num_sentences])

    max_freq = max(freq.values())
    for w in freq:
        freq[w] /= max_freq

    scored = []
    for i, sentence in enumerate(sentences):
        sent_words = [w.lower() for w in WORD_RE.findall(sentence)]
        if not sent_words:
            continue
        score = sum(freq.get(w, 0.0) for w in sent_words) / (len(sent_words) ** 0.5)
        if i == 0:
            score += 0.2  # lede boost: PIB releases state the key fact up front
        scored.append((score, i, sentence))

    top = sorted(scored, key=lambda x: -x[0])[:num_sentences]
    top_in_order = sorted(top, key=lambda x: x[1])
    return " ".join(s for _, _, s in top_in_order)


if __name__ == "__main__":
    sample = (
        "The Ministry of Health today launched a new digital initiative to "
        "improve rural healthcare access. Officials said the platform will "
        "connect over 10000 primary health centres. The Union Minister "
        "highlighted that this is part of a broader push towards digital "
        "governance. He added that the rollout would happen in three phases "
        "over the next two years, starting with five states."
    )
    print(summarize(sample, 2))
