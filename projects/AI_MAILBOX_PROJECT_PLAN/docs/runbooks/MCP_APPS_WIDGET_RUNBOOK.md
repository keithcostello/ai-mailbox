# MCP Apps Widget Runbook

How to build an interactive HTML widget that renders inside Claude (claude.ai, Claude Desktop, ChatGPT) via the MCP Apps extension.

## Prerequisites

- MCP server using FastMCP (Python `mcp>=1.9.0`, we use 1.27.0)
- Server deployed with Streamable HTTP transport (Railway, etc.)
- Server registered as a custom connector in claude.ai Settings > Connectors

## Architecture

```
User prompt → Claude calls tool → Host sees _meta.ui.resourceUri
  → Host fetches ui:// resource via resources/read
  → Host renders HTML in sandboxed iframe (claudemcpcontent.com)
  → Widget communicates via postMessage (JSON-RPC)
  → Widget calls server tools via host proxy
```

## Step 1: Create the Widget HTML

**File:** `src/ai_mailbox/ui/inbox_widget.html`

### Critical Rules

1. **ALL CSS must be inline** — Claude's CSP blocks external stylesheets even if declared in `resourceDomains`
2. **ALL JS must be inline** — Claude's CSP blocks external scripts (including the official ext-apps SDK from CDN)
3. **No external dependencies** — the HTML file must be 100% self-contained
4. **Render static content immediately** — don't wait for JS to show initial content. The iframe starts `visibility: hidden` and only becomes visible after the handshake completes.

### Inline MCP Apps Client

Instead of importing `@modelcontextprotocol/ext-apps`, implement the postMessage protocol directly:

```javascript
const MCPApp = {
    _reqId: 1,
    _pending: {},
    ontoolresult: null,

    connect() {
        window.addEventListener("message", (e) => this._handleMessage(e));
        // View sends ui/initialize TO the host
        var initId = this._reqId++;
        this._pending[initId] = {
            resolve: (result) => {
                // Send initialized notification
                window.parent.postMessage({
                    jsonrpc: "2.0",
                    method: "ui/notifications/initialized"
                }, "*");
            },
            reject: (err) => console.error("Init failed:", err)
        };
        window.parent.postMessage({
            jsonrpc: "2.0",
            method: "ui/initialize",
            id: initId,
            params: {
                protocolVersion: "2026-01-26",
                appInfo: { name: "My Widget", version: "1.0.0" },
                appCapabilities: {}
            }
        }, "*");
    },

    _handleMessage(event) {
        const msg = event.data;
        if (!msg || typeof msg !== "object") return;

        // Tool result notifications (multiple possible method names)
        if (msg.method === "ui/notifications/tool-result" ||
            msg.method === "ui/toolResult" ||
            msg.method === "notifications/ui/toolResult") {
            if (this.ontoolresult) this.ontoolresult(msg.params);
            return;
        }

        // Responses to our requests
        if (msg.id !== undefined && this._pending[msg.id]) {
            const { resolve, reject } = this._pending[msg.id];
            delete this._pending[msg.id];
            if (msg.error) reject(new Error(msg.error.message));
            else resolve(msg.result);
        }
    },

    async callServerTool(params) {
        const id = this._reqId++;
        return new Promise((resolve, reject) => {
            this._pending[id] = { resolve, reject };
            window.parent.postMessage({
                jsonrpc: "2.0",
                method: "tools/call",
                params: params,
                id
            }, "*");
            setTimeout(() => {
                if (this._pending[id]) {
                    delete this._pending[id];
                    reject(new Error("Timeout"));
                }
            }, 30000);
        });
    }
};
```

### Handshake Protocol

```
View → Host:  ui/initialize { protocolVersion, appInfo, appCapabilities }
Host → View:  response with host capabilities
View → Host:  ui/notifications/initialized
Host → View:  ui/notifications/tool-result { content, structuredContent }
```

**Critical:** The `protocolVersion` must be `"2026-01-26"` (not just a date string — use the spec version).

## Step 2: Register the Resource

In `server.py`:

```python
from pathlib import Path

WIDGET_URI = "ui://ai-mailbox/inbox.html"

@mcp.resource(
    WIDGET_URI,
    name="Inbox Widget",
    description="Interactive inbox",
    mime_type="text/html;profile=mcp-app",
    meta={"ui": {}},
)
def widget_resource() -> str:
    return Path(__file__).parent.joinpath("ui", "inbox_widget.html").read_text("utf-8")
```

### Key Details

- **MIME type MUST be** `text/html;profile=mcp-app` — this is how the host identifies MCP Apps resources
- **URI scheme MUST be** `ui://` — standard scheme for MCP Apps resources
- `meta={"ui": {}}` — no CSP needed if everything is inlined

## Step 3: Attach Widget to Tool

```python
@mcp.tool(meta={
    "ui": {"resourceUri": WIDGET_URI},
    "ui/resourceUri": WIDGET_URI,  # Legacy key for older hosts
})
def my_tool(...) -> CallToolResult:
    result = do_work()
    result_json = json.loads(json.dumps(result, default=str))
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(result_json))],
        structuredContent=result_json,
    )
```

### Key Details

- **Both `ui.resourceUri` (nested) and `ui/resourceUri` (flat) keys** — older hosts check the flat key
- **Return `CallToolResult` with `structuredContent`** — not a plain dict. The widget receives data via `structuredContent`.
- **Serialize through `json.dumps(default=str)`** — UUIDs and datetimes are not JSON-serializable by default

## Step 4: Verify in claude.ai Settings

After deploying, check Settings > Connectors > Your Connector:

- Tool should appear under **"Interactive tools"** (not "Other tools")
- This confirms claude.ai detected the `_meta.ui.resourceUri` on the tool

## Gotchas & Lessons Learned

### CSP Blocks Everything External

Claude's sandbox CSP for MCP Apps iframes:
```
script-src 'self' 'unsafe-inline' 'unsafe-eval' blob: data: https://assets.claude.ai
style-src 'self' 'unsafe-inline' https://assets.claude.ai
```

The spec says `resourceDomains` should expand to `script-src` and `style-src` — **Claude doesn't do this**. Your CDN domains will be blocked regardless of what you declare in the CSP metadata.

**Workaround:** Inline everything. No CDN.

### The Iframe Starts Hidden

Claude creates the iframe with `visibility: hidden`. It only becomes visible after the `ui/initialize` handshake completes. If your handshake fails silently, you'll see a blank space where the widget should be.

### Double-Iframe Architecture

Claude uses a double-iframe proxy:
- Outer iframe: `{hash}.claudemcpcontent.com/mcp_apps?...` (Claude's sandbox)
- Inner iframe: Your HTML (loaded via `srcdoc` or fetch)

PostMessage goes through the outer iframe, which proxies to your inner iframe.

### UUID Serialization

If your tool returns dicts with UUID objects, `CallToolResult(structuredContent=result)` will fail with "Object of type UUID is not JSON serializable". Round-trip through `json.dumps(default=str)` first.

### OAuth Issuer URL

If your server is deployed to multiple environments (staging, production), the OAuth `issuer_url` must match the environment. Use `RAILWAY_PUBLIC_DOMAIN` env var:

```python
railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
if railway_domain:
    issuer_url = f"https://{railway_domain}"
```

### GitHub Issue #482

Open issue on `modelcontextprotocol/ext-apps` describing the exact same symptom — widget host runtime not starting after successful resource fetch. Our fix (correct handshake params) may resolve it.

## Testing

### Mock Mode (no MCP connection)

Add `?mock=true` to the HTML URL to render with fixture data:
```
http://localhost:9876/inbox_widget.html?mock=true
```

### AI UX UAT

Use Claude in Chrome to:
1. Navigate to claude.ai
2. Send "check inbox"
3. Verify widget renders with data
4. Check iframe visibility: `getComputedStyle(iframe).visibility`
5. Click interactions and verify debug bar updates

### Verification Script

```javascript
// Run in claude.ai console after tool call
var iframes = document.querySelectorAll('iframe');
var mcp = Array.from(iframes).find(f => f.src.includes('mcp_apps'));
console.log('MCP iframe:', mcp ? {w: mcp.offsetWidth, h: mcp.offsetHeight, vis: getComputedStyle(mcp).visibility} : 'NOT FOUND');
```
