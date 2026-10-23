"""Athlete: actual class and Feature acquisition with printed prerequisites, [+HP] tags, trained stats and retraining.

AthleteScene holds only helpers (no tests); the Coaching and Adrenaline Rush
modules reuse it without inheriting any test method.
"""
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
import action_points as AP
import athlete as AT
import combat_stage_sources as CS
import frequency as FREQ
import state_codec as CODEC
import state_fields as FIELDS
import trainer_feature_acquisition as ACQUIRE
import world_entities as WORLD

ALL = (AT.CLASS, AT.REGIME, AT.COACHING, AT.ADRENALINE)


class AthleteScene:
    """Helpers only: real acquisition, exercise, arming and scene control through public entry points."""

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)
        self.setup()

    def setup(self, *, athletics=5, edges=('edge/육상-이니셔티브',), loyalty=6, positions=None, pokemon_athletics=4):
        positions = dict({'t':(1, 1), 'p':(2, 2), 'q':(3, 2)}, **(positions or {}))
        self.e = Engine(self.rules, seed=22142253)
        self.e.grid = Grid(14, 12)
        self.common = dict(level=30, size='중형',
            stats={'hp':20, 'atk':20, 'def':20, 'spa':20, 'spd':20, 'spe':20},
            moves=['move/몸통박치기'], abilities=[], types=['노말'],
            movement={'land':6, 'swim':0, 'sky':0, 'power':4}, weight_kg=30,
            skills={'육상':athletics, '전투':4, '곡예':4, '은신':4, '집중':3, '통찰':3})
        self.t = self.add('actual Athlete', 'trainer', positions['t'], classes=[], feats=[], edges=list(edges), exp_bank=100)
        self.p = self.add('actual runner', 'pokemon', positions['p'], trainer_id=self.t.entity_id, species='피카츄', types=['전기'],
            moves=['move/전광석화', 'move/몸통박치기'], speed=25, skills={'육상':pokemon_athletics, '전투':4, '곡예':4, '은신':4, '집중':3})
        self.q = self.add('actual foe', 'pokemon', positions['q'], side='foe', species='피카츄', types=['전기'],
            moves=['move/막치기', 'move/몸통박치기', 'move/전광석화'], speed=15)
        if loyalty is not None:
            self.e.gm.observe_loyalty(self.p, loyalty, reason='observed actual relationship')

    def add(self, name, kind, pos, speed=None, **extra):
        spec = dict(deepcopy(self.common), name=name, kind=kind)
        if speed is not None:
            spec['stats'] = dict(spec['stats'], spe=speed)   # distinct Speeds keep initiative schedules tie-free
        spec.update(extra)
        actor = Combatant(self.e.r, spec)
        self.e.gm.add_combatant(actor, pos=pos, side=extra.get('side', 'party'), reason='actual Athlete scene participant')
        prepare_body(self.e, actor, size='중형', offsets=[(0, 0)], reason='observed complete body')
        return actor

    def acquire(self, feature=None, actor=None, request=None):
        feature = AT.CLASS if feature is None else AT.uid(feature)
        actor = self.t if actor is None else actor
        return ACQUIRE.acquire_static(self.e, actor, feature,
            acquisition_request_id=request or ('athlete/' + actor.entity_id + '/' + feature))

    def whole(self):
        """Class and every Feature in printed order."""
        for feature in ALL:
            self.acquire(feature)

    def exercise(self, stats=('atk', 'spe'), reason='actual one-hour exercise'):
        return AT.exercise(self.e, self.t, list(stats), reason=reason)

    def arm(self, branch, skill=None, pokemon=None, trainer=None):
        return AT.arm_coaching(self.e, trainer or self.t, pokemon or self.p, branch, skill)

    def rejected(self, operation, pattern):
        return assert_rejected_unchanged(self.e, operation, reason_pattern=pattern)

    def valid(self):
        result = self.e.validate_state()
        self.assertTrue(result['valid'], result['issues'])

    def invalid(self):
        self.assertFalse(self.e.validate_state()['valid'])

    def restore(self):
        names = ('t', 'p', 'q', 'u')
        identities = {name:getattr(self, name).entity_id for name in names if hasattr(self, name)}
        self.e = CODEC.load_engine(self.rules, json.loads(json.dumps(self.e.export_state(), ensure_ascii=False)))
        actors = WORLD.actor_index(self.e)
        for name, identity in identities.items():
            setattr(self, name, actors[identity])

    def skills(self, actor=None, **ranks):
        actor = actor or self.t
        FIELDS.base_patch(actor, {'skills':dict(actor.spec['skills'], **ranks)}, reason='observed actual skill ranks')

    def combat(self, actor, *, count=30):
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor, initiative_count=count)

    def next_turn(self, actor, *, count=30):
        self.e.end_of_turn(self.e._active_turn_actor)
        self.e.end_round()
        self.combat(actor, count=count)

    def use(self, actor, target, move, *, face=10, **options):
        if move not in actor.moves:
            self.e.gm.set_move(actor, move, reason='actual complete known Move list')
        with patch.object(Engine, 'd20', return_value=face):
            return self.e.use_move_on(actor, target, move, self.e.everyone, set_damage=True, **options)

    def activations(self, actor):
        return actor.spec.get('frequency_state', {}).get('activations', {})

    def decisions(self, trainer, feature):
        import trainer_retraining as RETRAINING
        sources = {owned:RETRAINING.owned_source(self.e, trainer, owned) for owned in RETRAINING._owned(trainer)}
        retained = {source:list(trainer.spec['state_grants']['sources'][source].get('withdrawal_dependencies', []))
                    for owned, source in sources.items() if owned != feature}
        for child, parents in RETRAINING._native_dependencies(self.e, trainer, RETRAINING._owned(trainer)).items():
            if child != feature:
                retained[sources[child]] = [sources[parent] for parent in parents]
        return dict(request_id='retrain/' + feature, reason='actual trainer chooses retraining',
                    gm_decision={'allowed':True, 'reason':'GM reviewed prerequisites and narrative'},
                    retained_dependencies=retained)

    def retrain(self, feature):
        return self.e.retrain_trainer_source(self.t, feature, **self.decisions(self.t, feature))


class AthleteAcquisitionTests(AthleteScene, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    # ---------------------------------------------------------------- template and class
    def test_template_is_complete_and_class_acquisition_tags_hp_without_followers(self):
        self.assertEqual(len(AT.DEFINITIONS), 4)
        self.assertEqual(set(AT.DEFINITIONS), set(AT.FEATURES))
        for feature in AT.FEATURES:
            self.assertEqual(ACQUIRE.STATIC_FEATURES[feature]['clause_id'], AT.clause(feature))
        self.assertEqual((AT.clause(AT.CLASS), AT.clause(AT.COACHING), AT.clause(AT.ADRENALINE)),
                         ('input/ch04-trainer-classes.md:2214-2216', 'C04-095', 'input/ch04-trainer-classes.md:2240-2245'))
        hp, maximum = self.t.stats['hp'], self.t.max_hp
        receipt = self.acquire()
        self.assertEqual(receipt['snapshot'], {'athletics':5, 'edges':['edge/육상-이니셔티브'], 'parents':[]})
        self.assertEqual(receipt, self.acquire())
        self.assertEqual(self.t.spec['feats'], [AT.CLASS])
        self.assertEqual((self.t.stats['hp'], self.t.max_hp, self.t.spec['stats']['hp']), (hp + 1, maximum + 3, hp))
        for feature in (AT.REGIME, AT.COACHING, AT.ADRENALINE):
            self.assertIsNone(AT.acquired(self.t, feature))
        self.assertEqual(AT.trained_stats(self.t), [])
        self.assertEqual(self.t.stages, dict.fromkeys(CS.STATS, 0))
        self.whole()
        self.assertEqual((self.t.stats['hp'], self.t.max_hp), (hp + 4, maximum + 12))
        self.assertEqual(len(AT.records(self.t, active=True)), 4)
        self.restore()
        self.valid()
        self.assertEqual((self.t.stats['hp'], self.t.max_hp), (hp + 4, maximum + 12))
        # The tag belongs to the acquisition source: removing it is an inconsistency, not a free stat.
        self.t.spec['state_grants']['stat_sources']['hp']['sources'].pop('feature:' + self.t.entity_id + ':' + AT.COACHING)
        self.invalid()

    def test_class_requires_novice_athletics_one_printed_edge_and_an_actual_trainer(self):
        self.setup(athletics=2)
        self.rejected(self.acquire, 'Novice Athletics')
        self.setup(athletics=3, edges=())
        self.rejected(self.acquire, 'printed Edge')
        self.setup(athletics=3, edges=('edge/전문-트릭스터',))
        self.rejected(self.acquire, 'printed Edge')
        self.rejected(lambda:self.acquire(actor=self.p), 'Trainer|trainer')
        for edge in AT.EDGES:   # Stamina itself needs Expert Athletics or Combat; every printed alternative qualifies the class
            with self.subTest(edge=edge):
                self.setup(athletics=5, edges=(edge,))
                self.assertEqual(self.acquire()['snapshot'], {'athletics':5, 'edges':[edge], 'parents':[]})
        self.setup(athletics=3, edges=('edge/탑승-기량', 'edge/수영-선수'))
        self.assertEqual(self.acquire()['snapshot']['edges'], ['edge/탑승-기량', 'edge/수영-선수'])
        self.rejected(lambda:ACQUIRE.acquire_static(self.e, self.t, AT.CLASS, acquisition_request_id='athlete/again'), 'already acquired')

    def test_feature_prerequisites_need_the_class_training_regime_and_expert_athletics(self):
        self.setup(athletics=4)
        self.rejected(lambda:self.acquire(AT.REGIME), 'Athlete class')
        self.rejected(lambda:self.acquire(AT.COACHING), 'Athlete class')
        self.rejected(lambda:self.acquire(AT.ADRENALINE), 'Athlete class')
        self.acquire()
        self.rejected(lambda:self.acquire(AT.COACHING), 'Training Regime')
        self.rejected(lambda:self.acquire(AT.ADRENALINE), 'Expert Athletics')
        self.acquire(AT.REGIME)
        receipt = self.acquire(AT.COACHING)
        self.assertEqual(receipt['snapshot'], {'parents':['athlete/' + self.t.entity_id + '/' + AT.CLASS], 'athletics':4,
                                               'prerequisites':{AT.REGIME:['athlete/' + self.t.entity_id + '/' + AT.REGIME]}})
        self.rejected(lambda:self.acquire(AT.ADRENALINE), 'Expert Athletics')
        self.skills(육상=5)
        self.assertEqual(self.acquire(AT.ADRENALINE)['snapshot']['athletics'], 5)
        self.rejected(lambda:ACQUIRE.acquire_static(self.e, self.t, AT.COACHING, acquisition_request_id='athlete/again'), 'already acquired')
        self.rejected(lambda:self.acquire(AT.COACHING, actor=self.p), 'Trainer|trainer')
        self.restore()
        self.valid()
        record = next(row for row in self.t.spec['state_grants']['sources'].values()
                      if row.get('static_acquisition', {}).get('feature_id') == AT.CLASS)
        record['static_acquisition']['snapshot']['edges'] = []
        self.invalid()

    # ---------------------------------------------------------------- trained stats
    def test_exercise_is_an_outside_combat_hour_that_sets_two_default_plus_one_stages_and_replaces_them(self):
        self.rejected(lambda:self.exercise(), 'actual acquired Athlete')
        self.acquire()
        for stats in (['hp', 'atk'], ['atk'], ['atk', 'atk'], ['atk', 'def', 'spe'], 'atk', ['atk', '공격']):
            self.rejected(lambda:self.exercise(stats), 'two distinct trained stats')
        self.rejected(lambda:self.exercise(reason=''), 'reason')
        self.combat(self.p)
        self.rejected(lambda:self.exercise(), 'active encounter')
        self.e.end_scene()
        elapsed = self.e.elapsed_seconds
        row = self.exercise()
        self.assertEqual((row['stats'], row['seconds'], self.e.elapsed_seconds, self.t._action_history), (['atk', 'spe'], 3600, elapsed + 3600, ['extended']))
        self.assertEqual(AT.trained_stats(self.t), ['atk', 'spe'])
        self.assertEqual(self.t.stages, {'atk':1, 'def':0, 'spa':0, 'spd':0, 'spe':1})
        self.assertEqual(CS.effective_stage(self.t, 'atk'), 1)
        self.valid()
        # A second hour replaces both trained stats; the old default stages end with their source.
        self.exercise(['def', 'spd'], reason='actual second hour')
        self.assertEqual(self.t.stages, {'atk':0, 'def':1, 'spa':0, 'spd':1, 'spe':0})
        self.assertEqual([row['stats'] for row in self.t.spec[AT.TRAINED_HISTORY]], [['atk', 'spe']])
        self.assertEqual(self.e.elapsed_seconds, elapsed + 7200)
        # Ordinary combat stages stack on the trained default and reset to it at encounter end.
        self.combat(self.p)
        self.e.change_stage(self.t, 'def', 2)
        self.e.change_stage(self.t, 'atk', 1)
        self.assertEqual((self.t.stages['def'], self.t.stages['atk']), (3, 1))
        self.e.end_scene()
        self.assertEqual(self.t.stages, {'atk':0, 'def':1, 'spa':0, 'spd':1, 'spe':0})
        self.e.gm.snapshot('athlete')
        self.e.gm.restore('athlete')
        self.restore()
        self.valid()
        self.assertEqual((AT.trained_stats(self.t), self.t.stages['def'], self.t.stages['spd']), (['def', 'spd'], 1, 1))
        self.t.spec[AT.TRAINED_KEY]['stats'] = ['def', 'spa']
        self.invalid()
        self.t.spec[AT.TRAINED_KEY]['stats'] = ['def', 'spd']
        self.valid()
        self.t.spec[CS.STATE]['base'].pop(AT.BASE_PREFIX + self.t.entity_id)
        self.invalid()

    # ---------------------------------------------------------------- retraining
    def test_retraining_withdraws_only_what_each_athlete_source_justified(self):
        self.whole()
        self.exercise()
        hp = self.t.stats['hp']
        self.arm('sprint')
        self.e.gm.set_hp(self.t, value=100, reason='observed current HP')
        self.e.lose_hp(self.t, 50, source='actual hazard')
        self.assertIsNotNone(AT.adrenaline_trigger(self.t))
        self.assertIsNotNone(AT.armed(self.p))
        self.retrain(AT.ADRENALINE)
        self.assertIsNone(AT.adrenaline_trigger(self.t))
        self.assertIsNotNone(AT.armed(self.p))
        self.assertEqual(self.t.stats['hp'], hp - 1)
        self.retrain(AT.COACHING)
        self.assertIsNone(AT.armed(self.p))
        self.assertEqual(AT.trained_stats(self.t), ['atk', 'spe'])
        self.retrain(AT.REGIME)
        self.assertEqual(self.t.stages['atk'], 1)
        self.retrain(AT.CLASS)
        self.assertEqual((self.t.spec['feats'], self.t.stats['hp'], AT.trained_stats(self.t)), ([], hp - 4, []))
        self.assertEqual(self.t.stages, dict.fromkeys(CS.STATS, 0))
        self.assertEqual(self.t.spec[AT.TRAINED_HISTORY][-1]['cause'], 'retrained:' + AT.CLASS)
        self.restore()
        self.valid()
        self.rejected(lambda:self.exercise(), 'actual acquired Athlete')


if __name__ == '__main__':
    unittest.main()
