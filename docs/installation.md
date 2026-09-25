# Installation

## Prerequisites

| Requirement                                      | Why                                                   |
| ------------------------------------------------ | ----------------------------------------------------- |
| Hermes Agent, gateway running                    | The whole runtime: agent loop, Telegram, cron, memory |
| Telegram configured for Hermes                   | The only user-facing control surface                  |
| The bundled `google-workspace` skill, authorized | Google Sheets is the business-data source of truth    |
| A Meta app with the Threads use case             | Publishing                                            |
| A Google Sheet with the candidate table          | See [google-sheets-setup.md](google-sheets-setup.md)  |

## 1. Install the plugin

```bash
hermes plugins install msyamsularif/affiliate-threads-generator --enable
```

There is no installer script and nothing to clone by hand: the repository _is_
the plugin, and Hermes clones it into
`$HERMES_HOME/plugins/affiliate-threads-generator/` itself. `--enable` is what
makes the install prompt for the credentials the plugin cannot run without —
with their description, a link to the Meta app console, and the token masked as
you type. Values are stored in Hermes' credential store; you never edit a file,
and nothing is echoed back.

That one command is the whole install. The plugin is a bundle — it carries its
own tools, hooks, skill and slash command, and Hermes loads all of them from the
single directory it cloned.

| What                                                                                      | Where it lands                                      |
| ----------------------------------------------------------------------------------------- | --------------------------------------------------- |
| Two tools, three hooks, and the `/affiliate-threads` command                              | `$HERMES_HOME/plugins/affiliate-threads-generator/` |
| The bundled skill, reachable as `affiliate-threads-generator:affiliate-threads-generator` | the same directory, loaded by Hermes; never copied  |

Nothing is written to `$HERMES_HOME/skills/`, so there is no second copy to
install, update, or let drift.

Confirm it loaded:

```bash
hermes plugins list
```

You should see the plugin with two tools and three hooks. If it does not appear:

```bash
HERMES_PLUGINS_DEBUG=1 hermes plugins list
```

If it appears as _disabled_ naming a variable, the prompt was skipped — set it
with `hermes config set` (step 4) and re-enable.

Restart the gateway so the new tools are picked up:

```bash
hermes gateway restart
```

### Developing against a local checkout

To point Hermes at a working tree instead of a clone:

```bash
git clone https://github.com/msyamsularif/affiliate-threads-generator.git \
  "$HERMES_HOME/plugins/affiliate-threads-generator"
hermes plugins enable affiliate-threads-generator
```

## 2. Reaching the skill — there is nothing else to install

The skill ships inside the plugin, which registers it under a namespaced name:
`affiliate-threads-generator:affiliate-threads-generator`. Three ways in, all of
them live on a fresh install:

| You want to                            | Do this                                                                                                                                                       |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Generate a thread                      | Say so — "Buatkan content berikutnya." The plugin injects one line naming the skill whenever a turn looks like Affiliate Threads work, so the model loads it. |
| Check the wiring by hand               | `/affiliate-threads status` in any session — CLI, Telegram, Discord                                                                                           |
| Load it explicitly, or from a cron job | `skill_view("affiliate-threads-generator:affiliate-threads-generator")`                                                                                       |

A plugin skill is kept out of the system prompt's skill index and cannot be
edited with `skill_manage` — it is read-only, versioned with the code it belongs
to. That is exactly why the plugin also carries the pointer hook and the command:
without them, a bundled skill would be reachable only by someone who already knew
its name.

To stop the model seeing the pointer at all:

```yaml
# $HERMES_HOME/config.yaml
plugins:
  entries:
    affiliate-threads-generator:
      settings:
        announce_skill: false
```

Cron needs one thing from you: a prompt that names the skill. See
[cron-setup.md](cron-setup.md).

## 3. Validate the plugin

```bash
hermes plugins doctor "$HERMES_HOME/plugins/affiliate-threads-generator" --ci
```

This runs the same discovery, manifest parsing, import, `register(ctx)` and hook
registry that Hermes itself uses, and exits non-zero on any error. It also blocks
outbound sockets during registration, so a plugin that phones home at import time
fails here.

## 4. Credentials

Normally step 1 already collected what is needed. This section is for changing a
value later, or for skipping the prompt on purpose.

**Do not edit `.env` by hand, and never paste a token into a chat message.**
Hermes owns the credential lifecycle; the plugin declares the names through
`requires_env` / `optional_env` so Hermes knows what to ask for and where to put
it.

```bash
# Let Hermes ask — load the skill in the local CLI (ask for content) and it
# prompts for anything still unset.

# Or set one explicitly. Because these names are registered, Hermes routes the
# value to the credential store rather than config.yaml:
hermes config set THREADS_ACCESS_TOKEN "THQW..."
hermes config set AFFILIATE_SHEET_ID "1AbCdEf..."

# Or use the Desktop app: Capabilities → Plugins → the plugin's gear icon.
# Or a secret manager — Bitwarden, 1Password, or any CLI vault.
```

The plugin uses four variables:

| Variable               | Prompted at install | Secret? | Needed for                        |
| ---------------------- | ------------------- | ------- | --------------------------------- |
| `THREADS_ACCESS_TOKEN` | **yes** (masked)    | **yes** | Publishing                        |
| `AFFILIATE_SHEET_ID`   | **yes**             | no      | Reading candidates                |
| `THREADS_USER_ID`      | no                  | no      | Optional; resolved from `GET /me` |
| `AFFILIATE_SHEET_TAB`  | no                  | no      | Optional; defaults to `Sheet1`    |

The first two gate loading — without them the plugin does not load, and neither
does the bundled skill. The other two have working defaults and are declared only
so they appear in the config UI. If you would rather generate and preview before
wiring publishing, see
[credentials.md](credentials.md#the-one-consequence-worth-knowing).

On Telegram or Discord the install prompt is replaced by local setup guidance — a
secret is never collected in-band, because it would end up in the conversation
history and the session database.

See [threads-app-setup.md](threads-app-setup.md) for obtaining a token, and
[credentials.md](credentials.md) for the full mechanism — including where each
kind of value belongs (`plugin-data/` for state, `config.yaml` for settings, the
credential store for secrets) and why the standalone scripts need these in the
_environment_ rather than only as plugin settings.

## 5. Verify end to end

```bash
hermes chat -q "Run the affiliate-threads-generator doctor script."
```

Or directly:

```bash
SKILL_DIR="$HERMES_HOME/plugins/affiliate-threads-generator/skills/affiliate-threads-generator"
python3 "$SKILL_DIR/scripts/doctor.py"
```

A healthy setup looks like:

```
  ✓ plugin: found at .../plugins/affiliate-threads-generator (v1.1.2)
  ✓ settings: spreadsheet=... tab=Sheet1 eligible='Ready To Generate' topic_tag=required
  ✓ plugin_settings: 3 setting(s) read from ~/.hermes/config.yaml
  ✓ threads_api: @yourhandle (id 1234567890); token valid=True, expires in 58.4 days
  ✓ sheets: 12 data row(s) in Sheet1; google_api=/.../google_api.py
  ✓ next_candidate: ID 3 — Wireless Earbuds X (row 5)
  ✓ bundled_skill: .../plugins/affiliate-threads-generator/skills/affiliate-threads-generator/SKILL.md
  ✓ cron_job: affiliate-threads-generator [0 8 * * 0,1,3,5] next=... enabled=True
  ✓ token_refresh_job: threads-token-refresh [0 9 1 * *] next=... enabled=True
  ✓ unsynced_publishes: none

10/10 checks passed.
```

Any `✗` line comes with a `→` hint telling you exactly what to fix.

## 6. Schedule generation

See [cron-setup.md](cron-setup.md). A fresh `hermes plugins install` shows the
plugin's [after-install.md](../after-install.md), which the agent reads as
instructions and can act on with you — both jobs, the monthly token refresh
included. By hand, the generation job is:

```bash
hermes cron create "0 8 * * 0,1,3,5" \
  "Load the skill affiliate-threads-generator:affiliate-threads-generator with skill_view, then generate the next affiliate thread and send me the preview. Process exactly one candidate, then stop and wait for a decision." \
  --name "affiliate-threads-generator" \
  --deliver telegram
```

The scheduler only generates and previews. It never publishes.

### The other job: refresh the token monthly

The Threads token expires after 60 days, and a refresh resets the clock. That is
a second cron job, a script instead of a prompt — no model, nothing to approve:

```bash
hermes cron create "0 9 1 * *" \
  "Refresh the Threads token" \
  --no-agent \
  --script refresh-threads-token.sh \
  --deliver telegram \
  --name "threads-token-refresh"
```

It needs a `terminal.env_passthrough` line that the generation job does not, plus
the script body to go beside it. Both are in
[cron-setup.md](cron-setup.md#the-second-job-the-monthly-token-refresh).

## 7. First run

From Telegram:

```
Buatkan content berikutnya.
```

You should get a preview with the Product ID at the top. Reply `approve` and the
thread publishes. Reply `hold` or `cancel` and the Sheet is updated instead.

## Upgrading

```bash
hermes plugins update affiliate-threads-generator
hermes gateway restart
hermes plugins list          # confirm the version
```

One command, because there is one artifact: the tools, hooks, command and skill
all move together with the plugin. `$HERMES_HOME/plugins/` survives `hermes
update` — the updater only rebuilds the venv and the checkout. Plugin state under
`$HERMES_HOME/plugin-data/` survives too, which matters: it holds the publish
ledger.

## Troubleshooting

| Symptom                                  | Cause                                                 | Fix                                                                                                                                             |
| ---------------------------------------- | ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Plugin listed but disabled               | An unset `requires_env` gate, or a `register()` crash | Answer the prompt (`hermes plugins enable affiliate-threads-generator`), or `HERMES_PLUGINS_DEBUG=1 hermes plugins list` and read the traceback |
| Tools missing from the model's tool list | Toolset not enabled for the platform                  | `hermes tools` → enable `affiliate_threads` for Telegram and cron                                                                               |
| Cron run does not load the skill         | The job's prompt does not name it                     | Put `affiliate-threads-generator:affiliate-threads-generator` in the job prompt — see [cron-setup.md](cron-setup.md)                            |
| `doctor.py` cannot find the plugin       | Plugin not installed where Hermes looks               | `hermes plugins install msyamsularif/affiliate-threads-generator --enable`, or set `HERMES_HOME`                                                |
| `google_api.py could not be found`       | The google-workspace skill is not installed           | Install/authorize it, or set `HERMES_GAPI_PATH`                                                                                                 |
| Everything passes but nothing publishes  | Expected — publishing needs explicit human approval   | Reply `approve` to a preview                                                                                                                    |
