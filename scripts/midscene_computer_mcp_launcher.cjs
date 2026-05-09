#!/usr/bin/env node

const path = require("node:path");
const { createRequire } = require("node:module");

const rootDir = path.resolve(__dirname, "..");
const requireFromRoot = createRequire(path.join(rootDir, "package.json"));

const { ComputerMCPServer } = requireFromRoot("@midscene/computer/mcp-server");
const { launchMCPServer } = requireFromRoot("@midscene/shared/mcp");

function parseArgs(argv) {
  const args = {
    mode: process.env.MIDSCENE_MCP_MODE || "stdio",
    port: process.env.MIDSCENE_MCP_PORT || "3000",
    host: process.env.MIDSCENE_MCP_HOST || "localhost",
  };

  for (let i = 0; i < argv.length; i += 1) {
    const item = argv[i];
    if (item === "--mode" && argv[i + 1]) {
      args.mode = argv[++i];
    } else if (item === "--port" && argv[i + 1]) {
      args.port = argv[++i];
    } else if (item === "--host" && argv[i + 1]) {
      args.host = argv[++i];
    }
  }

  return args;
}

launchMCPServer(new ComputerMCPServer(), parseArgs(process.argv.slice(2))).catch(
  (error) => {
    const message = error instanceof Error ? error.stack || error.message : String(error);
    console.error(message);
    process.exit(1);
  },
);
