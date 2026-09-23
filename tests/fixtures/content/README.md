# Content regression corpus

Fixtures for the deterministic half of the anti-slop improvement. They pin what a
test can honestly pin: which drafts the **guardrails** flag, and that the style
target stays clean. The prose quality itself is judged by the antislop audit, not
by a unit test.

```
before/     legal drafts that read as templated — the soft signals must fire
expected/   the style target — no violations, no structural warnings
```

Each fixture is a JSON object:

```json
{
  "note": "why this fixture exists",
  "product_id": "12",
  "product_name": "Sensory Board 30cm",
  "affiliate_url": "https://shope.ee/abc123",
  "posts": [{ "text": "..." }]
}
```

`before/` drafts deliberately pass every **hard** guardrail. That is the point:
they are publishable, and the only thing standing between them and the preview is
the editorial layer. If one of them starts failing the hard rules, the guardrails
changed behaviour rather than gaining a signal.

`expected/` is a style target, not a template. It must stay clean: if a guardrail
change starts flagging it, the change is wrong, not the fixture.

Add a fixture here whenever a generated thread reads badly in a way the signals
missed — that is the only way the corpus grows usefully.
