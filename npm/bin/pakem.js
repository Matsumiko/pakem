#!/usr/bin/env node
"use strict";

/**
 * `npx pakem` installs the Pakem skill; every other argument is delegated to
 * the Python CLI that ships inside this package. Pakem stays Python; npm is
 * only the delivery mechanism.
 */
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const ROOT = path.resolve(__dirname, "..", "..");
const PKG = JSON.parse(fs.readFileSync(path.join(ROOT, "package.json"), "utf8"));
const PY = process.env.PAKEM_PYTHON || (process.platform === "win32" ? "python" : "python3");
const SKIP = new Set(["npm", "tests", "node_modules", ".git", ".github", "dist",
  "__pycache__", ".venv", "venv"]);
const SKIP_FILES = new Set([".gitignore", "requirements-dev.txt", "package.json", "package-lock.json"]);

function help() {
  console.log(`Pakem ${PKG.version}

Usage:
  npx pakem                         install the skill into ~/.claude/skills/pakem
  npx pakem install [options]       same, with options
  npx pakem <command> [args...]     run the Pakem CLI (init, check, finish, ...)

Install options:
  --dir <path>    install into a specific directory
  --project       install into ./.claude/skills/pakem
  --force         replace an existing installation
  --dry-run       show what would be copied

Examples:
  npx pakem
  npx pakem install --dir ~/.agents/skills/pakem
  npx pakem init --type app`);
}

function fail(message) {
  console.error(`pakem: ${message}`);
  process.exit(1);
}

function parseInstallArgs(args) {
  const out = { dir: null, project: false, force: false, dryRun: false };
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === "--dir") {
      if (!args[i + 1]) fail("--dir needs a path");
      out.dir = args[++i];
    } else if (arg === "--project") {
      out.project = true;
    } else if (arg === "--force") {
      out.force = true;
    } else if (arg === "--dry-run") {
      out.dryRun = true;
    } else if (arg === "--help" || arg === "-h") {
      help();
      process.exit(0);
    } else {
      fail(`unknown install option: ${arg}`);
    }
  }
  return out;
}

function targetDir(opts) {
  if (opts.dir) return path.resolve(opts.dir.replace(/^~(?=$|\/|\\)/, os.homedir()));
  if (opts.project) return path.resolve(process.cwd(), ".claude", "skills", "pakem");
  if (process.env.PAKEM_SKILL_DIR) return path.resolve(process.env.PAKEM_SKILL_DIR);
  return path.join(os.homedir(), ".claude", "skills", "pakem");
}

function pythonVersion() {
  const probe = spawnSync(PY, ["-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
    { encoding: "utf8" });
  if (probe.error || probe.status !== 0) return null;
  return probe.stdout.trim();
}

function install(opts) {
  const dest = targetDir(opts);
  if (opts.dryRun) {
    console.log(`Would install Pakem ${PKG.version} into ${dest}`);
    for (const name of fs.readdirSync(ROOT).sort()) {
      if (SKIP.has(name) || SKIP_FILES.has(name)) continue;
      console.log(`  ${name}`);
    }
    return;
  }

  if (fs.existsSync(dest)) {
    const entries = fs.readdirSync(dest);
    if (entries.length && !opts.force) {
      fail(`${dest} already exists. Re-run with --force to replace it.`);
    }
    if (entries.length) fs.rmSync(dest, { recursive: true, force: true });
  }
  fs.mkdirSync(dest, { recursive: true });

  let copied = 0;
  for (const name of fs.readdirSync(ROOT).sort()) {
    if (SKIP.has(name) || SKIP_FILES.has(name)) continue;
    const src = path.join(ROOT, name);
    const dst = path.join(dest, name);
    fs.cpSync(src, dst, {
      recursive: true,
      filter: (from) => !path.basename(from).startsWith(".") || path.basename(from) === ".gitignore",
    });
    copied++;
  }

  const py = pythonVersion();
  console.log(`Pakem ${PKG.version} installed in ${dest}`);
  console.log(`  ${copied} top-level entries copied`);
  if (!py) {
    console.log(`  [WARN] ${PY} not found. Pakem needs Python 3.10+.`);
  } else if (Number(py.split(".")[0]) < 3 || (Number(py.split(".")[0]) === 3 && Number(py.split(".")[1]) < 10)) {
    console.log(`  [WARN] Python ${py} found; Pakem needs 3.10+.`);
  } else {
    console.log(`  python: ${PY} ${py}`);
  }
  console.log("");
  console.log("Next:");
  console.log("  restart your agent so it loads SKILL.md");
  console.log(`  cd your-project && ${PY} ${path.join(dest, "scripts", "pakem.py")} init --type app`);
}

function runCli(args) {
  const cli = path.join(ROOT, "scripts", "pakem.py");
  if (!fs.existsSync(cli)) fail(`CLI not found in this package: ${cli}`);
  const result = spawnSync(PY, [cli, ...args], { stdio: "inherit", cwd: process.cwd() });
  if (result.error) fail(`cannot run ${PY}: ${result.error.message}`);
  process.exit(result.status === null ? 1 : result.status);
}

const args = process.argv.slice(2);
if (args.length === 0) {
  install(parseInstallArgs([]));
} else if (args[0] === "install") {
  install(parseInstallArgs(args.slice(1)));
} else if (["--dir", "--project", "--force", "--dry-run"].includes(args[0])) {
  install(parseInstallArgs(args));
} else if (args[0] === "--help" || args[0] === "-h" || args[0] === "help") {
  help();
} else {
  runCli(args);
}
