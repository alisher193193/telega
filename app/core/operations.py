from contextvars import ContextVar
from functools import wraps
import uuid

request_id: ContextVar[uuid.UUID | None] = ContextVar("request_id", default=None)


def operation(function):
    @wraps(function)
    async def wrapped(*args, **kwargs):
        if request_id.get() is not None:
            return await function(*args, **kwargs)
        token = request_id.set(uuid.uuid4())
        try:
            return await function(*args, **kwargs)
        finally:
            request_id.reset(token)
    return wrapped
