# Affiliate Threads — finish the setup

You are reading this because the operator just installed this plugin. The plugin
is loaded; the pipeline is not ready. Three things have to be true first, and two
of them fail silently if they are skipped.

Work through them in this order, ask before you create anything, then tell the
operator in two or three lines what you did. Nothing you do here publishes
anything.

---

## 1. Schedule the monthly Threads token refresh

**Do this one first, because skipping it fails sixty days from now with no
warning.** A Threads long-lived token is valid for 60 days, and refreshing it
resets the clock. Nothing in this plugin renews it — no code path refreshes a
token on its own, on purpose, because a token write is an operator action. Without
a job, publishing starts failing on day 60 with an auth error while the Sheet
still shows the row as ready, so it reads as a bug rather than an expired
credential.

Check whether it is already handled:

```bash
hermes cron list
```

If a job already refreshes this token, say so and go to step 2.

Otherwise tell the operator, in one or two lines, that the token lasts 60 days,
that nothing renews it, and that the pipeline stops publishing on day 60 unless
this job exists. Then offer to set it up now. The plugin's own copy of the recipe
is beside this file: `docs/threads-app-setup.md`, section "Automate it" — it has
the short script the job runs and the create command. Read it before you create
anything.

The command, once the script sits at `$HERMES_HOME/scripts/refresh-threads-token.sh`:

```bash
hermes cron create "0 9 1 * *" \
  "Refresh the Threads token" \
  --no-agent \
  --script refresh-threads-token.sh \
  --deliver telegram \
  --name "threads-token-refresh"
```

Three details decide whether it keeps working:

- `--no-agent` runs the shell script with no model in the loop and no prompt. It
  prints nothing when it succeeds, so a silent month is the good outcome — a
  delivered message means it needs attention.
- The job needs `THREADS_ACCESS_TOKEN` in `terminal.env_passthrough`. A
  `no_agent` script runs as a child with a sanitized environment, so `.env` is not
  inherited by default; without that line the job fails on every tick.
- The refresh writes the new token into `~/.hermes/.env`. A running gateway keeps
  the value it read at startup, so `hermes gateway restart` is what makes it live.

Confirm the token's state at any time, without waiting for the schedule:

```bash
SKILL_DIR="$HERMES_HOME/plugins/affiliate-threads-generator/skills/affiliate-threads-generator"
python3 "$SKILL_DIR/scripts/threads_token.py" status
```

`days_remaining` near 60 means a refresh ran recently.

This is the one job nobody notices is missing. `hermes plugins install` never
schedules anything, and a plugin's bundled skill does not produce a `/suggestions`
entry — Hermes turns a `blueprint:` frontmatter block into a suggestion for skills
installed from the skills hub, and this one ships inside the plugin. So the job is
created here, or it does not exist.

---

## 2. Schedule generation

The other job, same plugin. It runs the pipeline and delivers a preview; it never
publishes, because publishing needs a human reply.

```bash
hermes cron create "0 8 * * 0,1,3,5" \
  "Load the skill affiliate-threads-generator:affiliate-threads-generator with skill_view, then generate the next affiliate thread for Meta Threads and send me the preview. Process exactly one candidate, then stop and wait for a human decision." \
  --name "affiliate-threads-generator" \
  --deliver telegram
```

Monday, Wednesday, Friday and Sunday at 08:00 Asia/Jakarta — the host's local
time, so check `date '+%Z %z'` and set `TZ=Asia/Jakarta` for the gateway if the
host runs on UTC. `docs/cron-setup.md` covers that, the Telegram topic that makes
previews replyable, and what a scheduled run does and does not do.

---

## 3. Schedule the weekly metrics fetch

The third job. Every Monday at 10:00 Asia/Jakarta it pulls Threads insights for
posts published in the last 30 days — lifetime views/likes/replies/reposts/
quotes/shares for each thread's root post, plus the account's link-click totals
for the week — and appends them to a `Metrics` tab in the same spreadsheet. It
never publishes and never touches the candidate table.

Check whether it is already handled:

```bash
hermes cron list
```

If a metrics job already exists, say so and move on. Otherwise two things have
to be true before it is useful:

- **A `Metrics` tab in the spreadsheet.** Create it once by hand (a different
  name works if the `metrics_tab` setting is changed to match). The first run
  writes the header row; `doctor.py`'s `metrics_tab` check confirms it exists.
- **A token with `threads_manage_insights`.** Fresh installs authorize with the
  three scopes listed in `docs/threads-app-setup.md`. A token that predates that
  scope cannot gain it — the operator has to authorize again; that doc has the
  steps.

Then offer to create the job:

```bash
hermes cron create "0 10 * * 1" \
  "Fetch Threads insights for recently published posts" \
  --no-agent \
  --script fetch-threads-metrics.sh \
  --deliver telegram \
  --name "threads-metrics"
```

The script it runs sits at `$HERMES_HOME/scripts/fetch-threads-metrics.sh` —
`docs/cron-setup.md` has its body, and the `terminal.env_passthrough` note that
decides whether the job works at all. Unlike the token refresh (where silence is
the good outcome), this job's delivered message **is** the weekly report: posts
fetched, the top post, and the week's link clicks. Before the first Monday, run
it once by hand:

```bash
SKILL_DIR="$HERMES_HOME/plugins/affiliate-threads-generator/skills/affiliate-threads-generator"
python3 "$SKILL_DIR/scripts/fetch_metrics.py" --dry-run
```

---

## 4. Prove the wiring before the first real run

```bash
SKILL_DIR="$HERMES_HOME/plugins/affiliate-threads-generator/skills/affiliate-threads-generator"
python3 "$SKILL_DIR/scripts/doctor.py"
```

Every line should be `✓`. The `threads_api` line prints the token's validity and
days remaining, `cron_job` confirms the generation job, `token_refresh_job`
confirms the job from step 1, and `metrics_scope` / `metrics_tab` / `metrics_job`
confirm the job from step 3 — a `✗` on any of them names the fix in its `→` hint.
