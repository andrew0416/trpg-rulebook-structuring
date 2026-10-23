"""Source counterexample: printed core213/496 say Capabilities BY two."""
import test_core_baby_template as _fixture_test_core_baby_template
from copy import deepcopy
import json
import baby_templates as BABY
import capability_actions as CAP
import movement_actions as MOVE
import jump_actions as JUMP
import downtime as D
import state_codec as CODEC
from grid import Grid


class SourceCapabilityTests(_fixture_test_core_baby_template.BabyTemplateTests):
    def test_numeric_capabilities_are_reduced_by_two_not_power_capped_at_two(self):
        pokemon = self.pokemon()
        MOVE.set_capabilities(self.e, pokemon,
            {'land': 6, 'swim': 4, 'power': 6, 'high_jump': 3, 'long_jump': 4},
            basis='current', reason_text='GM observed this actual individual before Baby Template')
        before = MOVE.capabilities(self.e, pokemon, environment=False)
        before_power = CAP.power(pokemon)
        BABY.apply(self.e, pokemon, stat_reduction=2, reason='GM chose original optional Baby Template')
        after = MOVE.capabilities(self.e, pokemon, environment=False)
        with self.subTest(capability='Power', before=before_power):
            self.assertEqual(CAP.power(pokemon), before_power-2)
        for name in ('land', 'swim', 'high_jump', 'long_jump'):
            with self.subTest(capability=name, before=before[name]):
                self.assertEqual(after[name], before[name]-2)
        self.assertEqual(JUMP.limits(pokemon), {'high_jump': 1, 'long_jump': 2})
        self.assertEqual(self.e.move_profile(pokemon, movement_mode='land')[0], 4)

    def test_zero_one_two_three_boundaries_use_existing_domains_without_granting_modes(self):
        for power in (1, 2, 3, 6):
            with self.subTest(power=power):
                pokemon = self.pokemon()
                MOVE.set_capabilities(self.e, pokemon,
                    {'land': 3, 'sky': 1, 'swim': 2, 'burrow': 0, 'power': power,
                     'high_jump': 3, 'long_jump': 2}, basis='current',
                    reason_text='GM observed actual numeric capabilities before optional template')
                BABY.apply(self.e, pokemon, stat_reduction=2, reason='explicit GM template choice')
                caps = MOVE.capabilities(self.e, pokemon, environment=False)
                self.assertEqual({k: caps[k] for k in ('land', 'sky', 'swim', 'burrow')},
                                 {'land': 1, 'sky': 0, 'swim': 0, 'burrow': 0})
                self.assertNotIn('teleport', caps)
                self.assertEqual(JUMP.limits(pokemon), {'high_jump': 1, 'long_jump': 0})
                self.assertEqual(CAP.power(pokemon), max(1, power-2))

    def test_fifth_level_recovery_and_both_restores_remove_penalty_exactly_once(self):
        pokemon = self.pokemon()
        MOVE.set_capabilities(self.e, pokemon,
            {'land': 6, 'swim': 4, 'power': 6, 'high_jump': 3, 'long_jump': 4},
            basis='current', reason_text='GM observed actual starting capabilities')
        BABY.apply(self.e, pokemon, stat_reduction=2, reason='recovering template')
        D.gain_exp_combatant(self.e, pokemon, 'to next level')
        self.assertEqual(pokemon.spec[BABY.KEY]['stat_penalty_remaining'], 1)
        snapshot = self.e.gm.snapshot()
        loaded = self.restored_actor(pokemon)
        self.assertEqual(CAP.power(loaded), 4)
        self.assertEqual(JUMP.limits(loaded), {'high_jump': 1, 'long_jump': 2})
        D.gain_exp_combatant(self.e, pokemon, D.exp_for_level(self.r, 10)-pokemon.spec['exp'])
        self.assertEqual(pokemon.spec[BABY.KEY]['stat_penalty_remaining'], 0)
        self.assertEqual(CAP.power(pokemon), 6)
        self.assertEqual(JUMP.limits(pokemon), {'high_jump': 3, 'long_jump': 4})
        self.assertEqual(MOVE.capabilities(self.e, pokemon, environment=False)['land'], 6)
        self.e.gm.restore(snapshot)
        self.assertEqual(CAP.power(pokemon), 4)
        self.assertEqual(JUMP.limits(pokemon), {'high_jump': 1, 'long_jump': 2})

    def test_actual_movement_jump_and_invalid_observation_preserve_source_atomicity(self):
        pokemon = self.pokemon()
        MOVE.set_capabilities(self.e, pokemon,
            {'land': 6, 'swim': 4, 'power': 6, 'high_jump': 3, 'long_jump': 4},
            basis='current', reason_text='GM observed this actual individual')
        before = (self.snapshot(), self.e.rng.getstate(), self.e.elapsed_seconds)
        with self.assertRaises(ValueError):
            BABY.apply(self.e, pokemon, stat_reduction=2, height_reduction=.51,
                       reason='invalid observed size reduction')
        self.assertEqual((self.snapshot(), self.e.rng.getstate(), self.e.elapsed_seconds), before)
        BABY.apply(self.e, pokemon, stat_reduction=2, reason='explicit original-source selection')
        self.assertEqual(pokemon.spec[BABY.KEY]['source'], BABY.SOURCE)
        self.e.grid = Grid(20, 20); pokemon.pos = (0, 0); self.a.pos = (10, 0)
        self.e.start_round([pokemon]); self.e.start_of_turn(pokemon)
        self.e.approach(pokemon, self.a, 1, movement_mode='land')
        self.assertEqual(pokemon.pos, (4, 0))
        self.e.end_of_turn(pokemon)
        self.e.start_round([pokemon]); self.e.start_of_turn(pokemon)
        out = self.e.jump(pokemon, (6, 0), jump_id='baby-native-jump',
            difficult=False, clear_path=True, reason_text='ordinary clear jump under actual reduced limits')
        self.assertEqual(pokemon.pos, (6, 0))
        self.assertEqual(pokemon.budget['shift'], 0)
        saved = CODEC.dump_engine(self.e)
        broken = deepcopy(saved)
        # Inspect the actual codec graph, not an assumed nested JSON layout.
        actor_node = next(x for x in broken['nodes'].values()
            if x.get('kind') == 'actor' and x.get('entity_id') == pokemon.entity_id)
        attrs_node = broken['nodes'][actor_node['attrs']['$ref']]
        spec_ref = next(pair for pair in attrs_node['items'] if pair[0] == 'spec')[1]['$ref']
        spec_node = broken['nodes'][spec_ref]
        baby_pair = next(pair for pair in spec_node['items'] if pair[0] == BABY.KEY)
        baby_node = broken['nodes'][baby_pair[1]['$ref']]
        source_pair = next(pair for pair in baby_node['items'] if pair[0] == 'source')
        source_pair[1] = 'unselected/invented-template'
        before = self.snapshot()
        with self.assertRaises(ValueError): CODEC.load_engine(self.r, broken)
        self.assertEqual(self.snapshot(), before)
