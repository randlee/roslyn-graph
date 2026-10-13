// B0 experiments 4-6 on the openai-chatgpt provider (Codex OAuth): log token usage and tool calls per API call.
// The Codex backend URL is fixed in OpenWiki, so usage_proxy.py cannot sit in front of it; this wraps fetch instead
// and writes the same entries: {t, path, status, seconds, model, usage, tools}.
// Usage: OPENWIKI_USAGE_FILE=<log.jsonl> NODE_OPTIONS="--import file:///.../codex_usage.mjs" openwiki ...
import fs from "node:fs";

const out = process.env.OPENWIKI_USAGE_FILE;
const original = globalThis.fetch;

function record(entry) {
  if (out) fs.appendFileSync(out, JSON.stringify(entry) + "\n");
}

function summarize(text, entry) {
  for (const line of text.split("\n")) {
    if (!line.startsWith("data:")) continue;
    let e;
    try {
      e = JSON.parse(line.slice(5));
    } catch {
      continue;
    }
    if (e.type === "response.output_item.done" && e.item?.type === "function_call") {
      let input = e.item.arguments;
      try {
        input = JSON.parse(input || "{}");
      } catch {
        // keep the raw string
      }
      entry.tools.push({ name: e.item.name, input });
    }
    if (e.type === "response.completed" || e.type === "response.incomplete") {
      const u = e.response?.usage || {};
      entry.model = e.response?.model;
      entry.usage = {
        input_tokens: u.input_tokens || 0,
        output_tokens: u.output_tokens || 0,
        cache_read_input_tokens: u.input_tokens_details?.cached_tokens || 0,
        reasoning_tokens: u.output_tokens_details?.reasoning_tokens || 0,
      };
    }
  }
}

if (out && original) {
  globalThis.fetch = async function (input, init) {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input?.url;
    if (!url || !url.includes("/backend-api/codex/responses")) return original(input, init);
    const started = Date.now();
    const response = await original(input, init);
    const entry = { t: started / 1000, path: new URL(url).pathname, status: response.status, seconds: 0, model: null, usage: {}, tools: [] };
    if (!response.body) {
      record(entry);
      return response;
    }
    const [mine, theirs] = response.body.tee();
    (async () => {
      const decoder = new TextDecoder();
      let text = "";
      try {
        for await (const chunk of mine) text += decoder.decode(chunk, { stream: true });
      } catch {
        // the agent cancelled the stream; log what arrived
      }
      summarize(text, entry);
      entry.seconds = Math.round((Date.now() - started) / 10) / 100;
      record(entry);
    })();
    return new Response(theirs, { status: response.status, statusText: response.statusText, headers: response.headers });
  };
}
