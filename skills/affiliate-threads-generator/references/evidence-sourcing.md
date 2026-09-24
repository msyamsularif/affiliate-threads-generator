# Evidence sourcing — review-first, Shopee-aware

## Why this file exists

The naive assumption is "fetch the product page, read the specs". That is wrong
here twice over.

The `Affiliate URL` points at Shopee, which actively blocks automated access, so a
failed fetch is the normal case rather than an error to escalate. And the two
sources that _are_ reachable — the `Description` column and the product page —
are both written by someone who is selling the product. They say what the seller
wants said, not what is true about this unit.

**Hard rule: never attempt to bypass CAPTCHA, anti-bot measures or auth walls.**
Not with a different user agent, not with a headless browser, not with a proxy,
not with `execute_code`. If a page does not load, that is the end of that path.

## Confidence tiers

Every factual claim in the final copy must trace to exactly one of these — in
`firsthand` mode, tier 0 below included.

| Tier | Source                                                                                           | How much you may claim                                                                                                                                                                                                          |
| ---- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | **External web / review research**                                                               | "Review-derived observation" tier. Category norms, forum threads, video reviews, comparison articles. Search generally — do not scrape Shopee. This is the tier a thread is built from: nobody in it is selling.                |
| 2    | **Seller material** — the `Description` column and the product page (only if it actually loaded) | "Seller's own description" tier. Background and orientation only — **never copy**. Its claims are leads to verify: a claim that matters needs tier-1 corroboration or it stays out. No quotes, no paraphrases, no attributions. |
| 3    | **Inference**                                                                                    | Reasonable deduction from tiers 1-2. **Always hedged**: _"kemungkinan", "biasanya", "bisa jadi"_.                                                                                                                               |
| 4    | **Unsupported**                                                                                  | Never used as a factual claim. Remove it, or rewrite it as an explicit hedge or a question.                                                                                                                                     |

**Tier 0 — the stored testimony.** With `Used=Yes` and a non-empty `Testimonial`
(Step 1.5), the human's own account exists, and it outranks everything below as
the source for _personal_ material: it is the only source that can support a
first-hand claim. Report it as theirs, never amplify, generalize, or extend it —
inventing beyond it fails the same way an unsupported claim fails. It is
testimony, not verified fact: research corroborates it and never replaces it.
In `none` mode there is no tier 0 at all, and no first-hand claim may ship.

Research runs in **both** modes. With a testimony it supplies the context, the
corroboration, and the real trade-off; the testimony supplies the personal
material.

### Why the seller's own words sit below independent sources

The `Description` column is written by the operator and the product page by the
seller. Both are trying to make the product look good, so neither can settle a
claim about it. A thread whose substance is a paraphrase of that copy is an
advertisement with a hook on it — the one thing this pipeline exists not to
produce.

What seller material is genuinely good for:

- **Orientation** — what the product physically is, and who it appears to be for.
  Angles need that context before they can be scored.
- **Vocabulary** — the seller's words for the product's features are often the
  words buyers search with.
- **A claim to check** — "tahan 12 jam" in the description is a lead for tier-1
  research, not a fact. If nothing independent confirms it, leave it out:
  attributing it ("Klaim di deskripsi produknya...") is still the seller's
  seat, and the copy never sits there.
- **The visual profile** — physical details for Step 7, taken as description
  rather than as proof.

When tiers 1 and 2 are both thin, do not compensate by building the thread out of
the seller's copy. Shift the whole thread toward a **category-level** observation —
the problem space, the buying decision, the common mistake — where you can be
specific without repeating marketing.

## Procedure

### 1. Read the Description — as orientation, not as evidence

Before any web call. It is the cheapest way to find out what the product is, and
it often contains the operator's own hint about why this product is interesting.

Extract:

- what the product is, physically
- who the seller says it is for
- what the seller claims it does
- anything distinctive: material, size, mechanism, included parts
- anything the operator flagged as a caveat

Then mark every one of those as _their_ claims. The list is a research agenda, not
a fact list.

### 2. Attempt the affiliate page once (best effort)

One attempt. If it fails, note the failure and move on. Do not retry with
variations.

If it does load, extract only what you can quote as a claim: stated
specifications, dimensions, materials, warranty — as leads for tier-1
verification. Remember it is tier 2 — the seller talking about their own
product, so nothing from it goes into the copy.

### 3. External research

Search the web for the product and, more importantly, for its category:

- `<product> review` / `<product> review Indonesia`
- `<category> worth it` / `<category> masalah` / `<category> salah beli`
- competitor comparisons
- forum and community discussions

The most useful output of this step is usually **not** product facts — it is the
vocabulary real people use when they talk about this category. That vocabulary is
what makes the copy sound like a person rather than a listing.

### 4. Build the visual profile

You will need this in Step 7 if images are generated. Record:

- overall shape and proportions
- colour(s), and whether they are the product's or the packaging's
- material and finish
- distinctive physical features (controls, ports, seams, included accessories)

**Do not record anything you did not actually see or read.** If the only
description is "power bank 20000mAh hitam", the visual profile is "rectangular,
black, matte, no visible controls established" — and that is the whole profile.

### 5. Write the evidence ledger

Before Step 4 of the main pipeline, write yourself a short ledger. This is what
the Evidence Checker in Step 6 checks against.

```
CLAIM                                          TIER  SOURCE
common complaint: heavy for a pocket           1     forum thread <url>
"usually enough for a day trip"                1     review roundup <url>
20000mAh capacity                              2     Description column (seller's number)
PD 22.5W output                                2     product page (seller claim)
"claims 2x charge for a typical phone"         2     product page, corroborated by review <url>
likely fine for a day trip                     3     inference from capacity
"charges in 30 minutes"                        4     UNSUPPORTED — drop
```

Anything that lands in tier 4 does not go into the draft. Not softened, not
implied — removed.

A ledger holding tier-2 rows is holding leads, not copy material. Any of them
either earns tier-1 corroboration or it leaves the thread — attributed tier-2
claims are gone with the rest. A ledger that is _all_ tier 2 is not a thread
yet: it is the seller's copy with different punctuation, and it fails the
editorial audit in `references/editorial-rules.md`.

## Hedging language

The copy carries tier-1 claims; what still needs hedging is a tier-3 inference
built on them. Hedge it in a way that sounds like a person being honest, not
like a disclaimer:

| Instead of                 | Write                                                                                      |
| -------------------------- | ------------------------------------------------------------------------------------------ |
| "Baterainya tahan 2 hari." | "Buat perjalanan sehari biasanya aman; lebih dari itu tergantung pemakaian."               |
| "Ini yang paling nyaman."  | "Yang paling sering disebut di review: bagian ini."                                        |
| "Kualitasnya bagus."       | "Untuk kelas harga ini, yang biasanya jadi patokan: [what the reviews actually check]."    |
| "Cocok untuk semua orang." | "Cocok kalau [specific scenario]. Kalau [other scenario], ada opsi lain yang lebih masuk." |

## What this step is not

- Not a reason to write a feature list. Research feeds the _angle_, not the copy.
- Not a licence to repeat the seller's copy. Seller material is background — the
  thread's substance comes from somewhere the seller does not control.
- Not a licence to review a product you never used: without a stored testimony
  (Step 1.5) you have no first-hand experience and may never imply one; with one,
  you may only use what it says.
- Not a virality study. You are looking for something true and specific that a
  person would find worth reading.
