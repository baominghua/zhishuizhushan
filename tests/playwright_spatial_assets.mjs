import { chromium } from "../apps/web-operations/node_modules/playwright-core/index.mjs";
import { mkdir } from "node:fs/promises";

const baseURL = process.env.V2_VISUAL_BASE_URL || "http://127.0.0.1:8022";
const outputDir = process.env.V2_VISUAL_OUTPUT || "C:/Users/MECHREUO/.codex/visualizations/2026/08/19/smart-bamboo-3d-tiles";
const executablePath = process.env.V2_BROWSER_PATH || "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const testGeoTiff = process.env.V2_TEST_GEOTIFF || "";
const viewports = [
  { name: "desktop", width: 1440, height: 1000 },
  { name: "mobile", width: 390, height: 844 },
];

await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ executablePath, headless: true });
const failures = [];

for (const viewport of viewports) {
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    deviceScaleFactor: 1,
    extraHTTPHeaders: {
      "X-RS-User": "visual-reviewer",
      "X-RS-Roles": "admin",
      "X-RS-Areas": "*",
    },
  });
  const page = await context.newPage();
  const consoleErrors = [];
  let registeredTilesetPayload = null;
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  await page.route("**/api/3d-tiles/register", async (route) => {
    registeredTilesetPayload = route.request().postDataJSON();
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        accepted: true,
        task: { id: "task-visual-tileset", type: "3dtiles-register", status: "queued", progress: 0, message: "Queued", sceneId: "tiles-visual" },
      }),
    });
  });
  await page.route("**/api/tasks/task-visual-tileset", async (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ id: "task-visual-tileset", type: "3dtiles-register", status: "running", progress: 45, message: "正在校验 DJI 3D Tiles 目录", sceneId: "tiles-visual" }),
  }));

  const response = await page.goto(`${baseURL}/v2/drone/imagery-assets`, { waitUntil: "networkidle", timeout: 30_000 });
  if (!response?.ok()) failures.push(`${viewport.name}: HTTP ${response?.status()}`);
  await page.getByRole("heading", { name: "影像与点云成果" }).waitFor();
  await page.getByRole("button", { name: "上传成果" }).click();
  const panel = page.getByRole("dialog", { name: "上传并自动匹配" });
  await panel.waitFor();
  if (!(await panel.getByText("GeoTIFF 影像", { exact: true }).isVisible())) failures.push(`${viewport.name}: raster mode missing`);
  await panel.getByRole("button", { name: /LAS\/LAZ 点云/ }).click();
  if (!(await panel.getByText("同一航飞任务的 LAS/LAZ", { exact: false }).isVisible())) failures.push(`${viewport.name}: point-cloud batch input missing`);
  await panel.getByRole("button", { name: "服务器 / NAS 目录" }).click();
  if (!(await panel.getByPlaceholder(/terra_las_1_4/).isVisible())) failures.push(`${viewport.name}: server directory mode missing`);
  await panel.getByRole("button", { name: /DJI 3D Tiles/ }).click();
  if (!(await panel.getByText("直接登记 PNTS / B3DM，不重复转换", { exact: true }).isVisible())) failures.push(`${viewport.name}: DJI direct-registration mode missing`);
  if (!(await panel.getByRole("button", { name: "本机断点续传" }).isDisabled())) failures.push(`${viewport.name}: local upload must be disabled for a ready tileset`);
  const tilesetPath = panel.getByPlaceholder(/terra_pnts/);
  await tilesetPath.fill("/app/data/remote-sensing/inbox/邵武S1地块/terra_pnts");
  await panel.locator('input[name="name"]').fill("邵武 S1 DJI 点云");
  await page.screenshot({ path: `${outputDir}/spatial-assets-dji-tileset-form-${viewport.name}.png`, fullPage: true });
  if (viewport.name !== "desktop" || !testGeoTiff) {
    await panel.getByRole("button", { name: "登记并自动分析" }).click();
    await panel.getByRole("heading", { name: "正在校验 DJI 3D Tiles 目录" }).waitFor();
    if (registeredTilesetPayload?.path !== "/app/data/remote-sensing/inbox/邵武S1地块/terra_pnts") failures.push(`${viewport.name}: registered path payload mismatch`);
  }

  const pageOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  const panelOverflow = await panel.evaluate((element) => element.scrollWidth - element.clientWidth);
  if (pageOverflow > 2) failures.push(`${viewport.name}: page horizontal overflow ${pageOverflow}px`);
  if (panelOverflow > 2) failures.push(`${viewport.name}: panel horizontal overflow ${panelOverflow}px`);
  if (consoleErrors.length) failures.push(`${viewport.name}: console errors: ${consoleErrors.join(" | ")}`);
  await page.screenshot({ path: `${outputDir}/spatial-assets-dji-tileset-progress-${viewport.name}.png`, fullPage: true });

  if (viewport.name === "desktop" && testGeoTiff) {
    const suffix = Date.now().toString(36);
    const blockCodes = [`VIS-A-${suffix}`, `VIS-B-${suffix}`];
    const geometries = [
      [[[118.10, 26.50], [118.111, 26.50], [118.111, 26.52], [118.10, 26.52], [118.10, 26.50]]],
      [[[118.111, 26.50], [118.13, 26.50], [118.13, 26.52], [118.111, 26.52], [118.111, 26.50]]],
    ];
    for (let index = 0; index < blockCodes.length; index += 1) {
      const seeded = await context.request.post(`${baseURL}/api/forest-blocks`, {
        data: {
          blockCode: blockCodes[index],
          name: `可视化林班 ${index + 1}`,
          countyCode: "350703",
          countyName: "建阳区",
          townCode: "350703101",
          townName: "麻沙镇",
          villageName: "黄坑村",
          baseType: "self_operated",
          operationType: "timber",
          forestType: "毛竹",
          areaMu: 126.5,
          geometry: { type: "Polygon", coordinates: geometries[index] },
        },
      });
      if (!seeded.ok()) failures.push(`coverage seed ${blockCodes[index]}: HTTP ${seeded.status()}`);
    }
    await panel.getByRole("button", { name: /GeoTIFF 影像/ }).click();
    await panel.getByRole("button", { name: "本机断点续传" }).click();
    await panel.locator('input[type="file"]').setInputFiles(testGeoTiff);
    await panel.locator('input[name="name"]').fill(`跨林班自动匹配 ${suffix}`);
    await panel.getByRole("button", { name: "上传并自动分析" }).click();
    await panel.getByRole("heading", { name: "确认实际覆盖林班" }).waitFor({ timeout: 30_000 });
    for (const code of blockCodes) {
      if (!(await panel.getByText(code, { exact: true }).isVisible())) failures.push(`coverage result missing ${code}`);
    }
    if (await panel.locator('input[type="checkbox"]:checked').count() < 2) failures.push("coverage suggestions were not preselected");
    await page.screenshot({ path: `${outputDir}/spatial-assets-coverage-confirmation.png`, fullPage: true });
    await panel.getByRole("button", { name: /确认关联 \d+ 个林班/ }).click();
    await page.getByRole("dialog", { name: `跨林班自动匹配 ${suffix}` }).waitFor({ timeout: 15_000 });
  }
  if (viewport.name === "desktop") {
    let tilesetRequested = false;
    await page.route("**/api/scenes/tiles-map-visual", async (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "tiles-map-visual",
        name: "邵武 S1 DJI 点云",
        fileName: "tileset.json",
        fileType: "application/json",
        size: 1024,
        originalSize: 1024,
        assetType: "pointcloud",
        missionId: "DJI-S1",
        linkedBlockCodes: ["S1-001"],
        processingStage: "ready",
        capturedAt: "2026-08-13T12:00:00",
        resolution: "",
        bounds: [117.02, 27.13, 117.05, 27.16],
        crs: "EPSG:4978",
        width: 0,
        height: 0,
        bands: 0,
        opacity: 1,
        visible: true,
        transferStatus: "tileset-ready",
        tileUrl: "",
        tileJsonUrl: "",
        thumbnailUrl: "",
        tilesetUrl: `${baseURL}/qa-tiles/tileset.json`,
        createdAt: "2026-08-19T00:00:00Z",
        updatedAt: "2026-08-19T00:00:00Z",
      }),
    }));
    await page.route("**/qa-tiles/tileset.json", async (route) => {
      tilesetRequested = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          asset: { version: "1.0" },
          geometricError: 0,
          root: {
            boundingVolume: { region: [2.0426, 0.4735, 2.0432, 0.4741, 0, 500] },
            geometricError: 0,
          },
        }),
      });
    });
    await page.goto(`${baseURL}/v2/map?sceneId=tiles-map-visual&mode=3d`, { waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.waitForFunction(() => document.body.textContent?.includes("三维地球"), null, { timeout: 30_000 });
    await page.getByRole("button", { name: "图层" }).click();
    await page.getByText("三维点云与模型", { exact: true }).waitFor({ timeout: 30_000 });
    await page.waitForTimeout(1_000);
    if (!tilesetRequested) failures.push("desktop: registered tileset was not requested by the Cesium map");
    await page.screenshot({ path: `${outputDir}/spatial-assets-dji-tileset-map-desktop.png`, fullPage: true });
  }
  await context.close();
}

await browser.close();
if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log(`verified spatial asset upload flow at ${viewports.length} viewports; screenshots: ${outputDir}`);
