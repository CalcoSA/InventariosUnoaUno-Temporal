import math
import re
import unicodedata
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pyuca import Collator

_collator = Collator()


def js_string(value):
    if value is None:
        return 'null'
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def text(value):
    return js_string(value) if value else ''


def normalize_simple(value):
    return re.sub('[\u0300-\u036f]', '', unicodedata.normalize('NFD', js_string(value))).strip().lower()


def normalize(value):
    return re.sub(r'\s+', ' ', re.sub(r'[.\-_]', ' ', normalize_simple(text(value)))).strip()


def find_index(headers, options):
    choices = {normalize(x) for x in options}
    return next((i for i, h in enumerate(headers) if normalize(h) in choices), -1)


def cell(row, index, default=''):
    return row[index] if 0 <= index < len(row) else default


def number(value):
    if value is None or value == '':
        return 0.0
    try:
        s = js_string(value).strip()
        if not s:
            return 0.0
        if re.match(r'^0[xbo]', s, re.I):
            if not re.fullmatch(r'(?:0[xX][0-9a-fA-F]+|0[bB][01]+|0[oO][0-7]+)', s):
                return math.nan
            return float(int(s, 0))
        if s not in ('Infinity', '+Infinity', '-Infinity') and not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', s, re.ASCII):
            return math.nan
        return float(s)
    except (ValueError, TypeError, OverflowError):
        return math.nan


def number_or_zero(value):
    n = number(value)
    return 0 if math.isnan(n) else n


def convert_number(value, empty=0):
    return empty if value is None or value == '' else number(js_string(value).replace(',', '.', 1))


def normalize_factor(value, empty=1):
    factor = convert_number(value, empty)
    if not math.isfinite(factor):
        return empty
    while factor >= 10000:
        factor /= 10000
    return factor


def correct_factor(udm, saved):
    match = re.match(r'^x\s*(\d+(?:[.,]\d+)?)', text(udm).strip(), re.I | re.ASCII)
    if match:
        factor = number(match[1].replace(',', '.', 1))
        if factor > 0:
            return factor
    factor = normalize_factor(saved, 1)
    return factor if factor > 0 else 1


def date_key(value, timezone='America/Bogota'):
    if isinstance(value, datetime):
        return (value.astimezone(ZoneInfo(timezone)) if value.tzinfo else value).strftime('%Y-%m-%d')
    if isinstance(value, date):
        return value.isoformat()
    s = text(value).strip()
    match = re.fullmatch(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', s)
    return f'{match[3]}-{match[2]:0>2}-{match[1]:0>2}' if match else s


def summary_key(fecha, pdv, item, timezone='America/Bogota'):
    item = text(item).strip()
    return f'{date_key(fecha, timezone)}|{normalize(pdv)}|{item}' if item else ''


def duplicate_key(fecha, pdv, categoria, timezone='America/Bogota'):
    return date_key(fecha, timezone), normalize(pdv), normalize(categoria)


def remove_xlsx_extension(name):
    return re.sub(r'\.xlsx$', '', name, flags=re.I).strip()


def spanish_key(value, numeric=False):
    # Unicode collation; Spanish ñ must sort after n and before o.
    s = unicodedata.normalize('NFC', text(value))
    parts = re.split(r'([0-9]+)', s) if numeric else [s]
    primary, secondary, tertiary = [], [], []
    digit_weight = _collator.sort_key('0')[0]
    for part in parts:
        if numeric and part.isascii() and part.isdigit():
            primary.append((digit_weight, int(part)))
            secondary.append(32)
            tertiary.append(2)
            continue
        weights = _collator.sort_key(part.replace('ñ', 'n\uffff').replace('Ñ', 'N\uffff'))
        levels = [[]]
        for weight in weights:
            if weight == 0:
                levels.append([])
            else:
                levels[-1].append(weight)
        primary.extend((w, 0) for w in levels[0])
        secondary.extend(levels[1])
        tertiary.extend(levels[2])
    return tuple(primary), tuple(secondary), tuple(tertiary)


def spreadsheet_id(url):
    match = re.search(r'/spreadsheets/d/([\w-]+)', url)
    if match:
        return match[1]
    if re.fullmatch(r'[\w-]+', url):
        return url
    from app.errors import FunctionalError
    raise FunctionalError('La URL de Base Google Sheets no es válida.')
