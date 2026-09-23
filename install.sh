#!/usr/bin/env bash
#
# Install the Affiliate Threads plugin + its bundled Skill into Hermes.
#
#   ./install.sh                 # install plugin and skill
#   ./install.sh --plugin-only   # skip copying the skill to ~/.hermes/skills
#   ./install.sh --skill-only    # only refresh the standalone skill copy
#   ./install.sh --uninstall     # remove both
#
# Why the skill is copied twice:
#   * The plugin bundles the skill and registers it as `affiliate-threads-generator:<skill>`
#     so the plugin package is self-contained.
#   * A plain copy under ~/.hermes/skills/ gives it an unqualified name, which is
#     what cron's `--skill` flag and `/skill-name` look up.
#   Copying the same source directory keeps the two in sync on every re-run.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_SRC="${REPO_DIR}/plugins/affiliate-threads-generator"
SKILL_SRC="${PLUGIN_SRC}/skills/affiliate-threads-generator"

HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes}"
PLUGIN_DEST="${HERMES_HOME}/plugins/affiliate-threads-generator"
SKILL_DEST="${HERMES_HOME}/skills/affiliate-threads-generator"

MODE="all"
for arg in "$@"; do
  case "$arg" in
    --plugin-only) MODE="plugin" ;;
    --skill-only)  MODE="skill" ;;
    --uninstall)   MODE="uninstall" ;;
    -h|--help)
      sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "unknown option: $arg" >&2
      exit 2
      ;;
  esac
done

say() { printf '  %s\n' "$*"; }

if [ "$MODE" = "uninstall" ]; then
  echo "Removing Affiliate Threads from ${HERMES_HOME}"
  rm -rf "$PLUGIN_DEST"
  say "removed ${PLUGIN_DEST}"
  rm -rf "$SKILL_DEST"
  say "removed ${SKILL_DEST}"
  echo
  echo "Cron jobs are not touched. Review them with: hermes cron list"
  exit 0
fi

if [ ! -f "${PLUGIN_SRC}/plugin.yaml" ]; then
  echo "error: ${PLUGIN_SRC}/plugin.yaml not found — run this script from the repository root" >&2
  exit 1
fi

echo "Installing Affiliate Threads into ${HERMES_HOME}"

if [ "$MODE" != "skill" ]; then
  mkdir -p "${HERMES_HOME}/plugins"
  rm -rf "$PLUGIN_DEST"
  mkdir -p "$PLUGIN_DEST"
  # Copy the plugin tree, excluding caches and anything the user should not get.
  (cd "$PLUGIN_SRC" && tar --exclude='__pycache__' --exclude='*.pyc' -cf - .) \
    | (cd "$PLUGIN_DEST" && tar -xf -)
  say "plugin  -> ${PLUGIN_DEST}"
fi

if [ "$MODE" != "plugin" ]; then
  mkdir -p "${HERMES_HOME}/skills"
  rm -rf "$SKILL_DEST"
  mkdir -p "$SKILL_DEST"
  (cd "$SKILL_SRC" && tar --exclude='__pycache__' --exclude='*.pyc' -cf - .) \
    | (cd "$SKILL_DEST" && tar -xf -)
  say "skill   -> ${SKILL_DEST}"
fi

cat <<EOF

Next steps
----------
1. Enable the plugin. This is where Hermes collects the credentials:

     hermes plugins enable affiliate-threads-generator

   The plugin declares two variables it cannot run without (THREADS_ACCESS_TOKEN,
   AFFILIATE_SHEET_ID) via \`requires_env\`, so enabling prompts for them — with
   descriptions, a console link, and the token masked. Values are stored in
   Hermes' credential store; you never edit a file.

   Two more (THREADS_USER_ID, AFFILIATE_SHEET_TAB) have working defaults and are
   declared via \`optional_env\`, so they appear in the config UI and never gate.

   To change a value later, or to skip the prompt on purpose:

     hermes config set THREADS_ACCESS_TOKEN "THQW..."
     hermes config set AFFILIATE_SHEET_ID "1AbCdEf..."

   Full explanation, including where each kind of value belongs and why the
   standalone scripts need these in the environment: docs/credentials.md

2. Validate the install:

     hermes plugins doctor ${PLUGIN_DEST} --ci
     hermes plugins list

3. Verify the runtime wiring from a chat:

     "Run the affiliate-threads-generator doctor script."

4. Schedule the Mon/Wed/Fri/Sun 08:00 Asia/Jakarta generation run
   (see docs/cron-setup.md, or accept the suggestion with /suggestions):

     hermes cron create "0 8 * * 0,1,3,5" \\
       "Generate the next affiliate thread and send me the preview." \\
       --skill affiliate-threads-generator \\
       --name "affiliate-threads-generator" \\
       --deliver telegram

   The scheduler only generates and previews. It never publishes.

EOF
