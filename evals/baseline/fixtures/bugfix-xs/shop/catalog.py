"""Catálogo: listagem paginada dos produtos."""
from __future__ import annotations

DEFAULT_PAGE_SIZE = 10


def page(items: list, number: int, size: int = DEFAULT_PAGE_SIZE) -> list:
    """A página `number` (a primeira é a 1) de `items`, com até `size` itens."""
    if number < 1:
        raise ValueError("a numeração das páginas começa em 1")
    if size < 1:
        raise ValueError("o tamanho da página precisa ser positivo")
    start = number * size
    return items[start:start + size]


def page_count(items: list, size: int = DEFAULT_PAGE_SIZE) -> int:
    """Quantas páginas `items` ocupa."""
    if size < 1:
        raise ValueError("o tamanho da página precisa ser positivo")
    return (len(items) + size - 1) // size
