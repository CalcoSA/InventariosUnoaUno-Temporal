from datetime import datetime, timezone
import pytest
from app.utils import date_key


@pytest.mark.parametrize('value,expected', [('08/09/2026', '2026-09-08'), ('08-09-2026', '2026-09-08'),
    ('2026-09-08', '2026-09-08'), ('8/9/2026', '2026-09-08'), ('otro', 'otro'), ('', '')])
def test_dates(value, expected):
    assert date_key(value) == expected


def test_timezone():
    assert date_key(datetime(2026, 9, 8, 2, tzinfo=timezone.utc)) == '2026-09-07'
