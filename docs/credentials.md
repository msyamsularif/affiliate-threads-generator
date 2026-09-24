# Credentials

**No secret lives in this repository.** There is no credential literal in any
file here, and no code path reads one from anywhere except the environment that
Hermes builds for the process.

This document explains the whole chain, because the mechanism has four stages and
it is worth knowing which stage owns what.

---

## The chain

```
                     YOU
                      │  (1) enter it once, in a Hermes-owned prompt
                      ▼
        ┌─────────────────────────────┐
        │  Hermes credential store    │  ~/.hermes/.env
        │                             │  or Bitwarden / 1Password / any CLI vault
        └─────────────┬───────────────┘
                      │  (2) injected into the environment at process start
                      ▼
        ┌─────────────────────────────┐
        │  Process environment        │  os.environ["THREADS_ACCESS_TOKEN"]
        └──────┬───────────────┬──────┘
               │               │
        (3a)   │               │   (3b)
               ▼               ▼
    ┌──────────────────┐  ┌──────────────────────────────┐
    │  Plugin tools    │  │  terminal / execute_code     │
    │  (in-process)    │  │  children — sanitized env,    │
    │  reads os.environ│  │  only declared names pass     │
    └──────────────────┘  └──────────────────────────────┘
```

Stage 1 is Hermes' job. Stage 4 is where the project uses the value. Stages 2 and
3 are the part that surprises people, so they get their own section below.

---

## Where each thing lives

This is worth being precise about, because "put the plugin's config in
`~/.hermes/<plugin>/`" is the right instinct aimed at the wrong directory.

Hermes has **three** plugin-owned locations, and they are not interchangeable.

| Location                                                        | Holds                                                  | Written by                                                 | Used by this plugin for                   |
| --------------------------------------------------------------- | ------------------------------------------------------ | ---------------------------------------------------------- | ----------------------------------------- |
| `~/.hermes/plugin-data/<namespace>/state.json`                  | Writable runtime data — JSON, or an optional SQLite DB | The plugin, at runtime                                     | The publish ledger and the audit trail    |
| `~/.hermes/config.yaml` → `plugins.entries.<id>.settings`       | Non-secret settings                                    | You, the Desktop form, `hermes config set`                 | Sheet tab, thread length, guardrail knobs |
| Hermes credential store (`~/.hermes/.env`, or a secret manager) | **Secrets**                                            | You, via a prompt / `hermes config set` / the Desktop form | The Threads token                         |

`plugin-data/` is the directory-per-plugin store — one folder per plugin,
inspectable in one predictable place. It is where this project keeps its ledger:

```
~/.hermes/plugin-data/
├── agent-plugin-affiliate-threads-generator-<hash>/
│   └── state.json    # publish_ledger + publish_audit, written at runtime
└── affiliate-threads-generator/
    └── state.json    # the same keys, written by the skill's scripts
```

The directory name is not the plugin id, and the two writers do not share a file.
That is Hermes' design, not drift on this plugin's side:

- Inside Hermes, state goes through `ctx.state`, and Hermes files a _native_
  plugin's state under `agent-plugin-<slug>-<hash>/` — Windows-safe and
  collision-proof, and deliberately not derivable from the plugin name.
- Outside Hermes — the skill's scripts, `doctor.py`, a unit test — there is no
  `ctx.state` to write through, so `runtime.py` falls back to the documented
  `plugin_data_dir("<plugin-id>")` convention, `plugin-data/<plugin-id>/`.

Both hold the same keys, so **read the payload, not the path**. `doctor.py` walks
`plugin-data/*/state.json` and treats any file carrying a `publish_ledger` as this
plugin's. Inside Hermes, prefer `threads_check` or `/affiliate-threads status` —
they read the live record through the tool rather than guessing at a directory.

**Secrets do not go there**, and that is a platform rule rather than a style
preference. Hermes' own developer guide states it directly:

> One directory per plugin means every plugin's data is inspectable in one
> predictable place. Secrets don't belong here — credential reads go through the
> standard `.env` / secret-scope path like everywhere else.

The reasons hold up in practice:

- `plugin-data` is a plain directory. Anything in it is readable by whoever can
  read your home directory, it gets swept into casual backups, and it tends to be
  pasted into a bug report when something goes wrong.
- A secret there would bypass rotation. The credential store is what Hermes' secret
  managers write into, what `hermes doctor` inspects, and what gets scrubbed from
  logs and cron output.
- It would not follow a profile or machine change the way a vault entry does.

So the split is: **state in `plugin-data`, settings in `config.yaml`, secrets in
the credential store.** The plugin reads all three — just not interchangeably.

---

## What is declared where

The plugin and its bundled skill declare the _names_. Neither declares a value.

### `plugin.yaml` → `requires_env`

Two variables with no working default. These gate loading, and they are what
Hermes prompts for during `hermes plugins install` and `hermes plugins enable`.

| Variable               | Masked  | Needed for                                       |
| ---------------------- | ------- | ------------------------------------------------ |
| `THREADS_ACCESS_TOKEN` | **yes** | Publishing to Meta Threads                       |
| `AFFILIATE_SHEET_ID`   | no      | Reading candidates and recording publish results |

### `plugin.yaml` → `optional_env`

Two more, both with a working default or an automatic fallback. Declared so they
appear in the config UI; they never block a load.

| Variable              | Default                 | Needed for                 |
| --------------------- | ----------------------- | -------------------------- |
| `THREADS_USER_ID`     | resolved from `GET /me` | Pinning a specific account |
| `AFFILIATE_SHEET_TAB` | `Sheet1`                | Reading candidates         |

Two masking keys appear on the token entry, because Hermes has two separate
readers: `hermes_cli/plugins_cmd.py` builds the install prompt from `secret`, and
`hermes_cli/config.py` builds the config-UI entry from `password`. Setting only
one leaks the value unmasked on the other surface.

### `SKILL.md` → `required_environment_variables`

All four names again, plus `required_credential_files` for the Google OAuth
artifacts this skill borrows from `google-workspace`:

```yaml
required_credential_files:
  - path: google_token.json
  - path: google_client_secret.json
```

The skill-level declaration does two jobs the manifest cannot:

1. **Terminal passthrough** — see [the subtle part](#the-subtle-part-sanitized-child-processes).
2. **A prompt at the moment of use.** Hermes asks for anything still unset when
   the skill loads in the local CLI.

Declaring the Google files up front means Hermes reports "setup needed" _before_
the first Sheet call, and mounts them correctly if you run the agent on a remote
backend (Docker, Modal) where `~/.hermes/` is not simply on disk.

---

## Installing for someone else

If you are distributing this plugin, a new user's first contact with credentials
is the install prompt — no file editing required, and no instruction to go and
find one.

```
$ hermes plugins install msyamsularif/affiliate-threads-generator --enable

  This plugin needs the following to run.
  Values are stored in ~/.hermes/.env and never leave your machine.

  THREADS_ACCESS_TOKEN  (hidden)
    Long-lived Meta Threads user access token (60 days, refreshable). Needs the
    threads_basic and threads_content_publish scopes, from a Meta app created
    with the Threads use case.
    Get one at: https://developers.facebook.com/apps

  AFFILIATE_SHEET_ID
    Google Sheets spreadsheet id holding the candidate table — the long id in
    the sheet URL between /d/ and /edit.
```

Values are stored as they are collected, and already-set variables are skipped
silently, so re-running install or enable never re-asks for something you already
provided.

### The one consequence worth knowing

`requires_env` gates loading. While either variable is unset, Hermes reports the
plugin disabled and never calls `register(ctx)` — which means the bundled skill
does not load either. `hermes plugins list` names the missing variable, so this is
loud rather than mysterious, and answering the prompt clears it.

If you would rather research, generate and preview **before** wiring up
publishing, move `THREADS_ACCESS_TOKEN` from `requires_env` to `optional_env` in
the installed `plugin.yaml`. The plugin then loads without it, and
`threads_publish` fails closed on its own naming the missing variable. The
shipped split exists because most installs want the opposite: ready to publish, or
told clearly what is missing.

`hermes plugins update` restores the shipped manifest, so a local edit like that
needs re-applying after an update. For a single repository, prefer the prompt.

---

## Setting a credential

Five ways, all equivalent. Pick whichever fits the moment.

### 1. Answer the install prompt

Covered above. This is the normal path for a fresh install.

### 2. Let Hermes ask later

Load the skill in the local CLI — for instance by asking for content. Hermes sees
the declared variables, notices the missing one, and prompts for it directly. The
value goes into the credential store; you never type it into a chat message and
the model never sees it.

On a messaging platform (Telegram, Discord) there is nobody to prompt safely, so
Hermes shows local setup guidance instead of collecting a secret in-band. That is
deliberate: a token pasted into Telegram would live in the conversation history
and in the session database.

### 3. Set it explicitly

```bash
hermes config set THREADS_ACCESS_TOKEN "THQW..."
hermes config set AFFILIATE_SHEET_ID "1AbCdEf..."
```

Because these names are registered, Hermes routes them to the credential store
rather than `config.yaml`. This is also the path to use from a script or a
provisioning playbook.

### 4. The Desktop app

Capabilities → Plugins → the plugin's gear icon renders a form from the manifest's
`config_schema`. Fields declared `type: secret` are masked inputs that write
through the same credential route; secret values never touch `config.yaml`.

### 5. A secret manager (optional)

If you would rather not keep tokens in a file at all, Hermes can pull them from an
external vault at startup. The vault's own bootstrap token stays in `.env`;
everything else rotates centrally.

```yaml
# ~/.hermes/config.yaml
secrets:
  sources: [bitwarden]
  bitwarden:
    enabled: true
    project_id: "..."
```

Supported out of the box: **Bitwarden Secrets Manager** (`bws`), **1Password**
(`op://` references via the `op` CLI), and a **command helper** for anything else
(`pass`, `keepassxc-cli`, `secret-tool`, a custom script that prints `KEY=VALUE`
lines).

Precedence is deterministic: a value already in `.env` / your shell wins unless
the source sets `override_existing: true`; explicitly mapped sources beat bulk
ones; first source wins on ties. Every injected value is labelled with its origin,
so `hermes model` will show `(from Bitwarden)` next to a detected key.

---

## Why the `requires_env` / `optional_env` split

`requires_env` is the only field Hermes prompts for at install time, so anything
a new user genuinely cannot proceed without belongs there. It also **gates
loading** — which is why the two entries that have a working default do not.

|                                                    | `requires_env` | `optional_env` |
| -------------------------------------------------- | -------------- | -------------- |
| Prompts at `hermes plugins install` / `enable`     | yes            | no             |
| Appears in the setup wizard / config UI            | yes            | yes            |
| Routes `hermes config set` to the credential store | yes            | yes            |
| Disables the plugin while unset                    | **yes**        | no             |

A name must never appear in both lists. It would still gate, so the install
prompt would be a lie: the user answers it and the plugin stays disabled.
`tests/test_credentials.py` pins that invariant.

---

## The subtle part: sanitized child processes

The plugin's tools run **in-process**, so they read `os.environ` directly. Nothing
extra is needed for them.

The skill's scripts (`doctor.py`, `select_candidate.py`, `set_status.py`,
`validate_thread.py`, `threads_token.py`) run through the `terminal` tool as
**child processes**, and those children get a **sanitized environment**: Hermes
strips its managed credentials and forwards only the names you declare — in
`terminal.env_passthrough`, or in a loaded skill's `required_environment_variables`.

This is exactly why the skill declares all four names rather than only the secret.
An undeclared variable does not reach the script, and the script would fail with
"not configured" while the plugin itself worked fine. That failure mode is
confusing enough to be worth stating plainly:

> If a script cannot see a credential but the plugin can, the name is missing from
> the skill's `required_environment_variables`.

There is one consequence worth knowing. `AFFILIATE_SHEET_ID` can also be set as a
plain plugin setting (`plugins.entries.affiliate-threads-generator.settings.
spreadsheet_id` in `config.yaml`) — that works fine for the plugin, and the
Desktop settings form writes it there.

**Settings are not credentials, and the scripts read them from the same file.**
The skill's scripts import the plugin's own modules, and `runtime.py` reads
`plugins.entries.affiliate-threads-generator.settings.*` out of
`$HERMES_HOME/config.yaml` itself when it runs outside Hermes. So a guardrail or a
mode customised in the Desktop form — `max_posts`, `publish_mode` — is enforced
by `validate_thread.py` exactly
as `threads_publish` enforces it, and `spreadsheet_id` set there is enough for
`select_candidate.py` too.

Two caveats on that read:

- It needs PyYAML, which Hermes itself uses. Without it the scripts fall back to a
  narrow parser for the settings block; a construct neither can read confidently
  yields _no_ settings plus a warning on stderr, and `doctor.py`'s
  `plugin_settings` check goes red. A lint that ran with different rules than the
  publish tool says so rather than implying a clean bill of health.
- Secrets still belong in the credential store, never in `config.yaml`. Set
  `THREADS_ACCESS_TOKEN` in `.env` / via `hermes config set`, and declare it for
  `terminal.env_passthrough` if a script needs it directly.

If you want exactly one place for configuration, settings files cover the
settings and the credential store covers the token; neither substitutes for the
other.

Cron `no_agent` scripts are a third case: children too, but the skill is not
loaded during them, so `required_environment_variables` does not apply. Declare the
variable in `terminal.env_passthrough` instead — see
[threads-app-setup.md](threads-app-setup.md#automate-it).

---

## Rotation

A Threads long-lived token lasts 60 days and refreshing resets the clock, so a
monthly refresh is plenty:

```bash
# The skill ships inside the plugin; nothing is installed under ~/.hermes/skills/.
SKILL_DIR="$HERMES_HOME/plugins/affiliate-threads-generator/skills/affiliate-threads-generator"

python3 "$SKILL_DIR/scripts/threads_token.py" refresh --write-env
hermes gateway restart
```

`--write-env` rewrites the `THREADS_ACCESS_TOKEN=` line in `~/.hermes/.env`
(mode `0600`) and leaves everything else in the file alone. See
[threads-app-setup.md](threads-app-setup.md#keeping-the-token-alive) for the
scheduled version.

If you use a secret manager instead, rotate there and restart the gateway — the
plugin reads whatever the environment holds at call time and never caches a token
to disk itself.

---

## If a secret leaks

1. **Revoke it at the source.** For Threads: regenerate the token in the Meta app.
   Revoking is what actually stops the exposure; deleting a file does not.
2. Replace the value: `hermes config set THREADS_ACCESS_TOKEN "<new>"`.
3. Restart the gateway so no process keeps the old value in memory.
4. Check what else reached the same place. The Threads token cannot read your
   Sheet, and the Google token cannot post to Threads — separate credentials,
   separate blast radius. That separation is the point of not reusing one.

The audit trail is worth a look too, since it records publish attempts without
recording credentials:

```bash
hermes logs --level INFO | grep "audit threads_publish"
```

---

## What this project never does

- Never writes a credential into `config.yaml`, `plugin-data/`, the audit trail,
  or a log line.
- Never passes a credential to the model. `threads_check` reports _whether_ the
  token resolves and when it expires — never its value.
- Never accepts a token through a chat message on a messaging platform.
- Never reads a credential from anywhere but `os.environ`.
- Never commits one. `.env` is gitignored, and `.env.example` holds field names
  with empty values and a description, nothing more.

Test suite guards, in `tests/test_credentials.py`:

- every tracked file is scanned for vendor-shaped token literals
- `.env.example` must carry no values at all
- `requires_env` and `optional_env` must declare exactly the expected names, and
  must never overlap — a name in both lists would still gate, making the install
  prompt a lie
- the Threads token must be masked on both surfaces (`secret` _and_ `password`)
- the audit trail, `threads_check` and `public_summary()` must never contain a
  credential value

---

## Verify the wiring

```bash
# Are the names registered with Hermes?
hermes config show | grep -i -E "threads|affiliate" || true

# Does the plugin see a working token?
hermes chat -q "Run threads_check."

# Do the standalone scripts see everything they need?
SKILL_DIR="$HERMES_HOME/plugins/affiliate-threads-generator/skills/affiliate-threads-generator"
python3 "$SKILL_DIR/scripts/doctor.py"
```

`doctor.py` reports each declared variable as configured or missing, naming it
exactly. A `✓` on `threads_credentials` with a `✗` on `threads_api` means the token
is present but the API rejected it — an expiry or scope problem, not a wiring one.

The `plugin_settings` check says where the scripts got the plugin's settings from:
the host, `config.yaml`, or the defaults. A red one there means the scripts cannot
read the settings block and are enforcing the defaults instead.
