# Editorial rules

The affiliate-specific editorial layer. Read it before drafting, and run the
audits in section 9 after every draft and every rewrite.

`antislop` and `antislop-copywriting` remove the generic AI tells — vocabulary,
rhythm, signposting, forced parallelism, filler. This file is what is left when
they are done: the rules that only apply to affiliate Threads content, and the
audit that enforces them.

The two layers do not overlap. The external skills own prose. This file owns the
editorial intent.

---

## 1. Point of view first

Every thread has an editorial position — something the writer believes and wants
the reader to notice. A thread without one becomes a product description with
transitions.

Weak:

> Produk ini memiliki banyak tekstur.

Better:

> Jumlah tekstur bukan hal pertama yang perlu dilihat dari mainan seperti ini.

The second creates a position the thread can explore. The first is a fact waiting
for a template.

**The gate:** write the point of view in one line before drafting. If it is
generic — "produk ini punya beberapa kelebihan dan kekurangan" — stop. That is an
angle problem, not a wording problem. Go back to Step 3 and take the next
candidate.

## 2. Select details, do not dump research

Research may hold twenty facts. A thread is not a summary of research.

```
Research: 20 facts → shortlist: 5 useful facts → thread: 2-4 facts
```

The rest stay in the research notes. A thread that lists everything the research
found is a feature list wearing a narrative costume.

## 3. Do not explain every transition

Do not narrate the reasoning. "Jadi...", "Makanya...", "Contohnya...", "Dengan
kata lain...", "Kesimpulannya..." are all ordinary Indonesian — once. Three of
them in one thread is a rhythm the reader can feel, and it reads as
machine-written even when every sentence is true.

A transition earns its place only when it adds meaning the previous sentence did
not have.

`validate_thread.py` reports this as `repeated_transition_density`. It is a
warning, never a block.

## 4. Do not force a perfectly balanced thread

Post lengths vary. One post may be a single sentence. Another may be three. A
third may be one compact observation. Uniform post construction is a warning
sign, not a sign of craft.

The same goes for content balance: a thread does not need one drawback, one
benefit, one example and one summary. It needs whatever the angle actually
requires.

## 5. Product entry is earned, not scheduled

The product enters when the reader already has a reason to care.

Post 3-4 is the normal range, not a rule. The test is not "is this post 3?" but
"would a reader who has not bought anything still want this here?".

## 6. The thread does not need to cover everything

- Do not add a second drawback because the thread already has one.
- Do not add a specification because it is available.
- Do not create a "complete guide" feeling unless the chosen angle is actually a
  guide.

Coverage is not the goal. A thread that says one thing well beats a thread that
says five things adequately.

## 7. End on useful information, not a summary

Avoid closing with a restatement of everything above ("Jadi, produk ini cocok
untuk..."). End on one of:

- a practical boundary ("lebih masuk untuk dimainkan sambil ditemani")
- a buying consideration
- one concrete observation
- a contextual product detail
- a natural next action

The CTA and the disclosure come after that ending. They do not replace it.

## 8. Disclosure — explicit but lightweight

The disclosure is mandatory and stays on the post that carries the affiliate URL.
It does not need to be a paragraph. Which shape counts is the operator's setting:

- `disclosure_style: marker` (default) — any configured marker, anywhere.
  Preferred forms:

```
Link afiliasi.
```

```
Link afiliasi ↓
```

```
Detail produk:
https://...

Link afiliasi.
```

- `disclosure_style: tag` — a hashtag marker, `#ad`, on the **final** post. That
  tag alone is the disclosure: no sentence about commission is needed, which is
  the form to prefer when a sentence reads as hard-sell. It has to be on the last
  post, because that is the one carrying the link.

Under `publish_mode: two_stage` the link — and therefore the disclosure — belongs
to the link reply, not to the thread body. The thread then carries no "link
afiliasi nanti di reply" teaser either: it has to stand on its own without
promising a link.

The wording may vary as long as the commercial relationship is clear. What is not
allowed is hiding it, burying it under hashtags, or dropping it because the
ending reads better without it. `threads_publish` refuses to publish a thread
that does not satisfy the configured style, and that check is code, not judgement.

## 9. The audit passes

Two passes, in this order, after the draft and after every rewrite. Then the
evidence pass.

### 9.1 Anti-slop audit — the external skills

Run this when `antislop` and `antislop-copywriting` are installed. Their job is
the generic prose tells. Ask:

```
What makes this obviously AI-written?

Do not focus only on vocabulary. Look for structure, rhythm, signposting,
symmetry, and unnecessary explanation.
```

Their catalogue covers AI vocabulary, fake-candid openers, signposting
announcements, rule-of-three overuse, negative parallelism, staccato drama,
filler, generic conclusions and promotional tone. Do not duplicate that work
here — load the skills and apply them.

Installing them is optional. If they are not installed, skip this pass, run the
audits below, and say so on the preview's anti-slop line. A draft that did not go
through the generic pass must never be presented as if it did, and the missing
rules must not be reimplemented from memory — that is how the two layers drift
apart.

### 9.2 Affiliate editorial audit — this plugin

Run this after the anti-slop pass, on the same draft. The anti-slop skills do not
know what an affiliate thread is; this pass does.

```
Does this thread have a clear point of view?
Would the thread still be useful if the affiliate link disappeared?
Is the product supporting the conversation rather than becoming a product listing?
Is the thread more than a paraphrase of the seller's description?
Did we select only the evidence the angle required?
Does the ending feel like the natural next step of the conversation?
Is the disclosure present, short, and on the post the configuration expects?
```

### 9.3 Evidence pass — last

```
Does every product-specific factual claim have an evidence tier?
Did rewriting accidentally introduce a new fact?
Did anti-slop rewriting remove an important qualification?
Did the writer invent a personal experience?
```

### 9.4 The audit record

Hold this shape internally — it is what makes the rewrite targeted instead of a
re-roll:

```yaml
anti_slop_audit:
  obvious_ai_phrases: []
  signposting: []
  fake_candid: []
  forced_parallelism: []
  rule_of_three: []
  staccato_drama: []
  generic_claims: []
  generic_conclusion: []
  filler: []
  repetitive_structure: []
  promotional_language: []
  rhythm_problem: []
  voice_problem: []

editorial_audit:
  point_of_view: true
  interesting_without_product: true
  product_supports_story: true
  evidence_selective: true
  product_fit: true
  natural_ending: true
  disclosure_clear: true
```

The human does not see this unless they ask for it.

## 10. Bounded revision

```
Draft → anti-slop audit → affiliate audit → rewrite → second audit → final
```

**Two revision rounds maximum.**

If the thread still reads as templated after two rounds, stop polishing. The
problem is the angle, not the wording. Go back to Step 3, take the next-best
candidate from the shortlist, and write again. That is faster and produces better
copy than grinding the same structure.

## 11. What this file does not do

- It does not ban common words. "Jadi", "contoh" and "makanya" are ordinary
  Indonesian; the problem is density, not existence.
- It does not replace the evidence rules. A well-written claim with no evidence
  tier is still removed.
- It does not put publishing authority anywhere new. The pipeline still ends at
  the human's approval and the `threads_publish` tool.
- It does not override the hard guardrails. Character limits, the affiliate URL,
  the disclosure and the fabricated-experience ban are enforced in code, and a
  rewrite that breaks one is a rewrite that gets rejected.
