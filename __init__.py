"""Affiliate Threads — Hermes plugin registration.

The plugin's whole reason to exist is one irreversible side effect: publishing
to Meta Threads. Everything else this system does is a Skill built on Hermes'
existing capabilities.

    register(ctx)  ->  two tools, three hooks, one bundled skill, one command

The bundle is the unit of installation. ``hermes plugins install`` is the only
command a user runs: the skill is registered from here rather than published to
the skills hub, so there is no second copy to install, update, or let drift.

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
``pre_llm_call``
    Points the agent at the bundled skill when a turn looks like Affiliate
    Threads work. Plugin skills are namespaced and absent from the skill index,
    so this is what makes the bundle self-sufficient.
``pre_tool_call``
    Escalates every publish to Hermes' human-approval gate, so approval is
    enforced by the runtime and not by a prompt the model might ignore.
``post_tool_call``
    Audit trail for publish attempts.

Command
-------
``/affiliate-threads status``
    The read-only preflight, run by a human without spending a model turn.
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import commands, hooks, schemas, tools

logger = logging.getLogger(__name__)

TOOLSET = "affiliate_threads"

#: In-session slash command. Shorter than the plugin id because it is typed.
COMMAND_NAME = "affiliate-threads"

#: Skills bundled with the plugin. Each entry is a directory name under
#: ``skills/`` holding a ``SKILL.md``. Hermes exposes it as
#: ``<plugin-id>:<directory-name>`` — see ``hooks.SKILL_ID``.
BUNDLED_SKILLS = ("affiliate-threads-generator",)


def register(ctx) -> None:  # noqa: ANN001 - PluginContext is host-provided
    """Wire tools, hooks, the command and bundled skills into Hermes.

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

    ctx.register_hook("pre_llm_call", hooks.on_pre_llm_call)
    ctx.register_hook("pre_tool_call", hooks.on_pre_tool_call)
    ctx.register_hook("post_tool_call", hooks.on_post_tool_call)

    # A lambda because the host calls a command handler with the raw argument
    # string alone; the command needs the context to dispatch through the tool
    # registry, so it is closed over here.
    ctx.register_command(
        COMMAND_NAME,
        handler=lambda raw_args: commands.handle(ctx, raw_args),
        description="Affiliate Threads: setup status and the next eligible candidate",
        args_hint="[status]",
    )

    # Hermes namespaces this as `<plugin>:<skill>` (``hooks.SKILL_ID``), which is
    # the only name the agent ever needs. Nothing is copied into
    # ~/.hermes/skills/, so there is no second copy to update.
    skills_dir = Path(__file__).resolve().parent / "skills"
    for name in BUNDLED_SKILLS:
        skill_md = skills_dir / name / "SKILL.md"
        if skill_md.exists():
            ctx.register_skill(name, skill_md)
            logger.debug("registered bundled skill %s from %s", name, skill_md)
        else:
            logger.warning("bundled skill %s missing at %s", name, skill_md)

    logger.info(
        "affiliate-threads-generator ready (tools: threads_publish, threads_check; "
        "skill: %s; command: /%s)",
        hooks.SKILL_ID,
        COMMAND_NAME,
    )
