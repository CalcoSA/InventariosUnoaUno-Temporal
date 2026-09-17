from contextlib import contextmanager
from pathlib import Path
from filelock import FileLock, Timeout
from app.errors import FunctionalError


class InventoryLock:
    def __init__(self, path):
        self.path = path

    @contextmanager
    def acquire(self, timeout=30):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        try:
            with FileLock(self.path, timeout=timeout):
                yield
        except Timeout as error:
            raise FunctionalError(f'No se pudo obtener el bloqueo de inventario en {timeout} segundos. Intente nuevamente.') from error
