// Dev aid: screenshot a turn in flight with dev view on (live status + model-call timeline).
//   node scripts/live-shot.mjs [baseUrl] [outDir]
import { chromium, devices } from "@playwright/test";

const base = process.argv[2] ?? "http://127.0.0.1:5174";
const out = process.argv[3] ?? "screenshots";

async function shot(name, opts) {
  const browser = await chromium.launch();
  const page = await (await browser.newContext(opts)).newPage();
  await page.goto(base);
  await page.getByRole("button", { name: "Red Lantern scene only" }).click();
  await page.getByLabel("What do you do?").waitFor();
  const sw = page.getByRole("switch", { name: /DEV/ });
  if ((await sw.getAttribute("aria-checked")) !== "true") await sw.click();
  await page.getByLabel("What do you do?").fill("I look under the lantern on the tables.");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByTestId("live-calls").last().waitFor();
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${out}/${name}-live.png` });
  await browser.close();
}

await shot("desktop", { viewport: { width: 1440, height: 900 } });
await shot("phone", { ...devices["Pixel 7"] });
console.log("written to", out);
