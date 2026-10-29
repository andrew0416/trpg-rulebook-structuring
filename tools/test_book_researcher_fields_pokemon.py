"""Researcher Fields of Study: Climatology (static/teaching), Paleontology and Pokemon Caretaking Pokemon-side Features (ch04:2111-2128).

Borrows fixture helpers from the crafting module without inheriting its tests.
"""
import json
import unittest

import test_book_researcher_fields_crafting as fixture
from engine import Rules
import researcher_fields as RFS
import researcher_features as RF
import move_state as MOVES
import growth_stats as GROWTH
import world_entities as WORLD


class ResearcherFieldsPokemonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(fixture.ROOT, ruleset='core')

    setUp = fixture.ResearcherFieldsCraftingTests.setUp
    setup = fixture.ResearcherFieldsCraftingTests.setup
    trainer = fixture.ResearcherFieldsCraftingTests.trainer
    pokemon = fixture.ResearcherFieldsCraftingTests.pokemon
    rejected = fixture.ResearcherFieldsCraftingTests.rejected
    valid = fixture.ResearcherFieldsCraftingTests.valid
    restore = fixture.ResearcherFieldsCraftingTests.restore
    new_day = fixture.ResearcherFieldsCraftingTests.new_day

    def fossil(self, species, name, *, feature=False, hidden=None):
        """Search, restore (natively or with Fossil Restoration) and return the unhatched egg."""
        import skill_modifiers as SKILLS
        self.t.spec['items']['복원기'] = 1
        if 'pokemon_party_policy' not in self.t.spec:
            self.e.pokemon_activity(self.t, 'party_policy', mode='unlimited', reason='GM carrying policy', roster=[])
        self.e.pokemon_activity(self.t, 'fossil', phase='search', site={'name': 'GM deposit', 'fossils_present': True}, dc=15, minutes=120,
                                discovery={'id': name, 'species': 'pokemon/' + species}, fixed=[6] * SKILLS.rank(self.rules, self.t, '포켓몬학')[2])
        if feature:
            egg = RFS.fossil_restoration(self.e, self.t, fossil_id=name, seconds=600, reason='actual Fossil Restoration')['egg']
        else:
            egg = self.e.pokemon_activity(self.t, 'fossil', phase='restore', fossil_id=name)['egg']
        return next(row for row in self.t.spec['eggs'] if row['entity_id'] == egg['entity_id'])

    def hatch(self, egg, name, *, abilities=(), nature='노력'):
        details = dict(gender='female', nature=nature, abilities=list(abilities), moves=[], inheritance_moves=[], special_appearance=False)
        child = self.e.pokemon_activity(self.t, 'hatch_fossil', egg_id=egg['id'], name=name, ready=True, reason='GM confirmed readiness', details=details)['pokemon']
        self.e.gm.observe_loyalty(child, 6, reason='actual willing Pokemon')
        return child

    def restored(self, species, name, **extra):
        return self.hatch(self.fossil(species, name), name, **extra)

    # ------------------------------------------------------------ Climatology
    def test_climatology_grants_overcoat_while_qualified_and_the_grant_is_revoked_with_the_feature(self):
        self.t.spec['skills']['생존'] = 2
        self.rejected(lambda: RFS.activate_climatology(self.e, self.t), 'Climatology requires its printed skill rank')
        self.t.spec['skills']['생존'] = 3
        sid = RFS.activate_climatology(self.e, self.t)
        self.assertEqual((sid, self.t.abilities), (RFS.CLIMATOLOGY_PREFIX + self.t.entity_id, ['방진']))
        self.assertEqual(RFS.activate_climatology(self.e, self.t), sid)
        self.restore('t')
        self.assertEqual(self.t.abilities, ['방진'])
        self.t.spec['feats'].remove(RFS.CLIMATOLOGY)
        self.assertFalse(self.e.validate_state()['valid'])
        RFS.release_climatology(self.e, self.t)
        self.assertEqual(self.t.abilities, [])
        self.valid()

    def test_weather_systems_teaches_one_printed_weather_move_by_a_real_route_free_from_the_level_up_list(self):
        w = self.pokemon('투구', 20, 'learner', moves=['move/단단해지기', 'move/할퀴기'], tutor_points=8)
        s = self.pokemon('캐스퐁', 20, 'sunny', pos=(2, 0), moves=['move/몸통박치기'], tutor_points=8)   # Sunny Day is on its Level-Up list at 20
        self.rejected(lambda: RFS.weather_systems(self.e, self.t, w, 'move/몸통박치기', seconds=3600, reason='x'), 'Hail, Rain Dance, Sandstorm or Sunny Day')
        self.rejected(lambda: RFS.weather_systems(self.e, self.t, w, 'move/쾌청', seconds=3600, reason='x'), 'cannot learn that Move by level_up, tm, tutor')
        self.t.spec['skills']['생존'] = 4
        self.rejected(lambda: RFS.weather_systems(self.e, self.t, w, 'move/싸라기눈', seconds=3600, reason='x'), 'Weather Systems requires its printed skill rank')
        self.t.spec['skills']['생존'] = 6
        w.spec['tutor_points'] = 1
        self.rejected(lambda: RFS.weather_systems(self.e, self.t, w, 'move/싸라기눈', seconds=3600, reason='x'), 'two actual Tutor Points')
        w.spec['tutor_points'] = 8
        elapsed = self.e.elapsed_seconds
        out = RFS.weather_systems(self.e, self.t, w, 'move/싸라기눈', seconds=3600, reason='actual teaching')
        self.assertEqual((out['point_cost'], out['routes'], out['classification'], w.spec['tutor_points'], self.e.elapsed_seconds - elapsed), (2, ['tm'], 'taught', 6, 3600))
        self.assertIn('move/싸라기눈', w.moves)
        routes = RFS.learning_routes(self.e, s, 'move/쾌청')
        self.assertIn('level_up', routes)
        out = RFS.weather_systems(self.e, self.t, s, 'move/쾌청', seconds=3600, reason='level-up list route')
        self.assertEqual((out['point_cost'], s.spec['tutor_points'], s.spec['move_learning']['move/쾌청']['paid_tp']), (0, 8, 0))
        other = self.trainer('stranger', (5, 5))
        wild = self.pokemon('투구', 20, 'other owned', pos=(6, 5), owner=other, moves=['move/단단해지기'], tutor_points=8)
        self.rejected(lambda: RFS.weather_systems(self.e, self.t, wild, 'move/싸라기눈', seconds=3600, reason='x'), 'actual owned Pokemon')
        self.valid()
        self.restore('t')

    # ------------------------------------------------------------ Paleontology
    def test_fossil_restoration_lowers_birth_tutor_points_by_two_and_hatches_with_both_basic_abilities(self):
        self.t.spec['items']['복원기'] = 1
        self.e.pokemon_activity(self.t, 'party_policy', mode='unlimited', reason='GM carrying policy', roster=[])
        self.e.pokemon_activity(self.t, 'fossil', phase='search', site={'name': 'GM deposit', 'fossils_present': True}, dc=15, minutes=120,
                                discovery={'id': 'F', 'species': 'pokemon/프테라'}, fixed=[3] * 6)
        self.t.spec['skills']['포켓몬학'] = 2
        self.rejected(lambda: RFS.fossil_restoration(self.e, self.t, fossil_id='F', seconds=600, reason='x'), 'Fossil Restoration requires its printed skill rank')
        self.t.spec['skills']['포켓몬학'] = 6
        self.rejected(lambda: RFS.fossil_restoration(self.e, self.t, fossil_id='missing', seconds=600, reason='x'), 'unconsumed owned fossil')
        elapsed = self.e.elapsed_seconds
        out = RFS.fossil_restoration(self.e, self.t, fossil_id='F', seconds=600, reason='actual restoration')
        egg = self.t.spec['eggs'][0]
        self.assertEqual((out['phase'], self.e.elapsed_seconds - elapsed, egg['fossil_birth_policy']['tutor_points'], egg[RFS.FOSSIL_MARK]['tutor_points']),
                         ('restore', 600, 0, {'native': 1, 'printed_delta': -2, 'birth': 0, 'deficit': 1}))
        self.assertEqual(self.t.spec[RFS.KEY]['fossils'][-1]['status'], 'restored')
        self.restore('t')
        egg = self.t.spec['eggs'][0]
        self.rejected(lambda: self.hatch(egg, 'wrong', abilities=['겁주기']), 'must be exactly')
        child = self.hatch(egg, 'child')
        self.assertEqual((sorted(child.abilities), child.spec['tutor_points']), (['겁주기', '긴장감'], 0))
        self.valid()

    def test_single_basic_ability_species_needs_the_gm_hidden_ability_choice_before_hatching(self):
        egg = self.fossil('릴링', 'single', feature=True)
        self.rejected(lambda: self.hatch(egg, 'child'), 'GM-chosen hidden Ability')
        self.rejected(lambda: RFS.choose_hidden_ability(self.e, self.t, egg['entity_id'], ability='흡반', reason='x'), 'hidden Abilities')
        out = RFS.choose_hidden_ability(self.e, self.t, egg['entity_id'], ability='저수', reason='GM chose Water Absorb')
        self.assertEqual(out['gm_hidden_ability']['ability'], '저수')
        self.assertEqual(RFS.fossil_birth_details(self.e, self.t, egg, {'abilities': []})['abilities'], ['흡반', '저수'])
        two = self.fossil('프테라', 'two', feature=True)
        self.rejected(lambda: RFS.choose_hidden_ability(self.e, self.t, two['entity_id'], ability='잔인', reason='x'), 'already has two basic Abilities')
        self.valid()
        self.restore('t')

    def test_ancient_heritage_teaches_ancient_power_free_from_the_level_up_list_else_for_two_points_only_to_your_fossil_pokemon(self):
        k = self.restored('프테라', 'fossil')
        n = self.pokemon('투구', 20, 'ordinary', pos=(3, 0), moves=['move/단단해지기'], tutor_points=8)
        self.rejected(lambda: RFS.ancient_heritage(self.e, self.t, n, seconds=3600, reason='x'), 'restored from a fossil')
        self.rejected(lambda: RFS.ancient_heritage(self.e, self.t, k, seconds=3600, reason='x'), 'two actual Tutor Points')
        self.e.pokemon_activity(self.t, 'observe_tutor_points', target=k, balance=6, reason='GM establishes the actual balance')
        out = RFS.ancient_heritage(self.e, self.t, k, seconds=3600, reason='actual teaching')
        self.assertEqual((out['point_cost'], sorted(out['routes']), k.spec['tutor_points']), (0, ['level_up', 'tutor'], 6))
        self.assertTrue(RFS.ancient_heritage_active(self.e, k))
        self.rejected(lambda: RFS.ancient_heritage(self.e, self.t, k, seconds=3600, reason='x'), 'already learned')
        self.rejected(lambda: RFS.choose_ancient_power_class(self.e, k, '변화'), '물리 or 특수')
        self.assertEqual(RFS.choose_ancient_power_class(self.e, k, '물리'), '물리')
        self.restore('t')
        k = WORLD.actor_index(self.e)[k.entity_id]
        self.assertEqual(k.spec['researcher_ancient_power_choice'], '물리')
        t2 = self.restored('꼬마돌', 'paid')   # GM-approved nonstandard fossil species: Ancient Power only on its Tutor list
        self.e.pokemon_activity(self.t, 'observe_tutor_points', target=t2, balance=6, reason='GM establishes the actual balance')
        out = RFS.ancient_heritage(self.e, self.t, t2, seconds=3600, reason='tutor list route')
        self.assertEqual((out['point_cost'], out['routes'], t2.spec['tutor_points']), (2, ['tutor'], 4))
        self.valid()

    def test_genetic_memory_teaches_egg_and_tutor_moves_once_per_route_daily_twice_and_keeps_the_egg_route_outside_the_pool_limit(self):
        k = self.restored('프테라', 'fossil')
        self.e.pokemon_activity(self.t, 'observe_tutor_points', target=k, balance=12, reason='GM establishes the actual balance')
        self.rejected(lambda: RFS.genetic_memory(self.e, self.t, k, 'move/저주', route='tm', seconds=3600, reason='x'), 'route is egg or tutor')
        self.rejected(lambda: RFS.genetic_memory(self.e, self.t, k, 'move/아쿠아테일', route='egg', seconds=3600, reason='x'), 'cannot learn that Move by the egg route')
        self.t.spec['skills']['포켓몬학'] = 4
        self.rejected(lambda: RFS.genetic_memory(self.e, self.t, k, 'move/저주', route='egg', seconds=3600, reason='x'), 'Genetic Memory requires its printed skill rank')
        self.t.spec['skills']['포켓몬학'] = 6
        egg = RFS.genetic_memory(self.e, self.t, k, 'move/저주', route='egg', seconds=3600, reason='egg route')
        self.assertEqual((egg['point_cost'], egg['classification'], k.spec['tutor_points']), (2, 'natural', 10))
        self.rejected(lambda: RFS.genetic_memory(self.e, self.t, k, 'move/승부굳히기', route='egg', seconds=3600, reason='x'), 'already used the egg route')
        tutor = RFS.genetic_memory(self.e, self.t, k, 'move/아쿠아테일', route='tutor', seconds=3600, reason='tutor route')
        self.assertEqual((tutor['point_cost'], tutor['classification'], k.spec['tutor_points']), (2, 'taught', 8))
        self.assertTrue(RFS.pool_exempt(k.spec, 'move/저주'))
        self.assertFalse(RFS.pool_exempt(k.spec, 'move/아쿠아테일'))
        self.assertEqual(MOVES.describe(self.rules, k.spec, require_routes=True)['taught_count'], 1)
        other = self.restored('아마루스', 'second')
        self.e.pokemon_activity(self.t, 'observe_tutor_points', target=other, balance=6, reason='GM establishes the actual balance')
        self.rejected(lambda: RFS.genetic_memory(self.e, self.t, other, 'move/배리어', route='egg', seconds=3600, reason='x'), 'daily frequency')
        self.new_day()
        out = RFS.genetic_memory(self.e, self.t, other, 'move/배리어', route='egg', seconds=3600, reason='next day')
        self.assertEqual(out['route'], 'egg')
        self.valid()
        self.restore('t')

    def test_prehistoric_bond_makes_each_printed_relic_from_the_individuals_highest_nature_adjusted_base_stat(self):
        import items as ITEMS
        for species, relic, expected in (('아마루스', 'hp', 'save_mod'), ('두개도스', 'atk', 'crit_range'), ('방패톱스', 'def', None),
                                         ('릴링', 'spd', 'damage_reduction'), ('프테라', 'spe', None)):
            with self.subTest(relic=relic):
                self.setUp()
                k = self.restored(species, species)
                wrong = next(stat for stat in ('hp', 'atk', 'def', 'spa', 'spd', 'spe') if stat != relic)
                self.rejected(lambda: RFS.craft_relic(self.e, self.t, k, relic=wrong, minutes=10), 'among the highest nature-adjusted base stats')
                self.rejected(lambda: RFS.craft_relic(self.e, self.t, k, relic='spa' if relic != 'spa' else 'hp', minutes=10), 'among the highest')
                record = RFS.craft_relic(self.e, self.t, k, relic=relic, minutes=10)
                self.assertEqual((record['selected_stat'], record['feature'], self.t.spec['items'][record['id']]), (relic, RF.PREHISTORIC_BOND, 1))
                self.assertTrue(record['id'].startswith(RFS.DEFINITIONS[RFS.BOND]['relics'][relic]['prefix']))
                self.rejected(lambda: RFS.craft_relic(self.e, self.t, k, relic=relic, minutes=10), 'already produced a relic')
                RF.equip_relic(self.e, self.t, k, record['id'])
                self.assertEqual((k.item, self.t.spec['items'][record['id']]), (record['id'], 0))
                kinds = [m.get('type') for m in k.modifiers if m.get('_item') == record['id']]
                if relic == 'hp':
                    self.assertEqual(k.save_mod, 2)
                elif expected is not None:
                    self.assertIn(expected, kinds)
                if relic == 'spe':
                    self.assertEqual(RFS.evasion_bonus(self.e, k, self.rules.move('move/꼬리흔들기')), 2)
                    self.assertEqual(RFS.evasion_bonus(self.e, k, self.rules.move('move/전광석화')), 0)
                self.restore('t')
                k = WORLD.actor_index(self.e)[k.entity_id]
                self.assertEqual(ITEMS.register_item(self.e, k, record['id']), 0)
                self.valid()

    def test_relics_require_the_restorer_the_expert_rank_and_the_field_and_stay_bound_to_the_individual(self):
        k = self.restored('아마루스', 'crown')
        self.t.spec['skills']['포켓몬학'] = 4
        self.rejected(lambda: RFS.craft_relic(self.e, self.t, k, relic='hp', minutes=10), 'Prehistoric Bond requires its printed skill rank')
        self.t.spec['skills']['포켓몬학'] = 6
        self.rejected(lambda: RFS.craft_relic(self.e, self.t, k, relic='xyz', minutes=10), 'relic stat required')
        record = RFS.craft_relic(self.e, self.t, k, relic='hp', minutes=10)
        other = self.pokemon('아마루스', 10, 'other', pos=(4, 0))
        self.rejected(lambda: RF.equip_relic(self.e, self.t, other, record['id']), 'bound to another restored individual')
        self.assertEqual(RFS.relic_definition(record['id'])[0], 'hp')
        self.assertIsNone(RFS.relic_definition('item/기합의띠'))

    # ------------------------------------------------------------ Pokemon Caretaking
    def test_pusher_funds_the_listed_poke_edges_so_the_pokemon_pays_no_tutor_points(self):
        q = self.pokemon('파이리', 20, 'free', moves=[], abilities=[], tutor_points=0)
        self.t.spec['skills']['포켓몬학'] = 2
        self.rejected(lambda: self.e.pokemon_activity(self.t, 'teach_edge', target=q, edge='기본 원거리 공격', capability='불쏘시개', safe=True), 'Pusher requires its printed skill rank')
        self.t.spec['skills']['포켓몬학'] = 3
        elapsed = self.e.elapsed_seconds
        out = self.e.pokemon_activity(self.t, 'teach_edge', target=q, edge='기본 원거리 공격', capability='불쏘시개', safe=True)
        receipt = q.spec['learned_poke_edges'][-1]
        self.assertEqual((out['pusher_net_point_cost'], q.spec['tutor_points'], receipt['point_cost'], receipt['pusher']['net_point_cost'], receipt['pusher']['feature'], self.e.elapsed_seconds - elapsed),
                         (0, 0, 1, 0, RFS.PUSHER, 3600))
        other = self.pokemon('꼬부기', 20, 'paying', pos=(2, 0), moves=[], abilities=[], tutor_points=3)
        self.e.pokemon_activity(self.t, 'teach_edge', target=other, edge='재능 훈련', capability='power', safe=True)
        self.assertEqual(other.spec['tutor_points'], 2)   # an unlisted Poke Edge still costs its point
        stranger = self.trainer('stranger', (5, 5))
        self.rejected(lambda: self.e.pokemon_activity(stranger, 'teach_edge', target=other, edge='기본 원거리 공격', capability='물줄기', safe=True), 'belongs to a different trainer')
        self.valid()
        self.restore('t')

    def test_this_ones_special_marks_one_hatching_egg_once_per_pokemon_education_rank_above_untrained_and_the_child_carries_it(self):
        egg = self.fossil('프테라', 'first')
        self.rejected(lambda: RFS.special_quality(self.e, self.t, 'egg/missing', quality='x', reason='r'), 'actual unhatched egg')
        self.t.spec['skills']['포켓몬학'] = 3
        self.assertEqual(RFS.special_uses(self.e, self.t), 1)
        out = RFS.special_quality(self.e, self.t, egg['entity_id'], quality='GM: it hums in its sleep', reason='GM decision')
        self.assertEqual(out['quality'], 'GM: it hums in its sleep')
        self.rejected(lambda: RFS.special_quality(self.e, self.t, egg['entity_id'], quality='again', reason='r'), 'once per Pokemon Education rank')
        second = self.fossil('아마루스', 'second')
        self.rejected(lambda: RFS.special_quality(self.e, self.t, second['entity_id'], quality='x', reason='r'), 'once per Pokemon Education rank')
        self.t.spec['skills']['포켓몬학'] = 4
        RFS.special_quality(self.e, self.t, second['entity_id'], quality='GM: unusual colouring pattern', reason='GM decision')
        self.restore('t')
        child = self.hatch(next(row for row in self.t.spec['eggs'] if row['id'] == 'fossil/first'), 'child')
        self.assertEqual(child.spec['special_quality']['quality'], 'GM: it hums in its sleep')
        self.assertEqual(len(self.t.spec[RFS.KEY]['special_quality']), 2)
        self.valid()

    def test_rebalancing_adds_the_chosen_base_bonus_then_redistributes_points_for_two_tutor_points_once_per_pokemon(self):
        q = self.pokemon('근육몬', 20, 'target', moves=[], abilities=[], tutor_points=6)
        investment = GROWTH.project_actor(self.e, q)['permanent']['investment']
        legal = {'hp': 5, 'atk': 8, 'def': 7, 'spa': 4, 'spd': 4, 'spe': 2}
        self.assertEqual(sum(legal.values()), sum(investment.values()))
        self.rejected(lambda: RFS.rebalance(self.e, self.t, q, option='two_plus_two', stats=['atk'], investment=legal, seconds=3600, reason='x', request_id='r1'), 'exactly 2 distinct base stats')
        self.rejected(lambda: RFS.rebalance(self.e, self.t, q, option='two_plus_two', stats=['atk', 'def'], investment=investment, seconds=3600, reason='x', request_id='r1'), 'violates base relations')
        self.t.spec['skills']['포켓몬학'] = 5
        self.rejected(lambda: RFS.rebalance(self.e, self.t, q, option='two_plus_two', stats=['atk', 'def'], investment=legal, seconds=3600, reason='x', request_id='r1'), 'Re-Balancing requires its printed skill rank')
        self.t.spec['skills']['포켓몬학'] = 6
        before = dict(q.spec['stats'])
        out = RFS.rebalance(self.e, self.t, q, option='two_plus_two', stats=['atk', 'def'], investment=legal, seconds=3600, reason='actual rebalancing', request_id='r1')
        self.assertEqual((out['deltas'], q.spec['tutor_points']), ({'atk': 2, 'def': 2}, 4))
        self.assertEqual(q.spec['stats'], {'hp': 13, 'atk': 20, 'def': 16, 'spa': 9, 'spd': 10, 'spe': 7})
        self.assertNotEqual(q.spec['stats'], before)
        self.assertEqual(GROWTH.project_actor(self.e, q)['permanent']['stats'], q.spec['stats'])
        self.rejected(lambda: RFS.rebalance(self.e, self.t, q, option='all_plus_one', stats=None, investment=legal, seconds=3600, reason='x', request_id='r2'), 'only once')
        other = self.pokemon('근육몬', 20, 'one', pos=(3, 0), moves=[], abilities=[], tutor_points=6)
        self.restore('t')
        q, other = (WORLD.actor_index(self.e)[x.entity_id] for x in (q, other))
        self.assertEqual(GROWTH.project_actor(self.e, q)['permanent']['stats'], {'hp': 13, 'atk': 20, 'def': 16, 'spa': 9, 'spd': 10, 'spe': 7})
        out = RFS.rebalance(self.e, self.t, other, option='one_plus_three', stats=['atk'], investment={'hp': 6, 'atk': 10, 'def': 5, 'spa': 3, 'spd': 4, 'spe': 2}, seconds=3600, reason='one stat', request_id='r3')
        self.assertEqual((out['deltas'], other.spec['stats']['atk']), ({'atk': 3}, 10 + 3 + 10))
        self.valid()


if __name__ == '__main__':
    unittest.main()
