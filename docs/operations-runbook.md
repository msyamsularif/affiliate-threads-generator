# Operations runbook

## The mental model

```
AI creates and reasons.  Code controls and validates.  Human approves.
Threads publishes.       Google Sheets records the business state.
```

Four things can be true at once, and knowing which is which is most of operating
this system:

| Layer                   | Lives in                                  | Who can change it                                           |
| ----------------------- | ----------------------------------------- | ----------------------------------------------------------- |
| Business state          | Google Sheets                             | The operator, `set_status.py`, and `threads_publish` (once) |
| Content decisions       | The model's judgement                     | The model                                                   |
| The publish side effect | `threads_publish`, in code                | Nobody but that tool                                        |
| Approval                | Hermes' approval gate + the human's reply | The human                                                   |

If something went wrong, the first question is always: **which layer?**

---

## Daily / weekly rhythm

Nothing needs doing in the normal case. Generation runs Mon/Wed/Fri/Sun 08:00
Asia/Jakarta, delivers a preview, and waits.

The operator's job is two things:

1. Keep `Ready To Generate` rows stocked in the Sheet.
2. Answer the preview: `approve`, `hold`, `cancel`, or `regenerate <what to
change>`.

Everything else is exception handling.

---

## Health check

```bash
SKILL_DIR="$HERMES_HOME/plugins/affiliate-threads-generator/skills/affiliate-threads-generator"
python3 "$SKILL_DIR/scripts/doctor.py"
```

From any session, `/affiliate-threads status` runs the same read-only preflight
without spending a model turn.

Eight checks. Any `✗` comes with a `→` hint.

```
  ✓ plugin: found at .../plugins/affiliate-threads-generator (v1.0.1)
  ✓ settings: spreadsheet=... tab=Sheet1 eligible='Ready To Generate' disclosure=required
  ✓ threads_api: @yourhandle (id ...); token valid=True, expires in 58.4 days
  ✓ sheets: 12 data row(s) in Sheet1; google_api=...
  ✓ next_candidate: ID 3 — Wireless Earbuds X (row 5)
  ✓ bundled_skill: .../plugins/affiliate-threads-generator/skills/affiliate-threads-generator/SKILL.md
  ✓ cron_job: affiliate-threads-generator [0 8 * * 0,1,3,5] next=... enabled=True
  ✓ unsynced_publishes: none
```

Run it with `--format json` for monitoring, or `--no-network` when the host is
offline.

---

## The approval gate

There are two independent confirmations before anything reaches Threads:

1. **The human's own reply** in the conversation. The model sets
   `confirm_publish: true` only after that.
2. **Hermes' approval gate**, triggered by the plugin's `pre_tool_call` hook,
   which escalates every `threads_publish` call. This one the model cannot
   bypass — it is runtime behaviour, not an instruction.

To see what the gate will show, run the doctor or just look at the copy in the
preview. To disable the second gate:

```yaml
plugins:
  entries:
    affiliate-threads-generator:
      settings:
        require_approval_prompt: false
```

**Think before doing that.** The gate exists precisely because an instruction to
the model is not a guarantee. If it is noisy in practice, the better fix is to
make the preview the review artifact and let the gate be the final "yes".

---

## Common incidents

### "It says the row is not eligible"

`threads_publish` re-reads the Sheet and found a status other than
`Ready To Generate`. The error names the current status and what it means.

Most often: the human replied `hold` or `cancel` in an earlier turn, or the row
was already published. The tool is correct. **Do not retry, and do not set the
status back yourself** — ask the operator.

### "Published but the Sheet still says Ready To Generate"

Look at the return value:

```json
{
  "ok": true,
  "status": "published_sheet_write_failed",
  "threads_url": "https://..."
}
```

**The thread is live.** The Sheet write failed after the publish succeeded.

Recovery — call `threads_publish` again with the same `product_id`:

```
Publish product ID 12 again — the thread is already live, I just need the Sheet fixed.
```

The tool finds the ledger record, skips publishing entirely, and writes the Sheet.
It returns `{"status": "sheet_resynced"}`.

The doctor's `unsynced_publishes` check surfaces this case, so it will not go
unnoticed.

### "The token expired"

Symptoms: `threads_api` fails in the doctor, or publish returns an auth error.

```bash
SKILL_DIR="$HERMES_HOME/plugins/affiliate-threads-generator/skills/affiliate-threads-generator"
python3 "$SKILL_DIR/scripts/threads_token.py" status
python3 "$SKILL_DIR/scripts/threads_token.py" refresh --write-env
hermes gateway restart
```

If `refresh` also fails, the token is beyond saving — re-run the authorization
flow in [threads-app-setup.md](threads-app-setup.md) and `exchange` a fresh
short-lived token.

A long-lived token lasts 60 days and refreshing resets the clock. Set up the
monthly refresh job in [threads-app-setup.md](threads-app-setup.md#automate-it)
so this never becomes an incident.

### "Publishing is refused by the guardrails"

The error lists each violation with a code. The hard ones:

| Code                               | Fix                                                |
| ---------------------------------- | -------------------------------------------------- |
| `missing_disclosure`               | Add a disclosure line to the final post            |
| `affiliate_url_not_in_thread`      | Put the row's affiliate URL in a post              |
| `fabricated_personal_experience`   | Rewrite the flagged sentence as an observation     |
| `post_too_long`                    | Shorten it; emoji count as their UTF-8 byte length |
| `too_many_links`                   | Threads allows 5 unique links per post             |
| `too_few_posts` / `too_many_posts` | 3-6 posts                                          |
| `affiliate_url_missing_from_row`   | The Sheet row has no affiliate URL                 |

Then show a **new** preview and get a **new** approval — the previous approval was
for different copy.

The soft ones are `warnings`, and they never block. They are worth reading anyway,
because they are the difference between a preview that reads like a person wrote
it and one that reads like a template:

| Warning                       | Means                                                         |
| ----------------------------- | ------------------------------------------------------------- |
| `excessive_signposting`       | The copy announces what it is about to do ("mari kita bahas") |
| `repeated_transition_density` | Too many "Jadi, ..." / "Makanya, ..." sentence openers        |
| `excessive_enumeration`       | "Pertama, ... Kedua, ..." — prose turned into a list          |
| `product_detail_density`      | Spec dumping: too many number-plus-unit tokens in one thread  |
| `generic_phrase`              | An affiliate cliché with nothing specific behind it           |
| `product_overexposed`         | The product name carries the thread instead of supporting it  |

Thresholds are configurable and `0` disables a signal — see
[configuration.md](configuration.md#structural-soft-signals). The prose audit
itself is the external antislop skills; see
[antislop-integration.md](antislop-integration.md).

### "Shopee blocked the fetch"

Expected. This is not an incident. The research step is description-first by
design; the Shopee page is a bonus, never a dependency. If the model reports this
as a failure, it has misread the skill — point it at
`references/evidence-sourcing.md`.

### "The cron job stopped firing"

```bash
hermes cron status                              # is the scheduler ticking?
hermes cron list                                # what is the job's state?
hermes cron doctor                              # what is wrong, per job
hermes cron runs affiliate-threads-generator     # attempt ledger
hermes gateway restart
```

| Finding                            | Meaning                                                                                                    |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `blocked_config`                   | A preflight check failed. The alert names it. No tokens were spent.                                        |
| `Overdue:` and the gateway is down | The scheduler stopped ticking. Restart the gateway.                                                        |
| `last_fire_error`                  | The fire never reached the runner. Restart the gateway through its supervisor.                             |
| `delivery_failed`                  | The run succeeded but the preview never reached Telegram. Check the bot token and `TELEGRAM_HOME_CHANNEL`. |
| The run ignores the skill          | The job's prompt does not name it                                                                          | Include `affiliate-threads-generator:affiliate-threads-generator` in the job prompt |

### "It published the wrong thing"

This should be impossible, and if it happened, the interesting question is which
check failed:

1. Was `Status` still `Ready To Generate`? If not, the publish should have been
   refused — that would be a bug worth reporting.
2. Did the human actually approve _this_ copy? Check the audit trail:

```bash
hermes logs --level INFO | grep "audit threads_publish"
```

3. Was the approval for a different product, earlier in the conversation? The
   review context is the Product ID on screen, and the model is required to ask
   when it is ambiguous.

There is no undo. Deleting the post is a manual Threads action. Fix the Sheet
afterwards: set `Status=Done` and the `Threads URL` so the row is not picked up
again — or use `threads_publish` once, which does exactly that.

### "The agent wants to publish but nobody approved"

It must not. If the model asks "should I publish?" in a way that makes yes the
default, or sets `confirm_publish: true` without approval, that is a process
failure. Two things stop it anyway:

- the approval gate (`pre_tool_call`)
- `confirm_publish` in the tool

Report it, and consider raising the model's reasoning effort or re-reading the
skill's approval section with it.

---

## Audit trail

Two places, both durable.

### The log

```bash
hermes logs --level INFO | grep "audit"
```

Every `threads_publish` and `threads_check` call, with product id, outcome, stage
and duration.

### Plugin state

The last 50 entries are kept in plugin state under `publish_audit`, alongside the
publish ledger under `publish_ledger`, both inside `$HERMES_HOME/plugin-data/`:

```
$HERMES_HOME/plugin-data/
├── agent-plugin-affiliate-threads-generator-<hash>/state.json   # at runtime
└── affiliate-threads-generator/state.json                       # skill scripts
```

Which of the two holds the current ledger depends on which writer ran last, and
the directory is not derivable from the plugin name — Hermes namespaces
`ctx.state` for native plugins. Read the payload, not the path (that is what
`doctor.py` does), or ask `threads_check` / `/affiliate-threads status` for the
live answer.

```json
{
  "publish_ledger": {
    "12": {
      "product_id": "12",
      "media_ids": ["ABC123", "DEF456", "GHI789"],
      "permalink": "https://www.threads.net/@you/post/ABC123",
      "posts_count": 3,
      "published_at": "2026-09-23T01:00:12+00:00",
      "sheet_synced": true,
      "sheet_synced_at": "2026-09-23T01:00:13+00:00"
    }
  }
}
```

The ledger is not a second database. It holds one fact the Sheet cannot hold
safely: whether a publish succeeded before the Sheet write landed. Do not edit it
by hand; use the tools.

---

## Backups

| What                          | Why                      | How                                              |
| ----------------------------- | ------------------------ | ------------------------------------------------ |
| The Google Sheet              | It is the business state | Google's version history, plus a periodic export |
| `$HERMES_HOME/.env`           | Tokens                   | Your secret manager — not a git repo             |
| `$HERMES_HOME/plugin-data/`   | The publish ledger       | Included in Hermes' quick backups                |
| `$HERMES_HOME/cron/jobs.json` | The schedule             | Included in Hermes' quick backups                |

The Sheet's version history is the real safety net: any accidental `Status` write
is one revert away.

---

## Change management

Before changing anything in `plugin.yaml`, `config.py` or `guardrails.py`:

```bash
pytest                       # the deterministic layer is covered by tests
ruff check .
hermes plugins doctor "$HERMES_HOME/plugins/affiliate-threads-generator" --ci
```

Then reinstall and re-run the doctor:

```bash
hermes plugins update affiliate-threads-generator && hermes gateway restart
SKILL_DIR="$HERMES_HOME/plugins/affiliate-threads-generator/skills/affiliate-threads-generator"
python3 "$SKILL_DIR/scripts/doctor.py"
```

### If you edit the skill

There is one copy and it lives in the plugin directory, so the skill moves with
the code it runs beside:

```bash
hermes plugins update affiliate-threads-generator
```

That is the whole refresh — there is no separate skill install to keep in step.

### If you change the guardrails

`validate_thread.py` imports the plugin's own `guardrails.py`, so the lint and the
publish-time check cannot drift apart. That is deliberate — do not reimplement a
rule in the script.

---

## Escalation thresholds

| Situation                                           | Response                                                                                                    |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| One failed generation run                           | Ignore. Read the next preview.                                                                              |
| Two consecutive failures                            | Run `doctor.py`.                                                                                            |
| Publish fails twice with the same API error         | Treat as a token or scope problem. Check `threads_token.py status`.                                         |
| A publish that went live with a Sheet write failure | Repair immediately with `threads_publish` on the same product id.                                           |
| Any publish that nobody approved                    | Stop the pipeline (`hermes cron pause affiliate-threads-generator`), preserve the audit trail, investigate. |
| Rate limit hit                                      | Wait. 250 posts / 1000 replies per 24h. Do not retry in a loop.                                             |
