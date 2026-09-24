# Google Sheets contract

Google Sheets is the business-data source of truth **and** the state lock. There
is no database, and there is no separate queue. Whatever the Sheet says is what is
true.

## Columns

| Col | Field           | Meaning                                                                                                        |
| --- | --------------- | -------------------------------------------------------------------------------------------------------------- |
| A   | `ID`            | Unique product/content identifier. Numeric IDs sort first.                                                     |
| B   | `Product`       | Product name                                                                                                   |
| C   | `Description`   | Operator-written product description — the seller's own framing: **background for the writer, never evidence** |
| D   | `Affiliate URL` | The affiliate URL supplied by the operator                                                                     |
| E   | `Category`      | Product category                                                                                               |
| F   | `Threads URL`   | Published Threads URL. **Blank before publication.**                                                           |
| G   | `Status`        | Current workflow state                                                                                         |

A header row is optional. When A1 is `ID`, the first data row is row 2; otherwise
data starts at row 1. Everything in this skill handles both.

If the operator's table uses a different order, they can remap it with the
`columns` plugin setting — the helpers read whatever it resolves to, so nothing
in the skill needs to change. What the skill must never do is assume a layout the
plugin was not told about.

## Statuses

| Status              | Meaning                     | Eligible to generate? |
| ------------------- | --------------------------- | --------------------- |
| `In Progress`       | Being worked on elsewhere   | No                    |
| `Ready To Generate` | **The only eligible state** | Yes                   |
| `Hold`              | Human paused it             | No                    |
| `Cancel`            | Human rejected it           | No                    |
| `Done`              | Published                   | No                    |

Under `publish_mode: two_stage` there is one more, written by the tool: the
link-pending status (default `Link Pending`) means the thread is live and its
link reply has not been posted yet. It is never eligible and never `Done`, which
is what stops the row from being published twice while it waits.

Only `Ready To Generate` is ever eligible. There is no fallback, no "closest
match", and no case-insensitive approximation. A row whose status is
`ready to generate` (lowercase) is **not** eligible — the comparison is exact.

## Reading

The bundled `google-workspace` skill does the talking. Through it:

```bash
# whole table
$GAPI sheets get <SPREADSHEET_ID> "Sheet1!A1:G"

# one row
$GAPI sheets get <SPREADSHEET_ID> "Sheet1!A14:G14"
```

Or, more conveniently, through this skill's helpers:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/select_candidate.py            # next eligible, JSON
python3 ${HERMES_SKILL_DIR}/scripts/select_candidate.py --full     # next eligible, full row
python3 ${HERMES_SKILL_DIR}/scripts/select_candidate.py --id 12 --full
```

## Writing

**Only two things are ever written by this system.**

### 1. A status change (hold / cancel / resume)

```bash
python3 ${HERMES_SKILL_DIR}/scripts/set_status.py <PRODUCT_ID> Hold
python3 ${HERMES_SKILL_DIR}/scripts/set_status.py <PRODUCT_ID> Cancel
python3 ${HERMES_SKILL_DIR}/scripts/set_status.py <PRODUCT_ID> "Ready To Generate"
```

The script re-reads the row, verifies the ID matches, and writes only the `Status`
cell. It refuses to write if the ID is not found. Never write a status by hand —
always through the script, so the read-modify-write is atomic enough to notice a
mismatch.

### 2. The publish result (only by `threads_publish`)

`Status=Done` plus `Threads URL`. This happens inside the publish tool, after a
confirmed media ID, and nowhere else. **You never write these two fields
yourself.** Under `publish_mode: two_stage` the first half of the publish writes
the `Threads URL` plus the link-pending status instead of `Done`, and the status
only becomes `Done` when the deferred link reply goes out.

## What you must never do to the Sheet

- Edit `ID`, `Product`, `Description`, `Affiliate URL` or `Category`. Those are
  the operator's.
- Clear or rewrite `Threads URL`.
- Change a row's `Status` to `Done` — that is `threads_publish`'s job, and only
  after the posts are actually live.
- Delete rows.
- Touch any other tab or spreadsheet.

## Common situations

| Situation                       | What it means                          | What to do                                                 |
| ------------------------------- | -------------------------------------- | ---------------------------------------------------------- |
| No row has `Ready To Generate`  | Nothing to generate                    | Tell the human. Stop. Do not pick another status.          |
| Two rows share an ID            | Data problem                           | Report it; do not guess which one is meant                 |
| A row has no `Affiliate URL`    | CTA cannot be built                    | `threads_publish` refuses. Ask the operator to fill it in. |
| A row has no `Description`      | Only independent research is available | Research the category, or ask the operator to fill it in   |
| `Threads URL` is already filled | Already published                      | Not eligible. Report it.                                   |
| Status is blank                 | Not eligible                           | Report it. Do not assume it means ready.                   |

## Duplicate-publish protection

`threads_publish` checks three independent things before publishing:

1. `Status` is exactly the eligible value
2. `Threads URL` is empty
3. The plugin's publish ledger has no half-finished record for this ID

The ledger exists for one specific failure: the posts went live but the Sheet
write failed. In that case the next call for the same `product_id` repairs the
Sheet and publishes nothing. If you ever see
`status: "published_sheet_write_failed"`, that is what happened — tell the human
the thread is live, and re-call with the same ID.
