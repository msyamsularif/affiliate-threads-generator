# Beat library

A **beat is an intention, not a template.** The planner (Step 4) picks the beats
a thread needs, in the order the reader should meet them, and gives each one its
purpose. The writer (Step 5) decides how many posts each beat takes.

This is the replacement for the old post-role thinking. There is no "post 1 is
the hook, post 2 is the problem, post 3 is the product". There is a thought, and
there are the things that have to happen before it lands.

## The beats

| Beat                  | Purpose                                                |
| --------------------- | ------------------------------------------------------ |
| `scene`               | put the reader in a recognisable situation             |
| `observation`         | point out something easy to miss                       |
| `friction`            | expose a real annoyance                                |
| `question`            | surface the reader's natural question                  |
| `contrast`            | put two ideas beside each other                        |
| `realization`         | reveal what changed in the writer's understanding      |
| `consequence`         | explain what the previous point actually means         |
| `evidence`            | introduce a concrete researched detail                 |
| `product_clue`        | mention one relevant product detail                    |
| `boundary`            | explain who should or should not care                  |
| `trade_off`           | show the actual cost or limitation                     |
| `recommendation`      | state why the product fits the conversation            |
| `closing_observation` | leave a useful thought                                 |
| `contextual_cta`      | provide the link without turning the ending into an ad |

## There is no fixed sequence

Each of these is a complete thread:

```text
scene → friction → realization → evidence → product_clue → boundary
```

```text
question → contrast → evidence → product_clue → closing_observation
```

```text
observation → consequence → product_clue → trade_off
```

The writer chooses the **smallest number of beats** that makes the thought work.
Three beats that land beat six that pad. A beat that exists only because the
plan expected it to exist is the scaffolding this file is designed to remove.

## Beats are not posts

- Two beats may live in one post ("friction + contrast" is a normal first line).
- One beat may take two posts (an `evidence` beat with a caveat usually does).
- A beat list with six items is not a six-post thread; derive the post breaks
  from the writing, then check the count is inside 3-10.

## Choosing beats

Ask what the reader must understand before the next thing is believable:

- Does the thread need a situation before it can make a point? Start with
  `scene` or `observation` — not with `question` out of habit.
- Is the insight going to feel arbitrary? It needs `evidence` or `consequence`
  under it.
- Does the product enter because the conversation reached it? It needs a
  `product_clue` at the point where the reader is already asking.
- Would the recommendation overreach without it? It needs `boundary` or
  `trade_off` — the honest one, from the research.

### `beats_to_skip`

Record the beats deliberately left out, so the writer does not add them back
out of habit. The two most common entries are not beats at all but shapes:

- `summary` — a closing restatement of everything above
- `generic_conclusion` — "jadi, produk ini cocok untuk..." with no new
  information

These are always skippable, and skipping them is the difference between an
ending and a wrap-up. Any beat that would duplicate another beat's purpose
belongs here too.

## Relation to the other axes

| Thing               | Question it answers                                  | Where it lives                |
| ------------------- | ---------------------------------------------------- | ----------------------------- |
| angle               | what conversation is this thread having?             | `references/angle-library.md` |
| narrative structure | what remembered shape is the reader moved through?   | `references/content-rules.md` |
| beats               | what must happen, in order, for the thought to land? | this file                     |
| hook pattern        | what shape is sentence one?                          | `references/hook-patterns.md` |

The structure is picked from the rotation table and recorded in the content note.
The beats are planned fresh every run: writing the same beat sequence as the
last two threads is the same repetition problem as reusing a hook, just one
level up. The `beats` line in the content note is what the next run checks.

## Worked example

Angle `trade_off` — a 20000mAh power bank at 380g:

```yaml
beats:
  - beat: observation
    purpose: the number people buy by (mAh) is not the number they live with (g)
  - beat: friction
    purpose: the weight is the thing nobody mentions in the listing
  - beat: evidence
    purpose: real weight and real charge count from reviews, so the trade is concrete
  - beat: product_clue
    purpose: this one, at this weight, with this capacity — one detail only
  - beat: boundary
    purpose: if you only charge once a day, the lighter one is the better buy
```

Six items would have meant padding; five carries it. The `recommendation` beat
is deliberately absent (`beats_to_skip: [summary, generic_conclusion]`) — the
boundary already does the recommending, honestly.
