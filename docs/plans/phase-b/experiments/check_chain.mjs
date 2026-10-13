// B0 experiment 3: check a generated .openwikiignore with OpenWiki's own matcher.
// Usage: node check_chain.mjs <openwiki-ignore.js> <repo> <scope.json>
// Every scope file and its ancestors must be allowed, openwiki/ writable, and every other tracked file ignored.
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";

const [matcherPath, repo, scopePath] = process.argv.slice(2);
const { OpenWikiIgnore } = await import(pathToFileURL(matcherPath).href);
const ig = OpenWikiIgnore.parse(readFileSync(`${repo}/.openwikiignore`, "utf8"));
const scope = JSON.parse(readFileSync(scopePath, "utf8"));
const mode = process.argv[5] || "files";
const files = new Set(scope.files);
const dirsOpen = new Set(scope.files.map((f) => f.split("/").slice(0, -1).join("/")));
const tracked = execFileSync("git", ["-C", repo, "ls-files"], { encoding: "utf8", maxBuffer: 1 << 28 }).split("\n").filter(Boolean);

const problems = [];
for (const f of files) {
  const parts = f.split("/");
  for (let i = 1; i < parts.length; i++) {
    const d = parts.slice(0, i).join("/");
    if (ig.ignores(d, true)) problems.push(`ancestor ignored: ${d}`);
  }
  if (ig.ignores(f, false)) problems.push(`scope file ignored: ${f}`);
}
if (ig.ignores("openwiki", true) || ig.ignores("openwiki/index.md", false)) problems.push("openwiki/ not writable");
let allowedOutside = 0;
const examples = [];
for (const f of tracked) {
  if (files.has(f) || f.startsWith("openwiki/") || f === ".openwikiignore") continue;
  const inOpenDir = [...dirsOpen].some((d) => f.startsWith(`${d}/`));
  if (!ig.ignores(f, false)) {
    if (mode === "dirs" && inOpenDir) continue;
    allowedOutside++;
    if (examples.length < 10) examples.push(f);
  }
}
console.log(JSON.stringify({ type: "chain-check", mode, scopeFiles: files.size, tracked: tracked.length, problems, allowedOutside, examples }));
process.exit(problems.length || allowedOutside ? 1 : 0);
