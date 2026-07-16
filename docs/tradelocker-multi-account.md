# TradeLocker multi-account model

Agentic Forex Desk stores every TradeLocker connection and every account discovered through it. Credentials remain encrypted at rest. Broker account IDs are internal routing data; authenticated APIs and MCP account selection use durable public IDs and case-insensitive account aliases.

## Resolution rules

Read operations resolve one immutable account context from exactly one of:

1. an `account_alias` supplied by the user;
2. an execution profile public ID or name; or
3. the user's single default analysis account.

Resolution is tenant-scoped and fails closed when the connection or account is disabled, the broker no longer reports the account, or the selector belongs to another user. Cache identity includes the user, connection, stored account record, raw broker account pair, environment, and server.

## Discovery and migration

Discovery upserts the unique `(connection, broker account ID, accNum)` identity. It updates broker metadata while preserving the public account ID, alias, default selection, and profile bindings. Accounts omitted by a later discovery are marked unavailable rather than deleted.

On first startup, the former one-connection schema is migrated in place. Its encrypted credential value is copied without decryption or reconnection, the selected account becomes the default analysis account, the `hourly_forex_v1` strategy template is seeded, and a read-only execution profile is created for the migrated selection.

## MCP selectors

The safe account-facing tools are:

- `list_my_tradelocker_connections`
- `list_my_tradelocker_accounts`
- `get_account_status(account_alias=None)`
- `get_open_positions(account_alias=None)`
- `get_pending_orders(account_alias=None)`
- `list_execution_profiles`

Aliases are the only account selector accepted by read tools. Profile creation and mutation are intentionally limited to the authenticated web API and dashboard. This refactor adds no live broker-write capability; the existing demo-only execution safety boundary is unchanged.
