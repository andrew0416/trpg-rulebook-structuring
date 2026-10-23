"""Weight Class keyword reference through the actual selected rule reader."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules
import build_lookup_tables as TABLES

TABLE = 'pokemon/weight-classes'
# Transcribed from the original table, independent of the generated declaration.
DESCRIPTIONS = (
    '0~11kg / 0~25 lbs',
    '11~25kg / 25~55 lbs',
    '25~50kg / 55~110 lbs',
    '50~100kg / 110~220 lbs',
    '100~200kg / 220~440 lbs',
    '200kg / 440lbs 이상',
    '205kg 이상이고, 헤비메탈 특성을 가진 포켓몬',
)


class WeightReferenceTests(unittest.TestCase):
    def test_native_selected_lookup_preserves_all_source_rows_and_regeneration(self):
        rules = Rules(str(ROOT), ruleset='all')
        actual = rules.mech(TABLE)['by_weight_class']
        self.assertEqual(set(actual), {str(n) for n in range(1, 8)})
        for n, description in enumerate(DESCRIPTIONS, 1):
            with self.subTest(weight_class=n):
                self.assertEqual(actual[str(n)], {
                    'label': f'무게 등급 {n}', 'description': description})
        unit = rules.units[TABLE]
        self.assertEqual(unit['source'], {'chapter': 'ch10-index-reference', 'line': 426})
        self.assertEqual(TABLES.weight_class_table(str(ROOT / 'input')), unit)

    def test_missing_or_mislabelled_source_rows_cannot_be_published_as_a_full_table(self):
        original = (ROOT / 'input/ch10-index-reference.md').read_text(encoding='utf-8')
        bad_inputs = (
            original.replace('| 무게 등급 7 | 205kg 이상이고, 헤비메탈 특성을 가진 포켓몬 |\n', ''),
            original.replace('| 무게 등급 6 |', '| 무게 등급 5 |'),
        )
        with TemporaryDirectory() as directory:
            target = Path(directory) / 'ch10-index-reference.md'
            for text in bad_inputs:
                with self.subTest(source=text[-40:]):
                    self.assertNotEqual(text, original)
                    target.write_text(text, encoding='utf-8')
                    with self.assertRaises(ValueError):
                        TABLES.weight_class_table(directory)


if __name__ == '__main__':
    unittest.main()
