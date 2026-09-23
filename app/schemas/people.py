"""Validated inputs shared by Telegram and services."""
from app.schemas.directories import Field, parse, wire
from app.core.exceptions import ValidationError

LABELS = {"worker": "👷 Работники", "specialty": "🛠 Специальности", "crew": "👥 Бригады"}
PERMISSIONS = {"worker": "people", "specialty": "specialties", "crew": "crews"}
PAYMENTS = (("piecework", "Сдельная"), ("salary", "Оклад"), ("daily", "Дневная ставка"))
FIELDS = {
    "worker": (
        Field("full_name", "ФИО", required=True, length=255),
        Field("specialty_id", "Специальность", "reference", True, relation="specialty"),
        Field("payment_type", "Тип оплаты", "choice", True, choices=PAYMENTS),
        Field("base_rate", "Ставка, тенге", "money", True),
        Field("current_project_id", "Текущий объект (можно без объекта)", "reference", relation="project"),
    ),
    "specialty": (Field("name", "Название специальности", required=True, length=200),),
    "crew": (Field("name", "Название бригады", required=True, length=200),),
}


def fields(kind):
    if kind not in FIELDS:
        raise ValidationError("Неизвестный раздел людей")
    return FIELDS[kind]


def normalized_name(value):
    return " ".join(value.split()).casefold()


def validate(kind, values):
    definition = fields(kind)
    if set(values) - {field.name for field in definition}:
        raise ValidationError("Неизвестные поля")
    result = {field.name: parse(field, values.get(field.name)) for field in definition}
    for key in ("full_name", "name"):
        if key in result:
            result[key] = " ".join(result[key].split())
            if not result[key]:
                raise ValidationError("Название или ФИО не может быть пустым")
    return result
