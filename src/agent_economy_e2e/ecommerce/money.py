from decimal import Decimal, ROUND_HALF_UP

TWOPLACES = Decimal("0.01")


def money(value: float | int | Decimal | str) -> float:
    quantized = Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    return float(quantized)
