"""Chronicler records, archives and the three archive passives on actual native paths.

Reuse acquisition fixture helpers without inheriting or collecting its tests.
"""
from unittest.mock import patch
import unittest

import test_book_chronicler_acquisition as fixture
from engine import Engine, Rules
import action_points as AP
import chronicler as CH
import perception_observe as PERCEPTION
import skill_modifiers as SKILLS
import state_grants as G


class ChroniclerRecordTests(unittest.TestCase):
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

    def sensing(self, observer, target, *, faces):
        declaration = {'id':'chronicler-test:notice', 'source':CH.CLASS, 'capabilities':[], 'mode':'visual',
            'range':None, 'path':None, 'medium':[], 'vision':None, 'provider':'entity',
            'information':['presence'], 'check':{'skill':'통찰', 'dc':10, 'purpose':'notice_surroundings'}}
        return PERCEPTION.observe(self.e, observer, target, declaration, roll_options={'fixed':faces})

    def test_record_needs_an_actual_subject_one_ap_swift_and_extended_archival_into_an_owned_archive(self):
        self.whole()
        self.combat(self.t)
        ap = AP.available(self.t)
        self.rejected(lambda:self.record(self.t, 'trainer', 'self'), 'other trainer')
        self.rejected(lambda:self.record(self.p, 'trainer', 'kind'), 'other trainer')
        self.rejected(lambda:self.record('move/전광석화', 'move', 'unseen'), 'witnessed')
        self.rejected(lambda:self.record('route-1', 'place', 'absent'), 'present place')
        self.rejected(lambda:self.record(self.b, 'portrait', 'kind'), 'Pokemon, Trainer, Move or place')
        row = self.record(self.b, 'pokemon', 'rec-b')
        self.assertEqual((row['kind'], row['subject'], row['status'], row['archive']), ('pokemon', self.b.entity_id, 'provisional', None))
        self.assertEqual(AP.available(self.t), ap - 1)
        self.assertEqual(self.t.budget['swift'], 0)
        self.assertEqual(self.record(self.b, 'pokemon', 'rec-b'), row)  # replay returns the same record
        self.assertEqual(AP.available(self.t), ap - 1)
        self.rejected(lambda:self.record(self.p, 'pokemon', 'rec-b'), 'replay cannot change')
        # The ordinary economy lets a Standard fund a second Swift; the third Record has no action left.
        self.record(self.p, 'pokemon', 'rec-p')
        self.assertEqual((self.t.budget['standard'], AP.available(self.t)), (0, ap - 2))
        self.rejected(lambda:self.record(self.p, 'trainer', 'rec-x'), 'other trainer')
        self.c = self.add('third subject', 'pokemon', (6, 2), side='foe', species='피카츄', types=['전기'], speed=11)
        self.rejected(lambda:self.record(self.c, 'pokemon', 'rec-c'), 'Swift action unavailable')
        self.rejected(lambda:CH.archive(self.e, self.t, row['id'], seconds=600, reason='in combat'), 'encounter')
        self.assertEqual(CH.archived(self.t, 'profile'), set())
        self.e.end_of_turn(self.t)
        self.e.start_of_turn(self.b, initiative_count=20)
        self.use(self.b, self.p, 'move/전광석화', face=1)
        self.next_turn(self.t)
        move_row = self.record('move/전광석화', 'move', 'rec-move')
        self.assertEqual(move_row['subject'], 'move/전광석화')
        self.e.end_of_turn(self.t)
        self.e.end_round()
        self.e.end_scene()
        CH.observe_place(self.e, self.t, 'route-1', reason='actual present place')
        self.rejected(lambda:self.record('route-2', 'place', 'elsewhere'), 'present place')
        place_row = self.record('route-1', 'place', 'rec-place')
        elapsed = self.e.elapsed_seconds
        archived = CH.archive(self.e, self.t, row['id'], seconds=600, reason='actual completed archival')
        self.assertEqual((archived['status'], archived['archive'], self.e.elapsed_seconds), ('archived', 'profile', elapsed + 600))
        self.rejected(lambda:CH.archive(self.e, self.t, row['id'], seconds=600, reason='twice'), 'already archived')
        CH.archive(self.e, self.t, move_row['id'], seconds=600, reason='actual completed archival')
        CH.archive(self.e, self.t, place_row['id'], seconds=600, reason='actual completed archival')
        duplicate = self.record(self.b, 'pokemon', 'rec-b-again')
        self.rejected(lambda:CH.archive(self.e, self.t, duplicate['id'], seconds=600, reason='duplicate'), 'already in that archive')
        self.assertEqual(CH.archived(self.t, 'profile'), {self.b.entity_id})
        self.assertEqual(CH.archived(self.t, 'technique'), {'move/전광석화'})
        self.assertEqual(CH.archived(self.t, 'travel'), {'route-1'})
        self.restore()
        self.valid()
        self.assertEqual(CH.archived(self.t, 'technique'), {'move/전광석화'})
        self.assertEqual(self.t.spec[CH.KEY]['records'][duplicate['id']]['status'], 'provisional')

    def test_archival_needs_the_owned_archive_of_that_kind(self):
        self.acquire()  # Profile Archive only
        row = self.record(self.b, 'pokemon', 'rec-b')
        self.witness('move/전광석화')
        move_row = self.record('move/전광석화', 'move', 'rec-move')
        self.rejected(lambda:CH.archive(self.e, self.t, move_row['id'], seconds=600, reason='no technique'), 'Technique Archive')
        self.rejected(lambda:CH.archive(self.e, self.t, 'chronicler-record:nobody:9', seconds=600, reason='unknown'), 'actual Chronicler record')
        self.rejected(lambda:CH.archive(self.e, self.t, row['id'], seconds=0, reason='no time'), 'seconds')
        CH.archive(self.e, self.t, row['id'], seconds=600, reason='actual completed archival')
        self.acquire(CH.TRAINING, 1)
        CH.archive(self.e, self.t, move_row['id'], seconds=600, reason='actual completed archival')
        self.assertEqual(CH.archived(self.t, 'technique'), {'move/전광석화'})
        self.restore()
        self.valid()

    def test_off_turn_record_is_a_swift_interrupt_paid_from_the_next_turn(self):
        self.whole()
        self.combat(self.b, count=20)
        trigger = {'kind':'turn', 'actor_id':self.b.entity_id, 'serial':self.b.custom_conditions['combat_turn_serial'], 'round':self.e.round_no}
        ap = AP.available(self.t)
        self.rejected(lambda:self.record(self.b, 'pokemon', 'rec-b'), 'Swift action unavailable')
        self.rejected(lambda:CH.record_interrupt(self.e, self.t, self.b, kind='pokemon', reason='actual observed subject',
            request_id='rec-b', trigger=trigger, payment='someday'), 'Interrupt payment')
        row = CH.record_interrupt(self.e, self.t, self.b, kind='pokemon', reason='actual observed subject',
            request_id='rec-b', trigger=trigger, payment='next')
        self.assertEqual((row['status'], AP.available(self.t)), ('provisional', ap - 1))
        self.assertEqual(self.e.initiative_reaction_status()['frames'], 0)
        self.e.end_of_turn(self.b)
        self.e.end_round()
        self.combat(self.t)
        self.assertEqual(self.t.budget, {'standard':1, 'shift':1, 'swift':0})
        self.restore()
        self.valid()

    def test_profile_archive_adds_two_to_the_five_social_checks_only_against_archived_subjects(self):
        self.whole()
        self.c = self.add('unrecorded foe', 'pokemon', (6, 2), side='foe', species='피카츄', types=['전기'], speed=11)
        self.archive_subject(self.b, 'pokemon', 'rec-b')
        dice = SKILLS.rank(self.e.r, self.t, '매력')[2]
        for skill in ('매력', '교활', '명령', '협박', '직감'):
            with self.subTest(skill=skill):
                passed, total = self.e.skill_check(self.t, skill, 10, fixed=[2] * dice, skill_target=self.b)
                self.assertEqual(total, 2 * dice + 2)
                passed, total = self.e.skill_check(self.t, skill, 10, fixed=[2] * dice, skill_target=self.c)
                self.assertEqual(total, 2 * dice)
        passed, total = self.e.skill_check(self.t, '통찰', 10, fixed=[2] * dice, skill_target=self.b)
        self.assertEqual(total, 2 * dice)
        passed, total = self.e.skill_check(self.t, '매력', 10, fixed=[2] * dice)
        self.assertEqual(total, 2 * dice)
        self.u = self.add('other trainer', 'trainer', (1, 6), classes=[], feats=[], exp_bank=100, speed=18)
        passed, total = self.e.skill_check(self.t, '협박', 10, fixed=[2] * dice, skill_target=self.u)
        self.assertEqual(total, 2 * dice)
        self.archive_subject(self.u, 'trainer', 'rec-u')
        passed, total = self.e.skill_check(self.t, '협박', 10, fixed=[2] * dice, skill_target=self.u)
        self.assertEqual(total, 2 * dice + 2)
        pokemon_dice = SKILLS.rank(self.e.r, self.p, '매력')[2]
        passed, total = self.e.skill_check(self.p, '매력', 10, fixed=[2] * pokemon_dice, skill_target=self.b)
        self.assertEqual(total, 2 * pokemon_dice)  # the printed bonus belongs to the Chronicler
        self.restore()
        passed, total = self.e.skill_check(self.t, '명령', 10, fixed=[2] * dice, skill_target=self.b)
        self.assertEqual(total, 2 * dice + 2)
        self.valid()

    def test_technique_archive_gives_trainer_and_owned_pokemon_two_evasion_against_archived_moves(self):
        self.whole()
        self.u = self.add('other trainer', 'trainer', (1, 6), classes=[], feats=[], exp_bank=100, speed=18)
        self.v = self.add('other owned', 'pokemon', (2, 6), trainer_id=self.u.entity_id, tutor_points=8,
            species='피카츄', types=['전기'], moves=['move/전광석화'], speed=12)
        self.archive_move('move/전광석화')
        self.combat(self.b, count=20)
        ac = self.e.r.move('move/전광석화')['ac']
        for target, archived_face_hits in ((self.p, False), (self.t, False), (self.v, True)):
            with self.subTest(target=target.name):
                evasion = target.evasion('물리', attacker=self.b, engine=self.e)
                face = ac + evasion + 1  # hits without the archive bonus, misses with +2
                hp = target.hp
                self.use(self.b, target, 'move/전광석화', face=face)
                self.assertEqual(target.hp < hp, archived_face_hits)
                self.next_turn(self.b, count=20)
        # A Move outside the archive keeps the ordinary Evasion.
        evasion = self.p.evasion('물리', attacker=self.b, engine=self.e)
        hp = self.p.hp
        self.use(self.b, self.p, 'move/몸통박치기', face=ac + evasion + 1)
        self.assertLess(self.p.hp, hp)
        self.valid()

    def test_travel_archive_grants_the_chosen_ability_and_perception_bonus_while_present(self):
        self.whole()
        self.archive_place('route-1')
        self.assertIn('날카로운눈', self.t.abilities)
        source = G.state(self.t)['sources']['chronicler-travel:' + self.t.entity_id + ':' + self.t.entity_id]
        self.assertEqual((source['rule_id'], source['lifetime'], source['chronicler_travel']['place_id']), (CH.TRAINING, 'while_owned', 'route-1'))
        self.assertNotIn('날카로운눈', self.p.abilities)  # not observed at the place yet
        CH.observe_place(self.e, self.p, 'route-1', reason='actual present place')
        self.assertIn('날카로운눈', self.p.abilities)  # Observation Party
        self.assertEqual(G.state(self.p)['sources']['chronicler-travel:' + self.t.entity_id + ':' + self.p.entity_id]['rule_id'], CH.PARTY)
        self.assertEqual(self.sensing(self.t, self.b, faces=[2] * 6)['check']['total'], 14)
        self.assertEqual(self.sensing(self.p, self.b, faces=[2] * 6)['check']['total'], 14)
        CH.observe_place(self.e, self.t, 'town', reason='actual departure')
        self.assertNotIn('날카로운눈', self.t.abilities)
        self.assertIn('날카로운눈', self.p.abilities)
        self.assertEqual(self.sensing(self.t, self.b, faces=[2] * 6)['check']['total'], 12)
        CH.observe_place(self.e, self.p, None, reason='actual unknown place')
        self.assertNotIn('날카로운눈', self.p.abilities)
        CH.observe_place(self.e, self.t, 'route-1', reason='actual return')
        self.assertIn('날카로운눈', self.t.abilities)
        self.restore()
        self.valid()
        self.assertIn('날카로운눈', self.t.abilities)
        self.assertEqual(self.sensing(self.t, self.b, faces=[2] * 6)['check']['total'], 14)
        # A grant without its present archived place is detected.
        self.t.spec.pop(CH.PLACE)
        self.assertFalse(self.e.validate_state()['valid'])

    def decisions(self, trainer, uid):
        import trainer_retraining as RETRAINING
        sources = {owned:RETRAINING.owned_source(self.e, trainer, owned) for owned in RETRAINING._owned(trainer)}
        retained = {source:list(trainer.spec['state_grants']['sources'][source].get('withdrawal_dependencies', []))
                    for owned, source in sources.items() if owned != uid}
        for child, parents in RETRAINING._native_dependencies(self.e, trainer, RETRAINING._owned(trainer)).items():
            if child != uid:
                retained[sources[child]] = [sources[parent] for parent in parents]
        return dict(request_id='retrain/' + uid, reason='actual trainer chooses retraining',
                    gm_decision={'allowed':True, 'reason':'GM reviewed prerequisites and narrative'},
                    retained_dependencies=retained)

    def test_retraining_ends_the_travel_grants_its_source_justified_and_keeps_record_history(self):
        self.whole()
        self.archive_place('route-1')
        self.archive_subject(self.b, 'pokemon', 'rec-b')
        CH.observe_place(self.e, self.p, 'route-1', reason='actual present place')
        self.assertIn('날카로운눈', self.p.abilities)
        self.e.retrain_trainer_source(self.t, CH.PARTY, **self.decisions(self.t, CH.PARTY))
        self.assertNotIn(CH.PARTY, self.t.spec['feats'])
        self.assertNotIn('날카로운눈', self.p.abilities)
        self.assertIn('날카로운눈', self.t.abilities)
        self.valid()
        # The existing one-instance retraining contract does not retire a two-rank Feature;
        # the archive-loss boundary is exercised through the owner's exclusion plan instead.
        self.rejected(lambda:self.e.retrain_trainer_source(self.t, CH.TRAINING, **self.decisions(self.t, CH.TRAINING)), 'one actual trainer acquisition')
        self.assertEqual(set(CH.owned_archives(self.t, exclude=(CH.TRAINING,))), {'profile'})
        self.assertIsNone(CH.travel_grant_expected(self.e, self.t, exclude=(CH.TRAINING,)))
        self.assertEqual(CH.archived(self.t, 'travel'), {'route-1'})
        self.assertEqual(CH.archived(self.t, 'profile'), {self.b.entity_id})
        self.restore()
        self.valid()
        self.assertNotIn(CH.PARTY, self.t.spec['feats'])
        self.assertNotIn('날카로운눈', self.p.abilities)
        self.assertIn('날카로운눈', self.t.abilities)

    def test_observation_party_is_the_pokemon_side_of_the_travel_grant(self):
        self.acquire()
        self.acquire(CH.TRAINING, 1)
        self.acquire(CH.TRAINING, 2)
        self.archive_place('route-1')
        CH.observe_place(self.e, self.p, 'route-1', reason='actual present place')
        self.assertIn('날카로운눈', self.t.abilities)
        self.assertNotIn('날카로운눈', self.p.abilities)
        self.assertEqual(self.sensing(self.p, self.b, faces=[2] * 6)['check']['total'], 12)
        self.acquire(CH.PARTY)
        self.assertIn('날카로운눈', self.p.abilities)
        self.assertEqual(self.sensing(self.p, self.b, faces=[2] * 6)['check']['total'], 14)
        self.restore()
        self.valid()
