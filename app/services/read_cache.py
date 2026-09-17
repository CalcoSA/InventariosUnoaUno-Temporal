from collections import OrderedDict
from concurrent.futures import Future
from copy import deepcopy
from threading import Lock
from time import monotonic


class ReadCache:
    """TTL acotado en RAM; comparte una carga por clave entre threads del proceso."""

    def __init__(self, ttl, max_entries, clock=monotonic):
        self.ttl, self.max_entries, self.clock = ttl, max_entries, clock
        self._entries = OrderedDict()
        self._pending = {}
        self._lock = Lock()

    def get(self, key, loader):
        with self._lock:
            now = self.clock()
            for expired in [k for k, (until, _) in self._entries.items() if until <= now]:
                del self._entries[expired]
            if key in self._entries:
                _, value = self._entries[key]
                self._entries.move_to_end(key)
                future, owner = None, False
            else:
                future = self._pending.get(key)
                owner = future is None
                if owner:
                    future = self._pending[key] = Future()
        if future is None:
            return deepcopy(value)
        if owner:
            try:
                value = loader()
            except BaseException as error:
                # Despertar también a los demás solicitantes; nunca cachear fallos.
                with self._lock:
                    future.set_exception(error)
                    del self._pending[key]
                raise
            else:
                with self._lock:
                    self._entries[key] = (self.clock() + self.ttl, value)
                    while len(self._entries) > self.max_entries:
                        self._entries.popitem(last=False)
                    future.set_result(value)
                    del self._pending[key]
        # Cada respuesta es independiente: el consumidor no puede alterar la caché.
        return deepcopy(future.result())
