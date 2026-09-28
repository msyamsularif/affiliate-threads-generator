# Content regression corpus

Fixtures for the deterministic half of the anti-slop and anti-template work.
They pin what a test can honestly pin: which drafts the **guardrails** flag, and
that the style target stays clean. The prose quality itself is judged by the
antislop audit, not by a unit test.

```
before/     legal drafts that read as templated — the soft signals must fire
expected/   the style target — no violations, no structural warnings
blocked/    drafts a hard rule must refuse — each names the violation code it pins
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

Optional fields:

| Field               | Used by                                                                |
| ------------------- | ---------------------------------------------------------------------- |
| `recent`            | the cross-thread signals — recent content notes, newest first          |
| `experience`        | `firsthand` fixtures, with `testimonial`; default validates as `none`  |
| `testimonial`       | the stored testimony a `firsthand` fixture may draw on                 |
| `expect_violations` | `blocked/` fixtures only: the violation codes the draft exists to trip |

`before/` drafts deliberately pass every **hard** guardrail. That is the point:
they are publishable, and the only thing standing between them and the preview is
the editorial layer. If one of them starts failing the hard rules, the guardrails
changed behaviour rather than gaining a signal.

`expected/` is a style target, not a template. It must stay clean — the
anti-template diversity signals included, not just the older structural ones. If
a guardrail change starts flagging one, the change is wrong, not the fixture. The
fixtures deliberately cover different angles, categories, structures, post
counts, product-entry positions, CTA shapes and experience modes, so they
demonstrate a range rather than a house style.

`blocked/` are the drafts that must never reach a preview: fake personal
experience, guarantee language. They carry no "clean" expectation; the test
asserts the named violation codes are present.

Add a fixture here whenever a generated thread reads badly in a way the signals
missed — that is the only way the corpus grows usefully.
