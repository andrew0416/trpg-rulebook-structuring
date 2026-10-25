"""Exact S-cls_b-R1/R3/R4/R5 connections; reuse Researcher's native fixtures without inheriting their tests."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import test_book_researcher_fields_combat as combat_fixture
import test_book_researcher_fields_crafting as crafting_fixture
from engine import Rules
import action_points as AP
import items as ITEMS
import researcher_fields as RFS
import researcher_features as RF
import weather_state as WEATHER


class RemainingResearcherRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(crafting_fixture.ROOT, ruleset='core')

    setUp = combat_fixture.ResearcherFieldsCombatTests.setUp
    add = combat_fixture.ResearcherFieldsCombatTests.add
    combat = combat_fixture.ResearcherFieldsCombatTests.combat
    next_turn = combat_fixture.ResearcherFieldsCombatTests.next_turn
    use = combat_fixture.ResearcherFieldsCombatTests.use
    restored = combat_fixture.ResearcherFieldsCombatTests.restored
    rejected = crafting_fixture.ResearcherFieldsCraftingTests.rejected
    valid = crafting_fixture.ResearcherFieldsCraftingTests.valid
    restore = crafting_fixture.ResearcherFieldsCraftingTests.restore

    def test_chemical_warfare_native_throw_uses_only_the_two_by_two_blast(self):
        self.t.spec['items']['item/오물탄-잠듦'] = 1
        self.t.spec['skills'].update({'육상': 2, '곡예': 4})
        primary = self.add('primary', 'pokemon', (3, 1), side='foe', species='피카츄', speed=19)
        diagonal = self.add('inside diagonal', 'pokemon', (4, 2), side='foe', species='이상해씨', speed=18)
        distance_two = self.add('outside distance two', 'pokemon', (5, 1), side='foe', species='이상해씨', speed=17)
        opposite = self.add('outside opposite side', 'pokemon', (2, 1), side='party', species='이상해씨', speed=16)
        self.combat(self.t)
        RFS.chemical_warfare(self.e, self.t)
        result = self.e.use_item(self.t, 'item/오물탄-잠듦', primary, fixed_accuracy=20)
        self.assertTrue(result['hit'])
        self.assertEqual([row['target_id'] for row in result['chemical_warfare']], [diagonal.entity_id])
        self.assertEqual(['잠듦' in actor.conditions for actor in (primary, diagonal, distance_two, opposite)], [True, True, False, False])
        self.assertEqual(self.t.spec['items']['item/오물탄-잠듦'], 0)
        self.assertIsNone(self.t.spec[RFS.KEY]['chemistry']['warfare'])
        self.valid()

    def test_chemical_warfare_native_blast_includes_the_thrower_when_in_the_square(self):
        self.t.spec['items']['item/오물탄-독'] = 1
        self.t.spec['skills'].update({'육상': 2, '곡예': 4})
        primary = self.add('close primary', 'pokemon', (0, 0), side='foe', species='이상해씨', speed=15)
        self.combat(self.t)
        RFS.chemical_warfare(self.e, self.t)
        result = self.e.use_item(self.t, 'item/오물탄-독', primary, fixed_accuracy=20)
        self.assertTrue(result['hit'])
        self.assertIn(self.t.entity_id, [row['target_id'] for row in result['chemical_warfare']])
        self.assertIn('독', self.t.conditions)
        self.valid()

    def weather_actors(self):
        self.p = self.add('ally weather maker', 'pokemon', (2, 2), trainer_id=self.t.entity_id,
                          species='캐스퐁', level=20, types=['노말'], moves=['move/비바라기', 'move/쾌청'], speed=25)
        self.f = self.add('enemy weather maker', 'pokemon', (5, 2), side='foe', species='캐스퐁',
                          level=20, types=['노말'], moves=['move/쾌청', 'move/싸라기눈'], speed=15)
        self.combat(self.p)
        self.use(self.p, self.p, 'move/비바라기')
        self.next_turn(self.t)

    def test_enemy_native_move_consumes_the_paid_declaration_after_pending_restore(self):
        self.weather_actors()
        before = AP.available(self.t)
        RFS.temperature_control(self.e, self.t)
        self.assertEqual(AP.available(self.t), before - 1)
        self.restore('t', 'p', 'f')
        self.next_turn(self.f, count=15)
        self.use(self.f, self.f, 'move/쾌청')
        state = WEATHER.state(self.e)
        self.assertEqual(WEATHER.effective_weathers(self.e), ('rain', 'sunny'))
        self.assertEqual(state['layers'][0]['actor_id'], self.f.entity_id)
        self.assertEqual(state['layers'][0]['temperature_control']['trainer_id'], self.t.entity_id)
        self.assertIsNone(self.t.spec[RFS.KEY]['climatology']['temperature_control'])
        self.assertEqual(AP.available(self.t), before - 1)
        self.valid()

    def snow_warning_actor(self):
        self.s = self.add('enemy native Snow Warning', 'pokemon', (8, 2), side='foe',
                          species='캐스퐁', level=20, types=['노말'], moves=[],
                          abilities=['눈퍼트리기'], speed=14)
        return self.s

    def test_enemy_native_snow_warning_consumes_the_paid_declaration_after_pending_restore(self):
        import ability_native_actions as NATIVE
        self.weather_actors();self.snow_warning_actor()
        rain=deepcopy(WEATHER.state(self.e)['active']);before=AP.available(self.t)
        self.assertEqual(WEATHER.effective_weathers(self.e),('rain',))
        self.assertFalse(self.s.spec.get(NATIVE.HISTORY))  # Ownership/entry is not activation.
        RFS.temperature_control(self.e,self.t)
        self.assertEqual(AP.available(self.t),before-1)
        self.restore('t','p','f','s');self.next_turn(self.s,count=14)
        budgets=deepcopy(self.s.budget)
        receipt=self.e.activate_ability(self.s,'ability/눈퍼트리기',self.s)
        state=WEATHER.state(self.e);layer=deepcopy(state['layers'][0])
        self.assertEqual(WEATHER.effective_weathers(self.e),('rain','hail'))
        self.assertEqual((state['active']['id'],state['active']['deadline_round']),(rain['id'],rain['deadline_round']))
        self.assertEqual((layer['origin'],layer['source_id'],layer['actor_id'],layer['duration']),
                         ('ability','ability/눈퍼트리기',self.s.entity_id,5))
        self.assertEqual(layer['deadline_round'],layer['started_round']+5)
        self.assertEqual(layer['deadline_count'],14)
        self.assertEqual(layer['ability_activation_id'],receipt['id'])
        self.assertEqual(layer['temperature_control']['trainer_id'],self.t.entity_id)
        self.assertIsNone(self.t.spec[RFS.KEY]['climatology']['temperature_control'])
        self.assertEqual(AP.available(self.t),before-1)
        self.assertEqual(self.s.budget,budgets)
        self.assertEqual(len(self.s.spec[NATIVE.HISTORY]),1)
        self.restore('t','p','f','s')
        self.assertEqual(WEATHER.state(self.e)['layers'][0],layer)
        # Ordinary downstream Hail hurts a vulnerable actor, not its printed holder.
        hp=self.s.hp;foe_hp=self.f.hp
        self.next_turn(self.f,count=15);self.assertLess(self.f.hp,foe_hp)
        self.next_turn(self.s,count=14);self.assertEqual(self.s.hp,hp)
        while self.e.round_no<rain['deadline_round']+1:self.next_turn(self.s,count=14)
        self.assertEqual(WEATHER.effective_weathers(self.e),('hail',))
        current=WEATHER.state(self.e)['active']
        self.assertEqual((current['id'],current['deadline_round']),(layer['id'],layer['deadline_round']))
        while self.e.round_no<layer['deadline_round']+1:self.next_turn(self.s,count=14)
        self.assertEqual(WEATHER.effective_weathers(self.e),())
        self.assertEqual(AP.available(self.t),before-1);self.valid()

    def test_native_snow_warning_refuses_unpaid_forgery_suppression_and_exhaustion_atomically(self):
        self.weather_actors();self.snow_warning_actor()
        self.rejected(lambda:WEATHER.set_weather(self.e,'hail',rounds=5,source_id='ability/눈퍼트리기',
            origin='ability',actor=self.s),'actual paid native Ability')
        before=AP.available(self.t);RFS.temperature_control(self.e,self.t)
        self.next_turn(self.s,count=14)
        self.s.abilities_suppressed=True
        self.rejected(lambda:self.e.activate_ability(self.s,'ability/눈퍼트리기',self.s),'suppressed Ability')
        self.assertIsNotNone(self.t.spec[RFS.KEY]['climatology']['temperature_control'])
        self.s.abilities_suppressed=False
        self.e.activate_ability(self.s,'ability/눈퍼트리기',self.s)
        self.next_turn(self.t);RFS.temperature_control(self.e,self.t,
            replace_weather_id=WEATHER.state(self.e)['layers'][0]['id'])
        self.next_turn(self.s,count=14)
        self.rejected(lambda:self.e.activate_ability(self.s,'ability/눈퍼트리기',self.s),'frequency exhausted')
        self.assertIsNotNone(self.t.spec[RFS.KEY]['climatology']['temperature_control'])
        self.assertEqual(AP.available(self.t),before-2);self.valid()

    def test_native_snow_warning_without_declaration_replaces_weather_and_requires_actual_owner(self):
        self.weather_actors();self.snow_warning_actor();self.next_turn(self.s,count=14)
        self.rejected(lambda:self.e.activate_ability(self.f,'ability/눈퍼트리기',self.f),'does not own')
        self.e.activate_ability(self.s,'ability/눈퍼트리기',self.s)
        state=WEATHER.state(self.e)
        self.assertEqual(WEATHER.effective_weathers(self.e),('hail',))
        self.assertEqual(state['layers'],[])
        self.assertNotIn('temperature_control',state['active']);self.valid()

    def test_native_snow_warning_with_observed_environment_keeps_one_paid_producer_after_restore(self):
        import json
        import ability_native_actions as NATIVE, environment_change as EC, environment_derive as ED
        self.weather_actors();self.snow_warning_actor()
        policy=json.loads((crafting_fixture.ROOT/'data/examples/environment-derive.json').read_text(encoding='utf-8'))
        self.e.observe_environment('snow-warning-region',dict(gravity=1,pressure=1,air_available=True,medium='air'),
            source=policy['source'],reason='actual observed atmosphere before Snow Warning')
        self.e.bind_environment(self.t,policy,reason='independent observed trainer in the weather region')
        self.assertTrue(EC.has_pending(self.e));self.assertTrue(ED.bound(self.e,self.t))
        RFS.temperature_control(self.e,self.t)
        self.next_turn(self.s,count=14)
        budgets=deepcopy(self.s.budget);ap=AP.available(self.t)
        self.rejected(lambda:WEATHER.set_weather(self.e,'hail',rounds=5,source_id='ability/눈퍼트리기',
            origin='ability',actor=self.s),'actual paid native Ability')
        receipt=self.e.activate_ability(self.s,'ability/눈퍼트리기',self.s)
        self.assertEqual(WEATHER.effective_weathers(self.e),('rain','hail'))
        layer=deepcopy(WEATHER.state(self.e)['layers'][0])
        self.assertEqual(layer['ability_activation_id'],receipt['id'])
        self.assertEqual(layer['actor_id'],self.s.entity_id)
        self.assertEqual(len(self.s.spec[NATIVE.HISTORY]),1)
        self.assertEqual((self.s.budget,AP.available(self.t)),(budgets,ap))
        self.assertIsNone(self.t.spec[RFS.KEY]['climatology']['temperature_control'])
        self.assertEqual(ED.context(self.e,self.t)['region_id'],'snow-warning-region')
        self.restore('t','p','f','s')
        self.assertEqual(WEATHER.state(self.e)['layers'][0],layer)
        self.assertTrue(ED.bound(self.e,self.t));self.assertTrue(EC.has_pending(self.e))
        self.rejected(lambda:self.e.activate_ability(self.s,'ability/눈퍼트리기',self.s),'frequency exhausted')
        self.assertEqual(len(self.s.spec[NATIVE.HISTORY]),1)
        self.assertEqual((self.s.budget,AP.available(self.t)),(budgets,ap));self.valid()

    def two_weathers(self):
        self.weather_actors()
        RFS.temperature_control(self.e, self.t)
        self.next_turn(self.p, count=25)
        self.use(self.p, self.p, 'move/쾌청')
        self.assertEqual(WEATHER.effective_weathers(self.e), ('rain', 'sunny'))

    def test_third_native_weather_without_reactivation_replaces_both_occurrences(self):
        self.two_weathers()
        before = [WEATHER.state(self.e)['active']['id'], WEATHER.state(self.e)['layers'][0]['id']]
        self.next_turn(self.t)
        self.next_turn(self.f, count=15)
        self.use(self.f, self.f, 'move/싸라기눈')
        state = WEATHER.state(self.e)
        self.assertEqual((WEATHER.effective_weathers(self.e), state['layers']), (('hail',), []))
        self.assertEqual({row['id'] for row in state['history'] if row['end_reason'] == 'replaced'}, set(before))
        self.valid()

    def replace_weather(self, which):
        self.two_weathers()
        state = WEATHER.state(self.e)
        primary, layer = deepcopy(state['active']), deepcopy(state['layers'][0])
        replaced = primary if which == 'primary' else layer
        kept = layer if which == 'primary' else primary
        producer=self.f
        if which == 'layer':
            RFS.extreme_weather(self.e, self.t)
            self.assertIn('억압', self.f.conditions)
            # The suppressed foe cannot activate Daily Hail. An independent
            # Fire-type producer is exempt from this exact Sunny extreme effect.
            producer=self.add('legal replacement weather producer','pokemon',(8,4),side='foe',
                species='캐스퐁',level=20,types=['불꽃'],moves=['move/싸라기눈'],speed=14)
        self.next_turn(self.t)
        self.rejected(lambda: RFS.temperature_control(self.e, self.t), 'actual weather occurrence to replace')
        self.rejected(lambda: RFS.temperature_control(self.e, self.t, replace_weather_id=-1), 'actual weather occurrence to replace')
        before = AP.available(self.t)
        RFS.temperature_control(self.e, self.t, replace_weather_id=replaced['id'])
        self.assertEqual(AP.available(self.t), before - 1)
        self.next_turn(producer, count=14 if which=='layer' else 15)
        self.use(producer, producer, 'move/싸라기눈')
        state = WEATHER.state(self.e)
        self.assertEqual(WEATHER.effective_weathers(self.e), (kept['weather'], 'hail'))
        self.assertEqual((state['active']['id'], state['active']['deadline_round']), (kept['id'], kept['deadline_round']))
        self.assertEqual(len(state['layers']), 1)
        self.assertEqual(state['layers'][0]['temperature_control']['coexists_with'], kept['id'])
        self.assertEqual([row['id'] for row in state['history'] if row['end_source'] == RFS.TEMPERATURE], [replaced['id']])
        self.assertIsNone(self.t.spec[RFS.KEY]['climatology']['temperature_control'])
        self.assertEqual(AP.available(self.t), before - 1)
        if which == 'layer':
            self.assertNotIn('억압', self.f.conditions)
        self.valid()

    def test_reactivation_replaces_the_selected_primary_and_keeps_the_layers_original_deadline(self):
        self.replace_weather('primary')

    def test_reactivation_replaces_the_selected_layer_and_ends_only_its_extreme_effect(self):
        self.replace_weather('layer')

    def test_relic_crown_equips_another_native_fossil_and_rolls_back_late_registration_before_payment(self):
        source = self.restored('아마루스', 'crown source', pos=(7, 6))
        self.k = self.restored('두개도스', 'other revived holder', pos=(2, 2))
        plain = self.add('ordinary holder', 'pokemon', (4, 2), trainer_id=self.t.entity_id, species='아마루스', speed=15)
        record = RFS.craft_relic(self.e, self.t, source, relic='hp', minutes=10)
        self.rejected(lambda: RF.equip_relic(self.e, self.t, plain, record['id']), 'actual Pokemon revived from a fossil')
        native = ITEMS.register_item

        def fail_after_registration(engine, holder, identity):
            native(engine, holder, identity)
            raise ValueError('injected failure after actual relic registration')

        with patch.object(ITEMS, 'register_item', side_effect=fail_after_registration):
            self.rejected(lambda: RF.equip_relic(self.e, self.t, self.k, record['id']), 'injected failure after actual relic registration')
        RF.equip_relic(self.e, self.t, self.k, record['id'])
        self.assertEqual((source.save_mod, self.k.save_mod, self.t.spec['items'][record['id']]), (0, 2, 0))
        self.assertEqual(self.k.spec['relic_sources'][record['id']]['pokemon_id'], source.entity_id)
        self.restore('t', 'k')
        self.assertEqual(self.k.save_mod, 2)
        self.assertEqual(ITEMS.register_item(self.e, self.k, record['id']), 0)
        self.valid()

    def test_relic_crown_native_equipment_transfer_to_another_fossil_keeps_the_bonus_after_restore(self):
        source = self.restored('아마루스', 'crown source', pos=(7, 6))
        self.k = self.restored('두개도스', 'transferred holder', pos=(2, 2))
        identity = RFS.craft_relic(self.e, self.t, source, relic='hp', minutes=10)['id']
        RF.equip_relic(self.e, self.t, source, identity)
        selection = ITEMS.equipment_options(source, ('held',))[0]['key']
        result = ITEMS.transfer_equipment(self.e, source, self.k, selection)
        self.assertTrue(result['changed'])
        self.assertEqual((source.save_mod, self.k.save_mod), (0, 2))
        self.restore('t', 'k')
        self.assertEqual(self.k.save_mod, 2)
        self.assertEqual(ITEMS.register_item(self.e, self.k, identity), 0)
        self.valid()

    def test_another_fossil_holding_razors_uses_the_native_melee_hit_reaction(self):
        source = self.restored('방패톱스', 'razors source', pos=(3, 3))
        holder = self.restored('아마루스', 'razors holder', pos=(2, 2))
        identity = RFS.craft_relic(self.e, self.t, source, relic='def', minutes=10)['id']
        RF.equip_relic(self.e, self.t, source, identity)
        selection = ITEMS.equipment_options(source, ('held',))[0]['key']
        ITEMS.transfer_equipment(self.e, source, holder, selection)
        RFS.set_razors_reaction(self.e, source, True)
        RFS.set_razors_reaction(self.e, holder, True)
        foe = self.add('melee attacker', 'pokemon', (3, 2), side='foe', species='이브이',
                       level=5, types=['노말'], moves=['move/몸통박치기'], speed=15)
        self.combat(foe)
        before = foe.hp
        self.use(foe, source, 'move/몸통박치기', face=15)
        self.assertEqual(foe.hp, before)
        self.assertNotIn('researcher_relic_reactions', source.spec)
        self.next_turn(foe, count=15)
        self.use(foe, holder, 'move/몸통박치기', face=15)
        self.assertEqual(before - foe.hp, self.e.tick_loss(foe))
        self.assertEqual(holder.spec['researcher_relic_reactions'][-1]['relic'], identity)
        self.valid()

    def test_another_fossil_holding_a_sash_gets_two_evasion_on_the_native_status_move(self):
        source = self.restored('프테라', 'sash source', pos=(3, 3))
        holder = self.restored('두개도스', 'sash holder', pos=(1, 1))
        identity = RFS.craft_relic(self.e, self.t, source, relic='spe', minutes=10)['id']
        RF.equip_relic(self.e, self.t, source, identity)
        selection = ITEMS.equipment_options(source, ('held',))[0]['key']
        ITEMS.transfer_equipment(self.e, source, holder, selection)
        foe = self.add('status attacker', 'pokemon', (3, 2), side='foe', species='이브이',
                       level=5, types=['노말'], moves=['move/꼬리흔들기'], speed=15)
        self.combat(foe)
        control_threshold = self.rules.move('move/꼬리흔들기')['ac'] + source.evasion('변화')
        self.use(foe, source, 'move/꼬리흔들기', face=control_threshold)
        self.assertEqual(source.stages['def'], -1)
        # Tail Whip is a real Burst: keep the control recipient out of this
        # second native scope and introduce the sash holder only now.
        self.e.gm.set_position(holder,(2,2),reason='actual sash evasion recipient')
        self.e.gm.set_position(source,(6,3),reason='control outside later Burst')
        self.next_turn(foe, count=15)
        threshold = self.rules.move('move/꼬리흔들기')['ac'] + holder.evasion('변화') + 2
        self.use(foe, holder, 'move/꼬리흔들기', face=threshold - 1)
        self.assertEqual(holder.stages['def'], 0)
        self.next_turn(foe, count=15)
        self.use(foe, holder, 'move/꼬리흔들기', face=threshold)
        self.assertEqual(holder.stages['def'], -1)
        self.valid()


if __name__ == '__main__':
    unittest.main()
