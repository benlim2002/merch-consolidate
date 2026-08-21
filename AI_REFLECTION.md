# REFLECTION ON AI USAGE (CLAUDE)

Below are my reflections of the usage of AI, after-thoughts, and on where and what I used AI most for.

## How I use Claude
In my opinion, Claude is one of the best tools for code-related uses. Before approaching a solution, I would always write up an outline first and check it up with Claude. Most of the code was completed mainly with the help of IntelliSense (VsCode) and of course from the help of Claude too. The transcript can be accessed on `AI_REFLECTION.md`.

## AI as bug-catcher
1. Caught the _gemini_model initialization bug (variable set to a string instead of None, so the LLM fallback **silently never ran and failed** into keyword-only mode without any error).
2. Caught the keyword-matching substring bug (`"mart"` matching inside `"smart home solutions"`, wrongly classifying it as **Grocery & Convenience**, a single false-positive match that bypassed the ambiguity safety net).

## Where I disagreed with AI's suggestion.
1. AI initially suggested **embeddings or LLM-only** classification; I chose `keyword+LLM hybrid` instead for transparency/testability at this scale.
2. I proposed mapping states `(Penang, KL)` to regions; AI advised **against** silently hardcoding this, cautioning it was a spec question, not a coding decision. I ultimately kept a documented alias but flagged it explicitly in the `README.md` as a deliberate deviation, rather than either silently mapping it or blindly following the "reject strictly" advice.
3. When I noticed name/category mismatches `(e.g. "Kedai Emas Trading" tagged as a computer shop)`, I considered building an automated correction. AI argued this was scope creep beyond DATA_DICTIONARY's **7 rules** and that I'd have no ground truth to validate a new heuristic against. I eventually agreed and built a separate, clearly-labeled review script instead of folding it into the core pipeline. *trying to actually build a huesristic agent for this case would actually take up much more time, being it not as simple as mapping the states into region*

## What I verified by myself, not on AI's word
1. Confirmed `submission_id` is not chronological by checking actual data, before accepting AI's suggestion to switch the dedup tie-break to registration_date.
2. Confirmed `existing_merchants` schema (no branch/location column) directly against reference.db before deciding the dedup key.
3. Actually ran the full pipeline end-to-end multiple times to confirm each change didn't break row counts / rejection reasons.

## What approach I would take if given more time
1. **check.py's serial rate limit doesn't scale.** At 15s/unique pair, 10k unique (name, category) pairs is ~41 hours sequential. At scale I'd batch requests (Gemini supports multi-item prompts) or move to local LLM's which are much more faster.
2. **Keyword list is hardcoded in Python.** At scale, ops would want to add/adjust category keywords without a code deploy — I'd move CATEGORY_KEYWORDS into reference.db alongside categories, same as everything else that's supposed to be "nothing hardcoded."
3. **Dedup only compares within a single run.** Per the README, cross-run duplicate merchants aren't caught. With daily runs I'd need a persistent merchant identity store so today's submissions can be deduped against everything ever ingested, not just today's batch.
4. **No test suite beyond __main__ self-checks.** They're useful but ad hoc and don't run in CI. At scale I'd want a real pytest suite (including edge cases like ambiguous dates, phone formats, and the region-alias table) wired into CI so a change to one module can't silently break another's assumptions.