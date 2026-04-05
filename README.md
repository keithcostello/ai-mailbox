# AI Mailbox

MCP server for inter-AI messaging between Claude Desktop instances. Send messages, reply in threads, organize by project. OAuth 2.1 authentication — no API keys needed.

## How It Works

Two Claude Desktop instances connect to the same server. Each person logs in via browser (OAuth 2.1). Keith's AI can send messages to Amy's AI, and vice versa. Messages are organized by project and support threaded conversations.

## Tools

| Tool | What it does |
|------|-------------|
| `send_message` | Send a message to the other person |
| `check_messages` | Check your inbox (marks messages as read) |
| `reply_to_message` | Reply to a specific message (keeps the thread) |
| `get_thread` | See the full conversation from any message |
| `whoami` | Check your identity and unread counts |

No API keys in tool calls — your identity comes from the OAuth login.

## Setup (for Amy)

### 1. Connect in Claude Desktop

Go to **Settings > MCP > Add Custom Connector** and enter:

- **Name:** AI Mailbox
- **URL:** *(Keith will give you the Railway URL)*

### 2. Log in

When you first use the connector, a browser popup will open. Log in with:
- **Username:** amy
- **Password:** *(Keith will give you the password)*

### 3. Try it

Tell your Claude: "Check my messages" or "Send Keith a message about dinner plans"

No special project instructions needed — your identity is automatic from the login.

## Deploy (for Keith)

### 1. Push to GitHub

```bash
git init && git add . && git commit -m "Initial AI Mailbox"
git remote add origin https://github.com/YOUR_USER/ai-mailbox.git
git push -u origin main
```

### 2. Deploy on Railway

1. Create new project on [railway.com](https://railway.com)
2. Add a **PostgreSQL** plugin
3. Add a new service from your GitHub repo
4. Set environment variables:

```
DATABASE_URL=<auto-set by Railway Postgres plugin>
MAILBOX_JWT_SECRET=<generate: python -c "import secrets; print(secrets.token_urlsafe(48))">
MAILBOX_KEITH_PASSWORD=<choose a password>
MAILBOX_AMY_PASSWORD=<choose a password>
```

5. Generate a public domain for the service
6. Your MCP URL will be: `https://YOUR-SERVICE.up.railway.app/mcp`

## Development

```bash
pip install -e ".[dev]"
pytest -v   # 42 tests
```

## Architecture

```
src/ai_mailbox/
  config.py          # Environment config
  oauth.py           # OAuth 2.1 provider (login, tokens, PKCE)
  server.py          # FastMCP wiring + health + login endpoints
  db/
    schema.py        # Migration runner (SQLite + PostgreSQL)
    queries.py       # All SQL operations
    connection.py    # DB abstraction (SQLite/PostgreSQL)
    migrations/
      001_initial.sql  # Users + messages tables
      002_oauth.sql    # OAuth tables (clients, codes, tokens)
  tools/
    send.py          # send_message
    inbox.py         # check_messages
    reply.py         # reply_to_message
    thread.py        # get_thread
    identity.py      # whoami
```
