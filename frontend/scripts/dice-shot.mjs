// Dev aid: screenshot a called-for check and the landed die (dev view on).
//   node scripts/dice-shot.mjs [baseUrl] [outDir]
import { chromium, devices } from "@playwright/test";

const base = process.argv[2] ?? "http://127.0.0.1:5174";
const out = process.argv[3] ?? "screenshots";

async function shot(name, opts) {
  const browser = await chromium.launch();
  const page = await (await browser.newContext(opts)).newPage();
  await page.goto(base);
  await page.getByRole("button", { name: "Red Lantern scene only" }).click();
  await page.getByLabel("What do you do?").fill("Mira, let me in on it.");
  await page.getByRole("button", { name: "Send" }).click();
  const card = page.getByRole("region", { name: "A roll is called for" });
  await card.waitFor({ timeout: 30000 });
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${out}/${name}-roll-card.png` });
  const sw = page.getByRole("switch", { name: /DEV/ });
  if ((await sw.getAttribute("aria-checked")) !== "true") await sw.click();
  await card.getByRole("button", { name: "Roll", exact: true }).click();
  const die = page.getByTestId("dice-roll").last();
  await die.waitFor({ timeout: 30000 });
  await page.waitForTimeout(1500);
  await die.getByRole("button", { name: /engine dice/ }).click();
  await page.getByTestId("roll-certificate").waitFor();
  await page.screenshot({ path: `${out}/${name}-rolled.png` });
  await browser.close();
}

await shot("desktop", { viewport: { width: 1440, height: 900 } });
await shot("phone", { ...devices["Pixel 7"] });
console.log("written to", out);
