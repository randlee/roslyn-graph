// The README ignore-chain example, checked with OpenWiki's matcher. Usage: node readme_chain_example.mjs <openwiki dist/agent/openwiki-ignore.js>
import { pathToFileURL } from "node:url";
const { OpenWikiIgnore } = await import(pathToFileURL(process.argv[2]).href);
const ig = OpenWikiIgnore.parse(`*
!/openwiki/
!/src/
/src/*
!/src/Billing/
/src/Billing/*
!/src/Billing/Orders/
/src/Billing/Orders/*
!/src/Billing/Orders/Order.cs
!/src/Billing/Orders/OrderLine.cs
!/src/Billing/Payments/
secrets/`);
const want = {"src":"a","src/Billing":"a","src/Billing/Orders":"a","src/Billing/Orders/Order.cs":"a","src/Billing/Orders/OrderLine.cs":"a",
 "src/Billing/Orders/OrderMapper.cs":"i","src/Billing/Orders/Sub":"i","src/Billing/Orders/Sub/X.cs":"i","src/Billing/Payments/Pay.cs":"a",
 "src/Billing/Payments/Deep/P.cs":"a","src/Billing/Refunds/R.cs":"i","src/Other.cs":"i","openwiki/index.md":"a","src/Billing/Payments/secrets/k.txt":"i"};
const dirs = new Set(["src","src/Billing","src/Billing/Orders","src/Billing/Orders/Sub"]);
let bad = 0;
for (const [p,w] of Object.entries(want)) { const got = ig.ignores(p, dirs.has(p)) ? "i" : "a"; if (got!==w) bad++; console.log((got===w?"ok   ":"FAIL ")+got+" "+p); }
console.log(bad ? `${bad} mismatches` : "all as designed");
