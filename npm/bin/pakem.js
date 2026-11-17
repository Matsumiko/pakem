#!/usr/bin/env node
"use strict";

/**
 * `npx pakem-cli` installs the Pakem skill; every other argument is delegated
 * to the Python CLI that ships inside this package. Pakem stays Python; npm is
 * only the delivery mechanism.
 *
 * With a terminal it shows an interactive picker (like other skill installers).
 * Without a TTY, or with explicit flags, it installs non-interactively so agents
 * and CI can call it safely.
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
const HOME = os.homedir();
const INTERACTIVE = Boolean(process.stdin.isTTY && process.stdout.isTTY);

function help() {
  console.log(`Pakem ${PKG.version}

Usage:
  npx pakem-cli                     install the skill (interactive in a terminal)
  npx pakem-cli install [options]   same, with options
  npx pakem-cli <command> [args...] run the Pakem CLI (init, check, finish, ...)

Install options:
  --dir <path>    install into a specific directory
  --project       install into ./.claude/skills/pakem
  --force         replace an existing installation
  --dry-run       show what would be copied
  -y, --yes       never prompt (defaults to ~/.claude/skills/pakem)

Examples:
  npx pakem-cli
  npx pakem-cli install --dir ~/.agents/skills/pakem
  npx pakem-cli init --type app`);
}

function fail(message) {
  console.error(`pakem: ${message}`);
  process.exit(1);
}

function parseInstallArgs(args) {
  const out = {
    dir: null,
    project: false,
    force: false,
    dryRun: false,
    yes: false,
    interactive: false,
  };
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
    } else if (arg === "-y" || arg === "--yes") {
      out.yes = true;
    } else if (arg === "--interactive") {
      out.interactive = true;
    } else if (arg === "--help" || arg === "-h") {
      help();
      process.exit(0);
    } else {
      fail(`unknown install option: ${arg}`);
    }
  }
  return out;
}

function expand(target) {
  return path.resolve(String(target).replace(/^~(?=$|\/|\\)/, HOME));
}

function targetDir(opts) {
  if (opts.dir) return expand(opts.dir);
  if (opts.project) return path.resolve(process.cwd(), ".claude", "skills", "pakem");
  if (process.env.PAKEM_SKILL_DIR) return expand(process.env.PAKEM_SKILL_DIR);
  return path.join(HOME, ".claude", "skills", "pakem");
}

function pythonVersion() {
  const probe = spawnSync(PY, ["-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
    { encoding: "utf8" });
  if (probe.error || probe.status !== 0) return null;
  return probe.stdout.trim();
}

function pythonWarning(py) {
  if (!py) return `${PY} not found; Pakem needs Python 3.10+.`;
  const [major, minor] = py.split(".").map(Number);
  if (major < 3 || (major === 3 && minor < 10)) {
    return `Python ${py} found; Pakem needs 3.10+.`;
  }
  return null;
}

function copySkill(dest, opts) {
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
    fs.cpSync(path.join(ROOT, name), path.join(dest, name), {
      recursive: true,
      filter: (from) => !path.basename(from).startsWith("."),
    });
    copied++;
  }
  return copied;
}

function nextSteps(dest) {
  return [
    `restart your agent so it loads SKILL.md`,
    `cd your-project && ${PY} ${path.join(dest, "scripts", "pakem.py")} init --type app`,
  ];
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

  const copied = copySkill(dest, opts);
  const py = pythonVersion();
  console.log(`Pakem ${PKG.version} installed in ${dest}`);
  console.log(`  ${copied} top-level entries copied`);
  const warning = pythonWarning(py);
  console.log(warning ? `  [WARN] ${warning}` : `  python: ${PY} ${py}`);
  console.log("");
  console.log("Next:");
  for (const line of nextSteps(dest)) console.log(`  ${line}`);
}

async function interactiveInstall(seed) {
  const clack = await import("@clack/prompts");
  const { intro, outro, select, text, confirm, spinner, cancel, isCancel } = clack;

  intro(`Pakem ${PKG.version} · agent work discipline`);

  const choices = [
    { value: "claude-global", label: "Claude Code (global)", hint: "~/.claude/skills/pakem" },
    { value: "agents-global", label: "Agents / skills.sh (global)", hint: "~/.agents/skills/pakem" },
    { value: "claude-project", label: "This project", hint: "./.claude/skills/pakem" },
    { value: "custom", label: "Custom path", hint: "any skills folder" },
  ];

  const choice = await select({
    message: "Where should the skill live?",
    options: choices,
    initialValue: seed.dir ? "custom" : seed.project ? "claude-project" : "claude-global",
  });
  if (isCancel(choice)) {
    cancel("Installation cancelled.");
    return;
  }

  let dest;
  if (choice === "claude-global") dest = path.join(HOME, ".claude", "skills", "pakem");
  else if (choice === "agents-global") dest = path.join(HOME, ".agents", "skills", "pakem");
  else if (choice === "claude-project") dest = path.resolve(process.cwd(), ".claude", "skills", "pakem");
  else {
    const typed = await text({
      message: "Install path",
      placeholder: "~/.agents/skills/pakem",
      initialValue: seed.dir || "",
      validate: (value) => (!value ? "A path is required" : undefined),
    });
    if (isCancel(typed)) {
      cancel("Installation cancelled.");
      return;
    }
    dest = expand(typed);
  }

  if (fs.existsSync(dest) && fs.readdirSync(dest).length) {
    if (!seed.force) {
      const replace = await confirm({
        message: `${dest} already exists. Replace it?`,
        initialValue: false,
      });
      if (isCancel(replace) || !replace) {
        cancel("Installation cancelled.");
        return;
      }
      seed.force = true;
    }
  }

  const spin = spinner();
  spin.start(`Installing into ${dest}`);
  try {
    const copied = copySkill(dest, seed);
    spin.stop(`Installed ${copied} top-level entries`);
  } catch (error) {
    spin.stop("Installation failed");
    throw error;
  }

  const py = pythonVersion();
  const warning = pythonWarning(py);
  if (warning) outro(`Installed, but ${warning}`);
  else outro(`Installed · python ${py}`);
  console.log("");
  console.log("Next:");
  for (const line of nextSteps(dest)) console.log(`  ${line}`);
}

function runCli(args) {
  const cli = path.join(ROOT, "scripts", "pakem.py");
  if (!fs.existsSync(cli)) fail(`CLI not found in this package: ${cli}`);
  const result = spawnSync(PY, [cli, ...args], { stdio: "inherit", cwd: process.cwd() });
  if (result.error) fail(`cannot run ${PY}: ${result.error.message}`);
  process.exit(result.status === null ? 1 : result.status);
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length === 0) {
    const opts = parseInstallArgs([]);
    if (INTERACTIVE) return interactiveInstall(opts);
    return install(opts);
  }
  if (args[0] === "install") {
    const opts = parseInstallArgs(args.slice(1));
    const explicit = Boolean(opts.dir || opts.project || opts.yes || opts.dryRun);
    if (opts.interactive || (INTERACTIVE && !explicit)) return interactiveInstall(opts);
    return install(opts);
  }
  if (["--dir", "--project", "--force", "--dry-run", "-y", "--yes"].includes(args[0])) {
    return install(parseInstallArgs(args));
  }
  if (args[0] === "--help" || args[0] === "-h" || args[0] === "help") {
    help();
    return;
  }
  return runCli(args);
}

main().catch((error) => {
  fail(error && error.message ? error.message : String(error));
});
