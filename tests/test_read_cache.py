from concurrent.futures import Future, ThreadPoolExecutor
from threading import Barrier, Event, Lock
from unittest.mock import Mock

import pytest

from app.services.read_cache import ReadCache


def test_ttl_copies_and_bounded_lru():
    clock = Mock(return_value=0)
    cache = ReadCache(ttl=45, max_entries=2, clock=clock)
    loader = Mock(return_value=[{'item': '001'}])
    cache.get('a', loader)[0]['item'] = 'changed'
    clock.return_value = 44.9
    assert cache.get('a', loader) == [{'item': '001'}]
    assert loader.call_count == 1
    clock.return_value = 45
    cache.get('a', loader)
    assert loader.call_count == 2
    cache.get('b', loader)
    cache.get('a', loader)  # a es la más usada: expulsar b.
    cache.get('c', loader)
    assert list(cache._entries) == ['a', 'c']
    assert not cache._pending
    clock.return_value = 90
    cache.get('d', loader)
    assert list(cache._entries) == ['d']


@pytest.mark.parametrize('fails', [False, True])
def test_twenty_threads_share_one_load_and_failure(monkeypatch, fails):
    waiting, release = Event(), Event()
    mutex = Lock()
    waiters = 0

    class ObservedFuture(Future):
        def result(self, *args, **kwargs):
            nonlocal waiters
            with mutex:
                waiters += 1
                if waiters == 19:
                    waiting.set()
            return super().result(*args, **kwargs)

    monkeypatch.setattr('app.services.read_cache.Future', ObservedFuture)
    cache = ReadCache(ttl=180, max_entries=64)

    def load():
        assert release.wait(10)
        if fails:
            raise RuntimeError('backend unavailable')
        return ['product']

    loader = Mock(side_effect=load)
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = [pool.submit(cache.get, 'pdv', loader) for _ in range(20)]
        try:
            assert waiting.wait(10), 'Los 19 solicitantes deben esperar la misma carga'
            assert loader.call_count == 1
        finally:
            release.set()
        for future in futures:
            if fails:
                with pytest.raises(RuntimeError, match='backend unavailable'):
                    future.result(timeout=10)
            else:
                assert future.result(timeout=10) == ['product']
    assert loader.call_count == 1
    assert not cache._pending
    if fails:
        loader.side_effect = lambda: ['recovered']
        assert cache.get('pdv', loader) == ['recovered']
        assert loader.call_count == 2


def test_different_keys_load_concurrently():
    cache = ReadCache(ttl=180, max_entries=64)
    rendezvous = Barrier(2)

    def load(key):
        rendezvous.wait(timeout=10)
        return key

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(cache.get, 'a', lambda: load('a'))
        b = pool.submit(cache.get, 'b', lambda: load('b'))
        assert a.result(timeout=10) == 'a'
        assert b.result(timeout=10) == 'b'
