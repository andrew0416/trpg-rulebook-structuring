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
import state_grants as GRANTS
import world_entities as WORLD
import pokemon_party as PARTY
import trainer_retraining as RETRAIN
import trainer_xp_payments as XP
from native_scenario_fixture import assert_rejected_unchanged
import json


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

    def trainer(self, e, pos, *, feats=(), edges=(), choices=None, moves=(), items=None, type_links=None):
        return self.add(e, Combatant(self.rules, build_trainer(self.rules,
            'Source-backed acquired trainer', 30,
            {'hp':100, 'atk':15, 'def':15, 'spa':15, 'spd':15, 'spe':20},
            moves=list(moves), skills={'집중':7, '전투':4, '육상':3, '곡예':3},
            items=items or {}, extra={'classes':[], 'feats':list(feats),
                'edges':list(edges), 'edge_choices':choices or {}, 'exp_bank':100,
                'type_link_skills':type_links or {'불꽃':'집중'}})), pos)

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

    def before_pokemon_passive(self, uid):
        e = self.world()
        branch = TA.DEFINITIONS[uid]['branch']
        other = PASSIVE.GLACIAL_ICE if uid == PASSIVE.SHINING_FLAME else PASSIVE.SHINING_FLAME
        trainer = self.trainer(e, (1, 1), feats=[PASSIVE.CLAUSE_BY_RULE[other]],
            type_links={'불꽃':'집중', '얼음':'육상'})
        species = '눈꼬마' if uid == PASSIVE.GLACIAL_ICE else '염무왕'
        moves = [] if uid == PASSIVE.GLACIAL_ICE else ['move/불꽃세례']
        p = self.pokemon(e, species, (2, 2), owner=trainer, moves=moves)
        q = self.pokemon(e, species, (2, 4), owner=trainer, moves=moves)
        for feature in (TA.CLASS, TA.REFRESH):
            ACQUIRE.acquire_static(e, trainer, feature, branch=branch,
                acquisition_request_id='fire-passive/parent/' + feature)
        self.assertIsNone(PASSIVE._declaration(e, p, uid))
        self.assertIsNone(PASSIVE._declaration(e, q, uid))
        return e, trainer, p, q

    def acquire_pokemon_passive(self, e, trainer, uid):
        return ACQUIRE.acquire_static(e, trainer, uid,
            acquisition_request_id='fire-passive/acquire')

    def book_passive_declaration(self, e, trainer, pokemon, uid):
        declaration = PASSIVE._declaration(e, pokemon, uid)
        self.assertIsNotNone(declaration)
        owner, row, source = declaration
        self.assertIs(owner, trainer)
        self.assertEqual(row['owner_id'], trainer.entity_id)
        self.assertEqual(row['acquisition_source'], uid)
        native_clause, csv_clause = {
            PASSIVE.SHINING_FLAME: ('input/ch04-trainer-classes.md:1541-1544', 'C2CSV/input/db/feats.csv:R253:main'),
            PASSIVE.GLACIAL_ICE: ('input/ch04-trainer-classes.md:1677-1680', 'C2CSV/input/db/feats.csv:R273:main'),
        }[uid]
        self.assertEqual(row['native_clause_id'], native_clause)
        self.assertEqual(row['clause_id'], csv_clause)
        matches = [sid for sid, record in GRANTS.state(pokemon)['sources'].items()
                   if record.get('kind') == PASSIVE.KIND and record.get('rule_id') == uid]
        self.assertEqual(matches, [source])
        return row

    def passive_withdrawal_options(self, e, trainer, request, feature):
        sources = {uid: RETRAIN.owned_source(e, trainer, uid)
                   for uid in (TA.CLASS, TA.REFRESH, feature)}
        return dict(request_id=request, reason='actual source-specific Pokemon passive retraining',
            gm_decision={'allowed': True, 'reason': 'GM reviewed removal without replacing retained parents'},
            retained_dependencies={sources[TA.CLASS]: [], sources[TA.REFRESH]: [sources[TA.CLASS]]})

    def test_native_brightest_flame_projects_existing_late_and_foreign_owner_boundaries_once(self):
        for uid in (PASSIVE.SHINING_FLAME, PASSIVE.GLACIAL_ICE):
            with self.subTest(feature=uid):
                e, trainer, p, q = self.before_pokemon_passive(uid)
                other = self.trainer(e, (8, 8))
                foreign = self.pokemon(e, p.spec['species'], (8, 7), owner=other, moves=[])
                with patch.object(Engine, 'register_abilities', side_effect=AssertionError('acquisition must not replay enter')):
                    receipt = self.acquire_pokemon_passive(e, trainer, uid)
                for pokemon in (p, q):
                    self.book_passive_declaration(e, trainer, pokemon, uid)
                self.assertIsNone(PASSIVE._declaration(e, foreign, uid))
                late = self.pokemon(e, p.spec['species'], (4, 4), owner=trainer, moves=[])
                self.book_passive_declaration(e, trainer, late, uid)
                before = e.export_state()
                with patch.object(Engine, 'register_abilities', side_effect=AssertionError('projection must not replay enter')):
                    for _ in range(2):
                        for pokemon in (p, q, late):
                            PARTY.project_current_owner(e, pokemon)
                self.assertEqual(e.export_state(), before)
                self.assertEqual(self.acquire_pokemon_passive(e, trainer, uid), receipt)
                self.assertEqual(e.export_state(), before)

    def test_native_brightest_flame_restore_and_paid_withdrawal_preserve_csv_and_completed_attack(self):
        for uid in (PASSIVE.SHINING_FLAME, PASSIVE.GLACIAL_ICE):
            with self.subTest(feature=uid):
                e, trainer, p, q = self.before_pokemon_passive(uid)
                self.acquire_pokemon_passive(e, trainer, uid)
                csv_source = PASSIVE.CLAUSE_BY_RULE[uid]
                csv_owner = self.trainer(e, (8, 8), feats=[csv_source], type_links={'불꽃':'집중', '얼음':'육상'})
                csv_pokemon = self.pokemon(e, p.spec['species'], (8, 7), owner=csv_owner, moves=[])
                csv_row = PASSIVE._declaration(e, csv_pokemon, uid)[1]
                self.assertEqual(csv_row['acquisition_source'], csv_source)
                self.assertNotIn('native_clause_id', csv_row)
                ice = uid == PASSIVE.GLACIAL_ICE
                target = self.pokemon(e, '염무왕' if ice else '꼬부기', (5, 2), side='foe',
                    moves=['move/불꽃세례'] if ice else ['move/몸통박치기'])
                attacker, victim = (target, p) if ice else (p, target)
                if ice:
                    self.assertEqual(PASSIVE.damage_reduction(e, attacker, victim, self.rules.move('move/불꽃세례'), 2, False), 3)
                self.begin(e, attacker)
                self.attack(e, attacker, victim, 'move/불꽃세례', 19 if ice else 18)
                self.assertIn('화상', victim.conditions)
                e.end_of_turn(attacker)
                ids = [actor.entity_id for actor in (trainer, p, q, csv_owner, csv_pokemon, target)]
                e = Engine.import_state(self.rules, json.loads(json.dumps(e.export_state(), ensure_ascii=False)))
                trainer, p, q, csv_owner, csv_pokemon, target = [WORLD.actor_index(e)[uid] for uid in ids]
                for pokemon in (p, q):
                    self.book_passive_declaration(e, trainer, pokemon, uid)
                attacker, victim = (target, p) if ice else (p, target)
                history = deepcopy(HISTORY.records(victim), GRANTS._transition_token_anchors(e))
                uses = deepcopy(attacker.move_uses)
                branch = TA.DEFINITIONS[uid]['branch']
                parents = {parent: deepcopy(TA.acquired(trainer, parent, branch)) for parent in (TA.CLASS, TA.REFRESH)}
                other = PASSIVE.GLACIAL_ICE if uid == PASSIVE.SHINING_FLAME else PASSIVE.SHINING_FLAME
                unrelated = {pokemon.entity_id: deepcopy(PASSIVE._declaration(e, pokemon, other)[1])
                             for pokemon in (p, q)}
                options = self.passive_withdrawal_options(e, trainer, 'fire-passive/withdraw', uid)
                saved = e.gm.snapshot('fire-passive-before-withdrawal')
                bank = trainer.spec['exp_bank']
                result = e.retrain_trainer_source(trainer, uid, **options)
                self.assertEqual(trainer.spec['exp_bank'], bank-result['xp_paid'])
                self.assertIsNone(TA.acquired(trainer, uid))
                for pokemon in (p, q):
                    self.assertIsNone(PASSIVE._declaration(e, pokemon, uid))
                    PARTY.project_current_owner(e, pokemon)
                    self.assertIsNone(PASSIVE._declaration(e, pokemon, uid))
                for pokemon in (p, q):
                    self.assertEqual(PASSIVE._declaration(e, pokemon, other)[1], unrelated[pokemon.entity_id])
                    self.assertEqual(unrelated[pokemon.entity_id]['acquisition_source'], PASSIVE.CLAUSE_BY_RULE[other])
                self.assertEqual(PASSIVE._declaration(e, csv_pokemon, uid)[1]['acquisition_source'], csv_source)
                self.assertIn('화상', victim.conditions)
                self.assertEqual(HISTORY.records(victim), history)
                self.assertEqual(attacker.move_uses, uses)
                if ice:
                    self.assertEqual(PASSIVE.damage_reduction(e, attacker, victim, self.rules.move('move/불꽃세례'), 2, False), 0)
                self.assertEqual({parent: TA.acquired(trainer, parent, branch) for parent in parents}, parents)
                before = e.export_state()
                self.assertEqual(e.retrain_trainer_source(trainer, uid, **options), result)
                self.assertEqual(e.export_state(), before)
                e.gm.restore(saved)
                for pokemon in (p, q):
                    self.book_passive_declaration(e, trainer, pokemon, uid)
                self.assertIn('화상', victim.conditions)
                self.assertTrue(e.validate_state()['valid'])

    def test_native_brightest_flame_late_acquisition_projection_failure_is_atomic(self):
        for uid in (PASSIVE.SHINING_FLAME, PASSIVE.GLACIAL_ICE):
            with self.subTest(feature=uid):
                e, trainer, p, q = self.before_pokemon_passive(uid)
                actual = PASSIVE.register_all
                wanted = {p.entity_id, q.entity_id}
                installed = []
                def reject_after_projection(staged, pokemon):
                    result = actual(staged, pokemon)
                    if pokemon.entity_id in wanted and pokemon.entity_id not in installed:
                        self.assertIsNotNone(PASSIVE._declaration(staged, pokemon, uid))
                        installed.append(pokemon.entity_id)
                        if len(installed) == 2:
                            raise ValueError('late Pokemon passive projection rejected')
                    return result
                with patch.object(PASSIVE, 'register_all', reject_after_projection):
                    assert_rejected_unchanged(e, lambda: self.acquire_pokemon_passive(e, trainer, uid),
                        reason_pattern='late Pokemon passive projection rejected')
                self.assertEqual(set(installed), wanted)
                self.assertIsNone(TA.acquired(trainer, uid))
                for pokemon in (p, q):
                    self.assertIsNone(PASSIVE._declaration(e, pokemon, uid))
                self.acquire_pokemon_passive(e, trainer, uid)
                for pokemon in (p, q):
                    self.book_passive_declaration(e, trainer, pokemon, uid)

    def test_native_brightest_flame_late_paid_withdrawal_failure_restores_every_owner_projection(self):
        for uid in (PASSIVE.SHINING_FLAME, PASSIVE.GLACIAL_ICE):
            with self.subTest(feature=uid):
                e, trainer, p, q = self.before_pokemon_passive(uid)
                self.acquire_pokemon_passive(e, trainer, uid)
                options = self.passive_withdrawal_options(e, trainer, 'fire-passive/failed-withdrawal', uid)
                actual = XP.mark_used
                observed = []
                def reject_after_used(staged, owner, request_id, *, event_id):
                    result = actual(staged, owner, request_id, event_id=event_id)
                    if request_id == options['request_id']:
                        self.assertIsNone(TA.acquired(owner, uid))
                        for pokemon_id in (p.entity_id, q.entity_id):
                            self.assertIsNone(PASSIVE._declaration(staged, WORLD.actor_index(staged)[pokemon_id], uid))
                        observed.append(owner.spec['exp_bank'])
                        raise ValueError('late Pokemon passive withdrawal rejected')
                    return result
                with patch.object(XP, 'mark_used', reject_after_used):
                    assert_rejected_unchanged(e,
                        lambda: e.retrain_trainer_source(trainer, uid, **options),
                        reason_pattern='late Pokemon passive withdrawal rejected')
                self.assertEqual(len(observed), 1)
                for pokemon in (p, q):
                    self.book_passive_declaration(e, trainer, pokemon, uid)
                bank = trainer.spec['exp_bank']
                result = e.retrain_trainer_source(trainer, uid, **options)
                self.assertEqual(trainer.spec['exp_bank'], bank-result['xp_paid'])
                for pokemon in (p, q):
                    self.assertIsNone(PASSIVE._declaration(e, pokemon, uid))

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
