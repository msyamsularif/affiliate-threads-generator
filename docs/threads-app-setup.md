# Meta Threads app setup

You need a Threads user access token with two scopes. The token is what
`threads_publish` uses; nothing else in this system touches the Threads API.

## Scopes

| Scope                     | Needed for                                      |
| ------------------------- | ----------------------------------------------- |
| `threads_basic`           | `GET /me`, `GET /{media-id}` (permalink lookup) |
| `threads_content_publish` | Creating containers and publishing              |

`threads_manage_replies`, `threads_read_replies` and `threads_manage_insights`
are **not** needed. The plugin does not read replies or insights.

## 1. Create the Meta app

1. Go to <https://developers.facebook.com/apps> and create an app.
2. Choose the **Threads** use case.
3. When the app is created you get two pairs of credentials. Use the **Threads**
   app id and its matching app secret — not the Facebook ones.

Note the Threads app secret: the one-time token exchange in step 4 needs it.

## 2. Add yourself as a Threads tester

While the app is in development, only testers can authorize it.

1. App Dashboard → **App roles** → **Roles** → **Add People** → **Threads Tester**.
2. Invite your Threads account.
3. Accept the invitation at <https://www.threads.net/settings/account> →
   **Website permissions**.

Without this step the authorization window will refuse you.

## 3. Authorize and get a short-lived token

Implement or use the authorization window. The open-source
[Threads API sample app](https://github.com/fbsamples/threads_api) is the fastest
path — it handles the redirect and prints a token.

The flow:

```
GET https://threads.net/oauth/authorize
      ?client_id=<THREADS_APP_ID>
      &redirect_uri=<REDIRECT_URI>
      &scope=threads_basic,threads_content_publish
      &response_type=code
```

Then exchange the returned `code`:

```
POST https://graph.threads.net/oauth/access_token
      client_id=<THREADS_APP_ID>
      client_secret=<THREADS_APP_SECRET>
      grant_type=authorization_code
      redirect_uri=<REDIRECT_URI>
      code=<CODE>
```

You get a **short-lived token, valid for 1 hour**. Move fast, or start over.

## 4. Exchange it for a long-lived token (60 days)

```bash
export THREADS_APP_SECRET=<THREADS_APP_SECRET>

python3 "$HERMES_HOME/skills/affiliate-threads-generator/scripts/threads_token.py" \
  exchange --short-token <SHORT_LIVED_TOKEN> --write-env
```

The script calls the official exchange endpoint, prints the token's lifetime, and
with `--write-env` writes `THREADS_ACCESS_TOKEN=...` into `$HERMES_HOME/.env`
(mode 0600), preserving everything else in the file.

The equivalent Hermes-native way, if you would rather not let a script touch the
credential store:

```bash
# Without --write-env the script prints the token; pipe it in yourself.
hermes config set THREADS_ACCESS_TOKEN "THQW..."
```

Either route ends in the same place. `.env` and the credential store are the same
file — `hermes config set` just routes a registered name there for you, and also
works when you have configured an external secret manager instead. See
[credentials.md](credentials.md).

Without `--write-env` the script prints the token so you can paste it yourself. It
never prints the full token when it has written it to disk.

## 5. Resolve the user id

Optional — the plugin resolves it from `GET /me` and caches it. Pinning it is
useful when several accounts share a token file.

```bash
python3 "$HERMES_HOME/skills/affiliate-threads-generator/scripts/threads_token.py" status
```

```json
{
  "ok": true,
  "user_id": "1234567890",
  "username": "yourhandle",
  "token_valid": true,
  "expires_at": "2026-11-22T08:00:00+00:00",
  "days_remaining": 60.0,
  "scopes": ["threads_basic", "threads_content_publish"]
}
```

Copy `user_id` into the credential store as `THREADS_USER_ID` if you want it pinned:

```bash
hermes config set THREADS_USER_ID "1234567890"
```

## 6. Restart the gateway

```bash
hermes gateway restart
hermes chat -q "Run threads_check."
```

## Keeping the token alive

A long-lived token lasts **60 days** and can be refreshed at any time — even a
day after it was issued — for another 60 days. Refreshing resets the clock, so a
monthly job is plenty.

```bash
python3 "$HERMES_HOME/skills/affiliate-threads-generator/scripts/threads_token.py" \
  refresh --write-env
```

Then restart the gateway so the new value is loaded:

```bash
hermes gateway restart
```

### Automate it

A script-only cron job, no LLM involved:

```bash
hermes cron create "0 9 1 * *" \
  "Refresh the Threads token" \
  --no-agent \
  --script refresh-threads-token.sh \
  --deliver telegram \
  --name "threads-token-refresh"
```

`$HERMES_HOME/scripts/refresh-threads-token.sh`:

```bash
#!/bin/bash
# Refresh the Threads token and stay quiet unless it fails.
set -euo pipefail
SKILL="$HERMES_HOME/skills/affiliate-threads-generator/scripts/threads_token.py"
OUT="$(python3 "$SKILL" refresh --write-env)"
DAYS="$(python3 -c "import json,sys;print(json.loads(sys.argv[1]).get('expires_in',0)//86400)" "$OUT")"
if [ "$DAYS" -lt 40 ]; then
  echo "Threads token refresh looks wrong: only ${DAYS} days granted. Output: $OUT"
fi
# Empty stdout = silent tick.
```

**One thing this job needs that the others do not.** Cron children — `no_agent`
scripts included — run with a sanitized environment, so `THREADS_ACCESS_TOKEN` is
not inherited from `.env` by default. Declare it:

```yaml
# ~/.hermes/config.yaml
terminal:
  env_passthrough:
    - THREADS_ACCESS_TOKEN
```

Without that line the refresh script exits with `THREADS_ACCESS_TOKEN is not set`
and cron delivers the failure alert. (The skill's own scripts do not need this:
they are forwarded automatically because the skill declares the variable in its
`required_environment_variables`.)

Restart the gateway after the refresh so the running process picks up the new
value:

```bash
hermes gateway restart
```

Cron scripts run with a sanitized environment, so `THREADS_ACCESS_TOKEN` from
`.env` is not inherited by the script — which is fine, because the script reads
the token from the same `.env` through the plugin's config layer.

## Scopes: what a missing one looks like

| Error                                                                   | Missing scope             |
| ----------------------------------------------------------------------- | ------------------------- |
| `(#10) Application does not have permission for this action` on publish | `threads_content_publish` |
| `GET /me` fails with an auth error                                      | `threads_basic`           |

Both are fixed by re-authorizing with the correct scope list — a token cannot be
widened after the fact.

## Production note

While the app is in development mode, only testers can authorize it. That is fine
for this system: it publishes to one operator's account. You do **not** need App
Review unless other people will authorize the app with their own Threads accounts.

## Security

- The token lives only in Hermes' credential store (`$HERMES_HOME/.env`, or an
  external secret manager if you configured one). It is never in `config.yaml`,
  never in a plugin setting, and never in plugin state.
- The plugin never logs it. Errors carry the API's own message, not the token.
- `threads_check` reports whether credentials are configured, never their value.
- Cron and `terminal` children run with a sanitized environment — Hermes-managed
  credentials are not inherited unless a skill or `terminal.env_passthrough`
  declares them.
- Full mechanism: [credentials.md](credentials.md).
