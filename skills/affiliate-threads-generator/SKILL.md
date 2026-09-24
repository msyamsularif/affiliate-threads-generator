---
name: affiliate-threads-generator
description: >-
  Generate affiliate content for Meta Threads from Google Sheets candidates.
  Use for any request to create, regenerate, hold, cancel or approve Threads
  affiliate content — "buatkan content berikutnya", "generate lagi", "hold dulu
  yang ini", "saya approve", "regenerate tapi angle-nya lebih ke traveller".
  Runs the full pipeline: deterministic candidate selection, the experience
  check (asks whether the human has used the product before any research),
  review-first research (the seller's description is background, never
  evidence), angle discovery and scoring, a one-line point of view, narrative
  planning with a critic pass, drafting, an antislop audit, the affiliate
  editorial and evidence reviews, then a Telegram preview that waits for a
  human decision. Never publishes on its own.
version: 1.1.1
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
- enforces the hard guardrails (length, links, affiliate URL,
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
3. Never let anti-slop rules override affiliate evidence, product
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

| Need                              | Command                                                                                          |
| --------------------------------- | ------------------------------------------------------------------------------------------------ |
| Pick the next candidate           | `python3 ${HERMES_SKILL_DIR}/scripts/select_candidate.py`                                        |
| Set a status (hold/cancel/resume) | `python3 ${HERMES_SKILL_DIR}/scripts/set_status.py <PRODUCT_ID> <STATUS>`                        |
| Record the experience answer      | `python3 ${HERMES_SKILL_DIR}/scripts/set_experience.py <PRODUCT_ID> --used no`                   |
| Lint a draft before showing it    | `python3 ${HERMES_SKILL_DIR}/scripts/validate_thread.py --file draft.json --topic-tag "<topic>"` |
| Health check                      | `python3 ${HERMES_SKILL_DIR}/scripts/doctor.py`                                                  |
| Threads token status / refresh    | `python3 ${HERMES_SKILL_DIR}/scripts/threads_token.py status`                                    |

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

1. **Generate** (scheduled or manual) → Steps 1-8, with the Step 1.5 question
   whenever the experience answer is blank.
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

Read the candidate's full row — `Category`, `Description`, and the `Used` /
`Testimonial` answer — before moving on:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/select_candidate.py --id 12 --full
```

The description orients you — what the product is, how it is described — but it
is the seller's own copy. Never treat it as evidence; Step 2 says what counts.

### Step 1.5 — Experience check (ask-first)

The row's `Used` and `Testimonial` columns decide the mode everything after this
point is written and validated under. The mode comes from the Sheet — you never
choose it:

| Row state                            | Mode        | What the copy may claim                              |
| ------------------------------------ | ----------- | ---------------------------------------------------- |
| `Used=Yes` + non-empty `Testimonial` | `firsthand` | first-hand claims, traceable to the stored testimony |
| `Used=No`                            | `none`      | no first-hand claim at all                           |
| `Used=Yes`, empty testimony          | `none`      | ask once more for the testimony                      |
| `Used` blank                         | —           | ask first (below), and never guess                   |

**Blank → ask, then stop.** Send the question with the Product ID and the
product name, and wait — do not research, draft, or skip ahead:

```text
📦 Product ID: <ID>
🏷️ <Product> — <Category>
Sebelum saya riset: produk ini pernah kamu pakai sendiri?

• "belum" → saya tulis observation-only (tanpa klaim pengalaman)
• "pernah" + testimoni singkat (lama pakai, dipakai untuk apa, plus/minus)
```

On the answer, store it verbatim and continue from Step 2 in the same turn:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/set_experience.py 12 --used no
python3 ${HERMES_SKILL_DIR}/scripts/set_experience.py 12 --used yes --testimonial "<their own words>"
```

- **"belum"** → `--used no`. The copy is observation-only.
- **"pernah" + testimony** → `--used yes --testimonial "..."`, exactly their
  words: never paraphrase, summarize, or extend them. The stored text is tier 0
  in the evidence ledger (Step 2), and nothing in the copy may go beyond it.
- **"pernah" with no detail** → ask once for one sentence (how long, what for,
  what was good or not). If they still do not give one, store `--used yes` with
  no testimony: it validates as `none`, and the preview says so.
- If the conversation was reset since the question, ask which Product ID the
  answer belongs to — the question shows it; never guess.
- `ask_experience: false`, or a layout without the two columns, means there is
  no question: validate every draft as `none`.

A blank answer never generates. Scheduled and manual runs behave identically:
an unanswered question parks the run, and a later scheduled run asks again —
that repetition is by design, because there is no hidden state.

### Step 2 — Research (review-first, Shopee-aware)

The `Affiliate URL` points at Shopee, which blocks automated access. **A failed
fetch is expected, not a pipeline failure.** Never attempt to bypass CAPTCHA,
anti-bot or auth walls — that is a hard rule, not a preference.

Confidence tiers, highest first:

0. **The stored testimony** (the row's `Testimonial`, `firsthand` mode only) —
   the one source that can support a first-hand claim. It is the human's own
   account: report it as theirs, never amplify, generalize, or extend it.
1. **Independent evidence** — external web and review research: category norms,
   forum and community discussion, comparison articles, video reviews. Search
   generally; do not scrape Shopee. Nothing in this tier is written by someone
   selling the product, which is why the thread's substance comes from here.
2. **Seller material** — the `Description` column and, if it loads, the product
   page. The operator wrote the description and the seller wrote the page; both
   are self-description, so they are **background, not proof — and never copy**.
   Use them for orientation — what the product is, who it is for, which moment
   it plausibly serves, the physical details — and as a research agenda: every
   claim in them is a lead to verify with tier-1 evidence or to leave out.
   Nothing from them is quoted, paraphrased, or attributed in the copy
   ("Klaim di deskripsi produknya..." is the seller's seat too), apart from the
   bare identifiers a reader needs to find the right variant in the link post.
   A thread that repeats the seller's copy is an advertisement wearing a hook.
3. **Inference** — reasonable deduction from 1-2. Always hedged.
4. **Unsupported** — never used as a factual claim. Remove or rewrite it.

If tiers 1 and 2 both come back thin, shift to a **category-level**
problem/observation framing instead of inventing product-specific detail.

Research runs in **both** modes. In `firsthand` mode it supplies the context,
the corroboration, and the real trade-off; the testimony supplies the personal
material — never the other way round.

Also build a **visual profile** from what the material actually shows: shape,
colour, material, distinctive physical features. You will need it in Step 7.

Full procedure: `references/evidence-sourcing.md`.

### Step 3 — Angle discovery

Generate **5-8 distinct angle candidates**. Never jump to one "best angle".

First resolve the two pattern inputs in `references/category-playbook.md`: the
row's `Category` maps to a family, and the `Description` is read for orientation
only — what the object is and which moment it plausibly serves, never sentences
or claims to reuse. The family fixes the audience, the angles and hooks that
fit, and the sentence patterns; it never loosens the evidence rule.

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
- the `category_family` from `references/category-playbook.md`, and the
  audience address the copy will use
- the tension that makes it worth reading
- hook strategy for post 1, and the `hook_pattern` behind it — the shape rotates
  across runs too (`references/hook-patterns.md`)
- the objective of each post — what the reader notices, understands, or can do
  next because of it (objectives, not a fixed role template)
- the bridge between posts — what each post hands to the next, so the thread
  reads as one thought moving forward
- where the product becomes relevant, and why the narrative is ready for it
  there (post 3-4 is the normal range, not a rule)
- which post carries the CTA
- the `topic_tag` — one topic for the root post, and the topic a reader would
  search for. It is metadata, never text (Step 5)
- `affiliate_intensity` — default `2` (roughly 80% value, 20% product)
- `must_include` and `must_not_claim` lists
- which evidence tier each factual claim traces to

**Critic.** Before writing a single line of copy, answer all twelve questions in
`references/narrative-planner-critic.md`. If any answer is weak, revise the plan.

Bounded loop: **2-3 revision rounds maximum.** If it still fails after that, pick
a different angle from Step 3 rather than looping forever.

### Step 5 — Thread generation

Write **3-10 posts**. Dynamic — post length varies, and not every thread is the
same shape. Rotate the narrative structure across runs; never default to
`Hook → 3 benefits → CTA`. The structures are in `references/content-rules.md`,
the opening shapes in `references/hook-patterns.md`.

**No post carries a hashtag.** Threads is not Instagram: exactly one tag per post
becomes clickable, it is called a topic tag, and it is passed to
`threads_publish` as `topic_tag` — metadata, not copy. A hashtag trail at the end
of a reply buys no reach and is the clearest tell that a thread is an ad; the
tool refuses it (`hashtag_in_copy`), and nothing is allowlisted by default. Pick
the one topic a reader would search for —
the conversation, not the product name — within the platform's limits (1-50
characters, no `.` or `&`, no leading `#`). Details: `references/content-rules.md`.

Follow the content philosophy in `references/content-rules.md` and the editorial
rules in `references/editorial-rules.md`. The short version:

```
Audience → Problem/curiosity/observation → Interesting insight →
Specific evidence → Possible solution → Product → Contextual CTA
```

Select the two to four details the angle needs. Leave the rest in the research.
Include a genuine, evidence-backed trade-off when the angle has room for one —
and never fabricate a weakness.

**Write in the family's register** (`references/category-playbook.md`): spoken
Indonesian in the second person — friendly, casual, polite. Colloquial is right
("banget", "sih", "kok", "nih", "deh"); brochure phrasing ("produk ini
menawarkan…", "sangat cocok bagi…") is not. Address the audience the family
names, not a generic "kalian". The playbook's patterns are shapes with
placeholders — fill them with facts the research established, never copy the
example sentences.

**Posts have to connect.** Each post opens from the thought the previous one
left behind; a reader who lands mid-thread can tell what conversation they
joined. No orphan post, and no post that only summarizes — the ending hands the
reader something useful.

**The seller's seat.** The `Description` orients the research; it never reaches
the copy. No claim, praise, urgency, or sentence from it — not quoted, not
paraphrased, not attributed ("Klaim di deskripsi produknya…" included). A claim
it raises is a lead to verify with independent evidence or to drop. Bare
identifiers (the shade, size, or contents a reader needs to find the right
variant in the link post) are the one exception, and they carry no promise.

**The personal experience rule.** The mode the row resolved to in Step 1.5
decides this:

- In `none` mode: no first-hand claim at all. Never write _"Aku sudah coba..."_,
  _"Saya pakai ini setiap hari..."_, _"Menurut pengalaman saya..."_. Write
  _"Dari spesifikasi produk..."_, _"Berdasarkan review yang tersedia..."_,
  _"Untuk skenario seperti ini..."_ instead.
- In `firsthand` mode: first-hand claims are allowed inside what the stored
  testimony says. No invented duration, outcome, comparison, or number; the
  voice follows the witness (if the testimony says the child used it, the copy
  says so — never _"saya pakai"_); and guarantee language — _"dijamin"_,
  _"100% ampuh"_, _"pasti sembuh"_ — is refused in both modes

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
   than starring in it? is the copy in the family's register, and does every post
   connect to the one before it? is the ending earned rather than a summary? is
   there a line written from the seller's seat?
3. **Evidence review** — every factual claim traces to one of Step 2's tiers.
   Anything untraceable is removed or rewritten as an explicit hedge. Check that
   the rewrite did not introduce a new fact or drop a qualification.
4. **Deterministic lint** — the same check the publish tool will run In
   `firsthand` mode, every first-hand sentence must trace to the stored
   testimony too — a detail it does not contain fails this pass.:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/validate_thread.py --file draft.json
```

Fix every `violation`. Read the `warnings` and decide — they are signals, not
orders. Alongside the phrase warnings, `validate_thread.py` reports four
structural signals — `excessive_signposting`, `repeated_transition_density`,
`excessive_enumeration`, `product_detail_density` — plus `funnel_phrase` for
copy that only talks the reader toward the link ("klik link di bawah", "link di
bio", "cek reply") and `seller_viewpoint` for copy written from the seller's
seat. None of them blocks, and none of them is proof that the text is
AI-written — treat each as a reason to look again.

Three violations are newer to the list and easy to trip: `hashtag_in_copy` (a
`#tag` in the copy — any hashtag, and only explicitly allowlisted tokens may
stay), `topic_tag_missing`
(no topic tag was passed while `require_topic_tag` is on), and `topic_tag_invalid`
(the tag breaks the platform's own limits — that publish would have failed at the
API).

The lint follows the publish mode, so pass `--stage` when you are linting
something other than a whole thread. Under `publish_mode: two_stage` the thread
body is correctly missing the affiliate URL — it belongs to the link reply — and
the script says so instead of flagging it. Lint that reply with `--stage link`.

Do not show the human a draft that still has violations.
Pass `--product-id` so the lint reads the row's own experience answer — the mode
and the stored testimony — instead of assuming `none`. With no row to read, the
explicit form is `--experience firsthand --testimonial "<stored text>"`.

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
🏷️ <Product> — <Category> · <family>
🎯 Angle: <angle_type> — <core idea in one line>
🧭 Structure: <the narrative structure you used> · hook: <hook_pattern>
🔖 Topic: <topic_tag>
📊 Evidence: independent research — <what the substance traces to>
🧪 Experience: <none — tanpa klaim pengalaman | firsthand — dari testimoni tersimpan>
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

Reply with: approve · hold · cancel · regenerate <what to change>
```

**The Product ID line is mandatory.** It is the review context for every
approve/hold/cancel that follows. Do not use a separate store, do not rely on
conversation memory across a reset.

**The `🏷️` line carries the playbook family** (`<Category> · <family>`) — which
audience and register the copy was written for, so a wrong mapping is visible
before approval.

**The Topic line is mandatory too.** It is the tag that will be published with
the root post, so the human can veto it before anything goes out; changing it
never changes the copy. If they ask for a different one, take theirs (checked
against the platform's limits) instead of arguing from your shortlist.

**The Experience line is mandatory too** — `none` or `firsthand`, the mode the
row resolved to. It tells the human which rule the copy was written under and,
in `firsthand` mode, that the first-hand material came from their stored
testimony.
**The Anti-slop line is mandatory too**, and it reports what actually happened.
Without the external skills it reads
`🧹 Anti-slop: not installed — affiliate editorial + evidence review only`.
That is a normal configuration, not a defect: never present a draft as
anti-slop-audited when the skills were not loaded.

**When `publish_mode` is `two_stage`,** the copy you preview has no affiliate
link in it — it is deferred to the link reply. Say so on the
preview (replace the `Link:` line with something like
`🔗 Link: belum dipasang — akan jadi reply setelah post dapat view`), because
"approve" now means "publish this thread", not "publish this thread and its
link". Never let the human approve expecting a link that is not in the copy.

Then **stop**. Do not publish. Do not ask "should I publish?" in a way that makes
approval the default. Wait.

---

## Handling the human's reply

Full semantics, including edge cases and exact wording: `references/telegram-actions.md`.

| Reply                             | Action                                                                                                                                                         |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| approve / setuju / post aja / gas | Call `threads_publish` with the Product ID from the preview, the exact copy, and the preview's topic tag. Then report the URL.                                 |
| ganti tag-nya jadi <X>            | Change only the topic tag, checked against the platform's limits, and re-show the topic line. The copy does not move — the tag is metadata.                    |
| pasang linknya / tambahkan link   | Two-stage mode only. Preview the one-post link reply, wait for approval, then call `threads_publish` with the same Product ID, `stage: "link"`, and that post. |
| hold                              | `set_status.py <ID> Hold`. No publish.                                                                                                                         |
| cancel / jangan dipublish         | `set_status.py <ID> Cancel`. No publish.                                                                                                                       |
| regenerate <constraint>           | Step 3 again, same Product ID, same research unless new info is needed.                                                                                        |

| belum / belum pernah pakai | `set_experience.py <ID> --used no`, confirm briefly, then continue from Step 2 in `none` mode. |
| pernah, ini testimoni: <text> | `set_experience.py <ID> --used yes --testimonial "<their words>"`, confirm briefly, then continue from Step 2 in `firsthand` mode. |
**Two-stage publishing (`publish_mode: two_stage`).** Approval publishes the
thread only; the row then reads the link-pending status (default `Link Pending`)
instead of `Done`, and the affiliate link is still owed. Nothing attaches it on
its own and no timer does it — the link goes out when the human says the post has
enough views, as a reply to the last post of the thread. That reply is its own
publish: one post, the affiliate URL, previewed and approved the same way.
`/affiliate-threads status` lists the threads waiting for their link.

**Approval must be explicit, in the current turn, for the product on screen.**
Silence is not approval. An earlier "approve" for a different product is not
approval. Your own judgement that the copy is good is not approval.

After a successful publish, save a content-memory note:
`{content_id: <ID>, angle_type, topic, hook_pattern, topic_tag}` — see
`references/content-rules.md` for the format. This is what makes the next
thread's novelty check possible.

---

## Pitfalls

| Symptom                                           | What is actually happening                                                                                                                                                                                                                            |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `threads_publish` returns `stage: "precondition"` | The Sheet row changed — probably held or cancelled after the preview. Report it; do not retry.                                                                                                                                                        |
| `stage: "guardrails"`                             | The copy breaks a hard rule. Fix the listed violations and show a new preview.                                                                                                                                                                        |
| `stage: "credentials"`                            | No `THREADS_ACCESS_TOKEN`. Setup problem, not a content problem.                                                                                                                                                                                      |
| `stage: "publish"` with a rate-limit code         | Threads allows 250 posts / 1000 replies per 24h. Wait; do not hammer it.                                                                                                                                                                              |
| `status: "published_sheet_write_failed"`          | **The thread is live.** Do not publish again. Re-call with the same `product_id` — it only repairs the Sheet.                                                                                                                                         |
| Shopee page fetch failed                          | Expected. Research from independent sources instead; do not retry with a bypass.                                                                                                                                                                      |
| `select_candidate.py` returns `candidate: null`   | Nothing is `Ready To Generate`. Say so and stop.                                                                                                                                                                                                      |
| Human replies with just "ok"                      | Ambiguous. Ask which of approve/hold/cancel they mean.                                                                                                                                                                                                |
| A link card shows on the post with the URL        | Threads builds it from the first URL in a text-only post, and no API removes it. An image post carries no card at all, and `publish_mode: two_stage` keeps the card off every value post — say that instead of promising a removal the API cannot do. |
| `hashtag_in_copy`                                 | A `#tag` is in the copy. Drop the trail: the topic is metadata (`topic_tag`), and only explicitly allowlisted tokens may stay in the text.                                                                                                            |
| `topic_tag_missing`                               | `require_topic_tag` is on (the default) and nothing was passed. Choose the topic a reader would search for — not the product name — show it on the preview, and pass it to `threads_publish`.                                                         |
| `topic_tag_invalid`                               | The tag breaks the platform's limits: 1-50 characters, no `.` or `&`, no leading `#`, one line.                                                                                                                                                       |
| `funnel_phrase` warning                           | Copy like "klik link di bawah" or "cek reply" points at the link instead of giving a reason to click it. Rewrite it as something the reader gets.                                                                                                     |
| `seller_viewpoint` warning                        | The copy repeats or attributes the seller's words ("klaim di deskripsi produknya…", "kualitas premium"). The `Description` orients the research; its claims are leads to verify with independent sources or to drop — rewrite from the writer's seat. |
| `amplifier_language`                              | Guarantee/absolute wording ("dijamin", "100% ampuh") is refused in **both** modes. A personal account is one experience, not a promise — hedge it or drop it.                                                                                         |
| `experience_detail_unsupported`                   | A number, duration or frequency sits in a first-hand sentence but not in the stored testimony. Drop it, or use the testimony's own wording.                                                                                                           |
| `experience_attribution_unsupported`              | A second-hand claim names a person ("anakku", "temenku") the testimony never mentions. Write the witness the testimony describes, or drop it.                                                                                                         |
| The row's `Used` is blank                         | Do not generate. Ask the Step 1.5 question and wait; a later scheduled run asking again is by design, not a bug.                                                                                                                                      |
| `stage: "input"` on a link reply                  | The link stage publishes one post. `posts` must hold exactly one item — the reply, with the URL.                                                                                                                                                      |
| A row is stuck on `Link Pending`                  | The thread is live and its link reply was never approved. Preview that reply and wait; do not republish the thread.                                                                                                                                   |

## Verification

Before you send the preview, confirm all of these are true:

- [ ] The candidate came from `select_candidate.py`, not from a hand-read Sheet
- [ ] Exactly one candidate was processed
- [ ] 5-8 angles were generated and scored before one was chosen
- [ ] The novelty check against recent content notes ran
- [ ] A one-line point of view existed before drafting, and it is not generic
- [ ] The narrative critic answered all twelve questions
- [ ] `antislop` and `antislop-copywriting` were loaded, or the preview says they were not
- [ ] The anti-slop audit ran as an audit of the draft, not only as writing advice
- [ ] The affiliate editorial review ran after it
- [ ] Every factual claim traces to a named evidence tier
- [ ] The thread's substance comes from independent evidence, not from the seller's description
- [ ] No claim, sentence, or voice from the seller's material appears in the copy
- [ ] The `Category` was mapped to a playbook family, and the copy speaks to that family's audience
- [ ] The register is friendly, casual, polite — no stiff brochure lines
- [ ] Every post opens from the thought the previous one left; nothing reads as an orphan
- [ ] The row's experience answer was resolved before research — asked for and
      stored when blank, never guessed
- [ ] In `none` mode: no first-hand claim anywhere in the copy
- [ ] In `firsthand` mode: every first-hand claim traces to the stored testimony —
      nothing amplified, numbers and named persons grounded in it
- [ ] No guarantee/absolute language in any mode (`amplifier_language`)
- [ ] The preview shows the `🧪 Experience:` line
- [ ] Exactly one topic tag is chosen, it names the conversation rather than the product, and the preview shows it
- [ ] The topic tag respects the platform's limits (1-50 characters, no `.` or `&`, no leading `#`)
- [ ] The `hook_pattern` is not a repeat of the last two threads
- [ ] A trade-off or limitation is present when the angle has room for one, and it is real
- [ ] The ending gives the reader something useful instead of summarizing
- [ ] `validate_thread.py` reports zero violations — run it with `--topic-tag` and the stage the draft is for
- [ ] In two-stage mode the preview says the link is deferred, and the thread body really has no URL in it
- [ ] The preview shows the Product ID explicitly
- [ ] You stopped and waited instead of publishing
