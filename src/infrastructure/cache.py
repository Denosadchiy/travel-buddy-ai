"""
Simple in-memory cache abstraction for LLM responses.
Designed to be easily replaceable with Redis or other backends.
"""
from typing import Optional, Any
from datetime import datetime, timedelta
import hashlib
import json


class CacheEntry:
    """Cache entry with value and expiration."""

    def __init__(self, value: Any, ttl_seconds: int = 3600):
        self.value = value
        self.expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return datetime.utcnow() > self.expires_at


class ChatCache:
    """
    Abstract base for chat response caching.
    Designed to be swappable (in-memory, Redis, etc.).
    """

    def get(self, key: str) -> Optional[Any]:
        """Get cached value by key."""
        raise NotImplementedError

    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        """Set cached value with TTL."""
        raise NotImplementedError

    def clear(self) -> None:
        """Clear all cached values."""
        raise NotImplementedError

    @staticmethod
    def normalize_message(message: str) -> str:
        """Normalize message for cache key (lowercase, strip whitespace)."""
        return message.lower().strip()

    @staticmethod
    def generate_cache_key(trip_id: str, message: str) -> str:
        """Generate cache key from trip_id and normalized message."""
        normalized = ChatCache.normalize_message(message)
        # Use hash to keep key length manageable
        message_hash = hashlib.md5(normalized.encode()).hexdigest()
        return f"chat:{trip_id}:{message_hash}"


class InMemoryChatCache(ChatCache):
    """
    Simple in-memory cache implementation.
    Good for development and single-instance deployments.
    Replace with Redis for production multi-instance setups.
    """

    def __init__(self):
        self._cache: dict[str, CacheEntry] = {}

    def get(self, key: str) -> Optional[Any]:
        """Get cached value if exists and not expired."""
        entry = self._cache.get(key)
        if entry is None:
            return None

        if entry.is_expired():
            del self._cache[key]
            return None

        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        """Set cached value with TTL."""
        self._cache[key] = CacheEntry(value, ttl_seconds)

    def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()

    def cleanup_expired(self) -> int:
        """Remove expired entries. Returns number of entries removed."""
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired()
        ]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)


# Global cache instance (singleton for simplicity)
# In production, inject this as a dependency
_chat_cache = InMemoryChatCache()


def get_chat_cache() -> ChatCache:
    """Get the global chat cache instance."""
    return _chat_cache
