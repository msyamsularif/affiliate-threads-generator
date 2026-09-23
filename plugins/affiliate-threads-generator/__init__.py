"""Affiliate Threads — Hermes plugin registration.

The plugin's whole reason to exist is one irreversible side effect: publishing
to Meta Threads. Everything else this system does is a Skill built on Hermes'
existing capabilities.

    register(ctx)  ->  two tools, two hooks, one bundled skill

Tools
-----
``threads_publish``
    The only path to Meta Threads. Re-validates the Sheet's own state, enforces
    the hard content guardrails, publishes through the official Graph API, and
    records the outcome back into the Sheet.
``threads_check``
    Read-only preflight: credentials, identity, token expiry, Sheet reachability
    and the next eligible candidate.

Hooks
-----
``pre_tool_call``
    Escalates every publish to Hermes' human-approval gate, so approval is
    enforced by the runtime and not by a prompt the model might ignore.
``post_tool_call``
    Audit trail for publish attempts.
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import hooks, schemas, tools

logger = logging.getLogger(__name__)

TOOLSET = "affiliate_threads"

#: Skills bundled with the plugin. Each entry is a directory name under
#: ``skills/`` holding a ``SKILL.md``.
BUNDLED_SKILLS = ("affiliate-threads-generator",)


def register(ctx) -> None:  # noqa: ANN001 - PluginContext is host-provided
    """Wire tools, hooks and bundled skills into Hermes.

    Called exactly once at startup. Any exception here disables the plugin but
    leaves Hermes itself running.
    """
    # The plugin needs its own settings and plugin-scoped state at tool-call
    # time. Handlers only receive (args, **kwargs), so the context is bound here
    # and read back through runtime.py.
    from . import runtime

    runtime.bind(ctx)

    ctx.register_tool(
        name="threads_publish",
        toolset=TOOLSET,
        schema=schemas.THREADS_PUBLISH,
        handler=tools.threads_publish,
    )
    ctx.register_tool(
        name="threads_check",
        toolset=TOOLSET,
        schema=schemas.THREADS_CHECK,
        handler=tools.threads_check,
    )

    ctx.register_hook("pre_tool_call", hooks.on_pre_tool_call)
    ctx.register_hook("post_tool_call", hooks.on_post_tool_call)

    skills_dir = Path(__file__).resolve().parent / "skills"
    for name in BUNDLED_SKILLS:
        skill_md = skills_dir / name / "SKILL.md"
        if skill_md.exists():
            ctx.register_skill(name, skill_md)
            logger.debug("registered bundled skill %s from %s", name, skill_md)
        else:
            logger.warning("bundled skill %s missing at %s", name, skill_md)

    logger.info(
        "affiliate-threads-generator ready (tools: threads_publish, threads_check; skills: %s)",
        ", ".join(BUNDLED_SKILLS),
    )
