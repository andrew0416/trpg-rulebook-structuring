"""Current-owner projections occur inside the native transfer transaction."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from builder import build_trainer
from engine import Combatant, Rules
import action_points as AP
import class_passive_combat as CLASS
import items as ITEMS
import pokemon_party as PARTY
import state_grants as GRANTS
import state_codec as CODEC
import static_trainer_modifiers as STATIC
import weapon_actions as WEAPONS
import world_entities as WORLD
import native_scenario_fixture as NATIVE
import test_book_species_savant as BOOK
import test_category2_static_trainer_modifiers as STAT_FIXTURE
import test_category2_class_passive_combat_bulk as CLASS_FIXTURE
import test_category2_finisher as FINISHER
import test_category2_polished_shine as SHINE


class OwnerTransferProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for fixture in (BOOK.BookSpeciesSavantTests, STAT_FIXTURE.StaticTrainerModifierTests,
                        CLASS_FIXTURE.ClassPassiveCombatBulkTests, FINISHER.FinisherTests,
                        SHINE.PolishedShineTests):
            fixture.setUpClass()

    def roster(self, e, owner, pokemon):
        PARTY.configure(e, owner, mode='unlimited', reason='actual observed roster', roster=pokemon)

    def transfer(self, f, request='projection/transfer', *, old=None, new=None, reason='actual gift'):
        return PARTY.transfer(f.e, f.a if old is None else old, target=f.p,
            new_owner=f.b if new is None else new, reason=reason, request_id=request)

    def finisher(self, recipient=True):
        f = FINISHER.FinisherTests(); f.setUp()
        if recipient:
            f.b.spec['feats'] = [FINISHER.SOURCE]
            f.e.register_abilities(f.b)
        self.roster(f.e, f.a, [f.p]); self.roster(f.e, f.b, [f.foreign])
        return f

    def key(self, owner, source=FINISHER.SOURCE):
        return 'feature:' + owner.entity_id + ':' + source

    def test_eight_csv_declarations_and_six_species_stats_without_sustain_or_ap(self):
        for uid in sorted(CLASS.STRATAGEMS | CLASS.POKEMON_STATIC):
            with self.subTest(uid=uid, clause=CLASS.CLAUSE_BY_RULE[uid]):
                f = BOOK.BookSpeciesSavantTests(); f.setUp()
                trio = f.trio(); p = trio[0]; recipient = f.trainer('receiving ' + uid)
                recipient.spec['feats'].append(uid)
                if uid == CLASS.SPECIES_SAVANT:
                    recipient.spec['class_passive_choices'] = {uid: {'evolution_group': 'diglett-line'}}
                    p.spec['evolution_group'] = 'diglett-line'
                self.roster(f.e, f.t, trio); self.roster(f.e, recipient, [])
                f.acquire(trio)
                ap = deepcopy((recipient.spec.get('ap'), recipient.spec.get('ap_bound'),
                               AP.ActionPointAccount(recipient).available(),
                               dict(AP.ActionPointAccount(recipient).identified_bindings(allow_missing=True))))
                f.e.pokemon_activity(f.t, 'party_transfer', target=p, new_owner=recipient,
                    reason='actual gift', request_id='csv/' + uid)
                rows = GRANTS.state(p)['sources']
                self.assertIn(CLASS._source_id(recipient, p, uid), rows)
                self.assertNotIn(CLASS._source_id(f.t, p, CLASS.SPECIES_SAVANT), rows)
                self.assertEqual(p.stats, {stat: p.spec['stats'][stat] + int(uid == CLASS.SPECIES_SAVANT)
                                          for stat in BOOK.STATS})
                self.assertEqual(ap, (recipient.spec.get('ap'), recipient.spec.get('ap_bound'),
                    AP.ActionPointAccount(recipient).available(),
                    dict(AP.ActionPointAccount(recipient).identified_bindings(allow_missing=True))))
                if uid in CLASS.STRATAGEMS:
                    self.assertIsNone(CLASS._active(f.e, p, uid))
                self.assertTrue(f.e.validate_state()['valid'])

    def test_species_wrong_group_and_missing_or_invalid_selection_are_atomic(self):
        for choice in ({CLASS.SPECIES_SAVANT: {'evolution_group': 'other-line'}}, {},
                       {CLASS.SPECIES_SAVANT: {'evolution_group': ''}}):
            with self.subTest(choice=choice):
                f = BOOK.BookSpeciesSavantTests(); f.setUp(); trio = f.trio(); p = trio[0]
                new = f.trainer('CSV recipient'); new.spec['feats'] = [CLASS.SPECIES_SAVANT]
                new.spec['class_passive_choices'] = choice; p.spec['evolution_group'] = 'diglett-line'
                self.roster(f.e, f.t, trio); self.roster(f.e, new, []); f.acquire(trio)
                operation = lambda: PARTY.transfer(f.e, f.t, target=p, new_owner=new,
                    reason='actual gift', request_id='species/negative')
                if choice.get(CLASS.SPECIES_SAVANT, {}).get('evolution_group'):
                    operation()
                    self.assertEqual(p.stats, p.spec['stats'])
                    self.assertNotIn(CLASS._source_id(new, p, CLASS.SPECIES_SAVANT), GRANTS.state(p)['sources'])
                else:
                    problem = 'explicit class passive choice required' if not choice else 'explicit evolution group'
                    NATIVE.assert_rejected_unchanged(f.e, operation, reason_pattern=problem)

    def test_seven_static_sources_level_formula_branch_and_range_size(self):
        fixture = STAT_FIXTURE.StaticTrainerModifierTests()
        for field, (clause, source, branch) in STAT_FIXTURE.STAT_ROWS.items():
            with self.subTest(field=field):
                choices = {} if branch is None else {source: [branch]}
                e, old, p, _ = fixture.encounter(classes=[source], choices=choices, level=20)
                new = Combatant(fixture.r, build_trainer(fixture.r, 'recipient', 30,
                    dict.fromkeys(BOOK.STATS, 12), moves=[], abilities=[],
                    extra={'classes': [source], 'feats': [], 'feature_choices': choices}))
                e.gm.add_combatant(new, pos=(3, 0), side='party', reason='actual recipient')
                e.register_abilities(old); e.register_abilities(new)
                self.roster(e, old, [p]); self.roster(e, new, [])
                PARTY.transfer(e, old, target=p, new_owner=new, reason='actual gift', request_id='static/' + field)
                self.assertEqual(p.stats, {s: p.spec['stats'][s] + (3 if s == field else 0) for s in BOOK.STATS})
                rows = [r for r in GRANTS.state(p)['sources'].values() if r.get('clause_id') == clause]
                self.assertEqual(len(rows), 1); self.assertEqual(rows[0]['owner_id'], new.entity_id)
                self.assertFalse(any(r.get('owner_id') == old.entity_id for r in GRANTS.state(p)['sources'].values()))
        choices = {STATIC.STAT_ACE: ['spa'], STATIC.STAT_MASTERY: ['spa']}
        e, old, p, _ = fixture.encounter(classes=[STATIC.STAT_ACE], feats=[STATIC.STAT_MASTERY], choices=choices)
        new = Combatant(fixture.r, build_trainer(fixture.r, 'range recipient', 30,
            dict.fromkeys(BOOK.STATS, 12), moves=[], abilities=[], extra={
                'classes': [STATIC.STAT_ACE], 'feats': [STATIC.STAT_MASTERY], 'feature_choices': choices}))
        e.gm.add_combatant(new, pos=(3, 0), side='party', reason='actual recipient')
        e.register_abilities(old); self.roster(e, old, [p]); self.roster(e, new, [])
        PARTY.transfer(e, old, target=p, new_owner=new, reason='actual gift', request_id='static/range')
        blast = fixture.r.move('move/회오리')
        self.assertEqual((WEAPONS.range_spec(e, blast, p)['origin'],
                          WEAPONS.range_spec(e, blast, p)['size']), (8, 3))
        flame = fixture.r.move('move/화염방사')
        self.assertEqual(WEAPONS.range_spec(e, flame, p)['origin'], 6)

    def test_current_owner_conditional_fire_and_ice_consumers_keep_their_gates(self):
        fixture = CLASS_FIXTURE.ClassPassiveCombatBulkTests()
        for uid in (CLASS.SHINING_FLAME, CLASS.GLACIAL_ICE):
            with self.subTest(uid=uid):
                e, old, p, enemy = fixture.fixture(feats=[uid], pokemon_types=['얼음'],
                    pokemon_moves=['불꽃세례', '니트로차지'])
                new = Combatant(fixture.rules, build_trainer(fixture.rules, 'new type owner', 30,
                    dict.fromkeys(BOOK.STATS, 12), abilities=[], moves=[],
                    skills={'집중': '숙련', '생존': '숙련'},
                    extra={'feats': [uid], 'type_link_skills': {'불꽃': '집중', '얼음': '생존'}}))
                e.gm.add_combatant(new, pos=(3, 0), side='party', reason='actual recipient')
                self.roster(e, old, [p]); self.roster(e, new, [])
                PARTY.transfer(e, old, target=p, new_owner=new, reason='actual gift', request_id='type/' + uid)
                fire = e.r.move('move/화염방사')
                if uid == CLASS.GLACIAL_ICE:
                    self.assertEqual(CLASS.damage_reduction(e, enemy, p, fire, 2, False), 4)
                    self.assertEqual(CLASS.damage_reduction(e, enemy, p, fire, 1, False), 0)
                    self.assertEqual(CLASS.damage_reduction(e, enemy, p, dict(fire, type='노말'), 2, False), 0)
                else:
                    self.assertEqual(CLASS.damage_roll_modifier(e, p, enemy, fire, 1), 0)
                    e.apply_status(enemy, '화상', source='condition/화상', applied_by=new)
                    self.assertEqual(CLASS.damage_roll_modifier(e, p, enemy, fire, 1), 4)
                    self.assertEqual(CLASS.damage_roll_modifier(e, p, enemy, dict(fire, type='물'), 1), 0)
                    ember = e.r.move('move/불꽃세례')
                    self.assertEqual(CLASS.effect_range_bonus(e, p, ember, e.r.move_mech(ember['id'])[0]), 3)

    def test_finisher_native_transfer_target_conditions_exact_index_and_unrelated_state(self):
        f = self.finisher(); key = self.key(f.b)
        GRANTS.revoke(f.b, key, engine=f.e)
        GRANTS.apply_owned(f.e, f.p, 'fixture:independent', lambda: f.p.modifiers.append({'type': 'bonus_damage', 'value': 1}))
        before = deepcopy((f.foreign.spec, f.foreign.modifiers, f.foreign.stats, f.b.modifiers, f.b.stats))
        self.assertNotIn('trainer', f.p.spec)
        self.transfer(f)
        self.assertEqual(f.bonus(f.p), 1)
        f.e.apply_status(f.t, '둔화', source='condition/둔화', applied_by=f.b)
        f.e.apply_status(f.t, '넘어짐', source='condition/넘어짐', applied_by=f.b)
        self.assertEqual((f.bonus(f.p), f.bonus(f.b)), (6, 0))
        self.assertNotIn(key, GRANTS.state(f.b)['sources'])
        self.assertEqual(before, (f.foreign.spec, f.foreign.modifiers, f.foreign.stats, f.b.modifiers, f.b.stats))
        row = GRANTS.state(f.p)['sources'][key]
        self.assertEqual(row['effect_sources'], [key + ':1'])
        self.assertNotIn(self.key(f.a), GRANTS.state(f.p)['sources'])

    def test_polished_shine_transfer_steel_threshold_without_accuracy_crit_or_spatial_change(self):
        f = SHINE.PolishedShineTests(); f.setUp()
        f.b.spec['feats'] = [SHINE.SOURCE]; f.e.register_abilities(f.b)
        self.roster(f.e, f.a, [f.p]); self.roster(f.e, f.b, [f.foreign])
        move = f.r.move('move/아이언헤드'); spatial = WEAPONS.range_spec(f.e, move, f.p)
        self.transfer(f)
        self.assertEqual((f.bonus(f.p), f.bonus(f.p, '전기쇼크'), f.bonus(f.b)), (2, 0, 0))
        self.assertEqual(WEAPONS.range_spec(f.e, move, f.p), spatial)
        self.assertEqual(f.e.accuracy_check(f.p, f.t, move, fixed_roll=18), (True, 18, False))
        f.e.gm.send_out(f.p, pos=(2, 1), reason='new owner actually deploys transferred Pokemon')
        f.e.gm.observe_loyalty(f.p, 6, reason='actual new owner loyalty observed')
        self.assertGreater(f.attack(f.p, '아이언헤드', 13), 0)
        self.assertIn('풀죽음', f.t.conditions)
        self.assertNotIn(self.key(f.a, SHINE.SOURCE), GRANTS.state(f.p)['sources'])

    def test_no_recipient_feat_retransfer_and_replay_remain_inert(self):
        f = self.finisher(False)
        self.transfer(f); self.assertNotIn(self.key(f.a), GRANTS.state(f.p)['sources'])
        self.assertNotIn(self.key(f.b), GRANTS.state(f.p)['sources'])
        f = self.finisher()
        receipt = self.transfer(f); key = self.key(f.b)
        GRANTS.revoke(f.p, key, engine=f.e)
        before = CODEC.dump_engine(f.e)
        self.assertEqual(self.transfer(f), receipt); self.assertEqual(CODEC.dump_engine(f.e), before)
        NATIVE.assert_rejected_unchanged(f.e, lambda: self.transfer(f, reason='changed intent'), reason_pattern='intent|different|changed')
        self.transfer(f, 'projection/return', old=f.b, new=f.a)
        self.assertIn(self.key(f.a), GRANTS.state(f.p)['sources']); self.assertNotIn(key, GRANTS.state(f.p)['sources'])
        NATIVE.assert_rejected_unchanged(f.e, lambda: self.transfer(f), reason_pattern='actual owner')

    def test_json_fresh_rules_gm_restore_and_restored_replay_preserve_exact_parts_once(self):
        f = self.finisher(); f.e.apply_status(f.t, '둔화', source='condition/둔화', applied_by=f.a)
        snapshot = f.e.gm.snapshot(); receipt = self.transfer(f)
        payload = json.loads(json.dumps(CODEC.dump_engine(f.e), ensure_ascii=False))
        loaded = CODEC.load_engine(Rules(ROOT, ruleset='all'), payload); index = WORLD.actor_index(loaded)
        p, old, new = (index[x.entity_id] for x in (f.p, f.a, f.b))
        key = self.key(new); self.assertEqual(GRANTS.state(p)['sources'][key]['effect_sources'], [key + ':1'])
        self.assertNotIn(self.key(old), GRANTS.state(p)['sources'])
        self.assertEqual(len([m for m in p.modifiers if m.get('if_target_status_any')]), 1)
        target = index[f.t.entity_id]; move = loaded.r.move('move/몸통박치기')
        self.assertEqual(FINISHER.FX.passive_damage_mods(loaded, p, target, move,
            {'attacker': p, 'target': target, 'hit': True, 'move': move, 'engine': loaded})[1], 5)
        before = CODEC.dump_engine(loaded)
        self.assertEqual(PARTY.transfer(loaded, old, target=p, new_owner=new, reason='actual gift', request_id='projection/transfer'), receipt)
        self.assertEqual(CODEC.dump_engine(loaded), before)
        f.e.gm.restore(snapshot)
        self.assertIn(self.key(f.a), GRANTS.state(f.p)['sources']); self.assertNotIn(self.key(f.b), GRANTS.state(f.p)['sources'])
        self.assertEqual(f.bonus(f.p), 5)

    def test_late_projection_failure_rolls_back_rulings_rng_payments_sources_and_identities(self):
        f = self.finisher()
        f.b.spec['classes'] = [STATIC.ENDURING]
        GRANTS.grant(f.p, 'capabilities', 'Jump=1', 'fixture:refundable', 'feature',
            owner_id=f.a.entity_id, lifetime='your_pokemon', rule_id='observed/source', tutor_points=2)
        before = CODEC.dump_engine(f.e); rulings = deepcopy(f.e.rulings.log)
        identities = (f.p.spec, f.p.modifiers, f.a.spec['pokemon_registry'])
        original = ITEMS.project_owned_pokemon_features
        def fail(engine, owner, targets):
            original(engine, owner, targets)
            engine.rng.random(); engine.log('injected late failure', 'test/failure')
            engine.rulings.log.append({'test': 'discard this ruling'})
            raise RuntimeError('late projected generic failure')
        with patch.object(ITEMS, 'project_owned_pokemon_features', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'late projected generic'):
                self.transfer(f)
        self.assertEqual(CODEC.dump_engine(f.e), before); self.assertEqual(f.e.rulings.log, rulings)
        self.assertIs(f.p.spec, identities[0]); self.assertIs(f.p.modifiers, identities[1])
        self.assertIs(f.a.spec['pokemon_registry'], identities[2]); self.assertIs(WORLD.actor_index(f.e)[f.p.entity_id], f.p)

    def test_generic_admission_variants_and_new_name_share_normal_registration(self):
        f = self.finisher(False); name = 'feat/External Static Pokemon Bonus'
        f.b.spec['feats'] = [name]
        original = f.r.feat_effects
        base = {'id': name, 'frequency': {'raw': '항상', 'action': 'static'}}
        effects = [{'type': 'bonus_damage', 'value': 9, 'target': 'self'},
                   {'type': 'bonus_damage', 'value': 2, 'target': 'your pokemon'}]
        def definition(value): return (deepcopy(effects), deepcopy(base)) if value == name else original(value)
        with patch.object(f.r, 'feat_effects', side_effect=definition):
            ITEMS.register_feats(f.e, f.b)
            self.assertEqual(f.bonus(f.foreign), 2)
            self.transfer(f)
            self.assertEqual(f.bonus(f.p), 2)
            key = self.key(f.b, name)
            self.assertEqual(GRANTS.state(f.p)['sources'][key]['effect_sources'], [key + ':1'])
            GRANTS.revoke(f.p, key, engine=f.e)
            for variant in ('trigger', 'gm', 'action', 'missing_action', 'ap', 'ap_error', 'duration', 'while', 'move', 'ability', 'ambiguous_target'):
                with self.subTest(variant=variant):
                    def revised(value):
                        rows, header = definition(value)
                        if value != name: return rows, header
                        if variant == 'trigger': rows.append({'type': 'trigger', 'text': 'when a move hits'})
                        elif variant == 'gm': rows.append({'type': 'gm', 'note': 'choice required'})
                        elif variant == 'action': header['frequency'] = {'raw': '장면 – 신속 행동', 'action': 'swift'}
                        elif variant == 'missing_action': header['frequency'] = {'raw': 'unclear'}
                        elif variant == 'ap': header['frequency']['ap'] = 1
                        elif variant == 'ap_error': rows.append({'type': 'cost', 'ap': 'variable'})
                        elif variant in ('duration', 'while'): rows[1][variant] = 'scene'
                        elif variant == 'move': rows[1] = {'type': 'grant_move', 'move': '화염방사', 'target': 'your pokemon'}
                        elif variant == 'ability': rows[1] = {'type': 'grant_ability', 'ability': '맹화', 'target': 'your pokemon'}
                        else: rows[1]['target'] = 'own pokemon'
                        return rows, header
                    with patch.object(f.r, 'feat_effects', side_effect=revised):
                        self.assertEqual(ITEMS.project_owned_pokemon_features(f.e, f.b, (f.p,)), 0)
                    self.assertNotIn(key, GRANTS.state(f.p)['sources'])

    def test_generic_projection_requires_actual_ownership_and_never_calls_dedicated_registrars(self):
        f = self.finisher(); before = CODEC.dump_engine(f.e)
        fake = Combatant(f.r, deepcopy(f.foreign.spec))
        for targets in ((f.p,), (fake,), (f.foreign, f.foreign)):
            with self.subTest(targets=[x.entity_id for x in targets]):
                NATIVE.assert_rejected_unchanged(f.e, lambda: ITEMS.project_owned_pokemon_features(f.e, f.b, targets),
                    reason_pattern='distinct actual owned')
        self.assertEqual(CODEC.dump_engine(f.e), before)
        f.b.spec['feats'] += [CLASS.SHINING_FLAME, 'feat/지침']
        import move_state as MOVES
        import training_features as TRAINING
        with patch.object(MOVES, 'register_passive_feature', side_effect=AssertionError('unrelated slot registrar')), \
             patch.object(TRAINING, 'register_owned', side_effect=AssertionError('unrelated training registrar')):
            ITEMS.project_owned_pokemon_features(f.e, f.b, (f.foreign,))

    def test_normal_generic_manual_and_edge_admission_remain_separate(self):
        f = self.finisher(False)
        names = ['feat/External Paid', 'feat/External Trigger', 'feat/External GM', 'edge/External Passive']
        f.b.spec['feats'] = names[:3]; f.b.spec['edges'] = names[3:]
        original = f.r.feat_effects
        def definition(name):
            if name not in names: return original(name)
            header = {'id': name, 'frequency': {'raw': '항상', 'action': 'static'}}
            rows = [{'type': 'bonus_damage', 'value': 2, 'target': 'your pokemon'}]
            if name == names[0]: header['frequency']['ap'] = 1
            if name == names[1]: rows.append({'type': 'trigger', 'text': 'unparsed explicit trigger'})
            if name == names[2]: rows.append({'type': 'gm', 'note': 'needs explicit choice'})
            if name == names[3]: header['frequency'] = {'raw': 'edge acquisition'}
            return rows, header
        with patch.object(f.r, 'feat_effects', side_effect=definition):
            ITEMS.register_feats(f.e, f.b)
            self.assertEqual(f.bonus(f.foreign), 2)
            for name in names[:3]:
                self.assertNotIn(self.key(f.b, name), GRANTS.state(f.foreign)['sources'])
                self.assertTrue(any(row.get('type') == 'feat_manual' and row.get('name') == name for row in f.b.registry))
            self.transfer(f)
            self.assertEqual(f.bonus(f.p), 2)
            self.assertEqual(GRANTS.state(f.p)['sources'][self.key(f.b, names[3])]['effect_sources'],
                             [self.key(f.b, names[3]) + ':0'])


if __name__ == '__main__':
    unittest.main()
