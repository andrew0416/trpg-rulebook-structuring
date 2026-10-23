"""Three reviewed ability baselines share ownership, caps, conditions and restores."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
import state_fields as F,state_grants as G,combat_stage_sources as CS,base_stage_abilities as B
import effects as FX,held_equipment as HELD,state_codec as CODEC

class BaseStageAbilityTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.core=Rules(str(ROOT),ruleset='core');cls.playtest=Rules(str(ROOT),ruleset='playtest')
 def setUp(self):self.r=self.playtest;self.e=Engine(self.r,49)
 def actor(self,abilities=(),kind='pokemon',initial=None):
  spec=dict(name='holder'+str(len(self.e.gm.everyone)),kind=kind,level=10,stats={s:10 for s in F.STATS},types=[],abilities=list(abilities),moves=[],size='Medium',pos=(1+len(self.e.gm.everyone),1))
  if initial:spec['initial_stages']=initial
  c=Combatant(self.r,spec);self.e.gm.add_combatant(c);return c
 def valid(self):self.assertTrue(self.e.validate_state()['valid'])
 def test_always_ability_keeps_benefit_and_penalty_without_activation_until_source_ends(self):
  import json
  for kind in ('trainer','pokemon'):
   with self.subTest(kind=kind):
    self.setUp();c=self.actor([],kind);c.spec['weight_class']=4
    G.replace_baseline(self.e,c,'abilities',['라이트메탈 [Playtest]'])
    self.assertEqual(self.r.ability_freq['라이트메탈 [Playtest]'],'항상')
    self.e.register_abilities(c)
    for _ in range(2):
     self.e.register_abilities(c)
     self.assertEqual((c.stats['spe'],c.stats['def'],c.weight_class),(12,8,2))
     self.assertFalse(c.move_uses)
    self.e.gm.snapshot('always-benefit-and-penalty')
    G.replace_baseline(self.e,c,'abilities',[])
    self.assertEqual((c.stats['spe'],c.stats['def'],c.weight_class),(10,10,4))
    self.e.gm.restore('always-benefit-and-penalty')
    self.assertEqual((c.stats['spe'],c.stats['def'],c.weight_class),(12,8,2))
    engine=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
    actual=next(a for a in engine.gm.everyone if a.entity_id==c.entity_id)
    self.assertEqual((actual.stats['spe'],actual.stats['def'],actual.weight_class),(12,8,2))
    G.replace_baseline(engine,actual,'abilities',[])
    self.assertEqual((actual.stats['spe'],actual.stats['def'],actual.weight_class),(10,10,4))
    self.assertTrue(engine.validate_state()['valid'])
 def test_core_ability_name_and_effect_resolve_one_source_through_restore_and_withdrawal(self):
  import json
  definition=next(row for row in json.loads((ROOT/'output/entities/abilities.json').read_text(encoding='utf-8-sig')) if row['id']=='ability/불요의검')
  self.assertEqual(definition['name'],'불요의검');self.assertIn('공격 전투단계 +1',definition['effect'])
  self.r=self.core;self.e=Engine(self.r,49);c=self.actor([definition['name'],definition['id']])
  self.assertEqual(c.stages['atk'],1);self.e.register_abilities_one(c,definition['id']);self.assertEqual(c.stages['atk'],1)
  saved=self.e.gm.snapshot('definition');G.replace_baseline(self.e,c,'abilities',[]);self.assertEqual(c.stages['atk'],0)
  self.e.gm.restore(saved);self.assertEqual(c.stages['atk'],1)
  loaded=Engine.import_state(self.r,json.loads(json.dumps(self.e.export_state())))
  actual=next(x for x in loaded.everyone if x.entity_id==c.entity_id);self.assertEqual(actual.stages['atk'],1)
  G.replace_baseline(loaded,actual,'abilities',[]);self.assertEqual(actual.stages['atk'],0);self.assertTrue(loaded.validate_state()['valid'])
 def test_all_three_sources_and_exact_duplicate_ids_register_once_for_both_roles(self):
  for kind in ('trainer','pokemon'):
   for names,stat,value in [(('불굴의방패','ability/불굴의방패-2'),'def',1),(('불요의검','ability/불요의검-2'),'atk',1),(('곡예 [Playtest]','ability/곡예-playtest-2'),'spe',2)]:
    with self.subTest(kind=kind,names=names):
     self.setUp();c=self.actor(names,kind);self.assertEqual(c.stages[stat],value)
     for _ in range(3):self.e.register_abilities(c);self.assertEqual(c.stages[stat],value)
     rows=[v for k,v in c.spec[CS.STATE]['base'].items() if k.startswith(B.PREFIX)];self.assertEqual(len(rows),1);self.valid()
 def test_ordinary_changes_haze_recall_and_encounter_reset_preserve_baselines(self):
  c=self.actor(['불굴의방패','불요의검']);self.e.change_stage(c,'atk',3);self.assertEqual(c.stages['atk'],4)
  effect=next(x for x in self.r.moves_mech['move/흑안개']['effects'] if x['type']=='reset_stages')
  FX.h_reset_stages(self.e,c,c,{**effect,'target':'self'},{});self.assertEqual((c.stages['atk'],c.stages['def']),(1,1))
  self.e.change_stage(c,'def',-3);self.e.gm.recall(c,reason='actual recall');self.assertEqual((c.stages['atk'],c.stages['def']),(1,1))
  self.e.change_stage(c,'atk',2);self.e.end_encounter([c]);self.assertEqual(c.stages['atk'],1);self.valid()
 def test_source_removal_at_cap_does_not_subtract_a_guessed_clamped_delta(self):
  c=self.actor(['불요의검'],initial={'atk':6});self.assertEqual(c.stages['atk'],6)
  G.replace_baseline(self.e,c,'abilities',[]);self.assertEqual(c.stages['atk'],6)
  G.replace_baseline(self.e,c,'abilities',['불요의검']);self.assertEqual(c.stages['atk'],6)
  self.e.change_stage(c,'atk',-2);self.assertEqual(c.stages['atk'],4)
  G.replace_baseline(self.e,c,'abilities',[]);self.assertEqual(c.stages['atk'],3);self.valid()
 def test_suppression_and_fainting_remove_only_active_ability_contributions(self):
  self.r=self.core;self.e=Engine(self.r,49)
  c=self.actor(['불굴의방패','불요의검']);self.e.apply_status(c,'화상');self.assertEqual((c.stages['atk'],c.stages['def']),(1,-1))
  FX.h_suppress_ability(self.e,c,c,{},{});self.assertEqual((c.stages['atk'],c.stages['def']),(0,-2))
  c.abilities_suppressed=False;self.assertEqual((c.stages['atk'],c.stages['def']),(1,-1))
  self.e.cure_status(c,'화상');self.e.gm.set_hp(c,value=0,reason='actual faint');self.assertEqual((c.stages['atk'],c.stages['def']),(0,0))
  self.e.gm.revive(c,hp=10,reason='explicit GM restoration');self.assertEqual((c.stages['atk'],c.stages['def']),(1,1));self.valid()
 def test_unburden_held_condition_uses_physical_equipment_not_item_effect_count(self):
  for kind in ('trainer','pokemon'):
   self.setUp();c=self.actor(['곡예 [Playtest]'],kind);self.assertEqual(c.stages['spe'],2)
   self.e.gm.set_item(c,'기합의띠',reason='actual held item');self.assertEqual(c.stages['spe'],0)
   self.e.change_stage(c,'spe',-1);self.e.gm.set_item(c,None,reason='held item removed');self.assertEqual(c.stages['spe'],1)
   self.e.gm.set_item(c,'기합의띠',reason='another actual equipment observation');self.assertEqual(c.stages['spe'],-1)
   self.e.end_encounter([c]);self.assertEqual(c.stages['spe'],0);self.e.gm.set_item(c,None,reason='empty hands');self.assertEqual(c.stages['spe'],2);self.valid()
  self.setUp();c=self.actor(['곡예 [Playtest]','배달부'])
  import world_entities as W,items as ITEMS
  for uid,name in [('first','선제공격손톱'),('second','예리한손톱')]:
   W.register_object(self.e,uid,location={'kind':'unknown'},reason='observed held instance',kind='item_instance',item_rule_id='item/'+name,owner_id=c.entity_id)
   ITEMS.equip_held(self.e,c,name,source_instance_id=uid);self.assertEqual(c.stages['spe'],0)
  self.assertEqual(len(HELD.entries(c)),2);self.valid()
 def test_multiple_ability_granters_share_one_baseline_until_last_source_is_lost(self):
  c=self.actor()
  for source in ('feature:first','feature:second'):
   G.grant(c,'abilities','불굴의방패',source,'feature',rule_id=source);G.reconcile(self.e,c)
  self.assertEqual(c.stages['def'],1)
  G.revoke(c,'feature:first',engine=self.e);self.assertEqual(c.stages['def'],1)
  G.revoke(c,'feature:second',engine=self.e);self.assertEqual(c.stages['def'],0);self.valid()
 def test_same_source_refresh_composes_with_weather_and_independent_base_penalties(self):
  self.r=self.core;self.e=Engine(self.r,49);c=self.actor(['엽록소','불요의검'])
  self.e.gm.set_weather('sunny',rounds=5,reason='actual sun');CS.add_base(c,'herbal-fixture','atk',-1,source='item/herbal',ends='extended_rest')
  self.assertEqual((c.stages['spe'],c.stages['atk']),(4,0))
  self.e.gm.set_weather(None,reason='actual source-owned weather clearing');self.assertEqual((c.stages['spe'],c.stages['atk']),(0,0))
  CS.end_source(c,ends='extended_rest');self.assertEqual(c.stages['atk'],1);self.valid()
 def test_core_profile_excludes_playtest_and_keeps_the_two_allowed_baselines(self):
  self.r=self.core;self.e=Engine(self.r,49);c=self.actor(['곡예 [Playtest]','불굴의방패','불요의검'])
  self.assertEqual((c.stages['spe'],c.stages['def'],c.stages['atk']),(0,1,1));self.valid()
 def test_gm_and_durable_restore_preserve_sources_then_follow_new_equipment_state(self):
  c=self.actor(['곡예 [Playtest]','불요의검']);self.e.change_stage(c,'spe',-1);snap=self.e.gm.snapshot('baseline')
  self.e.gm.set_item(c,'기합의띠',reason='actual held');self.assertEqual(c.stages['spe'],-1);self.e.gm.restore(snap);self.assertEqual(c.stages['spe'],1)
  e=Engine.import_state(self.r,self.e.export_state());a=next(x for x in e.everyone if x.entity_id==c.entity_id)
  self.assertEqual(a.spec[CS.STATE],c.spec[CS.STATE]);e.gm.set_item(a,'기합의띠',reason='restored actor now holds item');self.assertEqual(a.stages['spe'],-1)
  G.replace_baseline(e,a,'abilities',[]);self.assertEqual((a.stages['spe'],a.stages['atk']),(-1,0));self.assertTrue(e.validate_state()['valid'])
 def test_altered_source_record_and_untracked_direct_stage_write_are_rejected(self):
  c=self.actor(['불요의검']);saved=deepcopy(c.spec[CS.STATE]);key=B.PREFIX+'ability/불요의검'
  c.spec[CS.STATE]['base'][key]['deltas']['atk']=5
  with self.assertRaises(CODEC.StateCodecError):self.e.export_state()
  c.spec[CS.STATE]=saved;vars(c)['stages']['atk']=5
  with self.assertRaises(ValueError):CS.validate(c)

if __name__=='__main__':unittest.main()
