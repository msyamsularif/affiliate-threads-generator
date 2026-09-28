# Voice profile

Anti-slop can tell the copy what it must not sound like. It cannot tell it what
_this account_ sounds like. That is what this file is for.

Two different jobs, both necessary:

```text
anti-slop      removes generic AI behaviour       (subtractive)
voice profile  adds account-specific character    (additive)
```

Without a voice source, the writer falls back to "good internet Indonesian" —
correct, readable, and interchangeable with any other account.

## Where it comes from

**Never invent a personality.** This profile is filled from real samples the
account owner supplies, and a trait only earns a line here after it shows up in
those samples. Until the owner refines it, the profile stays at the documented
default below — the register the category playbook already fixes (friendly,
casual, polite, second person). That default is a floor, not a character.

### Refining it from real samples

When the owner supplies a small corpus of their own posts (5-10 is enough),
extract — never copy:

```text
sentence length                        emoji frequency
sentence complexity                    question frequency
common connective words                first-person frequency
humor intensity                        use of slang
directness                             use of English terms
average post length                    paragraph density
```

Store the **profile**, never the sample posts: the samples are where the traits
were measured, not text to reuse. If the corpus and the profile disagree, the
corpus wins and the profile is edited.

## The profile

```yaml
voice_profile:
  language: id-ID
  register: casual
  politeness: friendly
  perspective: observer # writes from observation, never from claimed use
  directness: medium
  humor: low-medium
  warmth: medium
  skepticism: medium # willing to say a product is not for everyone
  sentence_rhythm: mixed # short reactions next to longer observations
  explanation_density: low
  product_promotion: restrained
  emoji_usage: low
  rhetorical_questions: occasional
  english_mix: occasional
  slang: natural-only # never forced
  punctuation: conversational

  preferred:
    - concrete observations
    - short reactions
    - understated humor
    - specific comparisons
    - useful caveats
    - unfinished-looking thought transitions when natural

  avoid:
    - motivational language
    - advertising language
    - exaggerated enthusiasm
    - fake first-person experience
    - forced jokes
    - artificial typos
    - forced slang
```

## How the pipeline uses it

| Step | What the voice profile decides there                                                                                                          |
| ---- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| 4    | Voice is resolved before the plan is written; the hook variants are scored on `voice_fit`                                                     |
| 5    | The draft is written in this voice — register, rhythm, directness                                                                             |
| 6    | Naturalization (`references/naturalization.md`) restores this voice after the anti-slop rewrite; the editorial audit asks whether it survived |

The category playbook still fixes the _floor_ (friendly, casual, polite, second
person, no brochure lines). The voice profile refines it; it never lowers it.

## What it never does

- **It never licenses a first-hand claim.** `perspective: observer` is the
  default for a reason: the experience rule (Step 1.5) is decided by the Sheet
  row, not by the profile.
- **It never overrides the evidence rules.** A voice trait cannot turn an
  unsupported claim into a supported one.
- **It is not a persona.** Traits describe how the account already writes, taken
  from real samples — they are not a character to perform. "Witty and uses lots
  of emojis" invented from nothing is as wrong as copying the samples.
- **It is not a list of sentences to paraphrase.** If the writer finds itself
  reusing sample wording, it has confused the profile with a corpus.

## Keeping it real

A voice trait that only exists because the model decided the account "should"
sound that way is the same failure as a fake experience claim, one level down.
When in doubt, leave the field at its default and write closer to the research.
