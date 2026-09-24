# PROJECT SPECIFICATION v2 — Affiliate Threads AI Automation (Hermes Agent Edition)

## 1. Document Purpose

This document supersedes the original standalone-application specification.
It is the single source of truth for the concept, architecture, workflow,
content strategy, guardrails, data model, and MVP boundaries of an
AI-powered affiliate content automation system for Meta Threads — **built
to run on top of [Hermes Agent](https://hermes-agent.nousresearch.com)
(Nous Research) instead of as a standalone Python application.**

This specification is intended to be consumed by an AI coding agent or
development team as the primary implementation context, and pairs with
the accompanying Hermes plugin package (`affiliate-threads-generator/`).

The implementation should prioritize:

- reusing Hermes' own infrastructure (Telegram gateway, cron scheduler,
  memory, bundled skills/tools) instead of rebuilding it
- writing custom code ONLY where a side effect must never depend on the
  model getting it right — in this system, that is exactly one place:
  publishing to Meta Threads
- deterministic business rules for candidate selection and state
  transitions, enforced in code or by re-reading the Sheet, not trusted
  to model discretion alone
- structured, evidence-traceable AI outputs
- human approval before publishing, always
- natural, non-spammy Threads content that reads as worth reading even
  without the affiliate link
- Google Sheets as the business-data source of truth (also the de facto
  lock/state machine — no separate database)
- Telegram as the only user-facing control surface
- the official Meta Threads API for publishing
- no infrastructure beyond what Hermes already provides

---

## 2. Product Vision

Build an AI-assisted affiliate content engine that turns product
candidates in Google Sheets into research-backed, conversation-oriented
Threads content, running on Hermes Agent rather than as a bespoke
application.

The system should not behave like a generic "product description to
marketing caption" generator.

Its core idea is:

> Do not ask "how do we sell this product?"
> Ask "what conversation is worth reading, and can this product naturally
> become a relevant solution?"

The product should usually be a supporting element in the story rather
than the protagonist. If the affiliate link were removed, the Thread
should still provide enough insight, curiosity, or usefulness to be worth
reading.

---

## 3. Architectural Shift: Why Hermes Agent

The original design called for a custom modular monolith: its own
Telegram bot, its own scheduler, its own agent loop, its own Google
Sheets/Threads adapters, SQLite for execution history. Hermes Agent
already provides most of that as ready infrastructure:

| Need                               | Original plan                                       | This spec (Hermes-based)                                                  |
| ---------------------------------- | --------------------------------------------------- | ------------------------------------------------------------------------- |
| Telegram interface                 | `python-telegram-bot`/`aiogram`, built by hand      | Hermes' built-in Messaging Gateway                                        |
| Scheduler                          | APScheduler, built by hand                          | Hermes' built-in Cron Scheduler                                           |
| Agent loop / intent handling       | Custom `ai/agent.py`                                | Hermes' agent loop + this system's own Skill                              |
| Google Sheets access               | Custom adapter                                      | Hermes' bundled `google-workspace` skill                                  |
| Web/product research               | `httpx` + BeautifulSoup + Playwright, built by hand | Hermes' bundled web/browser tools                                         |
| Image generation                   | Custom provider integration                         | Hermes' built-in image-generation tool (FAL.ai), optional                 |
| Execution history / content memory | SQLite                                              | Hermes' own persistent memory (no separate DB)                            |
| Threads publishing                 | Custom adapter                                      | **Custom Hermes plugin Tool — the one piece that must stay hand-written** |

The guiding principle carried over unchanged from the original design:

> AI creates and reasons. Code controls and validates. Human approves.
> Threads publishes. Google Sheets records the business state.

The only thing that changes is _where_ the "code controls and validates"
part lives: instead of an entire Python application, it lives in one
narrow, auditable Hermes plugin Tool (`threads_publish`) plus a set of
explicit instructions (a Skill) that tell the agent how to use Hermes'
existing capabilities correctly. Everything else is reused, not rebuilt.

---

## 4. Skill vs. Tool: The Core Design Decision

Hermes itself draws this distinction, and it is the organizing principle
of this whole redesign:

- **Skill** — instructions + shell/CLI + tools that already exist. No
  custom integration code. Used for: orchestration logic, writing style,
  research procedure, candidate-selection instructions, interpreting
  natural-language approve/hold/cancel/regenerate.
- **Tool** — requires end-to-end credential/auth handling and precise
  logic that must execute identically every time, regardless of what the
  model believes happened. Used for exactly one thing here: publishing to
  Meta Threads.

Every non-negotiable rule from the original spec that concerns a
side-effect (Section 12) is enforced at the Tool layer, in code — never
left as a Skill instruction alone, because a Skill instruction is
followed by the model, not guaranteed by it.

### Packaging: one bundle, one install

The Skill and the Tool ship inside the _same_ Hermes plugin, installed
with a single `hermes plugins install`. Hermes lets a plugin register a
skill of its own (`ctx.register_skill`), so the Skill is read straight
from the plugin directory, namespaced as
`affiliate-threads-generator:affiliate-threads-generator`, and versioned
with the code it belongs to.

Nothing is published to the skills hub and nothing is copied into
`~/.hermes/skills/`. There is therefore one artifact to install, one to
update, and no second copy of the pipeline that can drift away from the
guardrails the Tool enforces.

Two consequences belong to the plugin rather than to the operator:

- A plugin skill is kept out of the system prompt's skill index, so the
  plugin's `pre_llm_call` hook injects one line naming it whenever a turn
  looks like Affiliate Threads work. Without that, the Skill would ship
  and never be loaded.
- The name is namespaced, so a cron job names the Skill in its prompt
  rather than attaching it with `--skill`.

The bundle also carries the human-facing surface: the
`/affiliate-threads status` slash command runs the same read-only
preflight as `threads_check`, without spending a model turn.

---

## 5. Core Business Flow

```text
                         GENERATE CONTENT
                                │
                 ┌──────────────┴──────────────┐
                 │                             │
              SCHEDULED                       MANUAL
                 │                             │
      Hermes Cron: Mon/Wed/Fri/Sun 08:00   Telegram natural-language
      Asia/Jakarta                         request ("generate lagi")
                 │                             │
                 └──────────────┬──────────────┘
                                ↓
              Skill: affiliate-threads-generator (same for both triggers)
                                ↓
        STEP 1 — CANDIDATE SELECTION (deterministic)
        Read Sheet → filter Status == "Ready To Generate" →
        take exactly one (stable order by ID) → if none, notify & STOP
                                ↓
        STEP 2 — RESEARCH
        Description column = seller-side background (Shopee links block
        scraping — this is expected, not a failure) → best-effort page
        fetch → external web/review research → visual profile
                                ↓
        STEP 3 — ANGLE DISCOVERY & SELECTION
        5-8 candidates, scored, checked against recent-content memory
        for novelty
                                ↓
        STEP 4 — POINT OF VIEW → NARRATIVE PLANNER → NARRATIVE CRITIC
        One-line point of view first; objective-based plan; bounded revise
        loop (max 2-3 rounds) against 9 quality questions
                                ↓
        STEP 5 — THREAD GENERATOR
        Editorial rules, structural variation, personal-experience
        guardrail, contextual CTA, affiliate_intensity ≈ 2
                                ↓
        STEP 6 — ANTISLOP AUDIT → AFFILIATE EDITORIAL REVIEW → EVIDENCE
        Bounded revise loop (max 2 rounds), then the deterministic lint
                                ↓
        STEP 7 — IMAGE (OPTIONAL)
        Only if FAL_KEY is configured; otherwise skip to text-only thread
                                ↓
        STEP 8 — TELEGRAM PREVIEW
        Product ID always shown explicitly (this doubles as the review
        context — no separate database)
                                ↓
                    HUMAN REVIEW / DECISION
                                │
          ┌────────────────────┼─────────────────────┬──────────────┐
          │                    │                     │              │
       APPROVE                HOLD                 CANCEL      REGENERATE
          │                    │                     │              │
          ↓                    ↓                     ↓              ↓
   Tool: threads_publish   Sheet Status=Hold    Sheet Status=Cancel  Back to
   (re-validates Sheet          │                     │           Step 3 with
    Status before doing         ↓                     ↓          new constraint,
    anything)                 STOP                  STOP          same Product ID
          │
          ↓
   Threads Graph API: create container(s) → publish
          │
          ↓
   ONLY on confirmed success:
   Sheet Status=Done, Threads URL saved
```

Important — unchanged from the original spec:

- The scheduler is only a trigger; it never publishes automatically.
- Manual and scheduled generation use the exact same pipeline.
- Every generation request re-reads the Sheet before selecting a
  candidate.
- Each generation request processes exactly one candidate.
- No automatic publishing is allowed under any circumstance.
- Human approval is mandatory.

### 5.1 Optional: the deferred affiliate link

The default is one publish per thread, link included. The `publish_mode:
two_stage` setting splits that in two, which is what makes "let the post collect
views first, then attach the link" possible:

```text
stage 1  threads_publish stage="thread"   the thread, without the link
         Sheet: Threads URL = permalink, Status = <link_pending_status>
         (the link and the disclosure are both deferred to stage 2)
                        ↓
         the human watches the post; nothing is on a timer
                        ↓
stage 2  threads_publish stage="link"     one reply: affiliate URL + disclosure
         Sheet: Status = Done
```

Both halves are separate publishes: each is previewed, each needs its own
explicit human approval and its own pass through the approval gate, and each
re-validates the Sheet's own state before doing anything. Nothing about this
mode relaxes Section 14.

---

## 6. User Interaction Model

Telegram (via Hermes' Messaging Gateway) is the only user-facing control
surface. The user communicates in natural language, e.g.:

```text
Buatkan content berikutnya.
Generate lagi.
Hold dulu yang ini.
Saya approve.
Yang ini jangan dipublish.
Regenerate tapi angle-nya lebih ke orang yang sering travelling.
```

Natural-language UI does NOT mean uncontrolled autonomous execution.
Conceptually:

```text
User → Telegram (Hermes Gateway) → Skill (interpretation + orchestration)
     → Hermes bundled tools (Sheets/web/image) + Tool: threads_publish
     → Telegram response
```

For approve/hold/cancel, the "review context" is always **the Product ID
most recently shown in this conversation** — never inferred from free
text, and never a separate database. See
`references/telegram-actions.md` in the plugin package.

---

## 7. Google Sheets Data Model

Unchanged from the original spec — Google Sheets remains the business-data
source of truth, and also doubles as the state lock (no SQLite):

| Column          | Description                                                                                                     |
| --------------- | --------------------------------------------------------------------------------------------------------------- |
| `ID`            | Unique product/content identifier                                                                               |
| `Product`       | Product name                                                                                                    |
| `Description`   | Seller-side product description/context — **background material for the writer, never evidence, see Section 9** |
| `Affiliate URL` | Affiliate URL (Shopee) supplied by the user                                                                     |
| `Category`      | Product category                                                                                                |
| `Threads URL`   | Published Threads URL; blank before publication                                                                 |
| `Status`        | Current workflow state                                                                                          |

Allowed statuses: `In Progress`, `Ready To Generate`, `Hold`, `Cancel`,
`Done` — semantics unchanged from the original spec. The optional two-stage
publish mode (Section 5.1) adds one more, written by the tool: the configured
link-pending status (default `Link Pending`) marks a thread that is live but
still owes its affiliate-link reply. It is deliberately neither eligible nor
`Done`, so the row cannot be published twice while it waits.

Access is via Hermes' bundled `google-workspace` skill (`google_api.py
sheets get/update/append`), not a custom adapter.

---

## 8. Candidate Selection Rules

Unchanged in substance, re-homed to run inside the Skill's instructions
(Step 1), with an optional deterministic script
(`scripts/select_candidate.py`) available if you want this step
hard-guaranteed instead of model-followed:

1. Re-read the Sheet on every request.
2. Filter to rows where `Status == "Ready To Generate"` exactly.
3. Select exactly one — smallest/oldest ID, stable ordering.
4. If none eligible: notify via Telegram and stop. Never fall back to a
   different status.
5. Never process more than one row per request, scheduled or manual.
6. Multiple manual requests may happen in a day; each still processes
   only one candidate.

---

## 9. Research Strategy: Review-First, Shopee-Aware

This is a deliberate deviation from the original spec's assumption that
the product page can always be scraped.

**Reality:** the `Affiliate URL` points to Shopee, which actively blocks
automated access. Direct scraping will fail often. This is expected, not
a pipeline failure, and the system must never attempt to bypass
CAPTCHA/anti-bot/auth walls to work around it.

**Confidence tiers, highest to lowest:**

1. **External web/review research** (general search — NOT scraping
   Shopee, so not blocked by its anti-bot measures) — "review-derived
   observation" tier. Nothing in it is written by someone selling the
   product, which is why the thread's substance is built here.
2. **Seller material** — the `Description` column and the fetched
   product page (best-effort, only if it actually succeeds). This is the
   seller's own framing of their product, so it is **background and
   orientation, not evidence**: what the product is, who it is for, the
   physical details, and claims worth checking elsewhere. Anything taken
   from it is attributed back to the seller (_"Klaim di deskripsi
   produknya..."_), and it may never become the thread's main material —
   a thread that paraphrases the seller's copy is an advertisement with a
   hook.
3. **Inference** — reasonable deduction from tiers 1-2, always hedged.
4. **Unsupported** — never used as a factual claim; removed or rewritten.

If tiers 1 and 2 both come back thin, the system shifts toward a more
category-level observation/problem framing rather than making the
thread out of the seller's description. Full procedure lives in
`references/evidence-sourcing.md`.

---

## 10. Content Strategy (carried over in full, now enforced as explicit Skill instructions)

### 10.1 Content philosophy

```text
Audience → Problem/curiosity/observation → Interesting insight →
Specific evidence → Possible solution → Product → Contextual CTA + disclosure
```

Avoid: `Product → "great product" → Features → Benefits → Affiliate link`.

Three conceptual layers every Thread should move through: **Conversation**
(worth discussing?) → **Discovery** (insight that keeps reading?) →
**Solution** (can the product naturally address it?). Reject an angle
where the product feels artificially inserted.

### 10.2 Angle Discovery & Angle Library

Generate 5-8 distinct angle candidates before selecting — never jump to
"one best angle". Each candidate: `{angle_type, core_idea, tension}`.

Angle types: `problem`, `observation`, `unexpected_benefit`,
`unexpected_drawback`, `comparison`, `myth`, `trade_off`, `use_case`,
`who_is_this_for`, `who_should_skip`, `before_after`, `decision_guide`,
`checklist`, `mistake`, `hidden_feature`, `contrarian`,
`small_problem_simple_solution`.

### 10.3 Angle Scoring (0-10 each)

`relevance`, `curiosity`, `specificity`, `evidence_strength`,
`conversation_potential`, `product_fit`, `salesiness_penalty`,
`novelty_vs_recent`. High `product_fit` alone must never dominate
selection. Not a virality forecast.

### 10.4 Content memory (novelty check without a database)

The original spec proposed SQLite for tracking recent angle_type/topic/
hook_pattern to avoid repetition. This spec instead uses **Hermes' own
persistent memory**: after every successful publish, the Skill saves a
short memory note (`content_id, angle_type, topic, hook_pattern`), and
recalls recent notes during Angle Discovery to penalize repeats. No
separate infrastructure required.

### 10.5 Narrative Planner & Critic

Planner determines topic, audience, a required one-line **point of view**,
the tension, hook strategy, per-post **objectives** (not fixed roles), the
product entry point _together with why the narrative is ready for it
there_, CTA post, `affiliate_intensity` (default `2`, ~80% value / 20%
product), `must_include`/`must_not_claim`, and the evidence ledger.

Objectives, not roles: two objectives may collapse into one post, one may
take two posts. The product enters when the reader already has a reason to
care — post 3-4 is the normal range, not a rule.

Critic gates on the point of view first (a generic one fails immediately),
then answers 9 questions before Thread Generation proceeds (see Section 12
for the full checklist). Bounded to 2-3 revision rounds — never an
unbounded loop.

### 10.6 Thread Generator

3-10 posts, dynamic length. One narrative structure per Thread, rotated
across runs (observation→story→product, question→comparison→product,
problem→evidence→trade-off→product, hot take→explanation→product,
mistake→lesson→recommendation, checklist→example→product) — never
default to `Hook → 3 benefits → CTA` every time.

Include genuine, evidence-backed trade-offs/limitations. Never fabricate
a weakness.

### 10.7 Anti-Slop Strategy

Two layers, deliberately separate:

1. **Generic prose** — the external `antislop` and `antislop-copywriting`
   skills, loaded through Hermes. They own AI vocabulary, signposting,
   fake-candid framing, forced parallelism, rule-of-three, staccato drama,
   filler, rhythm and promotional tone. The plugin does not vendor them;
   if either cannot be loaded, the preview says so instead of implying an
   audit that did not happen.
2. **Affiliate editorial** — this plugin's own rules
   (`references/editorial-rules.md`): point of view, detail selection,
   product entry, ending, disclosure.

Human-like writing comes from genuine specifics, not imperfection
theater — never intentionally inject bad grammar or random mistakes.

`guardrails.py` keeps only what is specific to affiliate copy: a short
cliché list (_"praktis dan nyaman digunakan", "cocok untuk berbagai
kebutuhan", "wajib banget punya", "solusi yang tepat untuk kamu",
"kualitas terjamin", "worth it banget", "game changer", "must have"_) and
four structural counters — `excessive_signposting`,
`repeated_transition_density`, `excessive_enumeration`,
`product_detail_density`. All are warnings, never blocks, and none is
proof that a text is AI-written. Thresholds are configurable; `0`
disables a signal.

Bounded to 2 revision rounds. If the thread still reads as templated after
two, the angle is the problem: return to Angle Discovery.

### 10.8 Personal Experience Guardrail (hard rule)

Never write _"Aku sudah coba...", "Saya pakai ini setiap hari...",
"Menurut pengalaman saya..."_ — the system has no personal experience
with the product and none is supplied. Use _"Dari spesifikasi
produk...", "Berdasarkan review yang tersedia...", "Untuk skenario
seperti ini..."_ instead.

### 10.9 Evidence Checker

Every factual claim must trace to one of the four tiers in Section 9.
Anything that doesn't is removed or rewritten as an explicit hedge before
the draft reaches Telegram.

### 10.10 CTA & Disclosure

Contextual link language, e.g. _"Saya taruh detail produknya di sini
buat yang penasaran bentuk dan spesifikasinya."_ — never _"BELI
SEKARANG"_. Disclosure must remain explicit but lightweight, and the
operator picks the style:

- `disclosure_style: marker` (default) — any configured marker, in any
  post. "Link afiliasi." on the same post as the URL is the usual form.
- `disclosure_style: tag` — a hashtag marker (`#ad`) on the final post,
  which is the post carrying the link in single mode and the link reply
  itself in two-stage mode. That tag alone is the disclosure; no sentence
  mentioning commission is needed, which is the form to prefer when a
  sentence reads as hard-sell.

`threads_publish` refuses to publish either way when the configured shape
is missing. The goal is reducing hard-sell tone, not concealing the
commercial relationship.

### 10.11 Deferred Link Publishing (optional)

Under `publish_mode: two_stage` the affiliate link is deliberately not in
the thread. The thread body carries no URL and no disclosure; the row is
parked in the link-pending status; and the link goes out later, as a reply
to the last post, once a human decides the thread has been seen. Both
halves are separate publishes with separate approvals, and both are
enforced in code — the reply must carry the row's `Affiliate URL` and
satisfy the disclosure rule, exactly as the single-call mode requires of
the thread.

This is a delivery mode, not a relaxation: nothing here permits a thread
to go out with a link that was never disclosed, and nothing attaches the
link automatically.

### 10.12 Image Strategy (optional)

Only if Hermes' image-generation tool is available (`FAL_KEY` set).
Derive image briefs from the visual profile (Section 9) and narrative
intent; not every post needs an image. Preserve recognizable physical
characteristics (shape/color/material/distinctive features); never
invent unverified controls/features. If unavailable, publish text-only —
a normal path, not a degraded fallback.

---

## 11. Human Approval Gate

Unchanged principle, re-homed to the Tool layer:

```text
AI generates candidate
        ↓
Telegram presents candidate (Product ID always shown explicitly)
        ↓
Human selects Approve (explicit, in the current turn)
        ↓
Tool `threads_publish` independently re-verifies Sheet Status
        ↓
Tool publishes via official Threads Graph API
        ↓
Only on confirmed success: Sheet Status=Done, Threads URL saved
```

Never implement `AI → publish directly`. The only path to Meta Threads is
the `threads_publish` tool call.

Under the optional two-stage mode (Section 5.1) that gate runs twice: once
for the thread and once for the deferred link reply. Approving the thread
never carries over to the link.

### 11.1 Review context without a database

No SQLite. The "review context" is the Product ID most recently shown in
the current Telegram conversation — the Skill always displays it
explicitly, and every approve/hold/cancel/regenerate refers back to it.
If a session resets before approval, the Sheet row is still
`Ready To Generate`, so nothing is lost — the user simply triggers
generation again.

### 11.2 Human actions

| Action     | Trigger example                                                    | Result                                                                                                  |
| ---------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| Approve    | "Saya approve."                                                    | Call `threads_publish`; on success, Status=Done + Threads URL saved; on failure, Status untouched       |
| Hold       | "Hold dulu yang ini."                                              | Sheet Status=Hold; no publish                                                                           |
| Cancel     | "Yang ini jangan dipublish."                                       | Sheet Status=Cancel; no publish                                                                         |
| Regenerate | "Regenerate tapi angle-nya lebih ke orang yang sering travelling." | Back to Angle Discovery with new constraint, same Product ID, same research unless new info is required |

---

## 12. Narrative Critic Checklist (used every generation)

Gate — the point of view. A generic `point_of_view` fails the plan immediately,
before the questions below are answered.

1. Is the topic interesting without the product?
2. Does the hook create real curiosity?
3. Is there progression between posts?
4. Is the product introduced when the reader already has a reason to care?
5. Is the Thread only a feature list?
6. Does each post create a reason to continue?
7. Does the ending feel like an advertisement — and does it give the reader
   something useful rather than summarizing?
8. Are claims supported (traceable to Section 9's tiers)?
9. Is the angle too similar to recent content (Section 10.4)?

---

## 13. Component & Responsibility Map

```text
Hermes Agent (LLM + agent loop)
= intelligence, intent interpretation, research synthesis,
  angle/narrative reasoning, writing

Skill: affiliate-threads-generator
= orchestration instructions, affiliate editorial rules, the audit order,
  how to interpret natural-language decisions
  (NOT the final authority for side effects)

External antislop skills (antislop, antislop-copywriting)
= the generic AI-prose filter, loaded through Hermes, applied as an audit
  of the draft — referenced by name, never vendored

Tool: threads_publish (this system's one custom code artifact)
= control, precondition validation, publish authority, Sheet state
  update — the final authority for the one irreversible side effect

Hermes bundled google-workspace skill
= Google Sheets read/write (business data source of truth)

Hermes bundled web/browser tools
= product & review research

Hermes built-in image-generation tool (optional)
= visual asset creation

Telegram (via Hermes Messaging Gateway)
= user interface, human review/approval

Hermes Cron Scheduler
= trigger only, never publishes

Meta Threads (official Graph API)
= final publishing destination
```

---

## 14. Final Non-Negotiable Rules

1. Human approval is mandatory before every publish action.
2. Only `Ready To Generate` candidates are eligible for generation.
3. Every generation request re-checks Google Sheets.
4. Every generation request processes exactly one candidate.
5. Scheduled and manual generation use the same pipeline (same Skill).
6. Scheduled generation occurs only Monday, Wednesday, Friday, and Sunday
   at 08:00 Asia/Jakarta.
7. The scheduler never publishes automatically.
8. Product research must happen before content generation, and must never
   attempt to bypass anti-bot/CAPTCHA/auth protections on Shopee.
9. `Description` is seller-side background material, not evidence: the
   thread's substance comes from independent research, anything taken
   from the seller's copy is attributed, and scraped/external data is
   never treated as automatically true.
10. Generated images (if used) must preserve recognizable product
    characteristics and never invent unverified features.
11. Do not fabricate personal experience.
12. Do not fabricate product facts, criticism, or unsupported claims.
13. Affiliate disclosure must remain clear — either a configured marker
    anywhere in the thread, or, under `disclosure_style: tag`, a hashtag
    on the post that carries the link.
14. The product should naturally support the story, never be forced into
    it.
15. Final content should be worth reading even without the affiliate
    link.
16. Angle and narrative structure should vary over time (checked via
    Hermes memory, not a database).
17. No SQLite or other separate database is used — the Sheet itself is
    the state lock, and Hermes' own memory covers content-repetition
    checks.
18. No uncontrolled autonomous publishing by the AI — `threads_publish`
    is the only path to Threads, and it re-validates state itself. The
    optional deferred link reply (Section 5.1) is one more publish, not
    an exception: it needs its own approval and its own re-validation.
19. Application code (the Tool), not prompts, is the final authority for
    the publish side effect.
20. Keep the plugin minimal: reuse Hermes' bundled capabilities wherever
    possible; write custom code only where a side effect must not depend
    on model behavior.

---

## 15. Definition of Done for MVP

```text
[ ] Sheet candidates can be read via the bundled google-workspace skill
[ ] Ready To Generate selection is deterministic (instruction-driven or
    via select_candidate.py)
[ ] One candidate is processed per request
[ ] Manual generation works from Telegram natural language
[ ] Scheduled generation works Mon/Wed/Fri/Sun 08:00 Asia/Jakarta via
    Hermes Cron
[ ] Affiliate redirect resolution attempted; Shopee anti-bot failure is
    handled gracefully, never bypassed
[ ] Description treated as seller background; the thread's substance
    comes from independent research and attributed claims
[ ] External (non-Shopee) research supplements when the page is
    unavailable
[ ] 5-8 angles generated and scored before selection
[ ] Angle/structure novelty checked via Hermes memory
[ ] A one-line point of view is required before drafting
[ ] Narrative Critic can reject weak plans (bounded retries)
[ ] Thread copy follows content-philosophy + the affiliate editorial rules
[ ] Evidence Checker removes/softens untraceable claims
[ ] antislop + antislop-copywriting audit runs before the affiliate
    editorial and evidence reviews (bounded to 2 revision rounds)
[ ] Affiliate disclosure present, short, and in the shape the configured
    disclosure style requires (a marker anywhere, or a hashtag on the
    post carrying the link)
[ ] Optional two-stage mode: the thread publishes first, the affiliate
    link follows as a reply, and each half is separately approved
[ ] Link preview cards documented as unremovable through the API
[ ] Images generated only when FAL_KEY is configured; text-only
    otherwise
[ ] Telegram preview always shows the Product ID explicitly
[ ] Approve requires explicit human action in the same turn
[ ] Hold/Cancel update the Sheet correctly, no publish
[ ] Approve publishes only through threads_publish (official Threads
    Graph API)
[ ] threads_publish re-validates Sheet Status before publishing
[ ] Successful publish saves Threads URL and sets Status=Done
[ ] Failed publish never changes Status
[ ] The AI cannot reach Threads through any path other than
    threads_publish
```

---

## 16. Final Architectural Principle

```text
                    INTELLIGENCE
                  Hermes Agent (LLM)
                         │
                         ▼
                 Research + Reasoning
           (Review-first, Shopee-aware)
                         │
             ┌───────────┴───────────┐
             │                       │
       Angle Discovery       Narrative Planning
             │                       │
             └───────────┬───────────┘
                         ▼
                  Content Generation
                         │
          Antislop + Editorial + Evidence
                         │
              Image Creation (optional)
                         │
                         ▼
                 HUMAN DECISION
                Telegram (Hermes Gateway)
                         │
                         ▼
               APPLICATION AUTHORITY
             Tool: threads_publish (plugin)
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
        Google Sheets             Threads
        source of truth +         official
        state lock                Graph API
```

The central rule, unchanged from the original spec:

> AI creates and reasons. Code controls and validates. Human approves.
> Threads publishes. Google Sheets records the business state.

The only thing this version of the spec changes is _how much of that
code_ needs to be written by hand — reduced from a full modular monolith
to one plugin, one Skill, and one Tool.
