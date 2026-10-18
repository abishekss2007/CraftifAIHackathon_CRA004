// End-to-end check of the dashboard in a real headless Chromium.
//   node tools/e2e.mjs demo   http://127.0.0.1:8000/   (static demo site)
//   node tools/e2e.mjs live   http://127.0.0.1:8080/   (python -m safesight --source sim)
// Passes when the page loads with no script errors, reaches the expected state,
// and the scripted fall shows up in the incident list.
import { chromium } from 'playwright';

const [mode, url] = process.argv.slice(2);
if (!['demo', 'live'].includes(mode) || !url) {
  console.error('usage: node tools/e2e.mjs demo|live URL');
  process.exit(2);
}

const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const errors = [];
page.on('pageerror', e => errors.push(String(e)));
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

try {
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForFunction(m => document.getElementById('state').dataset.s === m, mode, { timeout: 15000 });
  await page.waitForFunction(
    () => [...document.getElementById('log').children].some(li => /FALL|MAN.DOWN|fell/i.test(li.textContent)),
    null, { timeout: 30000 });
  await page.waitForFunction(() => document.getElementById('status').dataset.level !== 'idle', null, { timeout: 10000 });
  const head = await page.textContent('#statusHead');
  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  await page.setViewportSize({ width: 390, height: 844 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  if (overflow) throw new Error('horizontal scroll at phone width');
  if (errors.length) throw new Error('page errors: ' + errors.join(' | '));
  console.log(`e2e ${mode} OK: status="${head}", desktop width ${width}px, no page errors`);
} catch (e) {
  console.error(`e2e ${mode} FAILED: ${e.message}`);
  await page.screenshot({ path: `e2e-${mode}-failure.png`, fullPage: true }).catch(() => {});
  process.exitCode = 1;
} finally {
  await browser.close();
}
