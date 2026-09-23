# Content rules

Everything in this file is enforced by judgement during writing, and partly by
`validate_thread.py` and `threads_publish` at publish time. Read it before Step 5.

## 1. Content philosophy

```
Audience → Problem/curiosity/observation → Interesting insight →
Specific evidence → Possible solution → Product → Contextual CTA + disclosure
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

## 3. Anti-slop

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

## 4. Personal experience — hard rule

The system has **no first-hand experience** with any product, and none is ever
supplied. Never write:

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

## 5. Trade-offs

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

## 6. CTA and disclosure

### CTA

Contextual link language, placed in the final post, earned by everything before it:

- "Saya taruh detail produknya di sini buat yang penasaran bentuk dan spesifikasinya."
- "Kalau mau cek spesifikasi lengkapnya, link-nya di bawah."
- "Untuk yang penasaran ukurannya, detailnya ada di sini."

Never:

- "BELI SEKARANG!!!"
- "Klik link di bio!"
- "Jangan sampai kehabisan!"
- Anything with a scarcity claim you cannot verify.

### Disclosure

The disclosure is mandatory, explicit, and short. The goal is to reduce the
hard-sell tone, not to conceal the commercial relationship.

- Keep it in the same post as the link.
- Keep it readable — not buried in a wall of hashtags.
- One line is enough:

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

The wording may vary as long as the commercial relationship is clear. Do not
expand it into a legal paragraph, do not repeat it across posts, and never drop it
because the ending reads better without it. `threads_publish` refuses to publish
without a disclosure marker, and the affiliate URL must appear in a post.

## 7. Post-by-post rules

- **3-6 posts.** Dynamic. A 3-post thread that lands is better than a padded 6.
- **Post length varies.** One sentence in one post is fine. Uniform construction
  is a warning sign, not a standard.
- **Post 1** earns the next post. No product mention.
- **The product enters when the reader already has a reason to care.** Post 3-4
  is the normal range, not a rule. Never post 1.
- **Every post creates a reason to continue.** If a post could be deleted without
  loss, delete it.
- **`affiliate_intensity` ≈ 2** — roughly 80% value, 20% product across the thread.
- **The ending gives the reader something useful** — a practical boundary, a
  buying consideration, one concrete observation — not a summary of what came
  before. The CTA and disclosure follow it; they do not replace it.
- **Max 500 characters per post** (emoji count as their UTF-8 byte length), and no
  more than 5 unique links in one post. `threads_publish` enforces both.

## 8. Content memory

There is no database. Hermes' own persistent memory is the novelty store.

### Before Step 3 — recall

Recall the last several notes and extract their `angle_type`, `topic` and
`hook_pattern`. Use them for the `novelty_vs_recent` score.

### After a successful publish — save

Save one short note:

```
affiliate-thread content note
content_id: 12
angle_type: trade_off
topic: power bank capacity vs weight
hook_pattern: "Semua orang beli yang paling gede, padahal..."
published: 2026-09-23
threads_url: https://www.threads.net/@.../post/...
```

Keep `hook_pattern` to the shape of the opening, not the whole line — that is what
you are checking against next time.

### What to do with a repeat

If the leading angle repeats a recent `angle_type`, penalise its
`novelty_vs_recent` score hard (0-2) and pick the next-best angle. If _every_
angle repeats, that is a signal the research step was too shallow — go back to
Step 2 and look wider before writing.
