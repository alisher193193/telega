import hashlib
import uuid
from sqlalchemy import select, func
from app.core.exceptions import ValidationError


async def lock_key(session, namespace: str, key: uuid.UUID) -> None:
    if not isinstance(key, uuid.UUID):
        raise ValidationError("Необходим UUID ключ идемпотентности")
    digest = hashlib.sha256(f"{namespace}:{key}".encode()).digest()[:8]
    await session.execute(select(func.pg_advisory_xact_lock(int.from_bytes(digest, "big", signed=True))))
