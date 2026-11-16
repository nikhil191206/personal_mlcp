// `npm run dev`: starts the local Python API (127.0.0.1:8765) and the Vite site together; Ctrl+C stops both.
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
// The repo is the folder above web/ when web/ lives inside it; otherwise a sibling called personal_mlcp.
const repo = process.env.ATLAS_REPO
  ? resolve(process.env.ATLAS_REPO)
  : existsSync(join(web, "..", "atlas")) ? resolve(web, "..") : resolve(web, "..", "personal_mlcp");
const python = [join(repo, ".venv", "Scripts", "python.exe"), join(repo, ".venv", "bin", "python")].find(existsSync);

if (!python) {
  console.error(`No Python virtual environment found in ${repo}\\.venv. Set ATLAS_REPO to the personal_mlcp folder.`);
  process.exit(1);
}

const children = [];
const start = (name, cmd, args) => {
  const child = spawn(cmd, args, { cwd: web, stdio: "inherit", env: { ...process.env, ATLAS_REPO: repo } });
  child.on("exit", (code) => {
    if (code && code !== 0) console.error(`${name} stopped with exit code ${code}`);
    stopAll();
  });
  children.push(child);
};
const stopAll = () => { for (const c of children) if (!c.killed) c.kill(); process.exit(0); };
process.on("SIGINT", stopAll);
process.on("SIGTERM", stopAll);

start("API", python, ["-u", join(web, "api", "server.py")]);
if (!process.argv.includes("--api-only")) {
  start("Website", process.execPath, [join(web, "node_modules", "vite", "bin", "vite.js")]);
}
