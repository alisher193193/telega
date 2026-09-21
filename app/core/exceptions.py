class AppError(Exception):
    """Базовое исключение проекта."""


class AccessDeniedError(AppError):
    """Пользователь не имеет необходимых прав."""


class ValidationError(AppError):
    """Ошибка валидации входных данных."""
