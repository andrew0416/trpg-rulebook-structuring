"""Direct producer, derivation, payload, lifetime, exception and save tests for G-Max."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
CANON = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

import gmax_moves as GMAX
import vortex_state as VORTEX
from builder import build_pokemon, build_trainer
from engine import Combatant, Engine, Rules
from grid import Grid
import move_completion as COMPLETE
import attack_damage_history as HISTORY
from native_scenario_fixture import prepare_gmax_scene


COMPLETED = {
    "C2CSV-MOVE-R1016", "C2CSV-MOVE-R1017", "C2CSV-MOVE-R1018",
    "C2CSV-MOVE-R1021", "C2CSV-MOVE-R1036", "C2CSV-MOVE-R1039",
    "C2CSV-MOVE-R1041", "C2CSV-MOVE-R1043", "C2CSV-MOVE-R1046",
}
ADDITIONAL = {"C2CSV-MOVE-R1034", "C2CSV-MOVE-R1035", "C2CSV-MOVE-R1045"}
DEFERRED = {
    "C2CSV-MOVE-R1027",
}


class GMaxMoveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="all")
        cls.declarations = {row["clause_id"]: row for row in GMAX.declarations(cls.r)}

    def setUp(self):
        previous = self.r.rulings
        self.r.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.r, 'rulings', previous)

    def world(self, clause, *, seed=1):
        return prepare_gmax_scene(self.r, self.declarations[clause], seed=seed)

    def activate(self, clause, *, seed=1):
        engine, actor, target, base, move_id = self.world(clause, seed=seed)
        result = engine.use_gmax_move_on(actor, target, base, move_id, [actor, target])
        return engine, actor, target, base, move_id, result

    def test_exact_source_rows_completed_subset_and_explicit_resumes(self):
        policy = json.loads((ROOT / "data/gmax-move-policy.json").read_text(encoding="utf-8"))
        self.assertEqual({row["clause_id"] for row in policy["moves"]}, COMPLETED | ADDITIONAL)
        self.assertEqual({row["clause_id"] for row in policy["deferred"]}, DEFERRED)
        self.assertTrue(all(row.get("reason") and row.get("resume_when") for row in policy["deferred"]))
        status_root = CANON if CANON.exists() else ROOT
        status = json.loads((status_root / "data/verification/category2-csv-abilities-moves-status.json").read_text(encoding="utf-8"))
        rows = {row["row_id"]: row for row in status["rows"] if row["row_id"] in COMPLETED | ADDITIONAL | DEFERRED}
        self.assertEqual(set(rows), COMPLETED | ADDITIONAL | DEFERRED)
        for declaration in policy["moves"] + policy["deferred"]:
            self.assertEqual(declaration["source_row_sha256"], rows[declaration["clause_id"]]["source_row_sha256"])

    def test_exact_species_learned_base_class_and_direct_call_gate(self):
        engine, actor, target, base, move_id = self.world("C2CSV-MOVE-R1016")
        planned = GMAX.plan(engine, actor, base, move_id)
        self.assertEqual(planned["class"], self.r.move(base)["class"])
        self.assertEqual(actor.spec[GMAX.STATE]["species_id"], self.declarations["C2CSV-MOVE-R1016"]["species_id"])
        before = (deepcopy(actor.budget), deepcopy(actor.move_uses),
                  deepcopy(getattr(engine, "_move_completions", {})))
        with self.assertRaisesRegex(ValueError, "direct G-Max use"):
            engine.use_move_on(actor, target, move_id, [actor, target])
        self.assertEqual((actor.budget, actor.move_uses,
                          getattr(engine, "_move_completions", {})), before)
        other = self.declarations["C2CSV-MOVE-R1017"]["move_id"]
        with self.assertRaisesRegex(ValueError, "exact species"):
            GMAX.plan(engine, actor, base, other)
        actor.moves.remove(base)
        actor.spec["moves"].remove(base)
        with self.assertRaisesRegex(ValueError, "actually learned"):
            GMAX.plan(engine, actor, base, move_id)

    def test_native_completion_hit_owns_payload_and_miss_has_none(self):
        # Legacy test ID retained for evidence continuity; Spirit Surge now owns the miss payload.
        hit, actor, target, base, move_id = self.world("C2CSV-MOVE-R1016", seed=1)
        hit.use_gmax_move_on(actor, target, base, move_id, [actor, target])
        self.assertEqual(len(hit._gmax_payload_receipts), 1)
        receipt = hit._move_completions[hit._gmax_payload_receipts[0]["completion_id"]]
        self.assertEqual(receipt["phase"], "complete")
        self.assertTrue(any(row["hit"] for row in receipt["results"].values()))

        miss, actor, target, base, move_id = self.world("C2CSV-MOVE-R1016", seed=31)
        before_hp = target.hp
        miss.use_gmax_move_on(actor, target, base, move_id, [actor, target])
        self.assertLess(target.hp, before_hp)
        self.assertEqual(len(miss._gmax_payload_receipts), 1)
        self.assertEqual(miss._gmax_payload_receipts[0]['target_ids'], [])
        self.assertNotIn(GMAX.EFFECTS, target.spec)

    def test_all_field_targets_share_one_preflight_and_transaction(self):
        engine, actor, first, base, move_id = self.world("C2CSV-MOVE-R1041")
        second = Combatant(self.r, build_pokemon(self.r, "Pikachu", 20, side="wild"))
        engine.gm.add_combatant(second)
        engine.time_actors([second])
        # The caller may provide an incomplete local view; the source says the
        # whole field, so the registered second foe must still participate.
        engine.use_gmax_move_on(actor, first, base, move_id, [actor, first])
        self.assertIn("조이기", first.conditions)
        self.assertIn("조이기", second.conditions)
        self.assertEqual(set(engine._gmax_payload_receipts[-1]["target_ids"]),
                         {first.entity_id, second.entity_id})

        engine, actor, first, base, move_id = self.world("C2CSV-MOVE-R1041")
        invalid = Combatant(self.r, build_pokemon(self.r, "Pikachu", 20, side="wild"))
        engine.gm.add_combatant(invalid)
        invalid.dead = True
        engine.time_actors([invalid])
        before = (deepcopy(actor.budget), deepcopy(actor.move_uses),
                  deepcopy(getattr(engine, "_move_completions", {})))
        with self.assertRaisesRegex(ValueError, "live field participants"):
            engine.use_gmax_move_on(actor, first, base, move_id, [actor, first])
        self.assertNotIn("조이기", first.conditions)
        self.assertEqual(engine._gmax_coin_rewards, [])
        self.assertEqual((actor.budget, actor.move_uses,
                          getattr(engine, "_move_completions", {})), before)

    def mapped_world(self, clause, *, first='gmax'):
        declaration = self.declarations[clause]
        derived = self.r.move(declaration['move_id'])
        source = build_pokemon(self.r, declaration['species_eng'], 50, side='party', abilities=[])
        actor = Combatant(self.r, source)
        base = next(mid for mid in actor.moves if self.r.move(mid)['type'] == derived['type']
                    and self.r.move(mid)['class'] in ('물리', '특수'))
        e = Engine(self.r, seed=1461); e.grid = Grid(32, 32)
        actor.pos = (4, 4)
        targets = [Combatant(self.r, build_pokemon(self.r, 'Snorlax', 100,
                    name=name, side='wild', abilities=[])) for name in ('inside', 'outside')]
        targets[0].pos, targets[1].pos = (9, 4), (27, 27)
        for member in (actor, *targets):
            e.gm.add_combatant(member)
            e.gm.set_footprint(member, [(0, 0)], reason='explicit scenario body')
        e.start_round(e.everyone)
        e.start_of_turn(actor if first == 'gmax' else targets[1], initiative_count=20)
        e.enter_gigantamax(actor, source_id='test/gmax-source', reason='actual mapped form')
        return e, actor, targets, base, derived['id']

    def learn_retaliation(self, engine, actor, move_id, reason):
        if move_id not in actor.moves:
            import move_state as MOVES
            view=MOVES.describe(engine.r,actor.spec,moves=actor.moves)
            if view['slot_count']==6:
                forgotten=next(mid for mid in actor.moves if mid!='struggle')
                engine.gm.set_move(actor,forgotten,add=False,
                    reason='actual explicit forgotten Move frees this retaliation slot')
        engine.gm.set_move(actor,move_id,reason=reason)

    def mapped_use(self, e, actor, target, base, move_id, face):
        with patch.object(Engine, 'd20', return_value=face):
            return e.use_gmax_move_on(actor, target, base, move_id, [actor, target],
                                      aim=(9, 4), set_damage=True)

    def test_all_twelve_spirit_surge_sources_complete_real_misses(self):
        for clause in sorted(COMPLETED | ADDITIONAL):
            with self.subTest(clause=clause):
                e, actor, (inside, outside), base, mid = self.mapped_world(clause)
                if clause == 'C2CSV-MOVE-R1046':
                    inside.last_move, outside.last_move = inside.moves[0], outside.moves[0]
                self.mapped_use(e, actor, inside, base, mid, 1)
                receipt = e._gmax_payload_receipts[-1]
                completion = e._move_completions[receipt['completion_id']]
                actual = COMPLETE.recipient_result(completion, inside)
                self.assertFalse(actual['hit']); self.assertFalse(actual['cancelled'])
                self.assertGreater(actual['dealt'], 0)
                self.assertNotIn(GMAX.EFFECTS, inside.spec)
                effect = self.declarations[clause]['effect']
                if effect == 'gravity':
                    import field_effects as FIELD
                    self.assertTrue(any(row['source_id'] == mid for row in FIELD.active_fields(e)))
                elif effect == 'area_hazard':
                    self.assertTrue(e.hazards)
                elif effect == 'confuse_and_coins':
                    self.assertNotIn('혼란', inside.conditions)
                    self.assertNotIn('혼란', outside.conditions)
                    self.assertEqual(receipt['target_ids'], [])
                    self.assertEqual(len(e._gmax_coin_rewards), 1)
                else:
                    self.assertNotIn(inside.entity_id, receipt['target_ids'])
                    self.assertIn(outside.entity_id, receipt['target_ids'])
                    self.assertTrue(outside.spec[GMAX.EFFECTS])
                restored = Engine.import_state(self.r, json.loads(json.dumps(e.export_state())))
                self.assertEqual(restored._gmax_payload_receipts, e._gmax_payload_receipts)

    def test_gold_rush_uses_native_body_area_and_never_entire_field(self):
        e, actor, (inside, outside), base, mid = self.mapped_world('C2CSV-MOVE-R1021')
        edge = Combatant(self.r, build_pokemon(self.r, 'Snorlax', 100,
                         name='body-edge', side='wild', abilities=[]))
        edge.pos = (13, 4); e.gm.add_combatant(edge)
        e.gm.set_footprint(edge, [(0, 0), (-1, 0), (-2, 0), (-3, 0), (-4, 0)],
                           reason='body overlaps actual attack area beyond its anchor')
        self.mapped_use(e, actor, inside, base, mid, 17)
        completion = next(iter(e._move_completions.values()))
        actual_ids = {target.entity_id for target in COMPLETE.actual_recipients(completion)}
        self.assertEqual(actual_ids, {inside.entity_id, edge.entity_id})
        self.assertEqual(set(e._gmax_payload_receipts[-1]['target_ids']), actual_ids)
        self.assertIn('혼란', inside.conditions); self.assertIn('혼란', edge.conditions)
        self.assertNotIn('혼란', outside.conditions)
        self.assertEqual(outside.hp, outside.max_hp)

    def test_printed_smite_half_damage_and_zero_damage_exception_are_native(self):
        damages = []
        for face in (17, 1):
            e, actor, (inside, outside), base, mid = self.mapped_world('C2CSV-MOVE-R1021')
            damages.append(self.mapped_use(e, actor, inside, base, mid, face))
        self.assertEqual(damages[1], damages[0] // 2)
        e, actor, (inside, outside), base, mid = self.mapped_world('C2CSV-MOVE-R1021')
        e.gm.set_types(inside, ['고스트'], reason='actual Normal damage immunity')
        self.mapped_use(e, actor, inside, base, mid, 1)
        outcome = COMPLETE.recipient_result(next(iter(e._move_completions.values())), inside)
        self.assertEqual(outcome['dealt'], 0); self.assertFalse(outcome['hit'])
        self.assertIn('혼란', inside.conditions)
        self.assertEqual(len(HISTORY.records(inside)), 1)
        self.assertEqual(HISTORY.records(inside)[0]['receipt']['requested'], 0)
        self.assertEqual(HISTORY.current_round(e, inside), 0)

    def test_native_smite_history_feeds_metal_burst_after_cold_restore_once(self):
        e, actor, (inside, outside), base, mid = self.mapped_world('C2CSV-MOVE-R1021')
        e.gm.set_position(actor, (8, 4), reason='actual adjacent burst recipient')
        self.learn_retaliation(e,inside,'move/메탈버스트','actually learned retaliation')
        for stat in ('def', 'spd'):
            e.gm.set_stage(inside, stat, value=-6, reason='actual low defense for HP and temporary HP loss')
        e.gm.set_temp_hp(inside, 3, duration_seconds=60, reason='actual temporary HP absorption')
        before = {'hp': inside.hp, 'temporary_hp': inside.temp_hp}
        requested = self.mapped_use(e, actor, inside, base, mid, 1)
        received = HISTORY.records(inside)
        self.assertEqual(len(received), 1)
        row = received[0]
        self.assertEqual(row['attacker_id'], actor.entity_id)
        self.assertEqual(row['target_id'], inside.entity_id)
        self.assertEqual(row['move_type'], '노말')
        self.assertEqual(row['receipt']['source'], mid)
        self.assertEqual(row['receipt']['requested'], requested)
        self.assertEqual(row['receipt']['before'], before)
        self.assertEqual(row['receipt']['after'], {'hp': inside.hp, 'temporary_hp': inside.temp_hp})
        self.assertEqual(row['receipt']['net_temporary_hp_loss'], 3)
        amount = HISTORY.current_round(e, inside)
        self.assertEqual(amount, before['hp'] + before['temporary_hp'] - inside.hp - inside.temp_hp)
        self.assertGreater(amount, 3)
        self.assertEqual(self.r.move('move/메탈버스트')['_source']['record_span'], [776, 776])
        completion = next(row for row in e._move_completions.values() if row['move_id'] == mid)
        self.assertFalse(COMPLETE.recipient_result(completion, inside)['hit'])
        self.assertNotIn('혼란', inside.conditions)
        with self.assertRaisesRegex(ValueError, 'live native Move recipient'):
            HISTORY.apply_smite(e, actor, inside, self.r.move(mid), requested, '노말')
        self.assertEqual(HISTORY.records(inside), received)
        e.end_of_turn(actor)
        e = Engine.import_state(self.r, json.loads(json.dumps(e.export_state())))
        index = {member.entity_id: member for member in e.time_actors()}
        actor, inside = index[actor.entity_id], index[inside.entity_id]
        self.assertEqual(HISTORY.records(inside), received)
        e.lose_hp(inside, 7, source='passive loss excluded from actual attack history')
        self.assertEqual(HISTORY.current_round(e, inside), amount)
        e.start_of_turn(inside, initiative_count=10)
        before_hp = actor.hp
        e.use_move_on(inside, actor, 'move/메탈버스트', e.everyone)
        self.assertEqual(before_hp - actor.hp, amount)
        self.assertEqual(actor.move_uses[mid], 1)
        self.assertEqual(len(e._gmax_coin_rewards), 1)
        self.assertEqual(HISTORY.records(actor)[-1]['receipt']['source'], 'move/메탈버스트')
        self.assertEqual(HISTORY.records(actor)[-1]['application_kind'], 'hp_loss')

    def test_bide_pending_scope_counts_later_smite_without_turning_miss_into_hit(self):
        import bide as BIDE
        e, actor, (inside, striker), base, mid = self.mapped_world('C2CSV-MOVE-R1021', first='outside')
        e.gm.set_position(actor, (8, 4), reason='actual later Bide release recipient')
        e.gm.set_position(striker, (9, 5), reason='actual initial Bide trigger attacker')
        self.learn_retaliation(e,striker,'move/몸통박치기','actually learned initial attack')
        self.learn_retaliation(e,inside,BIDE.SOURCE,'actually learned Bide reaction')
        self.assertEqual(self.r.move(BIDE.SOURCE)['_source']['record_span'], [446, 446])
        with patch.object(Engine, 'd20', return_value=17):
            e.use_move_on(striker, inside, 'move/몸통박치기', e.everyone, set_damage=True)
        trigger = next(key for key, event in reversed(list(e._passive_events.items()))
                       if event['actor'] is striker and event['target'] is inside
                       and event.get('phase') == 'producer_return_boundary')
        BIDE.reaction(e, inside, trigger, payment='next')
        initial_sequence = BIDE.pending(inside)['damage_sequence']
        self.assertEqual(initial_sequence, 1)
        e.end_of_turn(striker); e.start_of_turn(actor, initiative_count=10)
        self.mapped_use(e, actor, inside, base, mid, 1)
        later = [row for row in HISTORY.records(inside) if row['sequence'] > initial_sequence]
        self.assertEqual(len(later), 1)
        amount = HISTORY.amount(later[0]); self.assertGreater(amount, 0)
        completion = next(row for row in e._move_completions.values() if row['move_id'] == mid)
        self.assertFalse(COMPLETE.recipient_result(completion, inside)['hit'])
        miss_event = next(key for key, event in reversed(list(e._passive_events.items()))
                          if event.get('completion_id') == completion['id'] and event['target'] is inside
                          and event.get('phase') == 'producer_return_boundary')
        pending = deepcopy(BIDE.pending(inside))
        with self.assertRaisesRegex(ValueError, 'damaging Move Hit'):
            BIDE.reaction(e, inside, miss_event, payment='next')
        self.assertEqual(BIDE.pending(inside), pending)
        e.lose_hp(inside, 7, source='passive loss outside Bide damage scope')
        e.end_of_turn(actor)
        e = Engine.import_state(self.r, json.loads(json.dumps(e.export_state())))
        index = {member.entity_id: member for member in e.time_actors()}
        actor, inside = index[actor.entity_id], index[inside.entity_id]
        e.start_of_turn(inside, initiative_count=0)
        before_hp = actor.hp
        BIDE.release(e, inside, actor)
        self.assertEqual(before_hp - actor.hp, amount)
        self.assertIsNone(BIDE.pending(inside))
        self.assertEqual(inside.move_uses[BIDE.SOURCE], 1)
        self.assertEqual(actor.move_uses[mid], 1)

    def test_gold_rush_mixed_hit_and_smite_miss_keep_distinct_recipients(self):
        e, actor, (inside, outside), base, mid = self.mapped_world('C2CSV-MOVE-R1021')
        missed = Combatant(self.r, build_pokemon(self.r, 'Snorlax', 100,
                           name='evading-recipient', side='wild', abilities=[]))
        missed.pos = (10, 4); e.gm.add_combatant(missed)
        e.gm.set_footprint(missed, [(0, 0)], reason='actual second recipient body')
        e.gm.set_stage(inside, 'eva', value=-6, reason='actual low evasion')
        e.gm.set_stage(missed, 'eva', value=6, reason='actual high evasion')
        self.mapped_use(e, actor, inside, base, mid, 3)
        completion = next(iter(e._move_completions.values()))
        self.assertTrue(COMPLETE.recipient_result(completion, inside)['hit'])
        self.assertFalse(COMPLETE.recipient_result(completion, missed)['hit'])
        self.assertGreater(COMPLETE.recipient_result(completion, missed)['dealt'], 0)
        self.assertIn('혼란', inside.conditions)
        self.assertNotIn('혼란', missed.conditions)
        self.assertNotIn('혼란', outside.conditions)
        self.assertEqual(e._gmax_payload_receipts[0]['target_ids'], [inside.entity_id])
        self.assertEqual(len(e._gmax_coin_rewards), 1)

    def test_actual_drown_out_cancellation_has_no_gmax_effect_or_coin(self):
        import musician as MUSICIAN
        for clause in ('C2CSV-MOVE-R1021', 'C2CSV-MOVE-R1034', 'C2CSV-MOVE-R1035', 'C2CSV-MOVE-R1041'):
            with self.subTest(clause=clause):
                e, actor, (inside, outside), base, mid = self.mapped_world(clause)
                # Exercise the supported keyword extension with a real native cancellation.
                e.gm.set_ability(inside, '소리묻히기', reason='actual counter ability')
                actor.registry.append({'type': 'gain_keyword', 'keyword': '소리', 'moves': 'all'})
                e.rulings.add_answer('drown_out_no_accuracy',
                    {'source': MUSICIAN.DROWN, 'move_id': mid, 'dc': 1,
                     'reason': 'GM declares DC 1 for this no-Accuracy cancellation scenario; not a printed default'},
                    reason='explicit source-specific no-Accuracy Drown Out ruling')
                MUSICIAN.request_drown_out(e, inside, reason='accept native cancellation')
                self.mapped_use(e, actor, inside, base, mid, 1)
                completion = next(iter(e._move_completions.values()))
                self.assertTrue(all(row['cancelled'] for row in completion['results'].values()))
                self.assertEqual(e._gmax_payload_receipts, [])
                self.assertEqual(e._gmax_coin_rewards, [])
                self.assertFalse(e.hazards)
                self.assertNotIn(GMAX.EFFECTS, outside.spec)
                self.assertEqual(HISTORY.records(inside), [])

    def test_coin_payment_is_exact_once_after_loss_and_cold_restore(self):
        e, actor, (inside, outside), base, mid = self.mapped_world('C2CSV-MOVE-R1021')
        owner = Combatant(self.r, build_trainer(self.r, 'coin-owner', 20,
            dict(hp=30, atk=10, **{'def': 10}, spa=10, spd=10, spe=10),
            moves=[], extra={'money': 73}, side='party'))
        owner.pos = (25, 25); e.gm.add_combatant(owner)
        actor.spec['trainer_id'] = owner.entity_id
        e.gm.observe_loyalty(actor, 6, reason='observed current-owner obedience before native G-Max use')
        self.mapped_use(e, actor, inside, base, mid, 1)
        reward = e._gmax_coin_rewards[0]
        amount = actor.level * sum(reward['rolls'])
        self.assertEqual(owner.spec['money'], 73)
        self.assertEqual(reward['recipient_id'], owner.entity_id)
        restored = Engine.import_state(self.r, json.loads(json.dumps(e.export_state())))
        index = {member.entity_id: member for member in restored.time_actors()}
        restored.end_of_turn(index[actor.entity_id]); restored.end_encounter()
        restored.gm.observe_encounter_outcome(encounter_id='gmax-loss', participants=restored.everyone,
            winner=index[inside.entity_id], trainer_battle=False, reason='user side lost')
        paid = restored._gmax_coin_rewards[0]
        self.assertEqual(index[owner.entity_id].spec['money'], 73 + amount)
        self.assertEqual(paid['payment']['amount'], amount)
        self.assertEqual(paid['status'], 'collected')
        self.assertNotIn('money', index[inside.entity_id].spec)
        restored = Engine.import_state(self.r, json.loads(json.dumps(restored.export_state())))
        restored.end_encounter()
        index = {member.entity_id: member for member in restored.time_actors()}
        self.assertEqual(index[owner.entity_id].spec['money'], 73 + amount)
        restored._gmax_coin_rewards.append(deepcopy(restored._gmax_coin_rewards[0]))
        with self.assertRaisesRegex(ValueError, 'gmax_state'):
            restored.export_state()

    def test_coin_payment_invalid_balance_rolls_back_whole_native_end(self):
        e, actor, (inside, outside), base, mid = self.mapped_world('C2CSV-MOVE-R1021')
        self.mapped_use(e, actor, inside, base, mid, 1)
        e.end_of_turn(actor)
        actor.spec['money'] = -1
        before = deepcopy((e._gmax_coin_rewards, actor.spec[GMAX.STATE], actor.form, e.encounter_active))
        with self.assertRaises(ValueError):
            e.end_encounter()
        self.assertEqual(before, (e._gmax_coin_rewards, actor.spec[GMAX.STATE], actor.form, e.encounter_active))
        actor.spec['money'] = 0
        e.end_encounter()
        self.assertEqual(actor.spec['money'], e._gmax_coin_rewards[0]['amount'])

    def test_all_nine_actual_payload_producers(self):
        observed = set()
        for clause in sorted(COMPLETED):
            with self.subTest(clause=clause):
                engine, actor, target, base, move_id, result = self.activate(clause)
                self.assertEqual(engine._gmax_payload_receipts[-1]["clause_id"], clause)
                observed.add(clause)
                effect = self.declarations[clause]["effect"]
                rows = target.spec.get(GMAX.EFFECTS, [])
                if effect == "confuse_and_coins":
                    self.assertIn("혼란", target.conditions)
                    reward = engine._gmax_coin_rewards[-1]
                    self.assertEqual(reward["amount"], actor.level * sum(reward["rolls"]))
                elif effect == "sandblast":
                    self.assertIn("수렁", target.conditions)
                    self.assertEqual(rows[-1]["turns"], 4)
                elif effect == "bind":
                    self.assertIn("조이기", target.conditions)
                    self.assertTrue(rows[-1]["persists_if_owner_leaves"])
                elif effect == "delayed_sleep":
                    self.assertEqual(rows[-1]["face"], 2)
                    self.assertTrue(rows[-1]["pending"])
                    self.assertNotIn("잠듦", target.conditions)
                elif effect == "disable_and_suppress_last_move":
                    disabled = rows[-1]["disabled_move_id"]
                    self.assertEqual(disabled, target.last_move)
                    self.assertIn("사슬묶기", target.conditions)
                    self.assertIn("억압", target.conditions)
                else:
                    self.assertEqual(rows[-1]["kind"], "typed_residual")
                    self.assertEqual(rows[-1]["turns"], 4)
        self.assertEqual(observed, COMPLETED)

    def test_turn_lifetimes_vortex_exception_depletion_and_encounter_restore(self):
        engine, actor, target, _, _, _ = self.activate("C2CSV-MOVE-R1016")
        target.hp = target.max_hp
        initial = target.hp
        loss = target.base_max_hp // 6
        for remaining in (3, 2, 1, 0):
            GMAX.start_turn(engine, target)
            self.assertEqual(target.hp, initial - loss * (4 - remaining))
            rows = target.spec.get(GMAX.EFFECTS, [])
            self.assertEqual(rows[0]["turns"] if rows else 0, remaining)

        engine, actor, target, _, _, _ = self.activate("C2CSV-MOVE-R1043")
        GMAX.start_turn(engine, target)
        self.assertIn("잠듦", target.conditions)
        self.assertNotIn(GMAX.EFFECTS, target.spec)

        engine, actor, target, _, _, _ = self.activate("C2CSV-MOVE-R1041")
        actor.on_field = False
        VORTEX.turn_start(engine, target)
        self.assertIn("조이기", target.conditions)

        engine, actor, target, _, _, _ = self.activate("C2CSV-MOVE-R1046")
        row = target.spec[GMAX.EFFECTS][0]
        self.assertIn("억압", target.conditions)
        self.assertFalse(engine.cure_status(target, "억압"))
        self.assertIn("억압", target.conditions)
        import condition_instances as CONDITIONS
        CONDITIONS.boundary(engine, round_end=True)
        self.assertIn("억압", target.conditions)
        allowed, reason = CONDITIONS.move_allowed(engine, target, self.r.move(row["disabled_move_id"]))
        self.assertFalse(allowed)
        non_at_will = next(self.r.move(mid) for mid in target.moves
                           if self.r.move(mid)["id"] != row["disabled_move_id"] and
                           __import__("frequency").move_frequency(engine, mid, target)[0] != "at_will")
        self.assertFalse(GMAX.move_allowed(engine, target, non_at_will)[0])
        GMAX.end_encounter(engine, [actor, target])
        self.assertNotIn(GMAX.STATE, actor.spec)
        self.assertNotIn(GMAX.EFFECTS, target.spec)
        self.assertNotIn("억압", target.conditions)
        self.assertIsNone(actor.form)

    def test_save_restore_preserves_effect_sequence_coin_and_receipt_authority(self):
        engine, actor, target, _, _, _ = self.activate("C2CSV-MOVE-R1021")
        payload_before = deepcopy(engine._gmax_payload_receipts)
        reward_before = deepcopy(engine._gmax_coin_rewards)
        state = engine.export_state()
        restored = Engine.import_state(self.r, state)
        self.assertEqual(restored._gmax_payload_receipts, payload_before)
        self.assertEqual(restored._gmax_coin_rewards, reward_before)
        self.assertEqual(restored._gmax_effect_sequence, engine._gmax_effect_sequence)
        self.assertTrue(restored.validate_state()["valid"])
        owner = next(row for row in restored.time_actors() if row.side == "party")
        self.assertEqual(owner.form, owner.spec[GMAX.STATE]["form_id"])
        restored._gmax_payload_receipts[0]["completion_id"] = "forged"
        with self.assertRaisesRegex(ValueError, "gmax_state"):
            restored.export_state()


if __name__ == "__main__":
    unittest.main()
