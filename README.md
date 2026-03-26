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

## Sample output

```markdown
# java.lang.IllegalStateException
> Failed to process payment checkout

## Overview
- **Status:** open
- **Severity:** error
- **Occurrences:** 12,438
- **Affected users:** 9,204
- **First seen:** 2026-01-15T08:22:41.000Z
- **Last seen:** 2026-03-25T14:11:03.000Z
- **Release stages:** release

## Breakdowns
- **OS versions:** 15 40% | 14 22% | 13 15% | 12 10% | 16 8%
- **Manufacturers:** Samsung 35% | Xiaomi 20% | OPPO 15% | vivo 12% | Pixel 8%
- **Releases:** 3.12.0 (210) 30% | 3.11.2 (208) 25% | 3.13.0 (212) 20% | 3.10.1 (206) 15%
- **In Foreground:** True 100%
- **Network Access:** cellular 72% | wifi 26% | none 1%

## Stack Traces (2 distinct)
### Variant 1 (24x) CheckoutActivity
**Exception: java.lang.IllegalStateException**
> Failed to process payment checkout

  > CheckoutActivity:82 in `com.example.checkout.CheckoutActivity.processPayment`
  > CheckoutActivity:65 in `com.example.checkout.CheckoutActivity$onCreate$1$3.invokeSuspend`
    BaseContinuationImpl:? in `kotlin.coroutines.jvm.internal.BaseContinuationImpl.resumeWith`
    DispatchedTask:? in `kotlinx.coroutines.DispatchedTask.run`
  ... 6 more frames

**Breadcrumbs (variant 1, 2 distinct paths):**
**Path 1:**
  `14:10:41` [state] ProductActivity#onPause() (previous=onResume())
  `14:10:41` [state] CheckoutActivity#onCreate() (hasExtras=cart_id)
  `14:10:41` [state] CheckoutActivity#onResume() (previous=onCreate())
  `14:10:42` [request] OkHttp call succeeded (method=GET, url=https://api.example.com/v2/cart/details, duration=834)
  `14:10:48` [request] OkHttp call succeeded (method=POST, url=https://api.example.com/v2/payments/tokenize, duration=1205)
  `14:11:03` [request] OkHttp call failed (method=POST, url=https://api.example.com/v2/payments/charge, duration=15230)

**Path 2:**
  `14:08:12` [state] HomeActivity#onPause() (previous=onResume())
  `14:08:12` [state] CheckoutActivity#onCreate() (hasExtras=cart_id,promo_code)
  `14:08:12` [state] CheckoutActivity#onResume() (previous=onCreate())
  `14:08:13` [request] OkHttp call succeeded (method=GET, url=https://api.example.com/v2/cart/details, duration=412)
  `14:08:14` [request] OkHttp call succeeded (method=POST, url=https://api.example.com/v2/payments/tokenize, duration=980)
  `14:08:14` [request] OkHttp call succeeded (method=POST, url=https://api.example.com/v2/promo/validate, duration=340)
  `14:08:30` [request] OkHttp call failed (method=POST, url=https://api.example.com/v2/payments/charge, duration=16105)

### Variant 2 (6x) CheckoutActivity
**Exception: java.lang.IllegalStateException**
> Failed to process payment checkout

  > CheckoutActivity:94 in `com.example.checkout.CheckoutActivity.retryPayment`
  > CheckoutActivity:82 in `com.example.checkout.CheckoutActivity.processPayment`
  > CheckoutActivity:65 in `com.example.checkout.CheckoutActivity$onCreate$1$3.invokeSuspend`
    BaseContinuationImpl:? in `kotlin.coroutines.jvm.internal.BaseContinuationImpl.resumeWith`
  ... 8 more frames

## Metadata (latest event)
**app:**
  - activeScreen: CheckoutActivity
  - memoryUsage: 24117248
  - totalMemory: 31457280
  - processImportance: foreground
**device:**
  - networkAccess: cellular
  - screenResolution: 2400x1080
  - brand: Samsung
  - emulator: False
```

## CLI usage

The Python script also works standalone:

```bash
BUGSNAG_API_KEY=xxx python3 fetch_bugsnag_error.py https://app.bugsnag.com/org/project/errors/abc123
```
