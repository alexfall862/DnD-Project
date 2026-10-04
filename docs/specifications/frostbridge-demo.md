# Frostbridge Deterministic Demo Fixture v0.2

## 1. Purpose

Frostbridge is the hand-authored deterministic development fixture for the first playable vertical slice. It exists to test objective versus subjective truth, AI-PC knowledge isolation, NPC deception, claims versus facts, mysteries/clues, unique items, hidden mechanics, clocks, faction plans, offscreen simulation, split parties, AI disagreement, memory, save/reload, and event causality before procedural generation becomes the primary source of content.

Fixture data should use stable symbolic keys in seed code (for example `fixture.actor.elara`) that resolve to runtime UUIDs. Tests should not hardcode database UUID values.

## 2. World premise

Setting: **Veyr**.

Twenty years ago a century-long supernatural winter called the **Long Frost** abruptly ended. Northern frontier settlements, roads, institutions, and trade routes are being reclaimed. Ancient magical infrastructure buried beneath the region is beginning to reactivate. Most residents know magic exists, but very few understand the old systems.

## 3. Starting region — The Northern Reach

Traits:

- cold forests;
- rocky uplands;
- river valleys;
- abandoned imperial infrastructure;
- scattered reclaimed settlements.

Named settlements:

- Frostbridge (materialized in detail);
- Bellhaven (outline/reference level);
- Greybank (outline/reference level).

## 4. Frostbridge

Small town of roughly 1,800 residents.

Economy:

- river trade;
- timber;
- frontier supply;
- salvage.

Suggested simulation state:

```yaml
prosperity: 52
security: 64
food_supply: 71
political_stability: 48
outsider_hostility: 35
```

Active pressures:

- merchant Oric Dane has disappeared;
- restricted river docks are being used for smuggling;
- refugees have arrived from farther north;
- merchants dispute increased bridge tolls;
- strange noises/lights are reported beneath an abandoned quarry.

## 5. Locations

Materialized at seed:

- Town Gate
- Market Square
- Red Lantern Tavern
- Guard House
- Warehouse District
- Oric's Warehouse
- Restricted Dock
- River Bridge
- North Road
- Old Quarry Entrance

Latent/background:

- residences;
- temple;
- smithy;
- other warehouse buildings;
- cemetery;
- river islands.

### Topology

Town Gate connects to Market Square and North Road. Market Square connects to Red Lantern, Guard House, River Bridge, and Warehouse District. Warehouse District connects to Oric's Warehouse and Restricted Dock. North Road connects toward the Old Quarry.

Example travel times:

- Tavern → Guard House: 5 minutes
- Tavern → Restricted Dock: 12 minutes
- Town → Quarry: 45 minutes on foot

## 6. Opening scene

Location: Town Gate / Market Square boundary.

Time: late afternoon.

Weather: cold rain.

Visible situation: a wagon has lost a wheel near the gate; two guards and an irritated merchant argue about traffic; Red Lantern windows glow nearby; the party has just completed several days of travel and needs lodging.

No mandatory quest is presented. The party can help, talk, seek lodging, explore, leave, or do something else.

## 7. Human PC fixture — Alex

Controller: human.

Default mechanical test build:

```yaml
Might: 5
Agility: 6
Intellect: 6
Presence: 5
Resolve: 5
```

Skills:

- Investigation 2
- Awareness 2
- Persuasion 1
- Athletics 1
- Ranged 1
- Survival 1

Initial knowledge: knows Frostbridge exists and that Elara/Tomas are companions; does not initially know Oric or Captain Renn.

The seed may allow the human character to be replaced/customized while retaining the same fixture relationships.

## 8. AI companion — Elara Venn

Concept: former frontier scout in her early 30s searching for missing younger brother Joren Venn.

Attributes:

```yaml
Might: 5
Agility: 7
Intellect: 6
Presence: 4
Resolve: 6
```

Skills:

- Survival 3
- Awareness 2
- Ranged 2
- Stealth 2
- Investigation 1
- Medicine 1

Traits: Keen Observer, Frontier Veteran.

Behavior dimensions:

```yaml
risk_tolerance: 0.65
aggression: 0.40
empathy: 0.67
curiosity: 0.60
loyalty: 0.72
impulsiveness: 0.35
honesty: 0.75
sociability: 0.42
ambition: 0.38
```

Goals:

- find Joren;
- protect vulnerable frontier residents where practical;
- avoid becoming dependent on others.

Core-memory seeds:

- Joren leaving home after an argument;
- surviving an expedition where officials failed to send promised aid;
- Alex helping the group during an earlier dangerous journey.

Initial general beliefs: frontier authorities often protect themselves first (0.65); authority deserves scrutiny (0.70).

She does **not** initially know Renn is a smuggler/murderer or that Mira witnessed Renn meeting Oric.

## 9. AI companion — Tomas Vale

Concept: former municipal guard and civic-minded traveler.

Attributes:

```yaml
Might: 6
Agility: 5
Intellect: 5
Presence: 7
Resolve: 6
```

Skills:

- Persuasion 3
- Melee 2
- Awareness 2
- Intimidation 1
- Lore 1
- Medicine 1

Traits: Guard Training, Well Connected.

Behavior dimensions:

```yaml
risk_tolerance: 0.50
aggression: 0.45
empathy: 0.62
curiosity: 0.42
loyalty: 0.68
impulsiveness: 0.30
honesty: 0.82
sociability: 0.76
ambition: 0.45
```

Goals:

- prove public institutions can still serve people honestly;
- build useful civic connections in frontier settlements;
- avoid becoming cynical like former colleagues.

Initial beliefs: most guards are ordinary people trying to keep order (0.78); accusations against officials require evidence (0.82).

He does not know Renn personally before arriving.

## 10. Companion relationship seed

Elara → Tomas:

- trust 48
- respect 55
- affection 20
- fear 0
- resentment 8
- familiarity 45

Tomas → Elara:

- trust 62
- respect 68
- affection 28
- fear 0
- resentment 4
- familiarity 45

Their philosophical disagreement should create natural friction without forced hostility.

Companion ↔ Alex seeds (required by the worked testimony values in
`belief-update-rules.md` §4, which assume Elara→Alex trust ≈ 60):

Elara → Alex: trust 60, respect 52, affection 35, fear 0, resentment 2, familiarity 50

Tomas → Alex: trust 55, respect 50, affection 30, fear 0, resentment 0, familiarity 50

Alex → Elara: trust 55, respect 58, affection 30, fear 0, resentment 0, familiarity 50

Alex → Tomas: trust 50, respect 50, affection 25, fear 0, resentment 0, familiarity 50

## 11. Mira Holt

Owner/innkeeper of the Red Lantern. Importance: important.

Personality: practical, protective, observant, risk-averse, dry humor.

Goals:

- keep family/business safe;
- avoid open conflict with Captain Renn.

Objective knowledge:

- Oric visited Red Lantern two nights before disappearing;
- Renn met Oric privately that night;
- conversation became tense;
- Renn left first;
- Oric appeared frightened afterward.

Mira does **not** know Renn murdered Oric, where Oric died, or the full smuggling operation.

Relationship/emotion seeds toward Renn: fear 48, trust -35, respect 5. Toward Oric: affection 42, trust 58.

Mira is likely to evade questions if Renn/guards are nearby and may reveal more privately after trust develops.

## 12. Captain Dalen Renn

Role: captain of Frostbridge town guard. Importance: full.

Personality: controlled, socially competent, pragmatic, status-conscious, increasingly desperate.

### Objective truth

Renn is part of a smuggling operation moving restricted salvage through river docks. Oric discovered evidence linking Renn to it. Renn confronted Oric at the restricted dock and killed him during the confrontation; the death was not originally planned. Renn concealed the body outside town and altered the guard log.

This truth is locked once the mystery activates.

### Renn goals

- prevent discovery of Oric's fate;
- ensure the next smuggling shipment leaves successfully;
- accumulate enough money to leave Frostbridge before the operation collapses.

### Renn knowledge

Knows he killed Oric, where it happened, where the body is, which log entry he removed, who the smugglers are, and when the next shipment leaves. He does not know what additional evidence Oric may have hidden.

## 13. Oric Dane

Merchant/warehouse owner.

Objective lifecycle at campaign start: dead.

Public/most-actor belief: missing/unknown.

Before death Oric:

1. found shipping discrepancies;
2. copied suspicious transactions into a private ledger;
3. wrote a warning letter;
4. met Renn at Red Lantern;
5. confronted Renn near restricted dock;
6. was killed;
7. had his body concealed;
8. had a guard-log entry removed by Renn.

## 14. Locked mystery

Question: **What happened to Oric Dane?**

Objective truth: Captain Renn killed Oric after Oric discovered Renn's role in smuggling.

Status: active.

`solution_locked = true`.

## 15. Clues

### Merchant Ledger

Location: Oric's Warehouse. Hidden but discoverable. Contains repeated inventory discrepancies tied to restricted dock schedules. Supports smuggling investigation/dock relevance but not murder by itself.

### Mira's witness account

Dynamic social clue: Renn met Oric, they argued, Oric looked frightened afterward. Supports recent contact/conflict.

### Restricted Dock Mud

Distinct pale clay associated with restricted dock and found on relevant Oric evidence. Supports that Oric visited the dock. Requires observation/investigation to connect.

### Missing Guard Log Entry

Guard records show a numbered chronological gap around a restricted-dock patrol on the night Oric disappeared. Initially recoverable through physical draft, clerk memory, and administrative inconsistency. Physical draft becomes unavailable after Day +3, but alternate routes remain.

### Oric's Hidden Letter

Persistent immutable Document. Suggested text:

> If anything happens to me, look to the river. The manifests don't match what moves after midnight. I made the mistake of asking the wrong man about it.

The letter does not name Renn.

## 16. Red herring — debt to Mira

Objective fact: Oric owed Mira a meaningful but ordinary business debt and they argued about repayment. This makes Mira a plausible early suspicion but does not imply murder.

## 17. Mystery redundancy

Routes include Mira → Renn connection; warehouse → ledger → docks; mud → docks; Guard House → missing log; letter → river activity; observation of smugglers → Renn associates.

Loss of one clue cannot make the mystery unsolvable.

## 18. River Compact

Local smuggling faction, not a grand criminal empire.

Resources: moderate cash, dock access, three reliable laborers, one corrupt guard captain, two external buyers.

Public existence: unknown.

Goal: move next restricted-salvage shipment out of Frostbridge.

Plan:

1. assemble cargo;
2. destroy documentation linking Renn;
3. load barge;
4. depart at night;
5. pay external buyer.

Campaign start: step 1.

## 19. World clocks

Campaign starts at Day 0.

### Day +2

Trade caravan arrives, increasing activity and potentially witnesses/opportunities.

### Day +3

Renn destroys remaining physical guard-log draft. Numbering inconsistencies/clerk memory/other mystery paths remain.

### Day +5

River Compact attempts shipment departure if prerequisites remain valid.

### Day +8

Old Quarry disturbance escalates.

Scheduled events must revalidate prerequisites. If Renn is arrested, he cannot personally execute evidence destruction; simulator chooses a coherent alternative or no event.

## 20. Quarry pressure

Latent objective truth: ancient magical machinery beneath the abandoned quarry has begun intermittently activating.

Initial evidence: metallic noises, blue night light, frightened worker.

Do not deeply materialize the underground complex until the party investigates.

This unrelated clock proves the world advances beyond the main mystery.

## 21. Order of the Glass Sun

Regional faction studying/restoring pre-Frost magical infrastructure. Public reputation: scholarly but secretive. Current regional goal: locate a missing relay site in the Northern Reach.

Not initially central to Oric's murder; provides longer-term campaign structure.

## 22. Veyra's Chipped Dagger

Unique item instance, initially in Oric's Warehouse.

Known physical properties: well-made old dagger, chipped near tip, normal dagger damage.

Hidden objective property: +2 damage against spirit-tagged entities.

Hidden lore: forged from metal salvaged from a pre-Frost relay structure.

Finding the dagger reveals the physical item, not the hidden mechanic. Discovery routes for hidden property: use against a spirit, successful supernatural identification, research markings, or knowledgeable specialist.

## 23. Generated artifact test slot

At campaign creation request one low-tier unusual Long Frost artifact with at most one passive and one activated effect using registered primitives; forbid teleportation, resurrection, and permanent attribute increase. Save it as a campaign-specific mechanical definition with snapshot mechanics.

In deterministic fixture mode, FakeModelProvider returns a fixed valid artifact.

## 24. Party

Members: Alex (human), Elara (AI), Tomas (AI). Shared basic travel supplies and modest currency. Do not optimize perfectly.

Elara's authority skepticism and Tomas's institutional trust should generate genuine disagreement as evidence accumulates; neither viewpoint is scripted to “win.”

## 25. First social test — Mira

Player asks whether Renn was present the night Oric disappeared. Mira objectively knows yes. If guards are nearby, fear makes evasion likely; if trusted privately, she can reveal partial truth. Same knowledge, different context/decision.

Her partial reveal is `conveys: [{fact_ref: renn_met_oric, fidelity: partial}]`, which records
`clue_discoveries(route = testimony, fidelity = partial)` for each party member who hears it
(`communication-and-knowledge.md` §6).

## 26. First deception test — Renn

Asked when he last spoke to Oric, Renn may say “Weeks ago.” Structured output marks `speech_act=deception`, `knowingly_false=true`, and `conveys: [{fact_ref: renn_met_oric_that_night, stance: asserts_false, deliberate_false: true}]`. Recipients receive the spoken Claim, not the private flags. Expected recipient beliefs follow `belief-update-rules.md` §4 (Tomas, no prior relationship: `suspected ≈0.35–0.45`). The FakeModel fixture for this line must include the `conveys[]` entry; a variant fixture whose `conveys[]` references the murder fact must be rejected by the authorization check.

## 27. First whisper test

Alex privately tells Elara “I think Mira had something to do with Oric's disappearance.”

Expected:

- Alex knows he expressed the suspicion;
- Elara knows Alex suspects Mira;
- Tomas does not know;
- Mira does not know unless she legitimately overhears;
- objective world truth is unchanged;
- Elara may or may not adopt the suspicion.

Exact expected belief rows are given in `communication-and-knowledge.md` §8 and the worked
values in `belief-update-rules.md` §4. With the seeded Elara→Alex trust, Elara stores
`Alex suspects Mira` (`known 1.0`) and `Mira involved` (`suspected ≈0.56`); Alex stores
`Mira involved` (`stated/suspected 0.55`). The human sees only Alex's narration; Tomas's scene,
if separate, is offscreen (`human-visibility.md` §3).

## 28. First split-party test

Alex + Elara investigate warehouse; Tomas visits Guard House.

Warehouse group discovers ledger; Tomas discovers missing-log anomaly.

Before actual communication, neither group knows the other's findings despite party membership. Reunion does not synchronize automatically. Knowledge propagates only through speech/observation/document sharing.

Time: the warehouse scene is live (Alex is the focus actor) and advances the world clock; the
Guard House scene is offscreen and catches up per `time-accounting.md` §4 with at most one
bounded Tomas call. Reunion merges the scenes and equalizes `local_tick`. The human receives
nothing from the Guard House scene unless `spectator_mode` is on, and even then no Observation
for Alex is created.

## 29. Private AI action test

If Elara's brother goal becomes urgent and the party ignores leads, she may privately seek information. Spotlight/simulation budgets prevent runaway activity. Alex learns only through observation, disclosure, third-party reporting, or evidence.

## 30. Combat fixture

Near the warehouse at night, two desperate dock thieves attempt to steal supplies. They are not secret central villains.

Thief template:

```yaml
Might: 4
Agility: 6
Intellect: 4
Presence: 4
Resolve: 4
Health: 18
```

Skills: Stealth 2, Melee 1, Athletics 1. Equipment: knife, dark clothing. Goal: steal useful goods and escape; prefer fleeing/surrendering over fighting to death.

Tests initiative, distance bands, cover, AI turns, reactions, surrender/nonlethal outcomes.

## 31. Environmental improvisation

Warehouse contains wooden table, hanging oil lantern, stacked crates, cloth curtain, side window, heavy shelf. These invite barricades, fires, improvised cover, window escapes, and dropped crates so Rules Adjudicator is exercised.

Persistent consequences remain after combat. A burned curtain stays burned; a moved shelf remains blocking until changed.

## 32. Relationship test

Tomas may initially defend Renn's professionalism. Elara can respect Tomas's principles while becoming mildly frustrated. If Tomas later acknowledges evidence and revises his view, trust/respect may improve. All numeric changes require event-linked relationship deltas.

## 33. False-belief test

Possible early subjective states:

- Alex suspects Mira 0.55;
- Elara suspects Renn 0.45;
- Tomas thinks Oric may have fled voluntarily 0.40;
- objective truth remains Renn killed Oric.

## 34. Memory test

After Alex privately confides in Elara, Elara may store “Alex privately trusted me with his suspicion about Mira.” Tomas must not have a memory of the exchange. After restart, Elara should retrieve it when later discussing Mira or Alex's trust.

Optional later distortion test: repeated subjective experiences can compress into a broader belief/memory while preserving source lineage.

## 35. Persistent document test

Oric's hidden letter is an immutable Document entity and returns byte-for-byte identical text every reread.

## 36. Evidence destruction

At Day +3, the physical guard-log draft becomes destroyed via scheduled event. The mystery remains solvable through numbering inconsistency, clerk memory, and other clue paths.

## 37. Shipment simulation

At Day +5, shipment attempts departure if cargo/barge/Renn assistance prerequisites remain valid. If players disrupt prerequisites, simulation re-evaluates rather than forcing the original event.

## 38. Offscreen simulation

If the party leaves Frostbridge for four days: Day +2 caravan arrives, Day +3 evidence changes, River Compact plan advances, quarry clock progresses, and relevant companion personal plans may continue. No continuous per-NPC agent loop is required.

## 39. Control transfer compatibility

If Alex dies in a future test, control can transfer to Tomas (or another actor) without altering Tomas's existing memories, beliefs, goals, relationships, or history.

## 40. Seed implementation

Recommended data-driven fixture directory:

```text
backend/app/worldgen/seeds/frostbridge/
  world.yaml
  actors.yaml
  locations.yaml
  facts.yaml
  beliefs.yaml
  relationships.yaml
  mystery.yaml
  items.yaml
  clocks.yaml
```

A Python seed service can orchestrate validation/event creation.

`make seed-demo` should ensure Core Adventure is installed; create campaign/timeline/clock; create entities/locations/topology; actors/controllers/party/resources; facts/beliefs/relationships/goals/plans; mystery/clues/items; scheduled events/opening scene; verify invariants; print campaign ID.

Seed must fail transactionally on invalid references, missing mystery truth, invalid rules, leaked secret knowledge, invalid item mechanics, controller gaps, or topology errors.

## 41. Deterministic fixture mode

`FIXTURE_MODE=true` can use fixed random seed, FakeModelProvider, and fixed generated-artifact response. Interactive development can point the same world at the real local model.

## 41a. Player assertion fixtures

Under the default `personal` policy (`player-authored-canon.md`):

- "I check the compass my father gave me" → `self_minor`, accepted: an `item` entity with empty
  mechanics is created in Alex's possession, event `created_by_type = player_assertion`.
- "I draw the enchanted blade I always carry" → `self_major`, adjudicated: Rules Adjudicator
  proposes an ordinary blade (no enchantment) or refusal with an OOC note.
- "There's a back door out of the tavern" → `world_minor`, adjudicated (World Author decides
  against the materialized Red Lantern layout).
- "Renn is the killer, I know it" → `contradiction` with locked truth → refused as a Fact; it is
  still stored as Alex's `stated` belief/Claim.

## 41b. Budget expectations

With the configured local model the scripted path should run: tavern turns at ≤ 3 synchronous
calls each; the thief combat at ≤ 20 s per round p50 with fallback policies engaged by round 3;
the four-day advance with ≤ 4 simulator calls total. `turn_metrics` is the evidence.

## 42. Initial leakage matrix

| Information | Alex | Elara | Tomas | Mira | Renn |
|---|---|---|---|---|---|
| Oric publicly missing | may learn | may learn | may learn | yes | yes |
| Oric actually dead | no | no | no | no | yes |
| Renn met Oric | no | no | no | yes | yes |
| Renn killed Oric | no | no | no | no | yes |
| Renn smuggling role | no | no | no | partial/suspicion at most | yes |
| Hidden ledger | no | no | no | no | uncertain |
| Guard log altered | no | no | no | no | yes |
| Dagger harms spirits | no | no | no | no | no |

This becomes automated fixture assertions.

## 43. Deterministic vertical-slice path

1. Party enters Red Lantern.
2. Ask Mira about Oric.
3. Whisper suspicion to Elara; assert Tomas does not know.
4. Tomas speaks positively of Renn; allow disagreement.
5. Split party: Alex+Elara warehouse, Tomas Guard House.
6. Warehouse group discovers ledger/dagger; hidden property remains unknown.
7. Tomas discovers log anomaly.
8. Run warehouse thief encounter.
9. Rejoin; assert knowledge still asymmetric before conversation.
10. Characters exchange discoveries; assert propagation.
11. Question Renn; he lies; store Claim, not Fact.
12. Advance four days; caravan/evidence/shipment/quarry clocks process.
13. Restart application.
14. Reload and verify item ownership, hidden mechanics, beliefs, relationships, goals, memories, clue states, scheduled events, and world clock.

## 44. Completion criteria

Frostbridge must reliably demonstrate objective truth vs belief, locked mystery truth, NPC knowledge boundaries, deliberate deception, AI companion disagreement, private communication, split-party knowledge, unique item history, hidden mechanics, improvised rules, programmatic dice, combat, offscreen simulation, evidence destruction, persistent relationships, subjective memory, full restart/reload, and debug traceability.
