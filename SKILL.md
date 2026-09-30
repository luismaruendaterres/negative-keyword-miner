---
name: search-terms-negative-keywords
description: "Extract proposed negative keywords from a Google Ads search terms report uploaded as a CSV. Scores each search term for product fit, buyer fit, funnel stage and row-level evidence against a description of the business, then proposes negatives with score, reason, match type (broad, phrase, exact), scope (ad group, campaign, shared list, account) and supporting metrics. Use whenever the user uploads or mentions a search terms report, search query report, wasted ad spend, irrelevant clicks, or negative keywords for Google Ads, even if they do not say 'negative keyword'. Proposal only; never changes an ad account."
license: MIT
---

# Search Terms Negative Keyword Extractor

Turn a Google Ads search terms report (CSV) into a reviewable list of proposed negative keywords. Relevance depends on the business, so generic negative lists are dangerous: "free", "jobs", "cheap" or "login" can be junk for one company and good traffic for another. Do not score anything until the business is described. The output is a proposal for a human operator to challenge. Nothing is applied by this skill.

## Step 1: Data check

Load the CSV with the bundled script rather than ad hoc code:

```
python <skill_dir>/scripts/load_report.py /mnt/user-data/uploads/report.csv --out-dir work --brand "brand one,brand two"
```

It finds the real header under Google's title and date rows, drops totals rows and rows already excluded as negatives, handles UTF-16, tab and semicolon exports, converts numbers stored as text (currency symbols, " --", percent signs, European decimals), and writes `work/terms_clean.csv`, `work/terms_aggregated.csv` (one row per term, campaign and ad group, sorted by cost) and `work/data_check.json`. Add `--exclude-campaigns "pmax|performance max"` to drop aggregated PMax rows. Use the aggregated file for evaluation, and read the script's printed summary and `missing_fields` for the report to the user. Use `--brand` only after the user has confirmed their brand terms (Step 2); rerun if they change.

Needed fields (names vary by export, so map them and show the mapping):

- Search term (essential: without it there is nothing to evaluate)
- Campaign
- Ad group
- Triggering keyword
- Match type of the triggering keyword
- Clicks
- Spend (Cost)
- Conversions
- Conversion value
- Date range (often in the header rows of the export; otherwise ask)

Report back briefly: row count, date range, currency, total spend, total conversions, and the column mapping. **If any field is missing, say so plainly and explain what it weakens** (for example: no triggering keyword means no keyword-drift analysis and weaker match type advice; no conversion value means no revenue-based judgment; no date range means the spend cannot be put in context). Then ask whether to proceed without it. If the user says to ignore it, proceed and note the limitation once in the output summary rather than repeating it on every row. Do not silently work around missing data.

Also note, without treating it as a blocker: rows for Performance Max or Smart campaigns carry aggregated, directional search term data, and negatives for them are handled through account-level negatives and campaign settings. Exclude them from the proposal and say so once.

## Step 2: Business context

Before scoring, get a clear description of the business. Ask for whatever is missing, in one message, and do not invent answers:

1. **What the company sells**: products or services, and what is out of scope.
2. **Who can buy**: eligible customer types (consumers, small businesses, enterprises, specific industries, roles).
3. **Excluded segments**: who should not be targeted (students, job seekers, resellers, DIY users, competitors, existing customers, and so on).
4. **Supported geographies**: where the company sells, ships or serves.
5. **Minimum requirements**: minimum order size, price floor, company size, contract length, technical prerequisites, or anything that disqualifies a buyer.
6. **Acquisition vs support intent**: which kinds of query mean a prospect is shopping (acquisition) and which mean an existing customer needs help (support: login, cancel, invoice, manual, contact number, refund, and similar). State whether support-intent queries are wanted in these campaigns. Usually they are not, but it depends on the account.
7. **Own brand terms** (name, misspellings, products, domain): these are protected and never proposed as negatives.

Helpful but optional: target CPA or ROAS, landing pages per campaign or ad group, whether conversions are qualified (for example, a lead form fill vs a closed sale), and any existing negative keyword lists.

If the user declines to give context, proceed only on their instruction, infer what you can from campaign names, ad groups and converting queries, state the assumptions at the top of the output, and lean toward "Uncertain" (see Step 4) wherever the context would have decided the call.

## Step 3: Evaluate each search term

Aggregate rows by search term within campaign and ad group first, since the same query can appear several times. Then evaluate each term on four dimensions:

- **Product fit**: does the query describe something the company sells?
- **Buyer fit**: could the person searching actually buy, given who can buy, excluded segments, geography and minimum requirements?
- **Funnel stage**: acquisition intent (researching, comparing, ready to buy) vs support intent, job seeking, or other non-buying intent.
- **Evidence from the row**: clicks, spend, conversions, conversion value, the triggering keyword and its match type, and the campaign and ad group. Conversion history matters most: a term that converts, especially with qualified conversions, is strong evidence of fit whatever it looks like. Zero conversions on a handful of clicks proves almost nothing, whereas zero conversions on high spend does.

Do not apply invented spend cutoffs. Judge cost relative to the account (average CPC, total spend, share of spend) and to the user's target CPA if given, and say which yardstick you used.

## Step 4: Score and classify

Give each term a single fit score from 0 to 10, where low means "probably should not be bought" and high means "worth buying". The number exists to prioritize review; the written reason exists so the operator can challenge it.

| Score | Classification | Recommendation |
|---|---|---|
| 0-2 | Clearly irrelevant | Review for broad or phrase negative |
| 3-4 | Likely wrong buyer or intent | Review context and triggering keyword |
| 5-6 | Ambiguous | Keep active and collect more evidence |
| 7-8 | Relevant but unproven | Monitor spend and downstream quality |
| 9-10 | Strong fit or proven converter | Keep, and consider tighter campaign structure |

**Use "Uncertain" instead of a score** when the account context does not support a confident decision: the term could be good or bad depending on something the user has not said (for example, "used" when the company might or might not sell refurbished items, or a location not covered by the stated geographies). Give the reason and name the specific piece of information that would settle it. Never force a low score on a term just to look decisive.

## Step 5: Turn low scores into negatives

Only terms scoring 0-4, plus any "Uncertain" terms, appear in the proposal. Terms scoring 5-10 are not proposed; summarize how many fell in each band and the spend involved, and mention notable high-spend ones in prose (especially any 9-10 proven converters, which must be protected).

**Choose the negative keyword itself.** It may be the whole query, or a recurring modifier or theme shared by several queries. Prefer the smallest string that captures the wrong intent without catching good traffic. When one negative covers several queries, report how many and their combined metrics.

**Choose the match type:**

- **Broad**: blocks when the query contains all the negative terms, in any order. Best for themes that are always irrelevant. Main risk: blocking more combinations than expected.
- **Phrase**: blocks when the query contains the exact phrase in order. Best for repeated wrong-intent phrases. Main risk: missing reordered variations.
- **Exact**: blocks when the query is exactly those terms without extra words. Best for one proven bad query. Main risk: it takes many entries to cover a theme.

Negatives do not automatically match plurals, misspellings or close variants, so mention when a variant may need its own entry. A score of 0-2 points toward reviewing a broad or phrase negative; a score of 3-4 usually needs a narrower, exact or phrase, choice after looking at the triggering keyword.

**Choose the scope.** Use the smallest scope that solves the problem, because scope determines how much traffic a negative can block:

- **Ad group**: the term is wrong for one theme but valid elsewhere in the campaign.
- **Campaign**: the term is wrong for that campaign's product, geography or intent.
- **Shared list**: the term is wrong across a known group of campaigns (name the campaigns).
- **Account level**: the term is wrong across all relevant Search and Shopping inventory.

Name the actual campaign or ad group in the scope column, not just the level.

**Check the triggering keyword.** If a bad query only appears because a broad or phrase match keyword is too loose, say so: tightening that keyword may be better than, or in addition to, a negative.

## Step 6: Safety checks before presenting

Prioritize the list by (in order of weight, adjusted by judgment) spend and click volume, conversion and qualified conversion history, product and buyer relevance, match type and triggering keyword, campaign, ad group, geography and landing page, and your confidence that the query is truly wrong. Then verify:

- **No collisions.** Test every proposed negative, under its proposed match type, against all queries in the report. If it would block any query that converted, that scored 7 or higher, or that contains a protected brand term, drop it, narrow it (exact instead of phrase, ad group instead of campaign), or move it to "Uncertain".
- **No brand negatives.** No proposed negative may contain an own brand term. Brand campaigns often show zero or low conversions by design; if the account seems to overspend on its own brand, raise it as a bid strategy or impression share conversation, never as a negative.
- **Not already excluded**, if the user provided existing negatives.
- **Every reason cites row evidence** with real numbers from the report, not general impressions.
- **Broad negatives** are listed individually so they can be approved one by one.

Do these checks with the script instead of by eye. Write the candidates to `work/proposal.csv` with the columns `negative_keyword, score, classification, reason, match_type, scope_level, campaign, ad_group` (`match_type` is broad, phrase or exact; `scope_level` is ad_group, campaign, shared_list or account; `campaign` may list several names separated by `;`), then run:

```
python <skill_dir>/scripts/check_proposal.py --report work/terms_clean.csv --proposal work/proposal.csv --out work/proposal_checked.csv --brand "brand one,brand two" [--existing existing_negatives.csv]
```

It applies each negative under its proposed match type and scope to every report row and adds `queries_blocked`, `blocked_clicks`, `blocked_spend`, `blocked_conversions`, `blocked_conv_value`, `blocked_examples`, `flags` and `status`. **Use these `blocked_*` numbers as the supporting metrics in the output**, not figures typed from memory. Anything with status REVIEW (blocks a converting query, contains or blocks a brand term, matches nothing in scope, is possibly already covered, or has missing scope fields) must be fixed, narrowed, moved to "Uncertain" or dropped before presenting, or shown with the flag explained. Remember that a script check only sees queries in this report, so still consider good traffic that isn't in it.

## Step 7: Output

Present the proposed list in chat as a table, sorted by priority (spend at stake, then lowest score). Columns:

| Negative keyword | Score | Classification | Reason | Match type | Scope | Clicks | Spend | Conversions | Conversion value |

- **Reason**: one to three sentences covering product fit, buyer fit, funnel stage and evidence from the row, with the specific numbers.
- **Scope**: level plus the named campaign(s) or ad group(s).
- **Metrics**: totals across all queries the negative would cover. Add the triggering keyword(s) and the number of queries covered where useful.

Show "Uncertain" items in their own table with the same columns, the score cell reading "Uncertain", and the reason ending with what information would resolve it.

Above the tables give a short summary: date range, currency, spend reviewed, spend and share of total in the proposed negatives, counts by band, assumptions made, and any missing data the user chose to ignore. If the list is longer than about 25 rows, put the tables in a CSV file (same columns) and present it, keeping the chat summary short.

Finish by asking which items the user approves, changes or rejects. Everything is a proposal until the user says otherwise. When the user approves items (all or a subset), mark them in `proposal_checked.csv` by adding an `approved` column (yes/no), then run:

```
python <skill_dir>/scripts/export_editor.py --proposal work/proposal_approved.csv --out-dir export
```

This writes `editor_import.csv` (Campaign, Ad Group, Keyword, Criterion Type, for ad group and campaign level negatives), `shared_and_account.csv` and `shared_and_account.txt` (shared-list and account-level terms with match syntax, for pasting into the UI) and `export_report.txt` (what was exported or skipped, and why). Present the files, and tell the user to compare the Editor file's header and Criterion Type labels against an export of their own existing negatives before importing, since labels vary by Editor version, and to review the changes in Editor before posting. If the script reports errors, fix those rows and rerun; do not hand-edit around them.

## Boundaries

- This skill only reads the uploaded files. It never claims to have applied, posted or verified anything in a live account. To check results after import, the user can upload a fresh export of the negative keyword lists and this skill can compare it against the approved items.
- If nothing clears the bar, say the report looks clean and stop. Do not manufacture marginal candidates.
- If the CSV cannot be read or the search term column is absent, say exactly what is wrong and what is needed.

## Bundled scripts

All scripts use only the Python 3 standard library. Run any of them with `--help` for options.

| Script | Purpose |
|---|---|
| `scripts/load_report.py` | Import: clean the exported CSV, report missing fields, write `terms_clean.csv`, `terms_aggregated.csv`, `data_check.json` |
| `scripts/check_proposal.py` | Check: test proposed negatives against the report (match type and scope aware), recompute metrics, flag collisions |
| `scripts/export_editor.py` | Export: write the Google Ads Editor import file and shared/account lists from approved items |
| `scripts/nk_common.py` | Shared matching and parsing helpers (imported by the other scripts) |
| `examples/sample_search_terms.csv` | Small fictional report for trying the scripts |

Script matching follows Google's negative rules: broad blocks when all words appear in any order, phrase when the words appear contiguously in order, exact only when the query is exactly those words. Negatives do not match plurals, misspellings or close variants, and neither do the scripts.
