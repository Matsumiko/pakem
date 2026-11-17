#!/usr/bin/env node
"use strict";

/** Refuse to publish an npm package whose version drifted from the Python CLI. */
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const pkg = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
const cli = fs.readFileSync(path.join(root, "scripts", "pakem.py"), "utf8");
const match = cli.match(/^VERSION = "([^"]+)"$/m);

if (!match) {
  console.error("pakem: VERSION not found in scripts/pakem.py");
  process.exit(1);
}
if (match[1] !== pkg.version) {
  console.error(`pakem: package.json ${pkg.version} != scripts/pakem.py ${match[1]}`);
  console.error("Bump both before publishing.");
  process.exit(1);
}
if (!fs.existsSync(path.join(root, "SKILL.md"))) {
  console.error("pakem: SKILL.md missing from the package root");
  process.exit(1);
}
console.log(`pakem: version ${pkg.version} in sync`);
