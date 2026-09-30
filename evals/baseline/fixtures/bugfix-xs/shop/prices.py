"""Preços em centavos e a forma de mostrá-los."""
from __future__ import annotations


def format_brl(cents: int) -> str:
    """`123456` -> `R$ 1.234,56`."""
    sign = "-" if cents < 0 else ""
    reais, centavos = divmod(abs(cents), 100)
    return f"{sign}R$ {reais:,}".replace(",", ".") + f",{centavos:02d}"


def apply_discount(cents: int, percent: int) -> int:
    """O preço com `percent`% de desconto, arredondado para o centavo mais próximo."""
    if not 0 <= percent <= 100:
        raise ValueError("o desconto vai de 0 a 100%")
    return cents - (cents * percent + 50) // 100
