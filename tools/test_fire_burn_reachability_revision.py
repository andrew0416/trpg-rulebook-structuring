"""S-p2cfe-3: sourced Burn-range witnesses through ordinary native Move use.

The imported Firebringer sheet records its two printed choices and prerequisites;
it does not claim native character creation. Type Ace and TM teaching below use
their paid native entries. No trainer receives a Pokemon Move Sync permission.
"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import os
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE if (STAGE / 'data/core-rules.json').is_file() else Path(os.environ.get(
    'PTK_CANONICAL_ROOT', r'D:/trpg-rulebook-structuring/work/public-actions-20261023/repository'))
sys.path[:0] = [str(STAGE / 'engine'), str(ROOT / 'engine'),
                str(STAGE / 'tools'), str(ROOT / 'tools')]
from engine import Combatant, Engine, Rules
from builder import build_pokemon, build_trainer
from grid import Grid
from native_scenario_fixture import prepare_body
import attack_damage_history as HISTORY
import class_passive_combat as PASSIVE
import move_state as MOVES
import move_type_sync as SYNC
import pokemon_move_edges as EDGES
import pokemon_teaching as TEACH
import trainer_feature_acquisition as ACQUIRE
import type_ace as TA


class FireBurnReachabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='fantasy')

    def setUp(self):
        prior = self.rules.rulings
        self.rules.rulings = deepcopy(prior)
        self.addCleanup(setattr, self.rules, 'rulings', prior)
        self.rules.rulings.set_mech('gameplay/skill-rank-dice', 'by_rank_name.초월',
            {'rank':7, 'dice':'7d6', 'eng':'Transcendent'}, scope='campaign',
            reason='This campaign explicitly declares the actual Focus7 rank before sheet creation',
            rules=self.rules)

    def world(self):
        e = Engine(self.rules, seed=253624)
        e.grid = Grid(16, 12)
        return e

    def add(self, e, actor, pos, side='party'):
        e.gm.add_combatant(actor, pos=pos, side=side,
            reason='source-backed imported sheet in the actual encounter')
        prepare_body(e, actor, size=actor.spec['size'], offsets=[(0, 0)],
            reason='observed complete body for the actual participant')
        return actor

    def pokemon(self, e, species, pos, *, moves, owner=None, side='party', level=60):
        extra = {} if owner is None else {'trainer_id':owner.entity_id, 'tutor_points':8}
        actor = self.add(e, Combatant(self.rules, build_pokemon(self.rules, species,
            level, moves=moves, abilities=[], side=side, extra=extra)), pos, side)
        if owner is not None:
            e.gm.observe_loyalty(actor, 6, reason='actual willing owned Pokemon')
        return actor

    def trainer(self, e, pos, *, feats=(), edges=(), choices=None, moves=(), items=None):
        return self.add(e, Combatant(self.rules, build_trainer(self.rules,
            'Source-backed acquired trainer', 30,
            {'hp':100, 'atk':15, 'def':15, 'spa':15, 'spd':15, 'spe':20},
            moves=list(moves), skills={'집중':7, '전투':4, '육상':3, '곡예':3},
            items=items or {}, extra={'classes':[], 'feats':list(feats),
                'edges':list(edges), 'edge_choices':choices or {}, 'exp_bank':100,
                'type_link_skills':{'불꽃':'집중'}})), pos)

    def begin(self, e, actor):
        e.begin_encounter(e.everyone)
        e.start_round(e.everyone)
        e.start_of_turn(actor, initiative_count=30)
        e.enable_execution_trace()

    def attack(self, e, actor, target, mid, face):
        before = target.hp
        with patch.object(Engine, 'd20', return_value=face):
            e.use_move_on(actor, target, mid, e.everyone, set_damage=True)
        self.assertLess(target.hp, before, '\n'.join(e.log_lines[-30:]))
        self.assertEqual(actor.budget['standard'], 0)
        calculations = [calc for row in e.execution_traces()
            if row['kind'] == 'damage_calculation'
            for calc in row['calculations'] if 'damage_type' in calc]
        self.assertTrue(calculations)
        self.assertTrue(e.validate_state()['valid'])
        return calculations[-1]['damage_type']

    def emboar_scald(self, *, sync):
        e = self.world()
        trainer = self.trainer(e, (1, 1), items={'TM55':1})
        p = self.pokemon(e, '염무왕', (2, 2), owner=trainer, moves=['move/불꽃세례'])
        self.pokemon(e, '염무왕', (2, 4), owner=trainer, moves=['move/불꽃세례'])
        target = self.pokemon(e, '꼬부기', (5, 2), side='foe', moves=['move/몸통박치기'])
        self.assertEqual(p.types, ['불꽃', '격투'])
        self.assertNotIn('move/열탕', p.moves)
        self.assertIn('55 열탕', self.rules.learnsets['염무왕']['tm'])
        TEACH.register_machine(e, trainer, instance_id='actual-scald-tm', code='TM55')
        taught = TEACH.teach_machine(e, trainer, target=p, instance_id='actual-scald-tm')
        self.assertEqual((taught['point_cost'], p.spec['tutor_points'], e.elapsed_seconds),
                         (1, 7, 3600))
        self.assertEqual((trainer.spec['items']['TM55'],
            trainer.spec['teaching_machines']['actual-scald-tm']['status']), (0, 'consumed'))
        self.assertEqual(p.spec['move_learning']['move/열탕']['method'], 'tm')
        self.assertEqual(p.spec['move_learning']['move/열탕']['machine'], 'TM55')
        self.assertEqual(MOVES.describe(self.rules, p.spec)['classifications']['move/열탕'], 'taught')
        for feature in (TA.CLASS, TA.REFRESH, TA.uid('Brightest Flame'), TA.SYNC):
            options = {'branch':'불꽃'} if feature in (TA.CLASS, TA.REFRESH, TA.SYNC) else {}
            ACQUIRE.acquire_static(e, trainer, feature,
                acquisition_request_id='burn-range/' + feature, **options)
        self.assertEqual(TA.acquired(trainer, TA.CLASS, '불꽃')['snapshot']['rank'], 7)
        self.assertIs(PASSIVE._declaration(e, p, PASSIVE.SHINING_FLAME)[0], trainer)
        printed = deepcopy(self.rules.move('move/열탕'))
        if sync:
            row = TA.sync(e, trainer, p, '불꽃', seconds=60,
                application_id='actual-fire-scald', move_id='move/열탕', new_name='화염탕',
                effect_decision={'mode':'preserve', 'effects_exec':None,
                    'reason':'The learned Scald Burn rider remains appropriate for this Fire expression.'},
                feasibility_review='The printed range, AC, class and target count remain unchanged.',
                power_review='Damage base and Burn threshold remain printed; only type and name change.',
                reason='Actual extended Move Sync with its acquired Fire Type Ace prerequisites')
            self.assertEqual((row['synced_type'], p.spec['tutor_points'], e.elapsed_seconds),
                             ('불꽃', 6, 3660))
            self.assertEqual(SYNC.active(self.rules, p.spec)['id'], 'actual-fire-scald')
        projected = EDGES.prepare(e, p, self.rules.move('move/열탕'))
        self.assertEqual(projected['type'], '불꽃' if sync else '물')
        self.assertEqual(self.rules.move('move/열탕'), printed)
        self.assertEqual(printed['type'], '물')
        self.begin(e, p)
        return e, p, target

    def test_r253_actual_fire_emboar_learns_scald_pays_sync_and_reaches_plus3_boundary(self):
        for synced, face, burns in ((False, 12, False), (True, 11, False), (True, 12, True)):
            with self.subTest(synced=synced, face=face):
                e, p, target = self.emboar_scald(sync=synced)
                actual = self.attack(e, p, target, 'move/열탕', face)
                self.assertEqual(actual, '불꽃' if synced else '물')
                self.assertEqual(HISTORY.last_damage(target)['move_type'], actual)
                self.assertEqual('화상' in target.conditions, burns)

    def firebringer(self, *, electrify):
        e = self.world()
        trainer = self.trainer(e, (2, 2), feats=['화염인도자', PASSIVE.BURNING_BRAND],
            edges=['edge/원소-교감'], choices={'edge/원소-교감':['불꽃']},
            moves=['move/화염바퀴', 'move/도깨비불'])
        target = self.pokemon(e, '꼬부기', (3, 2), side='foe', moves=['move/몸통박치기'])
        # The same actual acquired Firebringer choices own both comparison cases.
        self.assertEqual(self.rules._selected_rule(PASSIVE.BURNING_BRAND), PASSIVE.BURNING_BRAND)
        self.assertTrue(PASSIVE.owns(trainer, PASSIVE.BURNING_BRAND))
        self.assertIs(PASSIVE._declaration(e, trainer, PASSIVE.BURNING_BRAND)[0], trainer)
        self.assertIn('move/화염바퀴', trainer.moves)
        self.assertEqual(trainer._state_origin['kind'], 'sheet_import')
        self.assertFalse(trainer._state_origin['creation_legality_certified'])
        if electrify:
            caster = self.pokemon(e, '목도리키텔', (5, 2), side='foe',
                moves=['move/송전'], level=45)
            self.assertIn('move/송전', MOVES.natural_moves(self.rules, caster.spec))
            self.begin(e, caster)
            e.use_move_on(caster, trainer, 'move/송전', e.everyone)
            self.assertEqual(caster.budget['standard'], 0)
            self.assertTrue(any(row.get('type') == 'type_override_moves'
                and row.get('as_type') == '전기' for row in trainer.registry))
            self.assertFalse(any(row.get('type') == 'type_override_moves' for row in target.registry))
            e.end_of_turn(caster)
            # Same round, before the caster's next turn ends: the printed duration is live.
            e.start_of_turn(trainer, initiative_count=20)
        else:
            self.begin(e, trainer)
        return e, trainer, target

    def test_r624_firebringer_flame_wheel_has_plus2_burn_boundary(self):
        for face, burns in ((16, False), (17, True)):
            with self.subTest(face=face):
                e, trainer, target = self.firebringer(electrify=False)
                self.assertEqual(self.attack(e, trainer, target, 'move/화염바퀴', face), '불꽃')
                self.assertEqual('화상' in target.conditions, burns)

    def test_r624_native_electrify_suppresses_fire_plus2_but_keeps_printed_burn19(self):
        for face, burns in ((17, False), (19, True)):
            with self.subTest(face=face):
                e, trainer, target = self.firebringer(electrify=True)
                self.assertEqual(self.rules.move('move/화염바퀴')['type'], '불꽃')
                self.assertEqual(self.attack(e, trainer, target, 'move/화염바퀴', face), '전기')
                self.assertEqual(HISTORY.last_damage(target)['move_type'], '전기')
                self.assertEqual('화상' in target.conditions, burns)


if __name__ == '__main__':
    unittest.main()
