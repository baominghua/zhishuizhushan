"""Smart Bamboo V2 API package.

V2 starts as a compatibility layer over the proven V1 repositories. Keeping the
HTTP contract isolated lets the storage implementation move to PostGIS without
forcing another frontend rewrite.
"""

from .router import router

__all__ = ["router"]
