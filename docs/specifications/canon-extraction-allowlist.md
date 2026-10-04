# Canon Extraction Allowlist v0.2

## 1. Purpose

The post-narration Canon Extractor is the one place where model prose can become persistent
state. Left open, it is the most likely source of canon drift ("the narrator mentioned a
chapel, so now there is a chapel"). This allowlist bounds it.

> **The extractor may persist decoration, not structure. Anything with mechanics, history,
> secrets, relationships or topology must be prestructured before narration.**

## 2. May persist (as `latent` lightweight canon)

- Furnishings and small environmental features of the **current location** (a bench, a
  cracked window, barrels, lantern light), as `location.properties.features[]` entries.
- Transient conditions of the current location: weather detail, smells, noise, crowding.
- Appearance details of **entities already present and already existing**, as
  `entity.metadata.descriptor` additions (grey cloak, limp, scar) — never new identity facts.
- Background extras present in the scene, as background NPC seeds (name optional, occupation,
  one trait), importance `background`.
- Ambient price/availability flavour for goods already in the location's trade list.

All extractor output starts `latent`. It becomes `established` only when a later player
action references it (search the barrels, talk to the limping guard).

## 3. May not persist (rejected by validator, not by prompt)

- New named entities of importance above `background`.
- Items with any mechanical property; any item at all if an effect/mechanics field is present.
- Facts about entities **not present** in the scene.
- History, lore, origins, rumours, prophecy.
- Secrets, motives, intentions, emotions of NPCs.
- Relationships, reputations, faction membership.
- Location topology: new exits, passages, connections, rooms.
- Anything contradicting existing canon of any status.
- Anything restating a character Claim as fact (speech is handled by
  `communication-and-knowledge.md`).

The validator checks classification against this list structurally (entity type, importance,
presence in scene, field names). A rejected candidate is logged; nothing is stored.

## 4. Narrator discipline

The Narrator prompt is told that important objects, characters, exits, documents and clues it
has not been given do not exist, and that it must not introduce them. The extractor allowlist
is the enforcement layer behind that instruction; the eval suite measures "narrator invents
disallowed structure" as a contradiction rate.

## 5. Tests

- Fixture narration containing a disallowed item (a key on the table) yields a rejected
  candidate and no entity.
- Fixture narration containing allowed decoration yields `latent` properties; a subsequent
  player search references them and promotes to `established`.
- Extractor output referencing an absent entity is rejected.
