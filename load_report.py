#!/usr/bin/env python3
"""Load and clean a Google Ads search terms report CSV.

Handles title/date rows above the header, totals rows, UTF-16 / tab / semicolon exports,
numbers stored as text (currency symbols, ' --', %, European decimals) and reports
which expected fields are missing and what that weakens.

Usage:
  python load_report.py report.csv --out-dir work [--brand "acme,acme crm"]
        [--exclude-campaigns "pmax|performance max"] [--keep-excluded]
        [--decimal auto|dot|comma] [--date-range "text"]

Writes into --out-dir:
  terms_clean.csv       one row per report row, normalized columns
  terms_aggregated.csv  one row per search term + campaign + ad group, sorted by cost
  data_check.json       what was found, what is missing, totals
"""
import argparse
import csv
import json
import os
import re
import sys
from collections import OrderedDict

from nk_common import contains_phrase, read_text, sniff_delimiter, tokens

# Priority-ordered aliases (first alias present in the header wins).
ALIASES = OrderedDict([
    ("search_term", ["search term", "search terms", "search query", "query"]),
    ("campaign", ["campaign", "campaign name"]),
    ("ad_group", ["ad group", "adgroup", "ad group name"]),
    ("keyword", ["keyword", "search keyword", "keyword text", "triggering keyword"]),
    ("keyword_match_type", ["keyword match type", "search keyword match type", "match type"]),
    ("added_excluded", ["added/excluded", "added / excluded", "added excluded"]),
    ("impressions", ["impr.", "impressions", "impr"]),
    ("clicks", ["clicks"]),
    ("cost", ["cost", "spend", "amount spent"]),
    ("conversions", ["conversions", "conv.", "conv"]),
    ("conv_value", ["conv. value", "conversion value", "conversions value", "total conv. value"]),
    ("currency", ["currency code", "currency"]),
])

CONSEQUENCE = {
    "search_term": "ESSENTIAL. Without the search term column there is nothing to evaluate.",
    "campaign": "Cannot scope negatives to a campaign or ad group, or spot brand campaigns.",
    "ad_group": "Cannot propose ad-group-level negatives; scope falls back to campaign level.",
    "keyword": "No triggering-keyword analysis: cannot tell whether tightening a keyword beats adding a negative.",
    "keyword_match_type": "Match type of the triggering keyword unknown: weaker advice on loose broad/phrase keywords.",
    "clicks": "Cannot judge click volume or average CPC; low-evidence terms are harder to separate.",
    "cost": "Cannot measure wasted spend or prioritize by dollars at stake.",
    "conversions": "Cannot protect converting queries or judge waste; the collision check is much weaker.",
    "conv_value": "No revenue-based judgment; low-value converters cannot be told apart from good ones.",
}
DATE_RANGE_NOTE = "No date range found in the file: spend cannot be put in context. Ask the user or pass --date-range."

NUMERIC = ("impressions", "clicks", "cost", "conversions", "conv_value")


def norm_header(h):
    h = re.sub(r"\s*\(.*?\)", "", (h or "").strip().lower())
    return re.sub(r"\s+", " ", h).strip()


def map_header(cells):
    normed = [norm_header(c) for c in cells]
    mapping = {}
    for field, aliases in ALIASES.items():
        for alias in aliases:
            if alias in normed:
                mapping[field] = normed.index(alias)
                break
    return mapping


def find_header(rows):
    best_i, best_n = None, 0
    for i, r in enumerate(rows[:40]):
        m = map_header(r)
        if "search_term" in m and len(m) > best_n:
            best_i, best_n = i, len(m)
    return best_i


def detect_decimal(values):
    comma = dot = 0
    for v in values:
        s = str(v).strip()
        if re.search(r",\d{1,2}$", s):
            comma += 1
        elif re.search(r"\.\d{1,2}$", s):
            dot += 1
    return "comma" if comma > dot else "dot"


def parse_number(value, decimal):
    s = str(value or "").strip()
    if s in ("", "--", "-", "\u2014", "n/a", "N/A"):
        return 0.0
    s = re.sub(r"[^\d,.\-]", "", s)
    if not re.search(r"\d", s):
        return 0.0
    sign = -1.0 if s.startswith("-") else 1.0
    s = s.replace("-", "")
    if decimal == "comma":
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return sign * float(s)
    except ValueError:
        return 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_path")
    ap.add_argument("--out-dir", default="work")
    ap.add_argument("--brand", default="", help="comma-separated own brand terms/misspellings")
    ap.add_argument("--exclude-campaigns", default="", help="regex; matching campaigns are dropped (e.g. PMax)")
    ap.add_argument("--brand-campaign-regex", default=r"brand|defen[cs]e|trademark")
    ap.add_argument("--keep-excluded", action="store_true", help="keep rows already marked Excluded")
    ap.add_argument("--decimal", choices=["auto", "dot", "comma"], default="auto")
    ap.add_argument("--date-range", default="", help="override the date range text")
    a = ap.parse_args()

    text, encoding = read_text(a.csv_path)
    lines = text.splitlines()
    delim = sniff_delimiter(lines)
    raw_rows = list(csv.reader(lines, delimiter=delim))

    hi = find_header(raw_rows)
    if hi is None:
        print("ERROR: could not find a header row with a 'Search term' column.", file=sys.stderr)
        sys.exit(2)
    mapping = map_header(raw_rows[hi])
    pre_header = [" ".join(c for c in r if c.strip()) for r in raw_rows[:hi] if any(c.strip() for c in r)]
    date_range = a.date_range or next((l for l in pre_header if re.search(r"\b(19|20)\d{2}\b", l)), "")

    body = raw_rows[hi + 1:]

    def cell(r, field):
        i = mapping.get(field)
        return r[i].strip() if i is not None and i < len(r) else ""

    numeric_raw = [cell(r, f) for r in body for f in ("cost", "conversions", "conv_value") if f in mapping]
    decimal = a.decimal if a.decimal != "auto" else detect_decimal(numeric_raw)

    brand_tokens = [tokens(b) for b in a.brand.split(",") if tokens(b)]
    brand_camp = re.compile(a.brand_campaign_regex, re.I) if a.brand_campaign_regex else None
    excl_camp = re.compile(a.exclude_campaigns, re.I) if a.exclude_campaigns else None

    dropped = {"blank_or_totals": 0, "excluded_already": 0, "excluded_campaigns": 0}
    clean = []
    for r in body:
        if not any(c.strip() for c in r):
            continue
        term = cell(r, "search_term")
        if term in ("", "--") or re.match(r"^total\s*:", term.lower()) or re.match(r"^total\s*:", (r[0] if r else "").strip().lower()):
            dropped["blank_or_totals"] += 1
            continue
        camp = cell(r, "campaign")
        if excl_camp and excl_camp.search(camp):
            dropped["excluded_campaigns"] += 1
            continue
        ae = cell(r, "added_excluded")
        if ae.lower().startswith("excluded") and not a.keep_excluded:
            dropped["excluded_already"] += 1
            continue
        row = OrderedDict()
        row["search_term"] = term
        row["campaign"] = camp
        row["ad_group"] = cell(r, "ad_group")
        row["keyword"] = cell(r, "keyword")
        row["keyword_match_type"] = cell(r, "keyword_match_type")
        row["added_excluded"] = ae
        for f in NUMERIC:
            row[f] = parse_number(cell(r, f), decimal) if f in mapping else 0.0
        row["currency"] = cell(r, "currency")
        row["brand_protective_campaign"] = int(bool(brand_camp and brand_camp.search(camp)))
        tt = tokens(term)
        row["contains_brand"] = int(any(contains_phrase(tt, b) for b in brand_tokens))
        clean.append(row)

    os.makedirs(a.out_dir, exist_ok=True)
    cols = ["search_term", "campaign", "ad_group", "keyword", "keyword_match_type", "added_excluded",
            "impressions", "clicks", "cost", "conversions", "conv_value", "currency",
            "brand_protective_campaign", "contains_brand"]

    def fmt(row):
        o = dict(row)
        o["impressions"] = int(round(o["impressions"]))
        o["clicks"] = int(round(o["clicks"]))
        for f in ("cost", "conversions", "conv_value"):
            o[f] = f"{o[f]:.2f}"
        return o

    with open(os.path.join(a.out_dir, "terms_clean.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for row in clean:
            w.writerow(fmt(row))

    groups = OrderedDict()
    for row in clean:
        k = (row["search_term"].lower(), row["campaign"].lower(), row["ad_group"].lower())
        g = groups.setdefault(k, {"search_term": row["search_term"], "campaign": row["campaign"],
                                  "ad_group": row["ad_group"], "keywords": [], "keyword_match_types": [],
                                  "added_excluded": [], "impressions": 0.0, "clicks": 0.0, "cost": 0.0,
                                  "conversions": 0.0, "conv_value": 0.0, "currency": row["currency"],
                                  "brand_protective_campaign": 0, "contains_brand": 0})
        for f in NUMERIC:
            g[f] += row[f]
        for src, dst in (("keyword", "keywords"), ("keyword_match_type", "keyword_match_types"),
                         ("added_excluded", "added_excluded")):
            if row[src] and row[src] not in g[dst]:
                g[dst].append(row[src])
        g["brand_protective_campaign"] = max(g["brand_protective_campaign"], row["brand_protective_campaign"])
        g["contains_brand"] = max(g["contains_brand"], row["contains_brand"])

    agg = sorted(groups.values(), key=lambda g: -g["cost"])
    agg_cols = ["search_term", "campaign", "ad_group", "keywords", "keyword_match_types", "added_excluded",
                "impressions", "clicks", "cost", "conversions", "conv_value", "currency",
                "brand_protective_campaign", "contains_brand"]
    with open(os.path.join(a.out_dir, "terms_aggregated.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=agg_cols)
        w.writeheader()
        for g in agg:
            o = dict(g)
            for f in ("keywords", "keyword_match_types", "added_excluded"):
                o[f] = " | ".join(g[f])
            o["impressions"] = int(round(g["impressions"]))
            o["clicks"] = int(round(g["clicks"]))
            for f in ("cost", "conversions", "conv_value"):
                o[f] = f"{g[f]:.2f}"
            w.writerow(o)

    missing = {f: CONSEQUENCE[f] for f in CONSEQUENCE if f not in mapping}
    notes = []
    if not date_range:
        notes.append(DATE_RANGE_NOTE)
    if mapping.get("keyword_match_type") is not None and norm_header(raw_rows[hi][mapping["keyword_match_type"]]) == "match type":
        notes.append("Only 'Match type' was found. In Google's search terms report this describes how the search "
                     "term matched (broad/phrase/exact/close variant), not necessarily the triggering keyword's own "
                     "match type. Treat keyword match type advice as approximate.")
    if "added_excluded" in mapping:
        added = sum(1 for r in clean if r["added_excluded"].lower().startswith("added"))
        if added:
            notes.append(f"{added} rows are already added as keywords (kept for the collision check; unlikely negative candidates).")
    currencies = sorted({r["currency"] for r in clean if r["currency"]})
    if len(currencies) > 1:
        notes.append(f"Multiple currencies found: {currencies}. Totals mix currencies.")

    check = OrderedDict([
        ("file", os.path.basename(a.csv_path)),
        ("encoding", encoding), ("delimiter", "tab" if delim == "\t" else delim),
        ("header_row_index", hi), ("decimal_format", decimal),
        ("date_range", date_range or None),
        ("rows_kept", len(clean)), ("aggregated_rows", len(agg)), ("dropped", dropped),
        ("currencies", currencies or None),
        ("total_clicks", int(round(sum(r["clicks"] for r in clean)))),
        ("total_cost", round(sum(r["cost"] for r in clean), 2)),
        ("total_conversions", round(sum(r["conversions"] for r in clean), 2)),
        ("total_conv_value", round(sum(r["conv_value"] for r in clean), 2)),
        ("brand_terms", [" ".join(b) for b in brand_tokens]),
        ("column_mapping", {f: raw_rows[hi][i] for f, i in mapping.items()}),
        ("missing_fields", missing), ("notes", notes),
    ])
    with open(os.path.join(a.out_dir, "data_check.json"), "w", encoding="utf-8") as fh:
        json.dump(check, fh, indent=2, ensure_ascii=False)

    print(f"Read {a.csv_path} ({encoding}, delimiter {check['delimiter']!r}, decimal '{decimal}')")
    print(f"Date range : {date_range or 'NOT FOUND'}")
    print(f"Rows kept  : {len(clean)}  (aggregated: {len(agg)})  dropped: {dropped}")
    print(f"Totals     : {check['total_clicks']} clicks, cost {check['total_cost']} {','.join(currencies)}, "
          f"{check['total_conversions']} conversions, conv value {check['total_conv_value']}")
    print("Mapped     : " + ", ".join(f"{f}<-'{v}'" for f, v in check["column_mapping"].items()))
    if missing:
        print("\nMISSING FIELDS (tell the user; proceed only if they say to ignore):")
        for f, c in missing.items():
            print(f"  - {f}: {c}")
    for n in notes:
        print(f"NOTE: {n}")
    print(f"\nWrote {a.out_dir}/terms_clean.csv, terms_aggregated.csv, data_check.json")
    if "search_term" not in mapping:
        sys.exit(2)


if __name__ == "__main__":
    main()
