#!/usr/bin/env node

const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");

const rootDir = path.resolve(__dirname, "..");
const requireFromRoot = createRequire(path.join(rootDir, "package.json"));

function usage() {
  console.error(
    "Usage: node scripts/save_midscene_computer_screenshot.cjs --output <png-path> [--display <display-id>]",
  );
}

function parseArgs(argv) {
  const args = {
    output: "",
    displayId: process.env.MIDSCENE_COMPUTER_DISPLAY_ID || "",
  };
  for (let i = 0; i < argv.length; i += 1) {
    const item = argv[i];
    if ((item === "--output" || item === "-o") && argv[i + 1]) {
      args.output = argv[++i];
    } else if ((item === "--display" || item === "--display-id") && argv[i + 1]) {
      args.displayId = argv[++i];
    } else if (item === "--help" || item === "-h") {
      usage();
      process.exit(0);
    }
  }
  return args;
}

function decodePngDataUrl(dataUrl) {
  const prefix = "data:image/png;base64,";
  if (!dataUrl.startsWith(prefix)) {
    throw new Error("Midscene screenshot did not return a PNG data URL");
  }
  return Buffer.from(dataUrl.slice(prefix.length), "base64");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.output) {
    usage();
    process.exit(2);
  }

  const { ComputerDevice } = requireFromRoot("@midscene/computer");
  const device = new ComputerDevice(
    args.displayId ? { displayId: args.displayId } : undefined,
  );
  const dataUrl = await device.screenshotBase64();
  const buffer = decodePngDataUrl(dataUrl);
  const outputPath = path.resolve(args.output);
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, buffer);

  console.log(
    JSON.stringify(
      {
        ok: true,
        output: outputPath,
        bytes: buffer.length,
        displayId: args.displayId || null,
      },
      null,
      2,
    ),
  );
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exit(1);
});
