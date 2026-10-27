"""Ошибки ядра. Интерфейс печатает их текст человеку и выходит с кодом 1."""


class ProduceError(Exception):
    """Базовая ошибка: текст уже написан по-русски и годится для вывода."""


class FileFormatError(ProduceError):
    """Файл не читается: оборван, не тот формат или нет нужных полей."""


class RunError(ProduceError):
    """Ошибка запуска: неизвестный этап, нет папки, неверный сегмент."""


class KeyMissingError(ProduceError):
    """Ключа YouTube нет в `.env` и в окружении."""


class KeyRejectedError(ProduceError):
    """YouTube отклонил ключ."""


class QuotaExceededError(ProduceError):
    """Квота YouTube на сегодня закончилась (или её не хватает на сбор)."""


class NetworkError(ProduceError):
    """YouTube не ответил."""
