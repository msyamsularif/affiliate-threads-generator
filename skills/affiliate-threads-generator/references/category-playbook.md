# Category playbook

Step 3 and Step 5 read this file. It turns the row's `Category` and `Description`
into the **sentence patterns** a thread uses: which audience it speaks to, which
angles and hooks fit, how the sentences are shaped, and which register they
carry. `Category` decides the pattern; `Description` only orients the research —
it never supplies copy.

This file settles the _shape_ of the writing. It does not touch the evidence
rules (`references/evidence-sourcing.md`), the hook vocabulary
(`references/hook-patterns.md`), the angle vocabulary
(`references/angle-library.md`), or the experience modes. Those apply on top of
whatever family a thread lands in.

---

## 1. Reading the two inputs

### `Category` → family

The Sheet's `Category` is operator free text, so map it to one of seven
families. Keywords, not exact matching — pick the family whose **audience**
matches the thread's moment:

| The category looks like                                                     | Family            |
| --------------------------------------------------------------------------- | ----------------- |
| bayi, anak, balita, mainan, stroller, MPASI, perlengkapan sekolah, ibu/mama | `kids-mom`        |
| skincare, makeup, lip, tint, serum, sunscreen, kosmetik, parfum             | `skincare-makeup` |
| snack, camilan, makanan, minuman, kopi, bumbu, kue, frozen food             | `food`            |
| baju, outfit, atasan, sepatu, tas, hijab, aksesori fashion                  | `fashion`         |
| dapur, alat masak, rumah, kebersihan, laundry, organizer, dispenser         | `household`       |
| elektronik, gadget, charger, power bank, audio, kabel, lampu, aksesori HP   | `gadget`          |
| anything mixed, missing, or ambiguous                                       | `other`           |

Ambiguity is editorial, not a lookup failure: choose the family of the reader
the thread is actually for, and when the category is a mix (a travel bag sold
as "fashion & travel"), pick the one whose hooks the angle can use. The family
appears on the preview (`🏷️ <Product> — <Category> · <family>`), so a wrong
mapping is visible to the human before anything is written around it.

### `Description` → the pattern, never the copy

The `Description` column is seller-side copy. Read it for orientation — and only
for orientation:

**Take from it:**

- what the object physically is
- which moment or problem it plausibly serves, and for whom
- the variant / shade / size / contents labels a reader needs to recognise the
  right item in the link post
- search vocabulary — the seller's words for the product's features are often
  the words buyers search with, so they are good research queries
- the visual profile for Step 7

**Never take from it:**

- claims ("tahan 12 jam", "bahan premium", "dibuat dari bahan aman")
- praise and marketing adjectives ("berkualitas", "nyaman", "wajib punya")
- urgency and promotions ("promo terbatas", "harga spesial")
- comparisons ("lebih awet dari merek lain")
- its sentences, its rhythm, or its voice

**The seller's seat — hard rule.** Nothing written from the seller's perspective
reaches the copy. Not quoted, not paraphrased, not attributed: _"Klaim di
deskripsi produknya tahan 2 hari"_ is the seller's seat too, and it is out. A
claim the description raises is a **lead**: verify it with independent evidence
(tier 1) or leave it out. Neutral identifiers are the one exception — the shade
name in the link post ("yang shade coral"), a size, a contents count — stated
flatly, never as a selling point, and never standing in for a performance claim.

`validate_thread.py` reports attribution and brochure vocabulary as the
`seller_viewpoint` warning. It is a soft signal, never a block — but it fires on
exactly the sentences this section refuses.

**The test.** Take the sentence you are about to write. If its truth rests on
the seller's word, it does not ship.

---

## 2. Voice — friendly, casual, polite

The register is spoken Indonesian: how a friend explains something they looked
into, in a chat — not how a listing describes itself.

- **Second person.** Speak to the reader: "kamu", "buat yang…", "kalau kamu
  tipe yang…". The family names its own address in Section 4 (for example
  "moms" in `kids-mom`). Never "Anda", never a corporate "kami", never a
  first-person persona — the writer's own experience enters only through the
  stored testimony (Step 1.5), and only as far as it says.
- **Casual is allowed; sloppy is not.** "banget", "sih", "kok", "nih", "deh",
  "tuh", "kan", "yaa" are ordinary. Capitalisation stays normal, punctuation
  stays clean, and the casualness never turns into slang the reader has to
  decode.
- **Polite means respectful.** No insults, no mocking the reader or the people
  in the story, no shaming ("mama yang baik pasti…"), no sarcasm aimed at
  anyone. Warm disagreement is fine; contempt is not.
- **One emotion per thread**, carried honestly (curiosity, relief, surprise) —
  and a soft joke only when it does not need a fact bent to land.
- **Emoji:** at most one per post, only where a person would really use one.
  Never a row of them.
- **Rhythm:** short lines, a blank line between ideas, no dense paragraphs, no
  bulleted feature lists. Read it out loud — if a line could sit in a product
  listing, rewrite it.

Stiff → human, as a shape reference:

| Stiff                                                      | Human                                                       |
| ---------------------------------------------------------- | ----------------------------------------------------------- |
| "Produk ini menawarkan kemudahan dalam penggunaan harian." | "Ada satu hal yang bikin ini lebih gampang dipakai harian." |
| "Sangat cocok bagi Anda yang mencari kenyamanan."          | "Masuk buat kamu yang lebih milih nyaman daripada ribet."   |
| "Tidak diragukan lagi kualitasnya."                        | (drop it — nothing specific is behind it)                   |
| "Dapat digunakan untuk berbagai kebutuhan."                | "Dipakai buat [satu situasi spesifik] juga aman."           |

---

## 3. Flow — the thread is one thought moving forward

Audience address is not enough; the posts have to connect.

- **The bridge rule.** Each post opens from the thought the previous post left
  behind — the next question it raised, the detail it promised, the doubt it
  planted. No post starts a new topic, and no post repeats the previous one in
  different words.
- **The mid-thread arrival test.** Cover the posts above one post and read it
  alone. A reader who lands there from the feed must still be able to tell what
  conversation they joined, and why this post belongs to it.
- **Every post earns the next.** The last line of each post is the reason to
  read on — not a teaser, a genuine next step in the thought.
- **The ending hands something over.** A boundary, a buying consideration, one
  concrete observation. Never a recap of the thread.

This is what the critic's progression question checks (questions 3 and 6 in
`references/narrative-planner-critic.md`); the family sections below only make
it concrete.

---

## 4. The families

Each family fixes: who the copy addresses, which angles and hooks fit it, the
sentence patterns, and the lines that would break trust in that category. The
angle and hook names are the vocabularies of `references/angle-library.md` and
`references/hook-patterns.md`; the patterns are **shapes with placeholders** —
never sentences to copy, and always filled with facts the research established.

### kids-mom

- **Audience** — the parent inside the situation: feeding, bedtime, first
  solids, play, school prep. Speak to them ("moms", "mama", "bun" when the
  thread is genuinely for parents — a kids' product is not automatically
  addressed to mothers only), never about them.
- **Angles that fit** — `problem`, `use_case`, `checklist`, `decision_guide`,
  `mistake`, `who_is_this_for`.
- **Hooks that fit** — `direct_address`, `scenario`, `question`,
  `mistake_callout`, `category_flag`. Warmth hooks without the first-hand form.
- **Patterns** —
  - "Buat yang lagi [situasi], [hal yang sering kejadian] itu normal kok. Yang sering kelewat justru [observasi]."
  - "Kalau [situasi] bikin [masalah], ini yang biasanya dicek orang sebelum beli: [1-2 hal]."
  - "[Detail yang bikin repot] itu bukan soal [salah paham umum] — masalahnya [penyebabnya]."
- **Keep it real** — no medical or developmental claims ("menambah nafsu makan",
  "meningkatkan ASI", "membantu tumbuh kembang"); no "anakku cocok"-style lines
  without the stored testimony; no shaming; age and safety details only when
  tier-1 sources state them.

### skincare-makeup

- **Audience** — the person deciding for their own skin or face. Address the
  need, not a stereotype: "kalau kamu tipe yang…", "buat yang [kondisi atau
  kebiasaan]".
- **Angles that fit** — `observation`, `myth`, `comparison`, `decision_guide`,
  `unexpected_drawback`, `who_is_this_for`.
- **Hooks that fit** — `question`, `observation`, `myth`, `late_awareness`,
  `boundary`.
- **Patterns** —
  - "Satu hal yang jarang dibahas soal [jenis produk]: [observasi]."
  - "Warna yang kelihatan di foto review itu [situasi]; yang perlu dicek justru [kriteria]."
  - "Kalau kamu tipe yang [kebutuhan], yang lebih masuk: [kriteria], bukan [pilihan populer]."
- **Keep it real** — no "menghilangkan jerawat", "memutihkan", "mengencangkan",
  "menyembuhkan": this family is where absolutes tempt hardest, and the
  amplifier guardrail refuses them in both modes. No invented swatches,
  textures, or before/after. Ingredient and performance claims need tier-1.
  Naming the shade in the link post is a label, not a promise.

### food

- **Audience** — the snacker or the household buyer. Playful is welcome —
  "tim [rasa]" comparisons, light humor — as long as the respect rule holds.
- **Angles that fit** — `comparison`, `observation`, `decision_guide`,
  `small_problem_simple_solution`, `who_is_this_for`.
- **Hooks that fit** — `question`, `comparison_open`, `scenario`,
  `direct_address`, `category_flag`.
- **Patterns** —
  - "Dua varian [X] dan [Y]: bedanya bukan cuma rasa, tapi [perbedaan praktis]."
  - "Kalau kamu tim [rasa atau tekstur], yang perlu dicek dari [jenis makanan]: [1-2 hal]."
  - "Isinya [X] — masuk buat [konteks pemakaian], dan itu yang biasanya kelewat."
- **Keep it real** — taste and texture only from reviews (tier 1); no "bikin
  ketagihan", no "dijamin enak"; no health halo ("sehat", "rendah gula") unless
  the research says it; a joke may bend the delivery, never the facts.

### fashion

- **Audience** — the value-focused shopper: "buat yang lagi cari [item] yang
  [kriteria]". Budget is a legitimate angle; cheapness alone is not a story.
- **Angles that fit** — `comparison`, `trade_off`, `use_case`, `checklist`,
  `who_is_this_for`, `unexpected_drawback`.
- **Hooks that fit** — `comparison_open`, `cost_statement`, `scenario`,
  `category_flag`, `late_awareness`.
- **Patterns** —
  - "Harga [X] itu bukan yang bikin untung — yang bikin untung itu [keputusan]."
  - "Buat yang cari [item] dengan [kriteria], kombinasinya biasanya susah: [A] tapi [B]."
  - "Sebelum checkout, dua hal ini yang biasanya baru kepikiran belakangan: [1-2 hal]."
- **Keep it real** — no fit claims without listed measurements; material and
  durability need tier-1; no "harga termurah" unless something actually
  compared it; size guidance tells the reader how to measure, never that it
  will fit.

### household

- **Audience** — the person solving a small daily annoyance. Thrifty, practical
  logic: cost per use, cost per contents, storage reality.
- **Angles that fit** — `small_problem_simple_solution`, `use_case`,
  `trade_off`, `cost_statement`, `checklist`.
- **Hooks that fit** — `question`, `scenario`, `cost_statement`,
  `direct_address`.
- **Patterns** —
  - "Masalahnya sepele: [masalah]. Yang bikin beda cuma [detail sederhana]."
  - "Hitungan yang lebih masuk: [logika per-pakai atau per-isi] — bukan harga di etiketnya."
  - "Kalau di rumah [situasi], [kriteria] lebih nentuin daripada [kriteria yang biasa dilihat]."
- **Keep it real** — cost-per-use math only with numbers the research
  establishes; no "hemat listrik/air" claims without a source; no durability
  promises; the annoyance in the hook must be one the reader recognises, not a
  hypothetical.

### gadget

- **Audience** — the person annoyed by a specific friction. Problem first, spec
  second; specs are support, never the argument.
- **Angles that fit** — `problem`, `trade_off`, `hidden_feature`, `myth`,
  `who_should_skip`.
- **Hooks that fit** — `question`, `contrarian`, `myth`, `cost_statement`,
  `scenario`.
- **Patterns** —
  - "Kalau [gangguan], yang sering kelewat itu bukan [angka besar], tapi [detail]."
  - "Dua-duanya [jenis]; bedanya baru kerasa waktu [skenario]. Sebelum itu, biasa aja."
  - "Yang perlu dicek sebelum beli: [kriteria], bukan [angka marketing]."
- **Keep it real** — wattage, protocols, ports, and compatibility only from
  tier-1; no "fast charging"-style claims taken from the listing; "lebih
  cepat/lebih kuat" needs a comparison source; a spec dump is not an angle.

### other

For categories that do not map cleanly — mixed, missing, or unfamiliar.

- **Audience** — "orang yang sedang [situasi dari description + research]".
  Name the situation; generic audiences make generic copy.
- **Angles that fit** — `problem`, `observation`, `decision_guide` are
  universal starters.
- **Hooks that fit** — `question`, `observation`, `scenario`.
- **Patterns** —
  - "Yang sering kelewat waktu [aktivitas]: [1-2 hal]."
  - "Kalau [situasi], yang lebih nentuin bukan [hal populer], tapi [hal praktis]."
- **Keep it real** — everything above still applies: description orientates,
  never writes; every claim needs a tier; the register stays friendly, casual,
  polite.

---

## 5. Rotation and recording

The family narrows the menu; it never locks the pattern. Hooks and narrative
structures still rotate exactly as `references/hook-patterns.md` and
`references/content-rules.md` describe — a family that always opens the same way
becomes its own template, which is the failure this pipeline exists to avoid.
When the content note records `hook_pattern` after a publish
(`references/content-rules.md`), the family used is worth writing down beside
it, so the next run can vary within the same family instead of defaulting back
to its first pattern.

## 6. Worked example (shape reference, not copy)

Row: `Product = Sensory Board 30 cm`, `Category = Baby & Kids`,
`Description = "Papan aktivitas sensorik 30cm, banyak tekstur untuk melatih
motorik halus. Bahan premium, aman, bikin anak betah. Wajib punya untuk
stimulasi!"`

- **Family** → `kids-mom` (the audience is the parent).
- **Orientation taken** → it is a 30 cm sensory board; textures and small
  parts; the moment it serves is play for a child still exploring by mouth.
  Search leads: "sensory board bayi", "fase oral bayi", "sensory play aman".
- **Left on the table** → "bahan premium", "aman", "bikin anak betah", "wajib
  punya", and the whole exclamation. None of it ships: nothing independent
  stands behind the claims, and "30 cm" only ships as a size the reader needs,
  never as reassurance.
- **Pattern chosen** → `direct_address` + a practical boundary:
  "Buat yang lagi [situasi], [hal kecil] itu yang biasanya kelewat — bukan
  [salah paham umum]."
- **Point of view it must defend** → the number of textures is not what makes a
  sensory board right for a child still in the oral phase.
- **Flow** → the hook names the situation; post 2 raises the small-part
  condition; post 3 admits what 30 cm means in practice; the ending hands over
  the boundary ("dimainkan sambil ditemani"); the link post names the size and
  the variant.

The same row with the material ignored would produce "banyak tekstur, bagus
untuk stimulasi" — the seller's line with different punctuation, which is
exactly what Step 2's tiers and this file both refuse.
