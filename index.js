#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { execFile } from "child_process";
import { promisify } from "util";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const execFileAsync = promisify(execFile);

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const FETCH_BUGSNAG_SCRIPT = join(__dirname, "fetch_bugsnag_error.py");
const BUGSNAG_API_KEY = process.env.BUGSNAG_API_KEY;

const server = new Server(
  { name: "bugsnag-tldr", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "fetch_bugsnag_error",
      description:
        "Fetch Bugsnag error details given an error URL. Returns a concise markdown summary with stack trace, breadcrumbs, breakdowns, and metadata. Requires BUGSNAG_API_KEY environment variable.",
      inputSchema: {
        type: "object",
        properties: {
          error_url: {
            type: "string",
            description:
              "Bugsnag error URL (e.g., https://app.bugsnag.com/org/project/errors/abc123)",
          },
          breadcrumb_paths: {
            type: "string",
            description:
              "Max distinct breadcrumb paths per trace variant (default: '5', or 'all')",
          },
          samples: {
            type: "number",
            description:
              "Number of events to sample for trace variant analysis (default: 100). Higher values give more accurate variant percentages but take longer.",
          },
        },
        required: ["error_url"],
      },
    },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  if (name !== "fetch_bugsnag_error") {
    throw new Error(`Unknown tool: ${name}`);
  }

  if (!BUGSNAG_API_KEY) {
    throw new Error("BUGSNAG_API_KEY environment variable is not set");
  }

  if (!args.error_url) {
    throw new Error("error_url parameter is required");
  }

  const scriptArgs = [FETCH_BUGSNAG_SCRIPT, args.error_url];
  if (args.breadcrumb_paths) {
    scriptArgs.push("-b", String(args.breadcrumb_paths));
  }
  if (args.samples) {
    scriptArgs.push("-s", String(args.samples));
  }

  try {
    const { stdout } = await execFileAsync("python3", scriptArgs, {
      env: { ...process.env, BUGSNAG_API_KEY },
      maxBuffer: 5 * 1024 * 1024,
    });

    return {
      content: [{ type: "text", text: stdout || "No error details returned" }],
    };
  } catch (error) {
    return {
      content: [
        {
          type: "text",
          text: `Error: ${error.message}\n${error.stderr || ""}`,
        },
      ],
      isError: true,
    };
  }
});

server.onerror = (error) => console.error("[MCP Error]", error);
process.on("SIGINT", async () => {
  await server.close();
  process.exit(0);
});

const transport = new StdioServerTransport();
await server.connect(transport);
console.error("bugsnag-tldr server running on stdio");
