# Cron setup

The schedule is a **trigger only**. It runs the same pipeline a manual request
runs, and it never publishes — publishing needs a human reply.

Required schedule: **Monday, Wednesday, Friday and Sunday at 08:00 Asia/Jakarta**.

Cron expression: `0 8 * * 0,1,3,5` (0 = Sunday).

---

## Before you start: the timezone

Hermes' scheduler uses the host's local time. Verify:

```bash
date '+%Z %z'
```

You want `WIB +0700`. If the host is on UTC, `0 8 * * 0,1,3,5` fires at 15:00
Jakarta.

**Fix it on the host** — set `TZ=Asia/Jakarta` for the gateway process. For a
systemd user service:

```bash
systemctl --user edit hermes-gateway
```

```ini
[Service]
Environment="TZ=Asia/Jakarta"
```

```bash
systemctl --user daemon-reload
systemctl --user restart hermes-gateway
```

Then confirm:

```bash
hermes cron list
hermes cron status
```

`cron status` prints the next run's actual instant, so you can check the offset
directly.

---

## Option A — accept the blueprint suggestion (recommended)

The skill declares a blueprint in its frontmatter. Installing it registers a
_suggested_ job; nothing is scheduled until you accept.

In any session:

```
/suggestions
/suggestions accept 1
```

That creates the job through the same `cron.jobs.create_job` path as the CLI —
there is no second scheduler.

## Option B — create it from the CLI

```bash
hermes cron create "0 8 * * 0,1,3,5" \
  "Generate the next affiliate thread for Meta Threads and send me the preview. Process exactly one candidate, then stop and wait for a human decision." \
  --skill affiliate-threads-generator \
  --name "affiliate-threads-generator" \
  --deliver telegram
```

Or in natural language, in any session:

```
Every Monday, Wednesday, Friday and Sunday at 8am, generate the next affiliate
thread and send me the preview on Telegram.
```

## Option C — create it from the Desktop or dashboard

The cron editor accepts the same expression, skill attachment, prompt and
delivery target.

---

## Recommended hardening

### Deliver to a dedicated Telegram topic

If Telegram topic mode is on, the root DM is reserved as a system lobby and you
cannot reply to a cron message that lands there. Point cron at a topic:

1. In the Telegram bot DM, create a topic named `Cron`.
2. Long-press the topic header → Copy link; the trailing integer is the topic id.
3. Add to `$HERMES_HOME/.env`:

```bash
TELEGRAM_CRON_THREAD_ID=12345
```

Replies to the delivered preview now land in that topic's session, so the review
context survives and you can reply `approve` directly to it.

### Make the delivery continuable

By default a cron delivery is fire-and-forget: it is sent, but it does not live in
the conversation history. Reply to it and the agent has no record of what it said
— which would destroy the review context.

Turn it on globally:

```yaml
# $HERMES_HOME/config.yaml
cron:
  mirror_delivery: true
```

Or per job:

```
/cron edit affiliate-threads-generator --attach-to-session
```

With this on, the delivered preview is seeded into a thread's session and your
reply continues with full context. **Do this** — the whole approve/hold/cancel
flow depends on the preview being in context.

### Limit the toolset

Generation needs the web, file and skills toolsets. It does not need `browser` or
`delegation`, and carrying them into every run bloats the tool schema on every
model call.

```bash
hermes cron edit affiliate-threads-generator --toolsets web,file,skills
```

### Keep the agent out of scheduling

By default a cron-launched agent cannot create or edit cron jobs. Leave
`cron.allow_agent_scheduling: false` (the default). This pipeline has no reason to
schedule itself.

---

## Verify

```bash
hermes cron list
```

```
affiliate-threads-generator  0 8 * * 0,1,3,5  telegram  enabled
  skills: affiliate-threads-generator
  next: 2026-09-27 08:00:00+07:00
```

Run it once immediately without waiting for the slot:

```bash
hermes cron run affiliate-threads-generator
```

Or from a session: `/cron run affiliate-threads-generator`.

You should receive a preview with a Product ID, and **nothing should be
published**. Check the Sheet: the row's `Status` is unchanged.

Also run the setup doctor, which verifies the job exists and is enabled:

```bash
python3 "$HERMES_HOME/skills/affiliate-threads-generator/scripts/doctor.py"
```

---

## What the scheduled run does and does not do

| Does                                     | Does not                         |
| ---------------------------------------- | -------------------------------- |
| Re-reads the Sheet                       | Publish                          |
| Picks exactly one eligible candidate     | Touch the Sheet's Status         |
| Researches, scores angles, plans, writes | Fall back to a different status  |
| Runs the reviews and the lint            | Process a second candidate       |
| Delivers the preview to Telegram         | Act on a reply it never received |

If nothing is eligible, the run says so and stops. That is the correct outcome,
not a failure.

The run is a **fresh session**, so the prompt has to be self-contained — which is
why the prompt above spells out "exactly one candidate, then stop". The attached
skill supplies everything else.

---

## Lifecycle

```bash
hermes cron pause affiliate-threads-generator     # stop scheduling, keep the job
hermes cron resume affiliate-threads-generator
hermes cron edit affiliate-threads-generator --schedule "0 8 * * 1,3,5"
hermes cron remove affiliate-threads-generator
hermes pause                                     # global emergency stop
hermes resume
```

`hermes pause` is the global kill switch: while it is engaged no scheduled fire
starts, through any door. Manual runs still execute — that is an operator
override.

---

## Troubleshooting

| Symptom                                                | Cause                                                                                     | Fix                                                                          |
| ------------------------------------------------------ | ----------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Job never fires                                        | Scheduler not ticking                                                                     | `hermes cron status`; then `hermes gateway restart`                          |
| Fires at the wrong hour                                | Host timezone                                                                             | Set `TZ=Asia/Jakarta` on the gateway service                                 |
| `blocked_config`                                       | A preflight check failed (missing credential, missing skill env, unknown delivery target) | Read the alert — it names the exact problem. No tokens were spent.           |
| `skill not found`                                      | Standalone skill copy missing                                                             | `./install.sh --skill-only`                                                  |
| Preview arrives but replies start a new session        | Delivery is not continuable                                                               | Set `cron.mirror_delivery: true` or `--attach-to-session`                    |
| Preview arrives in the main DM and replies are refused | Telegram topic mode lobby                                                                 | Set `TELEGRAM_CRON_THREAD_ID`                                                |
| Job fires but produces no preview                      | Delivery failure                                                                          | `hermes cron doctor`, `hermes cron runs affiliate-threads-generator`          |
| Overdue and never fired                                | Gateway was down through the slot                                                         | `hermes cron run affiliate-threads-generator`, then check the gateway service |

`hermes cron doctor` is read-only and exits non-zero while any finding stands —
useful as a watchdog.
