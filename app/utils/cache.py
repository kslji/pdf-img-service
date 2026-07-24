import hashlib
import time
from collections import OrderedDict
from typing import Any, Optional

class LRUCache:
    """Simple LRU cache with TTL for page images."""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()

    def _hash_key(self, pdf_bytes: bytes, page: int, dpi: int) -> str:
        """Create a cache key from PDF bytes hash, page number, and DPI."""
        pdf_hash = hashlib.md5(pdf_bytes).hexdigest()
        return f"{pdf_hash}_p{page}_dpi{dpi}"

    def get(self, pdf_bytes: bytes, page: int, dpi: int) -> Optional[bytes]:
        """Get cached value if it exists and hasn't expired."""
        key = self._hash_key(pdf_bytes, page, dpi)
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl_seconds:
                # Move to end (most recently used)
                self.cache.move_to_end(key)
                return value
            else:
                # Expired
                del self.cache[key]
        return None

    def set(self, pdf_bytes: bytes, page: int, dpi: int, value: bytes) -> None:
        """Store a value in cache."""
        key = self._hash_key(pdf_bytes, page, dpi)
        if key in self.cache:
            del self.cache[key]

        # Remove oldest if cache is full
        if len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)

        self.cache[key] = (value, time.time())

    def clear(self) -> None:
        """Clear the entire cache."""
        self.cache.clear()

# Global cache instance
_page_image_cache = LRUCache(max_size=100, ttl_seconds=300)

def get_cached_page_image(pdf_bytes: bytes, page: int, dpi: int) -> Optional[bytes]:
    """Get a cached page image."""
    return _page_image_cache.get(pdf_bytes, page, dpi)

def cache_page_image(pdf_bytes: bytes, page: int, dpi: int, image_bytes: bytes) -> None:
    """Cache a rendered page image."""
    _page_image_cache.set(pdf_bytes, page, dpi, image_bytes)

def clear_page_cache() -> None:
    """Clear all cached page images."""
    _page_image_cache.clear()
