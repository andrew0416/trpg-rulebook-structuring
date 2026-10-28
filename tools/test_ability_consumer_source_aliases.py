"""Actual source identities at the remaining ability consumer boundaries."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon, build_trainer
from ruleset import RuleFilter, UnresolvedRuleSelection
import equipment_protection as PROTECTION
import equipment_actions as EQUIPMENT
import movement_actions as MOVEMENT
import telekinetic as TK
import aura_guardian as AURA
import passive_event_profiles as PASSIVE
import stall_ability as STALL
import tumbler as TUMBLER
import initiative as INIT
import initiative_interrupts as INTERRUPTS
import state_codec as CODEC
import world_entities as WORLD

class AbilityConsumerAliasTests(unittest.TestCase):
    def world(self, rules, ability=None):
        engine = Engine(rules, 207)
        pokemon = Combatant(rules, build_pokemon(rules, '이상해씨', 20, name='actual ability holder',
            moves=['move/몸통박치기'], abilities=[] if ability is None else [ability],
            extra={'movement': {'land': 4}, 'movement_basis': 'base'}))
        trainer = Combatant(rules, build_trainer(rules, 'actual other participant', 20,
            {'hp': 30, 'atk': 10, 'def': 10, 'spa': 10, 'spd': 10, 'spe': 10},
            moves=['move/몸통박치기'], abilities=[]))
        engine.gm.add_combatant(pokemon, pos=(0, 0), side='party', reason='actual native participant')
        engine.gm.add_combatant(trainer, pos=(1, 0), side='foe', reason='actual native participant')
        return engine, pokemon, trainer

    def test_stall_exact_identity_keeps_native_queue_and_actual_own_turn_interrupt_protection(self):
        for stored in ('시간벌기', STALL.SOURCE):
            with self.subTest(stored=stored):
                engine, actor, other = self.world(Rules(ROOT, ruleset='core'), stored)
                self.assertIn(stored, actor.abilities)
                engine.gm.set_stat(actor, 'spe', value=60, reason='actual faster holder')
                self.assertEqual(INIT.order(engine, [actor, other]), [other, actor])
                engine.start_round([actor, other]);engine.start_of_turn(actor)
                trigger = INTERRUPTS._trigger(engine, {'kind': 'turn', 'actor_id': actor.entity_id,
                    'serial': actor.custom_conditions['combat_turn_serial'], 'round': engine.round_no})
                self.assertTrue(STALL.protected(engine, actor))
                with self.assertRaisesRegex(ValueError, 'cannot be Interrupted'):
                    STALL.require_interruptible(engine, trigger)
                restored = CODEC.load_engine(engine.r, CODEC.dump_engine(engine))
                actual = WORLD.actor_index(restored)[actor.entity_id]
                self.assertTrue(STALL.protected(restored, actual))
                actual.abilities_suppressed = True
                self.assertFalse(STALL.active(actual));self.assertFalse(STALL.protected(restored, actual))
                self.assertEqual(INIT.order(restored, restored.everyone)[0].entity_id, actor.entity_id)

        # The English CSV label is metadata, not a declared source selector alias.
        self.assertNotIn('Stall', engine.r.selection.names)
        before = engine.export_state(); before_logs = list(engine.log_lines)
        with self.assertRaises(UnresolvedRuleSelection):
            engine.gm.set_ability(actor, 'Stall', reason='undeclared English metadata is not a source identity')
        self.assertEqual(engine.export_state(), before)
        self.assertEqual(engine.log_lines, before_logs)

    def test_unowned_excluded_sources_remain_inapplicable_without_resolving_the_requested_uid(self):
        excluded = ['ability/점착', 'ability/대파의달인', 'ability/부유', 'ability/자기과신',
            'ability/나쁜손버릇', 'ability/매지션', AURA.STORM, AURA.STORM_TEST,
            AURA.SCRAPPY, 'ability/트위스트파워', STALL.SOURCE, 'ability/도주', 'ability/도주-playtest']
        rules = Rules(ROOT, ruleset='core')
        profile = deepcopy(rules.ruleset.profile)
        profile['exclude_units'] = list(profile.get('exclude_units', [])) + excluded
        rules.ruleset = RuleFilter(profile, 'unowned-ability-consumer-exclusions');rules._apply_ruleset()
        engine, actor, other = self.world(rules, '불면')
        before = deepcopy((actor.spec, other.spec, actor.abilities, other.abilities)), engine.rng.getstate(), list(engine.log_lines)
        # Use the already registered actors' actual retained state; no requested source is owned.
        self.assertFalse(PROTECTION.active(engine, actor, 'ability/점착'))
        self.assertFalse(PROTECTION.active(engine, actor, 'ability/대파의달인'))
        self.assertEqual(MOVEMENT.capabilities(engine, actor).get('levitate', 0), 0)
        self.assertEqual(TK.movement(engine, other, {'land': 4}), {'land': 4})
        for source in (AURA.STORM, AURA.STORM_TEST, AURA.SCRAPPY, 'ability/트위스트파워'):
            self.assertFalse(AURA.active_ability(actor, source))
        self.assertFalse(STALL.active(actor));self.assertIsNone(TUMBLER.run_away(actor))
        self.assertEqual(PASSIVE.eligibility(engine, {'actor': actor, 'target': other}, PASSIVE.RULE),
                         ('pending', 'source_listener_no_longer_owned'))
        for source, event in EQUIPMENT.REACTIONS.items():
            self.assertIsNone(EQUIPMENT.offer_reaction(engine, actor, {'event': event}, other, source))
        self.assertEqual(engine.rng.getstate(), before[1]);self.assertEqual(engine.log_lines, before[2])
        self.assertEqual((actor.spec, other.spec, actor.abilities, other.abilities), before[0])


if __name__ == '__main__':
    unittest.main()
