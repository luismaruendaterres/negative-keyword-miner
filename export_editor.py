#!/usr/bin/env python3
"""Turn an APPROVED proposal into files you can import into Google Ads.

Usage:
  python export_editor.py --proposal approved.csv --out-dir export [--encoding utf-8-sig]

Reads the same proposal columns as check_proposal.py. If the file has an 'approved' column,
only rows with yes/y/true/1/approved are exported; otherwise every row is exported.

Writes into --out-dir:
  editor_import.csv        Campaign, Ad Group, Keyword, Criterion Type
                           (ad group and campaign level negatives, for Google Ads Editor)
  shared_and_account.csv   shared list and account level negatives, one row per term
  shared_and_account.txt   the same terms with match syntax, for pasting into a shared list in the UI
  export_report.txt        what was exported, skipped and why

Criterion Type labels differ slightly between Editor versions. Before importing, compare the
header and labels with an export of your own existing negatives, and review in Editor before posting.
"""
import argparse
import csv
import os
import sys

from nk_common import nrow, norm_level, parse_match, pick, read_table, split_list, split_syntax, tokens

TRUE = {"yes", "y", "true", "1", "approved", "x"}
AD_GROUP_TYPE = {"exact": "Negative Exact", "phrase": "Negative Phrase", "broad": "Negative Broad"}
CAMPAIGN_TYPE = {"exact": "Campaign Negative Exact", "phrase": "Campaign Negative Phrase",
                 "broad": "Campaign Negative Broad"}


def syntax(neg, match):
    return {"exact": f"[{neg}]", "phrase": f'"{neg}"', "broad": neg}[match]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--proposal", required=True)
    ap.add_argument("--out-dir", default="export")
    ap.add_argument("--encoding", default="utf-8-sig")
    a = ap.parse_args()

    _, rows = read_table(a.proposal)
    has_approved = any("approved" in nrow(r) for r in rows)
    editor, shared, seen, log = [], [], set(), []

    for i, row in enumerate(rows, start=2):  # line 1 is the header
        n = nrow(row)
        if has_approved and pick(n, "approved").lower() not in TRUE:
            log.append(f"line {i}: skipped (not approved): {pick(n, 'negative_keyword', 'negative', 'keyword')}")
            continue
        neg, syn = split_syntax(pick(n, "negative_keyword", "negative", "keyword"))
        match = parse_match(pick(n, "match_type", "negative_match_type")) or syn
        level = norm_level(pick(n, "scope_level", "scope"))
        camps = split_list(pick(n, "campaign", "campaigns"))
        ag = pick(n, "ad_group", "adgroup")
        problems = []
        if not tokens(neg):
            problems.append("empty negative keyword")
        if match is None:
            problems.append("missing or invalid match type")
        if level is None:
            problems.append("missing or invalid scope level")
        if level == "ad_group" and (len(camps) != 1 or not ag):
            problems.append("ad group scope needs exactly one campaign and an ad group")
        if level == "campaign" and not camps:
            problems.append("campaign scope needs at least one campaign")
        if problems:
            log.append(f"line {i}: ERROR, not exported ({'; '.join(problems)}): {neg!r}")
            continue

        if level == "ad_group":
            key = (camps[0].lower(), ag.lower(), neg.lower(), match)
            if key not in seen:
                seen.add(key)
                editor.append([camps[0], ag, neg, AD_GROUP_TYPE[match]])
                log.append(f"line {i}: exported ad group negative {neg!r} ({match}) -> {camps[0]} / {ag}")
        elif level == "campaign":
            for c in camps:
                key = (c.lower(), "", neg.lower(), match)
                if key not in seen:
                    seen.add(key)
                    editor.append([c, "", neg, CAMPAIGN_TYPE[match]])
            log.append(f"line {i}: exported campaign negative {neg!r} ({match}) -> {'; '.join(camps)}")
        else:
            key = (level, neg.lower(), match)
            if key not in seen:
                seen.add(key)
                shared.append([neg, match, level, "; ".join(camps)])
                log.append(f"line {i}: {level} negative {neg!r} ({match}) -> shared file (import in the UI)")

    os.makedirs(a.out_dir, exist_ok=True)
    with open(os.path.join(a.out_dir, "editor_import.csv"), "w", newline="", encoding=a.encoding) as fh:
        w = csv.writer(fh)
        w.writerow(["Campaign", "Ad Group", "Keyword", "Criterion Type"])
        w.writerows(editor)
    with open(os.path.join(a.out_dir, "shared_and_account.csv"), "w", newline="", encoding=a.encoding) as fh:
        w = csv.writer(fh)
        w.writerow(["Keyword", "Match type", "Scope level", "Campaigns"])
        w.writerows(shared)
    with open(os.path.join(a.out_dir, "shared_and_account.txt"), "w", encoding="utf-8") as fh:
        for neg, match, _, _ in shared:
            fh.write(syntax(neg, match) + "\n")
    with open(os.path.join(a.out_dir, "export_report.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(log) + "\n")

    errors = sum("ERROR" in l for l in log)
    print(f"Editor rows: {len(editor)}   shared/account terms: {len(shared)}   errors: {errors}")
    print(f"Wrote files to {a.out_dir}/ (see export_report.txt)")
    if errors:
        print("Some rows were NOT exported; see export_report.txt.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
