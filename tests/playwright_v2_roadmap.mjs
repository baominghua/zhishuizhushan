import { chromium } from "../apps/web-operations/node_modules/playwright-core/index.mjs";
import { mkdir } from "node:fs/promises";

const baseURL = process.env.V2_VISUAL_BASE_URL || "http://127.0.0.1:8021";
const outputDir = process.env.V2_VISUAL_OUTPUT || ".codex-temp/visual-verification";
const executablePath = process.env.V2_BROWSER_PATH || "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const pages = [
  ["costs", "/v2/operations/costs", "经营成本核算"],
  ["resources", "/v2/resources/intelligence", "资源专题与长势监测"],
  ["integrations", "/v2/integrations", "集成与联调中心"],
  ["workforce", "/v2/workforce", "劳务培训与资质"],
  ["governance", "/v2/system/governance", "范围、权限与审计治理"],
  ["cockpit", "/v2/cockpit/leadership", "领导驾驶舱"],
];

await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ executablePath, headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  deviceScaleFactor: 1,
  extraHTTPHeaders: { "X-RS-User": "visual-reviewer", "X-RS-Roles": "admin", "X-RS-Areas": "*" },
});
const failures = [];
for (const [name, path, heading] of pages) {
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  const response = await page.goto(`${baseURL}${path}`, { waitUntil: "networkidle", timeout: 30_000 });
  if (!response?.ok()) failures.push(`${name}: HTTP ${response?.status()}`);
  const visibleHeading = await page.locator("h1").first().textContent();
  if (!visibleHeading?.includes(heading)) failures.push(`${name}: expected heading ${heading}, got ${visibleHeading}`);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  if (overflow > 2) failures.push(`${name}: horizontal overflow ${overflow}px`);
  if (consoleErrors.length) failures.push(`${name}: console errors: ${consoleErrors.join(" | ")}`);
  await page.screenshot({ path: `${outputDir}/${name}.png`, fullPage: true });
  await page.close();
}
await browser.close();
if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log(`verified ${pages.length} pages; screenshots: ${outputDir}`);
