// Dev aid: drive the UI against a running API and save screenshots at desktop and phone sizes.
//   node scripts/screenshots.mjs [baseUrl] [outDir]
import { chromium, devices } from "@playwright/test";

const base = process.argv[2] ?? "http://127.0.0.1:5174";
const out = process.argv[3] ?? "screenshots";

async function session(name, contextOptions) {
  const browser = await chromium.launch();
  const ctx = await browser.newContext(contextOptions);
  const page = await ctx.newPage();
  page.on("pageerror", (e) => console.log(`[${name}] page error:`, e.message));
  await page.goto(base);
  await page.getByRole("button", { name: "Red Lantern scene only" }).click();
  await page.getByLabel("What do you do?").waitFor();
  await page.screenshot({ path: `${out}/${name}-1-scene.png` });
  await page.getByLabel("What do you do?").fill("I look under the lantern on the tables.");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByText("Rain ticks on the shutters").first().waitFor({ timeout: 30000 });
  await page.getByLabel("What do you do?").fill("Innkeeper, has Oric Dane been in lately?");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByText("Not for a week").first().waitFor({ timeout: 30000 });
  await page.screenshot({ path: `${out}/${name}-2-played.png` });
  await page.getByRole("switch", { name: /DEV/ }).click();
  await page.getByRole("button", { name: "Trace" }).first().click();
  await page.getByTestId("trace").first().waitFor();
  await page.screenshot({ path: `${out}/${name}-3-dev-trace.png`, fullPage: false });
  await browser.close();
}

await session("desktop", { viewport: { width: 1440, height: 900 } });
await session("phone", { ...devices["iPhone 13"] });
console.log("screenshots written to", out);
