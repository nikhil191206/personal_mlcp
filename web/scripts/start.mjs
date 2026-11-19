// `npm start`: builds the website if needed, then runs ONE process: the Python backend serving the built site and the
// API together on http://127.0.0.1:8765, behind a password. Local only. Use `npm run dev` while developing.
import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repo = process.env.ATLAS_REPO
  ? resolve(process.env.ATLAS_REPO)
  : existsSync(join(web, "..", "atlas")) ? resolve(web, "..") : resolve(web, "..", "personal_mlcp");
const python = [join(repo, ".venv", "Scripts", "python.exe"), join(repo, ".venv", "bin", "python")].find(existsSync);

if (!python) {
  console.error(`No Python virtual environment found in ${repo}\\.venv. Set ATLAS_REPO to the personal_mlcp folder.`);
  process.exit(1);
}

if (!existsSync(join(web, "dist", "index.html")) || process.argv.includes("--rebuild")) {
  console.log("Building the website...");
  const vite = spawnSync(process.execPath, [join(web, "node_modules", "vite", "bin", "vite.js"), "build"], { cwd: web, stdio: "inherit" });
  if (vite.status !== 0) process.exit(vite.status ?? 1);
}

const api = spawn(python, ["-u", join(web, "api", "server.py")], {
  cwd: web, stdio: "inherit", env: { ...process.env, ATLAS_REPO: repo, SCOUT_SERVE: "1" },
});
api.on("exit", (code) => process.exit(code ?? 0));
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => api.kill());
