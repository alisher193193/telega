import datetime as dt
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from app.schemas.directories import FIELDS, fields, parse, validate
from app.core.exceptions import ValidationError, AccessDeniedError
from app.db.repositories import catalog as repo
from app.services import catalog
from app.bot.keyboards import directories as kb
from app.bot.handlers import directories as handlers, navigation
from app.bot.states.directories import DirectoryStates as States


def project_values(**changes):
    result = dict(name='Отель <Алма-Ата>', code='AA', address=None, customer=None,
                  start_date=None, planned_end_date=None, contract_amount='123.45', status='draft', comment=None)
    result.update(changes)
    return result


@pytest.mark.parametrize('value', ['NaN', 'sNaN', 'Infinity', '-Infinity', '-1', '1.001', '10000000000000000', '1e999999999'])
def test_directory_money_validation(value):
    with pytest.raises(ValidationError):
        validate('project', project_values(contract_amount=value))


def test_directory_float_rejected():
    with pytest.raises(ValidationError):
        validate('project', project_values(contract_amount=12.34))


def test_dates_and_decimal_are_typed():
    result = validate('project', project_values(start_date='22.09.2026', planned_end_date='2026-10-01'))
    assert result['start_date'] == dt.date(2026, 9, 22)
    assert result['planned_end_date'] == dt.date(2026, 10, 1)
    assert result['contract_amount'] == Decimal('123.45')


@pytest.mark.parametrize('changes', [dict(code=' '), dict(name='x' * 256), dict(status='deleted'),
    dict(start_date='2026-10-01', planned_end_date='2026-09-22'), dict(start_date='31.02.2026')])
def test_invalid_fields_rejected(changes):
    with pytest.raises(ValidationError):
        validate('project', project_values(**changes))


def test_unknown_fields_and_kind_rejected():
    with pytest.raises(ValidationError):
        validate('project', project_values(is_archived=True))
    with pytest.raises(ValidationError):
        fields('unknown')


@pytest.mark.parametrize('kind', FIELDS)
def test_query_filters_before_limit_and_escapes_wildcards(kind):
    statement = repo.listing_statement(kind, query='_%').limit(9).offset(8)
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert sql.index('WHERE') < sql.index('LIMIT')
    assert any('\\_\\%' in str(v) for v in statement.compile().params.values())


@pytest.mark.parametrize('kind', FIELDS)
def test_real_keyboard_callbacks_below_64_bytes(kind):
    nonce = uuid.uuid4().hex[:8]
    record_id = uuid.uuid4()
    markups = [kb.main_menu(), kb.listing([(record_id, '<name>')], nonce=nonce, page=12,
        more=True, archived=False), kb.card(nonce=nonce, archived=False, rate=kind == 'rate'),
        kb.confirm(nonce), kb.confirm(nonce, archive=True)]
    for field in fields(kind):
        markups.append(kb.field(field, nonce=nonce, has_value=True))
    for markup in markups:
        for row in markup.inline_keyboard:
            for button in row:
                assert len(button.callback_data.encode()) < 64
                assert kb.DirectoryCallback.unpack(button.callback_data).pack() == button.callback_data


async def test_change_accepts_either_permission(monkeypatch):
    check = AsyncMock(side_effect=[AccessDeniedError('no'), None])
    monkeypatch.setattr(catalog, 'require_permission', check)
    await catalog.require_change(object(), uuid.uuid4())
    assert [call.args[2] for call in check.call_args_list] == ['projects.manage', 'directories.manage']


async def test_no_change_permissions_denied(monkeypatch):
    monkeypatch.setattr(catalog, 'require_permission', AsyncMock(side_effect=AccessDeniedError('no')))
    with pytest.raises(AccessDeniedError):
        await catalog.require_change(object(), uuid.uuid4())


async def test_view_requires_projects_view(monkeypatch):
    check = AsyncMock(side_effect=AccessDeniedError('no'))
    monkeypatch.setattr(catalog, 'require_permission', check)
    with pytest.raises(AccessDeniedError):
        await catalog.list_page(object(), 'project', user_id=uuid.uuid4())
    assert check.call_args.args[2] == 'projects.view'


def test_card_escapes_html():
    text = handlers.summary('project', project_values(comment='<script>&hello'), {})
    assert '&lt;Алма-Ата&gt;' in text
    assert '&lt;script&gt;&amp;hello' in text
    assert '<script>' not in text


@pytest.fixture
async def state():
    storage = MemoryStorage()
    context = FSMContext(storage, StorageKey(bot_id=1, chat_id=1, user_id=1))
    yield context
    await storage.close()


async def test_back_preserves_draft_and_moves_one_field(state, monkeypatch):
    await state.set_state(States.editing)
    await state.update_data(kind='project', field_index=2, draft=project_values())
    show = AsyncMock()
    monkeypatch.setattr(handlers, 'show_field', show)
    await handlers.go_back(object(), state, SimpleNamespace(id=uuid.uuid4()))
    assert (await state.get_data())['field_index'] == 1
    assert (await state.get_data())['draft']['code'] == 'AA'
    show.assert_awaited_once()


async def test_confirm_has_no_save_until_preview(state, monkeypatch):
    await state.update_data(kind='project', field_index=len(fields('project')), draft=project_values(), labels={})
    event = SimpleNamespace(answer=AsyncMock())
    await handlers.show_field(event, state, SimpleNamespace(id=uuid.uuid4()))
    assert await state.get_state() == States.confirming.state
    markup = event.answer.call_args.kwargs['reply_markup']
    assert any(kb.DirectoryCallback.unpack(b.callback_data).action == 'save' for row in markup.inline_keyboard for b in row)


async def test_cancel_clears_state_and_data(state):
    await state.set_state(States.editing)
    await state.update_data(draft={'name': 'unsaved'})
    event = SimpleNamespace(answer=AsyncMock())
    await handlers.cancel(event, state)
    assert await state.get_state() is None
    assert await state.get_data() == {}


async def test_project_choice_does_not_add_unknown_contract_field(state, monkeypatch):
    await state.update_data(kind='contract', field_index=0, draft={})
    monkeypatch.setattr(handlers, 'show_field', AsyncMock())
    await handlers.accept_value(object(), state, object(), uuid.uuid4())
    assert 'contract_id' not in (await state.get_data())['draft']


async def test_stale_save_rejected(state):
    await state.set_state(States.confirming)
    await state.update_data(nonce='current')
    with pytest.raises(ValidationError, match='устарела'):
        await handlers.handle_action(object(), kb.DirectoryCallback(action='save', nonce='old'), state,
                                     SimpleNamespace(id=uuid.uuid4()))


async def test_search_uses_pagination_from_first_page(state, monkeypatch):
    await state.set_state(States.searching)
    await state.update_data(kind='project', page=8)
    show = AsyncMock()
    monkeypatch.setattr(handlers, 'show_list', show)
    await handlers.search_text(SimpleNamespace(text='Алма'), state, object())
    assert (await state.get_data())['query'] == 'Алма'
    assert show.call_args.kwargs == {}


async def test_menu_clears_fsm_without_saving(state, monkeypatch):
    await state.set_state(States.editing)
    await state.update_data(draft={'comment': 'keep'})
    start = AsyncMock()
    monkeypatch.setattr(navigation.start, 'start_handler', start)
    await navigation.home(object(), state, object())
    assert await state.get_data() == {}
    start.assert_awaited_once()


async def test_text_cancel_is_not_field_input(state):
    await state.set_state(States.editing)
    message = SimpleNamespace(text='Отменить', answer=AsyncMock())
    await navigation.control(message, state, object())
    assert await state.get_state() is None


async def test_rate_overlap_bounds():
    first = SimpleNamespace(valid_from=dt.date(2026, 1, 1), valid_to=dt.date(2026, 1, 31))
    assert not catalog._overlaps(first, {'valid_from': dt.date(2026, 2, 1), 'valid_to': None})
    assert catalog._overlaps(first, {'valid_from': dt.date(2026, 1, 31), 'valid_to': None})


async def test_new_rate_does_not_rewrite_old_prices(monkeypatch):
    pid, wid, uid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    values = dict(project_id=pid, contract_id=None, work_type_id=wid, unit_id=uid,
                  worker_rate=Decimal('150'), customer_rate=Decimal('300'), valid_from=dt.date(2026, 2, 1), valid_to=None, is_active=True)
    previous = SimpleNamespace(id=uuid.uuid4(), **dict(values, worker_rate=Decimal('100'), customer_rate=Decimal('200'), valid_from=dt.date(2026, 1, 1)))
    monkeypatch.setattr(repo, 'rate_family', AsyncMock(return_value=[previous]))
    monkeypatch.setattr(catalog.audit, 'record', AsyncMock())
    session = SimpleNamespace(add=MagicMock())
    new = await catalog._new_rate(session, values, previous, uuid.uuid4())
    assert previous.worker_rate == Decimal('100') and previous.customer_rate == Decimal('200')
    assert previous.valid_to == dt.date(2026, 1, 31)
    assert new.worker_rate == Decimal('150')


async def test_rate_same_start_rejected(monkeypatch):
    values = dict(project_id=None, contract_id=None, work_type_id=uuid.uuid4(), unit_id=uuid.uuid4(),
                  worker_rate=Decimal('1'), customer_rate=Decimal('2'), valid_from=dt.date(2026, 1, 1), valid_to=None, is_active=True)
    previous = SimpleNamespace(id=uuid.uuid4(), **values)
    monkeypatch.setattr(repo, 'rate_family', AsyncMock(return_value=[previous]))
    with pytest.raises(ValidationError):
        await catalog._new_rate(object(), values, previous, uuid.uuid4())


@pytest.mark.parametrize('kind', FIELDS)
async def test_each_form_reaches_preview_then_saves_once(kind, state, monkeypatch):
    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def begin(self): return self
    monkeypatch.setattr(handlers, 'session_factory', Session)
    monkeypatch.setattr(catalog, 'require_change', AsyncMock())
    monkeypatch.setattr(catalog, 'list_page', AsyncMock(return_value=([], False)))
    monkeypatch.setattr(handlers, 'render', AsyncMock())
    saved = []
    async def save(session, entity_kind, values, **kwargs):
        saved.append((validate(entity_kind, values), kwargs))
        return SimpleNamespace(id=uuid.uuid4())
    monkeypatch.setattr(catalog, 'save', save)
    async def card(event, state, user, entity_id):
        await state.set_state(States.card)
        await handlers.token(state)
    monkeypatch.setattr(handlers, 'show_card', card)
    await state.set_state(States.listing)
    await state.update_data(kind=kind, nonce='initial')
    callback = SimpleNamespace(answer=AsyncMock())
    user = SimpleNamespace(id=uuid.uuid4())
    await handlers.handle_action(callback, kb.DirectoryCallback(action='new', nonce='initial'), state, user)
    for field in fields(kind):
        value = ('draft' if field.name == 'status' else 'Text')
        if field.kind == 'reference': value = uuid.uuid4()
        if field.kind == 'money': value = '123.45'
        if field.kind == 'date': value = '22.09.2026'
        if field.kind == 'bool': value = True
        await handlers.accept_value(callback, state, user, value)
    assert await state.get_state() == States.confirming.state
    assert not saved
    data = await state.get_data()
    button = kb.DirectoryCallback(action='save', nonce=data['nonce'])
    await handlers.handle_action(callback, button, state, user)
    assert len(saved) == 1 and isinstance(saved[0][1]['idempotency_key'], uuid.UUID)
    with pytest.raises(ValidationError, match='устарела'):
        await handlers.handle_action(callback, button, state, user)
    assert len(saved) == 1


async def test_dispatcher_navigation_precedes_fsm_fields(monkeypatch):
    import copy
    from aiogram import Bot, Dispatcher, Router
    from aiogram.client.session.base import BaseSession
    from aiogram.types import Update, Message, Chat, User as TelegramUser
    from aiogram.fsm.storage.memory import SimpleEventIsolation

    class LocalSession(BaseSession):
        def __init__(self):
            super().__init__()
            self.sent = []
        async def close(self): pass
        async def make_request(self, bot, method, timeout=None):
            self.sent.append(method)
            return Message(message_id=999, date=dt.datetime.now(dt.timezone.utc),
                           chat=Chat(id=700, type='private'), text=getattr(method, 'text', ''))
        async def stream_content(self, *args, **kwargs):
            if False: yield b''
    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    monkeypatch.setattr(navigation, 'session_factory', Session)
    monkeypatch.setattr(navigation, 'require_permission', AsyncMock())
    monkeypatch.setattr(navigation.people, 'caps', AsyncMock(return_value={'worker.view'}))
    monkeypatch.setattr(handlers, 'session_factory', Session)
    monkeypatch.setattr(catalog, 'list_page', AsyncMock(return_value=([], False)))
    monkeypatch.setattr(catalog, 'reference_labels', AsyncMock(return_value={}))
    transport = LocalSession()
    bot = Bot('123456:unit-token', session=transport)
    dispatcher = Dispatcher(events_isolation=SimpleEventIsolation())
    dispatcher.include_router(copy.deepcopy(navigation.router))
    field_handler = AsyncMock()
    fallback = Router(name="test-fields")
    async def trap(message):
        await field_handler(message)
    fallback.message.register(trap, States.editing)
    dispatcher.include_router(fallback)
    system_user = SimpleNamespace(id=uuid.uuid4(), full_name='<name>')
    context = dispatcher.fsm.get_context(bot=bot, chat_id=700, user_id=701)
    try:
        for index, value in enumerate(['/menu', '🏗 Объекты', '👥 Люди', 'Отменить', 'Назад']):
            await context.set_state(States.editing)
            await context.update_data(kind='project', field_index=0, draft={}, nonce='test')
            message = Message(message_id=index + 1, date=dt.datetime.now(dt.timezone.utc), chat=Chat(id=700, type='private'),
                              from_user=TelegramUser(id=701, is_bot=False, first_name='test'), text=value)
            await dispatcher.feed_update(bot, Update(update_id=index, message=message), system_user=system_user)
        field_handler.assert_not_awaited()
        assert len(transport.sent) >= 5
    finally:
        await dispatcher.storage.close()
        await bot.session.close()
