// Parse and render every ```mermaid block in the given Markdown files with the
// real Mermaid library inside headless Chromium, the same renderer GitHub uses.
//   node tools/check_mermaid.mjs README.md docs/*.md
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { chromium } from 'playwright';

const files = process.argv.slice(2);
if (!files.length) { console.error('usage: node tools/check_mermaid.mjs FILE.md...'); process.exit(2); }
const blocks = files.flatMap(f => [...readFileSync(f, 'utf8').matchAll(/```mermaid\r?\n([\s\S]*?)```/g)]
  .map((m, i) => ({ where: `${f} diagram ${i + 1}`, code: m[1] })));
if (!blocks.length) { console.error('no mermaid diagrams found'); process.exit(1); }

const mermaidJs = createRequire(import.meta.url).resolve('mermaid/dist/mermaid.min.js');
const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
const page = await browser.newPage();
await page.setContent('<!doctype html><body></body>');
await page.addScriptTag({ path: mermaidJs });
let failed = 0;
for (const [i, b] of blocks.entries()) {
  const err = await page.evaluate(async ({ code, id }) => {
    try {
      mermaid.initialize({ startOnLoad: false });
      await mermaid.parse(code);
      await mermaid.render(id, code);
      return null;
    } catch (e) { return String(e && e.message || e); }
  }, { code: b.code, id: `m${i}` });
  if (err) { failed++; console.error(`FAIL ${b.where}: ${err.split('\n').slice(0, 4).join(' ')}`); }
  else console.log(`ok   ${b.where}`);
}
await browser.close();
console.log(`${blocks.length - failed}/${blocks.length} diagrams render`);
process.exitCode = failed ? 1 : 0;
