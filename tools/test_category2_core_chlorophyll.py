"""Core Chlorophyll source, single CS authority, and native world/persistence checks."""
from copy import deepcopy
from pathlib import Path
import sys, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'engine')]
from engine import Rules, Engine, Combatant
import builder, core_weather_abilities as CW, state_grants as G
import combat_stage_sources as CS, turn as TURN, effects as FX

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT), ruleset='core')
    def setUp(self):
        self.e=Engine(self.rules,712)
        self.c=Combatant(self.rules,builder.build_pokemon(self.rules,'이상해씨',5,pos=(1,1)))
        self.e.gm.add_combatant(self.c)
        # Default construction offers a birth choice; observe that actual choice.
        self.e.choose_growth_ability(self.c,'creation','엽록소',reason='observed native birth Ability choice')
        self.e.gm.set_stat(self.c,'spe',value=10,reason='explicit effective-speed fixture')
    def sunny(self):self.e.gm.set_weather('sunny',rounds=1,reason='native weather observation')
    # The owner core_weather_abilities.refresh reads effects.effective_weather over the sourced
    # weather registry (weather_state), so these fixtures place and clear weather through
    # engine.gm.set_weather(..., rounds=None) instead of assigning engine.weather directly.

    def test_default_builder_ability_admits_actual_core_definition(self):
        self.assertIn('엽록소',self.c.abilities)
        self.assertEqual(self.rules.selection.resolve_name('엽록소',('ability/',)),CW.RULE)
        self.assertEqual(self.rules.selection.units[CW.RULE]['source']['lines'],[416,416])
        self.assertEqual(self.rules.core_abilities[CW.RULE]['official_source']['physical_pages'],[313,342])
        self.assertIs(vars(self.c)[CW.ENGINE_REF],self.e)
        self.assertEqual(self.c.stages['spe'],0)
        self.assertEqual(self.c.staged('spe'),10)

    def test_c05_010_abilities_and_move_identities_have_separate_native_consumers(self):
        import encounter
        moves=list(self.c.moves)
        usable=encounter.usable_moves(self.e,self.c)
        self.assertTrue(moves)
        for move in moves:
            self.assertEqual(self.rules.move(move)['id'],move)
            self.assertTrue(move.startswith('move/') or move=='struggle')
        self.assertNotIn('엽록소',moves)
        self.sunny();self.assertEqual(self.c.staged('spe'),18)
        G.replace_baseline(self.e,self.c,'abilities',[])
        self.assertEqual((self.c.moves,encounter.usable_moves(self.e,self.c)),(moves,usable))
        loaded=Engine.import_state(self.rules,self.e.export_state());actor=loaded.everyone[0]
        self.assertEqual((actor.abilities,actor.moves),([],moves))
        self.assertEqual(encounter.usable_moves(loaded,actor),usable)
        self.assertEqual(actor.staged('spe'),10)

    def test_weather_effect_and_round_expiry_change_same_public_stage(self):
        original=deepcopy(self.c.spec['stats'])
        FX.h_set_weather(self.e,self.c,self.c,{'weather':'sunny','rounds':1},{})
        self.assertEqual(self.c.staged('spe'),18)  # consumer first, before display refresh
        self.assertEqual(self.c.stages['spe'],4)
        self.assertIn('spe+4',repr(self.c))
        self.assertEqual(self.c.spec['stats'],original)
        self.assertEqual(self.c.stats['spe'],10)
        self.e.start_round([self.c]);self.assertEqual(self.e.weather,"sunny")
        self.e.end_round()
        self.assertIsNone(self.e.weather)
        CS.validate(self.c)  # source validation can be the first read after expiry
        self.assertEqual((self.c.stages['spe'],self.c.staged('spe')),(0,10))

    def test_suppression_and_unsuppression_are_immediate_in_display_and_consumer(self):
        self.sunny();self.assertEqual(self.c.stages['spe'],4)
        FX.h_suppress_ability(self.e,self.c,self.c,{}, {})
        self.assertEqual((self.c.stages['spe'],self.c.staged('spe')),(0,10))
        self.c.abilities_suppressed=False
        self.assertEqual((self.c.stages['spe'],self.c.staged('spe')),(4,18))
        self.assertNotIn(CW.GUARD,vars(self.c))

    def test_cap_and_capped_noop_do_not_turn_conditional_bonus_permanent(self):
        self.e.change_stage(self.c,'spe',5);self.sunny()
        self.assertEqual(self.c.stages['spe'],6)
        self.e.change_stage(self.c,'spe',1)
        self.e.gm.set_weather(None,rounds=None,reason='actual sourced weather clear for the conditional stage fixture')
        self.assertEqual(self.c.stages['spe'],5)
        self.e.gm.set_weather('sunny',rounds=None,reason='actual sourced sunny for the conditional stage fixture');self.assertEqual(self.c.stages['spe'],6)
        self.e.gm.set_weather('rain',rounds=None,reason='actual sourced rain for the conditional stage fixture');self.assertEqual(self.c.stages['spe'],5)
        CS.validate(self.c)

    def test_combat_and_base_sources_publish_one_snapshot_and_preserve_aliases(self):
        self.sunny();alias=self.c.stages
        self.e.change_stage(self.c,'spe',1)
        self.assertEqual(self.c.staged('spe'),20)
        self.assertIs(alias,self.c.stages)
        CS.add_base(self.c,'item/herbal','spe',1,source='item/herbal',ends='end')
        self.assertEqual(self.c.stages['spe'],6)
        CS.end_source(self.c,ends='end')
        self.assertEqual(self.c.stages['spe'],5)
        self.e.gm.set_weather(None,rounds=None,reason='actual sourced weather clear for the conditional stage fixture')
        self.assertEqual((self.c.stages['spe'],self.c.staged('spe')),(1,12))
        self.assertIs(alias,self.c.stages)
        CS.end_encounter(self.c)
        self.assertEqual(self.c.stages['spe'],0)

    def test_transition_uses_staged_world_and_reanchors_on_commit(self):
        self.sunny();self.assertEqual(self.c.stages['spe'],4)
        def apply(staged_engine,staged_actor):
            self.assertIs(vars(staged_actor)[CW.ENGINE_REF],staged_engine)
            staged_engine.gm.set_weather('rain',rounds=None,reason='actual sourced rain inside the staged world')
            self.assertEqual(staged_actor.staged('spe'),10)
            self.assertEqual(self.c.stages['spe'],4)
            return staged_actor
        self.assertIs(G.transition(self.e,self.c,apply),self.c)
        self.assertIs(vars(self.c)[CW.ENGINE_REF],self.e)
        self.assertEqual((self.e.weather,self.c.stages['spe']),('rain',0))

    def test_permanent_and_temporary_source_removal_does_not_leave_bonus(self):
        self.sunny();self.assertEqual(self.c.stages['spe'],4)
        G.replace_baseline(self.e,self.c,'abilities',[])
        self.assertEqual((self.c.stages['spe'],self.c.staged('spe')),(0,10))
        G.grant(self.c,'abilities','엽록소','grant/sun','gm',rule_id=CW.RULE)
        G.reconcile(self.e,self.c)
        self.assertEqual(self.c.stages['spe'],4)
        G.revoke(self.c,'grant/sun',engine=self.e)
        self.assertEqual((self.c.stages['spe'],self.c.staged('spe')),(0,10))
        self.assertNotIn(CW.KEY,self.c.spec[CS.STATE]['base'])

    def test_snapshot_and_durable_restore_bind_the_actual_restored_engine(self):
        self.sunny();self.assertEqual(self.c.stages['spe'],4)
        self.c.observed_stage_map=self.c.stages
        self.e.gm.snapshot('sunny')
        self.e.gm.set_weather(None,rounds=None,reason='actual sourced weather clear for the conditional stage fixture');self.assertEqual(self.c.stages['spe'],0)
        self.e.gm.restore('sunny')
        self.assertIs(vars(self.c)[CW.ENGINE_REF],self.e)
        self.assertEqual(self.c.stages['spe'],4)
        n=Engine.import_state(self.rules,self.e.export_state());c=n.everyone[0]
        self.assertIs(vars(c)[CW.ENGINE_REF],n)
        self.assertIs(c.observed_stage_map,c.stages)
        self.e.gm.set_weather(None,rounds=None,reason='actual sourced weather clear for the conditional stage fixture')
        self.assertEqual(c.stages['spe'],4)
        n.gm.set_weather(None,rounds=None,reason='actual sourced weather clear on the restored engine')
        self.assertEqual(c.stages['spe'],0)
        self.assertEqual(c.staged('spe'),10)
        self.assertNotIn(CW.GUARD,vars(c))

    def test_other_engine_registration_rejected_before_cross_world_weather_binding(self):
        other=Engine(self.rules,3);other.weather='sunny'
        with self.assertRaises(ValueError):other.register_abilities_one(self.c,'엽록소')
        self.assertIs(vars(self.c)[CW.ENGINE_REF],self.e)
        self.assertEqual(self.c.stages['spe'],0)

    def test_playtest_identity_is_separate_and_does_not_gain_core_stages(self):
        from ruleset import ExcludedRuleSelection
        with self.assertRaises(ExcludedRuleSelection):self.rules.selection.resolve('ability/엽록소-playtest')
        r=Rules(str(ROOT),ruleset='all')
        c=Combatant(r,dict(id='pokemon/playtest-only',name='Playtest',kind='pokemon',level=5,
            stats=dict(hp=8,atk=8,**{'def':8},spa=8,spd=8,spe=10),abilities=['엽록소 [Playtest]'],moves=[]))
        e=Engine(r,5);e.gm.add_combatant(c);e.weather='sunny'
        self.assertEqual(r.selection.resolve_name('엽록소 [Playtest]',('ability/',)),'ability/엽록소-playtest')
        self.assertEqual(c.stages['spe'],0)
        self.assertNotIn(CW.KEY,c.spec.get(CS.STATE,{}).get('base',{}))
        self.assertTrue(any(row.get('type')=='initiative_multiplier' and row.get('value')==2 for row in c.modifiers + c.registry))

if __name__=='__main__':unittest.main(verbosity=2)
