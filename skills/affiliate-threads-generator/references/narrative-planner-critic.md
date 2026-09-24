# Narrative planner and critic

Step 4 of the pipeline. The planner produces a plan; the critic tries to destroy
it. Only a plan that survives the critic gets written.

The planner is not a fill-in-the-blanks template. Objectives, not roles: do not
force the same sequence of posts every time, and do not decide the product enters
at post 3 just because post 3 is where it usually enters.

## Planner output

Produce this explicitly. Not in your head — write it out, because the critic and
the writer both read it.

```yaml
topic: <one line — what this thread is actually about>
audience: <who specifically this is for>
angle_type: <from the angle library>
point_of_view: <one line — what the writer believes, and wants the reader to notice>
tension: <one line — the thing that makes it worth reading>

hook_strategy: >
  <what post 1 does, and why someone stops scrolling>

narrative:
  - objective: <what the reader learns or notices>
  - objective: <what changes in their understanding>
  - objective: <where the product becomes relevant, and why here>
  - objective: <the qualification or boundary>
  - objective: <the natural next action>

product_role: <supporting evidence / worked example / one answer among several>
product_entry: <post N — and the reason the reader is ready for it there>
cta_post: <the post that carries the link and the disclosure>
affiliate_intensity: 2 # ~80% value / 20% product
narrative_structure: <the structure used this time — rotated across runs>

must_include:
  - <specific detail from tier-1 evidence, or a tier-2 seller claim attributed to the seller>
  - <the real trade-off, when the angle has room for one>
  - <disclosure>
must_not_claim:
  - <anything unsupported (tier 4)>
  - <any first-hand experience>
  - <any invented weakness>

evidence_ledger:
  - claim: <claim>
    tier: 1
    source: <where it came from>
```

### On `point_of_view`

If it is generic — "produk ini punya beberapa kelebihan dan kekurangan" — stop
before writing anything. That is an angle problem, not a wording problem. Go back
to Step 3 and take the next candidate from the shortlist.

Good:

> "Yang menentukan mainan ini bukan banyaknya tekstur, tapi kapan tekstur itu
> aman untuk dikenalkan."

### On `narrative`

Objectives, not post roles. Two objectives may collapse into one post; one
objective may take two posts. The list is the order the reader moves through, and
it is allowed to be three items or six.

### On `product_entry`

The number is a consequence of the narrative, not a schedule. Record it together
with the reason: "post 3 — the reader has just seen what the problem costs, and
this is one answer to it." If the reason is "because the product usually enters at
post 3", the plan is not ready.

### On `affiliate_intensity`

A scale from 0 to 5, where the default is `2`:

| Value | Feel                                                                                           |
| ----- | ---------------------------------------------------------------------------------------------- |
| 0     | The product is never named                                                                     |
| 1     | The product is one example among several                                                       |
| 2     | **Default.** The product resolves the tension, and the thread would still be useful without it |
| 3     | The product is clearly the recommendation                                                      |
| 4     | The product is the topic                                                                       |
| 5     | A product listing                                                                              |

If the human asks for a harder sell, raise it to 3 — and say so plainly in the
preview so they can see what changed. Never go to 4 or 5; that is outside what this
system produces.

## Critic — the gate, then nine questions

### Gate: the point of view

Read `point_of_view` first. If it is generic, the plan fails immediately — do not
spend time on the other questions, go back to Step 3.

A point of view is a position the thread can explore. "Produk ini punya beberapa
kelebihan dan kekurangan" is not a position; it is a table of contents.

Then answer every question below. "Yes" without a reason is not an answer.

### 1. Is the topic interesting without the product?

Write the thread's premise with the product removed. If it is not interesting,
the plan fails. This is the single most important question.

### 2. Does the hook create real curiosity?

Read post 1 in isolation. Does it open a loop that only reading on can close? Or
is it a summary of what is coming (which closes the loop immediately and gives no
reason to continue)?

### 3. Is there progression between posts?

Each post must add something the previous one did not have. If post 3 restates
post 2 in different words, the plan fails.

### 4. Is the product introduced when the reader already has a reason to care?

Read `product_entry` and the reason attached to it, then read the posts before
it. If the only reason the product appears where it does is "that is where the
product usually appears", move it later or strengthen what comes before. It
never belongs in post 1.

### 5. Is the thread only a feature list?

Cover the product name. Does the text still read as an argument? If it becomes a
list of specifications, the plan fails.

### 6. Does each post create a reason to continue?

For each post, name the reason. "Because the thread is good" is not a reason.

### 7. Does the ending feel like an advertisement?

Read the last two posts together. If the answer is "yes, that turned into an ad",
rewrite the ending — not by hiding the disclosure, but by making sure the last
thing the reader gets is still value.

Ask the second half of the question too: does the ending give the reader
something useful — a boundary, a buying consideration, one concrete observation —
or does it merely summarize what came before? A summary is not an ending.

### 8. Are the claims supported?

Walk the evidence ledger. Every claim must map to tier 1-3, and the thread's
substance has to come from tier 1 — a thread built out of the seller's own
description is a paraphrase with a hook, and it fails here. Anything unsupported
(tier 4) is removed, not softened; anything taken from seller material (tier 2)
is attributed to the seller in the copy.

### 9. Is the angle too similar to recent content?

Check the recalled content notes for `angle_type` and `hook_pattern`. If it
matches one of the last three, the plan fails — go back to Step 3.

## The bounded loop

```
plan → critic → (fail) → revise → critic → (fail) → revise → critic
                                                            │
                                          still failing ────┴──► pick a different angle
```

**2-3 revision rounds maximum.** This is a hard bound, not a suggestion.

If the plan still fails after three rounds, the problem is not the plan — it is
the angle. Go back to Step 3 and take the next-best candidate from the shortlist.
That is faster and produces better copy than grinding the same idea.

## Worked failure

**Plan:** angle `hidden_feature` — "power bank ini punya fitur pass-through
charging yang jarang dibahas."

**Critic:**

1. _Interesting without the product?_ No. Pass-through charging is only interesting
   in relation to a product. **Fail.**
2. _Point of view?_ There is none — the feature is the premise. **Fail.**
3. _Product entry earned?_ No. `product_entry` would have to be post 1, because
   the feature _is_ the product.

**Verdict:** fail round 1.

**Revision attempt:** reframe as `problem` — "kenapa power bank sering mati
sendiri waktu lagi dipakai charge HP."

**Critic:**

1. _Interesting without the product?_ Yes — it is a real annoyance people
   recognise.
2. _Curiosity?_ Yes — it names a symptom and implies a cause.
3. _Claims supported?_ Partially — the cause needs tier 2-3 evidence. **Revise.**

**Verdict:** pass with a note to research pass-through behaviour before writing.

Note what happened: the fix was not better writing. It was a better angle.
