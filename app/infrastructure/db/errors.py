class DatabaseUnavailableError(RuntimeError):
    """БД недоступна (временные сетевые/коннект-ошибки)."""
    pass