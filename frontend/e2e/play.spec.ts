import { expect, test, type Page } from "@playwright/test";

// The Red Lantern scene with scripted model replies (backend/tests/e2e_server.py).

async function openDemo(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Red Lantern scene only" }).click();
  await expect(page.getByLabel("What do you do?")).toBeVisible();
}

async function say(page: Page, text: string) {
  await page.getByLabel("What do you do?").fill(text);
  await page.getByRole("button", { name: "Send" }).click();
}

const SECRETS = ["killed", "spirit", "hidden_properties", "renn_killed_oric"];

test("a turn shows mechanics first, then labelled speech and narration", async ({ page, browser }) => {
  await openDemo(page);
  await expect(page.locator(".scene-strip")).toContainText("Red Lantern Tavern");

  await say(page, "I look under the lantern on the tables.");
  const first = page.locator("article.turn").first();
  await expect(first.locator(".mechanics")).toContainText("search");
  await expect(first.locator(".mechanics .roll")).toContainText("1d20");
  await expect(first.locator(".narration")).toContainText("Rain ticks on the shutters");

  await say(page, "Innkeeper, has Oric Dane been in lately?");
  const second = page.locator("article.turn").nth(1);
  await expect(second.locator(".speech .who")).toContainText("Mira");
  await expect(second.locator(".speech q")).toContainText("Not for a week");
  await expect(second).toHaveAttribute("aria-busy", "false"); // the turn has completed

  // the feed lives on the server: a reload, and another device, show the same history
  await page.reload();
  await expect(page.locator("article.turn")).toHaveCount(2);
  const other = await browser.newContext();
  const phone = await other.newPage();
  await phone.goto(page.url());
  await expect(phone.locator("article.turn")).toHaveCount(2);
  await expect(phone.locator("article.turn").nth(1).locator(".speech q")).toContainText("Not for a week");
  await other.close();
});

test("a whisper goes to the chosen listener and their reply is labelled", async ({ page }) => {
  await openDemo(page);
  await page.getByRole("button", { name: "Whisper", exact: true }).click();
  await expect(page.getByRole("button", { name: "Send" })).toBeDisabled(); // no listener yet
  await page.getByLabel("Whisper to").selectOption({ label: "Elara" });
  await say(page, "Just so you know, keep this between us: Mira knows more than she says.");
  const turn = page.locator("article.turn").last();
  await expect(turn.locator(".player-line")).toContainText("whisper → Elara");
  await expect(turn.locator(".speech").filter({ hasText: "Understood." })).toContainText("whispers");
});

test("normal view carries no hidden data; dev view adds traces and Debug", async ({ page, isMobile }) => {
  await openDemo(page);
  await say(page, "I look under the lantern on the tables.");
  await expect(page.locator(".narration").first()).toContainText("Rain");

  // normal mode: no omniscient material anywhere the player can look
  for (const view of isMobile ? ["Character", "Party", "Journal"] : ["Character", "Party", "Journal", "Encyclopedia", "World"]) {
    await page.getByRole("button", { name: view, exact: true }).first().click();
    await expect(page.locator("main")).not.toContainText("Loading…", { timeout: 10_000 });
    const text = (await page.locator("body").innerText()).toLowerCase();
    for (const s of SECRETS) expect(text, `${view} mentions ${s}`).not.toContain(s);
  }
  await expect(page.getByRole("button", { name: "Debug" })).toHaveCount(0);
  await expect(page.getByTestId("trace")).toHaveCount(0);

  // dev view: the toggle reveals a trace per turn and the Debug view
  await page.getByRole("button", { name: "Play", exact: true }).first().click();
  await page.getByRole("switch", { name: /DEV/ }).click();
  await page.getByRole("button", { name: "Trace" }).first().click();
  const trace = page.getByTestId("trace").first();
  await expect(trace).toContainText("action.search");
  await trace.getByRole("tab", { name: /Model calls/ }).click();
  await expect(trace).toContainText("intent_interpreter");

  if (isMobile) {
    await page.getByRole("button", { name: "More" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Debug" }).click();
  } else {
    await page.getByRole("button", { name: "Debug" }).click();
  }
  await expect(page.getByRole("heading", { name: "Debug" })).toBeVisible();
  await expect(page.locator(".card.dev").first()).toContainText("calls");

  // switching dev off leaves the Debug view
  await page.getByRole("switch", { name: /DEV/ }).click();
  await expect(page.getByRole("heading", { name: "Debug" })).toHaveCount(0);
  await expect(page.getByLabel("What do you do?")).toBeVisible();
});
