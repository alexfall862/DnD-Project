# Persistent AI TTRPG Engine — Campaign & World Generation v0.1

## 1. Goal

Campaign creation should produce a structured, playable world rather than a giant setting essay.

The generator should create broad structure globally, deep detail locally, fixed truths where necessary, and leave distant unused content shallow/latent until play makes it relevant.

> **Generate the world's structure broadly, but its playable detail progressively.**

## 2. Creation modes

### Surprise Me

The player supplies minimal constraints such as campaign length and starting party size. The system chooses the remaining genre/tone/world configuration.

### Guided Creation

The system conversationally learns preferences such as genre, seriousness, humor, combat lethality, magic/technology prevalence, political complexity, simulation scope, survival detail, campaign length, narrative pressure, and AI party size.

The interaction should infer multiple settings from natural-language answers rather than behaving like a 100-field form.

### Custom / Imported World

The user can provide plain language, Markdown, PDFs, notes, character sheets, maps, rules notes, or structured data. The importer extracts entities, locations, facts, history, cultures, factions, relationships, important characters, secrets, and relevant mechanical assumptions into the same internal data model.

## 3. CampaignBrief

All creation modes compile to one structured CampaignBrief containing campaign mode, genres, tone dimensions, technology, supernatural assumptions, politics, world-simulation scope/depth, combat lethality, central plot pressure, mystery frequency, character focus, expected length, and starting party shape.

This becomes the shared input to all subsequent generation stages.

## 4. Genre modules

Genre changes world assumptions and available content, not merely prose style.

Possible modules include heroic fantasy, dark fantasy, low fantasy, science fantasy, space opera, cyberpunk, cosmic horror, western, noir, superhero, post-apocalyptic, historical, weird fiction, and survival.

A genre module can contribute item templates, traits, conditions, abilities, technology assumptions, common resources, encounter tags, world-generation constraints, and content families.

Multiple genre modules may combine when the fictional synthesis makes sense. Modules may declare compatibility/conflict metadata, but deliberate unusual combinations should remain possible.

## 5. Generation stages

Recommended pipeline:

1. Campaign Brief
2. Setting Premise
3. Physical / Metaphysical Rules
4. Macro Geography
5. Cultures
6. Political Structures
7. Major Factions
8. Historical Backbone
9. Current World State
10. Major Conflicts
11. Secrets
12. Campaign Pressures
13. Starting Region
14. Starting Settlement
15. Local Factions
16. Important NPCs
17. Starting Opportunities
18. Starting Party Integration
19. Opening Scene

Each stage returns structured proposals, validates them, commits them, and becomes input to later stages.

## 6. Setting premise

The first stage creates a concise identity and central tensions for the world, plus structured thematic facts.

Example: a continent emerging from a century-long magical winter, rebuilding borders while ancient things preserved beneath the ice awaken.

The premise should generate play opportunities rather than decorative lore.

## 7. Physics and metaphysics

Define only the foundational questions the setting needs: whether magic exists, how common/reliable it is, resurrection, gods/afterlife, FTL travel, supernatural laws, technology ceilings, etc.

These are high-level rules of reality and normally become established campaign canon immediately.

## 8. Macro geography

Generate continents/regions, climate bands, major routes, political boundaries, rivers/seas/mountain systems, and a few major settlement anchors.

Distant regions remain outlines. Do not generate every village in the world at campaign creation.

## 9. Cultures

Culture records can include homeland, languages, values, social structures, religions, customs, attitudes, technology, magic attitudes, and historical experiences.

Avoid monocultures: include internal variation and contested identities where useful.

## 10. Political structures

Generate states, city-states, tribes, corporations, governments, religious powers, alliances, confederations, and similar structures at appropriate resolution.

## 11. Factions

Each important faction should have public identity, ideology, public/hidden goals, resources, capabilities, territory, allies, rivals, leaders, plans, and simulation priority.

At least one active plan makes a faction actionable for the world simulator.

## 12. Historical backbone

Generate history that explains the current world rather than an exhaustive chronology.

Useful layers:

- ancient foundational events;
- major events in the last century;
- recent events in the last decade;
- immediate events in the last year.

History should connect to borders, faction relationships, attitudes, ruins, mysteries, and active conflicts.

## 13. Current world state and conflicts

Create a present-tense snapshot of wars, succession crises, economic disruption, plagues, migration, religious movements, technology/magic changes, environmental events, and other relevant conditions.

A small-scale campaign can generate local conflicts instead of global crises.

Each conflict should have participants, stakes, causes, current status, escalation/de-escalation possibilities, and player relevance.

## 14. Secrets

Important hidden truths are explicit structured facts with knowledge holders, suspected-by actors, consequences, and discovery routes.

Secrets do not live only inside prose.

## 15. Mysteries

Mysteries use truth-first generation:

`truth → participants → motive/cause → timeline → evidence → witnesses → clue routes → red herrings → discovery conditions`

Before activation, validate internal consistency, timeline plausibility, multiple discovery routes, redundancy if one clue is lost, accessibility, and that red herrings do not contradict the actual truth.

## 16. Campaign pressures rather than mandatory quests

Generate active pressures such as disappearing settlements, political instability, criminal expansion, resource shortages, ancient technology activation, or local feuds.

Campaign mode changes how strongly those pressures are organized into arcs.

### Authored mode

Can generate acts, expected turning points, important revelations, and antagonist trajectories, but should still represent situations and multiple paths rather than mandatory scenes.

### Sandbox mode

Creates multiple opportunities, factions, conflicts, locations, and rumors without privileging one storyline.

### Emergent simulation mode

Emphasizes faction plans, clocks, resource pressures, NPC goals, and political relationships; world activity generates story.

## 17. Starting region

The starting region is much more detailed than the broader world: terrain, settlements, roads, wilderness, local history, economy, regional factions, common dangers, travel conditions, rumors, and several unexplored sites.

## 18. Starting settlement

The first settlement must be immediately playable. Generate identity, population scale, layout, government, economy, social divisions, services, important buildings, conflicts, important NPCs, rumors, current events, and nearby adventure sites.

Not every building requires an entity before it matters.

Settlement simulation state can include prosperity, security, food supply, political stability, outsider hostility, and active pressures.

## 19. Important and background NPCs

A starting town might have roughly 6–12 important NPCs plus 10–20 lightweight seeds and unlimited on-demand background generation.

Important NPCs receive personality, goals, beliefs, relationships, knowledge, secrets, mechanics, and schedule. Background seeds can initially be name + occupation + one trait + one relationship + one concern, then be promoted when play makes them important.

## 20. Social graph

NPCs should not be generated as isolated strangers. Relationships between them create immediate social structure and help mysteries/negotiations feel coherent.

## 21. Starting opportunities

Generate several situations with multiple exposure methods rather than a list of “quests.” A missing merchant might be discoverable through a tavern conversation, notice board, family member, guard questioning, or abandoned wagon.

The player can ignore all of them.

## 22. Party integration

Starting AI companions need plausible reasons to be together: friends, coworkers, family, expedition members, shared survivors, recent hires, etc. They should have reasons to remain initially but are never permanently bound to the player.

If the player begins solo, ordinary NPCs can organically become companions. There is no magical “recruitable NPC” flag. A random baker can refuse an absurd invitation or eventually join if circumstances and personality justify it.

## 23. Character generation

Character creation supports guided conversation, manual form, AI-assisted generation, random generation, and import. All compile to the same validated mechanical representation.

AI companions additionally receive behavioral profile, goals, fears, values, core memories, tactical preferences, starting beliefs, relationships, and autonomy profile.

Starting companions should be differentiated mechanically and psychologically without forcing optimal party composition.

## 24. Opening scene

Campaign generation ends by creating opening location, current world time, weather, present actors, immediate situation, and player-visible description. It should present possibilities rather than force a quest.

Once play starts, ordinary session orchestration replaces campaign-generation mode.

## 25. Initial quality checks

Before play, validate:

- no established-canon contradictions;
- all entity references resolve;
- starting settlement is reachable/playable;
- AI PCs are mechanically legal;
- important NPCs have goals;
- major factions have active plans;
- opportunities have discovery routes;
- mysteries have fixed truths;
- perspectives do not leak secrets;
- ruleset references are valid.

## 26. Pre-play regeneration

Before canon is established, users can regenerate individual factions, companions, settlements, conflicts, tone, or similar latent content. Only dependent material is invalidated/regenerated.

Once play establishes information, ordinary regeneration cannot silently change it.

## 27. Progressive materialization

Distant content should move through:

`outline → latent → referenced → materialized → established`

If a player asks a scholar a concrete question about a previously shallow empire, World Author materializes the needed details, validates them against existing canon, and the communicated portion becomes established.

## 28. Campaign-generation acceptance target

A successful generator produces a broad coherent world without excessive unused detail, a deeply playable starting region/settlement, coherent NPC social relationships, several opportunities, at least one fixed-truth mystery, distinct AI companions, actionable factions, mechanically valid generated content, and latent distant content that remains revisable until encountered.
