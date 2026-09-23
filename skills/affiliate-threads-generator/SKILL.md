---
name: affiliate-threads-generator
description: >-
  Generate affiliate content for Meta Threads from Google Sheets candidates.
  Use for any request to create, regenerate, hold, cancel or approve Threads
  affiliate content — "buatkan content berikutnya", "generate lagi", "hold dulu
  yang ini", "saya approve", "regenerate tapi angle-nya lebih ke traveller".
  Runs the full pipeline: deterministic candidate selection, description-first
  research, angle discovery and scoring, a one-line point of view, narrative
  planning with a critic pass, drafting, an antislop audit, the affiliate
  editorial and evidence reviews, then a Telegram preview that waits for a human
  decision. Never publishes on its own.
version: 1.0.0
author: Affiliate Threads
license: MIT

# Credentials are declared here, never embedded in this skill or in the plugin.
#
# Declaring them does three things, all of them Hermes' own machinery:
#   1. Hermes prompts for any that are unset when this skill loads in the local
#      CLI, and stores them through the normal credential route. You can skip the
#      prompt and keep working — you simply cannot publish until it is set.
#   2. The declared names are forwarded into `terminal` and `execute_code`
#      children, which is how scripts/*.py sees them. Those children run with a
#      sanitized environment; an undeclared variable never reaches them.
#   3. On messaging platforms the prompt is replaced by local setup guidance, so
#      a secret is never collected in-band over Telegram.
required_environment_variables:
  - name: THREADS_ACCESS_TOKEN
    prompt: "Meta Threads long-lived user access token"
    help: >-
      Create a Meta app with the Threads use case, authorize with
      threads_basic + threads_content_publish, then exchange the short-lived
      token for a long-lived one. See docs/threads-app-setup.md.
    required_for: "publishing an approved thread (threads_publish)"
  - name: AFFILIATE_SHEET_ID
    prompt: "Google Sheets spreadsheet id"
    help: "The long id in the sheet URL, between /d/ and /edit."
    required_for: "reading candidates and recording publish results"
  - name: AFFILIATE_SHEET_TAB
    prompt: "Sheet tab name (Enter for Sheet1)"
    help: "The tab that holds the candidate table."
    required_for: "reading candidates"
  - name: THREADS_USER_ID
    prompt: "Meta Threads user id (optional — Enter to skip)"
    help: "Leave blank to let the plugin resolve it from GET /me."
    required_for: "pinning a specific Threads account"

# This skill reads and writes the Sheet through the bundled google-workspace
# skill, so it depends on that skill's OAuth artifacts. Declaring them lets
# Hermes report "setup needed" up front and mount them correctly on remote
# backends (Docker, Modal) instead of failing opaquely at the first Sheet call.
# Paths are relative to ~/.hermes/.
required_credential_files:
  - path: google_token.json
    description: "Google OAuth2 token created by the google-workspace setup script"
  - path: google_client_secret.json
    description: "Google OAuth2 client credentials from the Google Cloud Console"

metadata:
  hermes:
    tags: [Threads, Affiliate, Content, Marketing, Copywriting, Google Sheets]
    related_skills: [google-workspace]
    requires_toolsets: [web]
    blueprint:
      schedule: "0 8 * * 0,1,3,5"
      deliver: origin
      prompt: >-
        Load the skill affiliate-threads-generator:affiliate-threads-generator with
        skill_view, then generate the next affiliate thread for Meta Threads and send
        the preview. Process exactly one candidate, then stop and wait for a human
        decision.
---

# Affiliate Thread Generator

An affiliate content engine that turns one product candidate in Google Sheets into
a research-backed, conversation-oriented Threads thread — then stops and waits for
a human.

**The idea this skill is built around:**

> Do not ask "how do we sell this product?"
> Ask "what conversation is worth reading, and can this product naturally become
> a relevant solution?"

If the affiliate link were removed, the thread must still be worth reading.

---

## The one rule that is never negotiable

**You cannot publish.** There is no publishing path available to you except the
`threads_publish` tool, and that tool:

- re-reads the Sheet and refuses unless the row's `Status` is exactly
  `Ready To Generate`
- refuses unless the row's `Threads URL` is still empty
- enforces the hard guardrails (length, links, disclosure, affiliate URL,
  no fabricated first-hand experience)
- asks the human for a second confirmation through Hermes' approval gate
- writes `Status=Done` + `Threads URL` only after the posts are confirmed live

Do not try to reach the Threads API any other way — not with `terminal`, not with
`execute_code`, not with a browser. There is no token available to you anyway, and
attempting it is a process failure even if it would have worked.

Everything else in this skill is judgement. That one thing is not.

---

## Writing quality dependencies

The generic AI-writing filter is **not** in this skill. It lives in two external
skills, loaded through Hermes:

| Skill                  | What it is for                                                              |
| ---------------------- | --------------------------------------------------------------------------- |
| `antislop`             | the core filter — structural AI tells, filler, unsupported claims, CTA tone |
| `antislop-copywriting` | prose depth — rhythm, signposting, parallelism, fake-candid framing         |

Both are **optional**. Using them is the recommended setup; not having them is a
supported one. The pipeline always runs its own affiliate editorial and evidence
reviews — the external skills add the generic prose pass on top, and nothing
breaks without them.

When they are available:

1. Load both with `skill_view`.
2. Apply them as an **audit** of the draft, not only as advice while writing.
3. Never let anti-slop rules override affiliate evidence, disclosure, product
   fit, or safety requirements. They govern prose, not facts.
4. After the anti-slop pass, run this plugin's affiliate editorial review —
   `references/editorial-rules.md`.

When they are not, skip that pass and say so on the preview's anti-slop line
instead of implying an audit that did not happen. Do not reimplement the missing
rules from memory — that is how the two layers drift apart.

Setup, if you want it: [`docs/antislop-integration.md`](../../docs/antislop-integration.md).

---

## When to use this skill

Load it for anything in this family:

| The human says                                   | You do                                                |
| ------------------------------------------------ | ----------------------------------------------------- |
| "Buatkan content berikutnya." / "Generate lagi." | Full pipeline for one candidate → preview             |
| "Hold dulu yang ini."                            | Set that row's `Status=Hold`. Nothing else.           |
| "Yang ini jangan dipublish."                     | Set that row's `Status=Cancel`. Nothing else.         |
| "Saya approve." / "Post aja."                    | Call `threads_publish` for the Product ID on screen   |
| "Regenerate tapi angle-nya lebih ke X."          | Re-run from Step 3 with the new constraint            |
| "Kenapa belum ada yang jalan?"                   | Run the doctor script, report what is actually broken |

**Review context is always the Product ID most recently shown in this
conversation.** Never infer it from free text, and never guess when a session was
reset — ask.

---

## Quick reference

All scripts live in this skill's directory. `${HERMES_SKILL_DIR}` is substituted
for you when the skill loads.

| Need                              | Command                                                                    |
| --------------------------------- | -------------------------------------------------------------------------- |
| Pick the next candidate           | `python3 ${HERMES_SKILL_DIR}/scripts/select_candidate.py`                  |
| Set a status (hold/cancel/resume) | `python3 ${HERMES_SKILL_DIR}/scripts/set_status.py <PRODUCT_ID> <STATUS>`  |
| Lint a draft before showing it    | `python3 ${HERMES_SKILL_DIR}/scripts/validate_thread.py --json draft.json` |
| Health check                      | `python3 ${HERMES_SKILL_DIR}/scripts/doctor.py`                            |
| Threads token status / refresh    | `python3 ${HERMES_SKILL_DIR}/scripts/threads_token.py status`              |

| Tool                                                            | Use                                                              |
| --------------------------------------------------------------- | ---------------------------------------------------------------- |
| `threads_publish`                                               | The only way to publish. Requires explicit human approval first. |
| `threads_check`                                                 | Read-only preflight. Use before claiming something is broken.    |
| `skill_view("google-workspace")`                                | Sheet reads/writes and the OAuth setup                           |
| `skill_view("antislop")` · `skill_view("antislop-copywriting")` | The generic writing-quality filter. Load both before drafting.   |
| Hermes web/browser tools                                        | External research                                                |

---

## Procedure

### Step 0 — Orient

Decide which of these you are doing, then follow only that branch:

1. **Generate** (scheduled or manual) → Steps 1-8.
2. **Hold / Cancel / Resume** → read `references/telegram-actions.md`, run
   `set_status.py`, confirm to the human, stop.
3. **Approve** → read `references/telegram-actions.md`, then call
   `threads_publish` with the approved Product ID and the exact copy from the
   preview.
4. **Regenerate** → keep the same Product ID and the research from Step 2, jump
   to Step 3 with the human's new constraint.
5. **Diagnose** → `scripts/doctor.py`, then report.

One generation request processes **exactly one** candidate. Never batch, never
continue to a second product in the same request.

### Step 1 — Candidate selection (deterministic)

Run the script. Do not hand-pick from a raw Sheet dump.

```bash
python3 ${HERMES_SKILL_DIR}/scripts/select_candidate.py
```

It re-reads the Sheet, filters to rows whose `Status` is exactly
`Ready To Generate`, and returns the lowest numeric ID. Output is JSON:

```json
{
  "ok": true,
  "candidate": {
    "id": "12",
    "product": "...",
    "affiliate_url": "...",
    "row": 14
  }
}
```

- `candidate: null` → nothing is eligible. Tell the human plainly and **stop**.
  Never fall back to a different status, never invent a candidate.
- Never process more than one row per request, scheduled or manual.

Read the candidate's full row (including `Description`) before moving on:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/select_candidate.py --id 12 --full
```

### Step 2 — Research (description-first, Shopee-aware)

The `Affiliate URL` points at Shopee, which blocks automated access. **A failed
fetch is expected, not a pipeline failure.** Never attempt to bypass CAPTCHA,
anti-bot or auth walls — that is a hard rule, not a preference.

Confidence tiers, highest first:

1. **`Description` column** — trusted/verified. The operator wrote it for this
   product. Everything anchors here.
2. **Fetched product page** (only if it genuinely succeeds) — "seller marketing
   claim" tier. Not automatically true.
3. **External web/review research** — "review-derived observation" tier. Search
   the web generally; do not scrape Shopee.
4. **Inference** — reasonable deduction from 1-3. Always hedged.
5. **Unsupported** — never used as a factual claim. Remove or rewrite it.

If tiers 2 and 3 both come back thin, shift to a **category-level**
problem/observation framing instead of inventing product-specific detail.

Also build a **visual profile** while researching: shape, colour, material,
distinctive physical features. You will need it in Step 7.

Full procedure: `references/evidence-sourcing.md`.

### Step 3 — Angle discovery

Generate **5-8 distinct angle candidates**. Never jump to one "best angle".

Each candidate is `{angle_type, core_idea, tension}`. Draw `angle_type` from the
library in `references/angle-library.md`.

Then score each 0-10 on: `relevance`, `curiosity`, `specificity`,
`evidence_strength`, `conversation_potential`, `product_fit`, `salesiness_penalty`,
`novelty_vs_recent`.

**`product_fit` alone must never dominate.** A high-fit, low-curiosity angle loses
to a lower-fit, genuinely interesting one. This is not a virality forecast — it is
a filter for "would a person stop and read this?".

**Novelty check (no database).** Recall recent content notes from Hermes memory —
each published thread saved `{content_id, angle_type, topic, hook_pattern}`. If the
leading angle repeats a recent `angle_type` or `hook_pattern`, penalise it and pick
the next one. Read `references/content-rules.md` for the exact memory format.

Show the human your angle shortlist only when they asked to see the reasoning.
Otherwise carry it into Step 4.

### Step 4 — Point of view → narrative planner → narrative critic

**Point of view.** Write the thread's position in one line before anything else:

> "Jumlah tekstur bukan hal pertama yang perlu dilihat dari mainan seperti ini."

If the line is generic ("produk ini punya beberapa kelebihan dan kekurangan"),
stop. That is an angle problem, not a wording problem — go back to Step 3.

**Planner.** Decide, explicitly:

- topic, audience, and the point of view above
- the tension that makes it worth reading
- hook strategy for post 1
- the objective of each post — what the reader notices, understands, or can do
  next because of it (objectives, not a fixed role template)
- where the product becomes relevant, and why the narrative is ready for it
  there (post 3-4 is the normal range, not a rule)
- which post carries the CTA and the disclosure
- `affiliate_intensity` — default `2` (roughly 80% value, 20% product)
- `must_include` and `must_not_claim` lists
- which evidence tier each factual claim traces to

**Critic.** Before writing a single line of copy, answer all nine questions in
`references/narrative-planner-critic.md`. If any answer is weak, revise the plan.

Bounded loop: **2-3 revision rounds maximum.** If it still fails after that, pick
a different angle from Step 3 rather than looping forever.

### Step 5 — Thread generation

Write **3-6 posts**. Dynamic — post length varies, and not every thread is the
same shape. Rotate the narrative structure across runs; never default to
`Hook → 3 benefits → CTA`. The structures are in
`references/content-rules.md`.

Follow the content philosophy in `references/content-rules.md` and the editorial
rules in `references/editorial-rules.md`. The short version:

```
Audience → Problem/curiosity/observation → Interesting insight →
Specific evidence → Possible solution → Product → Contextual CTA + disclosure
```

Select the two to four details the angle needs. Leave the rest in the research.
Include a genuine, evidence-backed trade-off when the angle has room for one —
and never fabricate a weakness.

**Hard rule — no fabricated personal experience.** Never write _"Aku sudah
coba..."_, _"Saya pakai ini setiap hari..."_, _"Menurut pengalaman saya..."_. The
system has never touched the product. Write _"Dari spesifikasi produk..."_,
_"Berdasarkan review yang tersedia..."_, _"Untuk skenario seperti ini..."_.

### Step 6 — Audit, rewrite, then lint

Four passes on the draft, in this order:

1. **Anti-slop audit** (when the skills are installed) — with `antislop` and
   `antislop-copywriting` loaded, ask what makes this obviously AI-written.
   Structure, rhythm, signposting, symmetry and unnecessary explanation count
   for more than vocabulary. If the skills are not installed, skip this pass and
   note it on the preview's anti-slop line.
2. **Affiliate editorial review** — the questions in
   `references/editorial-rules.md`: is there a point of view? would the thread be
   useful without the link? is the product supporting the conversation rather
   than starring in it? is the ending earned rather than a summary?
3. **Evidence review** — every factual claim traces to one of Step 2's tiers.
   Anything untraceable is removed or rewritten as an explicit hedge. Check that
   the rewrite did not introduce a new fact or drop a qualification.
4. **Deterministic lint** — the same check the publish tool will run:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/validate_thread.py --json draft.json
```

Fix every `violation`. Read the `warnings` and decide — they are signals, not
orders. Alongside the phrase warnings, `validate_thread.py` reports four
structural signals: `excessive_signposting`, `repeated_transition_density`,
`excessive_enumeration`, `product_detail_density`. None of them blocks, and none
of them is proof that the text is AI-written — treat each as a reason to look
again.

Do not show the human a draft that still has violations.

Bounded loop: **2 revision rounds maximum.** If the thread still reads as
templated after two rounds, the angle is the problem — go back to Step 3 and take
the next candidate. Do not keep polishing the same structure.

### Step 7 — Image (optional)

Only if Hermes' image tool is available (that is, `FAL_KEY` is configured). Not
every post needs an image.

Derive the brief from the Step 2 visual profile and the narrative intent. The
image must preserve the product's recognizable physical characteristics — shape,
colour, material, distinctive features. **Never invent controls or features that
the research did not establish.**

If the image tool is unavailable, publish text-only. That is a normal path, not a
degraded fallback — do not apologise for it, do not mention it.

### Step 8 — Telegram preview

Send the preview in exactly this shape, so the human always has the review context
in front of them:

```
📦 Product ID: <ID>
🏷️ <Product> — <Category>
🎯 Angle: <angle_type> — <core idea in one line>
🧭 Structure: <the narrative structure you used>
📊 Evidence: description (primary) · <what else you actually found>
🧹 Anti-slop: antislop + antislop-copywriting · <N> revision round(s)
🖼️ Image: <yes, N images | text-only>

———————————————

POST 1/N
<copy>

POST 2/N
<copy>
...

———————————————
Link: <affiliate url>
Disclosure: <the disclosure line you used>

Reply with: approve · hold · cancel · regenerate <what to change>
```

**The Product ID line is mandatory.** It is the review context for every
approve/hold/cancel that follows. Do not use a separate store, do not rely on
conversation memory across a reset.

**The Anti-slop line is mandatory too**, and it reports what actually happened.
Without the external skills it reads
`🧹 Anti-slop: not installed — affiliate editorial + evidence review only`.
That is a normal configuration, not a defect: never present a draft as
anti-slop-audited when the skills were not loaded.

Then **stop**. Do not publish. Do not ask "should I publish?" in a way that makes
approval the default. Wait.

---

## Handling the human's reply

Full semantics, including edge cases and exact wording: `references/telegram-actions.md`.

| Reply                             | Action                                                                                               |
| --------------------------------- | ---------------------------------------------------------------------------------------------------- |
| approve / setuju / post aja / gas | Call `threads_publish` with the Product ID from the preview and the exact copy. Then report the URL. |
| hold                              | `set_status.py <ID> Hold`. No publish.                                                               |
| cancel / jangan dipublish         | `set_status.py <ID> Cancel`. No publish.                                                             |
| regenerate <constraint>           | Step 3 again, same Product ID, same research unless new info is needed.                              |

**Approval must be explicit, in the current turn, for the product on screen.**
Silence is not approval. An earlier "approve" for a different product is not
approval. Your own judgement that the copy is good is not approval.

After a successful publish, save a content-memory note:
`{content_id: <ID>, angle_type, topic, hook_pattern}` — see
`references/content-rules.md` for the format. This is what makes the next
thread's novelty check possible.

---

## Pitfalls

| Symptom                                           | What is actually happening                                                                                    |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `threads_publish` returns `stage: "precondition"` | The Sheet row changed — probably held or cancelled after the preview. Report it; do not retry.                |
| `stage: "guardrails"`                             | The copy breaks a hard rule. Fix the listed violations and show a new preview.                                |
| `stage: "credentials"`                            | No `THREADS_ACCESS_TOKEN`. Setup problem, not a content problem.                                              |
| `stage: "publish"` with a rate-limit code         | Threads allows 250 posts / 1000 replies per 24h. Wait; do not hammer it.                                      |
| `status: "published_sheet_write_failed"`          | **The thread is live.** Do not publish again. Re-call with the same `product_id` — it only repairs the Sheet. |
| Shopee page fetch failed                          | Expected. Move to description-first framing; do not retry with a bypass.                                      |
| `select_candidate.py` returns `candidate: null`   | Nothing is `Ready To Generate`. Say so and stop.                                                              |
| Human replies with just "ok"                      | Ambiguous. Ask which of approve/hold/cancel they mean.                                                        |

## Verification

Before you send the preview, confirm all of these are true:

- [ ] The candidate came from `select_candidate.py`, not from a hand-read Sheet
- [ ] Exactly one candidate was processed
- [ ] 5-8 angles were generated and scored before one was chosen
- [ ] The novelty check against recent content notes ran
- [ ] A one-line point of view existed before drafting, and it is not generic
- [ ] The narrative critic answered all nine questions
- [ ] `antislop` and `antislop-copywriting` were loaded, or the preview says they were not
- [ ] The anti-slop audit ran as an audit of the draft, not only as writing advice
- [ ] The affiliate editorial review ran after it
- [ ] Every factual claim traces to a named evidence tier
- [ ] No fabricated first-hand experience
- [ ] A trade-off or limitation is present when the angle has room for one, and it is real
- [ ] Disclosure is present, short, and on the same post as the affiliate URL
- [ ] The ending gives the reader something useful instead of summarizing
- [ ] `validate_thread.py` reports zero violations
- [ ] The preview shows the Product ID explicitly
- [ ] You stopped and waited instead of publishing
