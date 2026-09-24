# Anti-slop integration

The pipeline's writing quality has two layers, and they are deliberately
separate:

| Layer                               | Owns                                                                 | Lives in                          |
| ----------------------------------- | -------------------------------------------------------------------- | --------------------------------- |
| `antislop` + `antislop-copywriting` | generic AI-prose tells: structure, rhythm, signposting, filler, tone | external skills, loaded by Hermes |
| `affiliate-threads-generator`       | affiliate editorial rules, evidence, publish safety                  | this plugin                       |

The generic filter is **not vendored** into this plugin, and installing it is
**optional**: using it is the recommended setup, not a requirement. Vendoring it
would mean maintaining a fork of rules that already evolve on their own, and it
would remove the choice — a user who would rather run this plugin alone can.

The plugin references the skills by name and reports on the preview whether they
were loaded, so the choice is always visible.

## Install the two skills

antislop ships as standard Agent Skills (`<name>/SKILL.md`). Hermes reads project
skills from `.hermes/skills/`, so a project layout looks like this:

```text
affiliate-agent/
├── AGENTS.md
├── .hermes/
│   └── skills/
│       ├── antislop/
│       │   └── SKILL.md
│       └── antislop-copywriting/
│           └── SKILL.md
└── affiliate-threads-generator/     ← this repository
```

Two routes install them:

```bash
# 1. The antislop installer (recommended — also writes the pointer block)
npx antislop-ai

# 2. The skills directory
npx skills add miqdadbadjuber/anti-slop
```

Then let Hermes load skills out of the project:

```bash
hermes skills trust
```

Start a fresh session afterwards — skills load when a session starts.

## Verify

```bash
hermes chat -q "Load the antislop and antislop-copywriting skills, then summarise the copywriting patterns they cover."
```

If the skills are not reachable, generation still works. The pipeline continues
through the affiliate editorial and evidence reviews, and the preview carries
`🧹 Anti-slop: not installed — affiliate editorial + evidence review only`
instead of a revision count. That line is not decoration: a draft that did not go
through the generic pass must never be presented as if it did.

## Where the layers meet

The skill's own instructions live in
`skills/affiliate-threads-generator/SKILL.md` (the dependency contract, Step 6)
and `skills/affiliate-threads-generator/references/editorial-rules.md` (the
affiliate editorial audit and the audit record).

The division of labour, in one line each:

- `antislop` and `antislop-copywriting` say **how the prose reads**.
- The affiliate editorial audit says **whether the thread is worth reading at
  all**, and whether the product earned its place.
- `guardrails.py` and `threads_publish` say **what may not ship** — and they run
  last, in code.

Anti-slop rules never override evidence, product fit, or the
fabricated-experience ban. A rewrite that removes a qualification to sound more
natural is a regression, not an improvement.

## Version pinning

Tested with the `antislop` skill **v3.2.13**. To check what is installed:

```bash
cat <project>/.hermes/skills/antislop/VERSION
```

antislop does not update itself. When you update it (run the install command
again), re-run the content corpus and the manual scorecard in
`skills/affiliate-threads-generator/references/editorial-rules.md`, then update
the version recorded here.

## What is _not_ in this integration

- No copy of antislop's rules inside the plugin, and no second blacklist in
  `guardrails.py`. The code layer keeps a short list of affiliate clichés and four
  structural counters; everything else is the external skills' job.
- No hard ban on ordinary words ("jadi", "contoh", "makanya"). The structural
  signals are thresholds, and they are warnings, never blocks.
- No new publishing path. `threads_publish` is still the only route to Threads,
  and human approval is still the gate in front of it.
