"""HTTP API. Route handlers are thin: they validate, call services, and shape responses.

Normal endpoints are perspective-safe by construction; omniscient endpoints live only under
`/api/v1/debug` and require DEBUG_MODE (docs/specifications/api-contracts.md §18).
"""
