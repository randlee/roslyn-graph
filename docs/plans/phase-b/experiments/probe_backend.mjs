// B0 experiment 4 (tool level, no model): drive OpenWiki's own agent backend on a scoped clone, constructed exactly
// as the planner and page workers construct it, and check what each file tool exposes.
// Usage: node probe_backend.mjs <openwiki dist dir> <repo> <scope.json>
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import path from "node:path";

const [dist, repo, scopePath] = process.argv.slice(2);
const load = (rel) => import(pathToFileURL(path.join(dist, rel)).href);
const { OpenWikiLocalShellBackend } = await load("agent/docs-only-backend.js");
const { OpenWikiIgnore } = await load("agent/openwiki-ignore.js");

const scope = JSON.parse(readFileSync(scopePath, "utf8"));
const inScope = new Set(scope.files);
const ancestors = new Set(scope.files.flatMap((f) => f.split("/").slice(0, -1).map((_, i, a) => a.slice(0, i + 1).join("/"))));
const ignore = await OpenWikiIgnore.load(repo);
const backend = new OpenWikiLocalShellBackend({ docsOnly: true, writableWikiPages: ["openwiki/index.md"], openWikiIgnore: ignore,
  maxOutputBytes: 100_000, outputMode: "repository", rootDir: repo, timeout: 120, virtualMode: true });

const tracked = execFileSync("git", ["-C", repo, "ls-files"], { encoding: "utf8", maxBuffer: 1 << 28 }).split("\n").filter(Boolean);
const outside = tracked.filter((f) => !inScope.has(f) && !f.startsWith("openwiki/"));
const sample = outside.filter((_, i) => i % Math.max(1, Math.floor(outside.length / 200)) === 0);
const report = { type: "backend-probe", tracked: tracked.length, scopeFiles: inScope.size, problems: [] };
const strip = (p) => p.replace(/^\/+/, "");

// read: every scope file readable; a sample of outside files denied.
for (const f of inScope) {
  const r = await backend.read(`/${f}`);
  if (r.error) report.problems.push(`read denied in scope: ${f}: ${r.error}`);
}
let deniedReads = 0;
for (const f of sample) {
  const r = await backend.read(`/${f}`);
  if (r.error) deniedReads++; else report.problems.push(`read allowed outside: ${f}`);
}
report.outsideReadsDenied = `${deniedReads}/${sample.length}`;

// ls: walk every listable directory from the root; every surfaced file must be in scope.
const seen = new Set();
const queue = ["/"];
while (queue.length) {
  const dir = queue.shift();
  const r = await backend.ls(dir);
  if (r.error) { if (dir === "/" || ancestors.has(strip(dir).replace(/\/$/, ""))) report.problems.push(`ls denied: ${dir}: ${r.error}`); continue; }
  for (const e of r.files ?? []) {
    const p = strip(e.path).replace(/\/$/, "");
    if (seen.has(p)) continue;
    seen.add(p);
    if (e.is_dir) queue.push(`/${p}/`);
    else if (!inScope.has(p) && !p.startsWith("openwiki/") && p !== ".openwikiignore") report.problems.push(`ls surfaced outside file: ${p}`);
  }
}
report.lsFilesSurfaced = [...seen].filter((p) => inScope.has(p)).length;

// grep and glob from the root and from an opened ancestor.
const g = await backend.grep("class", "/", "*.cs");
const grepPaths = new Set((g.matches ?? []).map((m) => strip(m.path)));
report.grepFiles = grepPaths.size;
for (const p of grepPaths) if (!inScope.has(p)) report.problems.push(`grep matched outside: ${p}`);
const top = [...ancestors].sort((a, b) => a.length - b.length)[0];
const gl = await backend.glob("**/*.cs", `/${top}/`);
const globPaths = (gl.files ?? []).map((f) => strip(f.path));
report.globFiles = globPaths.length;
for (const p of globPaths) if (!inScope.has(p)) report.problems.push(`glob matched outside: ${p}`);
report.rootGlob = (await backend.glob("**/*", "/")).error ? "refused" : "allowed";

// shell and writes.
report.shellCat = (await backend.execute(`cat ${outside[0]}`)).exitCode === 0 ? "ran" : "refused";
report.writeOutsideDocs = (await backend.write("/src-note.md", "x")).error ? "denied" : "allowed";
report.writeDocs = (await backend.write("/openwiki/index.md", "# probe\n")).error ? "denied" : "allowed";

console.log(JSON.stringify(report, null, 1));
process.exit(report.problems.length ? 1 : 0);
