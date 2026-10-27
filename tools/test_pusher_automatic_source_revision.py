"""Pusher's nine native qualifying acquisitions are static and spend no TP/hour."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_book_researcher_fields_crafting as FIX
from engine import Rules
import researcher_fields as RFS
import capability_parameter_edges as PARAMETERS
import ranged_struggle as RANGED
import state_codec as CODEC
import state_grants as GRANTS
import world_entities as WORLD
import activity_jobs as JOBS
import wild_equipment as WILD


class PusherAutomaticSourceRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    setUp = FIX.ResearcherFieldsCraftingTests.setUp
    setup = FIX.ResearcherFieldsCraftingTests.setup
    trainer = FIX.ResearcherFieldsCraftingTests.trainer
    pokemon = FIX.ResearcherFieldsCraftingTests.pokemon
    rejected = FIX.ResearcherFieldsCraftingTests.rejected
    valid = FIX.ResearcherFieldsCraftingTests.valid
    restore = FIX.ResearcherFieldsCraftingTests.restore

    CASES = (
        ('poke_edge/기본-원거리-공격', 20, ['불쏘시개'], {'capability': '불쏘시개'}, 1),
        ('poke_edge/파동술', 30, ['파동 감지'], {}, 2),
        ('poke_edge/유혹적인-미끼', 20, ['매혹'], {}, 1),
        ('poke_edge/투명-연장', 20, ['투명'], {}, 1),
        ('poke_edge/장거리-판독', 20, ['텔레파시'], {}, 1),
        ('poke_edge/꼼꼼한-실', 20, ['실 날리기'], {}, 1),
        ('poke_edge/지진계', 20, ['진동감지'], {}, 1),
        ('poke_edge/tk-마스터리', 20, ['염력'], {}, 1),
        ('poke_edge/흔적-탐지', 20, ['추적자'], {}, 1),
    )

    def subject(self, case, *, level=None, capabilities=None, points=0):
        source, minimum, caps, choices, cost = case
        return self.pokemon('근육몬', minimum if level is None else level, 'subject',
            moves=[], abilities=[], tutor_points=points,
            capabilities=caps if capabilities is None else capabilities,
            skills={'육상': 3, '집중': 4, '통찰': 3})

    def acquire(self, q, source, **options):
        return self.e.pokemon_activity(self.t, 'teach_edge', target=q, edge=source, **options)

    def test_all_nine_native_sources_acquire_without_training_job_credit_tp_or_action(self):
        self.assertEqual({row[0] for row in self.CASES}, set(RFS.DEFINITIONS[RFS.PUSHER]['free_poke_edges']))
        for case in self.CASES:
            with self.subTest(source=case[0]):
                self.setup(capabilities=['파동술'])
                q = self.subject(case)
                self.e.start_round([self.t, q]); self.e.start_of_turn(self.t)
                elapsed = self.e.elapsed_seconds
                budgets = deepcopy((self.t.budget, ('budget' in vars(q), vars(q).get('budget'))))
                with patch.object(JOBS, 'run_fixed', side_effect=AssertionError('automatic acquisition reached training')):
                    out = self.acquire(q, case[0], from_training=True, **case[3])
                row = q.spec['learned_poke_edges'][-1]
                self.assertEqual((out['seconds'], out['point_cost'], q.spec['tutor_points'], self.e.elapsed_seconds), (0, 0, 0, elapsed))
                self.assertEqual((self.t.budget, ('budget' in vars(q), vars(q).get('budget'))), budgets)
                self.assertEqual((row['source'], row['point_cost'], row['training_source']), (case[0], case[4], RFS.PUSHER))
                self.assertEqual(row['pusher']['acquisition'], 'automatic')
                receipt = next(r for r in self.e.acquisition_receipts(q) if r['basis'] == 'native_learned_edge')
                self.assertEqual(receipt['debit']['amount'], 0)
                self.assertNotIn('training_credit', q.spec)
                self.valid()

    def test_every_level_and_capability_prerequisite_and_aura_provider_reject_unchanged(self):
        for case in self.CASES:
            for missing in ('level', 'capability'):
                with self.subTest(source=case[0], missing=missing):
                    self.setup(capabilities=['파동술'])
                    q = self.subject(case, level=case[1] - 1 if missing == 'level' else None,
                                     capabilities=[] if missing == 'capability' else None)
                    self.rejected(lambda: self.acquire(q, case[0], **case[3]), 'requir|prerequisite|qualification')
        self.setup()
        q = self.subject(self.CASES[1])
        self.rejected(lambda: self.acquire(q, self.CASES[1][0]), 'trainer capability')
        self.setup(capabilities=['파동술'])
        q = self.subject(self.CASES[0])
        self.t.spec['skills']['포켓몬학'] = 2
        self.rejected(lambda: self.acquire(q, self.CASES[0][0], **self.CASES[0][3]), 'printed skill rank')

    def test_basic_ranged_requires_each_real_choice_and_does_not_repeat_or_fund_other_edges(self):
        case = self.CASES[0]
        q = self.subject(case, capabilities=list(RANGED.CHOICES))
        self.rejected(lambda: self.acquire(q, case[0]), 'capability|choice|identity')
        for capability in RANGED.CHOICES:
            self.acquire(q, case[0], capability=capability)
            self.assertEqual(RANGED.range_for(q, capability), 6)
        self.rejected(lambda: self.acquire(q, case[0], capability=RANGED.CHOICES[0]), 'already')
        self.assertEqual((q.spec['tutor_points'], self.e.elapsed_seconds), (0, 0))
        self.rejected(lambda: self.acquire(q, 'poke_edge/재능-훈련', capability='power', safe=True), 'Tutor Point')
        ordinary = self.trainer('ordinary teacher', (5, 5), feats=[])
        paid = self.pokemon('근육몬', 20, 'paid', owner=ordinary, moves=[], abilities=[], tutor_points=1, capabilities=['불쏘시개'])
        self.e.start_round([ordinary, paid]); self.e.start_of_turn(ordinary)
        self.rejected(lambda: self.e.pokemon_activity(ordinary, 'teach_edge', target=paid, edge=case[0], capability='불쏘시개', safe=True), 'active encounter')
        self.e.end_encounter()
        elapsed = self.e.elapsed_seconds
        self.e.pokemon_activity(ordinary, 'teach_edge', target=paid, edge=case[0], capability='불쏘시개', safe=True)
        self.assertEqual((paid.spec['tutor_points'], self.e.elapsed_seconds - elapsed), (0, 3600))

    def test_new_capability_consumers_read_actual_aura_grant_bait_bonus_and_scoped_tracker_check(self):
        self.setup(capabilities=['파동술'])
        q = self.subject(self.CASES[1], level=30, capabilities=['파동 감지', '매혹', '추적자'])
        for index in (1, 2, 8):self.acquire(q, self.CASES[index][0])
        out = self.e.project_aura_thought(q, self.t, 'actual newly acquired Aura Pulse')
        self.assertEqual(out['sender_id'], q.entity_id)
        habitat = {'region': 'actual local clearing', 'species': ['잉어킹'], 'reason': 'GM observed local species'}
        WILD.attract(self.e, q, phase='place', bait_id='actual Alluring', habitat=habitat)
        out = WILD.attract(self.e, q, phase='wait', bait_id='actual Alluring', fixed=11)
        self.assertEqual((out['checks'][-1]['bonus'], out['checks'][-1]['total'], out['status']), (4, 15, 'awaiting_encounter'))
        ordinary = self.e.skill_roll(q, '통찰', fixed=[1, 1, 1]).total
        tracking = self.e.skill_roll(q, '통찰', fixed=[1, 1, 1], skill_context={'purpose': 'capability/추적자', 'reason': 'actual observed tracking task using Tracker'}).total
        self.assertEqual(tracking - ordinary, 4)
        self.rejected(lambda: self.e.skill_roll(q, '집중', fixed=[1] * 4, skill_context={'purpose': 'capability/추적자', 'reason': 'actual observed tracking task using Tracker'}), 'Perception')
        self.q = q; self.restore('t', 'q')
        self.assertIn('파동술', GRANTS.effective_capabilities(self.q))
        GRANTS.replace_baseline(self.e, self.t, 'capabilities', [])
        self.assertNotIn('파동술', GRANTS.effective_capabilities(self.q))
        aura = next(r for r in self.q.spec['learned_poke_edges'] if r['source'] == self.CASES[1][0])
        self.assertEqual((aura['status'], aura['refund']['points'], aura['refund']['net_points'], self.q.spec['tutor_points']), ('refunded', 2, 0, 0))
        self.valid()

    def test_enticing_bonus_requires_actual_alluring_placement_not_later_capability_or_unknown_history(self):
        self.q = q = self.pokemon('근육몬', 20, 'bait user', moves=[], abilities=[], tutor_points=0,
            capabilities=[], items={'미끼': 2}, skills={'육상': 3, '집중': 4, '통찰': 3})
        habitat = {'region': 'actual local clearing', 'species': ['잉어킹'], 'reason': 'GM observed local species'}
        placed = WILD.attract(self.e, q, phase='place', bait_id='physical bait', habitat=habitat)
        self.assertEqual(placed['attraction_source'], placed['source'])
        WILD.attract(self.e, q, phase='place', bait_id='legacy unknown', habitat=habitat)
        WILD.attract(self.e, q, phase='wait', bait_id='legacy unknown', fixed=1)
        legacy = q.spec['placed_bait']['legacy unknown']
        legacy.pop('attraction_source')
        prior_checks = deepcopy(legacy['checks'])
        self.assertEqual(q.spec['items']['미끼'], 0)
        GRANTS.replace_baseline(self.e, q, 'capabilities', ['매혹'])
        self.acquire(q, self.CASES[2][0])
        self.restore('t', 'q'); q = self.q
        for bait_id in ('physical bait', 'legacy unknown'):
            with self.subTest(bait_id=bait_id):
                out = WILD.attract(self.e, q, phase='wait', bait_id=bait_id, fixed=11)
                self.assertEqual((out['checks'][-1]['bonus'], out['checks'][-1]['total'], out['status']), (0, 11, 'placed'))
        legacy = q.spec['placed_bait']['legacy unknown']
        self.assertNotIn('attraction_source', legacy)
        self.assertEqual(legacy['checks'][:-1], prior_checks)
        placed = WILD.attract(self.e, q, phase='place', bait_id='actual Alluring', habitat=habitat)
        self.assertEqual((placed['attraction_source'], q.spec['items']['미끼']), ('capability/매혹', 0))
        out = WILD.attract(self.e, q, phase='wait', bait_id='actual Alluring', fixed=11)
        self.assertEqual((out['checks'][-1]['bonus'], out['checks'][-1]['total'], out['status']), (4, 15, 'awaiting_encounter'))
        self.valid()

    def test_restore_and_actual_prerequisite_loss_refund_zero_while_paid_control_refunds_actual_cost(self):
        self.setup(capabilities=['파동술'])
        self.q = q = self.subject(self.CASES[1], level=30, capabilities=['파동 감지', '실 날리기', '염력', '불쏘시개'])
        for index in (0, 1, 5, 7):self.acquire(q, self.CASES[index][0], **self.CASES[index][3])
        paid_owner = self.trainer('paid owner', (4, 4), feats=[])
        paid = self.pokemon('근육몬', 20, 'paid target', owner=paid_owner, tutor_points=1, moves=[], abilities=[], capabilities=['실 날리기'])
        self.e.pokemon_activity(paid_owner, 'teach_edge', target=paid, edge=self.CASES[5][0], safe=True)
        paid_id = paid.entity_id
        acquired = deepcopy(q.spec['learned_poke_edges'])
        self.restore('t', 'q'); q = self.q; paid = WORLD.actor_index(self.e)[paid_id]
        self.assertEqual(q.spec['learned_poke_edges'], acquired)
        self.e.gm.set_level(q, 19, reason='actual lost level prerequisite')
        self.e.gm.set_level(paid, 19, reason='actual lost paid prerequisite')
        self.assertEqual((q.spec['tutor_points'], paid.spec['tutor_points']), (0, 1))
        for row in q.spec['learned_poke_edges']:
            self.assertEqual((row['status'], row['refund']['net_points']), ('refunded', 0))
            self.assertEqual(row['refund']['points'], row['point_cost'])
        self.e.gm.set_level(q, 18, reason='further observation cannot refund again')
        self.assertEqual(q.spec['tutor_points'], 0)
        self.restore('t', 'q'); self.assertEqual(self.q.spec['tutor_points'], 0)
        self.valid()

    def test_failure_rolls_back_native_acquisition_and_closes_only_its_pusher_scope(self):
        q = self.subject(self.CASES[0])
        native = RANGED._teach
        def fail_after_native(*args, **kwargs):
            native(*args, **kwargs)
            raise ValueError('late native acquisition failure')
        with patch.object(RANGED, '_teach', side_effect=fail_after_native):
            self.rejected(lambda: self.acquire(q, self.CASES[0][0], **self.CASES[0][3]), 'late native acquisition failure')
        self.assertFalse(RFS.pusher_acquiring(self.e, self.t, q))
        self.acquire(q, self.CASES[0][0], **self.CASES[0][3])
        self.assertEqual((q.spec['tutor_points'], self.e.elapsed_seconds), (0, 0))

    def test_static_acquisition_does_not_require_its_owning_trainer_to_be_conscious(self):
        q = self.subject(self.CASES[0])
        self.e.gm.set_hp(self.t, value=0, reason='actual unconscious owner')
        self.acquire(q, self.CASES[0][0], **self.CASES[0][3])
        self.assertEqual((RANGED.range_for(q, '불쏘시개'), q.spec['tutor_points'], self.e.elapsed_seconds), (6, 0, 0))
        self.valid()

    def test_new_three_ordinary_sources_keep_selected_native_cost_hour_and_paid_refund(self):
        for index in (1, 2, 8):
            case = self.CASES[index]
            with self.subTest(source=case[0]):
                self.setup(feats=[], capabilities=['파동술'])
                q = self.subject(case, points=3)
                out = self.acquire(q, case[0], safe=True)
                self.assertEqual((out['point_cost'], out['seconds'], q.spec['tutor_points'], self.e.elapsed_seconds), (case[4], 3600, 3 - case[4], 3600))
                self.e.gm.set_level(q, case[1] - 1, reason='actual paid prerequisite loss')
                row = q.spec['learned_poke_edges'][-1]
                self.assertEqual((row['refund']['points'], q.spec['tutor_points']), (case[4], 3))
                self.assertNotIn('pusher', row)
                self.valid()

    def test_legacy_funded_receipt_shape_stays_readable_without_rewriting_history(self):
        q = self.subject(self.CASES[0])
        self.acquire(q, self.CASES[0][0], **self.CASES[0][3])
        # Project only the metadata fields emitted by the frozen old funding producer.
        row = q.spec['learned_poke_edges'][-1]
        row['pusher'].pop('acquisition'); row['pusher'].pop('seconds')
        row['training_source'] = 'input/ch05-pokemon.md:274'
        legacy = deepcopy(row)
        self.q = q; self.restore('t', 'q')
        self.assertEqual(self.q.spec['learned_poke_edges'][-1], legacy)
        self.assertEqual(next(r for r in self.e.acquisition_receipts(self.q) if r['basis'] == 'native_learned_edge')['debit']['amount'], 0)
        self.e.gm.set_level(self.q, 19, reason='actual legacy prerequisite loss')
        self.assertEqual((self.q.spec['tutor_points'], self.q.spec['learned_poke_edges'][-1]['refund']['net_points']), (0, 0))


if __name__ == '__main__':
    unittest.main()
