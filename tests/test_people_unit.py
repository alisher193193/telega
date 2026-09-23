import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from app.schemas.people import validate, normalized_name, fields
from app.core.exceptions import ValidationError, ConflictError, AccessDeniedError
from app.services import people
from app.bot.keyboards.people import PeopleCallback, keyboard
from app.bot.states.people import PeopleStates
from app.db.repositories.people import listing


def values(**kwargs):
    return dict(full_name="  Иван   Иванов  ", specialty_id=uuid.uuid4(),
                payment_type="piecework", base_rate="123.45", current_project_id=None, **kwargs)


@pytest.mark.parametrize("name", ["", "  ", "\t\n", "x" * 256])
def test_invalid_name(name):
    data = values()
    data["full_name"] = name
    with pytest.raises(ValidationError):
        validate("worker", data)


def test_normalized_names_and_decimal():
    parsed = validate("worker", values())
    assert parsed["full_name"] == "Иван Иванов"
    assert parsed["base_rate"] == Decimal("123.45")
    assert normalized_name("  МАЛЯР \t штукатур ") == normalized_name("маляр штукатур")
    assert validate("specialty", {"name": "  Электро  монтажник "})["name"] == "Электро монтажник"


@pytest.mark.parametrize("rate", ["NaN", "Infinity", "-Infinity", "-0.01", "0.001", "10000000000000000", "1e999999999", 1.2, True])
def test_invalid_rates(rate):
    data = values()
    data["base_rate"] = rate
    with pytest.raises(ValidationError):
        validate("worker", data)


@pytest.mark.parametrize("rate", ["0", "9999999999999999.99", "123,45"])
def test_money_boundaries(rate):
    data = values()
    data["base_rate"] = rate
    assert validate("worker", data)["base_rate"].is_finite()


@pytest.mark.parametrize("action", ["category", "savestatus", "savemember", "pick", "leave", "page", "save", "correct"])
def test_real_callback_pack(action):
    packed = PeopleCallback(action=action, value=uuid.uuid4().hex, nonce="12345678").pack()
    assert len(packed.encode()) < 64
    markup = keyboard([("Выбрать", action, uuid.uuid4().hex)], "12345678")
    assert all(len(b.callback_data.encode()) < 64 for row in markup.inline_keyboard for b in row)


@pytest.mark.parametrize("status,archived", [("terminated", False), ("on_leave", False), ("working", True)])
def test_cannot_join_inactive_worker(status, archived):
    with pytest.raises(ValidationError):
        people.ensure_joinable(SimpleNamespace(status=status, is_archived=archived),
                               SimpleNamespace(id=uuid.uuid4(), status="active"), None)


def test_no_two_active_crews():
    worker = SimpleNamespace(status="working", is_archived=False)
    crew = SimpleNamespace(id=uuid.uuid4(), status="active")
    people.ensure_joinable(worker, crew, SimpleNamespace(crew_id=crew.id))
    with pytest.raises(ConflictError):
        people.ensure_joinable(worker, crew, SimpleNamespace(crew_id=uuid.uuid4()))
    crew.status = "archived"
    with pytest.raises(ValidationError):
        people.ensure_joinable(worker, crew, None)


def test_filters_precede_limit():
    from sqlalchemy.dialects import postgresql
    sql = str(listing("worker", query="100%_", project_id=uuid.uuid4()).limit(9).compile(dialect=postgresql.dialect()))
    assert sql.index("WHERE") < sql.index("ORDER BY") < sql.index("LIMIT")
    assert "current_project_id" in sql and "ILIKE" in sql


@pytest.mark.asyncio
async def test_explicit_permissions_no_admin_bypass(monkeypatch):
    require = AsyncMock()
    monkeypatch.setattr(people, "require_permission", require)
    for kind, prefix in (("worker", "people"), ("specialty", "specialties"), ("crew", "crews")):
        await people.require(None, kind, None, "manage")
        assert require.call_args.args[-1] == prefix + ".manage"
    require.side_effect = AccessDeniedError("no")
    assert await people.capabilities(None, None) == set()


@pytest.mark.asyncio
async def test_idempotency_receipt_replayed_or_rejected(monkeypatch):
    row = SimpleNamespace(payload_hash="same", kind="worker", entity_id=uuid.uuid4())
    session = SimpleNamespace(get=AsyncMock(return_value=row))
    monkeypatch.setattr(people, "lock_key", AsyncMock())
    found = SimpleNamespace(id=row.entity_id)
    monkeypatch.setattr(people.repo, "get", AsyncMock(return_value=found))
    assert await people._receipt(session, uuid.uuid4(), "same") is found
    with pytest.raises(ConflictError):
        await people._receipt(session, uuid.uuid4(), "different")


@pytest.mark.asyncio
async def test_choice_rejects_archived(monkeypatch):
    monkeypatch.setattr(people, "require", AsyncMock())
    monkeypatch.setattr(people.repo, "get", AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4(), is_active=False)))
    with pytest.raises(ValidationError):
        await people.choice(None, "specialty", uuid.uuid4(), user_id=None, purpose="form")


@pytest.mark.asyncio
async def test_close_membership_retains_row_and_dates():
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    member = SimpleNamespace(id=uuid.uuid4(), worker_id=uuid.uuid4(), crew_id=uuid.uuid4(),
                             joined_on=now, joined_at=now.date(), left_at=None, left_on=None)
    session = SimpleNamespace(add=lambda row: None, flush=AsyncMock())
    await people._close_member(session, member, None, now)
    assert member.joined_on == now and member.left_on == now and member.left_at is not None


@pytest.mark.asyncio
async def test_fsm_back_cancel_and_escaped_preview(monkeypatch):
    from app.bot.handlers import people as handler
    storage = MemoryStorage()
    state = FSMContext(storage, StorageKey(bot_id=1, chat_id=1, user_id=1))
    await state.set_state(PeopleStates.confirming)
    await state.update_data(kind="worker", purpose="form", index=5, draft={}, editing=False)
    monkeypatch.setattr(handler, "form", AsyncMock())
    event = SimpleNamespace(answer=AsyncMock())
    await handler.back(event, state, SimpleNamespace(id=uuid.uuid4()))
    assert (await state.get_data())["index"] == 4
    await handler.cancel(event, state)
    assert await state.get_state() is None and await state.get_data() == {}
    text = handler.summary("worker", {"full_name": "<b>A&B</b>"}, {})
    assert "&lt;b&gt;A&amp;B&lt;/b&gt;" in text


@pytest.mark.asyncio
async def test_stale_callback_cannot_save():
    from app.bot.handlers import people as handler
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=2, user_id=2))
    await state.update_data(nonce="new")
    with pytest.raises(ValidationError, match="устарела"):
        await handler.action(SimpleNamespace(), PeopleCallback(action="save", nonce="old"), state, SimpleNamespace())


def test_bootstrap_has_all_six_permissions():
    from app.scripts.bootstrap_access import PERMISSIONS
    assert {f"{scope}.{action}" for scope in ("people", "specialties", "crews") for action in ("view", "manage")} <= PERMISSIONS.keys()


@pytest.mark.asyncio
async def test_navigation_dispatcher_never_consumes_controls_as_fields(monkeypatch):
    import copy
    from datetime import datetime, timezone
    from aiogram import Bot, Dispatcher, Router
    from aiogram.client.session.base import BaseSession
    from aiogram.types import Message, Update, Chat, User
    from app.bot.handlers import navigation, people as handler

    class Transport(BaseSession):
        async def close(self): pass
        async def make_request(self, bot, method, timeout=None):
            return Message(message_id=99, date=datetime.now(timezone.utc), chat=Chat(id=1, type="private"),
                           text=getattr(method, "text", ""))
        async def stream_content(self, *args, **kwargs):
            if False: yield b""

    monkeypatch.setattr(handler, "caps", AsyncMock(return_value={"worker.view"}))
    monkeypatch.setattr(handler, "form", AsyncMock())
    dispatcher = Dispatcher()
    dispatcher.include_router(copy.deepcopy(navigation.router))
    trap = AsyncMock()
    fallback = Router()
    async def field(message):
        await trap(message)
    fallback.message.register(field, PeopleStates.editing)
    dispatcher.include_router(fallback)
    bot = Bot("123456:unit-token", session=Transport())
    state = dispatcher.fsm.get_context(bot=bot, chat_id=1, user_id=1)
    for index, text in enumerate(("/menu", "🏠 Главное меню", "❌ Отменить", "◀️ Назад", "👥 Люди")):
        await state.set_state(PeopleStates.editing)
        await state.update_data(kind="worker", purpose="form", index=1, draft={})
        message = Message(message_id=index+1, date=datetime.now(timezone.utc), chat=Chat(id=1, type="private"),
                          from_user=User(id=1, is_bot=False, first_name="test"), text=text)
        await dispatcher.feed_update(bot, Update(update_id=index, message=message),
                                     system_user=SimpleNamespace(id=uuid.uuid4(), full_name="test"))
        if text in {"/menu", "🏠 Главное меню", "❌ Отменить"}:
            assert await state.get_state() is None and await state.get_data() == {}
    trap.assert_not_awaited()
    await dispatcher.storage.close()
    await bot.session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["worker", "specialty", "crew"])
async def test_form_preview_save_and_repeat(monkeypatch, kind):
    from app.bot.handlers import people as handler
    from contextlib import asynccontextmanager
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=3, user_id=3))
    await state.set_state(PeopleStates.editing)
    await state.update_data(kind=kind, purpose="form", index=0, draft={}, draft_labels={}, editing=False, key=str(uuid.uuid4()))
    event = SimpleNamespace(answer=AsyncMock())
    user = SimpleNamespace(id=uuid.uuid4())
    # Reference screens use service choices; they must not connect to PostgreSQL in unit tests.
    monkeypatch.setattr(handler, "picker", AsyncMock())
    @asynccontextmanager
    async def context():
        yield SimpleNamespace(begin=context)
    monkeypatch.setattr(handler, "session_factory", context)
    monkeypatch.setattr(people, "require", AsyncMock())
    monkeypatch.setattr(people, "save", AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())))
    async def card(*args, **kwargs):
        await state.set_state(PeopleStates.card)
        await state.update_data(nonce="different")
    monkeypatch.setattr(handler, "show_card", card)
    for field in fields(kind):
        value = uuid.uuid4() if field.relation else "piecework" if field.choices else "1.25" if field.kind == "money" else "<name>"
        await handler.accept(event, state, user, value, "Название" if field.relation else None)
    assert await state.get_state() == PeopleStates.confirming.state
    data = await state.get_data()
    button = PeopleCallback(action="save", nonce=data["nonce"])
    await handler.action(event, button, state, user)
    people.save.assert_awaited_once()
    with pytest.raises(ValidationError, match="устарела"):
        await handler.action(event, button, state, user)


@pytest.mark.parametrize("url", [None, "postgresql+asyncpg://x:x@postgres/work_accounting",
                               "postgresql+asyncpg://x:x@postgres/other_test"])
def test_migration_command_refuses_unapproved_target(monkeypatch, url):
    from app.scripts import migrate_people_test
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    if url:
        monkeypatch.setenv("TEST_DATABASE_URL", url)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:x@postgres/work_accounting")
    execute = AsyncMock()
    monkeypatch.setattr(migrate_people_test, "verify_database", execute)
    with pytest.raises(SystemExit):
        migrate_people_test.main()
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_menu_hides_ungranted_sections(monkeypatch):
    from app.bot.handlers import people as handler
    monkeypatch.setattr(handler, "caps", AsyncMock(return_value={"specialty.view"}))
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=7, user_id=7))
    event = SimpleNamespace(answer=AsyncMock())
    await handler.open_section(event, state, SimpleNamespace())
    markup = event.answer.call_args.kwargs["reply_markup"]
    callbacks = [PeopleCallback.unpack(b.callback_data) for row in markup.inline_keyboard for b in row]
    assert [cb.value for cb in callbacks if cb.action == "category"] == ["specialty"]
    assert not any(cb.action == "find" for cb in callbacks)


@pytest.mark.asyncio
async def test_crew_card_displays_current_and_historical_members(monkeypatch):
    from contextlib import asynccontextmanager
    from datetime import datetime, timezone
    from app.bot.handlers import people as handler
    now = datetime.now(timezone.utc)
    crew_id = uuid.uuid4()
    @asynccontextmanager
    async def session():
        yield None
    monkeypatch.setattr(handler, "session_factory", session)
    monkeypatch.setattr(people, "detail", AsyncMock(return_value={
        "id": str(crew_id), "name": "<Бригада>", "status": "active", "archived": False,
        "created_at": now.isoformat(), "version": "version",
    }))
    monkeypatch.setattr(people, "capabilities", AsyncMock(return_value={"crew.view"}))
    current = SimpleNamespace(joined_on=now, joined_at=now.date(), left_on=None, left_at=None)
    ended = SimpleNamespace(joined_on=now, joined_at=now.date(), left_on=now, left_at=now.date())
    monkeypatch.setattr(people, "members", AsyncMock(side_effect=[
        ([(current, "<Текущий>")], False), ([(ended, "<Бывший>")], False)]))
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=8, user_id=8))
    await state.update_data(kind="crew")
    event = SimpleNamespace(answer=AsyncMock())
    await handler.show_card(event, state, SimpleNamespace(id=uuid.uuid4()), crew_id)
    text = event.answer.call_args.args[0]
    assert "Действующие участники" in text and "Завершённые участия" in text
    assert "&lt;Текущий&gt;" in text and "&lt;Бывший&gt;" in text
    assert len(text) < 4096
    markup = event.answer.call_args.kwargs["reply_markup"]
    assert not any(PeopleCallback.unpack(b.callback_data).action in {"join", "edit", "status"}
                   for row in markup.inline_keyboard for b in row)
