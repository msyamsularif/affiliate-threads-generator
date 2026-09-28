# Naturalization

The pass that runs **after the anti-slop audit and before the affiliate
editorial review** (Step 6). Its job: make the draft read like a person wrote
it, while preserving every fact and every editorial intention.

## Why it is not called "humanization"

"Humanization" invites the wrong fix: artificial imperfections. The pass never
injects typos, bad grammar, random lowercase, forced slang, or random emojis.
Human writing is not careless writing.

What it removes is **visible scaffolding** — the sentences that keep the
structure standing, and nothing else. The goal is not to remove structure; the
goal is to hide it.

## The questions

Ask these of the draft, after the anti-slop pass has done its work:

```text
1. Which sentence sounds like it was written to explain the structure?
2. Which sentence exists only because the template expects it?
3. Which sentence repeats the previous thought?
4. Which sentence tells the reader something obvious instead of letting them infer it?
5. Which sentence sounds like seller copy?
6. Which sentence sounds more polished than the account normally sounds?
7. Where can one sentence disappear without losing meaning?
8. Does the product enter because the conversation reaches it, or because the
   planner scheduled it?
9. Does the ending give information, or merely conclude?
10. Does any line feel like it is trying to "sound human"?
```

Then **rewrite only the identified problems.** Do not regenerate the whole
thread by default — a re-roll loses the parts that were working, including the
research detail and the voice.

## The rules

### 1. Remove explanation scaffolding

> ✗ "Hal yang menarik dari produk ini adalah ukuran produknya."
>
> ✓ "Yang bikin ini menarik justru ukurannya."

Both sentences say the same thing. The first narrates that a point is being
made; the second makes it.

### 2. Prefer observation over conclusion

> ✗ "Jadi, ukuran produk ini perlu dipertimbangkan sesuai tahap perkembangan anak."
>
> ✓ "30 cm ternyata cepat terasa kecil begitu anak mulai merangkak."

The second is less "complete" grammatically, and much more evidently written by
someone who noticed something. A conclusion announces that the thinking is
finished; an observation hands the thinking to the reader.

### 3. Let one detail carry the meaning

Do not follow a concrete detail with three sentences explaining why it matters.
State it and trust the reader: "Dan ukurannya cuma 30 cm." can be the whole
paragraph.

### 4. Repeat the clearest word when repetition is natural

Do not rotate synonyms to avoid repetition. People repeat the word that is
actually the right word; only systems carry a mental thesaurus.

### 5. Keep uneven sentence lengths

```text
Awalnya kelihatan simpel.

Tapi bagian teksturnya justru yang bikin beda.

Masalahnya, kalau anak masih suka masukin benda ke mulut, bagian ini juga
yang harus paling diperhatikan.
```

One line, three lines, two lines. The rhythm is allowed to be uneven. If every
sentence in the thread has a similar length and shape, that is the thing to fix.

### 6. Do not manufacture imperfections

Never inject typos, bad grammar, random lowercase, forced slang, or random
emojis. If the only way a sentence can sound casual is a deliberate mistake, cut
the sentence instead.

### 7. Do not complete every thought

Some Threads writing is interesting precisely because the reader connects the
last step. If the argument still lands without the wrap-up sentence, drop the
wrap-up sentence.

## Worked rewrite

The draft, too structured — every sentence works, and the reader can feel the
machinery (hook → overlooked point → "makanya" → example → recommendation →
CTA):

```text
Waktu nyari mainan tekstur buat bayi, yang dicek biasanya satu hal: ada berapa
jenis teksturnya.

Yang hampir nggak pernah dicek: si kecil sekarang masih di fase masukin semua
benda ke mulut atau nggak.

Padahal jawaban pertanyaan kedua itu yang nentuin mainannya kepakai, atau malah
disimpan dulu. Makanya, konteksnya penting.

Contohnya, sensory playmat ini punya beberapa jenis tekstur...

Jadi, produk ini cocok buat dimainkan sambil ditemani.

Kalau mau lihat produknya:
<link>
```

The same thought, naturalized — scaffolding gone, facts untouched:

```text
Ada mainan bayi yang makin kelihatan menarik kalau teksturnya makin banyak.

Tapi kalau anak masih punya kebiasaan masukin benda ke mulut, jumlah tekstur
bukan hal pertama yang saya lihat.

Di sini detail kecilnya justru jadi penting. Ada bagian yang kasar, lembut,
kenyal, sampai tekstur yang lebih keras.

Dan ukurannya cuma 30 cm.

Jadi saya lebih melihatnya sebagai panel sensory kecil yang dipakai sambil
ditemani, bukan playmat yang ditaruh lalu ditinggal.

Detail ukuran dan variannya ada di sini:
<link>
```

Still structured internally. The structure is just no longer the thing you
notice.

## What it may not touch

- **Facts.** No claim is added, removed, or strengthened. Everything stays
  traceable to its evidence tier.
- **The trade-off.** Naturalization never softens a limitation to sound nicer.
- **Provenance.** In `firsthand` mode it cannot extend the testimony; in `none`
  mode it cannot introduce a first-hand claim with a more casual phrasing.
- **The voice profile** (`references/voice-profile.md`). After the anti-slop
  pass flattens the prose, naturalization restores the account's rhythm. If a
  rewrite makes the copy less specific, it failed — regardless of how natural it
  reads.
- **The hard rules.** Character limits, the affiliate URL, the topic tag. A
  naturalization rewrite that breaks one is a rewrite that gets rejected.

## Bounded

Two revision rounds, the same as the other passes. If the thread still reads as
templated after naturalization, the problem is upstream — the angle or the beat
plan, not the wording. Go back to Step 3, not into a third rewrite.

After every rewrite, the evidence review runs again (Step 6): a rewrite that
introduced a new fact or dropped a qualification is a regression, not an
improvement.
