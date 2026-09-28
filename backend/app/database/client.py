"""
backend/app/database/client.py

Supabase client singleton.

All repository modules import get_client() from here.
No module outside database/ should call create_client() directly.
"""

from __future__ import annotations

import os
from supabase import create_client, Client

_client: Client | None = None


def get_client() -> Client:
    """Return the shared Supabase client (lazy singleton)."""
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY env vars must be set. "
                "Get them from Supabase dashboard → Project Settings → API."
            )
        _client = create_client(url, key)
    return _client


def ping() -> bool:
    """Return True if Supabase connection is alive."""
    try:
        get_client().table("repos").select("id").limit(1).execute()
        return True
    except Exception:
        return False
