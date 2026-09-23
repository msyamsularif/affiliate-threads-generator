# Telegram actions — semantics

Telegram is the only user-facing control surface. The human writes naturally; this
file defines what each kind of message means and what you are allowed to do.

## The review context

**The review context is always the Product ID most recently shown in this
conversation.**

- Every preview displays the Product ID explicitly. That is its only job.
- There is no database of pending reviews. There is no "current item" variable.
  There is the ID on screen and the Sheet.
- If the conversation was reset, compacted, or the human opened a new session,
  you do not have a review context. **Ask.** Do not guess from the Sheet's first
  row, and do not infer from the human's wording.
- If the Sheet row is still `Ready To Generate`, nothing is lost — the human just
  triggers generation again.

## Action table

| Human message (any phrasing)                                       | Action                                                                                                             | Result                                                                   |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------ |
| "Saya approve." · "setuju" · "post aja" · "gas" · "publish it"     | Call `threads_publish` with the Product ID on screen, `confirm_publish: true`, and the exact copy from the preview | Success → `Status=Done`, `Threads URL` saved. Failure → Sheet untouched. |
| "Hold dulu yang ini." · "tahan dulu" · "nanti aja"                 | `set_status.py <ID> Hold`                                                                                          | `Status=Hold`. No publish.                                               |
| "Yang ini jangan dipublish." · "batal" · "cancel" · "skip"         | `set_status.py <ID> Cancel`                                                                                        | `Status=Cancel`. No publish.                                             |
| "Regenerate tapi angle-nya lebih ke orang yang sering travelling." | Back to Step 3 with the new constraint                                                                             | Same Product ID, same research, new angle → new preview                  |
| "Lanjut" · "next" with no product on screen                        | Ask which product                                                                                                  | —                                                                        |
| "ok" · "ya" · "sip" alone                                          | Ambiguous — ask which of approve/hold/cancel                                                                       | —                                                                        |

## Approve — the strict version

Approval has to satisfy all of these. If any one is missing, do not publish; ask.

1. **It is in the human's own message**, in the current turn.
2. **It is explicit.** "approve", "setuju", "post", "gas", "publish" — something
   that means _go_. "ok", "noted", "bagus" do not mean go.
3. **It refers to the product currently on screen.** "approve yang tadi" after two
   previews is ambiguous — ask which one.
4. **It is for this product.** An approval from earlier in the conversation for a
   different product does not carry over.
5. **You are not substituting your own judgement.** You thinking the copy is
   strong is not approval. This is the failure mode this rule exists to prevent.

If the human says something like "kirim" or "post" but no preview is on screen,
ask. A publish with no review context is exactly the accident this design exists
to make impossible.

### What happens when you call `threads_publish`

1. The tool checks `confirm_publish` and refuses if it is not set.
2. Hermes' approval gate shows the human the copy and asks for confirmation. This
   is a second, out-of-band confirmation — it exists because an instruction to the
   model is not a guarantee.
3. The tool re-reads the Sheet. If `Status` is no longer `Ready To Generate`, it
   refuses.
4. The tool runs the hard guardrails. If any fail, it refuses and lists them.
5. The tool publishes through the official Threads Graph API.
6. Only on a confirmed media ID: `Status=Done` and `Threads URL` are written.

### After a successful publish

Report, briefly:

```
✅ Published — Product ID <ID>
🔗 <threads url>
📊 Sheet updated: Status=Done
```

Then save the content-memory note (`content_id`, `angle_type`, `topic`,
`hook_pattern`) so the next run's novelty check works.

### After a failed publish

- `precondition` → the row changed under you (held, cancelled, already done).
  Report the current status. Do not retry, do not "fix" the Sheet yourself.
- `guardrails` → fix the listed violations, show a **new** preview, and wait for a
  new approval. The previous approval was for different copy.
- `credentials` → setup problem. Tell the human what is missing.
- `publish` → transient API failure. Report it. Nothing was recorded.
- `published_sheet_write_failed` → **the thread is live.** Do not publish again.
  Re-call `threads_publish` with the same `product_id`; the tool will only repair
  the Sheet.

## Hold

```
set_status.py <ID> Hold
```

Confirm to the human:

```
⏸️ Held — Product ID <ID>. Sheet Status=Hold. Nothing was published.
```

A held row is no longer eligible. Resuming means setting `Status` back to
`Ready To Generate` — only do that when the human asks for it.

## Cancel

```
set_status.py <ID> Cancel
```

```
🚫 Cancelled — Product ID <ID>. Sheet Status=Cancel. Nothing was published.
```

Cancelled is terminal for this pipeline. Do not resurrect it.

## Regenerate

`"Regenerate tapi angle-nya lebih ke <constraint>."`

- Same Product ID. Never re-select a candidate.
- Same research from Step 2 unless the constraint genuinely requires new
  information (for example "focus on the warranty" when warranty was never
  researched).
- Back to Step 3. The new constraint is a **hard filter** on the angle shortlist,
  not a soft preference — if the human says "more like someone who travels often",
  discard every angle that is not about that scenario.
- The new preview replaces the old one. The old copy is dead; the approval that
  follows applies to the new preview only.
- Regenerate as many times as the human wants. There is no limit, and there is no
  cost to the Sheet — the row stays `Ready To Generate` the whole time.

## Scheduled runs

The cron job (Mon/Wed/Fri/Sun 08:00 Asia/Jakarta) runs this exact pipeline and
delivers the preview to Telegram. It is a trigger, nothing more.

- The scheduled run **never** publishes, under any circumstance.
- If nothing is eligible, the run says so and stops.
- A reply to the delivered preview continues the conversation normally — the
  preview is in the session's history, so the review context survives.
