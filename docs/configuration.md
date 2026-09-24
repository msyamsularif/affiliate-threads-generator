# Configuration

Every setting has three possible sources. Later ones win:

1. the default in `plugin.yaml`
2. `plugins.entries.affiliate-threads-generator.settings.<key>` in
   `$HERMES_HOME/config.yaml` — editable in the Desktop app's
   Capabilities → Plugins tab, no YAML needed
3. the environment variable listed below, in `$HERMES_HOME/.env`

A few settings can also be overridden per tool call (`spreadsheet_id`,
`sheet_tab`).

Source 2 is one file, read by two paths: the plugin's tools go through Hermes,
and the bundled scripts — which run outside Hermes — parse `config.yaml`
themselves before falling back to the environment. A guardrail changed here
therefore changes what `validate_thread.py` enforces as well as what
`threads_publish` enforces, which is the point: the lint's promise is that a
draft passing it passes the publish. `doctor.py` reports where the settings
actually came from in its `plugin_settings` check.

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

| Setting                   | Default                                                                                       | Effect                                                                   |
| ------------------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `require_disclosure`      | `true`                                                                                        | Refuse to publish when no post carries a disclosure marker               |
| `disclosure_markers`      | `link afiliasi`, `affiliate link`, `tautan afiliasi`, `komisi`, `paid partnership`, `iklan berbayar` | Any one satisfies the requirement — a short sentence, never a hashtag    |
| `require_affiliate_url`   | `true`                                                                                        | The row's `Affiliate URL` must appear in some post                       |
| `require_topic_tag`       | `true`                                                                                        | A thread may not publish without a topic tag — see below                 |
| `allowed_hashtags`        | `[]`                                                                                          | Hashtags the copy may keep — empty by default, no hashtag belongs there  |
| `blocked_phrases`         | 11 regex patterns                                                                             | The fabricated-personal-experience ban. Case-insensitive.                |
| `min_posts` / `max_posts` | `3` / `10`                                                                                    | Thread length bounds                                                     |
| `max_chars_per_post`      | `500`                                                                                         | Threads' own limit; emoji count as their UTF-8 byte length               |
| `max_links_per_post`      | `5`                                                                                           | Threads rejects more                                                     |
| `container_wait_seconds`  | `5`                                                                                           | Pause between container creation and publishing                          |
| `publish_mode`            | `single` (`single` or `two_stage`)                                                            | Whether the affiliate link publishes with the thread or as a later reply |
| `link_pending_status`     | `Link Pending`                                                                                | Where a two-stage row parks between the two publishes                    |

### Hashtags and topic tags

Threads gives a post exactly **one** clickable tag, calls it a _topic tag_, and
reads it from the `topic_tag` publish argument rather than from the copy. When
that topic has a Threads community, the post is also surfaced inside the
community — the platform's real discovery mechanism. So the plugin treats that
argument as the reach channel, and treats hashtags typed into the copy as a
defect rather than a tactic.

- **`require_topic_tag` (`true`)** — a thread may not publish without one. The
  tag goes in the `topic_tag` argument as the bare topic (1-50 characters, no
  `.` or `&`, no leading `#`). It is metadata: it never appears in the copy, and
  the replies carry none.
- **`allowed_hashtags` (`[]`)** — empty by default, because the copy carries no
  hashtags at all. There is no hashtag disclosure either: `#ad` at the end is
  not used, reads as an unclear tag, and is refused like any other hashtag
  (`hashtag_in_copy`). Add a token here only if you genuinely want it in the
  text.

To publish untagged instead:

```yaml
plugins:
  entries:
    affiliate-threads-generator:
      settings:
        require_topic_tag: false
```

The soft signal in the same family is `funnel_phrase`: copy whose only job is to
move the reader toward the link ("cek link di bawah", "link di bio", "cek
reply"). It is a warning, never a block — the honest fix is a rewrite.

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
feels clumsy, change the wording, not the check: one short sentence is enough,
and it does not have to mention commission.

```
Link afiliasi.
```

```
Detail produknya:
https://...

Link afiliasi.
```

The usual place is the post carrying the link. There is no hashtag form: a
`#...` entry in `disclosure_markers` is dropped (the defaults are sentences), and
`#ad` in the copy is refused by `hashtag_in_copy`. What is never allowed is
dropping the disclosure, burying it, or putting it somewhere the reader
following the link will not have seen. See
`skills/affiliate-threads-generator/references/editorial-rules.md`.

---

## Deferred affiliate links (`publish_mode: two_stage`)

By default the thread and its affiliate link publish in one call. `two_stage`
splits that into two approved publishes, which is what makes the "let the post
collect views first, then attach the link" tactic possible:

```text
stage 1  threads_publish (stage: "thread")   the thread, without the link
         Sheet: Threads URL = permalink, Status = link_pending_status

         the human watches the post

stage 2  threads_publish (stage: "link")     one reply: the affiliate URL
         Sheet: Status = Done                 plus the disclosure
```

Rules that come with it:

- Both halves need their own explicit human approval; the second call is gated
  exactly like the first.
- The thread body is linted and published without the affiliate URL and without a
  disclosure, because at that moment there is no commercial relationship in the
  copy yet. Both are enforced on the reply instead: it must carry the row's
  `Affiliate URL` and satisfy the configured disclosure rule.
- `link_pending_status` is what marks a thread as unfinished. It has to differ
  from every other status in use; a value that collides with the eligible, done,
  hold, cancel or in-progress status is rejected and `Link Pending` is used
  instead. A collision would either publish the same row twice or read as a hold.
- Nothing posts the link on its own. If the human never asks for it, the thread
  simply stays parked, and `/affiliate-threads status` reports it as waiting.
- `validate_thread.py` follows the same stages: `--stage thread` (the default
  under this mode) lints the body, `--stage link` lints the single reply post.

Switch back to one-call publishing at any time by setting `publish_mode: single`;
the tool then refuses a parked row until it is finished by hand.

---

## Structural soft signals

These never block publishing. They come back from `threads_publish` and
`validate_thread.py` as `warnings`, so the model can rewrite before the preview
reaches a human.

Each one is a threshold, not a ban: one "Jadi," is ordinary Indonesian, three of
them is a rhythm the reader can feel. A value of `0` disables that signal.

| Setting                         | Default | Fires when                                                       |
| ------------------------------- | ------- | ---------------------------------------------------------------- |
| `signposting_warning_threshold` | `2`     | This many "mari kita bahas" / "yang perlu kamu tahu" phrases     |
| `transition_warning_threshold`  | `3`     | This many sentence-opening transitions ("Jadi, ...", "Makanya,") |
| `enumeration_warning_threshold` | `2`     | This many enumeration markers ("Pertama, ...", "Kedua: ...")     |
| `spec_token_warning_threshold`  | `6`     | This many number-plus-unit tokens in one thread (spec dumping)   |

None of these is proof that a text is AI-written, and none of them replaces the
prose audit: that lives in the external `antislop` and `antislop-copywriting`
skills — see [antislop-integration.md](antislop-integration.md).

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
          - "link afiliasi"
          - "komisi"
        # Optional: publish the thread first and attach the link as a reply
        # once the post has been seen. Two approvals, two publishes.
        # publish_mode: "two_stage"
        # link_pending_status: "Link Pending"
        #
        # Optional: allow a hashtag in the copy (empty means no hashtags at all,
        # which is the default). The topic tag is separate and is required by
        # default: it travels in the topic_tag argument, not in the text.
        # allowed_hashtags: ["#ootd"]
        # require_topic_tag: false
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

```bash
SKILL_DIR="$HERMES_HOME/plugins/affiliate-threads-generator/skills/affiliate-threads-generator"
python3 "$SKILL_DIR/scripts/doctor.py"
```

The doctor's `plugin_settings` line names the file the settings came from and how
many keys it contributed. If it is red, the scripts could not read that block and
are running on the defaults — see [credentials.md](credentials.md#the-subtle-part-sanitized-child-processes).
