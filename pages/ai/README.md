# ai: usage of one AI provider

User documentation: [docs/en/templates/ai.md](../../docs/en/templates/ai.md) ([Deutsch](../../docs/de/templates/ai.md)). Developer notes below.

```yaml
- type: ai
  provider: claude                # required, a key of PROVIDERS in page.py
  # key: ${OPENAI_ADMIN_KEY}      # anthropic-api, openai-api, xai-api (always ${VAR})
  # budget: 50                    # anthropic-api, openai-api: optional USD budget bar
  # team_id: ${XAI_TEAM_ID}       # xai-api
  # username: ${GITHUB_USER}      # copilot (with key: ${GITHUB_COPILOT_TOKEN})
  # monthly_allowance: 1500       # copilot: required, the plan's allowance
  # unit: premium-requests        # copilot: default ai-credits
  # title: Claude Max             # default: the provider's NAME
  # show: remaining               # default used; bars count down from 100 %
  # lang: en                      # default: top-level lang
  refresh: 30                     # claude only reads the push inbox, so this is cheap
```

- `page.py` validates `provider` and `lang`, then delegates `validate` and `fetch` to the module in `PROVIDERS`. A new provider is a module in `providers/` with `NAME`, `validate(options)` and `fetch(options, ctx)`, plus one line in `PROVIDERS`. `options["lang"]` is already resolved when the provider's `fetch` runs.
- Providers return any of the keys `rows`, `big`, `stand`, `message`, `sub`, `alert` (see `EMPTY` in `page.py`); the page fills in the rest, `title` and `clock`. `message` replaces the body with a notice.
- `show: remaining` is applied in `page.fetch`, not in the providers: each row's `percent` (share used) becomes `max(0, 100 - used)`, the text `N %` or the row's own `remaining_text` (copilot's counts), and the row gets `used`, which `ui.bar(..., used=)` takes for the color. In `used` mode `remaining_text` is dropped.
- `theme: "claude"` (set by `claude` and `anthropic-api`, also on notices) makes `template.html` add the claude.ai dark look: a CSS block and `serif_face_css()` (DejaVu Serif Bold, embedded only here, so other pages do not grow by ~470 KB). Bars are orange, `ui-warn` and `ui-bad` both red. No logo.
- `claude` reads `ctx.pushed("claude")`. The data comes from `tools/statusline/glancebox-statusline.sh` (or `.ps1`), which posts Claude Code's status-line JSON, or from the usage hook script `tools/statusline/glancebox-usage.sh` (or `.ps1`), which posts the `usage_report` line of `claude -p "/usage"` (experimental in Claude Code), both to `/api/v1/push/claude`; the server keeps only `rate_limits` and `usage_report` (`PUSH_KEYS`). A push with `usage_report` is read in that format, otherwise `rate_limits`; rows, reset text and notices are the same for both. Field names and units are documented at the top of `providers/claude.py`.
- The status-line script only sends JSON that contains `"rate_limits"` and the usage hook script only a line that contains `"usage_report"`, so a new session (no limits before its first answer) or a failed fetch does not wipe the values on the display.
- `anthropic-api`, `openai-api`, `xai-api` and `copilot` share `providers/_cost.py`: a per-process cache of the last successful result for `CACHE_S` = 300 s and of a failure for `FAIL_CACHE_S` = 60 s (a bad key does not hit the provider every refresh), keyed by (provider, sha256(key), and the `CACHE_SCOPE` options team_id, username, unit), the money format, the budget row and the `No data` notice (red header). Errors are logged with exception type and HTTP status only, never the exception text, so keys cannot reach the log. Endpoints, headers, fields and pagination are documented at the top of each provider module. `MIN_REFRESH` stays 0 because `claude` needs 30 s.
- `copilot` uses GitHub's documented billing usage endpoints (`ai_credit` or `premium_request`, fine-grained token with the user permission `Plan` read per the REST reference; a GitHub tutorial claims classic tokens only, so the docs offer a classic token as fallback on 403). They report usage only; no documented endpoint returns the entitlement (the Copilot SDK's `account.getQuota` is JSON-RPC into a running Copilot CLI, and `copilot_internal/*` is undocumented), so `monthly_allowance` is a required option.
