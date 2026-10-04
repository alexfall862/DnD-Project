"""Services coordinate domain behaviour over repositories and the engine.

They own transaction boundaries. Nothing outside a service mutates projections, and no
service mutates a projection outside an `EventTransaction` (Invariant 4).
"""
