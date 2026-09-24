# Google Sheets setup

The Sheet is the business-data source of truth **and** the workflow state lock.
There is no database anywhere in this system. Whatever the Sheet says is what is
true.

## 1. Create the sheet

A new Google Sheet with one tab (default name `Sheet1`). Row 1 is a header:

|       | A    | B         | C             | D               | E          | F             | G        |
| ----- | ---- | --------- | ------------- | --------------- | ---------- | ------------- | -------- |
| **1** | `ID` | `Product` | `Description` | `Affiliate URL` | `Category` | `Threads URL` | `Status` |

A header row is optional — the loader detects `ID` in A1 and adjusts. Keep the
header anyway; it makes the sheet readable for humans.

### Column semantics

| Column          | Who writes it      | Notes                                                                                                                                                                               |
| --------------- | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ID`            | Operator           | Unique. Numeric IDs sort first, ascending.                                                                                                                                          |
| `Product`       | Operator           | Product name                                                                                                                                                                        |
| `Description`   | Operator           | **Background material, written by the seller's side.** It orients the writer — what the product is, who it is for — and is never the thread's evidence. Keep it factual; see below. |
| `Affiliate URL` | Operator           | Required when `require_affiliate_url` is on (default). Must appear in the published thread.                                                                                         |
| `Category`      | Operator           | Used for category-level framing when product detail is thin                                                                                                                         |
| `Threads URL`   | `threads_publish`  | Blank before publication. Never write it by hand.                                                                                                                                   |
| `Status`        | Operator + scripts | See below                                                                                                                                                                           |

### Example rows

| ID  | Product             | Description                                                               | Affiliate URL           | Category   | Threads URL | Status            |
| --- | ------------------- | ------------------------------------------------------------------------- | ----------------------- | ---------- | ----------- | ----------------- |
| 1   | Power Bank 20000mAh | Matte black, 380g, 22.5W PD, 2 port (USB-A + USB-C), kabel USB-C included | https://shope.ee/abc123 | Power Bank |             | Done              |
| 2   | Wireless Earbuds X  | TWS, BT 5.3, 6 jam per charge, case 24 jam, IPX4, touch control           | https://shope.ee/def456 | Audio      |             | Ready To Generate |
| 3   | Laptop Stand Alu    | Aluminium, lipat, 6 level tinggi, sampai 17 inci, bobot 620g              | https://shope.ee/ghi789 | Aksesoris  |             | In Progress       |
| 4   | Tumbler 1L          | Stainless, tahan 12 jam panas, tutup anti bocor, 340g                     | https://shope.ee/jkl012 | Minuman    |             | Hold              |

Only row 2 is eligible. Everything else is skipped, whatever the request says.

### Writing a good Description

The description is seller-side copy: it tells the writer what the product is and
how it is being sold. It is **not** the evidence the thread is built from — that
comes from independent research (see
`skills/affiliate-threads-generator/references/evidence-sourcing.md`), because
the copy may not rest on the seller's own words.

What a good description does is make the product _checkable_: names, numbers and
materials that can be looked up and confirmed elsewhere.

Good — specific and checkable:

> Matte black, 380g, 22.5W PD, 2 port (USB-A + USB-C), kabel USB-C included.
> Bukan tipe yang bisa charge laptop, cuma HP dan tablet.

Poor — no information:

> Power bank bagus, murah, berkualitas.

The second one leaves the research step with nothing to look up, which pushes the
whole thread down to generic category talk.

## 2. Statuses

| Status              | Set by                 | Meaning                         |
| ------------------- | ---------------------- | ------------------------------- |
| `In Progress`       | Operator               | Being prepared elsewhere        |
| `Ready To Generate` | Operator               | **The only eligible state**     |
| `Hold`              | `set_status.py`        | Paused by the human             |
| `Cancel`            | `set_status.py`        | Rejected by the human           |
| `Done`              | `threads_publish` only | Published, `Threads URL` filled |

Exact match only, case-sensitive. `ready to generate` is not eligible.

With `publish_mode: two_stage` the tool also writes a link-pending status
(default `Link Pending`) between the two publishes, and the Sheet needs nothing
special for it: it is just another value in the same column. See
[configuration.md](configuration.md#deferred-affiliate-links-publish_mode-two_stage).

With `publish_mode: two_stage` the tool also writes a link-pending status
(default `Link Pending`) between the two publishes, and the Sheet needs nothing
special for it: it is just another value in the same column. See
[configuration.md](configuration.md#deferred-affiliate-links-publish_mode-two_stage).

## 3. Authorize the google-workspace skill

The plugin does not implement Google OAuth. It shells out to the bundled
`google-workspace` skill's `google_api.py`, which owns the token.

Ask Hermes:

```
Set up Google Workspace for me.
```

The setup walks through creating a Google Cloud project, enabling the Sheets API,
creating OAuth desktop credentials, and authorizing. The token then auto-refreshes.

Verify:

```bash
hermes chat -q "Read the first 5 rows of my affiliate sheet."
```

## 4. Point the plugin at the sheet

Grab the id from the URL:

```
https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit
                                      └────────── this ──────────┘
```

Add to `$HERMES_HOME/.env`:

```bash
AFFILIATE_SHEET_ID=1AbCdEfGhIjKlMnOpQrStUvWxYz
AFFILIATE_SHEET_TAB=Sheet1
```

Restart the gateway, then:

```bash
hermes chat -q "Run threads_check."
```

The `sheets` and `next_candidate` checks should both pass.

## 5. Manual operations

Read the next eligible candidate:

```bash
# The skill ships inside the plugin; nothing lands in ~/.hermes/skills/.
SKILL_DIR="$HERMES_HOME/plugins/affiliate-threads-generator/skills/affiliate-threads-generator"

python3 "$SKILL_DIR/scripts/select_candidate.py"
```

Hold, cancel or resume:

```bash
python3 "$SKILL_DIR/scripts/set_status.py" 2 Hold
python3 "$SKILL_DIR/scripts/set_status.py" 2 Cancel
python3 "$SKILL_DIR/scripts/set_status.py" 2 "Ready To Generate"
```

`set_status.py` re-reads the row first, verifies the ID matches, and refuses to
set `Done` — that state belongs to `threads_publish`.

## Rules of the road

**Never edit by hand:**

- `Threads URL` — written by the publish tool, after a confirmed media id
- `Status=Done` — same

**Never let the agent edit:**

- `ID`, `Product`, `Description`, `Affiliate URL`, `Category` — those are yours
- Any other tab or spreadsheet

**What the agent may change:** `Status`, via `set_status.py`, for
hold / cancel / resume only.

## Troubleshooting

| Symptom                                 | Cause                                      | Fix                                                                     |
| --------------------------------------- | ------------------------------------------ | ----------------------------------------------------------------------- |
| `no row with ID "2" in Sheet1`          | ID mismatch, or wrong tab                  | Check the tab name; IDs are compared as trimmed strings                 |
| `no spreadsheet configured`             | `AFFILIATE_SHEET_ID` missing               | `hermes config set AFFILIATE_SHEET_ID "<id>"`, then restart the gateway |
| `NOT_AUTHENTICATED`                     | google-workspace not authorized            | Re-run the Google Workspace setup                                       |
| `REFRESH_FAILED`                        | Refresh token revoked                      | Re-authorize google-workspace                                           |
| `Insufficient Permission`               | Sheets scope missing                       | Re-authorize including Sheets                                           |
| `google_api.py could not be found`      | Skill not installed in a standard location | Set `HERMES_GAPI_PATH`                                                  |
| `no row has Status "Ready To Generate"` | Nothing queued                             | That is not an error — set a row to `Ready To Generate`                 |
| Two rows share an ID                    | Data problem                               | Fix the sheet; the agent will refuse rather than guess                  |

## Sharing and permissions

The Sheet only needs to be accessible to the Google account you authorized with
`google-workspace`. It does not need to be public, and it should not be — the
affiliate URLs in it are yours.
