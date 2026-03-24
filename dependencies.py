# dependencies.py
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, HTTPException

import db


def _validate_session(session_token: str | None) -> dict | None:
    """Return user dict if session is valid and not expired, None otherwise.
    Slides the 7-day expiry window on each valid access."""
    if not session_token:
        return None
    session = db.get_session(session_token)
    if not session:
        return None
    new_expiry = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    db.update_session_expiry(session_token, new_expiry)
    return db.get_user_by_id(session["user_id"])


async def require_instructor_api(
    session_token: str | None = Cookie(default=None),
) -> dict:
    """FastAPI dependency for protected API routes. Raises HTTP 401 if not authenticated."""
    user = _validate_session(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
