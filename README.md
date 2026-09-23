# Affiliate Threads — Hermes Agent Plugin

An AI-assisted affiliate content engine for **Meta Threads**, implemented as a
[Hermes Agent](https://hermes-agent.nousresearch.com) plugin instead of a
standalone application.

Turns product candidates in Google Sheets into research-backed,
conversation-oriented Threads content, then waits for a human to approve before
anything is published.

> **Do not ask "how do we sell this product?"**
> Ask "what conversation is worth reading, and can this product naturally become
> a relevant solution?"

The central rule, carried over from the project specification:

```
AI creates and reasons.  Code controls and validates.  Human approves.
Threads publishes.       Google Sheets records the business state.
```

---

## What this repository contains

| Path                                                                    | What it is                                                                  |
| ----------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `plugins/affiliate-threads-generator/`                                   | The Hermes plugin — the **only** hand-written code artifact                 |
| `plugins/affiliate-threads-generator/skills/affiliate-threads-generator/` | The bundled Skill: pipeline, writing rules, references, helper scripts      |
| `docs/`                                                                 | Installation, configuration, Threads app setup, Sheets setup, cron, runbook |
| `tests/`                                                                | Unit tests for the plugin's deterministic layer                             |
| `install.sh`                                                            | One-command installer (plugin + skill)                                      |
| `PROJECT_SPEC_v2_plugins.md`                                            | The source-of-truth specification this implements                           |

---

## Architecture in one picture

```
User ──► Telegram (Hermes Messaging Gateway)
              │
              ▼
     Skill: affiliate-threads-generator
     (research, angles, narrative, writing, anti-slop)
              │
              ├─► Hermes bundled google-workspace skill  → Google Sheets (source of truth)
              ├─► Hermes bundled web/browser tools       → research
              ├─► Hermes built-in image generation       → optional visuals
              │
              ▼
     Human decision  (Approve / Hold / Cancel / Regenerate)
              │
              ▼
     Tool: threads_publish   ◄── the only path to Meta Threads
     (re-validates Sheet state, publishes, records the result)
              │
              ▼
     Meta Threads  (official Graph API)
```

**Skill vs Tool, in this project:**

- **Skill** — everything that can be expressed as instructions plus tools that
  already exist. Research, angle discovery, narrative planning, writing,
  anti-slop review, interpreting natural-language approve/hold/cancel.
- **Tool** — exactly one thing: `threads_publish`. A side effect must never
  depend on the model getting it right.

The plugin ships two tools:

| Tool              | Purpose                                                                                                                                                   |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `threads_publish` | Re-validates the Sheet row, publishes the thread via the official Threads Graph API, then writes `Status=Done` + `Threads URL`. The only path to Threads. |
| `threads_check`   | Read-only preflight: credentials, identity, token expiry, Sheet reachability, next eligible candidate.                                                    |

Two hooks:

| Hook             | Purpose                                                                       |
| ---------------- | ----------------------------------------------------------------------------- |
| `pre_tool_call`  | Escalates every `threads_publish` call to Hermes' own human-approval gate.    |
| `post_tool_call` | Writes an audit line for every publish attempt to `~/.hermes/logs/agent.log`. |

---

## Quick start

```bash
# 1. Install the plugin + skill
./install.sh

# 2. Enable it. This is where Hermes asks for the credentials — the plugin
#    declares them, so enabling prompts for what it cannot run without. Nothing
#    to edit, nothing echoed back, values go to Hermes' credential store.
hermes plugins enable affiliate-threads-generator

#    (Or install and enable from Git in one step:)
#    hermes plugins install <repo> --enable

# 3. Verify everything
hermes chat -q "Run the affiliate-threads-generator doctor script."
```

Then, from Telegram:

```
Buatkan content berikutnya.
```

Full instructions: [`docs/installation.md`](docs/installation.md).

---

## Non-negotiable rules enforced by this implementation

| #   | Rule                                       | Where it is enforced                                                                                                                                                                    |
| --- | ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Human approval before every publish        | `pre_tool_call` → Hermes approval gate                                                                                                                                                  |
| 2   | Only `Ready To Generate` rows are eligible | `threads_publish` re-reads the Sheet in code                                                                                                                                            |
| 3   | One candidate per request                  | Skill instructions + `select_candidate.py`                                                                                                                                              |
| 4   | Scheduler never publishes                  | Cron job only generates and previews                                                                                                                                                    |
| 5   | Sheet is the state lock, no separate DB    | `threads_publish` writes `Status` / `Threads URL`                                                                                                                                       |
| 6   | No fabricated personal experience          | `threads_publish` blocks known patterns before publishing                                                                                                                               |
| 7   | Disclosure stays visible                   | `threads_publish` requires a disclosure marker + the affiliate URL                                                                                                                      |
| 8   | Failed publish never changes Status        | Sheet write happens only after a confirmed media ID                                                                                                                                     |
| 9   | AI cannot reach Threads any other way      | No credential or publish path exists outside the tool                                                                                                                                   |
| 10  | Shopee anti-bot is never bypassed          | Skill instructions; research is description-first                                                                                                                                       |
| 11  | No secret ships in the repository          | Declared as names only (`requires_env` / `optional_env` + skill frontmatter); Hermes prompts for them at install and owns the values — see [`docs/credentials.md`](docs/credentials.md) |

---

## Requirements

- Hermes Agent with the gateway configured for Telegram
- A Meta app with the Threads use case, and a long-lived Threads user token
  with `threads_basic` + `threads_content_publish`
- The bundled `google-workspace` skill authorized for Sheets
- A Google Sheet with the columns described in
  [`docs/google-sheets-setup.md`](docs/google-sheets-setup.md)

## Development

The deterministic layer — guardrails, the Threads client, the Sheet client, the
publish tool, the hooks — is covered by tests. None of them touch the network: the
Threads API and the Google Sheets CLI are both faked at the boundary.

```bash
uv run --no-project --with pytest --with pyyaml --with ruff pytest -q
uv run --no-project --with ruff ruff check .
```

| Suite                            | What it pins down                                                                   |
| -------------------------------- | ----------------------------------------------------------------------------------- |
| `test_guardrails.py`             | Character/link limits, disclosure, the affiliate URL, the fabricated-experience ban |
| `test_config.py`                 | Settings resolution, column maths, A1 range building                                |
| `test_threads_client.py`         | Reply chaining, retry policy, container error states                                |
| `test_tools_publish.py`          | Every refusal path, and that a failed publish never writes the Sheet                |
| `test_hooks.py`                  | The approval gate fires for `threads_publish` and nothing else                      |
| `test_plugin_manifest.py`        | Declared tools/hooks match what `register()` registers; the skill is loadable       |
| `test_integration_end_to_end.py` | The whole cycle through a real subprocess to a fake `google_api.py`                 |

Before changing anything in `guardrails.py` or `tools.py`, run both commands.
The publish path is the one place where a quiet regression reaches a live
profile.

## License

MIT — see [`LICENSE`](LICENSE).
