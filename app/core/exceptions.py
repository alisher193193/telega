class AppError(Exception):
    """Базовое исключение проекта."""


class AccessDeniedError(AppError):
    """Пользователь не имеет необходимых прав."""


class ValidationError(AppError):
    """Ошибка валидации входных данных."""


class NotFoundError(AppError):
    """Запрашиваемая сущность не найдена."""


class ConflictError(AppError):
    """Операция конфликтует с текущим состоянием сущности."""
