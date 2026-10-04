"""Data-access split (database-schema.md §21).

- `objective`: ObjectiveWorldRepository — omniscient reads/writes for engine services and debug.
- `perspective`: PerspectiveRepository — the ONLY data path for anything that builds an actor's
  view or a model context. Every query is filtered by `actor_id`; it never selects
  `facts.truth_status`, `facts.canon_status`, `claims.deliberate_false`, `claims.fidelity`,
  `claims.source_*` or `items.hidden_properties`. `tests/invariants/test_repository_boundary.py`
  enforces that by scanning the source.
"""
