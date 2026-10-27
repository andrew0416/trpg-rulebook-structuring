"""Whole Core Psionic Sight and independent local CSV50 on actual native state."""
from copy import copy, deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon
from native_scenario_fixture import prepare_body, assert_rejected_unchanged
import test_book_telepath_full as FIX
import test_book_telekinetic_full as TKFIX
import psionic_sight as P
import telepath as T
import telepathy_core as TC
import trainer_feature_acquisition as A
import perception_observe as O
import perception_communicate as M
import state_grants as G
import state_codec as CODEC
import world_entities as W
import invisibility_state as INV
import survivalist_features as V
import combat_timing as TIME
import warper as WP


class PsionicSightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    setUp = TKFIX.TelekineticTests.setUp
    add = TKFIX.TelekineticTests.add
    close = TKFIX.TelekineticTests.close
    begin = TKFIX.TelekineticTests.begin
    turn = TKFIX.TelekineticTests.turn
    family = FIX.TelepathTests.family
    capable = FIX.TelepathTests.capable
    acquire = FIX.TelepathTests.acquire
    valid = TKFIX.TelekineticTests.valid

    def setup(self, rank=6):
        TKFIX.TelekineticTests.setup(self, rank=rank)
        self.o = self.add('Sight observer', (1, 1))

    def sight_acquire(self, edition='core', *, actor=None, request='actual/psionic-sight'):
        return A.acquire_static(self.e, actor or self.o, P.FEATURE,
            selection={'edition': edition}, acquisition_request_id=request)

    def environment(self, target, *, observer=None, path=True, present=True, light='normal'):
        observer = observer or self.o
        V.observe_environment(self.e, observer, terrains=['urban'], light=light, reason='actual observed lighting')
        return self.e.gm.observe_sensory_environment(observer, target, paths={'visual': path},
            present=present, reason='actual current visual route')

    def sense(self, target=None, *, observer=None):
        return self.e.psionic_sight(observer or self.o, target or self.b)

    def traces(self, target=None, *, observer=None):
        result = self.sense(target, observer=observer)
        self.assertEqual(result['status'], 'observed', result)
        return result['values']['traces']

    def suggestion(self, target=None):
        self.family(T.SUGGEST)
        self.capable()
        return self.e.suggestion(self.a, target or self.b, 'Actual optional suggested thought')

    def pokemon(self, name='actual residue Pokemon', pos=(5, 4), species='잉어킹'):
        actor = Combatant(self.rules, build_pokemon(self.rules, species, 20, moves=[], abilities=[],
            extra={'name': name, 'trainer_id': self.a.entity_id}))
        self.e.gm.add_combatant(actor, pos=pos, side='party', reason='actual registered Pokemon')
        prepare_body(self.e, actor, size=actor.spec['size'], offsets=[(0, 0)], reason='actual single-cell Pokemon')
        return actor

    def invisible(self, actor):
        G.grant(actor, 'capabilities', '투명', 'fixture:invisibility:' + actor.entity_id, 'fixture')
        self.begin(actor)
        self.e.change_invisibility(actor, True, reason='actual target capability activation')

    def reject(self, operation, reason):
        return assert_rejected_unchanged(self.e, operation, reason_pattern=reason)

    def restore(self, *, fresh=False):
        ids = [actor.entity_id for actor in (self.a, self.b, self.c, self.o)]
        rules = Rules(ROOT, ruleset=self.rules.ruleset.name) if fresh else self.rules
        self.e = CODEC.load_engine(rules, json.loads(json.dumps(self.e.export_state(), ensure_ascii=False)))
        self.a, self.b, self.c, self.o = [W.actor_index(self.e)[uid] for uid in ids]
        self.valid()

    def retrain(self):
        import trainer_retraining as R
        owned = R._owned(self.o)
        sources = {uid: R.owned_source(self.e, self.o, uid) for uid in owned}
        required = R._native_dependencies(self.e, self.o, owned)
        dependencies = {sid: [sources[p] for p in required.get(uid, [])]
                        for uid, sid in sources.items() if uid != P.FEATURE}
        return self.e.retrain_trainer_source(self.o, P.FEATURE, request_id='actual/retire-sight',
            reason='actual approved retraining', gm_decision={'allowed': True, 'reason': 'GM reviews actual source'},
            retained_dependencies=dependencies)

    def test_definition_exact_catalog_span_two_source_authorities_and_single_spdef_tag(self):
        for edition in ('core', 'local_csv'):
            with self.subTest(edition=edition):
                self.setup()
                before = self.o.stats['spd']
                row = self.sight_acquire(edition)
                self.assertEqual(row['snapshot']['source']['clause_id'], P.CSV if edition == 'local_csv' else P.BOOK)
                self.assertEqual(A.STATIC_FEATURES[P.FEATURE]['catalog_span'], [903, 907])
                self.assertEqual(P.DEFINITION['stat_tags'], ['spd'])
                self.assertEqual(self.o.stats['spd'], before + 1)
                self.assertEqual(self.sight_acquire(edition)['integrity'], row['integrity'])
                __import__('items').register_feats(self.e, self.o)
                self.assertEqual(self.o.stats['spd'], before + 1)
                self.assertFalse(P.records(self.a))
                self.restore(fresh=True)

    def test_core_requires_psychic_but_csv_accepts_actual_other_elemental_connection(self):
        # An imported actual sheet may own a different elemental branch.
        self.o.spec['edge_choices'] = {'edge/원소-교감': '불꽃'}
        self.reject(self.sight_acquire, 'Psychic Elemental Connection')
        row = self.sight_acquire('local_csv')
        self.assertEqual(row['snapshot']['elemental_types'], ['불꽃'])
        self.assertFalse(row['snapshot']['mystic_senses'])
        self.restore()

    def test_csv_mystic_senses_uses_real_rank_and_declared_extended_rank_not_a_six_cap(self):
        self.o.spec.update(edges=['edge/신비한-감각'], edge_choices={})
        self.reject(self.sight_acquire, 'Psychic Elemental Connection')
        self.reject(lambda: self.e.gm.set_skill(self.o, '직감', 7, reason='undeclared rank'), 'unresolved ordinary numeric')
        self.rules.rulings.set_mech('gameplay/skill-rank-dice', 'by_rank_name.초월',
            {'rank': 7, 'dice': '7d6', 'eng': 'Transcendent'}, reason='U-001 explicit campaign rank declaration', rules=self.rules)
        self.e.gm.set_skill(self.o, '직감', 7, reason='actual declared extended Intuition')
        self.assertTrue(self.sight_acquire('local_csv')['snapshot']['mystic_senses'])
        self.restore()

    def test_source_choices_versions_rank_and_replay_reject_without_new_acquisition(self):
        for selection in ({'edition': 'official_playtest'}, {'edition': 'core', 'ignore_invisibility': True}, 'local_csv'):
            self.reject(lambda selection=selection: A.acquire_static(self.e, self.o, P.FEATURE,
                selection=selection, acquisition_request_id='bad-selection'), 'selection')
        self.reject(lambda: A.acquire_static(self.e, self.o, P.FEATURE, rank=1,
            acquisition_request_id='bad-rank'), 'Ranked')
        with patch.dict(self.rules.ruleset.unit_versions, {P.FEATURE: 'invented'}):
            with self.assertRaises(ValueError):
                self.sight_acquire()
        self.assertFalse(P.records(self.o))
        self.sight_acquire()
        self.reject(lambda: self.sight_acquire('local_csv'), 'replay')

    def test_unknown_caster_groups_actual_human_and_pokemon_traces_without_identity_leak(self):
        self.sight_acquire()
        pokemon = self.pokemon()
        self.suggestion()
        self.suggestion(pokemon)
        self.environment(self.b)
        self.environment(pokemon)
        first, second = self.traces()[0], self.traces(pokemon)[0]
        self.assertEqual(first['signature'], second['signature'])
        for result in (first, second):
            self.assertNotIn('caster_id', result)
            self.assertNotIn('power_id', result)
            self.assertNotIn(self.a.entity_id, json.dumps(result))
            self.assertNotIn(T.SUGGEST, json.dumps(result))
        self.valid()

    def test_distinct_actual_pokemon_caster_is_anonymous_and_not_a_shared_type_group(self):
        self.sight_acquire()
        self.suggestion()
        pokemon = self.pokemon()
        G.grant(pokemon, 'capabilities', 'Telepathy', 'fixture:actual-telepath', 'fixture')
        self.e.gm.set_skill(pokemon, '집중', 6, reason='actual Pokemon Focus')
        G.grant(self.c, 'capabilities', 'Telepathy', 'fixture:actual-recipient', 'fixture')
        result = self.e.project_telepathic_thought(pokemon, [self.c], 'Actual unwilling projection',
            source_policy='core_1.05', request_id='pokemon-casting')
        self.assertTrue(result['results'][0]['event']['supernatural_trace'])
        self.environment(self.b)
        self.environment(self.c)
        self.assertNotEqual(self.traces()[0]['signature'], self.traces(self.c)[0]['signature'])
        self.assertNotIn(pokemon.entity_id, str(self.traces(self.c)))
        self.valid()

    def test_visible_casting_and_result_establish_known_signature_for_core_and_csv(self):
        for edition in ('core', 'local_csv'):
            with self.subTest(edition=edition):
                self.setup()
                self.sight_acquire(edition)
                self.environment(self.a)
                self.environment(self.b)
                self.suggestion()
                first = self.traces()[0]
                self.assertEqual(first['caster_id'], self.a.entity_id)
                if edition == 'local_csv':
                    self.assertEqual(first['power_id'], T.SUGGEST)
                else:
                    self.assertNotIn('power_id', first)
                self.assertEqual(len(self.o.spec[P.KNOWLEDGE]['groups'][self.a.entity_id]['witnesses']), 1)
                self.restore(fresh=True)
                self.assertEqual(self.traces()[0], first)

    def test_later_trace_and_caster_observation_do_not_invent_witnessed_casting(self):
        self.sight_acquire()
        self.suggestion()
        self.environment(self.a)
        self.environment(self.b)
        self.assertNotIn('caster_id', self.traces()[0])
        self.e.observe_target(self.o, self.a, dict(O.native(P.FEATURE, [], mode='visual',
            information=['identity']), path='visual', vision='usable'))
        self.assertNotIn('caster_id', self.traces()[0])

    def test_known_caster_does_not_invent_familiarity_with_an_unwitnessed_power(self):
        self.sight_acquire('local_csv')
        self.environment(self.a)
        self.environment(self.b)
        self.suggestion()
        self.assertEqual(self.traces()[0]['power_id'], T.SUGGEST)
        self.environment(self.a, path=False)
        self.e.gm.set_skill(self.a, '교활', 6, reason='actual second class prerequisite')
        A.acquire_static(self.e, self.a, WP.CLASS, acquisition_request_id='actual/second-class-warper')
        self.begin()
        self.e.arm_probability_control(self.a, self.c, purpose='skill',
            decision=lambda first: first.total < 15, reroll_fixed=[6] * 6)
        self.e.skill_check(self.c, '집중', 15, fixed=[1] * 6)
        self.environment(self.c)
        trace = self.traces(self.c)[0]
        self.assertEqual(trace['caster_id'], self.a.entity_id)
        self.assertNotIn('power_id', trace)
        self.restore()

    def test_witnessed_power_is_identified_from_unknown_other_caster_without_identity_leak(self):
        self.sight_acquire('local_csv')
        self.environment(self.a)
        self.environment(self.b)
        self.suggestion()
        first = self.traces()[0]
        self.assertEqual((first['caster_id'], first['power_id']), (self.a.entity_id, T.SUGGEST))
        # No visual route to the second actual caster was observed. The old
        # witnessed power remains familiar, but this signature is anonymous.
        self.family(T.SUGGEST, actor=self.c)
        self.begin(self.c)
        self.e.activate_telepath(self.c)
        self.e.suggestion(self.c, self.b, 'Actual second caster using the familiar power')
        second = self.traces()[-1]
        self.assertNotEqual(first['signature'], second['signature'])
        self.assertEqual(second['power_id'], T.SUGGEST)
        self.assertNotIn('caster_id', second)
        self.assertNotIn(self.c.entity_id, json.dumps(second))
        self.assertFalse(self.o.spec[P.KNOWLEDGE]['groups'][self.c.entity_id]['witnesses'])
        self.restore(fresh=True)
        self.assertEqual(self.traces()[-1], second)

    def test_actual_illusion_hides_caster_identity_but_not_witnessed_power_and_result(self):
        self.sight_acquire('local_csv')
        self.e.gm.set_ability(self.a, '일루전', reason='actual imported Core Illusion ability')
        self.e.register_abilities(self.a)
        self.begin()
        self.e.mark_illusion_appearance(self.a, self.c)
        self.e.mimic_illusion_appearance(self.a, self.c)
        self.environment(self.a)
        self.environment(self.b)
        self.suggestion()
        trace = self.traces()[0]
        self.assertEqual(trace['power_id'], T.SUGGEST)
        self.assertNotIn('caster_id', trace)
        witness = self.o.spec[P.KNOWLEDGE]['groups'][self.a.entity_id]['witnesses'][0]
        self.assertFalse(witness['caster_identified'])
        self.assertEqual(witness['caster_observation']['status'], 'partial')
        self.assertTrue(witness['target_observation']['values']['presence'])
        self.e.dismiss_illusion_appearance(self.a)
        self.assertNotIn('caster_id', self.traces()[0])
        valid_save = self.e.export_state()
        original = deepcopy(self.o.spec[P.KNOWLEDGE])
        for change, reason in ((lambda w: w.update(caster_identified=True), 'visible caster knowledge'),
                               (lambda w: w['target_observation']['values']['traces'][0].update(signature='forged'), 'observed trace instance')):
            self.o.spec[P.KNOWLEDGE] = deepcopy(original)
            data = self.o.spec[P.KNOWLEDGE]
            change(data['groups'][self.a.entity_id]['witnesses'][0])
            data['sha256'] = __import__('resolution_transaction').request_fingerprint(data['groups'])
            with self.assertRaisesRegex(ValueError, reason):
                P.validate_world(self.e, W.actor_index(self.e))
            with self.assertRaises(CODEC.StateCodecError):
                self.e.export_state()
            forged_save = deepcopy(valid_save)
            def mapping(ref):
                node = forged_save['nodes'][ref['$ref']]
                self.assertEqual(node['kind'], 'dict')
                return node['items']
            def field(ref, key):
                return next(pair for pair in mapping(ref) if pair[0] == key)
            saved_observer = next(node for node in forged_save['nodes'].values()
                if node['kind'] == 'actor' and node['entity_id'] == self.o.entity_id)
            knowledge = field(field(saved_observer['attrs'], 'spec')[1], P.KNOWLEDGE)[1]
            group = field(field(knowledge, 'groups')[1], self.a.entity_id)[1]
            witnesses = forged_save['nodes'][field(group, 'witnesses')[1]['$ref']]
            self.assertEqual(witnesses['kind'], 'list')
            saved_witness = witnesses['items'][0]
            if reason == 'visible caster knowledge':
                leaf = field(saved_witness, 'caster_identified')
                self.assertIs(leaf[1], False)
                leaf[1] = True
            else:
                observed = field(field(saved_witness, 'target_observation')[1], 'values')[1]
                traces = forged_save['nodes'][field(observed, 'traces')[1]['$ref']]
                self.assertEqual(traces['kind'], 'list')
                trace = traces['items'][0]
                self.assertEqual(field(trace, 'instance_id')[1], witness['instance_id'])
                field(trace, 'signature')[1] = 'forged'
            # Preserve the digest so cold-load must reject the actual witness
            # semantics, not an unrelated node or a stale knowledge checksum.
            field(knowledge, 'sha256')[1] = data['sha256']
            with self.assertRaises(CODEC.StateCodecError):
                CODEC.load_engine(self.rules, forged_save)
        self.o.spec[P.KNOWLEDGE] = original
        self.restore()
        self.assertNotIn('caster_id', self.traces()[0])

    def test_blocked_or_absent_caster_at_casting_never_unlocks_identity(self):
        for path, present in ((False, True), (None, True), (True, False), (True, None)):
            with self.subTest(path=path, present=present):
                self.setup()
                self.sight_acquire()
                self.environment(self.a, path=path, present=present)
                self.environment(self.b)
                self.suggestion()
                self.assertNotIn('caster_id', self.traces()[0])

    def test_unknown_path_blocked_absent_darkness_and_external_blindness_disclose_no_traces(self):
        self.sight_acquire()
        self.suggestion()
        self.assertEqual(self.sense()['reason'], 'path_unknown')
        self.environment(self.b, path=False)
        self.assertEqual(self.sense()['reason'], 'path_blocked')
        self.environment(self.b, present=False)
        self.assertEqual(self.sense()['values'], {'presence': False})
        self.environment(self.b, light='complete_darkness')
        self.assertEqual(self.sense()['reason'], 'vision_blocked')
        self.environment(self.b)
        self.assertTrue(self.e.apply_status(self.o, '실명', parameters={'cause': 'external'}))
        self.assertEqual(V.vision(self.e, self.o)[0], 'ordinary')
        self.assertIsNone(O.route(self.e, self.o, self.b, P.declaration(self.o))[2])
        self.assertTrue(self.e.apply_status(self.o, '완전 실명', parameters={'cause': 'external'}))
        self.assertEqual(self.sense()['reason'], 'vision_blocked')
        self.assertNotIn(P.KNOWLEDGE, self.o.spec)

    def test_actual_world_movement_invalidates_path_and_finite_provider_cannot_be_relabelled(self):
        self.sight_acquire()
        self.suggestion()
        self.environment(self.b)
        self.assertTrue(self.traces())
        self.e.gm.set_position(self.b, (7, 2), reason='actual target moved behind a different path')
        self.assertEqual(self.sense()['reason'], 'path_unknown')
        self.environment(self.b)
        for mutate in (lambda d: d.update(information=['identity']), lambda d: d.update(path=None),
                       lambda d: d.update(mode='mental'), lambda d: d.update(check={'skill': '집중', 'dc': 0, 'purpose': 'invented'})):
            value = P.declaration(self.o)
            mutate(value)
            self.reject(lambda: self.e.observe_target(self.o, self.b, value), 'provider|declaration')
        self.reject(lambda: self.e.psionic_sight(copy(self.o), self.b), 'actual')
        self.reject(lambda: self.e.psionic_sight(self.o, copy(self.b)), 'actual')
        W.register_object(self.e, 'actual:object-only', location={'kind': 'grid', 'cell': (9, 9)},
            weight_kg=1, reason='actual object outside Human or Pokemon target scope')
        self.reject(lambda: self.e.psionic_sight(self.o, self.e._physical_objects['actual:object-only']), 'actual')

    def test_no_trace_is_observed_absence_and_ordinary_psychic_move_is_not_a_producer(self):
        self.sight_acquire()
        self.environment(self.b)
        self.assertEqual(self.sense()['values'], {'presence': False, 'traces': []})
        self.e.gm.set_move(self.a, 'move/염동력', reason='actually learned ordinary Psychic Move')
        self.begin()
        with patch.object(Engine, 'd20', return_value=18):
            self.e.use_move(self.a, self.b, 'move/염동력', set_damage=True)
        self.assertFalse(T.live(self.b, 'psychic_residue'))

    def test_real_core_telepathy_unwilling_failed_attempt_leaves_trace_once_willing_does_not(self):
        self.sight_acquire()
        self.capable()
        M.permission(self.e, self.b, self.a, TC.SOURCE, True, reason='willing actual target')
        TC.awareness(self.e, self.a, self.b, True, reason='actual target awareness')
        self.e.read_telepathic_thought(self.a, self.b, source_policy='core_1.05', request_id='willing')
        self.assertFalse(T.live(self.b, 'psychic_residue'))
        M.permission(self.e, self.b, self.a, TC.SOURCE, False, reason='actual target refuses')
        options = {'sender': {'fixed': [1] * 6}, 'recipient': {'fixed': [6] * 6}}
        first = self.e.read_telepathic_thought(self.a, self.b, source_policy='core_1.05',
            request_id='unwilling-failed', roll_options=options)
        self.assertEqual(first['reason'], 'opposed_failed')
        self.assertEqual(len(T.live(self.b, 'psychic_residue')), 1)
        self.assertTrue(self.e.read_telepathic_thought(self.a, self.b, source_policy='core_1.05',
            request_id='unwilling-failed', roll_options=options)['replayed'])
        self.assertEqual(len(T.live(self.b, 'psychic_residue')), 1)
        self.environment(self.b)
        self.assertNotIn('caster_id', self.traces()[0])
        self.restore()

    def test_core_blocked_or_out_of_range_never_creates_an_unattempted_trace(self):
        self.sight_acquire()
        self.capable()
        M.permission(self.e, self.b, self.a, TC.SOURCE, False, reason='actual unwilling target')
        self.e.gm.set_position(self.b, (15, 2), reason='outside Focus six twice range')
        result = self.e.read_telepathic_thought(self.a, self.b, source_policy='core_1.05', request_id='outside')
        self.assertNotEqual(result['status'], 'delivered')
        self.assertIsNone(result['event'])
        self.assertFalse(T.live(self.b, 'psychic_residue'))
        self.e.gm.set_position(self.b, (6, 2), reason='actual in-range target')
        G.grant(self.b, 'capabilities', 'Mindlock', 'fixture:actual-mindlock', 'fixture')
        result = self.e.read_telepathic_thought(self.a, self.b, source_policy='core_1.05', request_id='blocked')
        # Mindlock blocks reading after an actual unwilling attempt; unlike
        # out-of-range routing above, that attempt still leaves Core308 residue.
        self.assertEqual(result['reason'], 'receiver_blocked')
        self.assertTrue(result['event']['supernatural_trace'])
        self.assertEqual(len(T.live(self.b, 'psychic_residue')), 1)
        self.valid()

    def test_actual_probability_reroll_uses_existing_trace_and_player_information_boundary(self):
        self.sight_acquire()
        self.e.gm.set_skill(self.c, '교활', 6, reason='actual Warper prerequisite')
        A.acquire_static(self.e, self.c, WP.CLASS, acquisition_request_id='actual/warper')
        self.begin(self.c)
        self.e.arm_probability_control(self.c, self.a, purpose='skill',
            decision=lambda first: first.total < 15, reroll_fixed=[6] * 6)
        self.e.skill_check(self.a, '집중', 15, fixed=[1] * 6)
        self.assertEqual(len(T.live(self.a, 'psychic_residue')), 1)
        self.environment(self.a)
        self.assertNotIn('caster_id', self.traces(self.a)[0])
        self.valid()

    def test_native_warning_reaction_creates_a_trace_on_actual_moved_ally(self):
        self.sight_acquire()
        self.family(T.WARNING)
        self.capable()
        self.e.gm.add_combatant(self.b, side='party', reason='actual ally attack recipient')
        self.e.gm.set_position(self.c, (5, 2), reason='actual adjacent attack origin')
        self.e.arm_telepath_reaction(self.a, T.WARNING, paths={self.b.entity_id: [(6, 3)]})
        self.begin(self.c)
        with patch.object(Engine, 'd20', return_value=18):
            self.e.use_move(self.c, self.b, 'move/몸통박치기', set_damage=True)
        self.assertEqual(self.b.pos, (6, 3))
        self.environment(self.b)
        self.assertEqual(len(self.traces()), 1)
        self.assertNotIn('caster_id', self.traces()[0])

    def test_suggestion_release_scene_and_clock_do_not_invent_residue_expiration(self):
        self.sight_acquire()
        row = self.suggestion()
        self.begin()
        self.e.release_suggestion(self.a, row['id'])
        self.close()
        self.e.end_scene()
        self.e.advance_time(86400)
        self.environment(self.b)
        self.assertEqual(len(self.traces()), 1)
        trace = T.live(self.b, 'psychic_residue')[0]
        self.assertEqual(trace['effect_instance']['lifetime'], {'boundary': 'unspecified'})
        TIME.expire(self.e, self.b, trace, event={'kind': 'gm_observed_residue_end', 'reason': 'actual world trace erased'})
        self.assertEqual(self.sense()['values'], {'presence': False, 'traces': []})
        self.restore()

    def test_csv_ignores_actual_target_invisibility_but_core_and_other_observer_do_not(self):
        self.sight_acquire('local_csv')
        self.sight_acquire('core', actor=self.c, request='actual/other-sight')
        self.suggestion()
        self.invisible(self.b)
        self.environment(self.b)
        self.environment(self.b, observer=self.c)
        self.assertEqual(len(self.traces()), 1)
        self.assertEqual(self.sense(observer=self.c)['reason'], 'target_invisible')
        self.assertEqual(INV.accuracy_penalty(self.e, self.b, observer=self.o), 0)
        self.assertEqual(INV.accuracy_penalty(self.e, self.b, observer=self.c), 4)
        self.assertEqual(INV.accuracy_penalty(self.e, self.b), 4)
        self.assertTrue(INV.projection(self.e, self.b)['active'])

    def test_csv_native_single_and_multi_accuracy_ignore_only_target_invisibility(self):
        self.sight_acquire('local_csv', actor=self.a)
        move = self.rules.move('move/물대포')
        base = next(n for n in range(2, 16) if self.e.accuracy_check(self.a, self.b, move, fixed_roll=n)[0])
        self.invisible(self.b)
        self.assertTrue(self.e.accuracy_check(self.a, self.b, move, fixed_roll=base)[0])
        for multi in (False, True):
            self.begin()
            before = self.b.hp
            with patch.object(Engine, 'd20', return_value=base):
                if multi:
                    self.e.use_move_on(self.a, self.b, 'move/물대포', [self.b], set_damage=True)
                else:
                    self.e.use_move(self.a, self.b, 'move/물대포', set_damage=True)
            self.assertLess(self.b.hp, before)
            self.assertEqual(self.a.budget['standard'], 0)
        self.valid()

    def test_csv_does_not_let_invisible_observer_use_moves_or_erase_own_invisibility(self):
        self.sight_acquire('local_csv', actor=self.a)
        self.invisible(self.a)
        self.assertFalse(P.ignores_invisibility(self.e, self.a, self.a))
        self.assertEqual(INV.accuracy_penalty(self.e, self.a, observer=self.a), 4)
        self.reject(lambda: self.e.use_move(self.a, self.b, 'move/물대포'), 'invisibility')
        self.assertTrue(INV.projection(self.e, self.a)['active'])

    def test_csv_uncertain_target_invisibility_does_not_erase_flat_body_or_visual_barriers(self):
        self.sight_acquire('local_csv')
        self.suggestion()
        self.invisible(self.b)
        self.close()
        self.e.end_round()
        self.e.advance_time(225)
        self.begin()
        self.e.end_encounter()
        self.assertIsNone(INV.projection(self.e, self.b)['active'])
        self.assertEqual(INV.accuracy_penalty(self.e, self.b, observer=self.o), 0)
        with self.assertRaisesRegex(ValueError, 'elapsed-time'):
            INV.accuracy_penalty(self.e, self.b, observer=self.c)
        self.environment(self.b, path=False)
        self.assertEqual(self.sense()['reason'], 'path_blocked')
        self.environment(self.b, light='complete_darkness')
        self.assertEqual(self.sense()['reason'], 'vision_blocked')
        self.environment(self.b)
        self.assertEqual(len(self.traces()), 1)
        # Separate accuracy reasons remain owned by their actual native owner.
        gengar = self.pokemon(name='actual flat Gengar', pos=(9, 9), species='팬텀')
        self.e.gm.observe_loyalty(gengar, 6, reason='actual obedient Pokemon')
        G.grant(gengar, 'capabilities', 'Shadow Meld', 'fixture:actual-shadow', 'fixture')
        self.begin(gengar)
        self.e.change_body_mode(gengar, 'shadow', reason='actual Gengar flattened into its surface shadow')
        self.assertEqual(INV.accuracy_penalty(self.e, gengar, observer=self.o), 4)
        self.restore()

    def test_unavailable_or_raw_unacquired_sight_does_not_supply_player_permission(self):
        self.invisible(self.b)
        self.o.spec['feats'].append(P.FEATURE)
        with self.assertRaisesRegex(ValueError, 'actual acquired source'):
            P.validate_actor(self.o)
        self.o.spec['feats'].remove(P.FEATURE)
        self.sight_acquire('local_csv')
        self.e.gm.set_hp(self.o, 0, reason='actual fainted observer')
        self.assertEqual(INV.accuracy_penalty(self.e, self.b, observer=self.o), 4)
        self.reject(self.sense, 'available Psionic Sight')

    def test_withdrawal_revokes_only_source_stat_and_invisibility_permission_not_actual_residue(self):
        before = self.o.stats['spd']
        self.sight_acquire('local_csv')
        self.suggestion()
        self.invisible(self.b)
        self.assertEqual(INV.accuracy_penalty(self.e, self.b, observer=self.o), 0)
        self.retrain()
        self.assertEqual(self.o.stats['spd'], before)
        self.assertEqual(INV.accuracy_penalty(self.e, self.b, observer=self.o), 4)
        self.assertTrue(T.live(self.b, 'psychic_residue'))
        self.reject(self.sense, 'acquired Psionic Sight')
        self.restore()

    def test_current_selection_unknown_version_and_unacquired_other_observer_do_not_gain_permission(self):
        self.sight_acquire('local_csv')
        self.invisible(self.b)
        self.assertEqual(INV.accuracy_penalty(self.e, self.b, observer=self.a), 4)
        self.assertFalse(P.ignores_invisibility(self.e, None, self.b))
        with patch.dict(self.rules.ruleset.unit_versions, {P.FEATURE: 'unreviewed'}):
            with self.assertRaises(ValueError):
                INV.accuracy_penalty(self.e, self.b, observer=self.o)
        selected = self.rules._selected_rule
        with patch.object(self.rules, '_selected_rule', side_effect=lambda uid, **kw: uid + '/other' if uid == P.FEATURE else selected(uid, **kw)):
            with self.assertRaises(ValueError):
                INV.accuracy_penalty(self.e, self.b, observer=self.o)
        self.assertEqual(INV.accuracy_penalty(self.e, self.b, observer=self.o), 0)

    def test_cold_and_gm_restore_keep_known_and_anonymous_groups_separate(self):
        self.sight_acquire()
        self.suggestion()
        self.environment(self.b)
        anonymous = self.traces()[0]
        self.e.gm.snapshot('anonymous-sight')
        self.environment(self.a)
        self.suggestion()
        self.assertEqual(self.traces()[0]['caster_id'], self.a.entity_id)
        self.e.gm.restore('anonymous-sight', reason='actual earlier observed world')
        self.assertEqual(self.traces()[0], anonymous)
        self.restore(fresh=True)
        self.assertEqual(self.traces()[0], anonymous)

    def test_forged_signature_knowledge_and_spdef_provenance_reject_native_save(self):
        self.sight_acquire()
        self.suggestion()
        self.environment(self.b)
        self.traces()
        original = deepcopy(self.o.spec[P.KNOWLEDGE])
        self.o.spec[P.KNOWLEDGE]['groups'][self.a.entity_id]['witnesses'].append({'caster_id': self.a.entity_id})
        with self.assertRaises(ValueError):
            self.e.export_state()
        self.o.spec[P.KNOWLEDGE] = original
        source, _ = P.records(self.o)[0]
        self.o.spec[G.KEY]['stat_sources']['spd']['sources'][source]['acquisition_stat_tag']['delta'] = 2
        with self.assertRaises(ValueError):
            self.e.export_state()

    def test_late_witness_failure_rolls_back_casting_cost_trace_knowledge_and_rng(self):
        self.sight_acquire()
        self.environment(self.a)
        self.environment(self.b)
        self.family(T.SUGGEST)
        self.capable()
        original = P.witness_created
        def fail(*args):
            original(*args)
            raise ValueError('late actual signature failure')
        with patch.object(P, 'witness_created', side_effect=fail):
            self.reject(lambda: self.e.suggestion(self.a, self.b, 'actual failed transaction'), 'late actual signature')
        self.assertFalse(T.live(self.b, 'psychic_residue'))
        self.assertNotIn(P.KNOWLEDGE, self.o.spec)


if __name__ == '__main__':
    unittest.main()
