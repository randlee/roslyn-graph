// B0 experiments 4-6: log every file-system path OpenWiki touches under a repository.
// Usage: OPENWIKI_TRACE_ROOT=<repo> OPENWIKI_TRACE_FILE=<log.jsonl> NODE_OPTIONS="--import file:///.../fs_trace.mjs" openwiki ...
import fs from "node:fs";
import fsp from "node:fs/promises";
import childProcess from "node:child_process";
import { syncBuiltinESMExports } from "node:module";
import path from "node:path";
import { promisify } from "node:util";

const root = process.env.OPENWIKI_TRACE_ROOT && path.resolve(process.env.OPENWIKI_TRACE_ROOT).toLowerCase();
const out = process.env.OPENWIKI_TRACE_FILE;
const append = fs.appendFileSync;

let busy = false;
function log(op, target) {
  if (!root || !out || busy) return;
  busy = true;
  try {
    write(op, target);
  } finally {
    busy = false;
  }
}

function write(op, target) {
  let p;
  try {
    p = path.resolve(typeof target === "string" ? target : target instanceof URL ? target.pathname.replace(/^\/([A-Za-z]:)/, "$1") : String(target));
  } catch {
    return;
  }
  if (!p.toLowerCase().startsWith(root)) return;
  append(out, JSON.stringify({ t: Date.now(), op, path: path.relative(root, p).split(path.sep).join("/") }) + "\n");
}

const READS = ["readFile", "readdir", "open", "stat", "lstat", "access", "opendir", "realpath"];
const WRITES = ["writeFile", "appendFile", "mkdir", "rm", "unlink", "rename", "cp"];
for (const name of [...READS, ...WRITES]) {
  const op = READS.includes(name) ? name : `write:${name}`;
  if (typeof fsp[name] === "function") {
    const orig = fsp[name];
    fsp[name] = function (target, ...rest) { log(op, target); return orig.call(this, target, ...rest); };
  }
  if (typeof fs[name] === "function") {
    const orig = fs[name];
    fs[name] = function (target, ...rest) { log(op, target); return orig.call(this, target, ...rest); };
  }
  const sync = `${name}Sync`;
  if (typeof fs[sync] === "function" && name !== "appendFile") {
    const orig = fs[sync];
    fs[sync] = function (target, ...rest) { log(`${op}Sync`, target); return orig.call(this, target, ...rest); };
  }
}
fs.createReadStream = ((orig) => function (target, ...rest) { log("createReadStream", target); return orig.call(this, target, ...rest); })(fs.createReadStream);
function logSpawn(name, cmd, args) {
  if (!root || !out || busy) return;
  busy = true;
  try {
    append(out, JSON.stringify({ t: Date.now(), op: `spawn:${name}`, cmd: String(cmd), args: Array.isArray(args) ? args.map(String) : [] }) + "\n");
  } finally {
    busy = false;
  }
}
for (const name of ["spawn", "execFile", "exec"]) {
  const orig = childProcess[name];
  const wrapped = function (cmd, ...rest) { logSpawn(name, cmd, rest[0]); return orig.call(this, cmd, ...rest); };
  // util.promisify(execFile) resolves {stdout, stderr} only through the custom hook; keep it.
  const custom = orig[promisify.custom];
  if (custom) wrapped[promisify.custom] = function (cmd, ...rest) { logSpawn(name, cmd, rest[0]); return custom.call(this, cmd, ...rest); };
  childProcess[name] = wrapped;
}
syncBuiltinESMExports();
