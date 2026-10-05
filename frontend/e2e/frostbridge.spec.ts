import { expect, test, type Page } from "@playwright/test";

// Milestone 10 acceptance: the Frostbridge scripted scenario played from the browser, with the
// model replaced by the vertical slice's script (backend/tests/e2e_server.py, E2E_FIXTURE=
// frostbridge). Combat staging (thieves placed by the engine) stays in the backend slice test;
// everything a player does here goes through the UI.

const SECRETS = ["killed oric", "renn_killed_oric", "spirit", "hidden_properties", "truth_status"];

async function turn(page: Page, text: string) {
  const before = await page.locator("article.turn").count();
  await page.getByLabel("What do you do?").fill(text);
  await page.getByRole("button", { name: "Send" }).click();
  const t = page.locator("article.turn").nth(before);
  await expect(t).toHaveAttribute("aria-busy", "false", { timeout: 30_000 });
  await expect(t.locator(".error-box")).toHaveCount(0);
  return t;
}

async function whisper(page: Page, to: RegExp, text: string) {
  await page.getByRole("button", { name: "Whisper", exact: true }).click();
  const group = page.getByRole("group", { name: "Whisper to" });
  const names = await group.getByRole("button").allTextContents();
  const label = names.find((o) => o !== "Party" && to.test(o));
  expect(label, `a whisper target matching ${to} among ${names.join(", ")}`).toBeTruthy();
  await group.getByRole("button", { name: label!, exact: true }).click();
  const t = await turn(page, text);
  await page.getByRole("button", { name: "Auto", exact: true }).click();
  return t;
}

async function noSecrets(page: Page, where: string) {
  const text = (await page.locator("body").innerText()).toLowerCase();
  for (const s of SECRETS) expect(text, `${where} shows "${s}"`).not.toContain(s);
}

async function view(page: Page, name: string) {
  await page.getByRole("navigation").getByRole("button", { name, exact: true }).click();
}

test("the Frostbridge scenario is playable from the browser", async ({ page }) => {
  test.setTimeout(240_000);
  await page.goto("/");
  await page.getByRole("button", { name: "New Frostbridge demo" }).click();
  await expect(page.locator(".scene-strip")).toContainText("Gate", { timeout: 60_000 }); // seeding

  // 1. the gate notice
  let t = await turn(page, "I read the notice on the gatepost.");
  await expect(t.locator(".mechanics")).toContainText("read");

  // 2. to the Red Lantern: the party moves together
  await turn(page, "We head to the Red Lantern, all three of us.");
  await expect(page.locator(".scene-strip")).toContainText("Red Lantern");

  // 3. Mira evades in public, tells more in a whisper
  t = await turn(page, "Innkeeper, has Oric Dane been in lately?");
  await expect(t.locator(".speech").first()).toBeVisible();
  t = await whisper(page, /innkeeper|Mira/i, "Just between us: did he meet someone before he vanished?");
  await expect(t.locator(".speech q").first()).toContainText("argued");

  // 4. a private whisper to Elara; 5. Tomas on the captain
  // the whole party is one tap away when whispering (here only Elara is chosen)
  await page.getByRole("button", { name: "Whisper", exact: true }).click();
  await expect(page.getByRole("group", { name: "Whisper to" }).getByRole("button", { name: "Party" })).toBeVisible();
  await page.getByRole("button", { name: "Auto", exact: true }).click();
  t = await whisper(page, /Elara/, "I think the innkeeper had something to do with his disappearance.");
  await expect(t.locator(".player-line")).toContainText("whisper → Elara");
  await turn(page, "Tomas, what do you make of the captain?");
  await noSecrets(page, "the tavern");

  // 6. the party splits: Tomas leaves for the guard house; Alex and Elara for the warehouse
  await turn(page, "Tomas, would you look at the guard house records?");
  await turn(page, "Elara and I go to the shuttered warehouse with the merchant sign.");
  // Alex has not learned the place's name: the strip says so rather than leaking it
  await expect(page.locator(".scene-strip")).toContainText("with Elara");
  await expect(page.locator(".scene-strip")).not.toContainText("Mira");
  await view(page, "Party");
  await expect(page.locator("main .member").filter({ hasText: "Tomas" })).toContainText("away");
  await view(page, "Play");

  // 7. the warehouse: ledger and dagger, the dagger's hidden property never shown
  await turn(page, "I search the office.");
  await turn(page, "I read the ledger.");
  await turn(page, "I search the main floor.");
  await turn(page, "I pick up the dagger.");
  await view(page, "Character");
  await expect(page.locator("main")).toContainText(/dagger/i);
  await noSecrets(page, "the character sheet");
  await view(page, "Play");

  // 9–11. rejoin, share the ledger, Renn
  await turn(page, "We go over to the guard house.");
  await turn(page, "Tomas, we found Oric's ledger. The dock numbers don't match.");
  await turn(page, "We go back to the tavern.");
  t = await turn(page, "Captain, when did you last speak to Oric Dane?");
  await expect(t.locator(".speech").first()).toBeVisible();
  await noSecrets(page, "the feed");

  // the encyclopedia knows Oric by name, and only what Alex knows
  await view(page, "Encyclopedia");
  await expect(page.locator("main")).toContainText("Oric");
  await noSecrets(page, "the encyclopedia");

  // a developer expands a turn to trace its resolution, then ends the scene and lets days pass
  await view(page, "Play");
  await page.getByRole("switch", { name: /DEV/ }).click();
  await page.getByRole("button", { name: "Trace" }).last().click();
  await expect(page.getByTestId("trace").last()).toContainText("Model calls");
  await view(page, "Debug");
  await page.getByRole("tab", { name: "Controls" }).click();
  await page.getByRole("button", { name: /End scene/ }).click();
  await expect(page.locator("pre.json").last()).toContainText("checkpoints", { timeout: 30_000 });
  await page.getByLabel("Hours").fill("96");
  await page.getByRole("button", { name: "Advance and simulate" }).click();
  await expect(page.locator("pre.json").last()).not.toContainText("error", { timeout: 60_000 });
  await page.getByRole("switch", { name: /DEV/ }).click();

  // the journal now holds the scene's entry
  await view(page, "Journal");
  await expect(page.locator("article.card").first()).toBeVisible();
  await noSecrets(page, "the journal");
});
