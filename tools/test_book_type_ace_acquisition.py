"""Type Ace: actual acquisition, teaching and permanent/scene resource boundaries."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from grid import Grid
from native_scenario_fixture import prepare_body, assert_rejected_unchanged
import acquired_features as ACQUIRED
import action_points as AP
import frequency as F
import move_state as MOVES
import move_type_sync as SYNC
import pokemon_move_edges as EDGES
import pokemon_party as PARTY
import state_codec as CODEC
import state_fields as FIELDS
import trainer_feature_acquisition as ACQUIRE
import type_ace as TA
import world_entities as WORLD


class TypeAceAcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)
        self.setup()

    def setup(self, *, elemental=None, natural=None):
        self.e = Engine(self.rules, seed=119128)
        self.e.grid = Grid(14, 12)
        self.common = dict(level=30, size='중형',
            stats={'hp':1000, 'atk':20, 'def':20, 'spa':20, 'spd':20, 'spe':20},
            moves=['move/몸통박치기'], abilities=[], types=['노말'],
            movement={'land':6, 'swim':0, 'sky':0, 'power':4}, weight_kg=30,
            skills={'명령':6, '매력':6, '직감':6, '집중':6, '협박':6, '육상':6, '전투':6})
        extra = {'classes':[], 'feats':[], 'exp_bank':100,
                 'type_link_skills':{'노말':'매력', '불꽃':'집중', '물':'육상', '전기':'집중', '격투':'전투'}}
        if elemental:
            extra.update(edges=['edge/원소-교감'], edge_choices={'edge/원소-교감':elemental})
        self.t = self.add('actual Type Ace', 'trainer', (1, 1), **extra)
        types = ['노말', '불꽃', '물', '전기', '격투']
        abilities = [] if natural is None else [natural]
        self.p = self.add('actual learner', 'pokemon', (2, 2),
            trainer_id=self.t.entity_id, tutor_points=8, types=types, abilities=abilities)
        if natural == '타입전략가':
            self.p.spec['ability_type_choices'] = {'ability/타입전략가':'노말'}
        self.q = self.add('distinct owned partner', 'pokemon', (2, 3),
            trainer_id=self.t.entity_id, tutor_points=8, types=types)
        self.b = self.add('actual native recipient', 'pokemon', (4, 2), side='foe')
        for p in (self.p, self.q):
            self.e.gm.observe_loyalty(p, 6, reason='actual willing Pokemon')

    def add(self, name, kind, pos, **extra):
        spec = dict(deepcopy(self.common), name=name, kind=kind)
        spec.update(extra)
        actor = Combatant(self.e.r, spec)  # the restored engine's rules object after restore()
        self.e.gm.add_combatant(actor, pos=pos, side=extra.get('side', 'party'),
            reason='actual Type Ace scene participant')
        prepare_body(self.e, actor, size='중형', offsets=[(0, 0)], reason='observed complete body')
        return actor

    def acquire(self, feature=None, branch='불꽃', actor=None):
        feature = TA.CLASS if feature is None else TA.uid(feature)
        options = {'branch':branch} if feature in (TA.CLASS, TA.REFRESH, TA.SYNC) else {}
        actor = self.t if actor is None else actor
        result = ACQUIRE.acquire_static(self.e, actor, feature,
            acquisition_request_id='type-ace/' + actor.entity_id + '/' + feature + '/' + branch, **options)
        if feature == TA.uid('Close Quarters Mastery'):
            scope = TA.close_quarters_source_choices(self.e.r)['decision_scope']
            TA.choose_close_quarters_source(self.e, actor, dict(value='english_one_marker_per_foe',
                reason='this existing native fixture explicitly uses the English incoming cap', scope=scope))
        return result

    def rejected(self, operation, pattern):
        return assert_rejected_unchanged(self.e, operation, reason_pattern=pattern)

    def valid(self):
        result = self.e.validate_state()
        self.assertTrue(result['valid'], result['issues'])

    def restore(self):
        names = ('t', 'p', 'q', 'b', 'u', 'v', 'w')
        identities = {name:getattr(self, name).entity_id for name in names if hasattr(self, name)}
        self.e = CODEC.load_engine(self.rules, json.loads(json.dumps(self.e.export_state(), ensure_ascii=False)))
        actors = WORLD.actor_index(self.e)
        for name, identity in identities.items():
            setattr(self, name, actors[identity])

    def combat(self, actor):
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor, initiative_count=30)

    def next_turn(self, actor):
        self.e.end_of_turn(self.e._active_turn_actor)
        self.e.end_round()
        self.combat(actor)

    def use(self, move):
        with patch.object(Engine, 'd20', return_value=10):
            return self.e.use_move_on(self.p, self.b, move, self.e.everyone, set_damage=True)

    def communication(self, trainer=None):
        self.e.gm.observe_sensory_environment(trainer or self.t, self.p,
            paths={'auditory':True}, present=True, reason='actual audible Order communication')

    def transfer(self):
        self.u = self.add('actual second Type Ace', 'trainer', (1, 4), classes=[], feats=[], exp_bank=100,
            type_link_skills=deepcopy(self.t.spec['type_link_skills']))
        self.v = self.add('second owner partner one', 'pokemon', (2, 4), trainer_id=self.u.entity_id,
            types=['불꽃', '노말'])
        self.w = self.add('second owner partner two', 'pokemon', (2, 5), trainer_id=self.u.entity_id,
            types=['불꽃', '노말'])
        for trainer, roster in ((self.t, [self.p, self.q]), (self.u, [self.v, self.w])):
            PARTY.configure(self.e, trainer, mode='standard', roster=roster,
                storage={'kind':'center', 'id':'type-ace-center-' + trainer.entity_id},
                reason='actual complete owned roster and campaign carrying policy')
        WORLD.transfer_owner(self.e, self.p, self.t, self.u,
            reason='actual later ownership transfer', request_id='type-ace/transfer')
        self.e.gm.send_out(self.p, pos=(2, 2), reason='actual transferred Pokemon returns to the field')
        self.e.gm.observe_loyalty(self.p, 6, reason='actual willing partner under the new Trainer')

    def teach(self, branch='불꽃', ability='last_chance', actor=None, pokemon=None, **extra):
        options = {'seconds':60, 'reason':'actual completed Type Ace teaching'}
        options.update(extra)
        return TA.teach(self.e, actor or self.t, pokemon or self.p, branch, ability, **options)

    def sync_decision(self, move='move/냉동빔', application='fire-beam'):
        return dict(application_id=application, move_id=move, new_name='화염광선',
            effect_decision={'mode':'replace', 'reason':'Fire replaces the cold rider at the same threshold.',
                'effects_exec':[{'type':'apply_status', 'status':'화상', 'target':'target', 'on_natural_roll_min':19}]},
            feasibility_review='The printed range, accuracy, class and targets remain unchanged.',
            power_review='Only burn replaces freeze; damage base and effect chance stay printed.',
            reason='GM observes completed permanent Move Sync')

    def test_template_is_complete_and_acquiring_class_does_not_acquire_followers(self):
        self.assertEqual(len(TA.DEFINITIONS), 75)
        self.assertEqual(set(TA.DEFINITIONS), set(TA.FEATURES))
        self.assertEqual(set(TA.TYPES), set(TA.SKILLS))
        receipt = self.acquire()
        self.assertEqual(receipt['snapshot']['branch'], '불꽃')
        self.assertEqual(receipt, self.acquire())
        self.assertEqual([r['feature_id'] for r in TA.records(self.t, active=True)], [TA.CLASS])
        self.assertEqual(self.t.spec['feature_choices'][TA.CLASS], ['불꽃'])
        self.assertFalse(self.p.abilities)
        self.assertEqual(self.p.spec['tutor_points'], 8)
        self.restore()
        self.valid()

    def test_class_requires_distinct_actually_owned_type_and_explicit_novice_skill(self):
        FIELDS.base_patch(self.q, {'types':['물']}, reason='observed different actual partner type')
        self.rejected(self.acquire, 'two matching Pokemon|Elemental Connection')
        self.add('unowned matching Pokemon', 'pokemon', (8, 8), types=['불꽃'])
        self.rejected(self.acquire, 'two matching Pokemon|Elemental Connection')
        FIELDS.base_patch(self.q, {'types':['불꽃']}, reason='actual qualified owned partner type')
        self.t.spec['type_link_skills'].pop('불꽃')
        self.rejected(self.acquire, 'explicit.*skill')
        self.t.spec['type_link_skills']['불꽃'] = '명령'
        self.rejected(self.acquire, 'explicit.*skill')
        self.t.spec['type_link_skills']['불꽃'] = '집중'
        FIELDS.base_patch(self.t, {'skills':dict(self.t.spec['skills'], 집중=2)}, reason='observed below Novice')
        self.rejected(self.acquire, 'rank')
        FIELDS.base_patch(self.t, {'skills':dict(self.t.spec['skills'], 집중=3)}, reason='observed actual Novice')
        self.acquire()
        self.valid()

    def test_elemental_alternative_requires_matching_connection_and_one_owned_pokemon(self):
        self.setup(elemental='불꽃')
        FIELDS.base_patch(self.q, {'types':['물']}, reason='only one actual Fire Pokemon')
        receipt = self.acquire()
        self.assertTrue(receipt['snapshot']['elemental'])
        self.assertEqual(sum('불꽃' in row['types'] for row in receipt['snapshot']['pokemon']), 1)
        self.setup(elemental='물')
        FIELDS.base_patch(self.q, {'types':['물']}, reason='only one Fire Pokemon and wrong Elemental branch')
        self.rejected(self.acquire, 'two matching Pokemon|Elemental Connection')
        self.setup(elemental='불꽃')
        for p in (self.p, self.q):
            FIELDS.base_patch(p, {'types':['물']}, reason='no actual Fire Pokemon')
        self.rejected(self.acquire, 'two matching Pokemon|Elemental Connection')

    def test_branch_prerequisites_selected_rank_and_four_class_slots_are_actual(self):
        self.rejected(lambda:self.acquire(TA.REFRESH), 'prerequisite')
        self.acquire()
        self.rejected(lambda:self.acquire(TA.REFRESH, '물'), 'prerequisite')
        self.rejected(lambda:self.acquire('Incandescence'), 'prerequisite')
        self.acquire('Brightest Flame')
        FIELDS.base_patch(self.t, {'skills':dict(self.t.spec['skills'], 집중=3)}, reason='selected Fire skill remains Novice')
        self.rejected(lambda:self.acquire('Incandescence'), 'rank')
        FIELDS.base_patch(self.t, {'skills':dict(self.t.spec['skills'], 집중=5)}, reason='actual Expert selected skill')
        self.acquire('Incandescence')
        for branch in ('노말', '물', '전기'):
            self.acquire(branch=branch)
        self.assertEqual(len(ACQUIRED.class_instances(self.t)), 4)
        self.rejected(lambda:self.acquire(branch='격투'), 'four|4|class')
        self.rejected(lambda:self.acquire(branch='에러'), 'type|branch')
        self.valid()

    def test_teaching_pays_two_points_extended_time_and_is_once_across_branches_and_transfer(self):
        self.acquire()
        self.acquire(branch='물')
        FIELDS.base_patch(self.p, {'types':['노말']}, reason='printed teaching target need not have the chosen type')
        before = self.e.elapsed_seconds
        self.teach()
        self.assertEqual(self.p.spec['tutor_points'], 6)
        self.assertEqual(self.e.elapsed_seconds, before + 60)
        self.assertEqual(TA.ability_branches(self.e, self.p, 'last_chance'), {'불꽃'})
        self.assertNotIn('ability/타입전략가', __import__('ability_transitions').known(self.p))
        self.rejected(lambda:self.teach('물', 'strategist'), 'only once')
        self.transfer()
        self.acquire(actor=self.u)
        self.restore()
        self.assertEqual(TA.ability_branches(self.e, self.p, 'last_chance'), {'불꽃'})
        self.rejected(lambda:self.teach(actor=self.u), 'only once')
        self.valid()

    def test_teaching_wrong_owner_points_choice_and_late_extended_failure_are_atomic(self):
        self.acquire()
        self.rejected(lambda:self.teach(pokemon=self.b), 'owned|Type Ace')
        self.rejected(lambda:self.teach(ability='invented'), 'Last Chance|Strategist')
        self.rejected(lambda:self.teach(seconds=0), 'seconds')
        self.rejected(lambda:self.teach(reason=''), 'reason')
        self.p.spec['tutor_points'] = 1  # actual remaining point balance
        self.rejected(self.teach, 'Tutor Points')
        self.p.spec['tutor_points'] = 2  # actual qualified point balance
        with patch.object(Engine, 'advance_time', side_effect=ValueError('late native Extended failure')):
            self.rejected(self.teach, 'late native Extended')
        self.teach(ability='strategist')
        self.assertEqual(self.p.spec['tutor_points'], 0)
        self.assertEqual(TA.ability_branches(self.e, self.p, 'strategist'), {'불꽃'})

    def test_refresh_pays_standard_two_ap_restores_chosen_scene_and_all_matching_eot(self):
        self.acquire()
        self.acquire(TA.REFRESH)
        moves = ['move/열풍', 'move/불대문자', 'move/냉동빔', 'move/화염방사', 'move/매지컬플레임']
        for move in moves:
            self.e.gm.set_move(self.p, move, reason='actual known Move available before encounter')
        self.communication()
        self.combat(self.p)
        for number, move in enumerate(moves):
            if number:
                self.next_turn(self.p)
            self.use(move)
        other = deepcopy(F.state(self.p)['moves']['move/냉동빔'])
        for move in ('move/화염방사', 'move/매지컬플레임'):
            self.assertFalse(F.move_allowed(self.e, self.p, move, outside_combat=False)[0])
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.t, initiative_count=20)
        before = AP.available(self.t)
        TA.refresh(self.e, self.t, self.p, '불꽃', 'move/불대문자')
        self.assertEqual(AP.available(self.t), before - 2)
        self.assertEqual(self.t.budget['standard'], 0)
        self.assertEqual(self.p.move_uses['move/불대문자'], 0)
        self.assertEqual(self.p.move_uses['move/열풍'], 1)
        self.assertEqual(F.state(self.p)['moves']['move/냉동빔'], other)
        for move in ('move/화염방사', 'move/매지컬플레임'):
            self.assertTrue(F.move_allowed(self.e, self.p, move, outside_combat=False)[0])
        self.restore()
        self.rejected(lambda:TA.refresh(self.e, self.t, self.p, '불꽃', 'move/불대문자'), 'frequency')
        self.e.end_encounter(self.e.everyone)
        self.transfer()
        self.acquire(actor=self.u)
        self.acquire(TA.REFRESH, actor=self.u)
        self.communication(self.u)
        self.combat(self.u)
        self.rejected(lambda:TA.refresh(self.e, self.u, self.p, '불꽃', 'move/불대문자'), 'frequency')
        self.valid()

    def test_refresh_rejects_unknown_wrong_type_eot_and_late_restoration_without_payment(self):
        self.acquire()
        self.acquire(TA.REFRESH)
        for move in ('move/불대문자', 'move/냉동빔', 'move/화염방사'):
            self.e.gm.set_move(self.p, move, reason='actual known native Move')
        self.communication()
        self.combat(self.t)
        self.e.gm.observe_sensory_environment(self.t, self.p, paths={'auditory':False}, present=True,
            reason='actual inaudible Order cannot reach this Pokemon')
        self.rejected(lambda:TA.refresh(self.e, self.t, self.p, '불꽃', 'move/불대문자'),
            'hear|communicat|percei|auditory|Order|지시|청각|전달|감각|음성')
        self.communication()
        for move, pattern in (('move/열풍', 'known'), ('move/냉동빔', 'matching Scene'),
                              ('move/화염방사', 'matching Scene')):
            self.rejected(lambda move=move:TA.refresh(self.e, self.t, self.p, '불꽃', move), pattern)
        with patch.object(F, 'restore_scene_use', side_effect=ValueError('late native restoration failure')):
            self.rejected(lambda:TA.refresh(self.e, self.t, self.p, '불꽃', 'move/불대문자'), 'late native restoration')
        self.assertEqual(self.t.budget['standard'], 1)
        self.assertTrue(F.activation_allowed(self.p, TA.REFRESH, {'kind':'scene', 'uses':1}, engine=self.e))

    def test_sync_requires_three_actual_type_ace_instances_across_branches(self):
        self.acquire()
        self.rejected(lambda:self.acquire(TA.SYNC), 'three actual')
        self.acquire(TA.REFRESH)
        self.acquire(branch='물')
        self.acquire(TA.SYNC)
        self.assertEqual(len(TA.acquired(self.t, TA.SYNC, '불꽃')['snapshot']['features']), 3)

    def test_sync_spends_one_point_extended_and_actual_move_consumes_permanent_custom_effect(self):
        self.acquire()
        self.acquire(TA.REFRESH)
        self.acquire('Brightest Flame')
        self.acquire(TA.SYNC)
        self.e.gm.set_move(self.p, 'move/몸통박치기', add=False, reason='actual single-Move learner before Sync')
        self.e.gm.set_move(self.p, 'move/냉동빔', reason='actual known selected Move')
        before = self.e.elapsed_seconds
        row = TA.sync(self.e, self.t, self.p, '불꽃', seconds=60, **self.sync_decision())
        self.assertEqual((self.p.spec['tutor_points'], self.e.elapsed_seconds), (7, before + 60))
        self.assertEqual((row['synced_type'], row['synced_name']), ('불꽃', '화염광선'))
        self.restore()
        projected = EDGES.prepare(self.e, self.p, self.rules.move('move/냉동빔'))
        self.assertEqual((projected['type'], projected['name']), ('불꽃', '화염광선'))
        self.combat(self.p)
        with patch.object(Engine, 'd20', return_value=19):
            self.e.use_move_on(self.p, self.b, 'move/냉동빔', self.e.everyone, set_damage=True)
        self.assertIn('화상', self.b.conditions)
        self.assertNotIn('얼음', self.b.conditions)
        self.assertTrue(any('화염광선' in line for line in self.e.log_lines))
        self.e.end_encounter(self.e.everyone)
        self.rejected(lambda:TA.sync(self.e, self.t, self.p, '불꽃', seconds=60,
            **self.sync_decision('move/몸통박치기', 'second-sync')), 'forget the active')
        MOVES.observe_learning(self.e, self.p, 'move/10만볼트', method='tutor', source='feat/기술-가르침',
            paid_tp=2, replace='move/냉동빔', reason='observed replacement tutoring forgets the prior synced Move')
        self.assertEqual(SYNC.rows(self.p.spec)[0]['status'], 'forgotten')
        second = self.sync_decision('move/10만볼트', 'second-sync')
        second.update(new_name='화염볼트', effect_decision={'mode':'preserve',
            'reason':'The printed effect remains appropriate.', 'effects_exec':None})
        TA.sync(self.e, self.t, self.p, '불꽃', seconds=60, **second)
        self.assertEqual(self.p.spec['tutor_points'], 6)
        self.assertEqual(SYNC.active(self.rules, self.p.spec)['id'], 'second-sync')
        self.valid()

    def test_sync_unknown_move_no_points_and_invalid_effect_leave_time_and_points_unchanged(self):
        self.acquire()
        self.acquire(TA.REFRESH)
        self.acquire('Brightest Flame')
        self.acquire(TA.SYNC)
        decision = self.sync_decision()
        self.rejected(lambda:TA.sync(self.e, self.t, self.p, '불꽃', seconds=60, **decision), 'actually learned')
        self.e.gm.set_move(self.p, 'move/냉동빔', reason='actual known chosen Move')
        decision['effect_decision'] = {'mode':'replace', 'reason':'Structurally incompatible scripted effect.',
            'effects_exec':[{'type':'set_weather', 'weather':'쾌청', 'rounds':5}]}
        self.rejected(lambda:TA.sync(self.e, self.t, self.p, '불꽃', seconds=60, **decision), 'effect kind')
        self.p.spec['tutor_points'] = 0  # actual exhausted Tutor Points
        self.rejected(lambda:TA.sync(self.e, self.t, self.p, '불꽃', seconds=60, **self.sync_decision()), 'Tutor Points')

    def test_extra_ordinary_accepts_either_natural_normal_ability_and_grants_only_the_other_once(self):
        for natural, kind in (('마지막기회', 'last_chance'), ('타입전략가', 'strategist')):
            with self.subTest(natural=natural):
                self.setup(natural=natural)
                self.acquire(branch='노말')
                self.acquire('Extra Ordinary', '노말')
                self.assertEqual(TA.ability_branches(self.e, self.p, kind), {'노말'})
                before = self.e.elapsed_seconds
                TA.extra_ordinary(self.e, self.t, self.p, seconds=60, reason='actual completed Extra Ordinary')
                self.assertEqual(self.p.spec['tutor_points'], 8)
                self.assertEqual(self.e.elapsed_seconds, before + 60)
                for ability in ('last_chance', 'strategist'):
                    self.assertEqual(TA.ability_branches(self.e, self.p, ability), {'노말'})
                self.restore()
                self.rejected(lambda:TA.extra_ordinary(self.e, self.t, self.p,
                    seconds=60, reason='actual repeated attempt'), 'only once')
                self.valid()

    def test_extra_ordinary_requires_actual_normal_target_ability_and_preserves_teaching_once(self):
        self.acquire(branch='노말')
        self.acquire('Extra Ordinary', '노말')
        self.rejected(lambda:TA.extra_ordinary(self.e, self.t, self.p, seconds=60,
            reason='actual unqualified attempt'), 'Last Chance|Normal Strategist')
        self.teach('노말', 'strategist')
        FIELDS.base_patch(self.p, {'types':['불꽃']}, reason='actual target is no longer Normal')
        self.rejected(lambda:TA.extra_ordinary(self.e, self.t, self.p,
            seconds=60, reason='actual wrong target type'), 'Normal Pokemon')
        FIELDS.base_patch(self.p, {'types':['노말']}, reason='actual Normal target type')
        TA.extra_ordinary(self.e, self.t, self.p, seconds=60, reason='actual completed Extra Ordinary')
        self.assertEqual(self.p.spec['tutor_points'], 6)
        self.rejected(lambda:self.teach('노말', 'last_chance'), 'only once')
        self.valid()


if __name__ == '__main__':
    unittest.main()
