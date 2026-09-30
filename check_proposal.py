#!/usr/bin/env python3
"""Test a proposed negative keyword list against the real search terms report.

For each proposed negative it works out, under the proposed match type and scope, which report
queries it WOULD block, recomputes the supporting metrics from the data (so numbers are not
typed by hand), and flags problems: converting queries blocked, brand terms, nothing matched,
already covered by an existing negative.

Usage:
  python check_proposal.py --report work/terms_clean.csv --proposal proposal.csv --out work/proposal_checked.csv
        [--brand "acme,acme crm"] [--existing existing_negatives.csv]

Proposal CSV columns (extra columns are kept and passed through):
  negative_keyword, match_type (broad|phrase|exact), scope_level (ad_group|campaign|shared_list|account),
  campaign, ad_group     (campaign may hold several names separated by ';' for campaign/shared_list scope)
Existing negatives CSV (optional): keyword, match_type (optional; [x] and "x" syntax also understood).
"""
import argparse
import csv
import sys

from nk_common import (blocks, contains_phrase, nrow, norm_level, parse_match, pick, read_table,
                       split_list, split_syntax, to_float, tokens)

ADDED = ["queries_blocked", "blocked_clicks", "blocked_spend", "blocked_conversions",
         "blocked_conv_value", "blocked_examples", "flags", "status"]


def load_report(path):
    headers, rows = read_table(path)
    out = []
    for r in rows:
        n = nrow(r)
        out.append({
            "term": pick(n, "search_term"),
            "campaign": pick(n, "campaign"), "ad_group": pick(n, "ad_group"),
            "clicks": to_float(n.get("clicks")), "cost": to_float(n.get("cost")),
            "conv": to_float(n.get("conversions")), "value": to_float(n.get("conv_value")),
        })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", required=True, help="terms_clean.csv or terms_aggregated.csv")
    ap.add_argument("--proposal", required=True)
    ap.add_argument("--out", default="proposal_checked.csv")
    ap.add_argument("--brand", default="")
    ap.add_argument("--existing", default="")
    a = ap.parse_args()

    report = load_report(a.report)
    for r in report:
        r["tok"] = tokens(r["term"])
    brand = [tokens(b) for b in a.brand.split(",") if tokens(b)]

    existing = []
    if a.existing:
        _, erows = read_table(a.existing)
        for r in erows:
            n = nrow(r)
            kw, syn = split_syntax(pick(n, "keyword", "negative_keyword", "negative"))
            m = parse_match(pick(n, "match_type")) or syn or "broad"
            if tokens(kw):
                existing.append((kw, m, tokens(kw)))

    headers, prop = read_table(a.proposal)
    if not prop:
        print("ERROR: proposal file has no rows.", file=sys.stderr)
        sys.exit(2)

    checked, n_review = [], 0
    for row in prop:
        n = nrow(row)
        neg_raw = pick(n, "negative_keyword", "negative", "keyword")
        neg, syn = split_syntax(neg_raw)
        match = parse_match(pick(n, "match_type", "negative_match_type")) or syn
        level = norm_level(pick(n, "scope_level", "scope"))
        camps = [c.lower() for c in split_list(pick(n, "campaign", "campaigns"))]
        ag = pick(n, "ad_group", "adgroup").lower()
        nt = tokens(neg)
        flags = []

        if not nt:
            flags.append("EMPTY_NEGATIVE")
        if match is None:
            flags.append("MISSING_OR_INVALID_MATCH_TYPE")
        if level is None:
            flags.append("MISSING_OR_INVALID_SCOPE_LEVEL")
        if level == "ad_group" and (not camps or not ag):
            flags.append("AD_GROUP_SCOPE_NEEDS_CAMPAIGN_AND_AD_GROUP")
        if level == "campaign" and not camps:
            flags.append("CAMPAIGN_SCOPE_NEEDS_CAMPAIGN")

        def in_scope(r):
            if level == "ad_group":
                return r["campaign"].lower() in camps and r["ad_group"].lower() == ag
            if level == "campaign":
                return r["campaign"].lower() in camps
            if level == "shared_list" and camps:
                return r["campaign"].lower() in camps
            return True  # account, or shared list with no campaigns named

        hit = [r for r in report if in_scope(r) and match and blocks(nt, r["tok"], match)] if nt else []
        by_term = {}
        for r in hit:
            t = by_term.setdefault(r["term"].lower(), {"term": r["term"], "cost": 0.0, "conv": 0.0, "value": 0.0})
            t["cost"] += r["cost"]; t["conv"] += r["conv"]; t["value"] += r["value"]

        if not hit and nt and match and level:
            flags.append("NO_MATCHING_QUERY_IN_SCOPE (typo, wrong scope, or nothing to block)")
        conv_terms = [t["term"] for t in by_term.values() if t["conv"] > 0 or t["value"] > 0]
        if conv_terms:
            flags.append("BLOCKS_CONVERTING_QUERY: " + "; ".join(conv_terms[:3]) + (" ..." if len(conv_terms) > 3 else ""))
        if any(contains_phrase(nt, b) for b in brand):
            flags.append("BRAND_TERM_IN_NEGATIVE")
        brand_hit = [t["term"] for t in by_term.values() if any(contains_phrase(tokens(t["term"]), b) for b in brand)]
        if brand_hit:
            flags.append("BLOCKS_BRAND_QUERY: " + "; ".join(brand_hit[:3]))
        for kw, m, et in existing:
            if nt and blocks(et, nt, m):
                flags.append(f"POSSIBLY_ALREADY_COVERED_BY: {kw} ({m}); check its scope")
                break

        top = sorted(by_term.values(), key=lambda t: -t["cost"])[:5]
        out = dict(row)
        out.update({
            "queries_blocked": len(by_term),
            "blocked_clicks": int(round(sum(r["clicks"] for r in hit))),
            "blocked_spend": f"{sum(r['cost'] for r in hit):.2f}",
            "blocked_conversions": f"{sum(r['conv'] for r in hit):.2f}",
            "blocked_conv_value": f"{sum(r['value'] for r in hit):.2f}",
            "blocked_examples": " | ".join(t["term"] for t in top),
            "flags": " || ".join(flags),
            "status": "REVIEW" if flags else "OK",
        })
        n_review += bool(flags)
        checked.append(out)

    cols = list(headers) + [c for c in ADDED if c not in headers]
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(checked)

    print(f"Checked {len(checked)} proposed negatives against {len(report)} report rows: "
          f"{len(checked) - n_review} OK, {n_review} need review. Wrote {a.out}")
    for c in checked:
        if c["flags"]:
            print(f"  REVIEW  {pick(nrow(c), 'negative_keyword', 'negative', 'keyword')!r}: {c['flags']}")


if __name__ == "__main__":
    main()
