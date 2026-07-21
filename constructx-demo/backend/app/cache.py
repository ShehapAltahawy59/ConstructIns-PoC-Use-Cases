"""Tiny in-memory result cache keyed by a per-module data version.

The AI evaluation is expensive, and several endpoints need the same result on
every dashboard refresh. We compute it once and reuse it until the underlying
data changes. Each write path calls `bump(module)` to invalidate the cache.
"""
from __future__ import annotations

from typing import Any, Callable

_versions: dict[str, int] = {"subcontractors": 0, "materials": 0}
_cache: dict[str, tuple[int, Any]] = {}


def bump(module: str) -> None:
    """Mark a module's data as changed (invalidates its cached results)."""
    _versions[module] = _versions.get(module, 0) + 1


def cached(key: str, module: str, compute: Callable[[], Any]) -> Any:
    """Return the cached value for `key` if the module's data hasn't changed,
    otherwise compute, store and return it."""
    version = _versions.get(module, 0)
    hit = _cache.get(key)
    if hit is not None and hit[0] == version:
        return hit[1]
    result = compute()
    _cache[key] = (version, result)
    return result
