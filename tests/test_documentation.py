from pathlib import Path
import re


def test_every_original_function_is_mapped():
    document = Path('MIGRATION_PARITY.md').read_text(encoding='utf-8')
    for file in Path('legacy').iterdir():
        for function in re.findall(r'function (\w+)\(', file.read_text(encoding='utf-8')):
            assert f'`{function}`' in document, function
