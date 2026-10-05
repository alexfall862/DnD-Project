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
  await expect(first.getByTestId("dice-roll")).toContainText("Search");
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
  await page.getByRole("group", { name: "Whisper to" }).getByRole("button", { name: "Elara", exact: true }).click();
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

test("a turn in flight keeps its status across views, and dev view shows each model call live", async ({ page }) => {
  await openDemo(page);
  await page.getByRole("switch", { name: /DEV/ }).click();
  await page.getByLabel("What do you do?").fill("I look under the lantern on the tables.");
  await page.getByRole("button", { name: "Send" }).click();
  const turn = page.locator("article.turn").last();
  // live, while the turn runs: a stage label with a clock, and the model calls as they happen
  await expect(turn.getByRole("status")).toContainText("…");
  const calls = turn.getByTestId("live-calls");
  await expect(calls).toContainText("intent_interpreter");
  await expect(calls).toContainText("request sent");
  // leave and come back mid-turn: the turn is still there, and still running or finished
  await page.getByRole("button", { name: "Character", exact: true }).first().click();
  await page.getByRole("button", { name: "Play", exact: true }).first().click();
  const again = page.locator("article.turn").last();
  await expect(again.locator(".player-line")).toContainText("lantern");
  await expect(again).toHaveAttribute("aria-busy", "false", { timeout: 30_000 });
  await expect(again.locator(".narration")).toContainText("Rain ticks");
  // what was sent opens from the trace of the finished turn
  await again.getByRole("button", { name: "Trace" }).click();
  await expect(again.getByTestId("trace")).toContainText("Model calls");
});

test("a called-for check waits for the player's roll, and dev view certifies the engine rolled", async ({ page }) => {
  await openDemo(page);
  await say(page, "Mira, let me in on it.");
  const card = page.getByRole("region", { name: "A roll is called for" });
  await expect(card).toContainText("Persuasion check");
  await expect(card).toContainText("need 14");
  await expect(card).toContainText("Failure");
  // nothing has happened yet: no die has been rolled
  await expect(page.getByTestId("dice-roll")).toHaveCount(0);
  await page.getByRole("switch", { name: /DEV/ }).click();
  await card.getByRole("button", { name: "Roll", exact: true }).click();
  const die = page.getByTestId("dice-roll").last();
  await expect(die).toContainText("vs 14", { timeout: 30_000 });
  await expect(die).toContainText(/Success|Failure|Natural/);
  await die.getByRole("button", { name: /engine dice/ }).click();
  await expect(page.getByTestId("roll-certificate")).toContainText("the same dice");
});

test("the Here strip shows your spot, who is where and the ways out", async ({ page }) => {
  await openDemo(page);
  await page.getByRole("button", { name: /Red Lantern Tavern/ }).click();
  const here = page.getByTestId("here");
  await expect(here).toContainText("Around you");
  await expect(here).toContainText("(you are here)");
  await expect(here).toContainText("Ways out");
  await expect(here).toContainText("min");
});

test("an unsent turn survives a trip to another view", async ({ page }) => {
  await openDemo(page);
  await page.getByLabel("What do you do?").fill("I study the faces at the bar");
  await page.getByRole("button", { name: "Character", exact: true }).first().click();
  await page.getByRole("button", { name: "Play", exact: true }).first().click();
  await expect(page.getByLabel("What do you do?")).toHaveValue("I study the faces at the bar");
});

test("Check mode calls for the named skill, and what it changes is shown", async ({ page }) => {
  await openDemo(page);
  await page.getByRole("button", { name: "Check", exact: true }).click();
  await page.getByLabel("Skill to check").selectOption("skill.investigation");
  await say(page, "the hearth for a loose stone");
  const card = page.getByRole("region", { name: "A roll is called for" });
  await expect(card).toContainText("Investigation check");
  await card.getByRole("button", { name: "Roll", exact: true }).click();
  const turn = page.locator("article.turn").last();
  await expect(page.getByTestId("dice-roll").last()).toBeVisible({ timeout: 30_000 });
  // on a success the ruling's consequence is recorded and shown; on a failure nothing changes
  const die = page.getByTestId("dice-roll").last();
  if ((await die.textContent())?.match(/Success/)) {
    await expect(turn.locator(".consequences")).toContainText("a loose hearthstone");
  }
});

test("the table assistant's suggestion goes into the composer with one tap", async ({ page }) => {
  await openDemo(page);
  await page.getByRole("button", { name: "OOC", exact: true }).click();
  await say(page, "what could I do here?");
  const tryIt = page.getByRole("button", { name: /Try: I search the hearth/ });
  await expect(tryIt).toBeVisible({ timeout: 30_000 });
  await tryIt.click();
  await expect(page.getByLabel("What do you do?")).toHaveValue("I search the hearth for a loose stone");
});

test("reconsidering a called-for check changes nothing", async ({ page }) => {
  await openDemo(page);
  await say(page, "Mira, let me in on it.");
  const card = page.getByRole("region", { name: "A roll is called for" });
  await card.getByRole("button", { name: "Reconsider" }).click();
  await expect(page.locator(".ooc-reply").last()).toContainText("You hold off");
  await expect(page.getByTestId("dice-roll")).toHaveCount(0);
});


test("a whisper can go to several people, and speech can name who it is for", async ({ page }) => {
  await openDemo(page);
  await page.getByRole("button", { name: "Whisper", exact: true }).click();
  const to = page.getByRole("group", { name: "Whisper to" });
  await to.getByRole("button", { name: "Elara", exact: true }).click();
  await to.getByRole("button", { name: "Tomas", exact: true }).click();
  await say(page, "keep this between us: Mira knows more than she says.");
  const t = page.locator("article.turn").last();
  await expect(t.locator(".player-line")).toContainText(/whisper → (Elara, Tomas|Tomas, Elara)/);
  await page.getByRole("button", { name: "Say", exact: true }).click();
  await page.getByRole("group", { name: "Speak to" }).getByRole("button", { name: "Mira", exact: true }).click();
  await say(page, "Innkeeper, has Oric Dane been in lately?");
  const t2 = page.locator("article.turn").last();
  await expect(t2.locator(".player-line")).toContainText("say → Mira");
  await expect(t2.locator(".speech").filter({ hasText: "Not for a week" })).toBeVisible({ timeout: 30_000 });
});
