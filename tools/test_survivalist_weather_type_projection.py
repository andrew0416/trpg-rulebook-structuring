"""U-012 actual Guide suppression retains owned Forecast/Mimicry choices."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
import ability_state_projection as P
import ability_transitions as A
import book_survivalist_fixture as FIX
import state_grants as G
import survivalist_class as SC
import trainer_feature_acquisition as ACQUIRE

FORECAST='ability/기분파'
MIMICRY='ability/의태'


class WeatherTypeProjectionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')

 def setUp(self):
  previous=self.rules.rulings
  self.rules.rulings=deepcopy(previous)
  self.addCleanup(setattr,self.rules,'rulings',previous)

 def world(self,source,*,weather='sunny'):
  w=FIX.scene(self.rules,feats=(SC.CLASS,SC.NATURAL,SC.TRAPPER))
  e,a,foe=(w[k] for k in ('engine','trainer','foe'))
  ACQUIRE.acquire_static(e,a,SC.GUIDE,acquisition_request_id='weather-types/guide',selection={'edition':'csv_hb'})
  FIX.env(e,a,'desert');FIX.env(e,w['partner'],'desert')
  e.gm.set_types(foe,['전기'],reason='actual baseline independent of weather')
  G.grant(foe,'abilities',source,'gm/weather-type-ability','gm',rule_id=source)
  G.reconcile(e,foe)
  e.gm.set_weather(weather,rounds=None,reason='actual persistent battlefield weather')
  return e,a,foe

 def guide(self,e,a):
  FIX.battle(e,a)
  return e.survivalist_activity(a,'wilderness_guide',reason='actual desert Guide Order')

 def expire(self,e,a):
  e.end_of_turn(a);e.end_round();e.start_round(e.everyone)
  e.at_initiative_count(21)
  e.at_initiative_count(20)

 def mimic(self,e,c,choice,environment='숲',gm_options=None):
  obs={'environment':environment,'fact':{'source':'test/observed-environment','reason':'actual observed field'}}
  if gm_options is not None:obs['gm_options']=gm_options
  return e.activate_ability_state(c,MIMICRY,choice=choice,observation=obs,reason='actual field type choice')

 def test_forecast_hides_without_deleting_choice_and_cold_restore_expires_at_same_count(self):
  e,a,c=self.world(FORECAST)
  chosen=deepcopy(c.spec[P.KEY][FORECAST]);learned=deepcopy(c.abilities)
  operation=deepcopy(c.spec[G.KEY]['type_sources']['sources'])
  self.assertEqual((c.types,c.form),(['불꽃'],'기분파/불꽃'))
  receipt=self.guide(e,a)
  self.assertIn(c.entity_id,receipt['weather_targets'])
  self.assertEqual(c.types,['전기']);self.assertNotEqual(c.form,'기분파/불꽃')
  self.assertEqual((c.spec[P.KEY][FORECAST],c.abilities),(chosen,learned))
  self.assertEqual(c.spec[G.KEY]['type_sources']['sources'],operation)
  self.assertTrue(A.active(c,FORECAST));self.assertTrue(e.validate_state()['valid'])
  loaded,index=FIX.restore(self.rules,e);enemy=index[c.entity_id];trainer=index[a.entity_id]
  self.assertEqual((enemy.types,enemy.spec[P.KEY][FORECAST]),(['전기'],chosen))
  loaded.end_of_turn(trainer);loaded.end_round();loaded.start_round(loaded.everyone)
  loaded.at_initiative_count(21);self.assertEqual(enemy.types,['전기'])
  loaded.at_initiative_count(20)
  self.assertEqual((enemy.types,enemy.form),(['불꽃'],'기분파/불꽃'))
  self.assertEqual(enemy.spec[P.KEY][FORECAST],chosen)
  self.assertTrue(loaded.validate_state()['valid'])

 def test_later_source_layers_and_new_baseline_survive_hide_restore_and_revoke(self):
  e,a,c=self.world(FORECAST)
  G.type_operation(c,'add',['고스트'],'test/later-add')
  order=list(c.spec[G.KEY]['type_sources']['sources'])
  self.assertEqual(c.types,['불꽃','고스트'])
  self.guide(e,a)
  self.assertEqual(c.types,['전기','고스트'])
  e.gm.set_types(c,['풀'],reason='legitimate baseline change while weather effect is hidden')
  self.assertEqual(c.types,['풀','고스트'])
  G.type_operation(c,'set',['물'],'test/later-set')
  chosen=deepcopy(c.spec[P.KEY][FORECAST])
  self.expire(e,a)
  self.assertEqual(c.types,['물'])
  self.assertEqual(list(c.spec[G.KEY]['type_sources']['sources']),order+['test/later-set'])
  self.assertEqual(c.spec[P.KEY][FORECAST],chosen)
  G.remove_owned(e,c,'test/later-set');self.assertEqual(c.types,['불꽃','고스트'])
  G.revoke(c,'gm/weather-type-ability',engine=e);G.reconcile(e,c)
  self.assertEqual(c.types,['풀','고스트'])
  self.assertNotIn(FORECAST,c.spec[P.KEY]);self.assertTrue(e.validate_state()['valid'])

 def test_forecast_tracks_weather_during_suppression_and_none_stays_nonweather(self):
  e,a,c=self.world(FORECAST)
  self.guide(e,a)
  e.gm.set_weather('rain',rounds=None,reason='actual weather changed during Guide')
  self.assertEqual((c.types,c.spec[P.KEY][FORECAST]['choice']),(['전기'],'물'))
  loaded,index=FIX.restore(self.rules,e)
  self.expire(loaded,index[a.entity_id])
  self.assertEqual(index[c.entity_id].types,['물'])
  self.assertTrue(loaded.validate_state()['valid'])
  e.gm.set_weather(None,reason='actual weather ended during Guide')
  self.assertEqual((c.types,c.spec[P.KEY][FORECAST]['choice']),(['노말'],'노말'))
  self.assertTrue(SC.weather_ability_suppressed(e,c,FORECAST))
  self.assertTrue(e.validate_state()['valid'])

 def test_forecast_keeps_independent_chosen_weather_when_primary_weather_changes(self):
  e,a,c=self.world(FORECAST)
  observed={'weather_effects':[
   {'weather':'sunny','source':'engine/weather-state','reason':'actual primary weather'},
   {'weather':'rain','source':'test/independent-rain','reason':'separately observed active rain'}]}
  e.activate_ability_state(c,FORECAST,choice='물',observation=observed,reason='choose actual independent rain')
  chosen=deepcopy(c.spec[P.KEY][FORECAST])
  self.guide(e,a)
  self.assertEqual((c.types,c.spec[P.KEY][FORECAST]),(['전기'],chosen))
  e.gm.set_weather('hail',rounds=None,reason='only primary weather changed')
  current=c.spec[P.KEY][FORECAST]
  self.assertEqual((c.types,current['choice']),(['전기'],'물'))
  self.assertIn(observed['weather_effects'][1],current['observation']['weather_effects'])
  loaded,index=FIX.restore(self.rules,e)
  self.expire(loaded,index[a.entity_id])
  self.assertEqual(index[c.entity_id].types,['물'])
  self.assertTrue(loaded.validate_state()['valid'])
 def test_mimicry_weather_choice_hides_but_terrain_and_gm_overlap_remain(self):
  cases=(('불꽃','숲',None,True),('풀','숲',None,False),
         ('불꽃','숲',['불꽃'],False),('물','민물',None,False),('물','rain',None,True))
  for choice,environment,extra,hidden in cases:
   with self.subTest(choice=choice,environment=environment,gm_options=extra):
    e,a,c=self.world(MIMICRY,weather='rain' if choice=='물' else 'sunny')
    self.mimic(e,c,choice,environment,extra)
    chosen=deepcopy(c.spec[P.KEY][MIMICRY])
    self.guide(e,a)
    self.assertEqual(c.types,['전기'] if hidden else [choice])
    self.assertEqual(c.spec[P.KEY][MIMICRY],chosen)
    loaded,index=FIX.restore(self.rules,e);enemy=index[c.entity_id]
    self.assertEqual(enemy.types,['전기'] if hidden else [choice])
    self.expire(loaded,index[a.entity_id])
    self.assertEqual((enemy.types,enemy.spec[P.KEY][MIMICRY]),([choice],chosen))
    self.assertTrue(loaded.validate_state()['valid'])

 def test_mimicry_scene_choice_survives_weather_change_then_ends_at_scene(self):
  e,a,c=self.world(MIMICRY)
  self.mimic(e,c,'불꽃');chosen=deepcopy(c.spec[P.KEY][MIMICRY])
  self.guide(e,a)
  e.gm.set_weather('rain',rounds=None,reason='scene continues after selection weather changed')
  self.assertEqual(c.types,['전기']);self.assertEqual(c.spec[P.KEY][MIMICRY],chosen)
  loaded,index=FIX.restore(self.rules,e);enemy=index[c.entity_id]
  self.expire(loaded,index[a.entity_id]);self.assertEqual(enemy.types,['불꽃'])
  loaded.end_scene(round_elapsed_seconds=10)
  self.assertEqual(enemy.types,['전기']);self.assertNotIn(MIMICRY,enemy.spec[P.KEY])
  self.assertTrue(loaded.validate_state()['valid'])

 def test_actual_ability_loss_during_suppression_never_resurrects_projection(self):
  for source in (FORECAST,MIMICRY):
   with self.subTest(source=source):
    e,a,c=self.world(source)
    if source==MIMICRY:self.mimic(e,c,'불꽃')
    self.guide(e,a)
    G.revoke(c,'gm/weather-type-ability',engine=e);G.reconcile(e,c)
    self.assertFalse(A.active(c,source));self.assertNotIn(source,c.spec[P.KEY])
    self.assertEqual(c.types,['전기'])
    loaded,index=FIX.restore(self.rules,e)
    self.expire(loaded,index[a.entity_id])
    self.assertEqual(index[c.entity_id].types,['전기'])
    self.assertNotIn(source,index[c.entity_id].spec[P.KEY])
    self.assertTrue(loaded.validate_state()['valid'])

 def test_forged_type_suppression_is_rejected_without_a_guide_marker(self):
  e,a,c=self.world(FORECAST)
  row=c.spec[G.KEY]['type_sources']
  row['suppressed']=[P.PREFIX+FORECAST]
  G._render_types(c,row)
  import type_state as TYPES
  with self.assertRaisesRegex(ValueError,'suppression differs'):
   TYPES.validate_actor(c)

 def test_mimicry_rejects_added_or_replaced_saved_candidates_without_observed_weather(self):
  for candidates in (['물','풀'],['물']):
   with self.subTest(candidates=candidates):
    e,a,c=self.world(MIMICRY,weather=None)
    self.mimic(e,c,'풀')
    c.spec[P.KEY][MIMICRY]['observation']['candidates']=candidates
    with self.assertRaisesRegex(ValueError,'stored Mimicry candidates changed'):
     P.validate_world(e,{c.entity_id:c})

 def test_mimicry_consistent_rewrite_cannot_replace_native_selection_weather(self):
  e,a,c=self.world(MIMICRY,weather=None)
  self.mimic(e,c,'풀')
  row=c.spec[P.KEY][MIMICRY]
  row['choice']='물';row['payload']=deepcopy(P.definition(self.rules,MIMICRY)['choices']['물'])
  row['observation']['candidates']=['물','풀']
  row['observation']['weather_observation']['weather']='rain'
  owned=c.spec[G.KEY]['type_sources'];owned['sources'][P.PREFIX+MIMICRY]['values']=['물']
  G._render_types(c,owned)
  with self.assertRaisesRegex(ValueError,'Mimicry observation differs from its native selection producer'):
   P.validate_world(e,{c.entity_id:c})
  with self.assertRaises(ValueError):
   FIX.restore(self.rules,e)

 def test_legacy_mimicry_retains_only_independently_proven_field_options(self):
  e,a,c=self.world(MIMICRY,weather=None)
  self.mimic(e,c,'풀')
  row=c.spec[P.KEY][MIMICRY]
  row['observation'].pop('weather_observation')
  c.spec[G.KEY]['sources'][P.PREFIX+MIMICRY].pop('field_observation')
  self.assertTrue(P.validate_world(e,{c.entity_id:c}))
  loaded,index=FIX.restore(self.rules,e)
  self.assertEqual(index[c.entity_id].types,['풀'])
  row['observation']['candidates']=['물','풀']
  with self.assertRaisesRegex(ValueError,'stored Mimicry candidates changed'):
   P.validate_world(e,{c.entity_id:c})

 def test_custom_mega_forecast_survives_real_guide_restore_expiry_and_scene_end(self):
  from engine import Combatant
  import items as ITEMS,world_entities as WORLD,mega_forms as MEGA
  e,a,_=self.world(MIMICRY)
  trainer=Combatant(self.rules,FIX.trainer_spec(self.rules,'opposing Mega trainer'))
  e.gm.add_combatant(trainer,pos=(9,3),side='wild',reason='actual opposing Trainer')
  c=Combatant(self.rules,FIX.pokemon_spec(self.rules,trainer,'Mega Forecast bearer'))
  e.gm.add_combatant(c,pos=(8,3),side='wild',reason='actual opposing owned Pokemon')
  for holder,uid,item in ((trainer,'weather-mega-ring','메가링'),(c,'weather-mega-stone','메가스톤')):
   WORLD.register_object(e,uid,kind='item_instance',item_rule_id=self.rules.item_effects(item)[1]['id'],
    owner_id=holder.entity_id,location={'kind':'unknown'},reason='actual inspected equipment')
   ITEMS.register_item(e,holder,item,source_instance_id=uid)
  form='mega/weather-projection-test'
  e.gm.define_mega_form(form,base_species='이브이',stat_changes={'atk':10},ability='기분파',types=['전기'],reason='actual custom Mega granting Forecast')
  e.gm.bind_mega_stone('weather-mega-stone',form,reason='actual custom stone affinity')
  FIX.battle(e,trainer,count=21)
  receipt=e.mega_evolve(trainer,c,form,ring='weather-mega-ring',stone='weather-mega-stone')
  sid=receipt['grant_source']
  self.assertEqual((c.types,c.form),(['불꽃'],'기분파/불꽃'))
  type_order=list(c.spec[G.KEY]['type_sources']['sources'])
  form_order=list(c.spec[G.KEY]['scalar_sources']['form']['sources'])
  e.end_of_turn(trainer);e.start_of_turn(a,initiative_count=20)
  e.survivalist_activity(a,'wilderness_guide',reason='actual desert Guide Order')
  self.assertEqual((c.types,c.form),(['전기'],form))
  self.assertIn(sid,c.spec[G.KEY]['sources'])
  self.assertTrue(e.validate_state()['valid'])
  loaded,index=FIX.restore(self.rules,e);enemy=index[c.entity_id]
  self.assertEqual((enemy.types,enemy.form),(['전기'],form))
  self.assertEqual(list(enemy.spec[G.KEY]['type_sources']['sources']),type_order)
  self.assertEqual(list(enemy.spec[G.KEY]['scalar_sources']['form']['sources']),form_order)
  self.expire(loaded,index[a.entity_id])
  self.assertEqual((enemy.types,enemy.form),(['불꽃'],'기분파/불꽃'))
  self.assertTrue(loaded.validate_state()['valid'])
  loaded.end_scene(round_elapsed_seconds=10)
  self.assertNotIn(MEGA.KEY,enemy.spec)
  self.assertNotIn(FORECAST,enemy.spec[P.KEY])
  self.assertNotIn(sid,enemy.spec[G.KEY]['sources'])
  self.assertTrue(loaded.validate_state()['valid'])

if __name__=='__main__':unittest.main()