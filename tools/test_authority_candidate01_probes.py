"""Candidate probes against the frozen validation03 authority contracts.

These are proposed regressions, not claims that the candidates were executed.
No callbacks mutate GM state; one native reroll decision deliberately returns
invalid input. Save edits change only one retained class-event scalar.
"""
from copy import copy, deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon
from grid import Grid
from native_scenario_fixture import prepare_body
import action_points as AP
import blessing_skill_rules as B
import class_actor_state_actions as CLASS
import common_checks as CHECKS
import consumption_execution as STOCK
import state_codec as CODEC
import trainer_feature_acquisition as ACQUIRE
import warper as WARPER
import world_entities as WORLD


class Candidate01Probes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fantasy = Rules(ROOT, ruleset='fantasy')
        cls.all_rules = Rules(ROOT, ruleset='all')

    def engine(self, base):
        rules = copy(base)
        rules.rulings = deepcopy(base.rulings)
        engine = Engine(rules, seed=291001)
        engine.grid = Grid(12, 8)
        self.assertIs(engine.rulings, engine.r.rulings)
        self.assertIsNot(engine.rulings, base.rulings)
        return engine

    def trainer(self, engine, name, position, *, feats=(), edges=(), gifts=(), choices=None):
        actor = Combatant(engine.r, {
            'id': 'candidate01/' + name, 'name': name, 'kind': 'trainer',
            'level': 30, 'size': '중형', 'types': ['노말'],
            'stats': {'hp': 40, 'atk': 12, 'def': 12, 'spa': 12, 'spd': 12, 'spe': 12},
            'skills': {'오컬트학': 3, '교활': 3, '육상': 3, '곡예': 3,
                       '의학': 4, '직감': 4, '명령': 4, '일반지식': 4, '집중': 3},
            'feats': list(feats), 'edges': list(edges), 'gifts': list(gifts),
            'edge_choices': dict(choices or {}), 'items': {}, 'moves': [],
            'abilities': [], 'classes': [], 'movement': {'land': 6, 'power': 3},
            'movement_basis': 'base', 'weight_kg': 30, 'exp_bank': 100,
        })
        engine.gm.add_combatant(actor, pos=position, side='party', reason='declared actual starting actor')
        prepare_body(engine, actor, size='중형', offsets=[(0, 0)], reason='actual one-cell body')
        return actor

    def wisdom_fixture(self, *, probability=False):
        engine = self.engine(self.fantasy)
        first = self.trainer(engine, 'wisdom', (2, 2),
            feats=('feat/나의-이름으로', 'supp-blessings/계약자'),
            edges=('edge/원소-교감',), gifts=(B.ANCIENT_WISDOM,),
            choices={'edge/원소-교감': '에스퍼'})
        second = self.trainer(engine, 'second', (3, 2))
        first.spec['gift_patrons'] = {B.ANCIENT_WISDOM: '뮤'}
        # The native Gift interface confirms an already-declared acquisition;
        # it does not fabricate an activation or authorize free AP.
        engine.confirm_blessing_gift(first, B.ANCIENT_WISDOM,
            configuration={'role': 'contractor'}, reason='actual acquired Contractor gift')
        if probability:
            ACQUIRE.acquire_static(engine, first, WARPER.CLASS,
                acquisition_request_id='candidate01/actual-warper')
            self.assertIsNotNone(WARPER.acquired(first, WARPER.CLASS))
        engine.start_round(engine.everyone)
        engine.start_of_turn(first, initiative_count=30)
        before = AP.available(first)
        engine.activate_blessing_skill_rule(first, B.ANCIENT_WISDOM,
            reason='pay the printed Contractor next-check activation')
        self.assertEqual(AP.available(first), before - 1)
        self.assertEqual(first.spec[B.STATE]['activations'][B.ANCIENT_WISDOM]['status'], 'pending')
        return engine, first, second

    def test_c01_01_late_native_reroll_refusal_does_not_consume_first_team_activation(self):
        engine, first, second = self.wisdom_fixture(probability=True)
        observed = []
        def invalid_choice(actual_roll):
            observed.append((actual_roll.rank, len(actual_roll.faces)))
            return 'invalid native choice'  # No engine, actor or GM mutation.
        engine.arm_probability_control(first, second, purpose='skill', decision=invalid_choice)
        actors = (first, second)
        def snapshot():
            return deepcopy((first.spec, second.spec, first.budget,
                first._action_history, engine.rng.getstate(), engine.log_lines,
                engine._ap_rolls), {id(actor): actor for actor in actors})
        before = snapshot()
        with self.assertRaisesRegex(ValueError, 'observed native reroll choice'):
            engine.common_action(skill='오컬트학', dc=10, mode='team',
                participants=[first, second], required_people=2,
                equal_contribution=True, no_main_actor=True)
        self.assertEqual(observed, [(3, 3)])
        self.assertFalse(getattr(engine, '_skill_sequences', {}))
        self.assertEqual(snapshot(), before,
            'A rejected nonfeatured team check lost RNG/logs but consumed a borrowed live first-actor activation')

    def test_c01_01_normal_world_response_pending_keeps_the_real_observed_roll_consumption(self):
        engine, first, _ = self.wisdom_fixture()
        paid = (AP.available(first), list(first._action_history))
        result = engine.common_action(first, '오컬트학', 5, mode='skill', fixed=[2] * 5)
        self.assertIsInstance(result, CHECKS.PendingDecision)
        self.assertEqual(result.check.total, 10)
        self.assertEqual(first.spec[B.STATE]['activations'][B.ANCIENT_WISDOM]['status'], 'consumed')
        self.assertEqual((AP.available(first), first._action_history), paid)
        ordinary = engine.skill_roll(first, '오컬트학', fixed=[2] * 3)
        self.assertEqual(len(ordinary.faces), 3)

    def test_c01_01_scoped_team_late_refusal_preserves_native_subjects(self):
        engine, first, second = self.wisdom_fixture(probability=True)
        engine.arm_probability_control(first, second, purpose='skill', decision=lambda roll: 'invalid choice')
        requests = []
        for actor in (first, second):
            plan = engine.plan_skill_check(actor, '오컬트학', purpose='team occult interpretation', target=actor, provider=actor)
            requests.append({'actor': actor, 'target': actor, 'provider': actor, 'skill': '오컬트학',
                'purpose': 'team occult interpretation', 'replacement': None, 'options': {}, 'expected_plan': plan})
        memo = {id(actor): actor for actor in (first, second)}
        before = deepcopy((first.spec, second.spec, engine.rng.getstate(), engine.log_lines, engine._ap_rolls), memo)
        with self.assertRaisesRegex(ValueError, 'observed native reroll choice'):
            engine.resolve_roll_context(requests, {'kind': 'team', 'dc': 10, 'required_people': 2}, request_id='candidate01/scoped-team')
        self.assertEqual(deepcopy((first.spec, second.spec, engine.rng.getstate(), engine.log_lines, engine._ap_rolls), memo), before)
        self.assertNotIn('candidate01/scoped-team', getattr(engine, '_roll_context_requests', {}))

    def test_c01_01_focus_task_pending_commits_actual_one_check_activation(self):
        engine, first, _ = self.wisdom_fixture()
        paid = (AP.available(first), list(first._action_history))
        result = engine.common_action(first, '오컬트학', 5, mode='focus_task', focus_dc=5,
            context={'kind': 'complex', 'purpose': 'read a complex occult inscription', 'focus_reason': 'sustained concentration'},
            task_options={'fixed': [2] * 5}, focus_options={'fixed': [2] * 3})
        self.assertIsInstance(result, CHECKS.PendingDecision)
        self.assertEqual((result.basis['task_roll'].total, result.basis['focus_roll'].total), (10, 6))
        self.assertEqual(first.spec[B.STATE]['activations'][B.ANCIENT_WISDOM]['status'], 'consumed')
        self.assertEqual((AP.available(first), first._action_history), paid)

    def test_c01_01_precision_pending_commits_actual_one_check_activation(self):
        engine, first, _ = self.wisdom_fixture()
        result = engine.common_action(first, '오컬트학', 5, mode='precise',
            context={'delicate': True, 'activity': 'ordinary_task', 'purpose': 'copy a precise occult inscription'},
            task_options={'fixed': [2] * 5})
        self.assertIsInstance(result, CHECKS.PendingDecision)
        self.assertEqual(result.check.total, 10)
        self.assertEqual(first.spec[B.STATE]['activations'][B.ANCIENT_WISDOM]['status'], 'consumed')

    def medical_fixture(self):
        engine = self.engine(self.all_rules)
        # This owner accepts declared acquired feats from a sheet, as its native
        # existing fixture does. Include Medic and its printed Medicine rank;
        # do not claim certification of character creation or purchase history.
        owner = self.trainer(engine, 'medic', (2, 2),
            feats=('feat/메딕', CLASS.MEDICAL_TECHNIQUE), edges=('edge/메딕-훈련',))
        targets = []
        for species, name, position in (('이상해씨', 'patient-a', (3, 2)), ('꼬부기', 'patient-b', (4, 2))):
            target = Combatant(engine.r, build_pokemon(engine.r, species, 20,
                name=name, moves=['몸통박치기'], abilities=[],
                extra={'trainer_id': owner.entity_id, 'trainer': owner.name}))
            engine.gm.add_combatant(target, pos=position, side='party', reason='actual owned patient')
            prepare_body(engine, target, size=target.spec['size'], offsets=[(0, 0)], reason='actual species-sized patient body')
            engine.gm.set_hp(target, value=1, reason='actual prior injury damage')
            targets.append(target)
        engine.start_round(engine.everyone)
        engine.start_of_turn(owner, initiative_count=30)
        owner.spec['items']['상처약'] = 1
        engine.use_item(owner, '상처약', targets[0])
        pending = [row for row in engine.pending_class_actor_state_actions(owner)
                   if row['source'] == CLASS.MEDICAL_TECHNIQUE]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['target_id'], targets[0].entity_id)
        payments = list(STOCK.validate(owner).values())
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments[0]['target_id'], targets[0].entity_id)
        self.assertEqual(owner.spec['items']['상처약'], 0)
        payload = json.loads(json.dumps(engine.export_state(), ensure_ascii=False))
        return engine, owner, *targets, pending[0]['id'], payload

    def restored(self, rules, payload, *actors):
        engine = Engine.import_state(rules, payload)
        index = WORLD.actor_index(engine)
        self.assertIs(engine.rulings, engine.r.rulings)
        return engine, *(index[actor.entity_id] for actor in actors)

    def test_c01_02_native_medicine_pending_roundtrip_resolve_replay_and_decline(self):
        original, owner, patient, other, event_id, payload = self.medical_fixture()
        engine, owner, patient, other = self.restored(original.r, payload, owner, patient, other)
        before = (patient.hp, other.hp, AP.available(owner))
        result = engine.resolve_class_actor_state_action(owner, event_id, use=True)
        self.assertTrue(result['used']); self.assertGreater(patient.hp, before[0])
        self.assertEqual(other.hp, before[1]); self.assertEqual(AP.available(owner), before[2] - 1)
        state = engine.export_state()
        with self.assertRaisesRegex(ValueError, 'pending'):
            engine.resolve_class_actor_state_action(owner, event_id, use=True)
        self.assertEqual(engine.export_state(), state)
        declined, owner, patient, other = self.restored(original.r, payload, owner, patient, other)
        before = (patient.hp, other.hp, AP.available(owner))
        self.assertFalse(declined.resolve_class_actor_state_action(owner, event_id, use=False)['used'])
        self.assertEqual((patient.hp, other.hp, AP.available(owner)), before)

    def test_c01_02_single_saved_target_edit_cannot_redirect_original_medicine_trigger(self):
        original, owner, patient, other, event_id, payload = self.medical_fixture()
        nodes = [node for node in payload['nodes'].values() if node['kind'] == 'dict'
                 and ['id', event_id] in node['items']
                 and ['source', CLASS.MEDICAL_TECHNIQUE] in node['items']]
        self.assertEqual(len(nodes), 1)
        target_fields = [pair for pair in nodes[0]['items'] if pair[0] == 'target_id']
        self.assertEqual(target_fields, [['target_id', patient.entity_id]])
        target_fields[0][1] = other.entity_id  # The only edited saved scalar.
        try:
            engine, owner, patient, other = self.restored(original.r, payload, owner, patient, other)
        except CODEC.StateCodecError:
            return  # Rejection at the import boundary is acceptable.
        payments = list(STOCK.validate(owner).values())
        self.assertEqual(payments[0]['target_id'], patient.entity_id)
        before = engine.export_state()
        before_hp = other.hp
        try:
            result = engine.resolve_class_actor_state_action(owner, event_id, use=True)
        except ValueError:
            self.assertEqual(engine.export_state(), before)
            return  # Rejection at consumption must be atomic.
        self.fail('single-field saved target edit accepted: original medicine target=' + patient.entity_id
                  + ', changed target=' + other.entity_id + ', other HP=' + str(before_hp) + '->' + str(other.hp)
                  + ', result=' + repr(result))


if __name__ == '__main__':
    unittest.main()