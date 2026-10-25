"""Whole Type Expertise: actual ranked acquisition and native STAB consumers."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from grid import Grid
from native_scenario_fixture import prepare_body, assert_rejected_unchanged
import acquired_features as ACQUIRED
import state_codec as CODEC
import state_grants as GRANTS
import trainer_feature_acquisition as T
import type_expertise as TYPE
import world_entities as WORLD

FIRE = ['move/불꽃세례', 'move/화염방사', 'move/도깨비불']
WATER = ['move/물대포', 'move/거품', 'move/껍질에숨기']
NORMAL = ['move/몸통박치기', 'move/전광석화', 'move/단단해지기']


class TypeExpertiseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def setUp(self):
        self.setup()

    def setup(self, *, rules=None, level=30, moves=None, types=None, edges=()):
        self.e = Engine(rules or self.rules, seed=1422026)
        self.e.grid = Grid(12, 12)
        actors = []
        for number in range(2):
            spec = {'id': 'trainer/type-expertise-' + str(number),
                    'name': 'Type Expertise ' + str(number), 'kind': 'trainer',
                    'level': level if number == 0 else 30, 'size': '중형', 'weight_kg': 30,
                    'weight_class': 3, 'stats': {'hp': 100, 'atk': 20, 'def': 20,
                        'spa': 20, 'spd': 20, 'spe': 30 - number * 10},
                    'types': list(types or []) if number == 0 else ['노말'],
                    'moves': list(FIRE + WATER if moves is None else moves) if number == 0 else NORMAL[:1],
                    'abilities': [], 'classes': [], 'feats': [],
                    'edges': list(edges) if number == 0 else [],
                    'skills': {'전투': 6, '집중': 6, '곡예': 6, '육상': 6, '은신': 6},
                    'movement': {'land': 6, 'power': 4, 'sky': 0, 'high_jump': 0},
                    'exp_bank': 100}
            actor = Combatant(self.e.r, spec)
            self.e.gm.add_combatant(actor, pos=(3 + number, 3),
                side='party' if number == 0 else 'foe', reason='actual Type Expertise test participant')
            prepare_body(self.e, actor, size='중형', offsets=[(0, 0)], reason='observed single-cell body')
            actors.append(actor)
        self.a, self.t = actors

    def acquire(self, *, rank=1, chosen='불꽃', stat='atk', edition='core', moves=None, request=None):
        selection = {'edition': edition, 'type': chosen, 'stat': stat}
        if moves is not None:
            selection['moves'] = list(moves)
        return T.acquire_static(self.e, self.a, TYPE.FEATURE, rank=rank,
            selection=selection, acquisition_request_id=request or 'type-expertise/' + str(rank))

    def reject(self, operation, reason):
        return assert_rejected_unchanged(self.e, operation, reason_pattern=reason)

    def turn(self):
        if self.e._active_turn_actor is not None:
            self.e.end_of_turn(self.e._active_turn_actor)
        if self.e.round_start_seconds is not None:
            self.e.end_round()
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a, initiative_count=30)

    def restore(self, *, fresh=False):
        ids = [self.a.entity_id, self.t.entity_id]
        rules = Rules(ROOT, ruleset=self.e.r.ruleset.name) if fresh else self.e.r
        payload = json.loads(json.dumps(self.e.export_state(), ensure_ascii=False))
        self.e = CODEC.load_engine(rules, payload)
        self.a, self.t = [WORLD.actor_index(self.e)[uid] for uid in ids]
        result = self.e.validate_state()
        self.assertTrue(result['valid'], result['issues'])

    def test_core_translation_csv_each_keep_actual_choice_two_ranks_and_no_defensive_type(self):
        for edition in ('core', 'local_translation', 'local_csv'):
            with self.subTest(edition=edition):
                self.setup()
                first = self.acquire(edition=edition, moves=FIRE if edition == 'local_translation' else None)
                second = self.acquire(rank=2, chosen='물', stat='spd', edition=edition,
                    moves=WATER if edition == 'local_translation' else None)
                self.assertEqual(first['snapshot']['source']['clause_id'], TYPE.CSV if edition == 'local_csv' else TYPE.BOOK)
                self.assertEqual(second['snapshot']['selection']['type'], '물')
                self.assertEqual(ACQUIRED.feature_rank(self.a, TYPE.FEATURE), 2)
                self.assertEqual(ACQUIRED.owned_rule_count(self.a, TYPE.FEATURE), 2)
                self.assertEqual(self.a.stats['atk'], 21)
                self.assertEqual(self.a.stats['spd'], 21)
                self.assertEqual(self.a.types, [])
                self.assertEqual(self.e.type_multiplier('불꽃', self.a)[0], 1)
                self.assertEqual(self.e.damage_base(self.a, self.e.r.move(FIRE[0])), 6)
                self.assertEqual(self.e.damage_base(self.a, self.e.r.move(WATER[0])), 6)
                self.restore()

    def test_all_six_stat_tags_apply_once_per_rank_and_replay_has_no_second_effect(self):
        for stat in TYPE.STATS:
            with self.subTest(stat=stat):
                self.setup()
                before = self.a.stats[stat]
                row = self.acquire(stat=stat)
                self.assertEqual(self.acquire(stat=stat)['integrity'], row['integrity'])
                self.assertEqual(self.a.stats[stat], before + 1)
                self.acquire(rank=2, stat=stat)
                self.assertEqual(self.a.stats[stat], before + 2)
                self.assertEqual(self.e.damage_base(self.a, self.e.r.move(FIRE[0])), 6)
                self.restore()

    def test_level_next_rank_maximum_and_source_specific_selection_reject_atomically(self):
        self.setup(level=8)
        self.reject(self.acquire, 'Level 9')
        self.e.gm.set_level(self.a, 9, reason='actual earned trainer level')
        self.reject(lambda: self.acquire(rank=2), 'next actual rank')
        self.reject(lambda: self.acquire(rank=True), 'printed domain')
        self.reject(lambda: self.acquire(chosen='전기'), 'three known')
        self.reject(lambda: self.acquire(stat='accuracy'), 'stat choice')
        self.reject(lambda: self.acquire(edition='local_translation', moves=FIRE[:2]), 'exactly three')
        self.reject(lambda: self.acquire(edition='local_translation', moves=[FIRE[0]] * 3), 'distinct')
        self.reject(lambda: self.acquire(edition='local_translation', moves=[*FIRE[:2], WATER[0]]), 'three known')
        self.reject(lambda: self.acquire(moves=FIRE), 'source-specific')
        self.acquire()
        self.acquire(rank=2, chosen='물')
        self.reject(lambda: self.acquire(rank=3), 'printed domain')

    def test_choice_and_source_replay_cannot_change_or_relabel_an_acquired_rank(self):
        self.acquire(edition='local_translation', moves=FIRE)
        self.reject(lambda: self.acquire(chosen='물', edition='local_translation', moves=WATER), 'replay')
        self.reject(lambda: self.acquire(edition='local_csv'), 'replay')
        self.reject(lambda: self.acquire(stat='spe', edition='local_translation', moves=FIRE), 'replay')
        self.reject(lambda: self.acquire(request='new-request'), 'next actual rank')

    def test_actual_learned_temporary_grant_qualifies_but_permission_and_overlay_do_not(self):
        self.setup(moves=FIRE[:2])
        GRANTS.grant_moves(self.a, [FIRE[2]], 'test:permission', 'effect',
            owner_id=self.a.entity_id, lifetime='user_turn_end', rule_id=FIRE[2], mode='permission')
        GRANTS.overlay(self.a, 'test:display', moves=FIRE)
        self.reject(self.acquire, 'three known')
        GRANTS.revoke(self.a, 'test:display', engine=self.e)
        GRANTS.revoke(self.a, 'test:permission', engine=self.e)
        GRANTS.grant_moves(self.a, [FIRE[2]], 'test:temporary-learned', 'effect',
            owner_id=self.a.entity_id, lifetime='user_turn_end', rule_id=FIRE[2], mode='learned')
        self.acquire()
        GRANTS.revoke(self.a, 'test:temporary-learned', engine=self.e)
        self.assertNotIn(FIRE[2], self.a.moves)
        self.assertEqual(self.e.damage_base(self.a, self.e.r.move(FIRE[0])), 6)
        self.reject(lambda: self.acquire(rank=2), 'three known')
        self.restore()

    def test_actual_martial_acquisition_produces_qualifying_learned_moves(self):
        self.setup(moves=['move/태권당수'], edges=['edge/기본-무술'])
        T.acquire_martial_artist(self.e, self.a, acquisition_request_id='actual/martial',
            selected_ability='철주먹', lifecycle_policy=T.LIFECYCLE_WHILE_OWNED)
        T.acquire_static(self.e, self.a, 'feat/무술-훈련', rank=1,
            branch=['move/마하펀치', 'move/두번차기'], acquisition_request_id='actual/martial-training')
        row = self.acquire(chosen='격투')
        self.assertTrue({'move/태권당수', 'move/마하펀치', 'move/두번차기'} <= set(row['snapshot']['known_moves']))
        self.assertTrue(TYPE.grants_stab(self.e, self.a, self.e.r.move('move/태권당수')))
        self.restore()

    def test_native_move_uses_selected_type_for_all_moves_and_pays_actual_action(self):
        self.acquire(edition='local_translation', moves=FIRE)
        self.e.gm.set_move(self.a, 'move/불꽃펀치', reason='actual later learned Fire Move')
        self.turn()
        before = self.t.hp
        result = self.e.use_move(self.a, self.t, 'move/불꽃펀치', set_damage=True)
        self.assertGreater(result, 0)
        self.assertLess(self.t.hp, before)
        self.assertEqual(self.a.budget['standard'], 0)
        self.assertTrue(any('자속보정' in line for line in self.e.log_lines))
        self.assertEqual(self.a.types, [])
        self.assertFalse(TYPE.grants_stab(self.e, self.a, self.e.r.move(WATER[0])))

    def test_repeated_type_and_existing_stab_never_stack_and_other_actor_gets_no_grant(self):
        self.setup(moves=NORMAL, types=['노말'])
        base = self.e.damage_base(self.a, self.e.r.move(NORMAL[0]))
        self.acquire(chosen='노말', stat='spd')
        self.acquire(rank=2, chosen='노말', stat='spe')
        self.assertEqual(self.e.damage_base(self.a, self.e.r.move(NORMAL[0])), base)
        self.assertEqual(len(TYPE.records(self.a)), 2)
        self.assertFalse(TYPE.grants_stab(self.e, self.t, self.e.r.move(NORMAL[0])))
        self.e.gm.set_types(self.a, ['물'], reason='actual independently changed defensive Type')
        self.assertEqual(self.e.damage_base(self.a, self.e.r.move(NORMAL[0])), base)
        self.assertEqual(self.a.types, ['물'])

    def test_struggle_and_actual_weapon_bound_attacks_keep_native_stab_exclusions(self):
        import optional_weapon_framework as WEAPONS
        import weapon_actions
        self.setup(moves=NORMAL)
        raw = self.e.r.move('struggle')
        struggle_base = self.e.damage_base(self.a, raw)
        self.acquire(chosen='노말', stat='spd')
        self.assertEqual(self.e.damage_base(self.a, raw), struggle_base)
        self.turn()
        self.assertGreater(self.e.use_move(self.a, self.t, 'struggle', set_damage=True), 0)
        self.assertFalse(any('자속보정' in line for line in self.e.log_lines))
        WORLD.register_object(self.e, 'object/expertise-weapon', location={'kind': 'unknown'},
            owner_id=self.a.entity_id, weight_kg=1, reason='observed actual weapon')
        WEAPONS.observe_weapon(self.e, self.a, 'object/expertise-weapon', name='actual mace',
            kind='소형 근접무기', grade='간단', arcane=False, metal=True,
            moves=['move/강타'], reason='actual weapon form and granted Move')
        key = WEAPONS.equip(self.e, self.a, 'object/expertise-weapon')
        for mid in (key, 'move/강타'):
            prepared = weapon_actions.prepare(self.e, self.a, self.e.r.move(mid), 'object/expertise-weapon')
            self.assertTrue(weapon_actions.excludes_stab(prepared))
            expected = prepared['damage_base'] + weapon_actions.damage_bonus(prepared)
            self.assertEqual(self.e.damage_base(self.a, prepared), expected)
        self.turn()
        self.assertGreater(self.e.use_move(self.a, self.t, 'move/강타', weapon_id='object/expertise-weapon', set_damage=True), 0)
        self.assertFalse(any('자속보정' in line for line in self.e.log_lines))

    def test_scene_round_day_and_forgotten_moves_do_not_rechoose_or_expire_static_acquisition(self):
        first = self.acquire()
        for move in FIRE:
            self.e.gm.set_move(self.a, move, add=False, reason='actual forgotten acquisition prerequisite Move')
        self.turn()
        self.e.end_of_turn(self.a)
        self.e.end_encounter(self.e.everyone)
        self.e.advance_time(86400)
        self.assertEqual(TYPE.records(self.a)[0][1]['integrity'], first['integrity'])
        self.assertTrue(TYPE.grants_stab(self.e, self.a, self.e.r.move(FIRE[0])))
        self.restore(fresh=True)
        self.assertTrue(TYPE.grants_stab(self.e, self.a, self.e.r.move(FIRE[0])))

    def test_gm_and_cold_restore_preserve_rank_choices_stats_and_native_stab(self):
        self.acquire(stat='hp')
        self.acquire(rank=2, chosen='물', stat='spe')
        original = deepcopy(TYPE.records(self.a))
        self.e.gm.snapshot('expertise')
        self.e.gm.set_move(self.a, FIRE[0], add=False, reason='actual later forgetting')
        self.e.gm.restore('expertise', reason='actual restored scene')
        self.assertEqual(TYPE.records(self.a), original)
        self.restore(fresh=True)
        self.assertEqual(TYPE.records(self.a), original)
        self.assertEqual(self.a.stats['hp'], 101)
        self.assertEqual(self.a.stats['spe'], 31)
        self.assertEqual(self.e.damage_base(self.a, self.e.r.move(WATER[0])), 6)

    def test_tampered_acquisition_and_stat_provenance_cannot_be_saved(self):
        self.acquire()
        state = self.e.export_state()
        # Corrupt the actual live receipt in isolation; the native serializer must reject it.
        sid, _ = TYPE.records(self.a)[0]
        selection = self.a.spec[GRANTS.KEY]['sources'][sid]['static_acquisition']['snapshot']['selection']
        original_type = selection['type']
        try:
            selection['type'] = '물'
            with self.assertRaisesRegex(ValueError, 'integrity'):
                T.validate_actor(self.a)
            with self.assertRaises(ValueError):
                self.e.export_state()
        finally:
            selection['type'] = original_type
        self.assertEqual(self.e.export_state(), state)
        original = self.a.spec[GRANTS.KEY]['stat_sources']['atk']['sources'].pop(sid)
        try:
            with self.assertRaisesRegex(ValueError, 'stat tag'):
                T.validate_actor(self.a)
        finally:
            self.a.spec[GRANTS.KEY]['stat_sources']['atk']['sources'][sid] = original
        self.restore()

    def test_rank2_retraining_retires_only_selected_rank_then_reacquisition_and_rank1_removal(self):
        first = self.acquire(stat='atk')
        second = self.acquire(rank=2, chosen='물', stat='spe')
        lower = TYPE.records(self.a)[0][0]
        options = {'request_id': 'type/retrain-2', 'reason': 'actual retraining',
                   'gm_decision': {'allowed': True, 'reason': 'GM reviewed this acquisition'},
                   'retained_dependencies': {lower: []}}
        self.reject(lambda: self.e.retrain_trainer_source(self.a, TYPE.FEATURE, rank=1, **options), 'higher rank')
        result = self.e.retrain_trainer_source(self.a, TYPE.FEATURE, rank=2, **options)
        self.assertEqual(result['xp_paid'], 2)
        self.assertEqual(self.a.spec['exp_bank'], 98)
        self.assertEqual(self.a.spec['feat_ranks'][TYPE.FEATURE], 1)
        self.assertEqual(self.a.stats['atk'], 21)
        self.assertEqual(self.a.stats['spe'], 30)
        self.assertEqual(TYPE.records(self.a), [(lower, {k: v for k, v in first.items() if k != 'status'})])
        ended = [entry['record'] for entry in self.a.spec[GRANTS.KEY]['ended_sources']
                 if entry['record'].get('static_acquisition', {}).get('feature_id') == TYPE.FEATURE]
        self.assertEqual([row['static_acquisition']['request_id'] for row in ended], [second['request_id']])
        self.assertEqual(ended[0]['retraining']['acquisition_receipt_ids'], [])
        self.assertTrue(TYPE.grants_stab(self.e, self.a, self.e.r.move(FIRE[0])))
        self.assertFalse(TYPE.grants_stab(self.e, self.a, self.e.r.move(WATER[0])))
        self.assertEqual(self.e.retrain_trainer_source(self.a, TYPE.FEATURE, rank=2, **options), result)
        self.assertEqual(self.a.spec['exp_bank'], 98)
        self.acquire(rank=2, chosen='불꽃', stat='spd', request='type/reacquired-2')
        self.restore()
        options['request_id'] = 'type/retrain-new-2'
        self.e.retrain_trainer_source(self.a, TYPE.FEATURE, rank=2, **options)
        options.update(request_id='type/retrain-1', retained_dependencies={})
        self.e.retrain_trainer_source(self.a, TYPE.FEATURE, rank=1, **options)
        self.assertNotIn(TYPE.FEATURE, self.a.spec['feats'])
        self.assertEqual(self.a.stats['atk'], 20)
        self.assertFalse(TYPE.grants_stab(self.e, self.a, self.e.r.move(FIRE[0])))
        self.restore(fresh=True)

    def test_selected_official_playtest_profile_and_unreviewed_source_versions(self):
        self.setup(rules=Rules(ROOT, ruleset='playtest'))
        self.acquire(edition='local_csv')
        self.assertEqual(self.e.damage_base(self.a, self.e.r.move(FIRE[0])), 6)
        self.restore()
        self.setup()
        with patch.dict(self.rules.ruleset.unit_versions, {TYPE.FEATURE: 'unreviewed'}):
            with self.assertRaisesRegex(ValueError, 'version|variant|profile|selected'):
                self.acquire()
        self.assertFalse(TYPE.records(self.a))

    def test_other_feature_retraining_preserves_both_type_ranks_and_requires_both_sources(self):
        self.acquire()
        self.acquire(rank=2, chosen='물', stat='spe')
        T.acquire_static(self.e, self.a, 'feat/퀵-스위치', acquisition_request_id='actual/quick-switch')
        lower, higher = [sid for sid, _ in TYPE.records(self.a)]
        options = {'request_id': 'other/retraining', 'reason': 'actual independent Feature retraining',
                   'gm_decision': {'allowed': True, 'reason': 'GM reviewed all retained ranks'},
                   'retained_dependencies': {higher: [lower]}}
        self.reject(lambda: self.e.retrain_trainer_source(self.a, 'feat/퀵-스위치', **options), 'every actual retained')
        options['retained_dependencies'][lower] = []
        self.e.retrain_trainer_source(self.a, 'feat/퀵-스위치', **options)
        self.assertEqual(ACQUIRED.owned_rule_count(self.a, TYPE.FEATURE), 2)
        self.assertEqual([sid for sid, _ in TYPE.records(self.a)], [lower, higher])
        self.assertEqual(self.a.stats['atk'], 21)
        self.assertEqual(self.a.stats['spe'], 31)
        self.assertEqual(self.e.damage_base(self.a, self.e.r.move(FIRE[0])), 6)
        self.assertEqual(self.e.damage_base(self.a, self.e.r.move(WATER[0])), 6)
        self.restore(fresh=True)

    def test_juggler_saved_contract_is_cold_warm_equivalent_and_tampering_remains_rejected(self):
        import juggler
        warm = Rules(ROOT, ruleset='core')
        engine = Engine(warm, seed=142)
        authentic = deepcopy(juggler.contract(warm))
        saved = CODEC.dump_engine(engine)
        cold = Rules(ROOT, ruleset='core')
        self.assertNotIn('_juggler_contract', vars(cold))
        self.assertEqual(CODEC.rules_fingerprint(cold), saved['rules'])
        self.assertEqual(CODEC.dump_engine(CODEC.load_engine(cold, saved))['rules'], saved['rules'])
        warm._juggler_contract = deepcopy(authentic)
        warm._juggler_contract['schema_version'] += 1
        with self.assertRaisesRegex(CODEC.StateCodecError, 'fingerprint mismatch'):
            CODEC.load_engine(warm, saved)
        warm._juggler_contract = authentic
        # Fault only the captured private source copy, never canonical data.
        source = Path(__file__).resolve().parents[1] / 'data/juggler-source-contract.json'
        original = source.read_bytes()
        tampered = json.loads(original)
        tampered['schema_version'] += 1
        try:
            source.write_text(json.dumps(tampered, ensure_ascii=False), encoding='utf-8')
            with self.assertRaisesRegex(CODEC.StateCodecError, 'fingerprint mismatch'):
                CODEC.load_engine(cold, saved)
        finally:
            source.write_bytes(original)
        self.assertEqual(CODEC.rules_fingerprint(cold), saved['rules'])


if __name__ == '__main__':
    unittest.main()
