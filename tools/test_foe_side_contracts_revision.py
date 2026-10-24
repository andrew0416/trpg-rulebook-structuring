"""Four source-specific foe contracts through actual attacks and stage producers."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from native_scenario_fixture import assert_rejected_unchanged, prepare_body
from grid import Grid
import equipment_actions as EQUIPMENT
import frequency as FREQUENCY
import food_effects as FOOD
import items as ITEMS
import state_grants as GRANTS
import type_ace as TA
import world_entities as WORLD
import effects_ext as EXT
import physics_maneuvers as MANEUVERS
import skill_modifiers as SKILLS
import action_points as AP
import passive_events as PASSIVE
import test_book_type_ace_acquisition as ACE
import test_book_type_ace_reactions as REACTIONS
import test_hazard_stage_provenance as HAZARDS
import test_stage_effect_boundary as STAGES
import test_temporary_hp_berry_preflight as COOKED


class FoeSideContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def world(self, *, move='move/몸통박치기', attacker_side='foe', target_side='party', target_kind='pokemon', abilities=()):
        e = Engine(self.rules, seed=0)
        e.grid = Grid(12, 12)
        actors = []
        for name, kind, pos, side, known in (
                ('source', 'pokemon', (2, 2), attacker_side, list(abilities)),
                ('recipient', target_kind, (3, 2), target_side, [])):
            actor = Combatant(self.rules, dict(name=name, kind=kind, level=30, side=side,
                pos=pos, size='중형', weight_kg=30, types=['노말'], abilities=known,
                stats=dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 20),
                moves=[move], movement={'land':6, 'swim':0, 'sky':0, 'power':4},
                skills={'전투':6, '육상':6, '곡예':6}, items={}))
            e.gm.add_combatant(actor, pos=pos, reason='actual source-specific contract participant')
            prepare_body(e, actor, size='중형', offsets=[(0, 0)], reason='observed complete native body')
            actors.append(actor)
        return e, *actors

    def equip(self, e, actor, item, *, held=False):
        identity = 'foe-contract/' + actor.entity_id + '/' + item
        WORLD.register_object(e, identity, kind='item_instance', item_rule_id=item,
            owner_id=actor.entity_id, location={'kind':'unknown'}, reason='actual pre-existing equipment')
        ITEMS.register_item(e, actor, item, source_instance_id=identity, as_held=held)
        return identity

    def start(self, e, actor):
        if e._active_turn_actor is not None:
            e.end_of_turn(e._active_turn_actor)
        e.start_round(e.everyone)
        e.start_of_turn(actor, initiative_count=20)

    def hit(self, e, actor, target, move, *, face=12):
        self.start(e, actor)
        # Only the die face is supplied; targeting, accuracy, damage and events run natively.
        with patch.object(Engine, 'd20', return_value=face):
            return e.use_move_on(actor, target, move, e.everyone, set_damage=True)

    def restore(self, e, *actors):
        loaded = Engine.import_state(e.r, json.loads(json.dumps(e.export_state(), ensure_ascii=False)))
        index = WORLD.actor_index(loaded)
        return loaded, *(index[actor.entity_id] for actor in actors)

    def valid(self, e):
        result = e.validate_state()
        self.assertTrue(result['valid'], result['issues'])

    def test_magician_actual_hit_side_matrix_preserves_item_and_frequency_without_foe(self):
        for source_side, target_side, offered in (
                ('foe', 'party', True), ('party', 'party', False),
                (None, 'party', False), ('foe', None, False), (None, None, False)):
            with self.subTest(source=source_side, target=target_side):
                e, a, t = self.world(attacker_side=source_side, target_side=target_side, abilities=['매지션'])
                physical = self.equip(e, t, 'item/선제공격손톱', held=True)
                initial = deepcopy(t._item_reg)
                hp = t.hp
                self.hit(e, a, t, 'move/몸통박치기')
                self.assertLess(t.hp, hp)
                rows = EQUIPMENT.pending(e)
                self.assertEqual(len(rows), int(offered))
                self.assertEqual(t._item_reg, initial)
                self.assertEqual(e._physical_objects[physical]['equipped_by'], t.entity_id)
                self.assertTrue(FREQUENCY.activation_allowed(a, 'ability/매지션', e.r.ability_freq['매지션'], engine=e))
                if offered:
                    EQUIPMENT.resolve(e, a, rows[0]['id'], accept=False)
                self.valid(e)

    def test_magician_true_hit_pending_restore_transfer_keeps_original_instance_and_source_refusal_atomic(self):
        e, a, t = self.world(abilities=['매지션'])
        physical = self.equip(e, t, 'item/선제공격손톱', held=True)
        self.hit(e, a, t, 'move/몸통박치기')
        e, a, t = self.restore(e, a, t)
        row = EQUIPMENT.pending(e)[0]
        e.gm.snapshot('actual-magician-hit')
        GRANTS.replace_baseline(e, a, 'abilities', [])
        assert_rejected_unchanged(e, lambda:EQUIPMENT.resolve(e, a, row['id'], accept=True),
            reason_pattern='reaction ability no longer available')
        e.gm.restore('actual-magician-hit', reason='restore actual hit and actual Magician grant')
        row = EQUIPMENT.pending(e)[0]
        e.gm.add_combatant(t, side=a.side, reason='later allegiance does not rewrite the actual triggering foe hit')
        EQUIPMENT.resolve(e, a, row['id'], accept=True)
        self.assertEqual(e._physical_objects[physical]['equipped_by'], a.entity_id)
        self.assertIsNone(t.item)
        self.assertFalse(FREQUENCY.activation_allowed(a, 'ability/매지션', e.r.ability_freq['매지션'], engine=e))
        self.valid(e)

    def test_magician_gm_side_change_before_hit_is_observed_without_rewriting_ability(self):
        e, a, t = self.world(attacker_side='party', abilities=['매지션'])
        self.equip(e, t, 'item/선제공격손톱', held=True)
        before = deepcopy(a.spec.get('state_grants', {}))
        e.gm.add_combatant(t, side='foe', reason='GM explicitly changes allegiance before the attack')
        e, a, t = self.restore(e, a, t)
        self.hit(e, a, t, 'move/몸통박치기')
        self.assertEqual(len(EQUIPMENT.pending(e)), 1)
        self.assertEqual(a.spec.get('state_grants', {}), before)
        EQUIPMENT.resolve(e, a, EQUIPMENT.pending(e)[0]['id'], accept=False)

    def berry(self, e, target, item='item/카리열매'):
        target.spec['items'][item] = 1
        result = e.use_item(target, item, target, duration_minutes=1,
            duration_reason='actual preparation and intake of selected resistance berry')
        e.consume_food_buff(target, buff_id=result['buff_id'])
        return result['buff_id']

    def test_resistance_berry_live_hit_side_matrix_consumes_only_for_actual_foe(self):
        damage = {}
        for source_side, target_side, consumed in (
                ('foe', 'party', True), ('party', 'party', False),
                (None, 'party', False), ('foe', None, False), (None, None, False)):
            with self.subTest(source=source_side, target=target_side):
                e, a, t = self.world(attacker_side=source_side, target_side=target_side)
                buff = self.berry(e, t)
                history = deepcopy(FOOD.get_buff(t, buff))
                hp = t.hp
                self.hit(e, a, t, 'move/몸통박치기')
                self.assertLess(t.hp, hp)
                damage[source_side, target_side] = hp - t.hp
                self.assertEqual(any(row.get('id') == buff for row in t.buffs), not consumed)
                if not consumed:
                    self.assertEqual(FOOD.get_buff(t, buff), history)
                    self.assertEqual(t.spec['food_hit_choice']['buff_id'], buff)
                self.valid(e)
        self.assertLess(damage['foe', 'party'], damage['party', 'party'])
        self.assertEqual(damage['party', 'party'], damage[None, 'party'])
        self.assertEqual(damage['party', 'party'], damage['foe', None])

    def test_super_effective_berry_native_wrong_type_neutral_and_foe_hit_boundaries(self):
        for move, target_type, consumed in (
                ('move/몸통박치기', '풀', False),
                ('move/불꽃세례', '노말', False),
                ('move/불꽃세례', '풀', True)):
            with self.subTest(move=move, target_type=target_type):
                e, a, t = self.world(move=move)
                e.gm.set_types(t, [target_type], reason='actual target matchup for selected Fire resistance berry')
                buff = self.berry(e, t, 'item/오카열매')
                self.hit(e, a, t, move)
                self.assertEqual(any(row.get('id') == buff for row in t.buffs), not consumed)
                self.valid(e)

    def test_resistance_berry_retains_real_grant_on_miss_then_restored_current_foe_hit_consumes_once(self):
        e, a, t = self.world(attacker_side='party')
        buff = self.berry(e, t)
        original = deepcopy(FOOD.get_buff(t, buff))
        self.hit(e, a, t, 'move/몸통박치기', face=1)
        self.assertEqual(FOOD.get_buff(t, buff), original)
        e.gm.add_combatant(a, side='foe', reason='GM explicitly changes attacker allegiance')
        e, a, t = self.restore(e, a, t)
        self.hit(e, a, t, 'move/몸통박치기')
        self.assertFalse(t.buffs)
        self.assertNotIn('food_hit_choice', t.spec)
        self.valid(e)

    def test_clear_amulet_actual_tickle_side_matrix_preserves_unrelated_equipment_source(self):
        for source_side, target_side, stages in (
                ('foe', 'party', (0, 0)), ('party', 'party', (-1, -1)),
                (None, 'party', (-1, -1)), ('foe', None, (-1, -1)), (None, None, (-1, -1))):
            with self.subTest(source=source_side, target=target_side):
                e, a, t = self.world(move='move/간지르기', attacker_side=source_side,
                    target_side=target_side, target_kind='trainer')
                physical = self.equip(e, t, 'item/클리어참')
                sources = deepcopy(t.spec['state_grants'])
                self.hit(e, a, t, 'move/간지르기')
                self.assertEqual((t.stages['atk'], t.stages['def']), stages)
                self.assertEqual(t.spec['state_grants'], sources)
                self.assertEqual(e._physical_objects[physical]['equipped_by'], t.entity_id)
                self.valid(e)

    def test_clear_amulet_actual_self_lowering_and_positive_stages_remain_after_restore(self):
        e, a, t = self.world(move='move/인파이트', target_kind='trainer')
        self.equip(e, t, 'item/클리어참')
        e, a, t = self.restore(e, a, t)
        self.hit(e, t, a, 'move/인파이트')
        self.assertEqual((t.stages['def'], t.stages['spd']), (-1, -1))
        e.gm.set_move(t, 'move/칼춤', reason='independent real self stage raise')
        self.hit(e, t, t, 'move/칼춤')
        self.assertEqual(t.stages['atk'], 2)
        self.valid(e)

    def test_clear_amulet_gm_side_change_then_removal_restores_actual_foe_stage_loss(self):
        e, a, t = self.world(move='move/간지르기', attacker_side='party', target_kind='trainer')
        self.equip(e, t, 'item/클리어참')
        e.gm.add_combatant(a, side='foe', reason='explicit current source-side change')
        e, a, t = self.restore(e, a, t)
        self.hit(e, a, t, 'move/간지르기')
        self.assertEqual((t.stages['atk'], t.stages['def']), (0, 0))
        ITEMS.unregister_item(e, t, 'item/클리어참')
        self.hit(e, a, t, 'move/간지르기')
        self.assertEqual((t.stages['atk'], t.stages['def']), (-1, -1))
        self.valid(e)

    def test_actual_hit_and_stage_producers_accept_absent_side_without_inventing_foe(self):
        for role in ('source', 'target'):
            for contract in ('magician', 'berry', 'amulet'):
                with self.subTest(role=role, contract=contract):
                    move = 'move/간지르기' if contract == 'amulet' else 'move/몸통박치기'
                    e, a, t = self.world(move=move, target_kind='trainer' if contract == 'amulet' else 'pokemon',
                        abilities=['매지션'] if contract == 'magician' else [])
                    if contract == 'magician':
                        self.equip(e, t, 'item/선제공격손톱', held=True)
                    elif contract == 'berry':
                        buff = self.berry(e, t)
                    else:
                        self.equip(e, t, 'item/클리어참')
                    unknown = a if role == 'source' else t
                    del unknown.side
                    unknown.spec.pop('side', None)
                    self.hit(e, a, t, move)
                    self.assertFalse(hasattr(unknown, 'side'))
                    if contract == 'magician':
                        self.assertFalse(EQUIPMENT.pending(e))
                    elif contract == 'berry':
                        self.assertEqual(t.spec['food_hit_choice']['buff_id'], buff)
                    else:
                        self.assertEqual((t.stages['atk'], t.stages['def']), (-1, -1))


class ClearAmuletCapturedHazardSideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        HAZARDS.HazardStageProvenanceTests.setUpClass()
        STAGES.StageEffectBoundaryTests.setUpClass()

    def test_actual_web_uses_saved_hazard_side_after_setter_changes_side_recall_and_restore(self):
        case = HAZARDS.HazardStageProvenanceTests()
        e, setter, _ = case.hazard_case().install(HAZARDS.WEB)
        target = case.trainer(e, side='wild', name='changed-setter-clear')
        cell = HAZARDS.CELLS[0]
        source = deepcopy(e.hazards[cell]['instances'][0])
        e.gm.add_combatant(setter, side='wild', reason='setter changes current allegiance after actual web placement')
        e.gm.recall(setter, reason='actual setter goes off field while the placed web remains')
        e, setter, target = case.restore(e, setter, target)
        self.assertFalse(setter.on_field)
        self.assertEqual(setter.side, target.side)
        self.assertEqual(e.hazards[cell]['instances'][0], source)
        EXT.on_enter_cell(e, target, cell)
        self.assertEqual(target.stages['spe'], 0)
        self.assertIn('둔화', target.conditions)
        self.assertTrue(e.validate_state()['valid'])

    def test_actual_deep_cold_feature_owner_is_distinct_from_attacking_pokemon(self):
        case = STAGES.StageEffectBoundaryTests()
        for owner_is_foe in (True, False):
            with self.subTest(owner_is_foe=owner_is_foe):
                world = case.world('amulet')
                helper, e, owner, attacker, target, _ = world
                e.gm.add_combatant(owner, side='party' if owner_is_foe else target.side,
                    reason='explicit feature-owner side independent of its attacking Pokemon')
                self.assertNotEqual(attacker.side, target.side)
                source, stats = case.produce('deep_cold', world)
                self.assertEqual({stat:target.stages[stat] for stat in stats},
                    dict.fromkeys(stats, 0 if owner_is_foe else -1))
                self.assertIn('얼음', target.conditions)


class CloseQuartersFoeContractTests(unittest.TestCase):
    setUpClass = classmethod(ACE.TypeAceAcquisitionTests.setUpClass.__func__)
    setUp = ACE.TypeAceAcquisitionTests.setUp
    setup = ACE.TypeAceAcquisitionTests.setup
    add = ACE.TypeAceAcquisitionTests.add
    acquire = ACE.TypeAceAcquisitionTests.acquire
    combat = ACE.TypeAceAcquisitionTests.combat
    next_turn = ACE.TypeAceAcquisitionTests.next_turn
    communication = ACE.TypeAceAcquisitionTests.communication
    restore = ACE.TypeAceAcquisitionTests.restore
    valid = ACE.TypeAceAcquisitionTests.valid
    family = REACTIONS.TypeAceReactionTests.family
    known = REACTIONS.TypeAceReactionTests.known
    sustain = REACTIONS.TypeAceReactionTests.sustain
    native = REACTIONS.TypeAceReactionTests.native
    completed = REACTIONS.TypeAceReactionTests.completed
    walk = REACTIONS.TypeAceReactionTests.walk

    def pending_fighting_hit(self, *, ally=False):
        self.family('격투', 'Close Quarters Mastery')
        from examples.declared_skill_ranks import configure
        self.enterContext(patch.object(self.e.r, 'rulings', deepcopy(self.e.r.rulings)))
        configure(self.e.r)
        self.e.gm.set_skill(self.t, '전투', 7, reason='observed seventh rank keeps actual acquired Type Ace history')
        target = self.q if ally else self.b
        if not ally:
            self.e.gm.set_position(self.p, (3, 2), reason='real adjacent foe Fighting hit')
        holder = target if ally else self.p
        GRANTS.replace_baseline(self.e, holder, 'abilities', ['나쁜손버릇' if ally else '매지션'])
        physical = FoeSideContractTests.equip(self, self.e, self.p if ally else target,
            'item/선제공격손톱', held=True)
        self.sustain('Close Quarters Mastery')
        before = target.hp
        self.native(self.p, target, 'move/태권당수')
        self.assertLess(target.hp, before)
        choices = EQUIPMENT.pending(self.e)
        self.assertEqual(len(choices), 1)
        self.assertEqual(choices[0]['source'], 'ability/나쁜손버릇' if ally else 'ability/매지션')
        completion = next(row for row in reversed(list(self.e._move_completions.values()))
            if row['actor'] is self.p and row['move_id'] == 'move/태권당수')
        self.assertNotEqual(completion['phase'], 'complete')
        event = next(event for event in self.e._passive_events.values()
            if event.get('completion_id') == completion['id'] and event['target'] is target
            and 'close_quarters_hit' in event)
        self.assertEqual(event['close_quarters_hit']['actor_id'], self.p.entity_id)
        self.assertEqual(event['close_quarters_hit']['target_id'], target.entity_id)
        self.assertIsNone(TA.marked(self.e, target))
        return target, physical, completion['id'], event['id']

    def test_pending_magician_foe_hit_marks_after_side_change_gm_and_cold_restore_without_repayment(self):
        target, physical, completion_id, event_id = self.pending_fighting_hit()
        facts = deepcopy(self.e._passive_events[event_id]['close_quarters_hit'])
        payments = deepcopy((self.p.move_uses, self.p.budget, dict(self.t.ap_account.identified_bindings()), AP.available(self.t)))
        acquisition = deepcopy(TA.acquired(self.t, TA.uid('Close Quarters Mastery')))
        hit_hp = target.hp
        self.e.gm.add_combatant(target, side=self.p.side,
            reason='GM observes later allegiance after the real foe hit and before the held-item decision')
        self.e.gm.snapshot('pending-close-quarters')
        row = EQUIPMENT.pending(self.e)[0]
        EQUIPMENT.resolve(self.e, self.p, row['id'], accept=False)
        self.assertIs(TA.marked(self.e, target), self.p)
        self.assertEqual(target.hp, hit_hp)
        self.assertEqual(self.e._move_completions[completion_id]['phase'], 'complete')
        self.e.gm.restore('pending-close-quarters', reason='restore actual pending hit without replaying the attack')
        self.assertIsNone(TA.marked(self.e, self.b))
        self.restore()
        self.assertEqual(self.e._passive_events[event_id]['close_quarters_hit'], facts)
        row = EQUIPMENT.pending(self.e)[0]
        EQUIPMENT.resolve(self.e, self.p, row['id'], accept=True)
        self.assertIs(TA.marked(self.e, self.b), self.p)
        self.assertEqual(self.e._physical_objects[physical]['equipped_by'], self.p.entity_id)
        self.assertEqual(self.b.hp, hit_hp)
        self.assertEqual((self.p.move_uses, self.p.budget, dict(self.t.ap_account.identified_bindings()), AP.available(self.t)), payments)
        self.assertEqual(TA.acquired(self.t, TA.uid('Close Quarters Mastery')), acquisition)
        self.valid()

    def test_pending_pickpocket_ally_hit_never_becomes_foe_hit_after_side_change_and_restore(self):
        target, physical, completion_id, event_id = self.pending_fighting_hit(ally=True)
        facts = deepcopy(self.e._passive_events[event_id]['close_quarters_hit'])
        self.assertEqual(facts['actor_side'], facts['target_side'])
        self.e.gm.add_combatant(target, side='foe', reason='later hostility cannot rewrite the actual ally hit')
        self.restore()
        row = EQUIPMENT.pending(self.e)[0]
        EQUIPMENT.resolve(self.e, self.q, row['id'], accept=False)
        self.assertEqual(self.e._move_completions[completion_id]['phase'], 'complete')
        self.assertIsNone(TA.marked(self.e, self.q))
        self.assertEqual(self.e._passive_events[event_id]['close_quarters_hit'], facts)
        self.assertEqual(self.e._physical_objects[physical]['equipped_by'], self.p.entity_id)
        self.valid()

    def test_pending_close_quarters_side_recipient_and_acquisition_tampering_rejects_restore(self):
        target, _, _, event_id = self.pending_fighting_hit()
        clean = json.loads(json.dumps(self.e.export_state(), ensure_ascii=False))
        for field, replacement in (('actor_side', target.side), ('target_id', self.q.entity_id),
                ('acquisition', 'invented-acquisition')):
            with self.subTest(field=field):
                event = self.e._passive_events[event_id]
                original = event['close_quarters_hit'][field]
                event['close_quarters_hit'][field] = replacement
                self.assertFalse(self.e.validate_state()['valid'])
                with self.assertRaises(ValueError):
                    Engine.import_state(self.rules, json.loads(json.dumps(self.e.export_state(), ensure_ascii=False)))
                event['close_quarters_hit'][field] = original
        loaded = Engine.import_state(self.rules, clean)
        self.assertEqual(loaded._passive_events[event_id]['close_quarters_hit'],
            self.e._passive_events[event_id]['close_quarters_hit'])

    def test_real_intercept_marks_only_actual_fighting_hit_recipient_and_not_immune_recipient(self):
        for immune in (False, True):
            with self.subTest(immune=immune):
                self.family('격투', 'Close Quarters Mastery')
                self.e.gm.set_position(self.b, (3, 2), reason='actual original melee target')
                self.u = self.add('actual interceptor', 'trainer', (3, 5), side='foe',
                    types=['고스트'] if immune else ['노말'], skills={'육상':3, '곡예':3, '전투':3},
                    movement={'land':8, 'swim':0, 'sky':0, 'power':4})
                self.e.watch_move_defense(self.b, [{'actor_id':self.u.entity_id,
                    'source':'maneuver/근접-가로채기'}], reason='actual declared native Intercept')
                self.sustain('Close Quarters Mastery')
                hp = self.b.hp
                with self.assertRaises(PASSIVE.PassiveEventPending):
                    self.native(self.p, self.b, 'move/태권당수')
                event_id = self.e._passive_pending
                self.e.choose_move_defense(event_id, self.u, use=True,
                    options={'path':[(3,5),(3,4),(3,3),(3,2)], 'skill':'육상', 'mode':'land',
                        'shove_destination':[4,2], 'roll_options':{'fixed':[6,6,6]}},
                    reason='real successful Intercept route')
                self.assertEqual(self.b.hp, hp)
                self.assertIsNone(TA.marked(self.e, self.b))
                self.assertIs(TA.marked(self.e, self.u), None if immune else self.p)
                row = self.completed()
                child = row['received'][self.u.entity_id]['child_event']
                if not immune:
                    self.assertEqual(self.e._passive_events[child]['close_quarters_hit']['target_id'], self.u.entity_id)
                self.restore()
                self.assertIs(TA.marked(self.e, self.u), None if immune else self.p)
                self.valid()

    def test_actual_fighting_move_ally_hit_has_no_mark_penalty_or_departure_attack(self):
        self.family('격투', 'Close Quarters Mastery', 'Face Me Whelp')
        self.sustain('Close Quarters Mastery')
        self.native(self.p, self.q, 'move/태권당수')
        self.assertIn(self.q, TA._completed_targets(self.completed()))
        self.assertIsNone(TA.marked(self.e, self.q))
        move = self.rules.move('move/몸통박치기')
        self.assertEqual((TA.accuracy(self.e, self.q, self.b, move, {}),
            TA.damage_bonus(self.e, self.q, self.b, move, 1)), (0, 0))
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.q, initiative_count=20)
        hp = self.q.hp
        completions = len(self.e._move_completions)
        self.walk(self.q, [(2, 4), (2, 5)])
        self.assertEqual((self.q.hp, len(self.e._move_completions)), (hp, completions))
        self.valid()

    def test_actual_foe_mark_restores_marker_identity_and_preserves_seven_rank_acquisition(self):
        self.family('격투', 'Close Quarters Mastery')
        from examples.declared_skill_ranks import configure
        self.enterContext(patch.object(self.e.r, 'rulings', deepcopy(self.e.r.rulings)))
        configure(self.e.r)
        self.e.gm.set_skill(self.t, '전투', 7, reason='actual rank above Master remains valid')
        self.e.gm.set_position(self.p, (3, 2), reason='actual adjacent Fighting attack')
        self.sustain('Close Quarters Mastery')
        source = deepcopy(TA.acquired(self.t, TA.uid('Close Quarters Mastery')))
        self.native(self.p, self.b, 'move/태권당수')
        self.assertIs(TA.marked(self.e, self.b), self.p)
        self.restore()
        self.assertIs(TA.marked(self.e, self.b), self.p)
        self.assertEqual(TA.acquired(self.t, TA.uid('Close Quarters Mastery')), source)
        self.valid()

    def test_explicit_side_change_before_fighting_hit_is_current_and_unknown_target_never_marked(self):
        for side in ('foe', None):
            with self.subTest(side=side):
                self.family('격투', 'Close Quarters Mastery')
                self.sustain('Close Quarters Mastery')
                if side is None:
                    self.q.side = None
                    self.q.spec['side'] = None
                else:
                    self.e.gm.add_combatant(self.q, side=side, reason='explicit current allegiance change')
                self.native(self.p, self.q, 'move/태권당수')
                self.assertIn(self.q, TA._completed_targets(self.completed()))
                self.assertIs(TA.marked(self.e, self.q), self.p if side == 'foe' else None)

    def test_actual_trip_hit_marks_foe_only_and_self_attempt_is_atomic(self):
        for side in ('party', 'foe', None):
            with self.subTest(side=side):
                self.family('격투', 'Close Quarters Mastery')
                self.sustain('Close Quarters Mastery')
                self.q.side = side
                self.q.spec['side'] = side
                options = dict(challenger_skill='전투', defender_skill='곡예', fixed_accuracy=20,
                    challenger_options={'fixed':[6] * SKILLS.rank(self.e.r, self.p, '전투')[2]},
                    defender_options={'fixed':[1] * SKILLS.rank(self.e.r, self.q, '곡예')[2]})
                assert_rejected_unchanged(self.e,
                    lambda:MANEUVERS.trip(self.e, self.p, self.p, **options),
                    reason_pattern='two distinct')
                MANEUVERS.trip(self.e, self.p, self.q, **options)
                self.assertIn('넘어짐', self.q.conditions)
                self.assertIs(TA.marked(self.e, self.q), self.p if side == 'foe' else None)


class ResistanceBerryPreparationFoeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        COOKED.TemporaryHPBerryPreflightTests.setUpClass()

    def test_real_salty_berry_on_ally_hit_does_not_require_foe_consumption_policy(self):
        case = COOKED.TemporaryHPBerryPreflightTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        e, chef, actor, attacker, berry, original = case.ready_berry()
        e.gm.add_combatant(attacker, side=actor.side, reason='actual ally hit keeps armed cooked berry')
        source = deepcopy(FOOD.get_buff(actor, berry))
        before = actor.hp
        FoeSideContractTests.start(self, e, attacker)
        with patch.object(Engine, 'd20', return_value=12):
            e.use_move_on(attacker, actor, 'move/몸통박치기', e.everyone, set_damage=True)
        self.assertLess(actor.hp + actor.temp_hp, before + 10)
        self.assertEqual(FOOD.get_buff(actor, berry), source)
        self.assertEqual(actor.spec['food_hit_choice']['buff_id'], berry)


if __name__ == '__main__':
    unittest.main()
