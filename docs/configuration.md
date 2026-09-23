# Configuration

Every setting has three possible sources. Later ones win:

1. the default in `plugin.yaml`
2. `plugins.entries.affiliate-threads-generator.settings.<key>` in
   `$HERMES_HOME/config.yaml` — editable in the Desktop app's
   Capabilities → Plugins tab, no YAML needed
3. the environment variable listed below, in `$HERMES_HOME/.env`

A few settings can also be overridden per tool call (`spreadsheet_id`,
`sheet_tab`).

---

## Credentials

| Setting                | Env                    | Notes                                                                                                      |
| ---------------------- | ---------------------- | ---------------------------------------------------------------------------------------------------------- |
| `threads_access_token` | `THREADS_ACCESS_TOKEN` | Long-lived Threads user token. **Secret** — declared with password/secret masking, never in `config.yaml`. |
| `threads_user_id`      | `THREADS_USER_ID`      | Optional. Resolved from `GET /me` and cached when empty.                                                   |
| `spreadsheet_id`       | `AFFILIATE_SHEET_ID`   | From the sheet URL: `/spreadsheets/d/<THIS>/edit`                                                          |
| `sheet_tab`            | `AFFILIATE_SHEET_TAB`  | Default `Sheet1`                                                                                           |

The plugin declares its credentials through Hermes rather than shipping or
hard-coding them. `THREADS_ACCESS_TOKEN` and `AFFILIATE_SHEET_ID` are in
`requires_env`, so Hermes prompts for them when the plugin is installed or enabled
and **does not load the plugin until they are set**. `THREADS_USER_ID` and
`AFFILIATE_SHEET_TAB` are in `optional_env`: they have working defaults and never
block a load.

Set them the Hermes way rather than by editing `.env`:

```bash
# Explicit — routed to the credential store because the names are registered
hermes config set THREADS_ACCESS_TOKEN "THQW..."

# Or let Hermes prompt: load the skill in the local CLI
# Or the Desktop form: Capabilities -> Plugins -> gear icon
# Or a secret manager: secrets.sources in config.yaml
```

Full mechanism, including why the skill's scripts need these in the environment
and not only as plugin settings: [credentials.md](credentials.md).

---

## Sheet layout

The default table is the documented contract:

| Col | Field           |
| --- | --------------- |
| A   | `ID`            |
| B   | `Product`       |
| C   | `Description`   |
| D   | `Affiliate URL` |
| E   | `Category`      |
| F   | `Threads URL`   |
| G   | `Status`        |

If your table differs, remap it with the `columns` setting instead of editing code:

```yaml
plugins:
  entries:
    affiliate-threads-generator:
      settings:
        columns:
          id: "A"
          product: "B"
          description: "D"
          affiliate_url: "E"
          category: "F"
          threads_url: "G"
          status: "H"
```

Rules:

- Fields you omit keep their defaults.
- Letters are case-insensitive.
- A map that names one column twice is **discarded entirely** and the documented
  layout is used — a contradictory layout would silently corrupt writes, so it is
  better to do nothing than to do the wrong thing.
- Unknown field names are ignored.

See [google-sheets-setup.md](google-sheets-setup.md) for the column semantics and
what a good `Description` looks like.

## Status vocabulary

| Setting              | Default             |
| -------------------- | ------------------- |
| `eligible_status`    | `Ready To Generate` |
| `done_status`        | `Done`              |
| `hold_status`        | `Hold`              |
| `cancel_status`      | `Cancel`            |
| `in_progress_status` | `In Progress`       |

Comparisons are **exact**, including case. A row whose status is
`ready to generate` is not eligible. That is intentional — a fuzzy match here is
how the wrong row gets published.

---

## Publish guardrails

These are enforced by `threads_publish` in code. Nothing here is a suggestion.

| Setting                   | Default                                                                                                                                        | Effect                                                     |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `require_disclosure`      | `true`                                                                                                                                         | Refuse to publish when no post carries a disclosure marker |
| `disclosure_markers`      | `#ad`, `#ads`, `#affiliate`, `#afiliasi`, `link afiliasi`, `affiliate link`, `tautan afiliasi`, `komisi`, `paid partnership`, `iklan berbayar` | Any one satisfies the requirement                          |
| `require_affiliate_url`   | `true`                                                                                                                                         | The row's `Affiliate URL` must appear in some post         |
| `blocked_phrases`         | 8 regex patterns                                                                                                                               | The fabricated-personal-experience ban. Case-insensitive.  |
| `min_posts` / `max_posts` | `3` / `6`                                                                                                                                      | Thread length bounds                                       |
| `max_chars_per_post`      | `500`                                                                                                                                          | Threads' own limit; emoji count as their UTF-8 byte length |
| `max_links_per_post`      | `5`                                                                                                                                            | Threads rejects more                                       |
| `container_wait_seconds`  | `5`                                                                                                                                            | Pause between container creation and publishing            |

### Tightening the blocked-phrase list

The defaults catch the common phrasings in Indonesian and English. Add your own
if your copy keeps slipping through:

```yaml
plugins:
  entries:
    affiliate-threads-generator:
      settings:
        blocked_phrases:
          - '\baku (sudah|udah|pernah) (coba|pakai)\b'
          - '\bdi pengalaman aku\b'
          - '\bproduk ini aku dapat dari\b'
```

### Relaxing the disclosure requirement

Don't. The specification is explicit that the disclosure stays clear — the goal
is a lower hard-sell tone, not a hidden commercial relationship. If the wording
feels clumsy, add your own marker to `disclosure_markers` rather than turning the
check off.

---

## Google Sheets plumbing

| Setting                 | Env                   | Default                                                                               |
| ----------------------- | --------------------- | ------------------------------------------------------------------------------------- |
| `google_api_path`       | `HERMES_GAPI_PATH`    | auto-discovered under `$HERMES_HOME/skills/**/google-workspace/scripts/google_api.py` |
| `google_api_command`    | `HERMES_GAPI_COMMAND` | `{python} {script}`                                                                   |
| `sheet_timeout_seconds` | —                     | `60`                                                                                  |

The plugin does not ship its own Google OAuth. It shells out to the bundled
`google-workspace` skill's `google_api.py`, so there is one credential store and
one refresh path. If you keep that script somewhere unusual, point
`google_api_path` at it.

`google_api_command` exists for the case where the CLI must run under a different
interpreter:

```yaml
google_api_command: "/opt/google-venv/bin/python {script}"
```

---

## Approval and audit

| Setting                   | Default | Effect                                                               |
| ------------------------- | ------- | -------------------------------------------------------------------- |
| `require_approval_prompt` | `true`  | Escalate every `threads_publish` call to Hermes' human-approval gate |
| `content_language`        | `id`    | Language for generated copy (`id` or `en`)                           |

`require_approval_prompt` is the second confirmation, on top of the human's
explicit approval in conversation. Turning it off removes an out-of-band check
that the model cannot bypass — think carefully before doing so, and read
[operations-runbook.md](operations-runbook.md#the-approval-gate).

---

## Full example

```yaml
# $HERMES_HOME/config.yaml
plugins:
  entries:
    affiliate-threads-generator:
      enabled: true
      settings:
        sheet_tab: "Candidates"
        eligible_status: "Ready To Generate"
        content_language: "id"
        max_posts: 5
        require_approval_prompt: true
        disclosure_markers:
          - "#afiliasi"
          - "link afiliasi"
          - "komisi"
```

Credentials do not appear in that block on purpose — they go through the
credential store, never `config.yaml`. See [credentials.md](credentials.md).

```bash
# Credentials, set the Hermes way (routed to the credential store):
hermes config set THREADS_ACCESS_TOKEN "THQW..."
hermes config set AFFILIATE_SHEET_ID "1AbCdEfGhIjKlMnOpQrStUvWxYz"
```

(Equivalently you can put them in `$HERMES_HOME/.env`, but `hermes config set` is
the supported path and also works with secret managers.)

After changing configuration or credentials, restart the gateway so the new
environment is loaded:

```bash
hermes gateway restart
```

## Verifying what is actually in effect

```bash
hermes chat -q "Run threads_check and show me the settings summary."
```

`threads_check` echoes the resolved settings back — including whether credentials
are configured — without ever printing a secret.
