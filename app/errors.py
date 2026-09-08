class FunctionalError(Exception):
    """Mensaje funcional que puede mostrarse al usuario."""


class ConfigurationError(FunctionalError):
    pass
