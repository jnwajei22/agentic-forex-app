# Agentic Forex Desk Frontend

Minimal Next.js onboarding UI for the Agentic Forex Desk Raspberry Pi backend. Authentication and access-token forwarding happen on the Next.js server. TradeLocker passwords are submitted directly through a same-origin server proxy and are never written to localStorage or sessionStorage.

## Local setup

Requirements: Node.js 20 LTS or newer and an Auth0 **Regular Web Application**.

```powershell
Copy-Item .env.example .env.local
npm install
npm run dev
```

Configure `.env.local`:

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://api.agenticforexdesk.com
AUTH0_SECRET=<64-hex-character-session-secret>
APP_BASE_URL=http://localhost:3000
AUTH0_DOMAIN=YOUR_TENANT.auth0.com
AUTH0_CLIENT_ID=<regular-web-app-client-id>
AUTH0_CLIENT_SECRET=<regular-web-app-client-secret>
AUTH0_AUDIENCE=https://mcp.justinnwajei.com
```

`AUTH0_AUDIENCE` must equal the Raspberry Pi backend's `AUTH_AUDIENCE`. Generate `AUTH0_SECRET` with `openssl rand -hex 32` or another cryptographically secure generator.

In the Auth0 application, add:

- Allowed callback URL: `http://localhost:3000/auth/callback`
- Allowed logout URL: `http://localhost:3000`
- Allowed web origin: `http://localhost:3000`

The `/login` page starts Auth0's `/auth/login` flow. Protected pages verify the server-side session. Calls under `/api/backend/*` are allowlisted proxy routes that attach the session access token as `Authorization: Bearer <token>` when calling the backend.

## Vercel deployment

1. Import the repository into Vercel and set the project root directory to `frontend`.
2. Add every variable from `.env.example` in Vercel Project Settings. Keep all `AUTH0_*` variables server-only; only `NEXT_PUBLIC_API_BASE_URL` is browser-visible.
3. Set `APP_BASE_URL` to the stable frontend domain, for example `https://app.agenticforexdesk.com`.
4. Add `https://app.agenticforexdesk.com/auth/callback` to Auth0 Allowed Callback URLs.
5. Add `https://app.agenticforexdesk.com` to Auth0 Allowed Logout URLs and Allowed Web Origins.
6. Configure the Raspberry Pi backend with `FRONTEND_ORIGIN=https://app.agenticforexdesk.com` and expose it through Cloudflare Tunnel at the URL in `NEXT_PUBLIC_API_BASE_URL`.
7. Deploy, log in, connect TradeLocker, discover accounts, and select one. The dashboard should then show `connected` and the selected account.

For Vercel preview URLs, register each callback URL in Auth0 or use a controlled preview-domain strategy. Never put `AUTH0_CLIENT_SECRET`, backend `BROKER_SECRET_KEY`, TradeLocker credentials, or access tokens in `NEXT_PUBLIC_*` variables.

## Pages

- `/` landing page
- `/login` Auth0 login entry
- `/dashboard` user and broker status
- `/connect-tradelocker` credential onboarding
- `/select-account` account discovery and selection
- `/settings` update or remove the broker connection

This frontend provides charting-platform onboarding only. It contains no payments or trade-execution functionality.
