# ChatGPT MCP Setup

Agentic Forex Desk exposes a Streamable HTTP MCP server alongside its existing REST API. The MCP tools use local mocked candle data and risk-checked previews only. Live trading and TradeLocker execution remain disabled.

## Run locally

Create and activate a Python 3.11 virtual environment, install dependencies, and start the shared FastAPI/MCP process:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The local MCP endpoint is:

```text
http://127.0.0.1:8000/mcp
```

ChatGPT cannot connect directly to localhost. Use an HTTPS tunnel for development.

If `MCP_SHARED_SECRET` is empty, `/mcp` accepts only localhost development requests and logs a warning that authentication is disabled. A tunnel uses a public Host header and will be rejected until a shared secret is configured.

## Configure MCP authentication

Generate a strong random secret outside the source tree and set it in your local `.env` file or deployment environment:

```dotenv
MCP_SHARED_SECRET=<strong-random-secret>
```

Restart Uvicorn after changing the environment. MCP clients must then send:

```http
Authorization: Bearer <strong-random-secret>
```

Never commit `.env`, print the secret in logs, or place the secret in ChatGPT instructions. Configure it only in the connector's protected authentication/credential field. A local protocol request can be checked with:

```powershell
$headers = @{
  Authorization = "Bearer $env:MCP_SHARED_SECRET"
  Accept = "application/json, text/event-stream"
}
Invoke-WebRequest -Method Post -Uri http://127.0.0.1:8000/mcp -Headers $headers -ContentType "application/json" -Body '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"local-check","version":"1.0"}}}'
```

## Expose with ngrok

With the server running on port 8000:

```powershell
ngrok http 8000
```

If ngrok reports `https://example.ngrok-free.app`, use:

```text
https://example.ngrok-free.app/mcp
```

## Expose with Cloudflare Tunnel

With the server running on port 8000:

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

If Cloudflare reports `https://example.trycloudflare.com`, use:

```text
https://example.trycloudflare.com/mcp
```

## Connect from ChatGPT

In ChatGPT, enable developer mode for connectors/apps if your plan and workspace permit it. Add a custom MCP connector, paste the public HTTPS `/mcp` URL, configure Bearer authentication using the value of `MCP_SHARED_SECRET` in the connector's protected credential field, and complete the connection flow. ChatGPT should then discover the eight registered tools.

Current OpenAI guidance for building ChatGPT apps is available in the [Apps SDK documentation](https://developers.openai.com/apps-sdk). FastMCP documents Streamable HTTP deployment and mounting in an existing FastAPI app in its [HTTP deployment guide](https://gofastmcp.com/deployment/http).

## Safety reminders

- Live trading is disabled, regardless of MCP requests.
- TradeLocker submission is not implemented and is never called.
- Remote MCP callers cannot disable the kill switch.
- Do not put broker API keys, account credentials, webhook secrets, tokens, or other secrets in ChatGPT instructions.
- Development tunnels expose the service publicly. `MCP_SHARED_SECRET` is required for tunneled access; add stronger production authentication and hardening before broader deployment.
