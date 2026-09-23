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

| Path                                                     | What it is                                                                                                                                                     |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `plugin.yaml`, `__init__.py` and the modules beside them | The Hermes plugin — the **only** hand-written code artifact. It lives at the repository root, which is what makes `hermes plugins install <owner>/<repo>` work |
| `skills/affiliate-threads-generator/`                    | The bundled Skill: pipeline, writing rules, references, helper scripts                                                                                         |
| `docs/`                                                  | Installation, configuration, Threads app setup, Sheets setup, cron, runbook                                                                                    |
| `tests/`                                                 | Unit tests for the plugin's deterministic layer                                                                                                                |
| `PROJECT_SPEC_v2_plugins.md`                             | The source-of-truth specification this implements                                                                                                              |

One `hermes plugins install` is the whole install. The plugin is a bundle — it
carries its own tools, hooks, skill and slash command, and Hermes loads all four
from this one directory. Nothing is copied into `~/.hermes/skills/`.

---

## Architecture in one picture

```
User ──► Telegram (Hermes Messaging Gateway)
              │
              ├─► /affiliate-threads status ──► threads_check (read-only, no model turn)
              │
              ▼
     Skill: affiliate-threads-generator
     (research, angles, point of view, narrative, drafting,
      antislop audit, editorial + evidence review)
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
  Both live in the same bundle. The plugin registers the skill from its own
  directory instead of publishing it to the skills hub, so there is one artifact to
  install, one to update, and no second copy that can drift.

There is also one slash command, `/affiliate-threads status`, which runs the
read-only preflight for a human.

The plugin ships two tools:

| Tool              | Purpose                                                                                                                                                   |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `threads_publish` | Re-validates the Sheet row, publishes the thread via the official Threads Graph API, then writes `Status=Done` + `Threads URL`. The only path to Threads. |
| `threads_check`   | Read-only preflight: credentials, identity, token expiry, Sheet reachability, next eligible candidate.                                                    |

Three hooks:

| Hook             | Purpose                                                                                                                                                 |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pre_llm_call`   | Injects one line naming the bundled skill when a turn looks like Affiliate Threads work — plugin skills are namespaced and absent from the skill index. |
| `pre_tool_call`  | Escalates every `threads_publish` call to Hermes' own human-approval gate.                                                                              |
| `post_tool_call` | Writes an audit line for every publish attempt to `~/.hermes/logs/agent.log`.                                                                           |

---

## Quick start

```bash
# The whole install. Hermes asks for the credentials here — the plugin declares
# them, so installing prompts for what it cannot run without. Nothing to edit,
# nothing echoed back, values go to Hermes' credential store.
hermes plugins install msyamsularif/affiliate-threads-generator --enable

# Restart the gateway so the new tools are discovered, then verify.
hermes gateway restart
hermes chat -q "Run the affiliate-threads-generator doctor script."
```

One command, because the plugin is a bundle: the tools, the hooks, the skill and
the `/affiliate-threads` command all arrive together. Nothing is written to
`~/.hermes/skills/`, so there is no second copy to install or keep in sync.

Then, from Telegram:

```
Buatkan content berikutnya.
```

To check the wiring without spending a model turn, use `/affiliate-threads status`.

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

Writing quality has one external dependency, preferred rather than required:

- The **`antislop`** and **`antislop-copywriting`** skills in the Hermes project
  (`.hermes/skills/`, then `hermes skills trust`). Without them the pipeline
  still generates, but the preview says the anti-slop layer was not loaded
  instead of claiming an audit that did not happen. Setup and version pinning:
  [`docs/antislop-integration.md`](docs/antislop-integration.md).

## Development

The deterministic layer — guardrails, the Threads client, the Sheet client, the
publish tool, the hooks — is covered by tests. None of them touch the network: the
Threads API and the Google Sheets CLI are both faked at the boundary.

Run both from the repository root:

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
| `test_skill_scripts.py`          | The doctor finds the publish ledger wherever Hermes filed it                        |
| `test_content_regression.py`     | The content corpus: templated drafts are flagged, the style target stays clean      |
| `test_integration_end_to_end.py` | The whole cycle through a real subprocess to a fake `google_api.py`                 |

Before changing anything in `guardrails.py` or `tools.py`, run both commands.
The publish path is the one place where a quiet regression reaches a live
profile.

## License

MIT — see [`LICENSE`](LICENSE).
