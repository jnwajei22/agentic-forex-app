# ChatGPT MCP OAuth Setup

Agentic Forex Desk exposes a Streamable HTTP MCP server at `https://mcp.justinnwajei.com/mcp/`. It uses mocked market data and risk-checked order previews only. Live trading, TradeLocker execution, and the kill-switch mutation tool are not exposed to ChatGPT.

## Configure an OAuth provider

Use an external OIDC/OAuth provider such as Auth0. `AUTH_ISSUER` is required whenever `MCP_REQUIRE_OAUTH=true` and must be the real issuer URL published by that provider; it is not the MCP server URL and cannot be a placeholder. Do not place a client secret in this server: the MCP server is the protected resource and verifies access tokens issued to ChatGPT.

If OAuth is required and `AUTH_ISSUER` is empty, the protected-resource metadata endpoint returns a `503` configuration error. This prevents it from advertising an empty `authorization_servers` list, which ChatGPT cannot use to begin OAuth discovery.

For Auth0:

1. Create an API with the identifier (audience) `https://mcp.justinnwajei.com`, or use another audience and set `AUTH_AUDIENCE` to it.
2. Add API permissions named `forex:read` and `forex:preview`.
3. Create or configure an application that ChatGPT can use with OAuth authorization code flow and PKCE. Add the callback URL shown by ChatGPT when creating the connector.
4. Ensure issued access tokens are JWTs, include the granted permissions in the `scope` claim, and use an asymmetric signing algorithm such as RS256.
5. Use the provider's exact issuer URL, including a trailing slash when the provider publishes one.

Configure the deployment environment:

```dotenv
MCP_REQUIRE_OAUTH=true
MCP_ALLOW_PUBLIC_NO_AUTH=false
AUTH_ISSUER=https://agentic-forex.us.auth0.com/
AUTH_AUDIENCE=https://mcp.justinnwajei.com
AUTH_JWKS_URL=https://agentic-forex.us.auth0.com/.well-known/jwks.json
```

Replace `agentic-forex.us.auth0.com` with the domain assigned by Auth0, or use the issuer and JWKS URL published by your chosen OIDC/OAuth provider. Preserve the issuer's trailing slash when the provider publishes one; JWT issuer validation requires an exact match.

The audience defaults to `https://mcp.justinnwajei.com` when `AUTH_AUDIENCE` is empty. Restart the server after changing these values.

The public protected-resource metadata document is available at:

```text
https://mcp.justinnwajei.com/.well-known/oauth-protected-resource
```

It identifies the configured authorization server and the supported `forex:read` and `forex:preview` scopes. An unauthenticated request to `/mcp/` receives a `401` response pointing ChatGPT to that metadata document through `WWW-Authenticate`.

## Connect from ChatGPT

In ChatGPT, enable developer mode for connectors/apps if your plan and workspace permits it. Create a custom MCP connector using:

```text
https://mcp.justinnwajei.com/mcp/
```

Choose OAuth and enter the client/provider values requested by ChatGPT. Request both `forex:read` and `forex:preview` so all connector tools are available. In addition to the forex analysis tools, the server exposes read-only TradeLocker config, symbol, quote, and candle tools under `forex:read` when TradeLocker credentials are configured.

TradeLocker account discovery is a two-step flow. Configure `TRADELOCKER_BASE_URL`, `TRADELOCKER_USERNAME`, `TRADELOCKER_PASSWORD`, and `TRADELOCKER_SERVER`, then run `get_tradelocker_accounts`. Copy the returned `accountId` and `accNum` into `TRADELOCKER_ACCOUNT_ID` and `TRADELOCKER_ACCOUNT_NUMBER` before using account-specific config, status, positions, symbols, quotes, or candles. Discovery never returns the configured password or TradeLocker tokens.

- `get_forex_watchlist`, `scan_forex_watchlist`, `generate_chart`, `get_account_status`, `get_open_positions`, and `get_trade_log` with `forex:read`
- `review_forex_order` with `forex:preview`

`set_kill_switch` and TradeLocker execution tools are intentionally not registered with the MCP server.

TradeLocker market data is opt-in. Keep `MARKET_DATA_PROVIDER=mock` (the default) unless you explicitly want scans and charts to read TradeLocker candles. No setting enables TradeLocker order submission.

## Run locally

Install dependencies and start the combined FastAPI/MCP process:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

OAuth remains required on localhost by default. For a local or manual client that cannot perform OAuth, the existing shared-secret mode is available only when explicitly selected:

```dotenv
MCP_REQUIRE_OAUTH=false
MCP_ALLOW_PUBLIC_NO_AUTH=false
MCP_SHARED_SECRET=<strong-random-test-secret>
```

Send that secret as `Authorization: Bearer <strong-random-test-secret>`. Never use shared-secret mode for the ChatGPT connector. Public no-auth mode remains an explicit test-only escape hatch and is disabled by default; OAuth takes precedence while `MCP_REQUIRE_OAUTH=true`.

## Safety reminders

- Live trading remains disabled regardless of MCP requests.
- No MCP tool calls TradeLocker or submits an order.
- Do not put broker credentials, OAuth tokens, client secrets, webhook secrets, or shared secrets in ChatGPT instructions.
- Keep `MCP_ALLOW_PUBLIC_NO_AUTH=false` for every public deployment.
