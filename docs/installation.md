# Installation

## Prerequisites

| Requirement                                      | Why                                                   |
| ------------------------------------------------ | ----------------------------------------------------- |
| Hermes Agent, gateway running                    | The whole runtime: agent loop, Telegram, cron, memory |
| Telegram configured for Hermes                   | The only user-facing control surface                  |
| The bundled `google-workspace` skill, authorized | Google Sheets is the business-data source of truth    |
| A Meta app with the Threads use case             | Publishing                                            |
| A Google Sheet with the candidate table          | See [google-sheets-setup.md](google-sheets-setup.md)  |

## 1. Install the plugin and the skill

From the repository root:

```bash
./install.sh
```

This copies:

| From                                                                    | To                                                 |
| ----------------------------------------------------------------------- | -------------------------------------------------- |
| `plugins/affiliate-threads-generator/`                                   | `$HERMES_HOME/plugins/affiliate-threads-generator/` |
| `plugins/affiliate-threads-generator/skills/affiliate-threads-generator/` | `$HERMES_HOME/skills/affiliate-threads-generator/`  |

Both copies matter:

- The **plugin** provides the tools and hooks. It also registers its own bundled
  skill, reachable as `affiliate-threads-generator:affiliate-threads-generator`.
- The **standalone skill copy** gives the skill an unqualified name. That is what
  cron's `--skill affiliate-threads-generator` flag and `/skill-name` look up.

Useful variants:

```bash
./install.sh --plugin-only     # plugin only
./install.sh --skill-only      # refresh the skill copy after editing it
./install.sh --uninstall       # remove both (cron jobs are left alone)
```

## 2. Enable the plugin

```bash
hermes plugins enable affiliate-threads-generator
```

**This is where Hermes asks for the credentials.** The plugin declares two
variables it cannot work without, so enabling it prompts for them — with their
description, a link to the Meta app console, and the token masked as you type.
Values are stored in Hermes' credential store; you never edit a file, and nothing
is echoed back.

If you would rather install and enable in one step, use
`hermes plugins install <repo> --enable` — same prompt.

Plugins are opt-in. Confirm it loaded:

```bash
hermes plugins list
```

You should see the plugin with two tools and two hooks. If it does not appear:

```bash
HERMES_PLUGINS_DEBUG=1 hermes plugins list
```

If it appears as _disabled_ naming a variable, the prompt was skipped — set it
with `hermes config set` (step 4) and re-enable.

## 3. Validate the plugin

```bash
hermes plugins doctor "$HERMES_HOME/plugins/affiliate-threads-generator" --ci
```

This runs the same discovery, manifest parsing, import, `register(ctx)` and hook
registry that Hermes itself uses, and exits non-zero on any error. It also blocks
outbound sockets during registration, so a plugin that phones home at import time
fails here.

## 4. Credentials

Normally step 2 already collected what is needed. This section is for changing a
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
python3 "$HERMES_HOME/skills/affiliate-threads-generator/scripts/doctor.py"
```

A healthy setup looks like:

```
  ✓ plugin: found at .../plugins/affiliate-threads-generator (v1.0.0)
  ✓ settings: spreadsheet=... tab=Sheet1 eligible='Ready To Generate' disclosure=required
  ✓ threads_api: @yourhandle (id 1234567890); token valid=True, expires in 58.4 days
  ✓ sheets: 12 data row(s) in Sheet1; google_api=/.../google_api.py
  ✓ next_candidate: ID 3 — Wireless Earbuds X (row 5)
  ✓ skill_installed: /.../skills/affiliate-threads-generator/SKILL.md
  ✓ cron_job: affiliate-threads-generator [0 8 * * 0,1,3,5] next=... enabled=True
  ✓ unsynced_publishes: none

8/8 checks passed.
```

Any `✗` line comes with a `→` hint telling you exactly what to fix.

## 6. Schedule generation

See [cron-setup.md](cron-setup.md). The short version:

```bash
hermes cron create "0 8 * * 0,1,3,5" \
  "Generate the next affiliate thread and send me the preview. Process exactly one candidate, then stop and wait for a decision." \
  --skill affiliate-threads-generator \
  --name "affiliate-threads-generator" \
  --deliver telegram
```

The scheduler only generates and previews. It never publishes.

## 7. First run

From Telegram:

```
Buatkan content berikutnya.
```

You should get a preview with the Product ID at the top. Reply `approve` and the
thread publishes. Reply `hold` or `cancel` and the Sheet is updated instead.

## Upgrading

```bash
git pull
./install.sh
hermes plugins list          # confirm the version
```

`$HERMES_HOME/plugins/` and `$HERMES_HOME/skills/` survive `hermes update` — the
updater only rebuilds the venv and the checkout. Plugin state under
`$HERMES_HOME/plugin-data/` survives too, which matters: it holds the publish
ledger.

## Troubleshooting

| Symptom                                  | Cause                                                                              | Fix                                                                 |
| ---------------------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Plugin listed but disabled               | A `requires_env` gate — none are declared here, so this means a `register()` crash | `HERMES_PLUGINS_DEBUG=1 hermes plugins list` and read the traceback |
| Tools missing from the model's tool list | Toolset not enabled for the platform                                               | `hermes tools` → enable `affiliate_threads` for Telegram and cron   |
| Cron says "skill not found"              | Standalone skill copy missing                                                      | `./install.sh --skill-only`                                         |
| `doctor.py` cannot find the plugin       | Plugin not installed where Hermes looks                                            | `./install.sh`, or set `HERMES_HOME`                                |
| `google_api.py could not be found`       | The google-workspace skill is not installed                                        | Install/authorize it, or set `HERMES_GAPI_PATH`                     |
| Everything passes but nothing publishes  | Expected — publishing needs explicit human approval                                | Reply `approve` to a preview                                        |
