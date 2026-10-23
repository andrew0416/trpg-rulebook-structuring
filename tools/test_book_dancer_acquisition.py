"""Dancer class (ch04:2266-2323): actual static acquisition of the class Ability choice and the five Features,
Dance Form creation of fixed Dance Moves, the Beguiling Dance template and the existing Dance Practice owner."""
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
from builder import build_pokemon
from native_scenario_fixture import prepare_body, assert_rejected_unchanged
import dancer as D
import trainer_feature_acquisition as TFA
import acquired_features as ACQUIRED
import action_points as AP
import frequency as FREQ
import state_codec as CODEC
import state_grants as G
import trainer_retraining as RETRAINING
import world_entities as WORLD

COMMON = dict(level=30, size='중형', stats={'hp': 100, 'atk': 20, 'def': 20, 'spa': 20, 'spd': 20, 'spe': 20}, abilities=[], types=['노말'],
              movement={'land': 6, 'swim': 0, 'sky': 0, 'power': 4}, weight_kg=30,
              skills={'곡예': 6, '육상': 6, '매력': 6, '명령': 4, '통찰': 4})
ALL_FEATURES = (D.DANCE_FORM, D.BEGUILING, D.PRACTICE, D.CHOREOGRAPHER, D.PIROUETTE, D.WALTZ)


class DancerAcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)
        self.e = Engine(self.rules, seed=20862128)
        self.e.grid = Grid(14, 12)
        self.t = self.add('actual Dancer', 'trainer', (1, 1), classes=[], feats=[], edges=[], items={}, money=100, moves=[], speed=30, exp_bank=50)

    # ------------------------------------------------------------ fixture helpers (shared by the other Dancer modules)
    def add(self, name, kind, pos, speed=None, side='party', **extra):
        spec = dict(deepcopy(COMMON), name=name, kind=kind)
        if speed is not None:
            spec['stats'] = dict(spec['stats'], spe=speed)   # distinct Speeds keep initiative schedules tie-free
        spec.update(extra)
        actor = Combatant(self.rules, spec)
        self.e.gm.add_combatant(actor, pos=pos, side=side, reason='actual Dancer scene participant')
        prepare_body(self.e, actor, size='중형', offsets=[(0, 0)], reason='observed complete body')
        if kind == 'pokemon' and extra.get('trainer_id'):
            self.e.gm.observe_loyalty(actor, 6, reason='actual willing Pokemon')
            self.e.register_abilities(actor)
        return actor

    def acquire(self, feature, branch=None, request=None, trainer=None):
        trainer = self.t if trainer is None else trainer
        return TFA.acquire_static(self.e, trainer, feature, branch=branch,
                                  acquisition_request_id=request or 'dancer/' + feature + ('/' + branch if branch else ''))

    def dancer(self, *features, ability='회전춤', trainer=None):
        """Acquire the class with its printed Ability choice, Dance Form and the listed Features in printed order."""
        self.acquire(D.CLASS, branch=ability, trainer=trainer)
        for feature in (D.DANCE_FORM, *[f for f in ALL_FEATURES if f in features and f != D.DANCE_FORM]):
            self.acquire(feature, trainer=trainer)

    def create(self, name, stages=None, contest_type='근사함', **options):
        return D.create_dance_move(self.e, self.t, name=name, stages=stages, contest_type=contest_type,
                                   reason='actual player choice at creation', **options)

    def rejected(self, operation, pattern):
        return assert_rejected_unchanged(self.e, operation, reason_pattern=pattern)

    def valid(self):
        report = self.e.validate_state()
        self.assertTrue(report['valid'], report['issues'])
        return report

    def invalid(self, pattern):
        report = self.e.validate_state()
        self.assertFalse(report['valid'])
        self.assertTrue(any(pattern in issue['message'] for issue in report['issues']), report['issues'])

    def restore(self, *names):
        identities = {name: getattr(self, name).entity_id for name in names}
        self.e = CODEC.load_engine(self.rules, json.loads(json.dumps(self.e.export_state(), ensure_ascii=False)))
        actors = WORLD.actor_index(self.e)
        for name, identity in identities.items():
            setattr(self, name, actors[identity])
        self.valid()

    def combat(self, actor, *, count=30):
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor, initiative_count=count)

    def next_turn(self, actor, *, count=30):
        if self.e._active_turn_actor is None:   # a codec-restored engine resumes at a fresh round
            return self.combat(actor, count=count)
        self.e.end_of_turn(self.e._active_turn_actor)
        self.e.end_round()
        self.combat(actor, count=count)

    def use(self, actor, target, move, *, face=10, **options):
        if move not in actor.moves:
            self.e.gm.set_move(actor, move, reason='actual complete known Move list')
        with patch.object(Engine, 'd20', return_value=face):
            return self.e.use_move_on(actor, target, move, self.e.everyone, **options)

    def answer(self, key, value):
        self.e.rulings.answers = [row for row in self.e.rulings.answers if row['key'] != key]
        self.e.rulings.add_answer(key, value, reason='explicit player choice', scope='permanent')

    def retrain(self, feature, trainer=None):
        trainer = self.t if trainer is None else trainer
        sources = {owned: RETRAINING.owned_source(self.e, trainer, owned) for owned in RETRAINING._owned(trainer)}
        retained = {source: list(trainer.spec['state_grants']['sources'][source].get('withdrawal_dependencies', []))
                    for owned, source in sources.items() if owned != feature}
        for child, parents in RETRAINING._native_dependencies(self.e, trainer, RETRAINING._owned(trainer)).items():
            if child != feature:
                retained[sources[child]] = [sources[parent] for parent in parents]
        return self.e.retrain_trainer_source(trainer, feature, request_id='retrain/' + feature, reason='actual trainer chooses retraining',
                                             gm_decision={'allowed': True, 'reason': 'GM reviewed prerequisites and narrative'},
                                             retained_dependencies=retained)

    # ------------------------------------------------------------ C04-096 class row and template
    def test_template_binds_six_definitions_and_class_acquisition_grants_only_the_chosen_ability(self):
        self.assertEqual(set(D.STATIC_DEFINITIONS), {D.CLASS, *ALL_FEATURES})
        for feature, row in D.STATIC_DEFINITIONS.items():
            static = TFA.STATIC_FEATURES[feature]
            self.assertEqual((static['clause_id'], static['class_template'], static.get('branch', False)), (row['clause_id'], D.CLASS, feature == D.CLASS))
            self.assertEqual(static['catalog_span'], list(self.rules.selection.units[feature]['source']['lines']))
        self.assertEqual(TFA.STATIC_FEATURES[D.CLASS]['clause_id'], 'C04-096')
        self.assertNotIn('interpretation', TFA._static_source(self.rules, D.CLASS))   # printed Korean choice, no English precedence
        self.rejected(lambda: self.acquire(D.CLASS, branch='무희'), 'printed Ability choice')
        self.rejected(lambda: self.acquire(D.CLASS), 'printed Ability choice')
        receipt = self.acquire(D.CLASS, branch='마이페이스')
        self.assertEqual((receipt['status'], receipt['snapshot']['branch'], self.t.abilities, D.chosen_ability(self.t)), ('acquired', '마이페이스', ['마이페이스'], '마이페이스'))
        self.assertEqual(self.t.spec['feats'], [D.CLASS])
        self.assertEqual(len(ACQUIRED.class_instances(self.t)), 1)
        row = self.t.spec['state_grants']['sources'][D.class_source_id(self.t, '마이페이스')]
        self.assertEqual((row['grants']['abilities'], row['rule_id'], row['lifetime'], row['dancer_class']['clause_id']), (['마이페이스'], D.CLASS, 'while_owned', 'C04-096'))
        self.assertTrue(self.e.immune_to(self.t, '혼란'))   # the chosen Ability is live on the trainer
        self.assertEqual(self.acquire(D.CLASS, branch='마이페이스')['status'], 'acquired')   # idempotent replay of the same request
        self.rejected(lambda: self.acquire(D.CLASS, branch='회전춤', request='dancer/second'), 'already acquired')
        self.assertFalse(any(f in self.t.spec['feats'] for f in ALL_FEATURES))   # the class never auto-grants its Features
        self.assertIsNone(D.state(self.t)['last_dance'])
        self.assertEqual((self.t.stats['spe'], D.stat_tag_operation(self.t, D.CLASS)), (31, {'delta': 1, 'minimum': None}))   # printed [+스피드] on the fixture's base Speed 30
        self.valid()

    def test_class_prerequisites_require_novice_acrobatics_and_novice_athletics_or_charm_before_any_receipt(self):
        self.t.spec['skills'].update({'곡예': 2, '육상': 6, '매력': 6})
        self.rejected(lambda: self.acquire(D.CLASS, branch='회전춤'), 'Novice Acrobatics')
        self.t.spec['skills'].update({'곡예': 3, '육상': 2, '매력': 2})
        self.rejected(lambda: self.acquire(D.CLASS, branch='회전춤'), 'Athletics or Charm')
        self.t.spec['skills']['매력'] = 3
        self.rejected(lambda: self.acquire(D.DANCE_FORM), 'Dancer prerequisite')
        receipt = self.acquire(D.CLASS, branch='회전춤')
        self.assertEqual(receipt['snapshot']['ranks'], {'곡예': 3, '육상': 2, '매력': 3})
        self.assertEqual(self.t.abilities, ['회전춤'])
        self.valid()

    def test_feature_prerequisites_follow_parents_and_printed_skill_ranks_and_are_revalidated_on_use(self):
        self.acquire(D.CLASS, branch='회전춤')
        self.rejected(lambda: self.acquire(D.BEGUILING), 'Dancer prerequisite')
        self.rejected(lambda: self.acquire(D.CHOREOGRAPHER), 'Dancer prerequisite')
        self.acquire(D.DANCE_FORM)
        self.t.spec['skills'].update({'곡예': 3, '육상': 3, '매력': 3})
        for feature, rank in ((D.CHOREOGRAPHER, 4), (D.PIROUETTE, 5), (D.WALTZ, 6)):
            self.rejected(lambda feature=feature: self.acquire(feature), 'printed skill rank')
            self.t.spec['skills']['매력'] = rank
            receipt = self.acquire(feature)
            self.assertEqual(receipt['snapshot']['ranks']['매력'], rank)
            self.t.spec['skills']['매력'] = 3
        self.acquire(D.BEGUILING)
        self.assertEqual(self.t.spec['feats'], [D.CLASS, D.DANCE_FORM, D.CHOREOGRAPHER, D.PIROUETTE, D.WALTZ, D.BEGUILING])
        self.assertEqual(self.t.stats['spe'], 36)   # base 30 + class + five Features, each printed [+스피드]
        self.assertTrue(all(D.stat_tag_operation(self.t, f) == {'delta': 1, 'minimum': None} for f in (D.DANCE_FORM, D.CHOREOGRAPHER, D.PIROUETTE, D.WALTZ, D.BEGUILING)))
        self.valid()
        self.acquire(D.PRACTICE)
        self.assertEqual((self.t.stats['spe'], D.stat_tag_operation(self.t, D.PRACTICE)), (37, None))   # Dance Practice keeps its static table tag (+1 from the existing feature_count source)
        self.valid()
        key = 'feature:' + self.t.entity_id + ':' + D.WALTZ
        removed = self.t.spec['state_grants']['stat_sources']['spe']['sources'].pop(key)
        self.invalid('acquisition tag')
        self.t.spec['state_grants']['stat_sources']['spe']['sources'][key] = removed
        self.valid()
        # Use-time qualification re-reads the actual sheet: parents and one printed skill rank.
        self.rejected(lambda: D.qualify(self.e, self.t, D.WALTZ), 'printed skill rank')
        self.t.spec['skills']['육상'] = 6
        self.assertEqual(D.qualify(self.e, self.t, D.WALTZ)['english'], 'Passing Waltz')
        other = self.add('class only', 'trainer', (6, 6), classes=[], feats=[], edges=[], items={}, money=100, moves=[], speed=29, exp_bank=50)
        self.acquire(D.CLASS, branch='마이페이스', trainer=other)
        self.rejected(lambda: D.qualify(self.e, other, D.DANCE_FORM), 'Dance Form required')
        self.rejected(lambda: D.qualify(self.e, other, D.WALTZ), 'Passing Waltz required')
        self.valid()

    # ------------------------------------------------------------ Dance Form and the Dance Move template
    def test_dance_form_creates_fixed_dance_moves_within_two_plus_one_per_other_dancer_feature(self):
        self.dancer()
        self.assertEqual(D.allowance(self.t), 2)
        first = self.create('불꽃왈츠', {'atk': 1, 'spe': 1}, '근사함')
        second = self.create('달빛탱고', {'spa': 2}, '아름다움')
        self.rejected(lambda: self.create('셋째춤', {'def': 2}, '강인함'), 'allows 2 Dance Moves')
        self.assertEqual([row['id'] for row in D.created_moves(self.t)], [first['id'], second['id']])
        self.assertEqual(self.t.moves, [first['id'], second['id']])
        self.assertEqual(self.t.spec['state_grants']['sources'][first['source_id']]['grants']['moves'], [first['id'], second['id']])
        self.assertEqual(first['source_id'], 'feature:' + self.t.entity_id + ':' + D.DANCE_FORM)
        move = self.rules.move(first['id'])
        self.assertEqual({k: move[k] for k in ('name', 'type', 'class', 'ac', 'frequency', 'range', 'contest')},
                         {'name': '불꽃왈츠', 'type': '노말', 'class': '변화', 'ac': None, 'frequency': '턴1회', 'range': '자신', 'contest': '근사함 - 준비하기!'})
        self.assertEqual(self.rules.move_mech(first['id'])[0]['effects_exec'],
                         [{'type': 'stage_change', 'stat': 'atk', 'delta': 1, 'target': 'self', '_src': 'dancer:불꽃왈츠'},
                          {'type': 'stage_change', 'stat': 'spe', 'delta': 1, 'target': 'self', '_src': 'dancer:불꽃왈츠'}])
        self.assertEqual(FREQ.move_frequency(self.e, first['id'], self.t), ('every_other_turn', 1))
        self.assertEqual(self.rules.move(second['id'])['contest'], '아름다움 - 준비하기!')
        self.assertEqual(self.rules.move_id(first['id']), first['id'])
        self.assertEqual(self.rules.move_id('불꽃왈츠'), None)   # the name alone is not a global move
        # The identity carries the choices; it cannot be edited afterwards.
        self.assertEqual(D.dance_instance(self.rules, first['id']), {'trainer_id': self.t.entity_id, 'name': '불꽃왈츠', 'template': 'form',
                                                                     'stages': {'atk': 1, 'spe': 1}, 'contest_type': '근사함', 'lowered': None})
        forged = D.dance_move_id(dict(D.dance_instance(self.rules, first['id']), stages={'atk': 2}))
        self.assertNotEqual(forged, first['id'])
        with self.assertRaises(ValueError):
            D.dance_instance(self.rules, first['id'][:-4] + 'AAAA')
        with self.assertRaises(ValueError):
            self.rules.move(D.DANCE_PREFIX + 'bad')
        self.assertTrue(all(D.is_dance_move(self.rules, mid) for mid in ('move/용의춤', 'move/나비춤', 'move/칼춤', first['id'])))
        self.assertFalse(D.is_dance_move(self.rules, 'move/흔들흔들댄스'))
        # Every other Dancer Feature adds one Dance Move, also when gained later.
        self.acquire(D.PIROUETTE)
        self.assertEqual(D.allowance(self.t), 3)
        third = self.create('바람의춤', {'def': 1, 'spd': 1}, '슬기로움')
        self.assertEqual(third['allowance'], 3)
        self.assertEqual(third['other_features'], [D.PIROUETTE])
        self.rejected(lambda: self.create('넷째춤', {'def': 2}, '강인함'), 'allows 3 Dance Moves')
        for feature in (D.BEGUILING, D.PRACTICE, D.CHOREOGRAPHER, D.WALTZ):
            self.acquire(feature)
        self.assertEqual(D.allowance(self.t), 7)
        self.valid()

    def test_beguiling_dance_template_lowers_one_chosen_stat_at_range_four_ac_three_with_excitement(self):
        self.dancer(D.BEGUILING)
        record = self.create('기만의탱고', template='beguiling', lowered='def', contest_type='강인함')
        move = self.rules.move(record['id'])
        self.assertEqual({k: move[k] for k in ('type', 'class', 'ac', 'frequency', 'range', 'contest')},
                         {'type': '노말', 'class': '변화', 'ac': 3, 'frequency': '턴1회', 'range': '4, 대상 1', 'contest': '강인함 - 고조'})
        self.assertEqual(self.rules.move_mech(record['id'])[0]['effects_exec'],
                         [{'type': 'stage_change', 'stat': 'def', 'delta': -2, 'target': 'target', '_src': 'dancer:기만의탱고'}])
        self.assertEqual(record['other_features'], [D.BEGUILING])
        self.assertEqual(record['clause_id'], 'input/ch04-trainer-classes.md:2288-2292')
        self.rejected(lambda: self.create('둘째', template='beguiling', lowered='def', contest_type='근사함'), 'contest type must match')
        self.rejected(lambda: self.create('둘째', template='beguiling', lowered='hp', contest_type='강인함'), 'lowers exactly one chosen combat stat')
        self.rejected(lambda: self.create('둘째', {'atk': 2}, template='beguiling', lowered='def', contest_type='강인함'), 'lowers exactly one chosen combat stat')
        ordinary = self.create('둘째춤', {'spe': 2}, '귀여움')
        self.assertEqual(self.rules.move(ordinary['id'])['contest'], '귀여움 - 준비하기!')
        self.valid()

    def test_dance_move_creation_refusals_are_atomic(self):
        self.acquire(D.CLASS, branch='마이페이스')
        self.rejected(lambda: self.create('춤', {'atk': 2}, '근사함'), 'Dance Form required')
        self.acquire(D.DANCE_FORM)
        self.rejected(lambda: self.create('춤', {'atk': 1}, '근사함'), r'raise one stat by \+2 or two different stats by \+1')
        self.rejected(lambda: self.create('춤', {'atk': 1, 'def': 2}, '근사함'), r'raise one stat by \+2')
        self.rejected(lambda: self.create('춤', {'atk': 1, 'def': 1, 'spe': 1}, '근사함'), r'raise one stat by \+2')
        self.rejected(lambda: self.create('춤', {'atk': 3}, '근사함'), r'raise one stat by \+2')
        self.rejected(lambda: self.create('춤', {'acc': 2}, '근사함'), 'combat stats')
        self.rejected(lambda: self.create('춤', {'atk': 2}, '귀여움'), 'contest type must match a stat the move affects')
        self.rejected(lambda: self.create('춤', {'atk': 2}, '멋짐'), 'contest type must be one of')
        self.rejected(lambda: self.create('춤', template='beguiling', lowered='def', contest_type='강인함'), 'Beguiling Dance required')
        self.rejected(lambda: self.create('춤', {'atk': 2}, '근사함', template='waltz'), 'template must be form or beguiling')
        self.rejected(lambda: self.create('칼춤', {'atk': 2}, '근사함'), 'collides with an existing Move')
        self.rejected(lambda: self.create(' ', {'atk': 2}, '근사함'), 'name required')
        self.create('불꽃왈츠', {'atk': 2}, '근사함')
        self.rejected(lambda: self.create('불꽃왈츠', {'spe': 2}, '귀여움'), 'already used by this trainer')
        other = self.add('other trainer', 'trainer', (5, 5), classes=[], feats=[], edges=[], items={}, money=100, moves=[], speed=29)
        self.rejected(lambda: D.create_dance_move(self.e, other, name='남의춤', stages={'atk': 2}, contest_type='근사함', reason='x'), 'Dance Form required')
        self.assertEqual(len(D.created_moves(self.t)), 1)
        self.valid()

    # ------------------------------------------------------------ Dance Practice (existing lesson owner) and lifetimes
    def test_dance_practice_acquisition_keeps_the_existing_lesson_owner_and_counts_toward_dance_form(self):
        self.dancer(D.PRACTICE, ability='마이페이스')
        self.assertEqual(D.allowance(self.t), 3)
        self.valid()
        pupil = self.add('pupil', 'pokemon', (2, 1), trainer_id=self.t.entity_id, speed=25, tutor_points=5)
        out = self.e.pokemon_activity(self.t, 'teach_feature_ability', target=pupil, feature=D.PRACTICE, ability='회전춤', seconds=45,
                                      reason='GM observed the completed Extended Ability lesson')
        self.assertEqual((out['source'], out['ability'], out['point_cost'], pupil.abilities, pupil.spec['tutor_points']),
                         (D.PRACTICE, 'ability/회전춤', 2, ['회전춤'], 3))
        self.rejected(lambda: self.e.pokemon_activity(self.t, 'teach_feature_ability', target=pupil, feature=D.PRACTICE, ability='마이페이스', seconds=45,
                                                      reason='second lesson'), '.')   # printed once per Pokemon stays with the existing owner
        self.assertEqual(pupil.spec['tutor_points'], 3)
        self.valid()

    def test_json_restore_and_retraining_keep_identities_and_withdraw_only_dance_form_grants(self):
        self.dancer(D.BEGUILING, D.PIROUETTE)
        first = self.create('불꽃왈츠', {'atk': 1, 'spe': 1}, '근사함')
        second = self.create('기만의탱고', template='beguiling', lowered='spa', contest_type='아름다움')
        self.restore('t')
        self.assertEqual(self.t.moves, [first['id'], second['id']])
        self.assertEqual([self.e.r.move(mid)['name'] for mid in self.t.moves], ['불꽃왈츠', '기만의탱고'])
        self.assertEqual(D.chosen_ability(self.t), '회전춤')
        self.assertEqual(D.allowance(self.t), 4)
        # Tampered records are refused by world validation.
        snapshot = deepcopy(self.t.spec[D.KEY])
        self.t.spec[D.KEY]['dance_moves'][0]['stages'] = {'atk': 2}
        self.invalid('differs from its fixed identity')
        self.t.spec[D.KEY] = deepcopy(snapshot)
        self.t.spec['feature_choices'][D.CLASS].append('마이페이스')
        self.invalid('exactly one printed Ability choice')
        self.t.spec['feature_choices'][D.CLASS] = ['회전춤']
        self.valid()
        # Retraining Dance Form withdraws exactly its Dance Move grants; the class Ability and other Features stay.
        self.retrain(D.PIROUETTE)
        self.assertEqual(self.t.moves, [first['id'], second['id']])
        self.retrain(D.BEGUILING)
        self.retrain(D.DANCE_FORM)
        self.assertEqual((self.t.moves, self.t.abilities, self.t.spec['feats']), ([], ['회전춤'], [D.CLASS]))
        self.assertEqual(len(self.t.spec[D.KEY]['dance_moves']), 2)   # history is kept, not re-granted
        self.valid()
        self.restore('t')
        self.assertEqual(self.t.moves, [])


if __name__ == '__main__':
    unittest.main()
