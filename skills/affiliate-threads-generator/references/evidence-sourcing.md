# Evidence sourcing — description-first, Shopee-aware

## Why this file exists

The naive assumption is "fetch the product page, read the specs". That assumption
is wrong here. The `Affiliate URL` points at Shopee, which actively blocks
automated access. A failed fetch is the normal case, not an error to escalate.

**Hard rule: never attempt to bypass CAPTCHA, anti-bot measures or auth walls.**
Not with a different user agent, not with a headless browser, not with a proxy,
not with `execute_code`. If a page does not load, that is the end of that path.

## Confidence tiers

Every factual claim in the final copy must trace to exactly one of these.

| Tier | Source                                                | How much you may claim                                                                                                                |
| ---- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | **`Description` column**                              | Trusted and verified. The operator wrote it deliberately, for this product. This is the anchor.                                       |
| 2    | **Fetched product page** (only if it actually loaded) | "Seller marketing claim" tier. It may be true; it is not evidence. Attribute it: _"Klaim di halaman produknya..."_                    |
| 3    | **External web / review research**                    | "Review-derived observation" tier. Search generally — blogs, forum threads, video reviews, comparison articles. Do not scrape Shopee. |
| 4    | **Inference**                                         | Reasonable deduction from 1-3. **Always hedged**: _"kemungkinan", "biasanya", "bisa jadi"_.                                           |
| 5    | **Unsupported**                                       | Never used as a factual claim. Remove it, or rewrite it as an explicit hedge or a question.                                           |

When tiers 2 and 3 are both thin, do not compensate by inventing product detail.
Shift the whole thread toward a **category-level** observation — the problem space,
the buying decision, the common mistake — where you can be specific without
claiming things you cannot support.

## Procedure

### 1. Read the Description first, fully

Before any web call. The description is the operator's own framing of why this
product is interesting; it often contains the exact angle the human wants.

Extract:

- what the product is, physically
- who it is for
- what problem the operator believes it solves
- anything distinctive: material, size, mechanism, included parts
- anything the operator flagged as a caveat

### 2. Attempt the affiliate page once (best effort)

One attempt. If it fails, note the failure and move on. Do not retry with
variations.

If it does load, extract only what you can quote as a claim: stated
specifications, dimensions, materials, warranty. Remember it is tier 2.

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
20000mAh capacity                              1     Description column
PD 22.5W output                                1     Description column
"claims 2x charge for a typical phone"         2     product page (seller claim)
common complaint: heavy for a pocket            3     forum thread <url>
likely fine for a day trip                      4     inference from capacity
"charges in 30 minutes"                        5     UNSUPPORTED — drop
```

Anything that lands in tier 5 does not go into the draft. Not softened, not
implied — removed.

## Hedging language

When you must use a tier-3 or tier-4 claim, hedge it in a way that sounds like a
person being honest, not like a disclaimer:

| Instead of                 | Write                                                                                      |
| -------------------------- | ------------------------------------------------------------------------------------------ |
| "Baterainya tahan 2 hari." | "Klaim di halaman produknya tahan 2 hari — angka itu biasanya tergantung pemakaian."       |
| "Ini yang paling nyaman."  | "Yang paling sering disebut di review: bagian ini."                                        |
| "Kualitasnya bagus."       | "Bahannya [material from description], yang untuk kelas harga ini biasanya [expectation]." |
| "Cocok untuk semua orang." | "Cocok kalau [specific scenario]. Kalau [other scenario], ada opsi lain yang lebih masuk." |

## What this step is not

- Not a reason to write a feature list. Research feeds the _angle_, not the copy.
- Not a licence to review a product you never used. You have no first-hand
  experience and may never imply one.
- Not a virality study. You are looking for something true and specific that a
  person would find worth reading.
