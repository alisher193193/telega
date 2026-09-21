# Stage 7: безопасный запуск тестов

Unit-тесты не требуют PostgreSQL и TEST_DATABASE_URL:

```bash
docker compose exec -T \
  -e DATABASE_URL=postgresql+asyncpg://unit:unit@invalid/unit_test \
  -e TEST_DATABASE_URL= \
  -e BOT_TOKEN=unit-placeholder \
  bot pytest -m 'not integration' -q -p no:cacheprovider
```

Fixtures не импортируют рабочий engine, не создают/удаляют БД и не меняют схему.
Интеграционные тесты помечаются по зависимости от db_session. После отбора тестов,
до их выполнения проверяются TEST_DATABASE_URL и DATABASE_URL. Дополнительно после
подключения выполняется SELECT current_database(), до любых записей.
URL обязан использовать postgresql+asyncpg, имя заканчивается на _test, имя
work_accounting и совпадение с рабочим адресом запрещены. URL с query-параметрами
также запрещён, чтобы не допустить переопределения адреса на уровне драйвера.

## Ручное создание тестовой базы (команды ещё не выполнялись)

Откройте интерактивный psql от существующего администратора PostgreSQL:

```bash
docker compose exec postgres sh -c 'exec psql -U "$POSTGRES_USER" -d postgres'
```

Внутри psql выполните:

```sql
CREATE ROLE work_accounting_test_runner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
\password work_accounting_test_runner
CREATE DATABASE work_accounting_test OWNER work_accounting_test_runner TEMPLATE template0;
\q
```

Пароль вводится в скрытом приглашении \password. Используйте отдельный тестовый
пароль. Если роль/база уже существуют, проверьте их вручную; не удаляйте их.
Не выдавайте тестовой роли права на таблицы рабочей базы.

Чтобы задать URL без пароля в истории команд, выполните на хосте (без shell tracing):

```bash
export TEST_DATABASE_URL="$(python3 -c 'from getpass import getpass; from urllib.parse import quote; print("postgresql+asyncpg://work_accounting_test_runner:" + quote(getpass("Пароль тестовой роли: "), safe="") + "@postgres:5432/work_accounting_test")')"
```

Переменная находится только в текущем shell. Не печатайте её. Docker Compose сам
не передаёт произвольные переменные в контейнер: впоследствии понадобится явное
`-e TEST_DATABASE_URL` (без значения в командной строке). Перезапуск рабочего бота
для этого не нужен. Добавлять тестовое подключение в исходники не требуется.

После CREATE DATABASE схема пустая. На текущем этапе остановитесь здесь:
применение миграций и интеграционный запуск требуют отдельного согласования.
Не запускайте тесты до подготовки схемы именно в тестовой БД. Новая миграция
`a84e2d71c903` подготовлена, но нигде не применялась в рамках этой работы.

Рабочий bot пока не перезапускать: новый код требует новых колонок. Существующие
контейнеры используют bind mount проекта; случайный перезапуск до согласованного
обновления схемы приведёт к несовместимости. Старую миграцию f3a9c7b1e442 не менять.
