"""Exact R0670 consumer over native recipient accuracy and damage producers."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon
from grid import Grid
import combat_timing as TIME
import homebrew_state as HOME
import passive_events as PASSIVE
import state_grants as G
import tera_shell as TS


class TeraShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')

    def setUp(self):
        self.e = Engine(self.r, 530)
        self.e.grid = Grid(20, 20)
        self.a = self.actor('attacker', [], (2, 2), 'opponent', ['노말'])
        self.t = self.actor('shell owner', ['테라셸'], (3, 2), 'party', ['풀', '독'])
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a, initiative_count=20)

    def actor(self, name, abilities, pos, side, types):
        moves = ['move/물대포', 'move/몸통박치기', 'move/덩굴채찍',
                 'move/물기', 'move/태권당수', 'move/위액']
        actor = Combatant(self.r, build_pokemon(self.r, '이상해씨', 30,
            name=name, moves=moves, extra={'abilities': abilities, 'pos': pos,
                'side': side, 'types': types, 'size': '중형'}))
        self.e.gm.add_combatant(actor)
        return actor

    def watch(self, owner=None):
        return self.e.watch_ability_interrupt(owner or self.t, TS.SOURCE,
            reason='owner requests an actual native hit choice')

    def waiting(self, move='move/물대포'):
        self.watch()
        hp = self.t.hp
        with self.assertRaises(PASSIVE.PassiveEventPending):
            self.e.use_move(self.a, self.t, move, set_damage=True)
        self.assertEqual(self.t.hp, hp)
        self.assertEqual(self.a.move_uses[move], 1)
        return self.e._passive_pending

    def choose(self, event, chosen='물', *, use=True):
        return self.e.choose_ability_interrupt(event, self.t, use=use,
            options={'chosen_type': chosen} if use else None,
            reason='actual recipient selects its resisting type')

    def fresh(self):
        saved = json.loads(json.dumps(self.e.export_state(), ensure_ascii=False))
        ids = self.a.entity_id, self.t.entity_id
        self.e = Engine.import_state(Rules(ROOT, ruleset='core'), saved)
        index = {a.entity_id: a for a in self.e.everyone}
        self.a, self.t = (index[i] for i in ids)
        return saved

    def activate(self, chosen='물', move='move/물대포'):
        event = self.waiting(move)
        self.choose(event, chosen)
        self.assertIsNone(self.e._passive_pending)
        return event

    def calc(self, move_id, *, target=None):
        self.e.enable_execution_trace()
        result = self.e.roll_damage(self.t, target or self.a,
            self.e.r.move(move_id), set_damage=True)
        rows = [c for r in self.e.execution_traces() for c in r['calculations']
                if c.get('source') == move_id and 'damage_base' in c]
        self.assertTrue(rows)
        return result, rows[-1]

    def test_actual_hit_changes_before_incoming_damage_and_pays_one_free_scene_use(self):
        # The incoming Water hit would be super effective against Fire. Its
        # actual damage must instead see the newly chosen resisting Water type.
        self.t.spec['types'] = ['불꽃']; self.t._types = ['불꽃']
        self.e.enable_execution_trace()
        event = self.waiting()
        self.assertEqual(self.t.types, ['불꽃'])
        hp = self.t.hp
        self.choose(event)
        self.assertEqual(self.t.types, ['물'])
        self.assertLess(self.t.hp, hp)
        self.assertEqual(self.t._action_history, ['free'])
        self.assertEqual(self.a._action_history, ['standard'])
        attempt = self.e._passive_events[event]['ability_interrupts']['attempts'][0]
        self.assertTrue(attempt['paid'])
        self.assertEqual(attempt['plan']['move']['type'], '물')
        self.assertEqual(HOME.stab_types(self.t), ['불꽃'])
        incoming = [c for r in self.e.execution_traces() for c in r['calculations']
                    if c.get('source') == 'move/물대포' and 'type_multiplier' in c]
        self.assertEqual(len(incoming), 1)
        self.assertEqual(incoming[0]['type_multiplier'], .5)
        self.t.abilities_suppressed = True
        self.assertEqual(self.t.types, ['물'])
        self.assertEqual(HOME.stab_types(self.t), ['불꽃'])
        self.assertEqual(HOME.damage_bonus(self.t, self.r.move('move/물대포'), engine=self.e), 10)
        self.t.abilities_suppressed = False
        with self.assertRaisesRegex(ValueError, 'frequency'):
            self.watch()

    def test_explicit_decline_does_not_change_types_or_pay_and_can_watch_again(self):
        event = self.waiting()
        self.choose(event, use=False)
        self.assertEqual(self.t.types, ['풀', '독'])
        self.assertEqual(getattr(self.t, '_action_history', []), [])
        self.assertNotIn(TS.KEY, self.t.spec)
        self.watch()

    def test_nonresisting_immunity_unknown_and_extra_options_reject_atomically(self):
        event = self.waiting()
        before = self.e.export_state()
        for chosen in ('불꽃', 'TYPO', '땅'):
            with self.subTest(chosen=chosen):
                with self.assertRaises(ValueError):
                    self.choose(event, chosen)
                self.assertEqual(self.e.export_state(), before)
        with self.assertRaises(ValueError):
            self.e.choose_ability_interrupt(event, self.t, use=True,
                options={'chosen_type': '물', 'hit': True}, reason='forged input')
        self.assertEqual(self.e.export_state(), before)
        self.choose(event)

    def test_direct_damage_and_fabricated_hit_do_not_authorize_activation(self):
        self.watch()
        before = deepcopy((self.t.spec, self.t.hp, self.e.rng.getstate()))
        with self.assertRaises(ValueError):
            TS.prepare(self.e, self.t, 'fake-event', '물')
        self.assertEqual((self.t.spec, self.t.hp, self.e.rng.getstate()), before)
        self.e.resolve_attack_damage(self.a, self.t, self.r.move('move/물대포'), set_damage=True)
        self.assertEqual(self.t.types, ['풀', '독'])
        self.assertNotIn(TS.KEY, self.t.spec)

    def test_miss_does_not_open_choice_or_consume_scene_frequency(self):
        self.watch()
        self.e.rng.seed(31)
        self.e.use_move(self.a, self.t, 'move/물대포', set_damage=True)
        self.assertIsNone(self.e._passive_pending)
        self.assertEqual(self.t.types, ['풀', '독'])
        self.assertNotIn(TS.KEY, self.t.spec)
        self.assertEqual(getattr(self.t, '_action_history', []), [])

    def test_pending_and_active_cold_restore_do_not_repeat_move_or_payment(self):
        event = self.waiting()
        self.fresh()
        self.choose(event)
        self.assertEqual(self.a.move_uses['move/물대포'], 1)
        self.assertEqual(self.t._action_history, ['free'])
        self.fresh()
        self.assertEqual(self.t.types, ['물'])
        self.assertEqual(HOME.stab_types(self.t), ['풀', '독'])
        self.e.end_encounter(self.e.everyone)
        self.assertEqual(self.t.types, ['풀', '독'])
        self.assertEqual(TIME.records(self.t), [])
        self.fresh()

    def test_retains_original_stab_and_new_type_gets_roll_bonus_before_scaling(self):
        ordinary_water, before_water = self.calc('move/물대포')
        ordinary_grass, before_grass = self.calc('move/덩굴채찍')
        self.activate()
        transformed_water, after_water = self.calc('move/물대포')
        transformed_grass, after_grass = self.calc('move/덩굴채찍')
        self.assertEqual(after_water['damage_base'], before_water['damage_base'])
        self.assertEqual(after_water['roll_modifier'], before_water['roll_modifier'] + 10)
        self.assertEqual(transformed_water, ordinary_water + 10)
        self.assertEqual(transformed_grass, ordinary_grass)
        self.assertEqual(after_grass['damage_base'], before_grass['damage_base'])
        self.a.spec['types'] = ['풀']; self.a._types = ['풀']
        _, resisted = self.calc('move/물대포')
        self.assertEqual(resisted['type_multiplier'], .5)
        self.assertEqual(resisted['adjustment'], 0)
        self.assertEqual(resisted['result'], int(resisted['after_defense'] * .5))

    def test_already_original_stab_type_gets_no_plus_ten(self):
        _, before = self.calc('move/덩굴채찍')
        self.activate(chosen='풀')
        _, after = self.calc('move/덩굴채찍')
        self.assertEqual(after['roll_modifier'], before['roll_modifier'])
        self.assertEqual(after['damage_base'], before['damage_base'])
        self.assertEqual(HOME.damage_bonus(self.t, self.r.move('move/덩굴채찍'), engine=self.e), 0)

    def test_transformation_survives_ability_withdrawal_then_ends_independently(self):
        self.activate()
        G.replace_baseline(self.e, self.t, 'abilities', [])
        self.assertEqual(self.t.types, ['물'])
        self.assertEqual(HOME.stab_types(self.t), ['풀', '독'])
        self.assertEqual(HOME.damage_bonus(self.t, self.r.move('move/물대포'), engine=self.e), 10)
        self.fresh()
        self.e.end_encounter(self.e.everyone)
        self.assertEqual(self.t.types, ['풀', '독'])
        self.assertEqual(self.t.abilities, [])

    def test_cleanup_reveals_independent_type_source_instead_of_restoring_stale_types(self):
        self.activate()
        G._source(self.t, 'independent-type', 'effect')
        G.type_operation(self.t, 'add', ['불꽃'], 'independent-type')
        self.assertEqual(set(self.t.types), {'물', '불꽃'})
        self.e.end_encounter(self.e.everyone)
        self.assertEqual(set(self.t.types), {'풀', '독', '불꽃'})
        self.assertIn('independent-type', self.t.spec[G.KEY]['sources'])

    def test_rejects_deleted_receipt_or_forged_lifetime_on_restore(self):
        self.activate()
        self.fresh()
        receipt = deepcopy(self.t.spec[TS.KEY])
        self.t.spec[TS.KEY] = {}
        with self.assertRaises(ValueError):
            TS.validate_world(self.e)
        self.t.spec[TS.KEY] = receipt
        TIME.records(self.t)[0]['ends'] = ['faint']
        with self.assertRaises(ValueError):
            self.e.export_state()

    def test_suppressed_or_unowned_source_cannot_watch(self):
        self.t.abilities_suppressed = True
        with self.assertRaises(ValueError):
            self.watch()

        self.t.abilities_suppressed = False
        G.replace_baseline(self.e, self.t, 'abilities', [])
        with self.assertRaises(ValueError):
            self.watch()

    def test_choice_uses_actual_individual_move_type_instead_of_catalog_type(self):
        import move_type_sync as SYNC
        SYNC.observe(self.e, self.a, application_id='shell-electric-water',
            move_id='move/물대포', chosen_type='전기', new_name='전기대포',
            effect_decision={'mode': 'preserve', 'reason': 'keep source effects', 'effects_exec': None},
            feasibility_review='GM accepts completed individual type adaptation',
            power_review='unchanged base damage', reason='actual completed adaptation')
        event = self.waiting()
        # Water resists the catalog move, but not its actual electric type.
        with self.assertRaises(ValueError):
            self.choose(event, '물')
        self.choose(event, '풀')
        self.assertEqual(self.t.types, ['풀'])
        self.assertEqual(self.e._passive_events[event]['ability_interrupts']['attempts'][0]
                         ['plan']['move']['type'], '전기')
        self.assertEqual(self.r.move('move/물대포')['type'], '물')

    def test_immunity_is_not_the_source_resisting_type_choice(self):
        event = self.waiting('move/몸통박치기')
        before = self.e.export_state()
        with self.assertRaises(ValueError):
            self.choose(event, '고스트')
        self.assertEqual(self.e.export_state(), before)
        self.choose(event, '바위')
        self.assertEqual(self.t.types, ['바위'])

    def test_recall_and_faint_do_not_end_the_explicit_combat_lifetime(self):
        self.activate()
        self.e.gm.recall(self.t, reason='actual recall during the encounter')
        self.assertEqual(self.t.types, ['물'])
        self.t.hp = 0
        self.e.check_fainted(self.t)
        self.assertEqual(self.t.types, ['물'])
        self.assertEqual(HOME.stab_types(self.t), ['풀', '독'])
        self.e.end_encounter(self.e.everyone)
        self.assertEqual(self.t.types, ['풀', '독'])

    def test_other_actual_source_stab_is_preserved_without_new_only_bonus(self):
        # Reuse the independently reviewed source-repair fixture's existing
        # Mighty form observation; its acquisition/activation is not credited.
        self.r = Rules(ROOT, ruleset='all')
        self.setUp()
        G.replace_baseline(self.e, self.t, 'abilities', ['테라셸', '마이티체인지[홈브류]'])
        self.t.form = '마이티폼'
        _, before = self.calc('move/태권당수')
        self.activate(chosen='격투', move='move/물기')
        _, after = self.calc('move/태권당수')
        self.assertEqual(after['damage_base'], before['damage_base'])
        self.assertEqual(after['roll_modifier'], before['roll_modifier'])
        self.assertEqual(HOME.damage_bonus(self.t, self.r.move('move/태권당수'), engine=self.e), 0)



if __name__ == '__main__':
    unittest.main()
