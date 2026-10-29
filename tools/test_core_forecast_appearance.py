"""C10-410's missing appearance connection over the existing Forecast owner."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT=Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_ability_state_projection as fixture
import ability_state_projection as P
import ability_transitions as A
import state_grants as G
import items as ITEMS
import world_entities as WORLD
from engine import Engine,Rules

SOURCE='ability/기분파'


class ForecastAppearanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=Rules(ROOT,ruleset='all')

    engine=fixture.AbilityStateProjectionTests.engine
    actor=fixture.AbilityStateProjectionTests.actor

    def projection(self,c,chosen):
        self.assertEqual(c.types,[chosen])
        self.assertEqual(c.form,'기분파/'+chosen)
        record=c.spec[P.KEY][SOURCE]
        self.assertEqual(record['choice'],chosen)
        self.assertEqual(record['payload'],{'form':'기분파/'+chosen,'types':[chosen]})
        self.assertEqual(c.spec[G.KEY]['scalar_sources']['form']['sources'][record['grant_source']],c.form)

    def test_actual_four_weather_moves_publish_form_and_type_without_capability_conflation(self):
        e=self.engine()
        moves=['move/쾌청','move/비바라기','move/싸라기눈','move/모래바람']
        c=self.actor(e,SOURCE,species='캐스퐁',moves=moves)
        baseline=deepcopy((c.stats,c.stages,c.hp,c.spec['stats'],c.spec['species']))
        source=self.r.ability_state_projection_policy['sources'][SOURCE]
        self.assertEqual(source['appearance_source']['clause_id'],'C10-410')
        self.assertTrue(source['appearance_source']['identity_only'])
        self.assertEqual(source['row_id'],'C2CSV-ABILITY-R0041')
        for move,weather,chosen,color in [
            ('move/쾌청','sunny','불꽃','orange'),
            ('move/비바라기','rain','물','blue and grey'),
            ('move/싸라기눈','hail','얼음','light blue'),
            ('move/모래바람','sandstorm','바위','rocky brown'),
        ]:
            with self.subTest(weather=weather):
                if e._active_turn_actor is not None:e.end_of_turn(e._active_turn_actor)
                e.start_round(e.everyone);e.start_of_turn(c,initiative_count=20)
                e.use_move(c,c,move)
                self.projection(c,chosen)
                view=e.capability_traits(c)['weathershape_appearance']
                self.assertEqual((view['source'],view['weather'],view['appearance']),('capability/날씨-형상',weather,color))
                self.assertEqual((c.stats,c.stages,c.hp,c.spec['stats'],c.spec['species']),baseline)
                self.assertEqual(e._weather_state['active']['source_id'],move)
        e.gm.set_weather(None,reason='actual weather ends')
        self.projection(c,'노말')
        G.grant(c,'capabilities','날씨 형상','test:independent-weathershape','independent capability owner')
        G.revoke(c,'test:independent-weathershape',engine=e)
        self.projection(c,'노말')
        self.assertTrue(e.validate_state()['valid'])

    def test_independent_weather_choice_keeps_same_form_through_refresh_end_and_generic_reconcile(self):
        for independent,chosen in [('rain','물'),('sunny','불꽃')]:
            with self.subTest(independent=independent):
                e=self.engine();c=self.actor(e,SOURCE)
                e.gm.set_weather('sunny',reason='actual primary sunlight')
                facts={'weather_effects':[
                    {'weather':'sunny','source':'gm/primary','reason':'actual primary sunlight'},
                    {'weather':independent,'source':'gm/local','reason':'separately observed active weather'},
                ]}
                e.activate_ability_state(c,SOURCE,choice=chosen,observation=facts,reason='choose actual independent weather')
                prior=deepcopy(c.spec[P.KEY][SOURCE])
                e.gm.set_move(c,'move/울음소리',reason='unrelated actual learned move')
                self.assertEqual(c.spec[P.KEY][SOURCE],prior)
                e.gm.set_weather('sunny',rounds=8,reason='refresh only primary weather')
                e.gm.set_weather(None,reason='only primary weather ends')
                self.projection(c,chosen)
                n=Engine.import_state(self.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
                restored=next(x for x in n.everyone if x.entity_id==c.entity_id)
                self.projection(restored,chosen)
                n.activate_ability_state(restored,SOURCE,choice='노말',observation={'weather_effects':[
                    {'weather':'none','source':'gm/local-end','reason':'independent weather actually ended too'},
                ]},reason='observe independent weather end')
                self.projection(restored,'노말')

    def test_native_source_loss_and_reacquisition_restore_owned_form_and_type(self):
        e=self.engine();c=self.actor(e,'ability/멀티타입')
        original_types=list(c.types)
        G._source(c,'test:independent-form','feature',rule_id='combat/struggle')
        G.scalar(c,'form','observed original appearance','test:independent-form')
        e.gm.set_weather('rain',reason='actual rain before acquiring Forecast')
        e.gm.set_ability(c,SOURCE,reason='actual Forecast acquisition')
        self.projection(c,'물')
        e.gm.set_ability(c,SOURCE,add=False,reason='actual Forecast source loss')
        self.assertEqual((c.types,c.form),(original_types,'observed original appearance'))
        self.assertNotIn(SOURCE,c.spec[P.KEY])
        self.assertNotIn('ability-state:'+SOURCE,c.spec[G.KEY]['sources'])
        self.assertIn('test:independent-form',c.spec[G.KEY]['sources'])
        e.gm.set_weather('sunny',reason='weather changes after Forecast source loss')
        self.assertEqual((c.types,c.form),(original_types,'observed original appearance'))
        e.gm.set_ability(c,SOURCE,reason='actual reacquisition in current sunlight')
        self.projection(c,'불꽃')
        self.assertTrue(e.validate_state()['valid'])

    def test_actual_selected_suppress_move_withdraws_and_native_end_reapplies_current_weather(self):
        e=self.engine(5);c=self.actor(e,'ability/멀티타입',pos=(3,2))
        original_types=list(c.types);original_form=c.form
        e.gm.set_ability(c,SOURCE,reason='actual acquired Forecast beside independent Multitype')
        attacker=self.actor(e,'ability/멀티타입',name='actual suppressing actor',moves=['move/위액'],pos=(2,2))
        e.gm.set_weather('rain',reason='actual rain')
        self.projection(c,'물');e.gm.snapshot('before actual suppression')
        e.start_round(e.everyone);e.start_of_turn(attacker,initiative_count=20)
        e.gm.choose_ability_transition(attacker,c,'move/위액',ability=SOURCE,reason='suppress only actual Forecast source')
        e.use_move(attacker,c,'move/위액')
        self.assertFalse(c.abilities_suppressed)
        self.assertFalse(A.active(c,SOURCE))
        self.assertEqual((c.types,c.form),(original_types,original_form))
        self.assertNotIn(SOURCE,c.spec[P.KEY])
        n=Engine.import_state(self.r,e.export_state())
        suppressed=next(x for x in n.everyone if x.entity_id==c.entity_id)
        self.assertFalse(suppressed.abilities_suppressed)
        self.assertEqual((suppressed.types,suppressed.form),(original_types,original_form))
        n.end_of_turn(n._active_turn_actor)
        n.end_encounter(n.everyone,round_elapsed_seconds=0)
        self.projection(suppressed,'물')
        e.gm.restore('before actual suppression',reason='existing native state restore removes suppression')
        self.assertFalse(c.abilities_suppressed);self.projection(c,'물')
        e.gm.set_weather('sunny',reason='actual later sunlight')
        self.projection(c,'불꽃')

    def test_actor_local_umbrella_masks_form_with_type_and_withdrawal_restores_both(self):
        e=self.engine();c=self.actor(e,SOURCE,species='캐스퐁')
        e.gm.set_weather('rain',reason='actual sourced global rain')
        self.projection(c,'물');occurrence=e._weather_state['active']['id']
        uid='test:forecast:actual-umbrella'
        WORLD.register_object(e,uid,location={'kind':'unknown'},reason='actual owned Umbrella',
            kind='item_instance',item_rule_id='item/만능우산',owner_id=c.entity_id)
        ITEMS.register_item(e,c,'item/만능우산',source_instance_id=uid)
        self.projection(c,'노말')
        self.assertEqual((e.weather,e._weather_state['active']['id']),('rain',occurrence))
        self.assertIsNone(e.capability_traits(c)['weathershape_appearance']['appearance'])
        restored=Engine.import_state(self.r,e.export_state())
        self.projection(next(x for x in restored.everyone if x.entity_id==c.entity_id),'노말')
        ITEMS.unregister_item(e,c,'item/만능우산')
        self.projection(c,'물')

    def test_form_and_payload_tampering_rejects_and_invalid_choice_is_atomic(self):
        e=self.engine();c=self.actor(e,SOURCE)
        e.gm.set_weather('rain',reason='actual rain')
        saved=e.export_state()
        with self.assertRaises(ValueError):e.activate_ability_state(c,SOURCE,choice='불꽃',reason='unavailable weather choice')
        self.assertEqual(e.export_state(),saved)
        for channel in ('visible','payload','owned_scalar'):
            with self.subTest(channel=channel):
                n=Engine.import_state(self.r,saved);other=next(x for x in n.everyone if x.entity_id==c.entity_id)
                if channel=='visible':other.form='invented appearance'
                elif channel=='payload':other.spec[P.KEY][SOURCE]['payload']['form']='invented appearance'
                else:other.spec[G.KEY]['scalar_sources']['form']['sources']['ability-state:'+SOURCE]='invented appearance'
                with self.assertRaises(Exception):n.export_state()

    def test_unrelated_grant_reconciliation_does_not_resolve_forecast_or_mutate_other_projection(self):
        e=self.engine();c=self.actor(e,'ability/멀티타입')
        e.activate_ability_state(c,'ability/멀티타입',choice='전기',reason='existing different source projection')
        prior=deepcopy(c.spec[P.KEY]);selected=self.r._selected_rule
        def restricted(uid):
            if uid==SOURCE:raise AssertionError('unrelated actor must not resolve Forecast source policy')
            return selected(uid)
        with patch.object(self.r,'_selected_rule',side_effect=restricted):
            e.gm.set_move(c,'move/울음소리',reason='actual unrelated move acquisition')
        self.assertEqual(c.spec[P.KEY],prior)
        self.assertEqual(c.types,['전기']);self.assertIsNone(c.form)
        self.assertTrue(e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
