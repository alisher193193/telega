"""Shared directory form definitions and server-side scalar validation."""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from app.core.exceptions import ValidationError
from app.core.numbers import money


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str = "text"
    required: bool = False
    length: int = 2000
    relation: str | None = None
    choices: tuple[tuple[str, str], ...] = ()


PROJECT_STATUSES = (("draft", "Черновик"), ("active", "Активен"),
                    ("paused", "Приостановлен"), ("completed", "Завершён"))
CONTRACT_STATUSES = (("draft", "Черновик"), ("active", "Активен"), ("closed", "Закрыт"))
BOOL = (("true", "Да"), ("false", "Нет"))
LABELS = {"project": "Объекты", "contract": "Договоры", "section": "Разделы",
          "work_type": "Виды работ", "unit": "Единицы измерения", "rate": "Расценки"}
FIELDS = {
    "project": (
        Field("name", "Название", required=True, length=255),
        Field("code", "Код", required=True, length=100),
        Field("address", "Адрес", length=500), Field("customer", "Заказчик", length=255),
        Field("start_date", "Дата начала", "date"), Field("planned_end_date", "Плановая дата окончания", "date"),
        Field("contract_amount", "Договорная сумма, ₸", "money"),
        Field("status", "Статус", "choice", True, choices=PROJECT_STATUSES), Field("comment", "Комментарий"),
    ),
    "contract": (
        Field("project_id", "Объект", "reference", True, relation="project"),
        Field("number", "Номер", required=True, length=100), Field("name", "Название", length=255),
        Field("contract_date", "Дата договора", "date"), Field("amount", "Сумма, ₸", "money"),
        Field("customer", "Заказчик", length=255), Field("start_date", "Дата начала", "date"),
        Field("end_date", "Дата окончания", "date"),
        Field("status", "Статус", "choice", True, choices=CONTRACT_STATUSES), Field("comment", "Комментарий"),
    ),
    "section": (
        Field("project_id", "Объект", "reference", True, relation="project"),
        Field("contract_id", "Договор (необязательно)", "reference", relation="contract"),
        Field("name", "Название", required=True, length=200), Field("code", "Код", required=True, length=100),
        Field("description", "Описание"),
    ),
    "unit": (Field("name", "Название", required=True, length=100),
             Field("code", "Обозначение (шт., м, м², м³, комплект, точка, день, час)", required=True, length=50)),
    "work_type": (
        Field("work_section_id", "Раздел", "reference", True, relation="section"),
        Field("name", "Название", required=True, length=200), Field("code", "Код", required=True, length=100),
        Field("unit_id", "Единица измерения", "reference", True, relation="unit"), Field("description", "Описание"),
    ),
    "rate": (
        Field("project_id", "Объект (пропустить — общая расценка)", "reference", relation="project"),
        Field("contract_id", "Договор (необязательно)", "reference", relation="contract"),
        Field("work_type_id", "Вид работы", "reference", True, relation="work_type"),
        Field("unit_id", "Единица измерения", "reference", True, relation="unit"),
        Field("worker_rate", "Цена рабочему, ₸", "money", True),
        Field("customer_rate", "Цена заказчику, ₸", "money", True),
        Field("valid_from", "Действует с", "date", True), Field("valid_to", "Действует по (включительно)", "date"),
        Field("is_active", "Активна", "bool", True, choices=BOOL),
    ),
}


def fields(kind):
    if kind not in FIELDS:
        raise ValidationError("Неизвестный справочник")
    return FIELDS[kind]


def parse(field: Field, value):
    if value is None or (isinstance(value, str) and value.strip() in {"", "-"}):
        if field.required:
            raise ValidationError(f"{field.label}: обязательное поле")
        return None
    if field.kind == "money":
        if not isinstance(value, (str, Decimal)):
            raise ValidationError(f"{field.label}: введите десятичное число")
        try:
            result = money(Decimal(value.strip().replace(",", ".")) if isinstance(value, str) else value)
        except InvalidOperation:
            raise ValidationError(f"{field.label}: некорректное число") from None
        if result < 0:
            raise ValidationError(f"{field.label}: сумма не может быть отрицательной")
        return result
    if field.kind == "date":
        if type(value) is date:
            return value
        if isinstance(value, str):
            for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(value.strip(), fmt).date()
                except ValueError:
                    pass
        raise ValidationError(f"{field.label}: используйте ДД.ММ.ГГГГ")
    if field.kind == "reference":
        try:
            return value if isinstance(value, UUID) else UUID(str(value))
        except ValueError:
            raise ValidationError(f"{field.label}: выберите запись из списка") from None
    if field.kind == "bool":
        if type(value) is bool:
            return value
        if value in {"true", "false"}:
            return value == "true"
        raise ValidationError(f"{field.label}: выберите Да или Нет")
    if not isinstance(value, str):
        raise ValidationError(f"{field.label}: требуется текст")
    value = value.strip()
    if len(value) > field.length:
        raise ValidationError(f"{field.label}: максимум {field.length} символов")
    if field.kind == "choice" and value not in dict(field.choices):
        raise ValidationError(f"{field.label}: выберите допустимый статус")
    return value


def validate(kind, values):
    definition = fields(kind)
    if set(values) - {f.name for f in definition}:
        raise ValidationError("Переданы неизвестные поля")
    result = {f.name: parse(f, values.get(f.name)) for f in definition}
    for start, end in (("start_date", "planned_end_date"), ("start_date", "end_date"), ("valid_from", "valid_to")):
        if result.get(start) and result.get(end) and result[end] < result[start]:
            raise ValidationError("Дата окончания не может быть раньше даты начала")
    return result


def wire(value):
    if isinstance(value, (date, UUID, Decimal)):
        return str(value)
    return value
