# Hook patterns

Post 1 has one job: earn the next post. `references/content-rules.md` rotates the
narrative _structure_; this file rotates the _shape of the opening sentence_.

Three different axes, deliberately separate:

| Thing               | Question it answers                            |
| ------------------- | ---------------------------------------------- |
| angle               | what conversation is this thread having?       |
| narrative structure | in what order does the reader move through it? |
| hook pattern        | what shape is sentence one?                    |

Two threads can share an angle and still open nothing alike, which is why the
hook gets its own vocabulary.

**The experience rule comes first.** In `none` mode (no stored testimony) no hook
may claim experience: the fabricated-personal-experience guardrail in
`threads_publish` blocks the obvious forms ("aku sudah coba", "gue udah pakai"),
and a hook is exactly where those claims want to live. The safe equivalent of
"wish I'd known this sooner" is the rhetorical version aimed at the world, not at
the writer: _"Kenapa ini jarang dibahas?"_ — never _"aku baru tahu ini
kemarin"_. In `firsthand` mode a first-hand hook is allowed, but only inside what
the stored testimony says (Step 1.5), and never as a guarantee.

## The patterns

Pick one per thread, and rotate it: if the last two content notes used the same
`hook_pattern`, choose a different one even if it fits slightly less well.

| Pattern           | Shape                                                                      | Example                                                                               |
| ----------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `question`        | the question the reader is already asking                                  | "Kenapa colokan hotel selalu di tempat yang paling nggak mungkin dijangkau?"          |
| `observation`     | something true that nobody has put into words                              | "Kebanyakan orang beli power bank berdasarkan mAh, bukan jarak colokannya."           |
| `contrarian`      | push back on the received wisdom, with evidence behind it                  | "Saran saya justru kebalikannya: jangan cari yang paling besar."                      |
| `mistake_callout` | name a common, recoverable error                                           | "Kesalahan paling umum: beli berdasarkan angka terbesar di kotaknya."                 |
| `boundary`        | draw who this is for, and who it is not                                    | "Kalau kamu cuma butuh buat charge sekali sehari, ini overkill."                      |
| `scenario`        | one specific scene, tight enough to recognise                              | "Naik kereta 6 jam, colokan cuma ada di gerbong makan."                               |
| `comparison_open` | two real options, with a verdict that depends on the reader                | "Dua-duanya bagus. Bedanya cuma satu: yang satu buat di tas, yang satu buat di saku." |
| `myth`            | a belief that does not survive contact with the facts                      | "'mAh gede = tahan lama' cuma benar kalau wattnya ikut naik."                         |
| `cost_statement`  | state the trade in one line                                                | "Kamu dapat kapasitas, kamu bayar pakai berat."                                       |
| `category_flag`   | what to check before buying anything in this category                      | "Yang sering kelewat waktu beli alat masak: tiga hal ini."                            |
| `late_awareness`  | rhetorical "why is this not discussed?" — never a personal discovery claim | "Kenapa ukuran 30 cm jarang dibahas untuk produk sekelas ini?"                        |
| `direct_address`  | name the reader and their situation                                        | "Kalau kamu masak tiap hari, bagian ini yang perlu kamu baca."                        |

### The tricky ones

`late_awareness` and reaction-style openers are the two patterns most likely to
tempt a fabricated experience claim. Compare:

- ✗ "Baru tahu ini kemarin, padahal udah lama nyari." — a first-hand claim the
  system cannot make without a stored testimony, and `threads_publish` blocks
  the wording in `none` mode.
- ✓ "Ini yang jarang dibahas soal produk sekelas ini." — the same curiosity,
  aimed at the category instead of at the writer.

If a hook only works when the writer has used the product, either take another
pattern or — when the row is `firsthand` and the testimony supports it — write
the fact the testimony actually contains, without adding to it.

## Choosing

| Angle type                               | Patterns that usually fit                |
| ---------------------------------------- | ---------------------------------------- |
| `problem`                                | `question`, `scenario`, `direct_address` |
| `observation`, `hidden_feature`          | `observation`, `late_awareness`          |
| `myth`, `contrarian`                     | `myth`, `contrarian`                     |
| `trade_off`, `unexpected_drawback`       | `cost_statement`, `boundary`             |
| `who_should_skip`, `who_is_this_for`     | `boundary`, `direct_address`             |
| `mistake`, `checklist`, `decision_guide` | `mistake_callout`, `category_flag`       |
| `comparison`                             | `comparison_open`                        |
| `use_case`                               | `scenario`                               |

A starting point, not a rule. The critic's second question — does post 1 open a
loop that only reading on can close? — is what actually decides.

## The shape rules

- **One sentence, not a paragraph.** Two at most.
- **No announcement.** "Mari kita bahas", "yang perlu kamu tahu", "ini dia
  alasannya" are what `validate_thread.py` warns about as
  `excessive_signposting`.
- **No product in post 1.** The product enters when the reader already has a
  reason to care — see the product-entry notes in
  `references/narrative-planner-critic.md`.
- **No promise the thread cannot keep.** The hook has to be paid off by what
  follows; a hook the thread never answers is worse than a dull one.
- **No hashtags.** The topic tag is metadata (`topic_tag`), set at publish time,
  never typed into the copy.

## Worked example

Angle `trade_off` — a 20000mAh power bank at 380g:

- `cost_statement`: "Kamu dapat kapasitas, kamu bayar pakai berat."
- `boundary`: "Kalau kamu cuma butuh buat charge sekali sehari, ini overkill."
- `scenario`: "Naik kereta 6 jam, colokan cuma ada di gerbong makan."

All three are the same angle. `cost_statement` states the trade, `boundary`
tells someone not to buy, `scenario` makes them picture the day. If the previous
thread already opened by stating the trade, take `boundary` — even though
`cost_statement` still fits the angle best. That is what rotation means.

## Recording it

After a successful publish, save the pattern's name (plus the opening line) in
the content note — format in `references/content-rules.md`, section 9.
`novelty_vs_recent` in the angle scoring reads it, and it is the only reason the
vocabulary has to stay stable between runs.
