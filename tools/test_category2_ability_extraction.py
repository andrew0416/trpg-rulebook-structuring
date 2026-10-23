"""Exact source recovery and native identity admission, not full effect certification."""
import csv, json, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'engine')]
from ptk_structure import parse_abilities, dedupe_ids
from engine import Rules, Engine, Combatant

class AbilityExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.failed = parse_abilities(str(ROOT / 'input/db/abilities.csv'))
        dedupe_ids(cls.rows)
        with (ROOT / 'input/db/abilities.csv').open(encoding='utf-8', newline='') as f:
            cls.original = list(csv.reader(f))
        cls.rules = Rules(str(ROOT), ruleset='core')

    def test_unparsed_frequency_does_not_remove_a_named_source_definition(self):
        self.assertEqual(self.failed, [])
        for name, nr in [('리시버', 112), ('빙점', 216), ('일루전', 333)]:
            row = next(r for r in self.rows if r['name'] == name)
            source = self.original[nr - 1]
            self.assertEqual(row['frequency'], source[1])
            self.assertEqual(row['effect_primary'], source[2])
            self.assertEqual(row['effect2'], source[6])
            self.assertEqual(row['_source']['record_span'], [nr, nr])
            self.assertEqual(row['frequency_parse']['status'], 'requires_rule_specific_interpretation')
            self.assertNotIn('freq_kind', row)
        self.assertEqual(next(r for r in self.rows if r['name'] == '리시버')['action'], '자유 행동')

    def test_receiver_exact_copy_preserves_both_coordinates_and_one_identity(self):
        matches = [r for r in self.rows if r['name'] == '리시버']
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['id'], 'ability/리시버')
        self.assertEqual(self.original[111], self.original[570])
        self.assertEqual(matches[0]['_source_duplicates'][0]['record_span'], [571, 571])

    def test_variant_unparsed_body_is_not_merged_and_missing_effect_is_reported(self):
        first = self.original[111]
        variant = list(first); variant[2] += ' 별도의 원문 변형.'; variant[6] = variant[2]
        missing = list(first); missing[0] = '효과 누락'; missing[2] = missing[6] = ''
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'abilities.csv'
            with p.open('w', encoding='utf-8', newline='') as f:
                csv.writer(f).writerows([self.original[0], first, first, variant, missing])
            records, failed = parse_abilities(str(p)); dedupe_ids(records)
        self.assertEqual([r['id'] for r in records], ['ability/리시버', 'ability/리시버-2'])
        self.assertEqual(len(records[0]['_source_duplicates']), 1)
        self.assertEqual(failed[0]['reason'], 'missing_effect_body')

    def test_actual_rules_lookup_gm_admission_and_durable_identity(self):
        e = Engine(self.rules, seed=447)
        for index, name in enumerate(['리시버', '빙점', '일루전']):
            uid = 'ability/' + name
            self.assertEqual(self.rules.selection.resolve_name(name, ('ability/',)), uid)
            self.assertEqual(self.rules.selection.resolve(uid), uid)
            self.assertEqual(self.rules.selection.units[uid]['source']['record_span'], [112,112] if index == 0 else [216,216] if index == 1 else [333,333])
            self.assertEqual(self.rules.ability_freq[name], self.original[[111,215,332][index]][1])
            c = Combatant(self.rules, dict(id='pokemon/recovered-' + str(index), name=name,
                kind='pokemon', level=5, stats=dict(hp=8, atk=8, **{'def':8}, spa=8, spd=8, spe=8),
                abilities=[name], moves=[], types=[]))
            e.gm.add_combatant(c, reason='source definition recovery acceptance')
        loaded = Engine.import_state(self.rules, e.export_state())
        self.assertEqual([c.abilities for c in loaded.everyone], [['리시버'], ['빙점'], ['일루전']])
        for c in loaded.everyone:
            self.assertEqual(loaded.r.selection.resolve_name(c.abilities[0], ('ability/',)), 'ability/' + c.abilities[0])

if __name__ == '__main__':
    unittest.main(verbosity=2)
