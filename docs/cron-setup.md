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

## Option A — let the install note create it

`hermes plugins install` ends by showing the plugin's
[`after-install.md`](../after-install.md), and Hermes hands that note to the agent
as instructions. It asks the agent to offer both jobs — this one and the monthly
token refresh — with the exact commands, so a fresh install can end with
everything scheduled and nothing left to remember.

The skill's `blueprint:` frontmatter is not a second path to the same thing. Hermes
turns a blueprint into a `/suggestions` entry only for a skill installed from the
skills hub; this skill ships inside the plugin and is never copied into
`~/.hermes/skills/`, so nothing offers it there. Option B below is the scheduling
step either way.

## Option B — create it from the CLI

```bash
hermes cron create "0 8 * * 0,1,3,5" \
  "Load the skill affiliate-threads-generator:affiliate-threads-generator with skill_view, then generate the next affiliate thread for Meta Threads and send me the preview. Process exactly one candidate, then stop and wait for a human decision." \
  --name "affiliate-threads-generator" \
  --deliver telegram
```

The prompt names the skill rather than attaching it with `--skill`: the skill
ships inside the plugin under a namespaced name, while `--skill` resolves bare
names against the skills installed in `$HERMES_HOME/skills/`. Naming it in the
prompt also keeps the job self-contained, which a fresh session needs anyway.

Or in natural language, in any session:

```
Every Monday, Wednesday, Friday and Sunday at 8am, generate the next affiliate
thread and send me the preview on Telegram.
```

## Option C — create it from the Desktop or dashboard

The cron editor accepts the same expression, prompt and delivery target. Put the
skill name in the prompt as in Option B.

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
SKILL_DIR="$HERMES_HOME/plugins/affiliate-threads-generator/skills/affiliate-threads-generator"
python3 "$SKILL_DIR/scripts/doctor.py"
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
why the prompt above names the skill and spells out "exactly one candidate, then
stop". The skill supplies everything else.

---

## The second job: the monthly token refresh

The generation job is the one this plugin ships a blueprint for. There is a
second job worth having, and it has no model in it at all.

A Threads long-lived token lasts **60 days**. Refreshing resets the clock, and it
works at any point — even a day after the token was issued — so a monthly refresh
is plenty, and nothing expires because a human forgot:

```bash
hermes cron create "0 9 1 * *" \
  "Refresh the Threads token" \
  --no-agent \
  --script refresh-threads-token.sh \
  --deliver telegram \
  --name "threads-token-refresh"
```

`--no-agent` is the point. The job runs a shell script: no prompt, no model call,
no tools, nothing to approve. On success the script prints nothing, so the job
delivers nothing — a silent month is the good outcome, and any message means it
needs you.

The script body, and the one line this job needs that the generation job does
not, are in [threads-app-setup.md](threads-app-setup.md#automate-it). Read both
before scheduling it.

Two ways this job goes wrong, both of them quiet for a month:

- **`THREADS_ACCESS_TOKEN is not set`, delivered on every tick.** A `no_agent`
  script still runs as a child with a sanitized environment, so `.env` is not
  inherited. Add the variable to `terminal.env_passthrough` — the YAML block on
  the setup page.
- **The refresh succeeds, and publishing still fails on an expired token.** The
  job writes the new value to `~/.hermes/.env`, while a running gateway keeps
  serving the old one it read at start. Restart it (`hermes gateway restart`)
  after the tick.

Check where the token stands at any time, without waiting for the schedule:

```bash
SKILL_DIR="$HERMES_HOME/plugins/affiliate-threads-generator/skills/affiliate-threads-generator"
python3 "$SKILL_DIR/scripts/threads_token.py" status
```

`days_remaining` back near 60 is what a healthy run looks like. The manual path
and the rotation reasoning are in [credentials.md](credentials.md#rotation).

`doctor.py` reports both jobs: `cron_job` for the generation schedule and
`token_refresh_job` for this one, so a refresh job that was never created shows up
red with the command that fixes it.

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

| Symptom                                                | Cause                                                                                     | Fix                                                                                 |
| ------------------------------------------------------ | ----------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Job never fires                                        | Scheduler not ticking                                                                     | `hermes cron status`; then `hermes gateway restart`                                 |
| Fires at the wrong hour                                | Host timezone                                                                             | Set `TZ=Asia/Jakarta` on the gateway service                                        |
| `blocked_config`                                       | A preflight check failed (missing credential, missing skill env, unknown delivery target) | Read the alert — it names the exact problem. No tokens were spent.                  |
| Job runs but ignores the skill                         | The job's prompt does not name it                                                         | Include `affiliate-threads-generator:affiliate-threads-generator` in the job prompt |
| Preview arrives but replies start a new session        | Delivery is not continuable                                                               | Set `cron.mirror_delivery: true` or `--attach-to-session`                           |
| Preview arrives in the main DM and replies are refused | Telegram topic mode lobby                                                                 | Set `TELEGRAM_CRON_THREAD_ID`                                                       |
| Job fires but produces no preview                      | Delivery failure                                                                          | `hermes cron doctor`, `hermes cron runs affiliate-threads-generator`                |
| Overdue and never fired                                | Gateway was down through the slot                                                         | `hermes cron run affiliate-threads-generator`, then check the gateway service       |

`hermes cron doctor` is read-only and exits non-zero while any finding stands —
useful as a watchdog.
