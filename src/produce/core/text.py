"""Мелкие помощники для текстов сообщений."""


def plural(n: int, one: str, few: str, many: str) -> str:
    """Форма русского существительного для числа: 1 поиск, 2 поиска, 5 поисков."""
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many
