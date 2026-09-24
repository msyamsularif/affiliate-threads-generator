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
    { "text": "post 4 copy with the link" }
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
- `topic_tag` — the one topic this thread publishes under; required by default
  (`require_topic_tag`). Root post only, and it is metadata: it never appears in
  the copy. Pass the bare topic — 1-50 characters, no `.` or `&`, no leading `#`,
  one line — the topic a reader would search for, not the product name. When the
  topic has a Threads community, the post is surfaced inside that community too.
- `stage` — `auto` (default), `thread` or `link`. Only meaningful under
  `publish_mode: two_stage`; see below.

## What it checks before doing anything

In this order. Any failure returns an error and **publishes nothing**.

1. **`confirm_publish`** is truthy.
2. **`product_id`** is present, and **`posts`** is non-empty.
3. **The Sheet row exists** for that ID.
4. **No half-finished publish** is already recorded for that ID (see below).
5. **`Status` is exactly the eligible value** — default `Ready To Generate`.
6. **`Threads URL` is empty.**
7. **Hard content guardrails:**
   - post count between `min_posts` (3) and `max_posts` (10)
   - no empty posts
   - ≤ 500 characters per post, counting emoji as their UTF-8 byte length
   - ≤ 5 unique links per post
   - `image_url`, if present, is `https://`
   - first-hand experience only when the row's stored testimony supports it:
     `fabricated_personal_experience` in `none` mode, and in `firsthand` mode the
     provenance checks `experience_detail_unsupported` (a number, duration or
     frequency the testimony does not contain) and
     `experience_attribution_unsupported` (a person the testimony never mentions)
   - no guarantee/absolute language (`amplifier_language`) — refused in both modes
   - no hashtags in the copy unless the operator allowlists a token
     (`hashtag_in_copy`) — Threads makes one tag per post clickable and that tag
     is `topic_tag`, so a hashtag trail only reads as spam
   - a topic tag is present when `require_topic_tag` is on, and it is one the API
     will accept (`topic_tag_missing`, `topic_tag_invalid`). The check applies to
     the root post; the deferred link reply carries none
   - the row's `Affiliate URL` actually appears in some post (stage `thread`
     under two-stage mode defers this to the link reply)
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

## Two-stage publishing (deferred affiliate link)

Default is `publish_mode: single`: the thread and its link go out in one call.
Under `publish_mode: two_stage` the link is deliberately left out of the thread
and posted later, as a reply, so the post can collect views without a commercial
link on it.

```
stage 1  stage: "thread"   the thread                -> Status = link_pending_status
stage 2  stage: "link"     one reply, the link + tag -> Status = Done
```

- `stage: "auto"` (the default) reads the Sheet: an eligible row starts the
  thread, a row sitting in `link_pending_status` gets its reply. `thread` and
  `link` say which half you mean, and are refused if the row disagrees.
- Stage `thread` publishes the copy as given, without requiring the affiliate
  URL — it does not exist in the copy yet. It writes the permalink
  and `link_pending_status` to the row, which is what makes the next call a
  different call.
- Stage `link` takes **exactly one** post in `posts`: the reply. It must carry
  the row's `Affiliate URL`, and it is posted as
  a reply to the last post of the thread (the media id is in the ledger, not in
  the Sheet).
- Both stages need `confirm_publish` and both are escalated to the approval gate.
  The human approves the thread, then approves the link.
- The reply is published with `reply_to_id`, so it appears inside the thread —
  the root post is never republished.

The statuses it can return:

| `status`                            | Meaning                                                                                                                           |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `published_awaiting_link`           | Stage 1 is live; the row is parked in `link_pending_status`.                                                                      |
| `link_reply_published`              | Stage 2 is live; the row is `Done`.                                                                                               |
| `link_published_sheet_write_failed` | The reply is live but the Sheet still says pending. **Do not post it again.** Re-call stage `link` and it only repairs the Sheet. |

If the ledger has no record of the thread, stage `link` refuses: a reply needs
the media id of the post it answers, and only the ledger holds it. Post the reply
by hand in the Threads app and set the row to `Done` in that case.

## Rate limits

Threads allows **250 published posts and 1000 replies per 24 hours** per profile.
A 5-post thread costs 1 post + 4 replies. Hitting the limit returns a rate-limit
error code; the tool reports it and nothing is recorded. Wait — do not retry in a
loop.

## Link cards

Threads builds a preview card for the first URL in a text-only post. That is the
platform's own behaviour, and no API turns it off:

- **`link_attachment` cannot remove the card.** It only chooses _which_ URL gets
  one, and only on a `media_type=TEXT` post. The plugin does not send it, because
  the affiliate URL has to be in the copy anyway and a second URL would only count
  against the per-post link limit.
- The card follows the **first** URL in the post, so the post carrying the
  affiliate link should keep it as that post's only URL.
- Link previews are a text-only feature: an `IMAGE` post carries no link card.
- Threads counts unique URLs per post and rejects a post with more than 5. That
  is the same number as `max_links_per_post`, which refuses the copy before the
  API ever sees it. A `link_attachment` repeating a URL already in the text
  counts once; a different one is one more link.

"Remove the card" is a reasonable thing for a human to ask for, so have the real
answers ready:

- **The value posts never carry a card** — they carry no URL at all. Only the
  link post can show one.
- **An `IMAGE` post suppresses the card entirely.** If the link reply should look
  like a post rather than a link, give that post an image.
- **`publish_mode: two_stage` is the structural answer:** the thread collects its
  views before a link exists anywhere in it, and the card only appears on the
  reply that was already asking for the click.
- Posting that one reply by hand in the app is the remaining option, and it
  leaves the plugin's own accounting behind (`stage: "link"` never runs) — say so
  if the human chooses it.

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
