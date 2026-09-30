# negative-keyword-miner

**What's Inside**

SKILL.md is the skill.

scripts/load_report.py (import) cleans your uploaded CSV. It finds the real header, drops totals rows, and handles UTF-16, tab and semicolon files. It writes a cleaned file, an aggregated file (one row per term, campaign and ad group, sorted by cost) and a data check listing any missing fields and what each one weakens.

scripts/check_proposal.py (check) tests each proposed negative against the real report, using its match type and scope. It recalculates the supporting metrics from your data and flags problems: blocking a converting query, brand terms, matching nothing in scope, or possibly already covered by an existing negative.

scripts/export_editor.py (export) turns approved items into editor_import.csv for Google Ads Editor, plus shared_and_account.txt and shared_and_account.csv for shared-list and account-level terms. It also writes a report of anything skipped and why.

scripts/nk_common.py holds the shared helpers, and examples/sample_search_terms.csv is a small fictional report for trying things out.



**How It Works**

The user downloads the search terms report data into a CSV file and uploads it to Claude.

The search terms report data includes campaign, ad group, triggering keyword, match type, clicks, spend, conversions, conversion value, and the date range. A strong prompt asks for product fit, buyer fit, funnel stage, and evidence from the row. If any data type is missing, tell the user; if the user asks to ignore it, proceed.

The model needs a clear description of what the company sells, who can buy, excluded segments, supported geographies, minimum requirements, and the difference between acquisition and support intent. Generic negative lists are dangerous because relevance depends on the business.

The output is a proposed list with the negative keyword, score, reason, negative keyword match type, scope, and supporting metrics (i.e., clicks, spend, conversions, conversion value).

Use a simple score and a written reason. The number prioritizes review. The explanation lets the operator challenge the model. Use “uncertain” when the account context does not support a confident decision. The score measures how good a fit the query is, so low scores are the negative candidates.

Score: 0-2; Classification: clearly irrelevant; Recommendation: Review for broad or phrase negative.
Score: 3-4; Classification: likely wrong buyer or intent; Recommendation: Review context and triggering keyword.
Score: 5-6; Classification: ambiguous; Recommendation: Keep active and collect more evidence.
Score: 7-8; Classification: relevant but unproven; Recommendation: Monitor spend and downstream quality.
Score: 9-10; Classification: strong fit or proven converter; Recommendation: Keep, and consider tighter campaign structure.

For match type for the negatives, keep in mind the following:

Broad: blocks when the query contains all negative terms in any order, best for themes that are always irrelevant, main risk is blocking more combinations than expected.
Phrase: blocks when the query contains the exact phrase in order, best for repeated wrong-intent phrases, main risk is missing reordered variations.
Exact: blocks when the query is the exact terms without extra words, best for one proven bad query, main risk is that it requires many entries to cover a theme.

Scope determines how much traffic the negative can block. Use the smallest scope that solves the problem.

Ad group: the term is wrong for one theme but valid elsewhere in the campaign.
Campaign: the term is wrong for that campaign’s product, geography, or intent.
Shared list: the term is wrong across a known group of campaigns.
Account level: the term is wrong across all relevant Search and Shopping inventory.

A useful system should prioritize terms by:

Spend and click volume
Conversion and qualified conversion history
Product and buyer relevance
Match type and triggering keyword
Campaign, ad group, geography, and landing page


Each proposed negative is tested against every query in the report, and it's dropped or narrowed if it would block a converting query, a query scoring 7 or higher, or a brand term.
Your own brand terms are never proposed as negatives.
After you approve items, it can generate a Google Ads Editor import CSV. Nothing is ever applied to a live account.

