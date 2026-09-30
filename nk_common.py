"""Shared helpers for the negative keyword scripts (standard library only)."""
import csv
import re

MATCH_TYPES = ("broad", "phrase", "exact")


def tokens(text):
    """Lowercase word tokens. Apostrophes are dropped, other punctuation splits words."""
    text = (text or "").lower().replace("'", "").replace("\u2019", "")
    return re.findall(r"[^\W_]+", text, flags=re.UNICODE)


def blocks(neg_tokens, query_tokens, match):
    """Would a negative (already tokenized) block this query under the match type?

    broad  : all negative words appear in the query, any order
    phrase : negative words appear contiguously and in order
    exact  : query is exactly the negative words, nothing extra
    Negatives do not match plurals, misspellings or close variants.
    """
    if not neg_tokens:
        return False
    if match == "broad":
        return set(neg_tokens) <= set(query_tokens)
    if match == "phrase":
        n = len(neg_tokens)
        return any(query_tokens[i:i + n] == neg_tokens for i in range(len(query_tokens) - n + 1))
    if match == "exact":
        return neg_tokens == query_tokens
    return False


def contains_phrase(haystack_tokens, needle_tokens):
    return blocks(needle_tokens, haystack_tokens, "phrase")


def parse_match(value):
    v = (value or "").strip().lower()
    for name in MATCH_TYPES:
        if name in v:
            return name
    return None


def split_syntax(keyword):
    """'[x]' -> ('x','exact'), '"x"' -> ('x','phrase'), '-x' or 'x' -> ('x', None)."""
    k = (keyword or "").strip()
    if len(k) >= 2 and k[0] == "[" and k[-1] == "]":
        return k[1:-1].strip(), "exact"
    if len(k) >= 2 and k[0] == '"' and k[-1] == '"':
        return k[1:-1].strip(), "phrase"
    return k.lstrip("-").strip(), None


def norm_level(value):
    v = (value or "").strip().lower()
    if "ad" in v and "group" in v:
        return "ad_group"
    if "campaign" in v:
        return "campaign"
    if "shared" in v or "list" in v:
        return "shared_list"
    if "account" in v:
        return "account"
    return None


def key_norm(name):
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")


def nrow(row):
    """Row dict with normalized keys (lowercase, underscores)."""
    return {key_norm(k): (v if v is not None else "") for k, v in row.items() if k is not None}


def pick(nr, *names):
    for n in names:
        v = nr.get(n)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return ""


def split_list(value):
    return [p.strip() for p in re.split(r"\s*[;|]\s*", value or "") if p.strip()]


def read_text(path):
    raw = open(path, "rb").read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16"), "utf-16"
    if b"\x00" in raw[:200]:
        return raw.decode("utf-16-le", errors="replace"), "utf-16-le"
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1"), "latin-1"


def sniff_delimiter(lines):
    best, best_score = ",", -1
    for d in (",", "\t", ";"):
        try:
            rows = list(csv.reader(lines[:40], delimiter=d))
        except csv.Error:
            continue
        score = max((len(r) for r in rows), default=0)
        if score > best_score:
            best, best_score = d, score
    return best


def read_table(path):
    """Simple CSV read for clean files (proposal, cleaned report). Returns (headers, rows)."""
    text, _ = read_text(path)
    lines = text.splitlines()
    delim = sniff_delimiter(lines)
    reader = csv.DictReader(lines, delimiter=delim)
    rows = [r for r in reader if any((v or "").strip() for v in r.values() if isinstance(v, str))]
    return reader.fieldnames or [], rows


def to_float(value, default=0.0):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default
