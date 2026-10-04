"""Deterministic rules engine (docs/architecture/02-rules-engine.md).

Pure modules: no database, no model provider. The engine defines what mechanics are *allowed to
do*; rulesets (declarative packages under `backend/rulesets/`) define what they *mean*.
"""
