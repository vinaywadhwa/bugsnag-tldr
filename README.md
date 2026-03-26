# bugsnag-tldr

MCP server that turns a Bugsnag error URL into a condensed, actionable summary. Unlike the official Bugsnag API (or MCP servers that mirror it verbatim), this strips away the noise and surfaces what actually matters when debugging: grouped stack trace variants, distinct breadcrumb paths, breakdown percentages, and key metadata. One tool call, one readable markdown doc.

## Setup

### Option 1: npx (no install)

Add to your MCP config (`~/.mcp.json` for Claude Code, or your client's MCP settings):

```json
{
  "mcpServers": {
    "bugsnag": {
      "command": "npx",
      "args": ["-y", "bugsnag-tldr"],
      "env": {
        "BUGSNAG_API_KEY": "<your-bugsnag-personal-auth-token>"
      }
    }
  }
}
```

### Option 2: Clone and run locally

```bash
git clone https://github.com/vinaywadhwa/bugsnag-tldr.git
cd bugsnag-tldr
npm install
```

Then add to your MCP config:

```json
{
  "mcpServers": {
    "bugsnag": {
      "command": "node",
      "args": ["/path/to/bugsnag-tldr/index.js"],
      "env": {
        "BUGSNAG_API_KEY": "<your-bugsnag-personal-auth-token>"
      }
    }
  }
}
```

## Requirements

- Node.js 18+
- Python 3.6+ (uses only standard library, no pip install needed)

## Getting your Bugsnag API key

1. Go to [Bugsnag](https://app.bugsnag.com) > Settings > My account > Personal auth tokens
2. Create a new token
3. Use it as `BUGSNAG_API_KEY`

## Tool: `fetch_bugsnag_error`

**Input:**
- `error_url` (required): A Bugsnag error URL (eg: `https://app.bugsnag.com/org/project/errors/abc123`)
- `breadcrumb_paths` (optional): Max distinct breadcrumb paths per trace variant. Default `5`, or `all`

**Output:** Markdown summary including:
- Error class and message
- Status, severity, occurrence count, affected users
- Release stages and linked issues
- Breakdowns by OS version, device, country, etc.
- Stack traces grouped by distinct variants
- Breadcrumb trails (multiple distinct paths per variant)
- Event metadata

## CLI usage

The Python script also works standalone:

```bash
BUGSNAG_API_KEY=xxx python3 fetch_bugsnag_error.py https://app.bugsnag.com/org/project/errors/abc123
```
