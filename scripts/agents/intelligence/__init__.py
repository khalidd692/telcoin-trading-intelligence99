"""TEL99 agent intelligence layer (router, shared memory, controlled improvement).

Stdlib only, deterministic, and safe to run in CI. Nothing here calls a paid
service, submits an order, merges a branch or changes a permission.
"""

__all__ = ["memory", "router", "catalog", "improvement"]
