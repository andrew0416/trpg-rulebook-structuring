"""CSV whole Dancer: same Dance Form/template owners, one explicit Waltz prerequisite difference."""
from pathlib import Path
from unittest.mock import patch
import unittest

import test_book_dancer_acquisition as fixture
from engine import Rules
from ruleset import RuleFilter
import dancer as D
import action_points as AP

ROOT = Path(__file__).resolve().parents[1]


class DancerCsvTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    add = fixture.DancerAcquisitionTests.add
    acquire = fixture.DancerAcquisitionTests.acquire
    dancer = fixture.DancerAcquisitionTests.dancer
    create = fixture.DancerAcquisitionTests.create
    rejected = fixture.DancerAcquisitionTests.rejected
    valid = fixture.DancerAcquisitionTests.valid
    invalid = fixture.DancerAcquisitionTests.invalid
    restore = fixture.DancerAcquisitionTests.restore
    combat = fixture.DancerAcquisitionTests.combat
    next_turn = fixture.DancerAcquisitionTests.next_turn
    use = fixture.DancerAcquisitionTests.use
    answer = fixture.DancerAcquisitionTests.answer
    retrain = fixture.DancerAcquisitionTests.retrain

    def setUp(self):
        self.version('local_csv')
        fixture.DancerAcquisitionTests.setUp(self)

    def version(self, version):
        self.rules.ruleset = RuleFilter({'sources': ['core'], 'unit_versions': {} if version is None else {D.WALTZ: version}})
        self.rules._apply_ruleset()

    def test_csv_waltz_requires_practice_not_form_and_uses_the_same_native_dance_stage_consumer(self):
        self.acquire(D.CLASS, branch='마이페이스')
        self.acquire(D.DANCE_FORM)
        self.rejected(lambda: self.acquire(D.WALTZ), 'Dancer prerequisite.*댄스-연습')
        self.acquire(D.PRACTICE)
        self.t.spec['skills'].update({'곡예': 5, '육상': 5, '매력': 5})
        self.rejected(lambda: self.acquire(D.WALTZ), 'printed skill rank')
        self.t.spec['skills']['매력'] = 6
        receipt = self.acquire(D.WALTZ)
        self.assertEqual(receipt['source']['behavior_source'], D.waltz_source(self.rules))
        self.assertEqual(set(receipt['snapshot']['parents']), {D.PRACTICE})
        # The CSV variant also works with no Dance Form: printed Dance Moves are independent.
        other = self.add('CSV dancer without Form', 'trainer', (6, 6), classes=[], feats=[], edges=[], items={}, money=100, moves=[], speed=29)
        self.acquire(D.CLASS, branch='마이페이스', trainer=other)
        self.acquire(D.PRACTICE, trainer=other)
        self.acquire(D.WALTZ, trainer=other)
        self.assertNotIn(D.DANCE_FORM, other.spec['feats'])
        ally = self.add('ally', 'pokemon', (7, 6), trainer_id=other.entity_id, speed=25, tutor_points=5)
        self.answer(D.WALTZ_PROMPT, ally.entity_id)
        self.combat(other, count=29)
        ap = AP.available(other)
        self.use(other, other, 'move/칼춤')
        self.assertEqual((other.stages['atk'], ally.stages['atk'], AP.available(other)), (0, 2, ap - 1))
        self.assertEqual(other.spec[D.KEY]['waltzes'][-1]['ally_id'], ally.entity_id)
        self.valid()

    def test_csv_source_and_parent_dependency_survive_restore_without_rewriting_book_receipts(self):
        self.acquire(D.CLASS, branch='마이페이스')
        self.acquire(D.PRACTICE)
        self.acquire(D.WALTZ)
        sid = D.acquisition_source_id(self.t, D.WALTZ)
        expected = [D.acquisition_source_id(self.t, D.PRACTICE)]
        self.assertEqual(self.t.spec['state_grants']['sources'][sid]['withdrawal_dependencies'], expected)
        self.restore('t')
        self.rules = self.e.r   # The native codec returns a new Rules object; switch the restored reader.
        self.assertEqual(self.t.spec['state_grants']['sources'][sid]['withdrawal_dependencies'], expected)
        self.rejected(lambda: self.retrain(D.PRACTICE), 'retained grant depends on withdrawn source')
        self.version(None)
        self.invalid('static Feature acquisition source or owner changed')
        self.version('local_csv')
        self.valid()
        self.retrain(D.WALTZ)
        self.retrain(D.PRACTICE)
        self.assertEqual(self.t.spec['feats'], [D.CLASS])
        self.valid()

    def test_csv_template_keeps_all_five_stat_contest_choices_and_both_two_stat_choices(self):
        self.dancer(*fixture.ALL_FEATURES)
        for index, (stat, contest) in enumerate(D.CONTEST_TYPES.items()):
            row = self.create('CSV 단일춤 ' + str(index), {stat: 2}, contest)
            self.assertIn(row['id'], self.t.moves)
            self.assertEqual(self.rules.move(row['id'])['contest'], contest + ' - 준비하기!')
            effects = self.rules.move_mech(row['id'])[0]['effects_exec']
            self.assertEqual([(e['stat'], e['delta'], e['target']) for e in effects], [(stat, 2, 'self')])
        for index, contest in enumerate(('근사함', '귀여움')):
            row = self.create('CSV 두스탯춤 ' + str(index), {'atk': 1, 'spe': 1}, contest)
            self.assertIn(row['id'], self.t.moves)
            self.assertEqual(self.rules.move(row['id'])['contest'], contest + ' - 준비하기!')
        self.assertEqual((len(D.created_moves(self.t)), D.allowance(self.t)), (7, 7))
        self.valid()

    def test_unknown_waltz_versions_and_modified_csv_bytes_never_select_a_rule(self):
        self.version('unknown')
        with self.assertRaisesRegex(ValueError, 'unknown Passing Waltz source version'):
            D.waltz_source(self.rules)
        self.version('local_csv')
        original = Path.read_bytes
        def read(path):
            content = original(path)
            return content + b' ' if path.name == 'feats.csv' else content
        with patch.object(Path, 'read_bytes', read):
            with self.assertRaisesRegex(ValueError, 'Passing Waltz CSV source changed'):
                D.waltz_source(self.rules)
        self.assertEqual(D.waltz_source(self.rules)['parents'], [D.PRACTICE])


if __name__ == '__main__':
    unittest.main()
