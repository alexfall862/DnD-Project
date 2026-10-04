"""Persistence layer: engine/session factories and repositories.

Repositories here perform persistence and retrieval only; they contain no game rules
(docs/architecture/05-implementation-plan.md §8). From Milestone 03 onward this package is
split into ObjectiveWorldRepository / PerspectiveRepository / DebugRepository
(docs/specifications/database-schema.md §21) so that "which repository is in use" answers
"objective truth or one actor's perspective?".
"""
