"""C11-142 native connections and the printed modified Save band 1 through 8."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import unittest
import test_attack_loss_provenance as FIX
from engine import Combatant, Engine, Rules
import condition_instances as CI
import condition_recovery as RECOVERY
import effect_instances as E
import effects as FX
import effects_ext as EXT
import eldritch_magic as EM
import temporary_hp as TEMP
import turn as TURN
import world_entities as W

ROOT = Path(__file__).resolve().parents[1]


def legacy_after_confusion_save(engine, actor, check):
    """Frozen pre-repair native hook: produce real unversioned <=8 history."""
    import common_checks as C
    row = EM.active(actor)
    if row is None:
        return
    EM.validate_record(actor, row)
    if getattr(engine, '_active_turn_actor', None) is not actor or '잠듦' in actor.conditions:
        raise ValueError('Dementia rider requires its actual awake holder end-turn save')
    turn = C.integer(actor.custom_conditions.get('combat_turn_serial'), 'Dementia holder turn', 1)
    if row['saves'] and row['saves'][-1]['turn'] == turn:
        if row['saves'][-1]['check'] != check:
            raise ValueError('Dementia cannot replace its actual end-turn save')
        return row['saves'][-1]
    effective = check['natural'] + check['base_dc'] - check['dc']
    event = {'turn': turn, 'at': engine.elapsed_seconds, 'check': dict(check),
             'effective': effective, 'stat': None, 'before': None, 'after': None,
             'stage_receipt': None}
    if effective <= 8:
        import combat_stage_sources as STAGES
        stat = engine.rng.choice(STAGES.STATS)
        before = actor.stages[stat]
        issuer = W.actor_index(engine)[row[E.KEY]['applied_by_actor_id']]
        result = FX.run_effects(engine, issuer, actor,
                               [{'type': 'stage_change', 'stat': stat, 'delta': -1}],
                               {'hit': True}, row['source'])
        if result.pending or result != (1, 0) or result.outcomes[0].status != 'completed':
            raise ValueError('Dementia native stage contribution did not complete')
        event.update(stat=stat, before=before, after=actor.stages[stat],
                     stage_receipt=result.outcomes[0].receipt)
    row['saves'].append(event)
    return event


class EldritchMagicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # These end-save/AoO assertions explicitly exercise the February revision.
        cls.r = Rules(str(ROOT), ruleset='core-confusion-feb2016')
    actor = FIX.AttackLossTests.actor
    setUp = FIX.AttackLossTests.setUp

    def adopt(self, actor=None):
        return EM.adopt(self.e, actor or self.a, reason='GM explicitly adopts C11-142 on this actual actor')

    def hit(self, move='move/분노의앞니', target=None, face=16, actor=None, engine=None):
        engine = engine or self.e
        actor = actor or self.a
        TURN.reset_budget(engine, actor)
        with patch.object(Engine, 'd20', return_value=face) as draw:
            engine.use_move_on(actor, target or self.b, move,
                               engine.everyone or engine.gm.everyone, set_damage=True)
        return draw

    def valid(self, engine=None):
        result = (engine or self.e).validate_state()
        self.assertTrue(result['valid'], result['issues'])

    def end_save(self, face, stat='def'):
        active=getattr(self.e,'_active_turn_actor',None)
        if active is not None:self.e.end_of_turn(active)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.b)
        self.assertFalse(TURN.can_aoo(self.e, self.b))
        with patch.object(Engine, 'd20', return_value=face) as draw, patch.object(
                type(self.e.rng), 'choice', return_value=stat) as choose:
            self.e.end_of_turn(self.b)
        return draw, choose

    def test_actual_pokemon_and_trainer_adoption_reaches_native_damaging_hit_at_16(self):
        for kind in ('pokemon', 'trainer'):
            with self.subTest(kind=kind):
                self.setUp()
                if kind == 'trainer':
                    self.a = self.actor('actual trainer', kind='trainer')
                original = deepcopy(self.r.move('move/분노의앞니'))
                self.adopt()
                draw = self.hit()
                row = EM.active(self.b)
                self.assertIsNotNone(row)
                self.assertEqual(draw.call_count, 1)
                self.assertEqual(row['source'], 'move/분노의앞니')
                self.assertEqual(row[E.KEY]['applied_by_actor_id'], self.a.entity_id)
                self.assertEqual(row['effect'], EM.PAYLOAD)
                self.assertEqual(self.b.conditions, {'혼란'})
                self.assertEqual(EXT.save_dc(self.e, self.b, None, 16), 18)
                self.assertIsNone(EM.active(self.a))
                self.assertEqual(self.r.move('move/분노의앞니'), original)
                self.valid()

    def test_actual_15_miss_status_no_face_and_public_accuracy_observation_do_not_inflict(self):
        # Keep the historical ID: damaging never-miss Swift still has a natural
        # face (ch07:263-268,301; moves.csv:663). Only no-check Status is excluded.
        for name, face in (('move/분노의앞니', 15), ('move/분노의앞니', 1)):
            with self.subTest(move=name, face=face):
                self.setUp()
                self.adopt()
                self.hit(name, face=face)
                self.assertIsNone(EM.active(self.b))
                self.assertNotIn('혼란', self.b.conditions)
                self.valid()
        self.setUp()
        self.adopt()
        draw = self.hit('move/스피드스타', face=20)
        row = EM.active(self.b)
        self.assertIsNotNone(row)
        event = self.e._move_completions[row['origin']['id']][EM.FIELD][self.b.entity_id]
        self.assertEqual((draw.call_count, event['natural'], event['effect_face']), (1, 20, 20))
        self.valid()
        self.setUp()
        self.a.moves.append('move/칼춤')
        self.a.spec['moves'] = self.a.moves[:]
        self.adopt()
        self.hit('move/칼춤', target=self.a, face=20)
        self.assertIsNone(EM.active(self.a))
        self.e.accuracy_check(self.a, self.b, self.r.move('move/분노의앞니'), fixed_roll=20)
        with self.assertRaisesRegex(ValueError, 'actual dispatched native Ability'):
            EM.after_hit(self.e, self.a, self.b, self.r.move('move/분노의앞니'), 20)
        self.assertIsNone(EM.active(self.b))
        self.valid()

    def test_legal_damaging_hit_with_no_hp_loss_still_afflicts_actual_recipient(self):
        self.adopt()
        TEMP.grant(self.e, self.b, 1000)
        hp = self.b.hp
        self.hit()
        self.assertEqual(self.b.hp, hp)
        self.assertLess(self.b.temp_hp, 1000)
        self.assertIsNotNone(EM.active(self.b))
        self.valid()

    def test_ordinary_confusion_and_reapplication_use_one_instance_and_native_curse_origin(self):
        self.e.apply_status(self.b, '혼란')
        self.adopt()
        self.hit()
        first = EM.active(self.b)
        completion = list(self.e._move_completions.values())[-1]
        # A replay can only return the original recipient receipt; it cannot
        # re-inflict from the completed attack or convert its multihit suffix.
        before = self.e.export_state()
        EM.after_hit(self.e, self.a, self.b, self.r.move('move/분노의앞니'), 20,
                     completion_id=completion['id'])
        self.assertEqual(self.e.export_state(), before)
        self.assertFalse(self.e.apply_status(self.b, '혼란', source='move/이상한빛', applied_by=self.a))
        self.assertNotIn('저주', self.b.conditions)
        second = self.actor('second actual Eldritch inflictor')
        self.adopt(second)
        self.hit(actor=second)
        self.assertIs(EM.active(self.b), first)
        self.assertEqual(CI.records(self.b, '혼란'), [first])
        self.assertIn('저주', self.b.conditions)
        self.assertIs(self.b.custom_conditions['curse_origin'], second)
        self.assertEqual(EXT.save_dc(self.e, self.b, None, 16), 18)
        self.e.cure_status(self.b, '혼란')
        self.assertIsNone(EM.active(self.b))
        self.assertIn('저주', self.b.conditions)
        self.assertEqual(EXT.save_dc(self.e, self.b, None, 16), 16)
        self.valid()

    def test_withdrawal_retains_inflicted_source_and_both_native_restore_paths_keep_identity(self):
        self.adopt()
        self.hit()
        identity = EM.active(self.b)['id']
        self.assertTrue(EM.withdraw(self.e, self.a, reason='GM withdraws future Eldritch attacks'))
        self.hit('move/용의분노')
        self.assertNotIn('저주', self.b.conditions)
        self.assertEqual(EM.active(self.b)['id'], identity)
        snapshot = self.e.gm.snapshot()
        saved = self.e.export_state()
        self.e.cure_status(self.b, '혼란')
        self.e.gm.restore(snapshot)
        for world in (self.e, Engine.import_state(self.r, json.loads(json.dumps(saved)))):
            actual = W.actor_index(world)[self.b.entity_id]
            self.assertEqual(EM.active(actual)['id'], identity)
            self.assertEqual(EXT.save_dc(world, actual, None, 16), 18)
            world.cure_status(actual, '혼란')
            self.assertIsNone(EM.active(actual))
            self.assertEqual(EXT.save_dc(world, actual, None, 16), 16)
            self.valid(world)

    def test_shared_save_dc_owner_applies_penalty_to_general_and_other_condition_checks(self):
        self.adopt()
        self.hit()
        for condition, dc in ((None, 16), ('마비', 11), ('잠듦', 16)):
            with self.subTest(condition=condition):
                out = RECOVERY.saving_check(self.e, self.b, condition, dc, fixed=dc)
                self.assertEqual(out['dc'], dc + 2)
                self.assertFalse(out['passed'])
        self.b.save_mod = 3
        out = RECOVERY.saving_check(self.e, self.b, None, 16, fixed=15)
        self.assertEqual(out['dc'], 15)
        self.assertTrue(out['passed'])
        self.valid()

    def test_changed_adoption_and_new_native_source_receipt_are_rejected(self):
        self.adopt()
        original = deepcopy(self.a.spec[EM.ADOPTION])
        self.a.spec[EM.ADOPTION]['actor_id'] = self.b.entity_id
        before = (self.a.budget.copy(), self.a.move_uses.copy(), self.e.rng.getstate())
        with self.assertRaisesRegex(ValueError, 'actor-owned'):
            self.e.use_move_on(self.a, self.b, 'move/분노의앞니', self.e.everyone)
        self.assertEqual((self.a.budget, self.a.move_uses, self.e.rng.getstate()), before)
        self.a.spec[EM.ADOPTION] = original
        self.hit()
        producer = list(self.e._move_completions.values())[-1]
        event = producer[EM.FIELD][self.b.entity_id]
        face = event['natural']
        event['natural'] = 15
        self.assertFalse(self.e.validate_state()['valid'])
        event['natural'] = face
        self.valid()

    def test_actual_shared_area_attack_reuses_one_accuracy_face_for_all_real_targets(self):
        import test_category2_csv_item_transfers as AREA_FIX
        from grid import Grid
        f = AREA_FIX.Tests()
        f.r = self.r
        e, a, b, c, mid = f.fixture('불태우기', held=(None, None, None), seed=1)
        e.grid = Grid(10, 10)
        EM.adopt(e, a, reason='actual area attacker explicitly adopts C11-142')
        with patch.object(Engine, 'd20', return_value=16) as draw:
            e.use_move_on(a, b, mid, e.everyone, set_damage=True)
        self.assertEqual(draw.call_count, 1)
        self.assertIsNotNone(EM.active(b))
        self.assertIsNotNone(EM.active(c))
        self.assertIsNone(EM.active(a))
        producer = list(e._move_completions.values())[-1]
        self.assertEqual(set(producer[EM.FIELD]), {b.entity_id, c.entity_id})
        self.valid(e)

    def test_real_weapon_effect_range_bonus_reaches_16_without_a_new_accuracy_draw(self):
        import test_category2_optional_weapon_framework as WEAPON_FIX
        import optional_weapon_framework as FW
        import improvised_weapons as IMPROVISED
        f = WEAPON_FIX.OptionalWeaponFrameworkTests()
        f.r = Rules(self.r.root, ruleset='all')
        cases = (('arcane_grant', True, 'move/렌딩-스펠', False),
                 ('arcane_struggle', True, None, False),
                 ('ordinary_struggle', False, None, False),
                 ('fragile_struggle', False, None, True))
        for name, arcane, granted, breaks in cases:
            with self.subTest(weapon_path=name):
                e, a, foe, _ = f.fixture(occult=4, combat=4)
                uid = f.weapon(e, a, 'eldritch/' + name, arcane=arcane,
                               moves=[granted] if granted else [])
                if arcane:
                    FW.bond(e, a, uid, family='arcane')
                if breaks:
                    IMPROVISED.configure(e, a, uid, ac_mode='accuracy_roll', ac_delta=0,
                        db_delta=0, break_after_attack=True, gm_id='gm/eldritch-weapon',
                        source='gm/observed-fragile-weapon', reason='this actual weapon breaks after its attack')
                key = FW.equip(e, a, uid)
                mid = granted or key
                EM.adopt(e, a, reason='actual weapon user adopts C11-142')
                f.start(e, a)
                face = 13 if arcane else 16
                with patch.object(Engine, 'd20', return_value=face) as draw:
                    e.use_move(a, foe, mid, weapon_id=uid, set_damage=True)
                self.assertEqual(draw.call_count, 1)
                row = EM.active(foe)
                self.assertIsNotNone(row)
                self.assertEqual(row['source'], mid)
                completion = e._move_completions[row['origin']['id']]
                event = completion[EM.FIELD][foe.entity_id]
                self.assertEqual((event['natural'], event['effect_face']), (face, 16))
                self.assertEqual(completion['move']['_weapon_attack']['key'], key)
                self.assertEqual(row['attack']['class'], '특수' if arcane else '물리')
                self.assertIs(completion['actor'], a)
                if not granted:
                    self.assertEqual(e.r.moves[mid]['source'], 'weapon')
                    self.assertEqual(tuple(e.r.selection.dependencies[mid]),
                                     ('combat/struggle', 'ch09-equipment/장비/무기'))
                self.valid(e)
                if arcane:
                    continue
                # Native destruction releases equipment after completion; the
                # inflicted source keeps the original derived definition.
                self.assertEqual(W.physical_lifecycle(e._physical_objects[uid])['destroyed'], breaks)
                if breaks:
                    self.assertNotIn(key, a.custom_conditions.get('equipped_weapons', {}))
                    self.assertNotIn(key, a.moves)
                fingerprint, origin = row['source_fingerprint'], row['origin']['id']
                original_move = deepcopy({k: v for k, v in completion['move'].items()
                                          if k != '_actual_targets'})
                target_ids = tuple(c.entity_id for c in completion['move']['_actual_targets'])
                saved = e.export_state()
                e.gm.snapshot('eldritch-weapon')
                e.cure_status(foe, '혼란')
                e.gm.restore('eldritch-weapon')
                restored = Engine.import_state(e.r, json.loads(json.dumps(saved)))
                for world in (e, restored):
                    actual, target = (W.actor_index(world)[actor.entity_id] for actor in (a, foe))
                    retained = EM.active(target)
                    self.assertEqual(retained['source_fingerprint'], fingerprint)
                    self.assertEqual(retained['origin']['id'], origin)
                    actual_move = world._move_completions[origin]['move']
                    self.assertEqual({k: v for k, v in actual_move.items() if k != '_actual_targets'}, original_move)
                    self.assertEqual(tuple(c.entity_id for c in actual_move['_actual_targets']), target_ids)
                    self.assertTrue(all(W.actor_index(world)[c.entity_id] is c
                                        for c in actual_move['_actual_targets']))
                    self.assertEqual(W.physical_lifecycle(world._physical_objects[uid])['destroyed'], breaks)
                    self.assertEqual(EXT.save_dc(world, target, None, 16), 18)
                    if breaks:
                        self.assertNotIn(key, actual.moves)
                    self.valid(world)
                    world.cure_status(target, '혼란')
                    self.assertIsNone(EM.active(target))
                    self.valid(world)

    def test_actual_pass_creature_child_uses_native_hit_and_does_not_afflict_objects(self):
        import test_pass_moves as PASS_FIX
        import test_physical_object_attacks as OBJECT_FIX
        import test_category2_csv_item_transfers as OBJECT_ACTORS
        f = PASS_FIX.Tests()
        f.base = OBJECT_FIX.Tests()
        f.base.f = OBJECT_ACTORS.Tests()
        f.base.f.r = self.r
        e, a, b, mid, adjudications = f.fixture()
        EM.adopt(e, a, reason='actual Pass attacker adopts C11-142')
        with patch.object(Engine, 'd20', return_value=16):
            out = f.execute(e, a, mid, adjudications)
        self.assertIsNotNone(EM.active(b))
        producer = e._move_completions[out['completion_id']]
        self.assertEqual(set(producer[EM.FIELD]), {b.entity_id})
        self.assertEqual(len(CI.records(b, '혼란')), 1)
        self.valid(e)

    def test_actual_intercept_afflicts_only_native_recipient_after_original_accuracy(self):
        import test_category2_move_defense_reactions as DEFENSE_FIX
        f = DEFENSE_FIX.MoveDefenseReactionsTests()
        f.rules = self.r
        f.setUp()
        EM.adopt(f.e, f.a, reason='actual intercepted attacker adopts C11-142')
        f.watch()
        with patch.object(Engine, 'd20', return_value=16):
            event = f.waiting()
        f.choose(event, options=f.melee())
        self.assertIsNone(EM.active(f.t))
        self.assertIsNotNone(EM.active(f.r))
        producer = f.completion()
        self.assertEqual(set(producer[EM.FIELD]), {f.r.entity_id})
        self.valid(f.e)

    def test_actual_published_status_ability_attack_is_excluded(self):
        from ruleset import bind_rule_identity
        import test_foundation_maneuvers_opposed as OPPOSED_FIX
        f = OPPOSED_FIX.OpposedTests()
        f.r = f.rules = self.r
        f.setUp()
        f.e.gm.set_ability(f.a, '현혹', reason='actual native Status attack Ability')
        EM.adopt(f.e, f.a, reason='actual Status ability attacker adopts C11-142')
        uid = self.r.selection.resolve_name('현혹', ('ability/',))
        effects = bind_rule_identity(self.r.ability_effects['현혹'], uid)
        with patch.object(Engine, 'd20', return_value=20) as draw:
            EXT.h_attack(f.e, f.a, f.b, effects[0], {'attacker': f.a, 'target': f.b})
        self.assertEqual(draw.call_count, 1)
        self.assertIn('잠듦', f.b.conditions)
        self.assertIsNone(EM.active(f.b))
        self.valid(f.e)

    def test_subtype_reuses_native_confusion_self_loss_without_a_second_attack_draw(self):
        self.adopt()
        self.hit()
        self.e.rng.seed(1)
        before = self.b.hp
        expected = self.b.staged('atk') // 2
        draw = self.hit(actor=self.b, target=self.a)
        completion = list(self.e._move_completions.values())[-1]
        self.assertEqual(completion['confusion']['face'], 1)
        self.assertEqual(completion['confusion']['result']['amount'], expected)
        self.assertEqual(self.b.hp, before - expected)
        self.assertEqual(draw.call_count, 1)
        self.assertIsNone(EM.active(self.a))
        self.valid()

    def test_sleep_suppresses_the_actual_confusion_end_save_and_added_rider(self):
        self.adopt()
        self.hit()
        active=getattr(self.e,'_active_turn_actor',None)
        if active is not None:self.e.end_of_turn(active)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.b)
        self.assertFalse(TURN.can_aoo(self.e, self.b))
        self.e.apply_status(self.b, '잠듦')
        with patch.object(Engine, 'd20', return_value=20), patch.object(
                RECOVERY, 'saving_check', wraps=RECOVERY.saving_check) as checks:
            self.e.end_of_turn(self.b)
        self.assertFalse(any(call.args[2] == '혼란' for call in checks.call_args_list))
        self.assertEqual(EM.active(self.b)['saves'], [])
        self.assertIn('혼란', self.b.conditions)
        self.valid()

    def test_native_confusion_immunity_and_volatile_cures_own_the_subtype_lifetime(self):
        self.adopt()
        self.e.gm.set_ability(self.b, '마이페이스', reason='actual native Confusion immunity')
        self.hit()
        self.assertIsNone(EM.active(self.b))
        self.assertEqual(EXT.save_dc(self.e, self.b, None, 16), 16)
        self.valid()
        for boundary in ('recall', 'encounter_end'):
            with self.subTest(boundary=boundary):
                self.setUp()
                self.adopt()
                self.hit()
                active=getattr(self.e,'_active_turn_actor',None)
                if active is not None:self.e.end_of_turn(active)
                self.e.start_round(self.e.everyone)
                if boundary == 'recall':
                    self.e.gm.recall(self.b, reason='actual afflicted Pokemon recall')
                else:
                    self.e.end_encounter(self.e.everyone)
                self.assertIsNone(EM.active(self.b))
                self.assertNotIn('혼란', self.b.conditions)
                self.assertEqual(EXT.save_dc(self.e, self.b, None, 16), 16)
                self.valid()

    def test_dementia_save_preflight_refuses_changed_source_before_roll_or_consumable(self):
        import fashion_items as FASHION
        self.adopt()
        self.hit()
        row = EM.active(self.b)
        original = row['source_fingerprint']
        row['source_fingerprint'] = 'changed native source'
        with patch.object(Engine, 'd20') as draw, patch.object(FASHION, 'consume_save_bonus') as consume:
            with self.assertRaisesRegex(ValueError, 'selected damaging attack source'):
                RECOVERY.saving_check(self.e, self.b, None, 16)
        draw.assert_not_called()
        consume.assert_not_called()
        row['source_fingerprint'] = original
        self.valid()

    def test_actual_net_removal_uses_minus_two_without_running_the_confusion_rider(self):
        from tools import test_category3_net_capsule as NET_FIX
        import net_capsule as NET
        f = NET_FIX.NetTests()
        f.rules = Rules(self.r.root, ruleset='core+errata')
        f.setUp()
        for actor in (f.a, f.q):
            actor.spec['size'] = 'Medium'
        f.fire()
        f.q.pos = (4, 0)
        EM.adopt(f.e, f.q, reason='actual Net Cap recipient is struck by an adopted actor')
        self.hit('struggle', actor=f.q, target=f.p, engine=f.e)
        row = EM.active(f.p)
        original = row['source_fingerprint']
        row['source_fingerprint'] = 'changed native source'
        TURN.reset_budget(f.e, f.p)
        before = (deepcopy(f.p.budget), f.e.rng.getstate())
        with self.assertRaisesRegex(ValueError, 'selected damaging attack source'):
            f.e.remove_net(f.p)
        self.assertEqual((f.p.budget, f.e.rng.getstate()), before)
        row['source_fingerprint'] = original
        failed = f.e.remove_net(f.p, fixed=10)
        self.assertFalse(failed['removed'])
        self.assertEqual(failed['check']['dc'], 17)
        TURN.reset_budget(f.e, f.p)
        self.assertTrue(f.e.remove_net(f.p, fixed=12)['removed'])
        self.assertIsNone(NET.active(f.p))
        self.assertEqual(EM.active(f.p)['saves'], [])
        self.valid(f.e)

    def test_actual_breather_checks_minus_two_then_cures_dementia_and_native_repeat_curse(self):
        import test_category2_breather as BREATHER_FIX
        for face, completed in ((16, False), (18, True)):
            with self.subTest(face=face):
                f = BREATHER_FIX.BreatherTests()
                f.r = self.r
                f.setUp()
                f.e.end_of_turn(f.a)
                f.e.start_of_turn(f.b)
                EM.adopt(f.e, f.b, reason='actual Breather actor receives repeated Dementia')
                self.hit('struggle', actor=f.b, target=f.a, engine=f.e)
                self.hit('struggle', actor=f.b, target=f.a, engine=f.e)
                self.assertIs(f.a.custom_conditions['curse_origin'], f.b)
                f.e.end_of_turn(f.b)
                active=getattr(f.e,'_active_turn_actor',None)
                if active is not None:f.e.end_of_turn(active)
                f.e.start_round(f.e.everyone)
                f.e.start_of_turn(f.a)
                f.e.lose_hp(f.b, f.b.base_max_hp, source='actual Curse source fainting')
                out = f.take(fixed_save=face)
                self.assertEqual(out['save']['dc'], 18)
                self.assertEqual(out['completed'], completed)
                self.assertEqual(EM.active(f.a) is None, completed)
                self.assertEqual('저주' not in f.a.conditions, completed)
                if not completed:
                    self.assertEqual(EM.active(f.a)['saves'], [])
                self.valid(f.e)



    def test_misty_native_delay_retains_first_infliction_through_restore_and_withdrawal(self):
        import field_effects as FIELD_EFFECTS
        for ordinary_pending in (False, True):
            with self.subTest(ordinary_pending=ordinary_pending):
                self.setUp()
                self.adopt()
                effect = self.r.move_mech('move/미스트필드')[0]['effects_exec'][0]
                FIELD_EFFECTS.install(self.e, self.a, effect, 'move/미스트필드')
                if ordinary_pending:
                    self.e.apply_status(self.b, '혼란', source='move/이상한빛', applied_by=self.a)
                self.hit()
                first = list(self.e._move_completions.values())[-1]
                pending = deepcopy(FIELD_EFFECTS._pending(self.b)[0])
                self.assertEqual(first[EM.FIELD][self.b.entity_id]['outcome'], 'deferred')
                self.assertEqual(EXT.save_dc(self.e, self.b, None, 16), 16)
                self.hit()
                self.assertEqual(FIELD_EFFECTS._pending(self.b)[0], pending)
                self.assertNotIn('저주', self.b.conditions)
                EM.withdraw(self.e, self.a, reason='withdraw after actual deferred infliction')
                loaded = Engine.import_state(self.r, json.loads(json.dumps(self.e.export_state())))
                target = W.actor_index(loaded)[self.b.entity_id]
                active=getattr(loaded,'_active_turn_actor',None)
                if active is not None:loaded.end_of_turn(active)
                loaded.start_round(loaded.everyone)
                loaded.start_of_turn(target)
                self.assertIsNone(EM.active(target))
                with patch.object(Engine, 'd20', side_effect=AssertionError('deferred Confusion cannot save early')):
                    loaded.end_of_turn(target)
                self.assertIsNotNone(EM.active(target))
                self.assertEqual(EM.active(target)['origin']['id'], first['id'])
                self.assertEqual(EXT.save_dc(loaded, target, None, 16), 18)
                self.assertNotIn(FIELD_EFFECTS.DEFERRED, target.custom_conditions)
                self.valid(loaded)

    def test_misty_native_cure_and_later_immunity_end_only_the_pending_subtype(self):
        import field_effects as FIELD_EFFECTS
        for outcome in ('cure', 'later_immunity'):
            with self.subTest(outcome=outcome):
                self.setUp()
                self.adopt()
                effect = self.r.move_mech('move/미스트필드')[0]['effects_exec'][0]
                FIELD_EFFECTS.install(self.e, self.a, effect, 'move/미스트필드')
                self.hit()
                event = list(self.e._move_completions.values())[-1][EM.FIELD][self.b.entity_id]
                if outcome == 'cure':
                    self.e.cure_status(self.b, '혼란')
                    self.assertEqual(event['outcome'], 'deferred_cured')
                else:
                    self.e.gm.set_ability(self.b, '마이페이스', reason='native immunity before delayed activation')
                active=getattr(self.e,'_active_turn_actor',None)
                if active is not None:self.e.end_of_turn(active)
                self.e.start_round(self.e.everyone)
                self.e.start_of_turn(self.b)
                self.e.end_of_turn(self.b)
                self.assertIsNone(EM.active(self.b))
                self.assertNotIn('혼란', self.b.conditions)
                self.assertNotIn(FIELD_EFFECTS.DEFERRED, self.b.custom_conditions)
                self.assertEqual(EXT.save_dc(self.e, self.b, None, 16), 16)
                self.valid()

    def test_printed_low_range_uses_actual_modified_save_and_excludes_zero_and_negative(self):
        cases = ((1, 0, -1, False), (2, 0, 0, False), (3, 0, 1, True),
                 (8, 0, 6, True), (9, 0, 7, True), (10, 0, 8, True),
                 (11, 0, 9, False), (17, 0, 15, False), (18, 0, 16, False),
                 (7, 3, 8, True), (8, 3, 9, False), (3, -1, 0, False))
        for face, bonus, effective, drops in cases:
            with self.subTest(face=face, bonus=bonus):
                self.setUp()
                self.adopt()
                self.hit()
                identity = EM.active(self.b)['id']
                self.b.save_mod = bonus
                hp = self.b.hp
                draw, choose = self.end_save(face)
                row = next(row for row, _ in E.records(self.b) if row['id'] == identity)
                event, = row['saves']
                self.assertEqual(event['save_band_version'], 2)
                self.assertEqual((event['check']['natural'], event['check']['dc'], event['effective']),
                                 (face, 18 - bonus, effective))
                self.assertEqual(event['check']['passed'], effective >= 16)
                self.assertEqual(self.b.stages['def'], -1 if drops else 0)
                self.assertEqual(event['stat'], 'def' if drops else None)
                self.assertEqual((draw.call_count, choose.call_count), (1, int(drops)))
                self.assertEqual(self.b.hp, hp)
                self.assertEqual(EM.active(self.b) is None, effective >= 16)
                self.valid()

    def test_printed_band_native_gm_and_json_restore_keep_stage_receipts(self):
        for face in (1, 2, 3, 10, 11):
            with self.subTest(face=face):
                self.setUp()
                self.adopt()
                self.hit()
                self.end_save(face, 'spa')
                event = EM.active(self.b)['saves'][0]
                stages = dict(self.b.stages)
                saved = self.e.export_state()
                checkpoint = self.e.gm.snapshot()
                self.e.cure_status(self.b, '혼란')
                self.e.gm.restore(checkpoint)
                loaded = Engine.import_state(self.r, json.loads(json.dumps(saved)))
                for world in (self.e, loaded):
                    target = W.actor_index(world)[self.b.entity_id]
                    retained, = EM.active(target)['saves']
                    self.assertEqual(target.stages, stages)
                    self.assertEqual((retained['effective'], retained['save_band_version']),
                                     (event['effective'], 2))
                    if retained['stage_receipt'] is not None:
                        producer = world._effect_dispatch_receipts[retained['stage_receipt']]
                        self.assertIs(producer['target'], target)
                        self.assertEqual(producer['effect'],
                                         {'type': 'stage_change', 'stat': 'spa', 'delta': -1})
                    self.valid(world)

    def test_legacy_negative_and_zero_histories_survive_both_restores_and_new_saves(self):
        for face in (1, 2):
            with self.subTest(face=face):
                self.setUp()
                self.adopt()
                # Genuine old adoption shape predates the explicit GM choice.
                self.a.spec[EM.ADOPTION].pop('save_band_basis')
                self.hit()
                # Run the exact old producer at the real native end-turn boundary.
                with patch.object(EM, 'after_confusion_save', legacy_after_confusion_save):
                    self.end_save(face, 'spa')
                original, = EM.active(self.b)['saves']
                self.assertNotIn('save_band_version', original)
                self.assertEqual((original['effective'], self.b.stages['spa']), (face - 2, -1))
                saved = self.e.export_state()
                checkpoint = self.e.gm.snapshot()
                self.e.cure_status(self.b, '혼란')
                self.e.gm.restore(checkpoint)
                loaded = Engine.import_state(self.r, json.loads(json.dumps(saved)))
                for world in (self.e, loaded):
                    target = W.actor_index(world)[self.b.entity_id]
                    first, = EM.active(target)['saves']
                    self.assertNotIn('save_band_version', first)
                    self.assertEqual(target.stages['spa'], -1)
                    self.assertIs(world._effect_dispatch_receipts[first['stage_receipt']]['target'], target)
                    active=getattr(world,'_active_turn_actor',None)
                    if active is not None:world.end_of_turn(active)
                    world.start_round(world.everyone)
                    world.start_of_turn(target)
                    with patch.object(Engine, 'd20', return_value=face), patch.object(
                            type(world.rng), 'choice') as choose:
                        world.end_of_turn(target)
                    choose.assert_not_called()
                    first, second = EM.active(target)['saves']
                    self.assertEqual((second['effective'], second['save_band_version'], second['stat']),
                                     (face - 2, 2, None))
                    self.assertEqual(target.stages['spa'], -1)
                    self.valid(world)
                    world.cure_status(target, '혼란')
                    historical = Engine.import_state(world.r, json.loads(json.dumps(world.export_state())))
                    actual = W.actor_index(historical)[target.entity_id]
                    terminal = next(row for row, phase in E.records(actual)
                                    if EM.owns(row) and phase == 'terminal')
                    old, new = terminal['saves']
                    self.assertNotIn('save_band_version', old)
                    self.assertEqual(new['save_band_version'], 2)
                    self.assertEqual(actual.stages['spa'], -1)
                    self.assertIs(historical._effect_dispatch_receipts[old['stage_receipt']]['target'], actual)
                    self.valid(historical)

    def test_new_band_tampering_is_rejected_by_gm_and_json_restore(self):
        self.adopt()
        self.hit()
        self.end_save(3, 'spa')
        original = self.e.export_state()
        checkpoint = self.e.gm.snapshot()
        actor_refs = self.e.gm.snapshots[checkpoint]['actor_refs']
        clean_snapshot = deepcopy(self.e.gm.snapshots[checkpoint], dict(actor_refs))
        mutations = ({'save_band_version': 1}, {'save_band_version': True},
                     {'save_band_version': 3}, {'effective': 0, 'natural': 2},
                     {'effective': -1, 'natural': 1}, {'stage_receipt': None})
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                snapshot = self.e.gm.snapshots[checkpoint]
                custom = snapshot['combatants'][id(self.b)]['custom_conditions']
                event, = next(row for row in custom[CI.KEY] if EM.owns(row))['saves']
                event.update({key: value for key, value in mutation.items() if key != 'natural'})
                if 'natural' in mutation:
                    event['check']['natural'] = mutation['natural']
                before = self.e.export_state()
                with self.assertRaises(ValueError):
                    self.e.gm.restore(checkpoint)
                self.assertEqual(self.e.export_state(), before)
                self.e.gm.snapshots[checkpoint] = deepcopy(clean_snapshot, dict(actor_refs))
                bad = deepcopy(original)
                events = [node for node in bad['nodes'].values()
                          if node['kind'] == 'dict'
                          and any(pair[0] == 'save_band_version' for pair in node['items'])]
                self.assertEqual(len(events), 1)
                for pair in events[0]['items']:
                    if pair[0] in mutation:
                        pair[1] = mutation[pair[0]]
                if 'natural' in mutation:
                    check = bad['nodes'][dict(events[0]['items'])['check']['$ref']]
                    for pair in check['items']:
                        if pair[0] == 'natural':
                            pair[1] = mutation['natural']
                with self.assertRaises(ValueError):
                    Engine.import_state(self.r, bad)
        self.valid()

    def test_low_save_uses_all_five_native_stage_choices_with_floor_and_immunity(self):
        import combat_stage_sources as STAGES
        for stat, mode in [(stat, 'ordinary') for stat in STAGES.STATS] + [
                ('atk', 'floor'), ('def', 'immune')]:
            with self.subTest(stat=stat, mode=mode):
                self.setUp()
                self.adopt()
                self.hit()
                if mode == 'floor':
                    self.e.change_stage(self.b, stat, -6)
                elif mode == 'immune':
                    self.e.gm.set_ability(self.b, '클리어바디', reason='native stage-loss immunity')
                before = dict(self.b.stages)
                _, choose = self.end_save(10, stat)
                self.assertEqual(choose.call_args_list, [((STAGES.STATS,), {})])
                expected = dict(before)
                if mode == 'ordinary':
                    expected[stat] -= 1
                self.assertEqual(self.b.stages, expected)
                event, = EM.active(self.b)['saves']
                producer = self.e._effect_dispatch_receipts[event['stage_receipt']]
                self.assertEqual(producer['effect'], {'type': 'stage_change', 'stat': stat, 'delta': -1})
                self.assertIs(producer['actor'], self.a)
                self.assertIs(producer['target'], self.b)
                self.assertEqual(producer['status'], 'completed')
                self.valid()

    def test_actual_low_save_history_and_cure_keep_native_receipt_aliases_on_json_restore(self):
        self.adopt()
        self.hit()
        self.end_save(10, 'spa')
        row = EM.active(self.b)
        original = row['saves'][0]['effective']
        row['saves'][0]['effective'] = 0
        self.assertFalse(self.e.validate_state()['valid'])
        row['saves'][0]['effective'] = original
        restored = Engine.import_state(self.r, json.loads(json.dumps(self.e.export_state())))
        target = W.actor_index(restored)[self.b.entity_id]
        self.assertEqual(target.stages['spa'], -1)
        self.assertEqual(len(EM.active(target)['saves']), 1)
        restored.cure_status(target, '혼란')
        self.assertEqual(target.stages['spa'], -1)
        self.valid(restored)
        archived = Engine.import_state(self.r, json.loads(json.dumps(restored.export_state())))
        target = W.actor_index(archived)[self.b.entity_id]
        terminal = next(row for row, phase in E.records(target) if EM.owns(row) and phase == 'terminal')
        event, = terminal['saves']
        self.assertIn(event['stage_receipt'], archived._effect_dispatch_receipts)
        self.assertIsNone(EM.active(target))
        self.valid(archived)

    def test_save_basis_boundaries_use_one_actual_native_save(self):
        cases = ((1, 0, -1), (2, 0, 0), (3, 0, 1), (8, 0, 6),
                 (9, 0, 7), (10, 0, 8), (11, 0, 9), (7, 3, 8),
                 (8, 3, 9), (3, -1, 0))
        for basis in EM.SAVE_BASES:
            for face, bonus, effective in cases:
                with self.subTest(basis=basis, face=face, bonus=bonus):
                    self.setUp()
                    EM.adopt(self.e, self.a, reason='explicit GM Save interpretation', save_band_basis=basis)
                    self.hit()
                    self.b.save_mod = bonus
                    draw, choose = self.end_save(face)
                    row = EM.active(self.b)
                    event, = row['saves']
                    selected = face if basis == 'natural_save' else effective
                    drops = 1 <= selected <= 8
                    self.assertEqual(row['adoption']['save_band_basis'], basis)
                    self.assertEqual((event['check']['natural'], event['effective']), (face, effective))
                    self.assertEqual(event['save_band_version'], 3 if basis == 'natural_save' else 2)
                    self.assertEqual(event.get('save_band_basis'), 'natural_save' if basis == 'natural_save' else None)
                    self.assertEqual((self.b.stages['def'], draw.call_count, choose.call_count),
                                     (-1 if drops else 0, 1, int(drops)))
                    self.valid()

    def test_save_basis_is_captured_by_native_producer_instance_and_both_restore_paths(self):
        for basis in EM.SAVE_BASES:
            with self.subTest(basis=basis):
                self.setUp()
                chosen = EM.adopt(self.e, self.a, reason='GM interpretation recorded', save_band_basis=basis)
                self.hit()
                row = EM.active(self.b)
                producer = self.e._move_completions[row['origin']['id']][EM.FIELD][self.b.entity_id]
                self.assertEqual((producer['adoption'], row['adoption']), (chosen, chosen))
                chosen['save_band_basis'] = 'caller cannot alter captured choice'
                self.end_save(2, 'spa')
                original = self.e.export_state()
                checkpoint = self.e.gm.snapshot()
                self.a.spec[EM.ADOPTION]['save_band_basis'] = ('modified_save' if basis == 'natural_save' else 'natural_save')
                self.assertFalse(self.e.validate_state()['valid'])
                self.a.spec[EM.ADOPTION]['save_band_basis'] = basis
                self.e.cure_status(self.b, '혼란')
                self.e.gm.restore(checkpoint)
                loaded = Engine.import_state(self.r, json.loads(json.dumps(original)))
                for world in (self.e, loaded):
                    target = W.actor_index(world)[self.b.entity_id]
                    self.assertEqual(EM.active(target)['adoption']['save_band_basis'], basis)
                    self.assertEqual(target.stages['spa'], -1 if basis == 'natural_save' else 0)
                    active=getattr(world,'_active_turn_actor',None)
                    if active is not None:world.end_of_turn(active)
                    world.start_round(world.everyone)
                    world.start_of_turn(target)
                    with patch.object(Engine, 'd20', return_value=9), patch.object(type(world.rng), 'choice', return_value='spd'):
                        world.end_of_turn(target)
                    self.assertEqual(target.stages['spd'], 0 if basis == 'natural_save' else -1)
                    world.cure_status(target, '혼란')
                    archived = Engine.import_state(self.r, json.loads(json.dumps(world.export_state())))
                    actual = W.actor_index(archived)[target.entity_id]
                    terminal = next(row for row, phase in E.records(actual) if EM.owns(row) and phase == 'terminal')
                    self.assertEqual(terminal['adoption']['save_band_basis'], basis)
                    self.assertEqual(len(terminal['saves']), 2)
                    self.valid(archived)

    def test_invalid_save_basis_rejects_before_adoption_state_or_rng_change(self):
        before = self.e.export_state()
        for basis in (None, True, 'natural', '', []):
            with self.subTest(basis=basis):
                with self.assertRaisesRegex(ValueError, 'save_band_basis'):
                    EM.adopt(self.e, self.a, reason='invalid GM choice', save_band_basis=basis)
                self.assertEqual(self.e.export_state(), before)
        self.adopt()
        self.assertEqual(self.a.spec[EM.ADOPTION]['save_band_basis'], 'modified_save')
        self.valid()

    def _basis_rider_failure(self, basis):
        self.setUp()
        EM.adopt(self.e, self.a, reason='GM interpretation rollback', save_band_basis=basis)
        self.hit()
        active=getattr(self.e,'_active_turn_actor',None)
        if active is not None:self.e.end_of_turn(active)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.b)
        self.e.rng.seed(1)
        before = self.e.export_state()
        original = FX.run_effects
        def fail_after_stage(engine, actor, target, effects, *args, **kwargs):
            result = original(engine, actor, target, effects, *args, **kwargs)
            if any(effect.get('type') == 'stage_change' for effect in effects):
                raise RuntimeError('late Dementia native stage failure')
            return result
        with patch.object(FX, 'run_effects', side_effect=fail_after_stage):
            with self.assertRaisesRegex(RuntimeError, 'late Dementia native stage failure'):
                self.e.end_of_turn(self.b)
        self.assertEqual(self.e.export_state(), before)
        self.e.end_of_turn(self.b)
        event, = EM.active(self.b)['saves']
        self.assertEqual(event['check']['natural'], 5)
        self.assertEqual(sum(self.b.stages.values()), -1)
        self.valid()

    def test_rider_failure_rolls_back_actual_end_turn_then_retries_the_same_native_randomness(self):
        for basis in EM.SAVE_BASES:
            with self.subTest(basis=basis):
                self._basis_rider_failure(basis)


if __name__ == '__main__':
    unittest.main()
