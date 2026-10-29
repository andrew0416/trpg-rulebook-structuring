"""Exact target-weather and represented native airborne predicates for Thunder.

Unrepresented Bounce/Sky Drop phases remain unknown; these tests do not claim
that their missing native movement producers have been implemented.
"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import effect_contracts as CONTRACTS
import effects_ext as EXT
import movement_actions as MOVEMENT
import state_codec as CODEC
import world_entities as WORLD
import test_category2_setup_move_state as SETUP_FIX
import test_csv_main113_weather_boundaries as WEATHER_FIX

AIRBORNE='target airborne (뛰어오르기/공중날기/프리폴)'


class ProceduralPredicateTests(unittest.TestCase):
    setUpClass=classmethod(SETUP_FIX.SetupMoveStateTests.setUpClass.__func__)
    setUp=SETUP_FIX.SetupMoveStateTests.setUp
    next_turn=SETUP_FIX.SetupMoveStateTests.next_turn

    def context(self,actor,target):
        move=self.e.r.move('move/번개')
        return {'attacker':actor,'target':target,'move':move,'source_id':move['id'],
                'engine':self.e,'hit':True,'nat':2}

    def test_thunder_target_sun_and_rain_do_not_borrow_attacker_local_weather(self):
        WEATHER_FIX.WeatherBoundaryTests.equip(self,self.e,self.b,'item/만능우산',
                                             'predicate/target-umbrella')
        move=self.e.r.move('move/번개');mechanics,_=self.e.r.move_mech(move['id'])
        for weather,text in (('sunny','target in sunny weather'),('rain','target in rain weather')):
            with self.subTest(weather=weather):
                self.e.gm.set_weather(weather,rounds=None,reason='actual sourced weather for target-local Thunder')
                covered=self.context(self.a,self.b);exposed=self.context(self.b,self.a)
                self.assertFalse(CONTRACTS.condition_text(self.e,self.a,self.b,text,covered))
                self.assertFalse(EXT._eval_cond(self.e,self.a,self.b,text,covered))
                self.assertTrue(CONTRACTS.condition_text(self.e,self.b,self.a,text,exposed))
                self.assertTrue(EXT._eval_cond(self.e,self.b,self.a,text,exposed))
                covered_result=EXT.accuracy_hook(self.e,self.a,self.b,move,mechanics,covered)
                exposed_result=EXT.accuracy_hook(self.e,self.b,self.a,move,mechanics,exposed)
                if weather=='sunny':
                    self.assertIsNone(covered_result[0]);self.assertEqual(exposed_result[0],11)
                else:
                    self.assertFalse(covered_result[3]);self.assertTrue(exposed_result[3])
                    self.assertFalse(self.e.accuracy_check(self.a,self.b,move,fixed_roll=2)[0])
                    self.assertTrue(self.e.accuracy_check(self.b,self.a,move,fixed_roll=2)[0])

    def test_real_fly_preparation_cold_restore_and_descent_bound_airborne_predicate(self):
        self.e.gm.observe_natural_weather('clear without a weather effect',reason='known ordinary battlefield')
        self.assertGreater(MOVEMENT.capabilities(self.e,self.a)['sky'],0)
        self.assertFalse(CONTRACTS.condition_text(self.e,self.b,self.a,AIRBORNE,self.context(self.b,self.a)))
        self.assertEqual(self.e.use_setup_move_on(self.a,self.b,SETUP_FIX.FLY,
                         self.e.everyone,setup_options={}),0)
        self.assertTrue(CONTRACTS.condition_text(self.e,self.b,self.a,AIRBORNE,self.context(self.b,self.a)))
        ids=(self.a.entity_id,self.b.entity_id)
        saved=json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False))
        self.e=CODEC.load_engine(self.r,saved)
        index=WORLD.actor_index(self.e);self.a,self.b=(index[identity] for identity in ids)
        self.assertTrue(CONTRACTS.condition_text(self.e,self.b,self.a,AIRBORNE,self.context(self.b,self.a)))
        self.assertTrue(CONTRACTS.never_miss_allowed(self.e,self.b,self.a,
                        {'type':'never_miss','if':AIRBORNE},self.context(self.b,self.a)))
        self.next_turn()
        with patch.object(self.e,'d20',return_value=10):
            self.e.use_setup_move_on(self.a,self.b,SETUP_FIX.FLY,self.e.everyone,
                setup_options={'path':[{'position':(3,2),'altitude':25},{'position':(4,2),'altitude':25}]})
        self.assertFalse(self.a.airborne)
        self.assertFalse(CONTRACTS.condition_text(self.e,self.b,self.a,AIRBORNE,self.context(self.b,self.a)))
        self.assertEqual(self.a.move_uses[SETUP_FIX.FLY],1)

    def test_fickle_exact_readers_keep_unknown_history_read_only(self):
        text='target hit user super-effectively since last turn'
        move=self.e.r.move('move/변덕레이저')
        context={'attacker':self.a,'target':self.b,'move':move,'source_id':move['id'],'engine':self.e}
        before=deepcopy(self.a.spec),self.e.rng.getstate()
        # Only the first actual own turn exists; no prior-own-start coverage is
        # invented by either predicate consumer. Native positive history is
        # exercised in its owner's tests and the actual procedural Fickle hit.
        self.assertIsNone(CONTRACTS.condition_text(self.e,self.a,self.b,text,context))
        self.assertIsNone(EXT._eval_cond(self.e,self.a,self.b,text,context))
        self.assertEqual((self.a.spec,self.e.rng.getstate()),before)

    def test_bare_legacy_airborne_move_markers_do_not_create_phase_or_false_certainty(self):
        self.e.gm.set_move(self.a,'move/프리폴',reason='actual known Move is not a physical preparation')
        for identity in (SETUP_FIX.FLY,'move/뛰어오르기','move/프리폴'):
            with self.subTest(move=identity):
                self.a.setup_move=identity  # Deliberately incomplete legacy input, not a native grant.
                try:
                    self.assertIsNone(CONTRACTS.condition_text(self.e,self.b,self.a,AIRBORNE,self.context(self.b,self.a)))
                    with self.assertRaises(CONTRACTS.EffectContractError):
                        CONTRACTS.never_miss_allowed(self.e,self.b,self.a,
                            {'type':'never_miss','if':AIRBORNE},self.context(self.b,self.a))
                finally:self.a.setup_move=None


if __name__=='__main__':unittest.main()
