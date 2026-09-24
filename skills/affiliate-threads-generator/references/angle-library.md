# Angle library

An **angle** is the conversation the thread is having. The product is a supporting
element inside it.

Generate **5-8 candidates** before choosing. Jumping straight to one "best angle"
is how you end up with a feature list.

Each candidate is:

```json
{
  "angle_type": "trade_off",
  "core_idea": "Power bank besar itu menang kapasitas, kalah di berat — dan itu bukan masalah kalau kamu tahu kapan pakainya.",
  "tension": "Semua orang beli yang paling besar, padahal yang paling sering dipakai justru yang paling ringan."
}
```

`tension` is the part that makes it worth reading. If you cannot name the tension
in one line, the angle is not ready.

Which types fit first depends on the product's category family — see
`references/category-playbook.md`.

## The types

### `problem`

The friction people already feel. Start from the annoyance, not the fix.

> _"Kenapa colokan hotel selalu di tempat yang paling nggak mungkin dijangkau?"_

### `observation`

Something true about the category that most people have not put into words.

> _"Kebanyakan orang beli power bank berdasarkan mAh, bukan berdasarkan jarak colokannya."_

### `unexpected_benefit`

A genuine advantage that is not the headline feature.

> _"Ukurannya yang kecil bukan cuma soal ringkas — dia yang bikin kamu nggak mikir dua kali buat bawa."_

### `unexpected_drawback`

A real limitation of the _category_ or of the _buying decision_, stated honestly.

> _"Yang perlu kamu tahu sebelum beli yang kapasitasnya paling gede: kamu akan berhenti bawa dia."_

### `comparison`

Two real options, weighed, with a verdict that depends on the reader.

> _"Dua-duanya bagus. Bedanya cuma satu: yang satu buat di tas, yang satu buat di saku."_

### `myth`

A belief people hold that does not survive contact with the specs.

> _"'mAh gede = tahan lama' cuma benar kalau wattnya ikut naik."_

### `trade_off`

Name the trade explicitly. This is usually the most credible type.

> _"Kamu dapat kapasitas, kamu bayar pakai berat. Pertanyaannya cuma: kamu beneran butuh yang mana?"_

### `use_case`

One specific scenario, described tightly enough that the reader recognises it.

> _"Skenario: naik kereta 6 jam, colokan cuma ada di gerbong makan."_

### `who_is_this_for`

Draw the boundary. Name who it fits and, implicitly, who it does not.

> _"Ini masuk kalau kamu [X]. Kalau kamu [Y], uangmu lebih baik ke tempat lain."_

### `who_should_skip`

Explicitly tell some readers not to buy. High trust, low salesiness.

> _"Kalau kamu cuma butuh buat charge sekali sehari, ini overkill."_

### `before_after`

The change in the reader's day, not a photo pair.

> _"Sebelum: nyari colokan di bandara. Sesudah: nggak mikirin colokan sama sekali."_

### `decision_guide`

Turn the choice into two or three questions with answers.

> _"Tiga pertanyaan yang jawabannya nentuin kamu butuh yang mana."_

### `checklist`

A short list of things to check before buying anything in this category.

> _"Yang sering kelewat waktu beli [kategori]: empat hal ini."_

### `mistake`

A specific, common, recoverable error.

> _"Kesalahan paling umum: beli berdasarkan angka terbesar di kotaknya."_

### `hidden_feature`

Something real, in the specs or reviews, that most people miss.

> _"Ada satu detail di spesifikasinya yang hampir nggak pernah dibahas: [detail]."_

### `contrarian`

Push back on the category's received wisdom — with evidence, not for effect.

> _"Saran saya justru kebalikannya: jangan cari yang paling besar."_

### `small_problem_simple_solution`

The unglamorous fix for the unglamorous problem.

> _"Masalahnya sepele: kabelnya kusut. Solusinya juga sepele."_

## Scoring

Score each candidate 0-10. Keep the scores visible in your reasoning.

| Dimension                | Question                                                                   |
| ------------------------ | -------------------------------------------------------------------------- |
| `relevance`              | Does this matter to the audience of this product, right now?               |
| `curiosity`              | Does post 1 make someone stop scrolling?                                   |
| `specificity`            | Could this thread be about any product in the category? If yes, score low. |
| `evidence_strength`      | Can every claim trace to tier 1-3?                                         |
| `conversation_potential` | Would a stranger want to reply?                                            |
| `product_fit`            | Does the product genuinely resolve the tension?                            |
| `salesiness_penalty`     | How much does this smell like an ad? (higher = worse)                      |
| `novelty_vs_recent`      | How different is this from recent posts? (0 if it repeats)                 |

### The rule about `product_fit`

**High `product_fit` alone must never dominate selection.** A `who_should_skip`
angle with mediocre fit and high curiosity beats a `hidden_feature` angle with
perfect fit and no reason to read. This is the single most common way this system
degrades into a catalogue.

### Tie-breakers

1. Prefer the higher `novelty_vs_recent`.
2. Prefer the higher `evidence_strength`.
3. Prefer the lower `salesiness_penalty`.
4. Prefer the type used least recently.

## Rejection tests

Reject an angle if any of these is true:

- The product has to be mentioned in post 1 for the angle to make sense.
- You cannot write three posts about it without repeating yourself.
- The tension is manufactured — nobody actually feels it.
- Every factual claim it needs is tier 4 or 5.
- It is the same `angle_type` and `hook_pattern` as one of the last three
  published threads.
- Removing the product leaves nothing worth reading.

That last one is the real test. Apply it honestly.

## Worked example

Product: a compact 20000mAh power bank. Description says 22.5W PD, 380g, matte
black, two ports.

```
1. problem          "colokan nggak pernah di tempat yang kamu butuhin"    rel 8 cur 6 spec 5 ev 6 conv 7 fit 7 sal 2 nov 7  = 40
2. myth             "'mAh gede = tahan lama' cuma kalau wattnya naik"     rel 8 cur 8 spec 7 ev 7 conv 8 fit 7 sal 3 nov 9  = 47
3. trade_off        "dapat kapasitas, bayar pakai berat (380g)"           rel 9 cur 7 spec 9 ev 9 conv 8 fit 9 sal 2 nov 8  = 53
4. who_should_skip  "kalau charge sehari sekali, ini overkill"            rel 8 cur 9 spec 8 ev 8 conv 9 fit 8 sal 1 nov 9  = 52
5. checklist        "4 hal yang sering kelewat sebelum beli power bank"   rel 8 cur 6 spec 6 ev 7 conv 7 fit 5 sal 2 nov 5  = 38
6. comparison       "buat di tas vs buat di saku"                         rel 8 cur 6 spec 7 ev 7 conv 7 fit 8 sal 3 nov 6  = 44
7. use_case         "kereta 6 jam, colokan cuma di gerbong makan"         rel 8 cur 8 spec 7 ev 6 conv 8 fit 7 sal 2 nov 8  = 46
```

Winner: `trade_off` (53). `who_should_skip` is a close second and a better novelty
pick if `trade_off` ran recently — which is exactly what `novelty_vs_recent` is
for.

Notice that #3 wins on `specificity` and `evidence_strength`, not on
`product_fit` alone. It also has the lowest salesiness penalty, which is a feature.
