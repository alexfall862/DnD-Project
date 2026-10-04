# Core Adventure Rules v0.1

## 1. Purpose

Core Adventure is the first original ruleset used to prove the generic engine. It is intentionally conventional, compact, genre-flexible, and easy for both humans and models to reason about.

It is not intended to be the final game system.

## 2. Core check

Default resolution:

`1d20 + Attribute + Skill + modifiers` versus Difficulty.

Higher is better. Tasks with no meaningful uncertainty do not require checks.

### Difficulty scale

- 8 — routine under pressure
- 11 — easy
- 14 — moderate
- 17 — hard
- 20 — severe
- 23 — extraordinary
- 26 — extreme

### Margin

`margin = total - difficulty`

Suggested outcomes:

- ≤ -10: critical failure
- -9 to -1: failure
- 0 to +4: success
- +5 to +9: strong success
- +10+: exceptional success

Natural 1 may create a complication candidate; natural 20 may create a benefit candidate. Neither overrides impossible fiction.

## 3. Attributes

Five attributes, 1–10 scale, typical adult around 5:

- **Might** — strength, force, endurance, carrying capacity.
- **Agility** — coordination, reflexes, balance, precision.
- **Intellect** — reasoning, technical understanding, memory, analysis.
- **Presence** — social force, charisma, deception, leadership, performance.
- **Resolve** — willpower, focus, courage, mental endurance.

Interpretation: 1–2 poor, 3–4 below average, 5 average, 6–7 strong, 8–9 exceptional, 10 extraordinary.

## 4. Skills

Initial ranks:

- 0 untrained
- 1 familiar
- 2 trained
- 3 expert
- 4 master
- 5 legendary

Initial skills:

**Physical**: Athletics, Acrobatics, Stealth

**Awareness**: Awareness, Investigation

**Knowledge**: Lore, Technology, Medicine, Survival, Crafting

**Social**: Persuasion, Deception, Intimidation, Performance

**Combat (initially broad)**: Melee, Ranged

Genre modules may add Arcana, Piloting, Hacking, Occult, Firearms, Navigation, etc.

### Flexible attribute-skill pairing

Skills have default pairings, but the adjudicator may choose a different attribute when fiction warrants it. Examples: Might + Intimidation for a physical threat; Intellect + Persuasion for a careful logical argument.

## 5. Opposed checks

Both actors roll appropriate checks; higher total wins. Default tie behavior favors the defender.

## 6. Core resources

### Health

`Health max = 10 + (Might × 2)`

At Health > 0, actor is active unless another effect says otherwise. At Health ≤ 0, actor becomes incapacitated. Further severe damage can produce Injury, Dying, or Death depending on campaign lethality.

Suggested campaign lethality modes: heroic, standard, deadly, brutal.

### Stamina

`Stamina max = 5 + Might + Resolve`

Used for physical maneuvers, sprinting, certain defenses, and abilities. Short rest restores some Stamina.

### Resolve Points

`Resolve Points max = 3 + Resolve`

Used for special mental/supernatural/narrative abilities, fear resistance, or pushing through adversity. Genre modules may reinterpret.

## 7. Defense and armor

Base Defense:

`10 + Agility`

Initial armor model:

- light armor: +1 Defense
- medium armor: +2 Defense
- heavy armor: +3 Defense; Agility contribution capped at 5

Future rulesets may instead use damage reduction; the engine remains generic.

## 8. Initiative and action economy

Default initiative:

`1d20 + Agility`, descending.

Ties: higher Awareness skill, then engine random tie-breaker.

Normal turn:

- 1 Major Action
- 1 Movement
- 1 Reaction

Minor trivial interactions are free where reasonable.

## 9. Movement and positioning

Theater-of-the-mind distance bands:

- Engaged
- Close
- Near
- Far
- Distant

Normal Movement usually changes one distance step. Sprint may require Major Action or Stamina.

Cover:

- partial: +2 Defense against relevant attacks
- strong: +4 Defense
- total: normally cannot be targeted

High ground is typically +1 when clearly advantageous.

## 10. Attacks

### Melee

`1d20 + Might + relevant skill` vs Defense.

### Ranged

`1d20 + Agility + relevant skill` vs Defense, subject to range/cover.

### Example weapon damage

- knife: `1d4 + appropriate Might contribution`
- sword: `1d8 + Might contribution`
- great axe: `1d10 + Might contribution`
- bow: `1d8`
- pistol: `1d8`
- rifle: `1d10`

Exact attribute damage contribution is tunable during playtesting; the engine should not hardcode it globally.

## 11. Reactions

Initial reactions:

- **Defend** — spend Reaction for +2 Defense against one attack.
- **Protect** — adjacent ally attacked; spend Reaction to grant defense/intercept when fiction permits.
- **Opportunity Attack** — leaving Engaged range unsafely may trigger a reaction attack.

## 12. Conditions

Initial conditions:

- Bleeding
- Burning
- Blinded
- Frightened
- Stunned
- Prone
- Restrained
- Poisoned
- Exhausted
- Hidden

Examples:

**Burning:** end-of-turn `1d4` fire damage; an action can attempt to extinguish; water may remove automatically where appropriate.

**Bleeding:** after strenuous Major Action, lose 1 Health; Medicine can remove.

**Frightened:** -2 to actions directly confronting source; may require Resolve to approach.

**Hidden:** actor is not automatically targetable by observers who have not detected it. This directly exercises perspective-aware mechanics.

## 13. Rest and healing

Short Rest: 1 hour; restore half maximum Stamina.

Long Rest: 8 hours; restore all Stamina, all Resolve Points, and some Health. Campaign survival modules can alter recovery.

Medicine checks can stabilize dying characters, treat injuries, restore limited Health, and remove specific conditions. Genre modules can add stronger magical/technological healing.

## 14. Character creation

Default sequence:

1. Concept
2. Attributes
3. Background
4. Skill training
5. Traits
6. Equipment
7. Personal details

### Attributes

All attributes begin at 3; player receives 10 additional points; maximum starting attribute 8.

### Skills

8 skill points; maximum starting rank 3; cost 1 point per rank.

### Background

A background grants one trained skill, one narrative/mechanical trait, one contact or relationship, starting equipment, and one core-memory seed.

Initial examples: Soldier, Scholar, Outlaw, Merchant, Wanderer, Healer, Official, Craftsperson, Explorer.

### Traits

Choose 2 positive/complex traits. Examples: Night Vision, Veteran, Quick Reflexes, Well Connected, Iron Will, Keen Memory, Streetwise, Survivor.

### Complications

Optional hooks such as Debt, Enemy, Oath, Addiction, Wanted, Dependent, Curse, Reputation. They should create world/story consequences rather than being mere numeric penalties.

## 15. AI-assisted creation

A user can describe a concept in prose. The LLM proposes attributes/background/skills/traits/equipment consistent with the creation budget. The engine validates. The user may manually adjust.

AI companions additionally receive personality, values, fears, goals, quirks, tactical tendencies, relationship tendencies, and autonomy profile.

## 16. Starting equipment

Equipment comes from background package, setting, manual purchase, or AI recommendation. No classes are required.

## 17. Advancement

Core Adventure uses Advancement Points awarded for meaningful milestones/goals rather than individual kills.

Initial costs:

- skill rank: new rank × 2 AP
- attribute: new value × 3 AP
- trait/ability: variable

These numbers are explicitly tunable.

## 18. Abilities

Characters acquire special abilities independently of class. Examples: Power Strike, Field Medicine, Quick Draw, Arcane Sight, Commanding Presence, Hacker's Instinct, Psionic Push.

Example **Power Strike**: cost 2 Stamina; requires melee weapon; +1 damage die on successful attack.

Example **Field Medicine**: once per short rest; Medicine check; success restores `1d6 + Intellect` Health; strong success may remove Bleeding.

Example **Push Through**: cost 1 Resolve Point; trigger failed check; reroll and accept second result.

## 19. Genre modules

### Fantasy

Adds Arcana, Mana, spell abilities, magical items, fantasy creatures/backgrounds, and traditions such as arcane/divine/primal/occult.

Example Mana: `3 + Intellect + Resolve`.

### Sci-Fi

Adds Piloting/Hacking/Firearms, energy weapons, cybernetics, vehicles, oxygen, radiation, etc.

### Horror

Adds Stability, Trauma, fear mechanics, Occult, and stronger hidden-information pressure.

### Survival

Adds Hunger, Thirst, Fatigue, temperature exposure, detailed ammunition, encumbrance, and travel resources.

All are modular/toggleable.

## 20. Social interaction

Routine reasonable requests often need no roll. High-stakes persuasion/deception/intimidation may.

Difficulty composition can consider trust, danger, goal alignment, payment, status, evidence, etc. Success changes willingness/behavior within plausibility; it is not mind control.

Deception is generally opposed by Awareness, Investigation, or relevant knowledge depending on context. Successful insight typically grants evidence/tells, not omniscient truth.

Intimidation can increase fear/willingness but may worsen future trust/resentment.

## 21. Perception and investigation

Plainly visible facts are simply communicated. Rolls are reserved for concealed, subtle, distant, difficult, or time-pressured details.

Investigation generally discovers preexisting clues. A high roll should not retroactively create arbitrary evidence to force the plot.

Knowledge checks determine whether a character already knows or can infer relevant information; they do not bypass secrets that do not logically follow.

## 22. Environmental improvisation

Freeform play is encouraged. Example: “I shove the bookshelf over to block the doorway.” The adjudicator evaluates shelf size, Might/Athletics, doorway dimensions, and time pressure, then proposes a legal check/effect composition such as moving the shelf and applying a blocked condition.

## 23. Travel

Default travel:

route → travel time → world clock advancement → configured resource consumption → scheduled/world-event processing → encounter opportunities.

Detailed survival modules add more.

## 24. Encounters

Encounter types include social, hazard, combat, discovery, travel complication, and mystery. World Author/Simulator provides purpose, participants, environment, stakes, and escalation; the rules engine ensures mechanically valid actors/content.

Threat labels such as Minor, Standard, Elite, Boss, Overwhelming are generation guidance, not enforced balance guarantees.

## 25. Example creature — Mire Hound

- Might 6
- Agility 7
- Intellect 2
- Presence 2
- Resolve 5
- Health 22
- Awareness 2, Stealth 2
- Trait: Keen Smell
- Bite: `1d20 + Agility + Melee`, `1d6+2` damage
- Dragging Bite: on strong success, target becomes Prone

## 26. Example companion — Elara Venn

- Might 5
- Agility 7
- Intellect 6
- Presence 4
- Resolve 6
- Survival 3, Awareness 2, Ranged 2, Stealth 2, Investigation 1, Medicine 1
- Traits: Keen Observer, Frontier Veteran
- Goals: find missing brother; protect vulnerable settlements; avoid dependence
- Behavior dimensions defined in Frostbridge fixture

## 27. Initial unique-item patterns

Generated unique items should exercise passive modifiers, resource costs, perspective-aware information reveal, activation counts, conditions, and persistent instance history.

Example concept: a lantern that detects supernatural disturbances at a Resolve cost and can inflict Shaken after repeated use.

## 28. Hidden-property example

`Veyra's Chipped Dagger` looks like an ordinary dagger but objectively deals bonus damage against spirits. The bonus remains absent from character context until discovered, while the rules engine can apply it to an actual spirit attack.

## 29. Core Adventure acceptance

The ruleset must resolve: simple/opposed checks, attack/damage, conditions, healing, resource spending, movement, cover, reaction, initiative, rest, social/knowledge checks, hidden item properties, generated abilities/items, and improvised rulings.
