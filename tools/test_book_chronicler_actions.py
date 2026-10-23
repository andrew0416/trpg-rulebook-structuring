"""Chronicler actions: Archive Tutor, Targeted Profiling and the three Cinematic Analyses.

Reuse acquisition fixture helpers without inheriting or collecting its tests.
"""
from unittest.mock import patch
import unittest

import test_book_chronicler_acquisition as fixture
from engine import Engine, Rules
import action_points as AP
import chronicler as CH
import combat_timing as TIMING
import move_state as MOVES
import priority_actions as PRIORITY
import skill_modifiers as SKILLS


class ChroniclerActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(fixture.ROOT, ruleset='core')

    # Only fixture methods are borrowed: no inherited test methods or load_tests.
    setUp = fixture.ChroniclerAcquisitionTests.setUp
    setup = fixture.ChroniclerAcquisitionTests.setup
    add = fixture.ChroniclerAcquisitionTests.add
    acquire = fixture.ChroniclerAcquisitionTests.acquire
    whole = fixture.ChroniclerAcquisitionTests.whole
    rejected = fixture.ChroniclerAcquisitionTests.rejected
    valid = fixture.ChroniclerAcquisitionTests.valid
    restore = fixture.ChroniclerAcquisitionTests.restore
    combat = fixture.ChroniclerAcquisitionTests.combat
    next_turn = fixture.ChroniclerAcquisitionTests.next_turn
    use = fixture.ChroniclerAcquisitionTests.use
    witness = fixture.ChroniclerAcquisitionTests.witness
    record = fixture.ChroniclerAcquisitionTests.record
    archive_subject = fixture.ChroniclerAcquisitionTests.archive_subject
    archive_move = fixture.ChroniclerAcquisitionTests.archive_move
    archive_place = fixture.ChroniclerAcquisitionTests.archive_place
    new_day = fixture.ChroniclerAcquisitionTests.new_day
    communication = fixture.ChroniclerAcquisitionTests.communication

    def tutor(self, pokemon, move, **extra):
        options = dict(seconds=3600, reason='actual completed Archive Tutor teaching')
        options.update(extra)
        return CH.tutor(self.e, self.t, pokemon, move, **options)

    def other_owner(self):
        self.u = self.add('other trainer', 'trainer', (1, 6), classes=[], feats=[], exp_bank=100, speed=18)
        self.v = self.add('other owned', 'pokemon', (2, 6), trainer_id=self.u.entity_id, tutor_points=8,
            species='피카츄', types=['전기'], moves=['move/전광석화'], speed=12)
        self.e.gm.observe_loyalty(self.v, 6, reason='actual willing Pokemon')

    def test_archive_tutor_teaches_an_archived_learnable_move_daily_for_two_points_and_keeps_the_pool_limit(self):
        self.whole()
        self.other_owner()
        self.archive_move('move/전기자석파')   # Pikachu Level 18 and TM73
        self.archive_move('move/몸통박치기')   # witnessed, but outside every Pikachu route
        self.rejected(lambda:self.tutor(self.p, 'move/10만볼트'), 'archived Technique Move record')
        self.rejected(lambda:self.tutor(self.p, 'move/몸통박치기'), 'Level Up, TM or Tutor')
        wild = self.add('wild subject', 'pokemon', (8, 8), side='wild', species='피카츄', types=['전기'], tutor_points=8, speed=13)
        self.rejected(lambda:self.tutor(wild, 'move/전기자석파'), 'owned Pokemon')
        self.p.spec['tutor_points'] = 1
        self.rejected(lambda:self.tutor(self.p, 'move/전기자석파'), 'two actual Tutor Points')
        self.p.spec['tutor_points'] = 12
        self.rejected(lambda:self.tutor(self.p, 'move/전기자석파', seconds=0), 'seconds')
        elapsed = self.e.elapsed_seconds
        result = self.tutor(self.p, 'move/전기자석파')
        # A Level-Up-list Move stays a natural Move of the species; it costs the printed points anyway.
        self.assertEqual((result['move'], result['point_cost'], result['classification']), ('move/전기자석파', 2, 'natural'))
        self.assertEqual(sorted(result['routes']), ['level_up', 'tm'])
        self.assertEqual((self.p.spec['tutor_points'], self.e.elapsed_seconds), (10, elapsed + 3600))
        self.assertIn('move/전기자석파', self.p.moves)
        self.assertEqual(self.p.spec['move_learning']['move/전기자석파']['paid_tp'], 2)
        self.assertEqual(self.t.spec[CH.KEY]['tutoring'][-1]['other_owner'], False)
        self.rejected(lambda:self.tutor(self.v, 'move/전기자석파'), 'daily frequency')
        self.new_day()
        self.tutor(self.v, 'move/전기자석파')
        self.assertEqual((self.v.spec['tutor_points'], self.t.spec[CH.KEY]['tutoring'][-1]['other_owner']), (6, True))
        self.new_day()
        self.c = self.add('second witnessed foe', 'pokemon', (6, 2), side='foe', species='피카츄', types=['전기'], speed=11)
        self.archive_move('move/10만볼트', user=self.c)   # TM24 only at level 30: a taught Move
        self.rejected(lambda:self.tutor(self.v, 'move/10만볼트'), 'only once')
        taught = self.tutor(self.p, 'move/10만볼트')
        self.assertEqual((taught['classification'], taught['routes']), ('taught', ['tm']))
        for move in ('move/바위깨기', 'move/깨트리기'):
            self.new_day()
            self.archive_move(move, user=self.c)
            self.tutor(self.p, move)
        self.assertEqual(MOVES.describe(self.e.r, self.p.spec)['taught_count'], 3)
        self.new_day()
        self.archive_move('move/차지빔', user=self.c)
        self.rejected(lambda:self.tutor(self.p, 'move/차지빔', replace='move/꼬리흔들기'), 'combined TM/Tutor moves exceed')
        self.rejected(lambda:self.tutor(self.p, 'move/깨트리기'), 'already learned')
        self.restore()
        self.valid()
        self.assertEqual(self.p.spec['tutor_points'], 4)
        self.assertEqual(len(self.t.spec[CH.KEY]['tutoring']), 5)

    def test_targeted_profiling_order_gives_next_turn_accuracy_and_mold_breaker_only_against_archived_subjects(self):
        self.whole()
        self.e.gm.set_ability(self.b, '부유', reason='actual defensive Levitate')
        self.c = self.add('unrecorded levitating foe', 'pokemon', (6, 2), side='foe', species='피카츄', types=['전기'], abilities=['부유'], speed=11)
        self.archive_subject(self.b, 'pokemon', 'rec-b')
        self.e.gm.set_move(self.p, 'move/진흙뿌리기', reason='actual known Ground Move')
        self.communication()
        self.combat(self.t)
        self.rejected(lambda:CH.profile_order(self.e, self.t, self.b), 'owned Pokemon')
        ap = AP.available(self.t)
        facts = CH.profile_order(self.e, self.t, self.p)
        self.assertEqual((AP.available(self.t), self.t.budget['standard']), (ap - 2, 0))
        self.assertEqual(facts['active_serial'], self.p.custom_conditions.get('combat_turn_serial', 0) + 1)
        self.assertEqual(CH.profiling_record(self.p)['source'], CH.PROFILING)
        self.restore()   # the pending next-turn record survives the JSON round trip
        self.assertEqual(CH.profiling_record(self.p)['chronicler_profiling'], facts)
        self.valid()
        self.rejected(lambda:CH.profile_order(self.e, self.t, self.p), 'already pending|Standard action unavailable')
        self.assertEqual(CH.accuracy_bonus(self.e, self.p, self.b, {'id':'move/진흙뿌리기'}), 0)  # not yet its turn
        self.e.end_of_turn(self.t)
        self.e.start_of_turn(self.p, initiative_count=20)
        self.assertEqual(CH.accuracy_bonus(self.e, self.p, self.b, {'id':'move/진흙뿌리기'}), 2)
        self.assertEqual(CH.accuracy_bonus(self.e, self.p, self.c, {'id':'move/진흙뿌리기'}), 0)
        self.assertTrue(CH.defensive_ignored(self.e, self.p, self.b))
        self.assertFalse(CH.defensive_ignored(self.e, self.p, self.c))
        ac = self.e.r.move('move/진흙뿌리기')['ac']
        evasion = self.b.evasion('특수', attacker=self.p, engine=self.e)
        hp = self.b.hp
        self.use(self.p, self.b, 'move/진흙뿌리기', face=ac + evasion - 1)   # hits only with +2; Levitate ignored
        self.assertLess(self.b.hp, hp)
        self.e.end_of_turn(self.p)
        self.assertIsNone(CH.profiling_record(self.p))
        self.e.end_round()
        self.combat(self.p, count=20)
        hp = self.b.hp
        self.use(self.p, self.b, 'move/진흙뿌리기', face=ac + evasion - 1)   # ordinary accuracy again
        self.assertEqual(self.b.hp, hp)
        self.next_turn(self.p, count=20)
        hp = self.b.hp
        self.use(self.p, self.b, 'move/진흙뿌리기', face=ac + evasion + 1)   # hits, but Levitate is back
        self.assertEqual(self.b.hp, hp)
        self.valid()
        # An unarchived foe keeps its Levitate even during the profiled turn.
        self.setup()
        self.whole()
        self.c = self.add('unrecorded levitating foe', 'pokemon', (6, 2), side='foe', species='피카츄', types=['전기'], abilities=['부유'], speed=11)
        self.archive_subject(self.b, 'pokemon', 'rec-b')
        self.e.gm.set_move(self.p, 'move/진흙뿌리기', reason='actual known Ground Move')
        self.communication()
        self.combat(self.t)
        CH.profile_order(self.e, self.t, self.p)
        self.e.end_of_turn(self.t)
        self.e.start_of_turn(self.p, initiative_count=20)
        hp = self.c.hp
        self.use(self.p, self.c, 'move/진흙뿌리기', face=19)
        self.assertEqual(self.c.hp, hp)
        AP.spend(self.t, AP.available(self.t) - 1)
        self.next_turn(self.t)
        self.communication()
        self.rejected(lambda:CH.profile_order(self.e, self.t, self.p), 'two available AP')
        self.restore()
        self.valid()

    def test_character_study_replaces_a_social_check_with_the_chroniclers_perception_three_daily_once_per_scene(self):
        self.whole()
        self.c = self.add('unrecorded foe', 'pokemon', (6, 2), side='foe', species='피카츄', types=['전기'], speed=11)
        archived = self.archive_subject(self.b, 'pokemon', 'rec-b')
        dice = SKILLS.rank(self.e.r, self.p, '매력')[2]
        options = dict(record_id=archived['id'], actor=self.p, target=self.b, skill='매력', dc=15, purpose='social_contest',
                       reason='actual recorded subject conversation', fixed=[2] * dice, perception_fixed=[3] * 6)
        self.rejected(lambda:CH.character_study(self.e, self.t, **dict(options, actor=self.c)), 'ally')
        self.rejected(lambda:CH.character_study(self.e, self.t, **dict(options, target=self.c)), 'recorded subject')
        self.rejected(lambda:CH.character_study(self.e, self.t, **dict(options, skill='통찰')), 'replaces only')
        result = CH.character_study(self.e, self.t, **options)
        self.assertEqual(result['replacement']['skill'], '통찰')
        self.assertEqual((result['replacement']['total'], result['replacement']['passed'], result['triggered']['rolled']), (18, True, False))
        self.assertEqual(self.t.spec[CH.KEY]['analyses'][-1]['kind'], 'character_study')
        self.rejected(lambda:CH.character_study(self.e, self.t, **options), 'already used this scene')
        self.e.end_scene()
        own = CH.character_study(self.e, self.t, **dict(options, actor=self.t, fixed=[2] * 6, perception_fixed=[1] * 6))
        self.assertEqual((own['replacement']['total'], own['replacement']['passed']), (6, False))
        self.e.end_scene()
        CH.character_study(self.e, self.t, **options)
        self.e.end_scene()
        self.rejected(lambda:CH.character_study(self.e, self.t, **options), 'daily frequency')
        self.new_day()
        CH.character_study(self.e, self.t, **options)
        self.restore()
        self.valid()
        self.assertEqual(len(self.t.spec[CH.KEY]['analyses']), 4)

    def test_recreation_performs_an_archived_learnable_move_as_the_pokemon_gains_initiative_once_per_move_per_day(self):
        self.whole()
        self.archive_move('move/10만볼트')
        self.archive_move('move/바위깨기')
        self.archive_move('move/전광석화')
        self.combat(self.p, count=20)
        self.rejected(lambda:CH.recreation(self.e, self.t, self.p, 'move/전광석화'), 'already on the actual Move List')
        self.rejected(lambda:CH.recreation(self.e, self.t, self.p, 'move/볼트체인지'), 'archived Technique Move record')
        self.rejected(lambda:CH.recreation(self.e, self.t, self.b, 'move/10만볼트'), 'owned Pokemon')
        result = CH.recreation(self.e, self.t, self.p, 'move/10만볼트')
        self.assertIn('move/10만볼트', self.p.moves)
        self.assertEqual(result['routes'], ['tm'])
        self.rejected(lambda:CH.recreation(self.e, self.t, self.p, 'move/바위깨기'), 'already used this scene')
        hp = self.b.hp
        self.use(self.p, self.b, 'move/10만볼트', face=19)
        self.assertLess(self.b.hp, hp)
        self.assertEqual(MOVES.describe(self.e.r, self.p.spec)['classifications'].get('move/10만볼트'), None)
        self.e.end_of_turn(self.p)
        self.assertNotIn('move/10만볼트', self.p.moves)
        self.assertNotIn(result['permission_source'], self.p.spec['state_grants']['sources'])
        self.e.end_round()
        self.e.end_scene()
        self.combat(self.p, count=20)
        self.rejected(lambda:CH.recreation(self.e, self.t, self.p, 'move/10만볼트'), 'already chosen for Recreation today')
        self.use(self.p, self.b, 'move/전광석화', face=1)
        self.rejected(lambda:CH.recreation(self.e, self.t, self.p, 'move/바위깨기'), 'before it acts')
        self.e.end_of_turn(self.p)
        self.e.end_round()
        self.e.end_scene()
        self.combat(self.p, count=20)
        CH.recreation(self.e, self.t, self.p, 'move/바위깨기')
        self.assertIn('move/바위깨기', self.p.moves)
        self.restore()
        self.valid()
        self.assertIn('move/바위깨기', self.p.moves)
        self.e.end_of_turn(self.p)
        self.assertNotIn('move/바위깨기', self.p.moves)
        self.valid()

    def test_situational_awareness_at_the_present_place_lets_an_ally_act_with_advanced_priority(self):
        self.whole()
        self.q = self.add('second owned', 'pokemon', (2, 3), trainer_id=self.t.entity_id, tutor_points=8,
            species='피카츄', types=['전기'], moves=['move/전광석화'], speed=22)
        self.e.gm.observe_loyalty(self.q, 6, reason='actual willing Pokemon')
        archived = self.archive_place('route-1')
        CH.observe_place(self.e, self.t, 'town', reason='actual departure')
        self.e.prepare_initiative_schedule(self.e.everyone, source='gm/test-schedule')
        self.e.start_round(self.e.everyone)
        self.rejected(lambda:CH.situational_awareness(self.e, self.t, self.p, record_id=archived['id']), 'present place')
        CH.observe_place(self.e, self.t, 'route-1', reason='actual return')
        self.rejected(lambda:CH.situational_awareness(self.e, self.t, self.t, record_id=archived['id']), 'other than yourself')
        self.rejected(lambda:CH.situational_awareness(self.e, self.t, self.b, record_id=archived['id']), 'ally')
        self.rejected(lambda:PRIORITY.use(self.e, self.p, self.b, 'move/전광석화', situational_awareness=self.t), 'entitlement')
        self.e.start_of_turn(self.p)   # the ally already acted this round
        self.e.end_of_turn(self.p)
        token = CH.situational_awareness(self.e, self.t, self.p, record_id=archived['id'])
        self.assertEqual((token['variant'], self.p.spec[CH.PRIORITY]['owner_id']), ('advanced', self.t.entity_id))
        self.rejected(lambda:CH.situational_awareness(self.e, self.t, self.q, record_id=archived['id']), 'already used this scene')
        hp = self.b.hp
        with patch.object(Engine, 'd20', return_value=19):
            result = PRIORITY.use(self.e, self.p, self.b, 'move/전광석화', situational_awareness=self.t)
        self.assertEqual(result['source'], CH.CINEMATIC)
        self.assertLess(self.b.hp, hp)
        self.assertNotIn(CH.PRIORITY, self.p.spec)
        self.assertEqual(self.e.initiative_reaction_status()['owed_turns'][0]['due_round'], self.e.round_no + 1)
        self.e.finish_initiative_reaction()
        self.restore()
        self.valid()
        # An unused entitlement lapses when the ally's ordinary turn begins.
        self.e.end_scene()
        self.e.prepare_initiative_schedule(self.e.everyone, source='gm/test-schedule')
        self.e.start_round(self.e.everyone)
        CH.situational_awareness(self.e, self.t, self.q, record_id=archived['id'])
        self.assertIn(CH.PRIORITY, self.q.spec)
        self.e.start_of_turn(self.p)   # the schedule's first turn belongs to the faster ally
        self.e.end_of_turn(self.p)
        self.assertIn(CH.PRIORITY, self.q.spec)
        self.e.start_of_turn(self.q)
        self.assertNotIn(CH.PRIORITY, self.q.spec)
        self.e.end_of_turn(self.q)
        self.valid()
