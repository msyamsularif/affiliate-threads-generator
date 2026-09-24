# Content rules

Everything in this file is enforced by judgement during writing, and partly by
`validate_thread.py` and `threads_publish` at publish time. Read it before Step 5.

## 1. Content philosophy

```
Audience → Problem/curiosity/observation → Interesting insight →
Specific evidence → Possible solution → Product → Contextual CTA
```

Not this:

```
Product → "great product" → Features → Benefits → Affiliate link
```

Every thread moves through three conceptual layers:

1. **Conversation** — is this worth discussing at all?
2. **Discovery** — is there an insight that keeps someone reading?
3. **Solution** — can the product naturally address what was raised?

If the product feels inserted rather than arrived at, reject the angle.

**The test:** delete the affiliate link. Is the thread still worth reading? If no,
start over.

## 2. Narrative structure rotation

One structure per thread, rotated across runs. Never default to
`Hook → 3 benefits → CTA`.

| Structure                                | Shape                                                                          |
| ---------------------------------------- | ------------------------------------------------------------------------------ |
| observation → story → product            | Notice something, tell it as a scene, land on the product                      |
| question → comparison → product          | Ask, weigh two options, pick with reasons                                      |
| problem → evidence → trade-off → product | State the friction, show what the data says, admit the cost, offer the product |
| hot take → explanation → product         | Say the uncomfortable thing, defend it, offer the product                      |
| mistake → lesson → recommendation        | Name the common error, extract the lesson, recommend                           |
| checklist → example → product            | List what matters, walk one example, show the product                          |

Before writing, check recent content notes in Hermes memory. If the last two
threads used the same structure, use a different one even if it fits slightly
less well.

A structure is a starting shape, not a template. The objective-based plan in
`references/narrative-planner-critic.md` wins when the two disagree — if the
angle needs a different shape, use it and say which structure you actually used
in the preview.

Post 1 rotates on the same principle, with its own vocabulary of opening shapes:
`references/hook-patterns.md`. If the last two threads opened the same way, take
a different pattern — a repeated hook is the fastest way for a profile to start
reading as a content farm.

## 3. Hashtags, topic tags, and reach

Threads is not Instagram. Exactly **one** tag per post becomes clickable, it is
called a _topic tag_, and it is set through `threads_publish`'s `topic_tag`
argument — not typed into the copy. When that topic has a Threads community, the
post is also surfaced inside the community. That is the reach this mechanism
buys, and it is the whole mechanism.

- **No hashtags in the copy.** `threads_publish` refuses them
  (`hashtag_in_copy`). The only hashtags that may stay are ones the operator
  explicitly allowlists (`allowed_hashtags`), and there are none by default. A
  trail at the end of a reply changes nothing about how the post is distributed,
  and it is the single clearest tell that a thread is an ad.
- **Exactly one topic tag per thread**, chosen in the planner and passed as
  `topic_tag`. It belongs to the root post; the replies carry none.
- **The tag is the conversation, not the product** — `sensory play`,
  `power bank`, `perawatan kulit` — not the product name, not a brand, not a
  model number. A tag that only makes sense because something is for sale is a
  listing label, and nobody follows it.
- **The platform's limits are hard**: 1-50 characters, no `.`, no `&`, no
  leading `#`, one line. Anything else is refused before the API sees it
  (`topic_tag_missing`, `topic_tag_invalid`).
- **You cannot verify a community from the API.** If the operator has named the
  communities that exist in their market (the topics showing a three-dot icon on
  the tag in the app), prefer one of those; otherwise choose the most-followed
  topic that is still honest about the thread.

Reach comes from a relevant tag plus copy worth reading. It never comes from
stuffing tags into the text.

## 4. Anti-slop

Human-sounding writing comes from **genuine specifics**, not from imperfection
theatre. Never inject typos, slang, or grammatical errors to seem casual. The
specificity is the whole trick.

The generic AI-writing filter is not in this file. Load `antislop` and
`antislop-copywriting` and apply them as an audit — structure, rhythm,
signposting, forced parallelism, filler, promotional tone. This file keeps only
what is specific to affiliate copy.

### The replacement technique

Every generic sentence is a specific sentence you have not looked up yet.

| Generic                 | Specific                                                        |
| ----------------------- | --------------------------------------------------------------- |
| "Bahannya berkualitas." | "Bahannya [material], dan itu kelihatan dari [visible detail]." |
| "Banyak yang suka."     | "Yang paling sering disebut di review: [thing]."                |
| "Ukurannya pas."        | "[X] cm — masuk saku jaket, nggak masuk saku celana."           |
| "Hemat tempat."         | "Kalau dilipat jadi [size] — sekitar [comparison object]."      |

### What `validate_thread.py` still flags

A short list of affiliate clichés comes back as warnings — "praktis dan nyaman
digunakan", "cocok untuk berbagai kebutuhan", "wajib banget punya", "solusi
yang tepat untuk kamu", "kualitas terjamin", "worth it banget", "game changer",
"must have". Read them; do not ignore them. They never block publishing, and the
wider prose catalogue belongs to the external antislop skills, not to this list.

## 5. Personal experience — provenance, in two modes

The system itself has **no first-hand experience** with any product. What it can
have is the human's: a testimony stored in the row (Step 1.5). The row's answer
picks the mode, and you never pick it.

**`none` mode** (no testimony): never write

- "Aku sudah coba..."
- "Saya pakai ini setiap hari..."
- "Menurut pengalaman saya..."
- "Waktu saya coba..."
- "I've been using this for..."

`threads_publish` blocks these patterns and will refuse to publish. Use instead:

- "Dari spesifikasi produk..."
- "Berdasarkan review yang tersedia..."
- "Untuk skenario seperti ini..."
- "Yang sering disebut di review..."

This applies to implications too. "Baterainya masih 40% setelah sehari" is a
first-hand claim even without the word "saya".

**`firsthand` mode** (a testimony is stored): first-hand claims are allowed, but
only inside what it says. Nothing is added to it — no duration, outcome,
comparison, or number it does not contain — and the voice follows the witness:
if the testimony says the child used it, the copy says so, never "saya pakai".
Guarantee language is the one thing that stays banned either way: "dijamin",
"100% ampuh", "pasti sembuh" are refused by `amplifier_language` whatever the
row says.

## 6. Trade-offs

A genuine, evidence-backed limitation is what separates a recommendation from an
advertisement. Include one when the angle has room for it.

**Never fabricate a weakness.** A made-up drawback is exactly as dishonest as a
made-up benefit, and it is worse because it reads as credible. If the research did
not surface a real limitation, the honest move is a trade-off inherent to the
category ("kapasitas besar selalu berarti berat") — which is true and specific.

Do not add a second drawback just because the thread already has one, and do not
add a specification just because it is available. Balance is not the goal;
honesty is.

Good: _"380g itu berat buat di saku. Kalau prioritasmu ringan, ini bukan yang
kamu cari."_
Bad: _"Sayangnya warnanya cuma hitam."_ (invented, trivial, and reads as fake)

## 7. CTA

### CTA

Contextual link language, placed in the final post, earned by everything before it.
The CTA says **what the reader gets** — the reader is already on the post that
carries the link, so there is nothing to point at:

- "Saya taruh detail produknya di sini buat yang penasaran bentuk dan spesifikasinya."
- "Untuk yang penasaran ukurannya, ini detailnya: <link>"
- "Spesifikasi lengkap dan variannya ada di sini: <link>"

Never:

- "BELI SEKARANG!!!"
- "Klik link di bio!" or any funnel line whose only job is to move the reader
  toward the link: "cek link di bawah", "link-nya di reply", "cek reply",
  "DM aku", "buruan". `validate_thread.py` reports these as `funnel_phrase`.
- "Jangan sampai kehabisan!"
- Anything with a scarcity claim you cannot verify.

### When the link is deferred (`publish_mode: two_stage`)

Under two-stage publishing the thread body carries no URL at all — it belongs to
the link reply that goes out later. So:

- Do not write "link afiliasi di reply berikutnya" teasers or "cek reply"
  prompts. The thread has to stand on its own without promising a link.
- The reply is its own piece of copy: one post and the affiliate URL.

## 8. Post-by-post rules

- **3-10 posts.** Dynamic. A 3-post thread that lands is better than a padded 10.
- **Post length varies.** One sentence in one post is fine. Uniform construction
  is a warning sign, not a standard.
- **No post carries a hashtag.** None at all. The topic tag is metadata
  (`topic_tag`), not text; only tokens the operator explicitly allowlists may
  stay.
- **Post 1** earns the next post. No product mention.
- **The product enters when the reader already has a reason to care.** Post 3-4
  is the normal range, not a rule. Never post 1.
- **Every post creates a reason to continue**, and opens from the thought the
  previous post left behind — a reader who lands mid-thread can tell what
  conversation they joined (`references/category-playbook.md` §3). If a post
  could be deleted without loss, delete it.
- **`affiliate_intensity` ≈ 2** — roughly 80% value, 20% product across the thread.
- **The ending gives the reader something useful** — a practical boundary, a
  buying consideration, one concrete observation — not a summary of what came
  before. The CTA follows it; it does not replace it.
- **The seller's description never reaches the copy.** It orients the research —
  what the product is, what to look for — and its claims are leads to verify.
  No quote, no paraphrase, no attribution: a claim only ships when independent
  evidence carries it, and bare identifiers (shade, size, contents) carry no
  promise.
- **Max 500 characters per post** (emoji count as their UTF-8 byte length), and no
  more than 5 unique links in one post. `threads_publish` enforces both.

## 9. Content memory

There is no database. Hermes' own persistent memory is the novelty store.

### Before Step 3 — recall

Recall the last several notes and extract their `angle_type`, `topic`,
`hook_pattern` and `topic_tag`. Use the first three for the `novelty_vs_recent`
score, and the tags to keep a category from publishing under the same topic every
single time.

### After a successful publish — save

Save one short note:

```
affiliate-thread content note
content_id: 12
angle_type: trade_off
topic: power bank capacity vs weight
hook_pattern: cost_statement — "Kamu dapat kapasitas, kamu bayar pakai berat."
topic_tag: power bank
published: 2026-09-23
threads_url: https://www.threads.net/@.../post/...
```

`hook_pattern` is the pattern's name from `references/hook-patterns.md`, with the
opening quoted after it — the name is what you check against next time, so keep
the vocabulary stable. `topic_tag` records the topic the post went out under,
which is how you notice a whole category drifting onto one tag.

### What to do with a repeat

If the leading angle repeats a recent `angle_type`, penalise its
`novelty_vs_recent` score hard (0-2) and pick the next-best angle. If _every_
angle repeats, that is a signal the research step was too shallow — go back to
Step 2 and look wider before writing.
