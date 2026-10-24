"""Chronicler: actual acquisition of the class, archive choices and Feature prerequisites."""
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
import chronicler as CH
import frequency as FREQ
import state_codec as CODEC
import state_fields as FIELDS
import trainer_feature_acquisition as ACQUIRE
import world_entities as WORLD


class ChroniclerAcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)
        self.setup()

    def setup(self, *, perception=6):
        self.e = Engine(self.rules, seed=19321982)
        self.e.grid = Grid(14, 12)
        self.common = dict(level=30, size='중형',
            stats={'hp':1000, 'atk':20, 'def':20, 'spa':20, 'spd':20, 'spe':20},
            moves=['move/몸통박치기'], abilities=[], types=['노말'],
            movement={'land':6, 'swim':0, 'sky':0, 'power':4}, weight_kg=30,
            skills={'통찰':perception, '매력':6, '직감':6, '명령':6, '교활':6, '협박':6, '집중':6})
        self.t = self.add('actual Chronicler', 'trainer', (1, 1), classes=[], feats=[], exp_bank=100,
            chronicler_archive_choices={CH.CLASS:'profile', CH.TRAINING + ':1':'technique', CH.TRAINING + ':2':'travel'},
            chronicler_travel_ability='날카로운눈')
        self.p = self.add('actual learner', 'pokemon', (2, 2), trainer_id=self.t.entity_id, tutor_points=8,
            species='피카츄', types=['전기'], moves=['move/전광석화', 'move/꼬리흔들기'], speed=25)
        self.b = self.add('actual recorded foe', 'pokemon', (4, 2), side='foe', species='피카츄', types=['전기'],
            moves=['move/전광석화', 'move/전기자석파'], speed=15)
        self.e.gm.observe_loyalty(self.p, 6, reason='actual willing Pokemon')

    def add(self, name, kind, pos, speed=None, **extra):
        spec = dict(deepcopy(self.common), name=name, kind=kind)
        if speed is not None:
            spec['stats'] = dict(spec['stats'], spe=speed)   # distinct Speeds keep initiative schedules tie-free
        spec.update(extra)
        actor = Combatant(self.e.r, spec)
        self.e.gm.add_combatant(actor, pos=pos, side=extra.get('side', 'party'),
            reason='actual Chronicler scene participant')
        prepare_body(self.e, actor, size='중형', offsets=[(0, 0)], reason='observed complete body')
        return actor

    def acquire(self, feature=None, rank=None, actor=None):
        feature = CH.CLASS if feature is None else CH.uid(feature)
        actor = self.t if actor is None else actor
        suffix = '' if rank is None else '/' + str(rank)
        options = {} if rank is None else {'rank':rank}
        return ACQUIRE.acquire_static(self.e, actor, feature,
            acquisition_request_id='chronicler/' + actor.entity_id + '/' + feature + suffix, **options)

    def whole(self):
        """Class, both Archival Training ranks and every Feature in printed order."""
        self.acquire()
        self.acquire(CH.TRAINING, 1)
        self.acquire(CH.TRAINING, 2)
        self.acquire(CH.TUTOR)
        self.acquire(CH.PROFILING)
        self.acquire(CH.PARTY)
        self.acquire(CH.CINEMATIC)

    def rejected(self, operation, pattern):
        return assert_rejected_unchanged(self.e, operation, reason_pattern=pattern)

    def valid(self):
        result = self.e.validate_state()
        self.assertTrue(result['valid'], result['issues'])

    def restore(self):
        names = ('t', 'p', 'b', 'u', 'v', 'c', 'q')
        identities = {name:getattr(self, name).entity_id for name in names if hasattr(self, name)}
        self.e = CODEC.load_engine(self.rules, json.loads(json.dumps(self.e.export_state(), ensure_ascii=False)))
        actors = WORLD.actor_index(self.e)
        for name, identity in identities.items():
            setattr(self, name, actors[identity])

    # ---- shared scene helpers borrowed by the record/action test modules ----
    def combat(self, actor, *, count=30):
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor, initiative_count=count)

    def next_turn(self, actor, *, count=30):
        self.e.end_of_turn(self.e._active_turn_actor)
        self.e.end_round()
        self.combat(actor, count=count)

    def use(self, actor, target, move, *, face=10):
        if move not in actor.moves:
            self.e.gm.set_move(actor, move, reason='actual complete known Move list')
        with patch.object(Engine, 'd20', return_value=face):
            return self.e.use_move_on(actor, target, move, self.e.everyone, set_damage=True)

    def witness(self, move, *, user=None, target=None):
        """A foe actually uses the Move in a short encounter, then the scene ends."""
        user = self.b if user is None else user
        target = self.p if target is None else target
        self.combat(user, count=20)
        self.use(user, target, move, face=1)
        self.e.end_of_turn(user)
        self.e.end_round()
        self.e.end_scene()

    def record(self, target, kind, request):
        return CH.record(self.e, self.t, target, kind=kind, reason='actual observed subject', request_id=request)

    def archive_subject(self, target, kind, request):
        row = self.record(target, kind, request)
        return CH.archive(self.e, self.t, row['id'], seconds=600, reason='actual completed archival')

    def archive_move(self, move, *, user=None):
        if not any(r.get('move_id') == move for r in getattr(self.e, '_move_completions', {}).values()):
            self.witness(move, user=user)
        return self.archive_subject(move, 'move', 'move:' + move)

    def archive_place(self, place):
        CH.observe_place(self.e, self.t, place, reason='actual present place')
        return self.archive_subject(place, 'place', 'place:' + place)

    def new_day(self):
        for actor in self.e.everyone:
            FREQ.new_day(actor)

    def communication(self, pokemon=None):
        self.e.gm.observe_sensory_environment(self.t, pokemon or self.p,
            paths={'auditory':True}, present=True, reason='actual audible Order communication')

    def test_template_is_complete_and_class_choice_grants_one_archive_without_followers(self):
        self.assertEqual(len(CH.DEFINITIONS), 6)
        self.assertEqual(set(CH.DEFINITIONS), set(CH.FEATURES))
        self.assertEqual(set(CH.ANALYSES), {'character_study', 'recreation', 'situational_awareness'})
        for uid in CH.FEATURES:
            self.assertEqual(ACQUIRE.STATIC_FEATURES[uid]['clause_id'], CH.clause(uid))
        receipt = self.acquire()
        self.assertEqual(receipt['snapshot']['archive'], 'profile')
        self.assertEqual(receipt['snapshot']['perception'], 6)
        self.assertEqual(receipt, self.acquire())
        self.assertEqual(self.t.spec['feats'], [CH.CLASS])
        self.assertEqual(set(CH.owned_archives(self.t)), {'profile'})
        self.assertEqual(CH.archived(self.t, 'profile'), set())
        self.assertIsNone(CH.acquired(self.t, CH.TUTOR))
        self.assertEqual(CH.acquired(self.t, CH.TRAINING), [])
        self.restore()
        self.valid()
        self.assertEqual(set(CH.owned_archives(self.t)), {'profile'})

    def test_class_requires_novice_perception_and_an_explicit_unowned_archive_choice(self):
        self.setup(perception=2)
        self.rejected(self.acquire, 'Perception')
        self.setup()
        self.t.spec['chronicler_archive_choices'] = {}
        self.rejected(self.acquire, 'archive choice')
        self.t.spec['chronicler_archive_choices'] = {CH.CLASS:'library'}
        self.rejected(self.acquire, 'archive choice')
        self.t.spec['chronicler_archive_choices'] = {CH.CLASS:'profile', CH.TRAINING + ':1':'profile'}
        self.acquire()
        self.rejected(lambda:self.acquire(CH.TRAINING, 1), 'already owned')
        self.p.spec['chronicler_archive_choices'] = {CH.CLASS:'profile'}
        self.rejected(lambda:self.acquire(actor=self.p), 'Trainer|trainer')

    def test_archival_training_ranks_add_archives_in_order_and_travel_needs_a_selected_ability(self):
        self.rejected(lambda:self.acquire(CH.TRAINING, 1), 'Chronicler class')
        self.acquire()
        self.rejected(lambda:self.acquire(CH.TRAINING, 2), 'next actual rank')
        self.rejected(lambda:self.acquire(CH.TRAINING), 'explicit acquired rank in the printed domain')
        self.acquire(CH.TRAINING, 1)
        self.assertEqual(set(CH.owned_archives(self.t)), {'profile', 'technique'})
        self.assertEqual(self.t.spec['feat_ranks'][CH.TRAINING], 1)
        # The bilingual class reference means Perception, not the CSV's Frisk.
        self.t.spec['chronicler_travel_ability'] = '통찰'
        self.assertEqual(CH._travel_ability(self.e.r, '통찰'), '감지')
        self.t.spec['chronicler_travel_ability'] = '위협'
        self.rejected(lambda:self.acquire(CH.TRAINING, 2), 'Keen Eye or Perception')
        self.t.spec['chronicler_travel_ability'] = '날카로운눈'
        receipt = self.acquire(CH.TRAINING, 2)
        self.assertEqual(receipt['snapshot']['travel_ability'], '날카로운눈')
        self.assertEqual(receipt['snapshot']['previous'], CH.acquired(self.t, CH.TRAINING, 1)['request_id'])
        self.assertEqual(set(CH.owned_archives(self.t)), {'profile', 'technique', 'travel'})
        self.assertEqual(CH.owned_archives(self.t)['travel']['feature'], CH.TRAINING)
        self.rejected(lambda:self.acquire(CH.TRAINING, 3), 'explicit acquired rank in the printed domain')
        self.assertFalse(self.t.abilities)  # no place observed yet
        self.restore()
        self.valid()

    def test_feature_prerequisites_need_the_owned_archive_printed_rank_and_four_features(self):
        self.acquire()
        self.rejected(lambda:self.acquire(CH.TUTOR), 'Technique Archive')
        self.rejected(lambda:self.acquire(CH.PARTY), 'Travel Archive')
        self.rejected(lambda:self.acquire(CH.CINEMATIC), 'four actual Chronicler Features')
        self.acquire(CH.TRAINING, 1)
        self.acquire(CH.TRAINING, 2)
        self.rejected(lambda:self.acquire(CH.CINEMATIC), 'four actual Chronicler Features')
        FIELDS.base_patch(self.t, {'skills':dict(self.t.spec['skills'], 통찰=4)}, reason='observed Adept Perception')
        self.rejected(lambda:self.acquire(CH.TUTOR), 'Perception rank')
        self.rejected(lambda:self.acquire(CH.PROFILING), 'Perception rank')
        self.acquire(CH.PARTY)
        FIELDS.base_patch(self.t, {'skills':dict(self.t.spec['skills'], 통찰=5)}, reason='observed Expert Perception')
        self.acquire(CH.TUTOR)
        self.rejected(lambda:self.acquire(CH.CINEMATIC), 'Perception rank')
        FIELDS.base_patch(self.t, {'skills':dict(self.t.spec['skills'], 통찰=6)}, reason='observed Master Perception')
        receipt = self.acquire(CH.CINEMATIC)
        self.assertEqual(len(receipt['snapshot']['features']), 5)
        self.acquire(CH.PROFILING)
        self.assertEqual(len(CH.records(self.t, active=True)), 7)
        self.restore()
        self.valid()

    def test_json_and_gm_restore_keep_receipts_and_reject_tampered_archive_choice(self):
        self.whole()
        before = deepcopy(self.t.spec['state_grants']['sources'])
        self.e.gm.snapshot('chronicler')
        self.e.gm.restore('chronicler')
        self.assertEqual(self.t.spec['state_grants']['sources'], before)
        self.restore()
        self.valid()
        self.assertEqual(set(CH.owned_archives(self.t)), {'profile', 'technique', 'travel'})
        record = next(row for row in self.t.spec['state_grants']['sources'].values()
                      if row.get('static_acquisition', {}).get('feature_id') == CH.CLASS)
        record['static_acquisition']['snapshot']['archive'] = 'travel'
        self.assertFalse(self.e.validate_state()['valid'])
