"""Declared ordinary ordinals and effect ranks through source-owned native consumers."""
from copy import copy, deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools'), str(ROOT / 'examples')]
from engine import Rules, Engine, Combatant
from rulings import Rulings
from declared_skill_ranks import configure
from native_scenario_fixture import assert_rejected_unchanged
import skill_modifiers as SK
import state_codec as CODEC
import state_grants as GRANTS
import special_entities as SPECIAL
import world_entities as WORLD
import items as ITEMS
import pokemon_party as PARTY
import pokemon_teaching as TEACH
import mentor_csv as MENTOR
import move_state as MOVES
import survivalist_class as SURVIVAL
import book_survivalist_fixture as SURVIVAL_FIX
import supplemental_state as DIGITAL
import optional_physical_equipment as OPTIONAL
import test_master_rank_eight_consumers as ORIGINAL
import test_category2_mentor_csv as MENTOR_CSV_FIX
import test_category2_mentor_move_state as MENTOR_BOOK_FIX
import test_category2_defensive_hacking as HACK_FIX
import test_foundation_network_integrity as NETWORK_FIX
import test_category2_optional_physical_equipment as FLUTE_FIX


class DeclaredRankConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bases = {kind: Rules(ROOT, ruleset=kind) for kind in ('core', 'all', 'fantasy')}

    def rules(self, kind='core'):
        rules = copy(self.bases[kind])
        rules.rulings = Rulings()
        configure(rules)
        return rules

    def pool(self, engine, actor, skill, rank):
        self.assertEqual(SK.rank(engine.r, actor, skill)[1:], ('7d6', rank))
        result = engine.skill_roll(actor, skill, fixed=[2] * 7)
        self.assertEqual((result.rank, result.dice_count, result.total), (rank, 7, 14))

    def restored(self, engine):
        loaded = CODEC.load_engine(engine.r,
                                   json.loads(json.dumps(CODEC.dump_engine(engine), ensure_ascii=False)))
        self.assertTrue(loaded.validate_state()['valid'])
        return loaded, WORLD.actor_index(loaded)

    def forged_save(self, engine, marker, field, value):
        saved = CODEC.dump_engine(engine)
        count = 0
        for node in saved['nodes'].values():
            if node.get('kind') == 'dict' and list(marker) in node['items']:
                for item in node['items']:
                    if item[0] == field:
                        if isinstance(value, list):
                            referenced = saved['nodes'][item[1]['$ref']]
                            self.assertEqual(referenced['kind'], 'list')
                            referenced['items'] = list(value)
                        else:
                            item[1] = value
                        count += 1
        self.assertGreater(count, 0)
        with self.assertRaises(CODEC.StateCodecError):
            CODEC.load_engine(engine.r, saved)

    def venom(self, rank):
        f = ORIGINAL.PotentVenomVirtuosoTests('runTest'); f.rules = self.rules()
        f.family('독', 'Potent Venom')
        skill = f.t.spec['type_link_skills']['독']
        f.e.gm.set_skill(f.t, skill, rank, reason='Declared Type Link ordinal')
        self.pool(f.e, f.t, skill, rank)
        f.answer('type_ace_choice', True); f.answer('type_ace_potent_venom_stat', 'atk')
        f.e.gm.set_position(f.b, (3, 2), reason='Adjacent poisoned recipient')
        f.combat(f.p); f.native(f.p, f.b, 'move/독가루', face=15)
        self.assertEqual(f.b.custom_conditions['type_ace_poison']['rank'], rank)
        f.valid()
        return f

    def test_declared_potent_venom_retains_ordinal_damage_and_both_restores(self):
        for rank in (7, 10):
            with self.subTest(rank=rank):
                f = self.venom(rank)
                f.e.gm.snapshot('venom'); f.e.cure_status(f.b, '독'); f.e.gm.restore('venom')
                f.restore(); self.assertEqual(f.b.custom_conditions['type_ace_poison']['rank'], rank)
                lost, tick = f.poison_tick(); self.assertEqual(lost, tick + rank)
                f.valid()

    def test_declared_potent_venom_rejects_undeclared_and_noninteger_saved_ranks(self):
        f = self.venom(10)
        source = f.b.custom_conditions['type_ace_poison']['source']
        for value in (11, 0, 10.0, True):
            with self.subTest(value=value):
                self.forged_save(f.e, ('source', source), 'rank', value)
        f.valid()

    def dietician(self, rank):
        f = ORIGINAL.DieticianVirtuosoTests('runTest'); f.r = self.rules('all'); f.e = Engine(f.r, 419)
        f.owner = f.trainer('declared-chef', intuition=rank, virtuoso=False)
        f.p = f.pokemon(f.owner); ITEMS.register_feats(f.e, f.owner)
        return f

    def test_declared_dietician_prerequisite_evidence_preserves_fixed_seven_capacity_and_transfer(self):
        f = self.dietician(7)
        self.pool(f.e, f.owner, '직감', 7)
        self.assertEqual(f.owner.spec['dietician_acquisition']['intuition_rank'], 7)
        second = f.trainer('mythic-chef', intuition=10, virtuoso=False)
        self.pool(f.e, second, '직감', 10)
        for owner, roster in ((f.owner, [f.p]), (second, [])):
            PARTY.configure(f.e, owner, mode='unlimited', roster=roster, reason='Actual complete roster')
        f.e.gm.snapshot('dietician')
        PARTY.transfer(f.e, f.owner, target=f.p, new_owner=second, request_id='rank-transfer', reason='Actual transfer')
        self.assertEqual((f.view()['capacity'], second.spec['dietician_acquisition']['intuition_rank']), (7, 10))
        loaded, actors = self.restored(f.e)
        self.assertEqual(actors[second.entity_id].spec['dietician_acquisition']['intuition_rank'], 10)
        self.assertEqual(MOVES.vitamin_state(loaded.r, actors[f.p.entity_id].spec)['capacity'], 7)
        f.e.gm.restore('dietician')
        self.assertEqual(f.view()['capacity_sources'][0]['owner_id'], f.owner.entity_id)

    def test_declared_dietician_rejects_undeclared_effect_only_and_below_expert_evidence(self):
        f = self.dietician(10)
        for rank in (8, 11, 4, True, 10.0):
            with self.subTest(rank=rank):
                self.forged_save(f.e, ('source', 'feat/영양사'), 'intuition_rank', rank)
        self.assertTrue(f.e.validate_state()['valid'])

    def terrain(self, rank):
        rules = self.rules(); SURVIVAL.definitions(rules)
        world = SURVIVAL_FIX.scene(rules, survival=rank)
        e, a = world['engine'], world['trainer']
        for terrain in ('ocean', 'urban'): SURVIVAL_FIX.master(e, a, terrain)
        SURVIVAL_FIX.talents(e, a, 'ocean', 'urban'); SURVIVAL_FIX.env(e, a, 'urban')
        self.pool(e, a, '생존', rank)
        return world

    def test_declared_survival_effect_minutes_and_floor_half_evasion_use_ordinal(self):
        for rank in (7, 10):
            with self.subTest(rank=rank):
                world = self.terrain(rank); e, a, foe = world['engine'], world['trainer'], world['foe']
                self.assertEqual(SURVIVAL.evasion_bonus(e, a, foe, {'id': SURVIVAL.PUSH}), rank // 2)
                self.assertEqual(SURVIVAL.evasion_bonus(e, a, foe, {'id': SURVIVAL.TRIP}), rank // 2)
                self.assertEqual(SURVIVAL.evasion_bonus(e, a, foe, {'id': 'move/몸통박치기'}), 0)
                bandit = Combatant(e.r, SURVIVAL_FIX.trainer_spec(e.r, 'declared-bandit', survival=3, movement={'land': 6, 'power': 4}))
                e.gm.add_combatant(bandit, pos=(1, 2), side='wild', reason='Adjacent actual attacker')
                e.gm.set_position(world['partner'], (3, 5), reason='Clear the push lane')
                bandit.spec['weight_kg'] = a.spec['weight_kg'] = 30
                SURVIVAL_FIX.battle(e, bandit)
                need = 4 + a.evasion('변화', engine=e)
                pushed = e.push(bandit, a, challenger_skill='전투', defender_skill='전투',
                    fixed_accuracy=need + rank // 2 - 1,
                    challenger_options={'fixed': [3] * 4}, defender_options={'fixed': [2] * 4})
                self.assertFalse(pushed); self.assertEqual(a.pos, (2, 2))
                e.end_scene(e.everyone, round_elapsed_seconds=10)
                e.observe_breathing(a, air_available=False, medium='water', timing_policy='grace_boundary', reason='Actual dive')
                self.assertEqual(a.spec['_respiration']['grace_seconds'], 60 * rank)
                loaded, actors = self.restored(e); diver = actors[a.entity_id]
                loaded.advance_time(60 * rank - 1, [diver]); self.assertEqual(diver.injuries, 0)
                loaded.advance_time(1, [diver]); self.assertEqual(diver.injuries, 1)

    def test_declared_glyph_capacity_uses_ordinal_and_overflow_is_atomic(self):
        for rank in (7, 10):
            with self.subTest(rank=rank):
                f = ORIGINAL.GlyphVirtuosoTests('runTest'); f.fantasy = self.rules('fantasy')
                f.world(virtuoso=False, count=rank + 1)
                f.e.gm.set_skill(f.a, '오컬트학', rank, reason='Declared glyph creator ordinal')
                self.pool(f.e, f.a, '오컬트학', rank)
                SPECIAL.observe_batch(f.e, [f.glyph(n) for n in range(rank)], reason='Actual active glyphs')
                self.assertEqual(SPECIAL.view(f.e, 'glyph-0')['state_view']['active_glyph_limit'], rank)
                assert_rejected_unchanged(f.e, lambda: SPECIAL.observe(f.e, f.glyph(rank), reason='Overflow'),
                                           reason_pattern='active glyphs exceed')
                loaded, _ = self.restored(f.e)
                self.assertEqual(SPECIAL.view(loaded, 'glyph-0')['state_view']['active_glyph_limit'], rank)

    def mentor(self, route, rank):
        rules = self.rules()
        if route == 'csv':
            f = MENTOR_CSV_FIX.MentorCSVTests('runTest'); f.rules = rules
        else:
            f = MENTOR_BOOK_FIX.MentorMoveStateTests('runTest'); f.r = rules
        f.setUp(); f.e.gm.set_skill(f.a, '매력', rank, reason='Declared selected Mentor rank')
        if route == 'csv': f.acquire()
        self.pool(f.e, f.a, '매력', rank)
        return f

    def pupil(self, f, route, level):
        return f.pupil('브케인', level, tp=8) if route == 'csv' else f.pokemon(level)

    def test_declared_mentor_book_and_csv_allowance_uses_two_ordinals_and_preserves_history(self):
        for route in ('book', 'csv'):
            for rank in (7, 10):
                with self.subTest(route=route, rank=rank):
                    f = self.mentor(route, rank); boundary = 40 - rank - 3
                    below = self.pupil(f, route, boundary - 1)
                    assert_rejected_unchanged(f.e, lambda: f.teach(below, 'move/화염방사'), reason_pattern='allowance')
                    p = self.pupil(f, route, boundary); out = f.teach(p, 'move/화염방사')
                    self.assertEqual((out['classification'], p.spec['tutor_points'], f.e.elapsed_seconds), ('natural', 7, 60))
                    self.assertEqual(p.spec['move_learning']['move/화염방사']['mentor_skill_ranks'], [rank, 3])
                    if route == 'csv':
                        self.assertEqual(MENTOR.receipt(f.a)['selection']['acquisition_snapshot']['ranks'], [rank, 3])
                    f.e.gm.snapshot('mentor'); f.e.gm.set_move(p, 'move/화염방사', add=False, reason='Later forgetting')
                    f.e.gm.restore('mentor'); f.e.gm.set_skill(f.a, '매력', 3, reason='Later skill change')
                    loaded, actors = self.restored(f.e)
                    self.assertEqual(MOVES.describe(loaded.r, actors[p.entity_id].spec)['classifications']['move/화염방사'], 'natural')

    def test_declared_mentor_history_rejects_undeclared_and_unwitnessed_effect_ranks(self):
        for route in ('book', 'csv'):
            f = self.mentor(route, 10); p = self.pupil(f, route, 27); f.teach(p, 'move/화염방사')
            row = deepcopy(p.spec['move_learning']['move/화염방사'])
            for rank in (8, 11, 2, True, 10.0):
                with self.subTest(route=route, rank=rank):
                    altered = deepcopy(row); altered['mentor_skill_ranks'][0] = rank
                    with self.assertRaises(ValueError): TEACH.validate_mentor_ranks(f.e.r, altered)
            self.forged_save(f.e, ('method', 'mentor_csv' if route == 'csv' else 'mentor'), 'mentor_skill_ranks', [11, 3])
            self.assertTrue(f.e.validate_state()['valid'])

    def test_declared_flute_allies_keep_five_dr_and_scene_lifetime_after_restore(self):
        for rank in (7, 10):
            with self.subTest(rank=rank):
                f = FLUTE_FIX.OptionalPhysicalEquipmentTests('runTest'); f.r = self.rules('all')
                e, a, ally, _ = f.fixture(); f.equip(e, a, 'crafted_item/따스한-플루트', 'declared-flute')
                e.gm.set_skill(a, '오컬트학', rank, reason='Declared flute ordinal'); self.pool(e, a, '오컬트학', rank)
                allies = [ally]
                for n in range(rank):
                    extra = f.actor('declared-ally-' + str(n)); extra.side = a.side; extra.pos = (7 + n, 2)
                    e.gm.add_combatant(extra); allies.append(extra)
                e.start_round(e.everyone); e.start_of_turn(a, initiative_count=20)
                assert_rejected_unchanged(e, lambda: OPTIONAL.activate_heartwarming_flute(e, a, protected_allies=allies),
                                           reason_pattern='exceeds the wielder')
                out = OPTIONAL.activate_heartwarming_flute(e, a, protected_allies=allies[:rank])
                self.assertEqual(len(out['protected']), rank)
                loaded, actors = self.restored(e); ghost = {'type': '고스트', 'class': '특수'}
                self.assertEqual([ITEMS.item_damage_reduction(actors[x.entity_id], ghost, engine=loaded) for x in allies], [5] * rank + [0])
                loaded.end_scene(loaded.everyone, round_elapsed_seconds=10)
                self.assertEqual(ITEMS.item_damage_reduction(actors[ally.entity_id], ghost, engine=loaded), 0)

    def hacking(self, rank, *, native=True):
        kind = HACK_FIX.DefensiveHackingTests if native else NETWORK_FIX.IntegrityTests
        f = kind('runTest'); f.poly = self.rules('all'); f.setUp()
        # Skill and its dependent avatar maximum are one observed state change.
        def apply(e, actor):
            actor.spec['skills'].update({'집중': rank, '기술학': rank})
            avatar = e._physical_objects['target-avatar']; maximum = DIGITAL.avatar_maximum(e, actor)
            avatar.update(integrity=maximum, max_integrity=maximum, optional_trainer_stats=True)
        GRANTS.transition(f.e, f.t, apply)
        f.target = f.e._physical_objects['target-avatar']; self.pool(f.e, f.t, '집중', rank)
        return f

    def test_declared_hacking_and_avatar_use_ordinals_while_native_roll_keeps_seven_dice(self):
        for rank in (7, 10):
            with self.subTest(rank=rank):
                f = self.hacking(rank); hp = f.t.hp; maximum = f.t.level * 2 + f.t.stats['hp'] * rank // 2 + 10
                self.assertEqual(f.target['max_integrity'], maximum)
                view = SPECIAL.view(f.e, 'target-avatar')['state_view']
                self.assertEqual((view['digital_stats']['atk'], view['digital_stats']['def']), (3 * rank, 3 * rank))
                f.e.gm.snapshot('avatar')
                out = f.run_effect(); self.assertEqual((out['requested'], out['derivation']['reduction']), (24 - rank, rank))
                self.assertEqual((f.target['integrity'], f.t.hp), (maximum - 24 + rank, hp))
                loaded, actors = self.restored(f.e)
                self.assertEqual(loaded._physical_objects['target-avatar']['max_integrity'], maximum)
                f.e.gm.restore('avatar'); self.assertEqual(f.e._physical_objects['target-avatar']['integrity'], maximum)
                bad = dict(f.e._physical_objects['target-avatar'], max_integrity=maximum + 1)
                assert_rejected_unchanged(f.e, lambda: SPECIAL.observe(f.e, bad, reason='Invalid maximum'), reason_pattern='maximum integrity')

    def test_declared_defensive_feature_adapter_uses_effect_rank_for_virtuoso(self):
        f = self.hacking(10, native=False)
        def acquire(e, a):
            a.level = a.spec['level'] = 30
            a.spec['skills']['집중'] = 6
            a.spec['edges'] = ['방어적 해킹', 'edge/거장']
            a.spec['edge_choices'] = {'edge/거장': ['집중']}
            avatar = e._physical_objects['target-avatar']; maximum = DIGITAL.avatar_maximum(e, a)
            avatar.update(integrity=maximum, max_integrity=maximum)
        GRANTS.transition(f.e, f.t, acquire)
        policy = f.policy(); policy['effect']['defensive_feature'] = {'source': policy['source'], 'names': ['방어적 해킹'], 'skill': '집중'}
        self.assertEqual(SK.rank(f.e.r, f.t, '집중')[1:], ('6d6', 6))
        out = f.run_effect(policy); self.assertEqual((out['requested'], out['derivation']['reduction']), (16, 8))


if __name__ == '__main__':
    unittest.main()
