# Publish contract — how `threads_publish` behaves

`threads_publish` is the only path from this system to Meta Threads. It is
application code, not a prompt, and it re-derives its own preconditions rather
than trusting anything the model reported.

## Calling it

```json
{
  "product_id": "12",
  "posts": [
    { "text": "post 1 copy" },
    { "text": "post 2 copy" },
    { "text": "post 3 copy", "image_url": "https://.../image.jpg" },
    { "text": "post 4 copy with the link and the disclosure" }
  ],
  "confirm_publish": true,
  "approval_note": "saya approve",
  "topic_tag": "powerbank"
}
```

- `product_id` — the exact ID shown in the preview the human approved.
- `posts` — the thread in order. Post 1 is the root; each later post is published
  as a reply to the previous one, so they appear as one thread.
- `confirm_publish` — must be `true`. Set it only after explicit human approval.
- `approval_note` — optional quote of the human's own words, for the audit log.
- `topic_tag` — optional, root post only, 1-50 chars, no `.` or `&`.

## What it checks before doing anything

In this order. Any failure returns an error and **publishes nothing**.

1. **`confirm_publish`** is truthy.
2. **`product_id`** is present, and **`posts`** is non-empty.
3. **The Sheet row exists** for that ID.
4. **No half-finished publish** is already recorded for that ID (see below).
5. **`Status` is exactly the eligible value** — default `Ready To Generate`.
6. **`Threads URL` is empty.**
7. **Hard content guardrails:**
   - post count between `min_posts` (3) and `max_posts` (6)
   - no empty posts
   - ≤ 500 characters per post, counting emoji as their UTF-8 byte length
   - ≤ 5 unique links per post
   - `image_url`, if present, is `https://`
   - no fabricated first-hand experience (blocked phrase list)
   - a disclosure marker is present in some post
   - the row's `Affiliate URL` actually appears in some post
8. **`THREADS_ACCESS_TOKEN`** resolves.

## What it does

```
create container (post 1) ──► wait ──► publish ──► media_id_1
create container (post 2, reply_to_id=media_id_1) ──► wait ──► publish ──► media_id_2
...
GET /{media_id_1}?fields=permalink,username
```

Then, **and only then**:

```
ledger: record {product_id, media_ids, permalink, sheet_synced: false}
Sheet:  F=permalink, G=Done
ledger: sheet_synced = true
```

The ledger write happens _before_ the Sheet write on purpose. If the Sheet write
fails, the record of what was published survives, so a retry can finish the Sheet
instead of publishing a duplicate.

## What it returns

### Success

```json
{
  "ok": true,
  "status": "published",
  "product_id": "12",
  "threads_url": "https://www.threads.net/@user/post/ABC123",
  "media_ids": ["ABC123", "DEF456", "GHI789"],
  "posts_published": 3,
  "sheet": {
    "ok": true,
    "row": 14,
    "status": "Done",
    "threads_url": "https://..."
  },
  "warnings": [{ "code": "generic_phrase", "message": "...", "post": 2 }],
  "next_step": "..."
}
```

`warnings` are soft anti-slop signals that did not block. They are worth reading —
but the copy is live now, so they are for the next thread, not this one.

### Published, but the Sheet write failed

```json
{
  "ok": true,
  "status": "published_sheet_write_failed",
  "threads_url": "https://...",
  "sheet": { "ok": false, "row": 14, "error": "..." },
  "next_step": "The thread is live... Re-call threads_publish with the same product_id..."
}
```

**The thread is live.** Do not publish again. Re-call with the same `product_id`
and it will only retry the Sheet write.

### Repaired a half-finished publish

```json
{
  "ok": true,
  "status": "sheet_resynced",
  "product_id": "12",
  "threads_url": "https://..."
}
```

Nothing new was published. The Sheet was behind by one write and is now correct.

### Refused

```json
{
  "ok": false,
  "stage": "precondition",
  "error": "Row 14 (ID 12) has Status \"Hold\", not \"Ready To Generate\". Nothing was published.",
  "hint": "The human held this one. Resume it by setting Status back to the eligible value first.",
  "current_status": "Hold",
  "expected_status": "Ready To Generate"
}
```

| `stage`        | Meaning                                                 | What to do                                  |
| -------------- | ------------------------------------------------------- | ------------------------------------------- |
| `approval`     | `confirm_publish` was not set                           | Show the preview and wait for real approval |
| `input`        | Missing `product_id` or empty `posts`                   | Fix the call                                |
| `sheets_read`  | Could not read the Sheet                                | Setup problem — run `threads_check`         |
| `sheets_setup` | No spreadsheet configured, or `google_api.py` not found | Setup problem                               |
| `precondition` | The row's state changed                                 | Report it. Do not retry.                    |
| `guardrails`   | Hard rules failed — `violations` lists them             | Rewrite, re-preview, re-approve             |
| `credentials`  | No `THREADS_ACCESS_TOKEN`                               | Setup problem                               |
| `publish`      | The Threads API refused                                 | Report. Nothing was recorded.               |
| `sheets_write` | Sheet write failed after a publish                      | Re-call to repair                           |

## Rate limits

Threads allows **250 published posts and 1000 replies per 24 hours** per profile.
A 5-post thread costs 1 post + 4 replies. Hitting the limit returns a rate-limit
error code; the tool reports it and nothing is recorded. Wait — do not retry in a
loop.

## What the tool will never do

- Publish when the row is not eligible.
- Publish when the human did not confirm.
- Write `Status=Done` before the posts are live.
- Change the row's `Status` on a failed publish.
- Publish the same product twice because of a Sheet failure.
- Let a bypass path exist — there is no other token, no other endpoint, and no
  other tool.

## Approval, in one paragraph

The tool is not the approval. The `pre_tool_call` hook escalates every
`threads_publish` call to Hermes' human-approval gate, and the tool's own
`confirm_publish` check refuses without an explicit flag. Those two together are
the mechanism. Your job is to not set the flag until the human has actually said
yes, in their own words, about the product on screen.
