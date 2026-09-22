from decimal import Decimal, InvalidOperation, localcontext, ROUND_HALF_EVEN
from app.core.exceptions import ValidationError


def numeric(value: Decimal, scale: int, label: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValidationError(f"{label}: требуется конечное десятичное число")
    bound = Decimal(10) ** (18 - scale)
    if value.copy_abs() >= bound:
        raise ValidationError(f"{label}: превышен диапазон NUMERIC(18,{scale})")
    try:
        rounded = value.quantize(Decimal(1).scaleb(-scale))
    except InvalidOperation:
        raise ValidationError(f"{label}: недопустимая точность") from None
    if rounded != value:
        raise ValidationError(f"{label}: допускается не более {scale} знаков после запятой")
    return rounded


def volume(value: Decimal) -> Decimal:
    return numeric(value, 3, "Объём")


def money(value: Decimal) -> Decimal:
    return numeric(value, 2, "Сумма")


def line_amount(quantity: Decimal, unit_price: Decimal) -> Decimal:
    quantity = volume(quantity)
    unit_price = money(unit_price)
    # The product of NUMERIC(18,3) and NUMERIC(18,2) may exceed the default context.
    with localcontext() as context:
        context.prec = 40
        result = (quantity * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        return money(result)
