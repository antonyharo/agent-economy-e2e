class EcommerceError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(EcommerceError):
    pass


class ConflictError(EcommerceError):
    pass


class ValidationError(EcommerceError):
    pass
