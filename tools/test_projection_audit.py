"""Source-required boundaries absent from the existing projection cases.

Only actual public producers are invoked. The existing fixture builds native
actors; no local replacement implementation or mirrored calculation is used.
"""
from copy import deepcopy
import test_category2_ability_state_projection as _fixture_test_category2_ability_state_projection
import ability_state_projection as P
import growth_milestones as M
from engine import Engine, Rules


class ProjectionAuditTests(_fixture_test_category2_ability_state_projection.AbilityStateProjectionTests):
    def test_creation_initialization_cannot_be_bypassed_by_direct_activation_or_restore(self):
        for ability, species, choice in [('ability/뱀무늬-playtest', '아보크', '공격무늬'),
                                          ('ability/연대감', '시비꼬', '그린 페더')]:
            with self.subTest(ability=ability):
                e = self.engine()
                c = self.actor(e, ability, species=species)
                before = e.export_state()
                with self.assertRaises(ValueError):
                    e.activate_ability_state(c, ability, choice=choice, reason='not a creation event')
                self.assertEqual(e.export_state(), before)
                options = {'choice': choice} if ability == 'ability/연대감' else {}
                e.initialize_ability_state(c, ability, reason='actual creation', **options)
                n = Engine.import_state(self.r, e.export_state())
                restored = n.everyone[0]
                before = n.export_state()
                with self.assertRaises(ValueError):
                    n.initialize_ability_state(restored, ability, reason='already-created restored actor', **options)
                self.assertEqual(n.export_state(), before)

    def test_forecast_primary_end_preserves_secondary_then_explicit_weather_update_changes_choice(self):
        e = self.engine()
        c = self.actor(e, 'ability/기분파')
        e.gm.set_weather('sunny', reason='actual primary weather')
        facts = {'weather_effects': [
            {'weather': 'sunny', 'source': 'gm/primary', 'reason': 'sunny primary'},
            {'weather': 'rain', 'source': 'gm/local', 'reason': 'independent rain still active'},
        ]}
        e.activate_ability_state(c, 'ability/기분파', choice='물', observation=facts, reason='select local rain')
        e.gm.set_weather(None, reason='only primary sunlight ends')
        self.assertEqual(c.types, ['물'])
        n = Engine.import_state(self.r, e.export_state())
        c = n.everyone[0]
        self.assertEqual(c.types, ['물'])
        n.activate_ability_state(c, 'ability/기분파', choice='노말',
                                 observation={'weather_effects':[{'weather':'none','source':'gm/weather','reason':'local rain ended too'}]},
                                 reason='explicit independent weather ended')
        self.assertEqual(c.types, ['노말'])

    def test_sunglow_source_survives_recall_and_cap_then_only_its_scene_contribution_ends(self):
        e = self.engine()
        c = self.actor(e, 'ability/노을-playtest')
        e.gm.set_ability(c, 'ability/불요의검', reason='independent default Attack source')
        e.change_stage(c, 'atk', 3)
        e.gm.set_weather('sunny', reason='actual sunlight')
        e.activate_ability(c, 'ability/노을-playtest', (c, {'mode': 'charge'}))
        e.start_round(e.everyone)
        e.start_of_turn(c, initiative_count=20)
        e.activate_ability(c, 'ability/노을-playtest', (c, {'mode': 'spend'}))
        self.assertEqual(c.stages['atk'], 6)
        e.change_stage(c, 'atk', 1)
        e.gm.recall(c, reason='same scene recall')
        self.assertEqual(c.stages['atk'], 3)
        e.end_of_turn(c)
        e.end_scene([c], round_elapsed_seconds=0)
        self.assertEqual(c.stages['atk'], 1)

    def test_stance_change_real_blessing_and_defense_raise_restore_shield_form(self):
        for move in ('move/리플렉터', 'move/철벽'):
            with self.subTest(move=move):
                e = self.engine()
                c = self.actor(e, 'ability/배틀스위치', moves=[move])
                e.activate_ability_state(c, 'ability/배틀스위치', choice='블레이드폼', reason='actual full form change')
                e.start_round(e.everyone)
                e.start_of_turn(c, initiative_count=20)
                e.use_move(c, c, move)
                self.assertEqual(c.form, '실드폼')

    def test_sunglow_attack_stage_remains_until_scene_end_after_encounter_end(self):
        e = self.engine()
        c = self.actor(e, 'ability/노을-playtest')
        e.gm.set_weather('sunny', reason='actual sunlight')
        e.activate_ability(c, 'ability/노을-playtest', (c, {'mode': 'charge'}))
        e.start_round(e.everyone)
        e.start_of_turn(c, initiative_count=20)
        e.activate_ability(c, 'ability/노을-playtest', (c, {'mode': 'spend'}))
        self.assertEqual(c.stages['atk'], 2)
        e.end_of_turn(c)
        e.end_encounter([c], round_elapsed_seconds=0)
        self.assertEqual(c.stages['atk'], 2)
        e.end_scene([c])
        self.assertEqual(c.stages['atk'], 0)

    def test_forecast_secondary_weather_choice_survives_unrelated_primary_refresh(self):
        e = self.engine()
        c = self.actor(e, 'ability/기분파')
        e.gm.set_weather('sunny', reason='observed primary sunlight')
        observations = {'weather_effects': [
            {'weather': 'sunny', 'source': 'gm/primary', 'reason': 'observed sunlight'},
            {'weather': 'rain', 'source': 'gm/local-rain', 'reason': 'independent observed local rain'},
        ]}
        e.activate_ability_state(c, 'ability/기분파', choice='물',
                                 observation=observations, reason='choose the still-active rain')
        self.assertEqual(c.types, ['물'])
        e.gm.set_weather('sunny', rounds=8, reason='refresh sunlight; local rain remains active')
        self.assertEqual(c.types, ['물'])

    def test_serpent_creation_pattern_cannot_be_rerolled_by_repeated_initialization(self):
        e = self.engine(77)
        c = self.actor(e, 'ability/뱀무늬-playtest', species='아보크')
        e.initialize_ability_state(c, 'ability/뱀무늬-playtest', reason='actual creation')
        original = deepcopy(c.spec[P.KEY]['ability/뱀무늬-playtest'])
        rng = e.rng.getstate()
        choices = [original['choice']]
        for _ in range(12):
            try:
                e.initialize_ability_state(c, 'ability/뱀무늬-playtest', reason='same actor already created')
            except ValueError:
                pass
            choices.append(c.spec[P.KEY]['ability/뱀무늬-playtest']['choice'])
        self.assertEqual(set(choices), {original['choice']}, choices)
        self.assertEqual(e.rng.getstate(), rng)

    def test_quill_creation_color_cannot_be_reselected_after_natural_pool_is_used(self):
        e = self.engine()
        c = self.actor(e, 'ability/연대감', species='시비꼬')
        e.initialize_ability_state(c, 'ability/연대감', choice='그린 페더', reason='actual creation color')
        before = M.natural_abilities(self.r, c.spec, pools=('숨겨진 특성', '대단한 특성'))
        original = deepcopy(c.spec[P.KEY]['ability/연대감'])
        try:
            e.initialize_ability_state(c, 'ability/연대감', choice='옐로우 페더', reason='same actor already created')
        except ValueError:
            pass
        self.assertEqual(c.spec[P.KEY]['ability/연대감'], original)
        self.assertEqual(M.natural_abilities(self.r, c.spec, pools=('숨겨진 특성', '대단한 특성')), before)

    def test_power_construct_accepts_distinct_perfect_hp_and_keeps_original_hp_authority(self):
        e = self.engine()
        c = self.actor(e, 'ability/스웜체인지')
        original = deepcopy(c.spec['stats'])
        perfect = deepcopy(original)
        donor = next(k for k in ('atk', 'def', 'spa', 'spd', 'spe') if perfect[k] > 1)
        perfect[donor] -= 1
        perfect['hp'] += 1
        original_max = c.base_max_hp
        e.configure_form_allocations(c, {'50%폼': original, '퍼펙트폼': perfect},
                                     active='50%폼', source='ability/스웜체인지')
        e.start_round(e.everyone)
        e.start_of_turn(c, initiative_count=20)
        c.hp = original_max // 2 - 1
        current_hp = c.hp
        e.activate_ability_state(c, 'ability/스웜체인지', choice='퍼펙트폼', reason='actual below-half daily use')
        self.assertEqual((c.hp, c.base_max_hp), (current_hp, original_max))
        self.assertGreater(c.temp_hp, original_max // 2)
