"""Hunter: actual class and Feature acquisition with printed prerequisites, the class Ability choice, [+Speed] tags and retraining.

HunterScene holds only helpers (no tests); the Surprise! and pack modules reuse it without inheriting any test method.
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
import ability_transitions as ABILITIES
import action_points as AP
import hunter as HU
import state_codec as CODEC
import state_fields as FIELDS
import trainer_feature_acquisition as ACQUIRE
import world_entities as WORLD

ALL = (HU.CLASS, HU.TACTICS, HU.SURPRISE, HU.REFLEXES, HU.FINISHER, HU.LOOK_AWAY, HU.PACK_MASTER)
CLAUSES = {HU.CLASS:'input/ch04-trainer-classes.md:2336-2338', HU.TACTICS:'input/ch04-trainer-classes.md:2340-2345',
           HU.SURPRISE:'input/ch04-trainer-classes.md:2347-2352', HU.REFLEXES:'C04-097', HU.FINISHER:'input/ch04-trainer-classes.md:2360-2364',
           HU.LOOK_AWAY:'input/ch04-trainer-classes.md:2366-2371', HU.PACK_MASTER:'input/ch04-trainer-classes.md:2373-2378'}


class HunterScene:
    """Helpers only: real acquisition, arming, combat turns and scene control through public entry points."""

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)
        self.setup()

    def setup(self, *, survival=5, stealth=5, positions=None, pack=('팀워크', '무리사냥'), loyalty=6, ally_ability=None):
        """t: the Hunter; p/u: owned Pokemon (p with pack[0], u with pack[1]); q: the foe; b: an ally Trainer with its Pokemon v."""
        positions = dict({'t':(1, 1), 'p':(3, 2), 'u':(4, 3), 'q':(4, 2), 'b':(1, 4), 'v':(2, 4)}, **(positions or {}))
        self.e = Engine(self.rules, seed=32614471)
        self.e.grid = Grid(14, 12)
        self.common = dict(level=30, size='중형',
            stats={'hp':20, 'atk':20, 'def':20, 'spa':20, 'spd':20, 'spe':20},
            moves=['move/몸통박치기'], abilities=[], types=['노말'],
            movement={'land':6, 'swim':0, 'sky':0, 'power':4}, weight_kg=30,
            skills={'생존':survival, '은신':stealth, '전투':4, '곡예':4, '육상':4, '집중':3, '통찰':3})
        self.t = self.add('actual Hunter', 'trainer', positions['t'], classes=[], feats=[], edges=[], exp_bank=100)
        self.p = self.add('actual pack one', 'pokemon', positions['p'], trainer_id=self.t.entity_id, species='피카츄', types=['전기'],
            moves=['move/몸통박치기', 'move/전광석화', 'move/전기쇼크'], abilities=[pack[0]] if pack[0] else [], speed=25)
        self.u = self.add('actual pack two', 'pokemon', positions['u'], trainer_id=self.t.entity_id, species='피카츄', types=['전기'],
            moves=['move/몸통박치기', 'move/전광석화', 'move/전기쇼크'], abilities=[pack[1]] if pack[1] else [], speed=23, tutor_points=5)
        self.q = self.add('actual foe', 'pokemon', positions['q'], side='foe', species='피카츄', types=['전기'],
            moves=['move/막치기', 'move/몸통박치기', 'move/전광석화'], speed=15)
        self.b = self.add('actual ally Trainer', 'trainer', positions['b'], classes=[], feats=[], edges=[], exp_bank=100, speed=18)
        self.v = self.add('actual ally Pokemon', 'pokemon', positions['v'], trainer_id=self.b.entity_id, species='피카츄', types=['전기'],
            moves=['move/몸통박치기', 'move/전광석화', 'move/전기쇼크'], abilities=[ally_ability] if ally_ability else [], speed=21)
        if loyalty is not None:
            for pokemon in (self.p, self.u, self.v):
                self.e.gm.observe_loyalty(pokemon, loyalty, reason='observed actual relationship')

    def add(self, name, kind, pos, speed=None, **extra):
        spec = dict(deepcopy(self.common), name=name, kind=kind)
        if speed is not None:
            spec['stats'] = dict(spec['stats'], spe=speed)   # distinct Speeds keep initiative schedules tie-free
        spec.update(extra)
        actor = Combatant(self.e.r, spec)
        self.e.gm.add_combatant(actor, pos=pos, side=extra.get('side', 'party'), reason='actual Hunter scene participant')
        prepare_body(self.e, actor, size='중형', offsets=[(0, 0)], reason='observed complete body')
        return actor

    def acquire(self, feature=None, actor=None, request=None, branch=None):
        feature = HU.CLASS if feature is None else HU.uid(feature)
        actor = self.t if actor is None else actor
        if feature == HU.CLASS and branch is None:
            branch = 'ability/팀워크'
        return ACQUIRE.acquire_static(self.e, actor, feature, branch=branch,
            acquisition_request_id=request or ('hunter/' + actor.entity_id + '/' + feature))

    def whole(self, branch='ability/팀워크'):
        """Class and every Feature in printed order."""
        for feature in ALL:
            self.acquire(feature, branch=branch if feature == HU.CLASS else None)

    def rejected(self, operation, pattern):
        return assert_rejected_unchanged(self.e, operation, reason_pattern=pattern)

    def valid(self):
        result = self.e.validate_state()
        self.assertTrue(result['valid'], result['issues'])

    def invalid(self):
        self.assertFalse(self.e.validate_state()['valid'])

    def restore(self):
        names = ('t', 'p', 'u', 'q', 'b', 'v')
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

    def turn(self, actor, *, count=20):
        """Close the active turn and open this actor's turn in the same round."""
        if self.e._active_turn_actor is not None:
            self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_of_turn(actor, initiative_count=count)

    def next_round(self, actor, *, count=30):
        if self.e._active_turn_actor is not None:
            self.e.end_of_turn(self.e._active_turn_actor)
        self.e.end_round()
        self.combat(actor, count=count)

    def use(self, actor, target, move, *, face=10, **options):
        if move not in actor.moves and move != 'struggle':
            self.e.gm.set_move(actor, move, reason='actual complete known Move list')
        with patch.object(Engine, 'd20', return_value=face):
            return self.e.use_move_on(actor, target, move, self.e.everyone, set_damage=True, **options)

    def answer(self, key, value):
        self.e.rulings.answers[:] = [a for a in self.e.rulings.answers if a['key'] != key]
        self.e.rulings.add_answer(key, value, reason='actual selected native scene choice')

    def activations(self, actor):
        return actor.spec.get('frequency_state', {}).get('activations', {})

    def accuracy_log(self, actor):
        return [line for line in self.e.log_lines if line.startswith('  ' + actor.name + ' ') and '명중 d20=' in line]

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


class HunterAcquisitionTests(HunterScene, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    # ---------------------------------------------------------------- template and class
    def test_template_is_complete_and_class_choice_grants_the_ability_with_a_speed_tag_without_followers(self):
        self.assertEqual(len(HU.DEFINITIONS), 7)
        self.assertEqual(set(HU.DEFINITIONS), set(HU.FEATURES))
        for feature in HU.FEATURES:
            self.assertEqual(ACQUIRE.STATIC_FEATURES[feature]['clause_id'], HU.clause(feature))
            self.assertEqual(HU.clause(feature), CLAUSES[feature])
        self.assertTrue(ACQUIRE.STATIC_FEATURES[HU.CLASS]['branch'])
        self.assertFalse(any(ACQUIRE.STATIC_FEATURES[f].get('branch') for f in ALL[1:]))
        speed, maximum = self.t.stats['spe'], self.t.spec['stats']['spe']
        self.assertFalse(ABILITIES.active(self.t, 'ability/팀워크'))
        receipt = self.acquire()
        self.assertEqual(receipt['snapshot'], {'branch':'ability/팀워크', 'survival':5, 'stealth':5, 'parents':[]})
        self.assertEqual(receipt, self.acquire())
        self.assertEqual((self.t.spec['feats'], self.t.spec['feature_choices'][HU.CLASS]), ([HU.CLASS], ['ability/팀워크']))
        self.assertEqual((self.t.stats['spe'], self.t.spec['stats']['spe']), (speed + 1, maximum))
        self.assertTrue(ABILITIES.active(self.t, 'ability/팀워크'))
        self.assertFalse(ABILITIES.active(self.t, 'ability/무리사냥'))
        self.assertEqual(HU.class_ability(self.t), 'ability/팀워크')
        for feature in ALL[1:]:
            self.assertIsNone(HU.acquired(self.t, feature))
        self.whole()
        self.assertEqual(self.t.stats['spe'], speed + 7)
        self.assertEqual(len(HU.records(self.t, active=True)), 7)
        self.restore()
        self.valid()
        self.assertEqual((self.t.stats['spe'], HU.class_ability(self.t)), (speed + 7, 'ability/팀워크'))
        self.assertTrue(ABILITIES.active(self.t, 'ability/팀워크'))
        # The tag belongs to the acquisition source: removing it is an inconsistency, not a free stat.
        self.t.spec['state_grants']['stat_sources']['spe']['sources'].pop('feature:' + self.t.entity_id + ':' + HU.SURPRISE)
        self.invalid()

    def test_class_choice_may_be_pack_hunt_and_the_grant_is_not_an_unsourced_ability(self):
        self.rejected(lambda:self.acquire(branch='무리사냥'), 'exact Ability identity')
        receipt = self.acquire(branch='ability/무리사냥')
        self.assertEqual(receipt['snapshot']['branch'], 'ability/무리사냥')
        self.assertTrue(ABILITIES.active(self.t, 'ability/무리사냥'))
        self.assertFalse(ABILITIES.active(self.t, 'ability/팀워크'))
        self.assertEqual(self.t.spec.get('abilities', []), [])
        source = self.t.spec['state_grants']['sources']['feature:' + self.t.entity_id + ':' + HU.CLASS + ':ability/무리사냥']
        self.assertEqual(source['grants']['abilities'], ['무리사냥'])
        self.restore()
        self.valid()
        # A grant that disagrees with the acquired choice is detected.
        source = self.t.spec['state_grants']['sources']['feature:' + self.t.entity_id + ':' + HU.CLASS + ':ability/무리사냥']
        source['grants']['abilities'] = ['팀워크']
        self.invalid()

    def test_class_requires_novice_survival_and_stealth_a_printed_choice_one_acquisition_and_an_actual_trainer(self):
        self.setup(survival=2, stealth=3)
        self.rejected(self.acquire, 'Novice Survival')
        self.setup(survival=3, stealth=2)
        self.rejected(self.acquire, 'Novice Stealth')
        self.setup(survival=3, stealth=3)
        self.rejected(lambda:self.acquire(branch='위협'), 'Teamwork or Pack Hunt')
        self.rejected(lambda:ACQUIRE.acquire_static(self.e, self.t, HU.CLASS, acquisition_request_id='hunter/none'), 'Teamwork or Pack Hunt')
        self.rejected(lambda:self.acquire(actor=self.p), 'Trainer|trainer')
        self.assertEqual(self.acquire()['snapshot'], {'branch':'ability/팀워크', 'survival':3, 'stealth':3, 'parents':[]})
        self.rejected(lambda:ACQUIRE.acquire_static(self.e, self.t, HU.CLASS, branch='ability/팀워크', acquisition_request_id='hunter/again'), 'already acquired')
        self.rejected(lambda:ACQUIRE.acquire_static(self.e, self.t, HU.CLASS, branch='ability/무리사냥', acquisition_request_id='hunter/other'), 'already acquired')
        self.valid()

    # ---------------------------------------------------------------- Feature prerequisites
    def test_feature_prerequisites_follow_the_printed_class_skill_and_pack_tactics_chain(self):
        self.setup(survival=3, stealth=3)
        for feature in ALL[1:]:
            self.rejected(lambda:self.acquire(feature), 'Hunter class')
        self.acquire()
        self.acquire(HU.TACTICS)
        self.rejected(lambda:self.acquire(HU.SURPRISE), 'Adept Stealth or Survival')
        self.rejected(lambda:self.acquire(HU.REFLEXES), 'Adept Stealth or Survival')
        self.rejected(lambda:self.acquire(HU.FINISHER), 'Adept')
        self.rejected(lambda:self.acquire(HU.LOOK_AWAY), 'Adept')
        self.rejected(lambda:self.acquire(HU.PACK_MASTER), 'Expert')
        self.skills(은신=4)
        receipt = self.acquire(HU.SURPRISE)
        self.assertEqual(receipt['snapshot'], {'parents':['hunter/' + self.t.entity_id + '/' + HU.CLASS], 'survival':3, 'stealth':4})
        self.acquire(HU.REFLEXES)
        self.rejected(lambda:self.acquire(HU.FINISHER), 'Adept Survival')
        self.rejected(lambda:self.acquire(HU.LOOK_AWAY), 'Adept Survival')
        self.skills(생존=4)
        self.acquire(HU.FINISHER)
        receipt = self.acquire(HU.LOOK_AWAY)
        self.assertEqual(receipt['snapshot']['prerequisites'], {HU.TACTICS:['hunter/' + self.t.entity_id + '/' + HU.TACTICS]})
        self.rejected(lambda:self.acquire(HU.PACK_MASTER), 'Expert')
        self.skills(생존=5)
        self.rejected(lambda:self.acquire(HU.PACK_MASTER), 'Expert Stealth')
        self.skills(은신=5)
        self.acquire(HU.PACK_MASTER)
        self.assertEqual(len(HU.records(self.t, active=True)), 7)
        self.restore()
        self.valid()

    def test_pack_tactics_prerequisite_needs_the_actual_feature_not_the_class_alone(self):
        self.acquire()
        self.rejected(lambda:self.acquire(HU.LOOK_AWAY), 'Pack Tactics')
        self.rejected(lambda:self.acquire(HU.PACK_MASTER), 'Pack Tactics')
        self.acquire(HU.TACTICS)
        self.acquire(HU.LOOK_AWAY)
        self.acquire(HU.PACK_MASTER)
        self.valid()

    # ---------------------------------------------------------------- existing consumers keep working after real acquisition
    def test_real_class_acquisition_feeds_the_existing_pack_tactics_lesson_and_finisher_registration(self):
        import items as ITEMS
        self.acquire()
        self.acquire(HU.TACTICS)
        self.acquire(HU.FINISHER)
        before = ABILITIES.known(self.u)
        result = self.e.pokemon_activity(self.t, 'teach_feature_ability', target=self.u, feature=HU.TACTICS, ability='팀워크',
                                         seconds=45, reason='GM observed the completed Extended Ability lesson')
        self.assertEqual(result['ability'], 'ability/팀워크')
        self.assertEqual(self.u.spec['tutor_points'], 3)
        self.assertTrue(ABILITIES.active(self.u, 'ability/팀워크'))
        self.assertNotIn('ability/팀워크', before)
        # Finisher registers through the existing owner against the actually acquired Feature.
        ITEMS.register_feats(self.e, self.t, pokemon=[self.p, self.u])
        import effects as FX
        move = self.e.r.move('move/몸통박치기')
        bonus = lambda actor:FX.passive_damage_mods(self.e, actor, self.q, move, {'attacker':actor, 'target':self.q, 'hit':True, 'move':move, 'engine':self.e})[1]
        self.assertEqual((bonus(self.t), bonus(self.p)), (0, 0))
        self.e.apply_status(self.q, '둔화', source='condition/둔화', applied_by=self.t)
        self.assertEqual((bonus(self.t), bonus(self.p), bonus(self.v)), (5, 5, 0))
        self.restore()
        self.valid()

    # ---------------------------------------------------------------- retraining
    def test_retraining_the_class_withdraws_the_ability_and_dependent_features_and_the_tags(self):
        speed = self.t.stats['spe']
        self.whole()
        self.assertTrue(ABILITIES.active(self.t, 'ability/팀워크'))
        self.assertEqual(self.t.stats['spe'], speed + 7)
        self.retrain(HU.PACK_MASTER)
        self.assertIsNone(HU.acquired(self.t, HU.PACK_MASTER))
        self.assertEqual(self.t.stats['spe'], speed + 6)
        self.assertEqual(len(HU.records(self.t, HU.PACK_MASTER)), 1)
        self.valid()
        # The class cannot be retrained while an acquired Hunter Feature still depends on it (native prerequisite).
        self.rejected(lambda:self.retrain(HU.CLASS), 'prerequisite cannot be omitted|depends on withdrawn source')
        for feature in (HU.LOOK_AWAY, HU.FINISHER, HU.REFLEXES, HU.SURPRISE, HU.TACTICS):
            self.retrain(feature)
        self.assertEqual(self.t.stats['spe'], speed + 1)
        self.retrain(HU.CLASS)
        self.assertIsNone(HU.acquired(self.t, HU.CLASS))
        self.assertFalse(ABILITIES.active(self.t, 'ability/팀워크'))
        self.assertEqual(self.t.stats['spe'], speed)
        for feature in ALL:
            self.assertIsNone(HU.acquired(self.t, feature))
        self.restore()
        self.valid()
        self.assertFalse(ABILITIES.active(self.t, 'ability/팀워크'))

    def test_tampered_receipts_and_orphan_runtime_records_are_detected_on_validation(self):
        self.whole()
        self.valid()
        source = self.t.spec['state_grants']['sources']['feature:' + self.t.entity_id + ':' + HU.REFLEXES]
        sealed = deepcopy(source['static_acquisition'])
        # The historical qualification is bound to the sealed snapshot: a rewritten rank breaks the integrity seal.
        source['static_acquisition']['snapshot']['stealth'] = 2
        self.invalid()
        source['static_acquisition'] = deepcopy(sealed)
        self.valid()
        # Trainer-only Hunter runtime state on a Pokemon is an inconsistency.
        self.p.spec[HU.SURPRISE_ARMED] = {'target_id':self.q.entity_id, 'acquisition':'x', 'clause_id':HU.clause(HU.SURPRISE), 'armed_at':0}
        self.invalid()
        self.p.spec.pop(HU.SURPRISE_ARMED)
        # A Pack Hunt trigger without the actual Ability and a Pack Master bonus without its Hunter owner are detected.
        self.v.spec[HU.PACK_HUNT_TRIGGER] = {'round':1, 'at':0, 'ally_id':self.b.entity_id, 'foe_id':self.q.entity_id, 'move_id':'struggle', 'melee':True, 'reflexes':False}
        self.invalid()
        self.v.spec.pop(HU.PACK_HUNT_TRIGGER)
        self.valid()


if __name__ == '__main__':
    unittest.main()
