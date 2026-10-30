"""R755/R756 use the existing whole Survivalist owner and actual acquired parents.

Only source differences and their real consumers are asserted here. The unchanged
Book suite and R754 producer retain their own shared obligation evidence.
"""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Combatant,Engine
from native_scenario_fixture import assert_rejected_unchanged
import book_survivalist_fixture as FIX
import combat_timing as TIME
import environ_moves as ENV
import frequency as FREQ
import movement_actions as MOVE
import state_grants as GRANTS
import survivalist_class as SC
import survivalist_features as V
import trainer_feature_acquisition as ACQUIRE
import trainer_retraining as RETRAIN


class SurvivalistHBTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')

 def setUp(self):
  previous=self.rules.rulings
  self.rules.rulings=deepcopy(previous)
  self.addCleanup(setattr,self.rules,'rulings',previous)

 def acquire(self,e,a,feature,*,edition='csv_hb',request=None):
  return ACQUIRE.acquire_static(e,a,feature,acquisition_request_id=request or 'hb/'+a.entity_id+'/'+feature,selection={'edition':edition})

 def world(self,*,adaptive=False,ally=False,terrains=('forest',),foe_moves=None):
  w=FIX.scene(self.rules,feats=(SC.CLASS,SC.NATURAL,SC.TRAPPER),ally=ally,foe_moves=foe_moves)
  e,a=w['engine'],w['trainer']
  self.acquire(e,a,SC.GUIDE)
  if adaptive:self.acquire(e,a,SC.ADAPTIVE)
  for actor in (a,w['partner'],*([w['ally']] if ally else [])):FIX.env(e,actor,*terrains)
  return w

 def guide(self,e,a,**options):
  return e.survivalist_activity(a,'wilderness_guide',reason='GM observed all current terrains',**options)

 def adapt(self,e,a,terrain='forest',**options):
  return e.survivalist_activity(a,'adaptive_geography',terrain_name=terrain,reason='actual subject gains Initiative',**options)

 def rejected(self,e,fn,pattern):return assert_rejected_unchanged(e,fn,reason_pattern=pattern)

 def next_round(self,e,actor):
  active=getattr(e,'_active_turn_actor',None)
  if active is not None:e.end_of_turn(active)
  e.end_round();e.start_round(e.everyone);e.start_of_turn(actor,initiative_count=20)

 def test_exact_hb_sources_real_prerequisites_hp_and_base754_are_not_whole_class_grants(self):
  definitions=SC.hb_definitions(self.rules)['features']
  self.assertEqual({row['csv_record'] for row in definitions.values()},{755,756})
  self.assertEqual(tuple(definitions[SC.ADAPTIVE]['cycle']),SC.CYCLE)
  w=FIX.scene(self.rules,feats=(),survival=3);e,a=w['engine'],w['trainer']
  hp=a.stats['hp'];FIX.acquire(e,a,SC.CLASS)
  self.assertEqual(a.stats['hp'],hp+1)
  self.assertEqual(a.spec['feats'],[SC.CLASS])
  self.rejected(e,lambda:self.acquire(e,a,SC.GUIDE),'printed Survival rank')
  self.rejected(e,lambda:self.acquire(e,a,SC.ADAPTIVE),'printed Survival rank|four acquired')
  e.gm.set_skill(a,'생존',6,reason='actual Master Survival')
  self.rejected(e,lambda:self.acquire(e,a,SC.ADAPTIVE),'four acquired')
  for feature in (SC.NATURAL,SC.TRAPPER):FIX.acquire(e,a,feature)
  hp=a.stats['hp'];receipt=self.acquire(e,a,SC.GUIDE)
  self.assertEqual((a.stats['hp'],receipt['snapshot']['selection']),(hp+1,{'edition':'csv_hb'}))
  hp=a.stats['hp'];self.acquire(e,a,SC.ADAPTIVE)
  self.assertEqual(a.stats['hp'],hp+1)
  self.assertEqual((SC.edition(a,SC.GUIDE),SC.edition(a,SC.ADAPTIVE)),('csv_hb','csv_hb'))
  self.rejected(e,lambda:self.acquire(e,a,SC.GUIDE,edition='book'),'replay cannot change optional selection')
  self.rejected(e,lambda:self.acquire(e,a,SC.GUIDE,edition='unknown',request='bad-edition'),'already acquired|edition')
  base=e.survivalist_activity(a,'select_csv_terrains',clause_id=V.CSV_CLAUSES[1],terrains=['forest','ocean','urban'],minutes=1,reason='R754 actual paid daily selection')
  self.assertEqual((base['clause_id'],base['feature_count'],e.elapsed_seconds),(V.CSV_CLAUSES[1],5,60))
  FIX.env(e,a,'forest')
  self.assertEqual(e.skill_roll(a,'생존',fixed=[1]*6).total,8)
  self.assertIn('forest',MOVE.naturewalk_terrains(e,a))
  self.assertNotIn(SC.TALENT,a.spec['feats'])
  self.assertTrue(e.validate_state()['valid'])

 def test_all_current_terrains_apply_once_to_actual_allies_with_scene_three_standard_and_one_round_expiry(self):
  current=('forest','grassland','wetland','ocean','urban')
  w=self.world(ally=True,terrains=current,foe_moves=['move/냉동빔'])
  e,a,p,friend,foe=(w[k] for k in ('engine','trainer','partner','ally','foe'))
  land=MOVE.capabilities(e,p)['land'];swim=MOVE.capabilities(e,p)['swim']
  initiative=e.initiative_value(p).value;evade=friend.evasion('물리',engine=e)
  move=self.rules.move('move/냉동빔');damage=e.roll_damage(foe,p,move,set_damage=True)
  FIX.battle(e,a)
  receipt=self.guide(e,a,terrain_name='forest')
  self.assertEqual((receipt['edition'],set(receipt['branches']),receipt['terrains']),('csv_hb',{'grassland_forest','ocean_wetland','urban'},list(current)))
  self.assertEqual((a.budget['standard'],FREQ.state(a)['activations'][SC.GUIDE]['used']),(0,1))
  self.assertEqual((len(FIX.guide_rows(p)),len(FIX.guide_rows(friend))), (3,3))
  self.assertEqual((FIX.guide_rows(a),FIX.guide_rows(foe)),([],[]))
  self.assertEqual((e.initiative_value(p).value,MOVE.capabilities(e,p)['land'],MOVE.capabilities(e,p)['swim']),(initiative+5,land+2,swim+2))
  self.assertNotIn('은밀',GRANTS.effective_capabilities(p))
  self.assertEqual((friend.evasion('물리',engine=e),e.roll_damage(foe,p,move,set_damage=True)),(evade+1,damage-5))
  e.end_of_turn(a);e.end_round();e.start_round(e.everyone);e.at_initiative_count(21)
  self.assertEqual(len(FIX.guide_rows(p)),3)
  e.start_of_turn(a,initiative_count=20)
  self.assertEqual((FIX.guide_rows(p),e.initiative_value(p).value,MOVE.capabilities(e,p)['land']),([],initiative,land))
  for used in (2,3):
   self.guide(e,a)
   self.assertEqual(FREQ.state(a)['activations'][SC.GUIDE]['used'],used)
   self.next_round(e,a)
  self.rejected(e,lambda:self.guide(e,a),'Scene frequency exhausted')
  self.assertTrue(e.validate_state()['valid'])

 def test_hp_tag_is_one_actual_source_on_replay_restore_and_paid_feature_withdrawal(self):
  e=Engine(self.rules,seed=756)
  spec=FIX.trainer_spec(self.rules,'actual paid retraining participant');spec['exp_bank']=2
  a=Combatant(self.rules,spec);e.gm.add_combatant(a,side='party',reason='actual trainer with observed banked XP')
  FIX.acquire(e,a,SC.CLASS)
  base=a.stats['hp'];receipt=self.acquire(e,a,SC.GUIDE)
  source=RETRAIN.owned_source(e,a,SC.GUIDE)
  self.assertEqual(a.stats['hp'],base+1)
  self.assertEqual(a.spec[GRANTS.KEY]['stat_sources']['hp']['sources'][source],{'acquisition_stat_tag':{'delta':1,'minimum':None}})
  self.assertEqual(self.acquire(e,a,SC.GUIDE),receipt)
  self.assertEqual(a.stats['hp'],base+1)
  loaded,index=FIX.restore(self.rules,e);again=index[a.entity_id]
  self.assertEqual(again.stats['hp'],base+1)
  parent=RETRAIN.owned_source(loaded,again,SC.CLASS)
  result=loaded.retrain_trainer_source(again,SC.GUIDE,request_id='hb-hp-withdraw',reason='actual Feature retraining',gm_decision={'allowed':True,'reason':'GM confirmed no retained child'},retained_dependencies={parent:[]})
  self.assertEqual((again.stats['hp'],again.spec['exp_bank'],result['xp_paid']),(base,0,2))
  self.assertNotIn(SC.GUIDE,again.spec['feats'])
  self.assertEqual(self.acquire(loaded,again,SC.GUIDE)['status'],'withdrawn')
  self.assertEqual(again.stats['hp'],base)
  self.assertTrue(loaded.validate_state()['valid'])

 def test_hb_geography_actual_paid_shift_and_nature_power_keep_as_if_without_changing_world(self):
  w=self.world(adaptive=True,terrains=('wetland',));e,a,foe=(w[k] for k in ('engine','trainer','foe'))
  e.survivalist_activity(a,'select_csv_terrains',clause_id=V.CSV_CLAUSES[1],terrains=['forest'],minutes=1,reason='actual R754 selected forest')
  e.gm.set_position(a,(0,0),reason='actual corridor start');e.gm.set_position(foe,(0,5),reason='actual target beyond marsh')
  e.gm.set_movement_capabilities(a,{'land':3},basis='current',reason='actual current land speed')
  e.grid.slow={(0,1),(0,2),(0,3)}
  MOVE.observe_cell_terrain(e,[(0,y) for y in range(6)],['wetland'],'actual marsh corridor')
  e.gm.set_move(a,ENV.NATURE,reason='actual learned Nature Power')
  e.gm.set_stat(foe,'hp',value=100,reason='observed robust target');e.gm.set_hp(foe,foe.max_hp,reason='healthy target')
  e.observe_environment('actual',dict(gravity=1,pressure=1,air_available=True,medium='air',environ='늪지'),source=ENV.NATURE,reason='observed actual marsh environment')
  FIX.battle(e,a);self.adapt(e,a)
  self.next_round(e,a)
  e.approach(a,foe)
  self.assertEqual((a.pos,a.budget['shift']),((0,3),0))
  before=foe.hp
  with patch.object(e,'d20',return_value=17):e.use_move(a,foe,ENV.NATURE,set_damage=True)
  self.assertLess(foe.hp,before)
  self.assertEqual((a.budget['standard'],a.move_uses[ENV.NATURE]),(0,1))
  self.assertNotIn('move/에너지볼',a.move_uses)
  self.assertEqual((foe.stages['spd'],e.grid.slow,e.grid.terrain_types['0,3']),(-1,{(0,1),(0,2),(0,3)},['wetland']))
  self.assertEqual(ENV.prepare(e,a,self.rules.move(ENV.NATURE))['_environ_selection']['environ'],'숲')
  self.assertTrue(e.validate_state()['valid'])

 def test_hb_geography_selected_as_if_survives_changed_actual_environment_and_cell_terrain(self):
  w=self.world(adaptive=True,terrains=('wetland',));e,a,foe=(w[k] for k in ('engine','trainer','foe'))
  e.survivalist_activity(a,'select_csv_terrains',clause_id=V.CSV_CLAUSES[1],terrains=['forest'],minutes=1,reason='actual R754 selected forest')
  e.gm.set_position(a,(0,0),reason='actual wetland departure');e.gm.set_position(foe,(0,5),reason='actual target across desert')
  e.gm.set_movement_capabilities(a,{'land':3},basis='current',reason='actual current land speed')
  e.grid.slow={(0,1),(0,2),(0,3)}
  MOVE.observe_cell_terrain(e,[(0,0)],['wetland'],'actual wetland departure cell')
  MOVE.observe_cell_terrain(e,[(0,y) for y in range(1,6)],['desert'],'actual desert destination cells')
  e.gm.set_move(a,ENV.NATURE,reason='actual learned Nature Power')
  e.gm.set_stat(foe,'hp',value=100,reason='observed robust target');e.gm.set_hp(foe,foe.max_hp,reason='healthy target')
  facts=dict(gravity=1,pressure=1,air_available=True,medium='air')
  e.observe_environment('wetland',dict(facts,environ='늪지'),cells=[(0,0)],source=ENV.NATURE,reason='actual departure environment')
  e.observe_environment('desert',dict(facts,environ='사막'),cells=[(0,y) for y in range(1,6)],source=ENV.NATURE,reason='actual destination environment')
  FIX.battle(e,a);row=self.adapt(e,a)
  self.next_round(e,a)
  self.assertTrue(MOVE.ordinary_terrain(e,a,(0,1)))
  e.approach(a,foe)
  self.assertEqual((a.pos,a.budget['shift']),((0,3),0))
  FIX.env(e,a,'desert')
  self.assertEqual((SC.as_if(e,a),V.current_environment(e,a)['terrains']),(row,('desert',)))
  self.assertEqual(e.skill_roll(a,'생존',fixed=[1]*6).total,8)
  self.assertTrue(MOVE.ordinary_terrain(e,a,a.pos))
  prepared=ENV.prepare(e,a,self.rules.move(ENV.NATURE));selection=prepared['_environ_selection']
  witness=selection['adaptive_geography']
  self.assertEqual((selection['environ'],witness['actual_environ'],witness['activation_environ']),('숲','사막','늪지'))
  self.assertEqual(selection['effective_facts']['environ'],'사막')
  self.assertEqual(ENV.mechanics(e,prepared,self.rules.move_mech(ENV.NATURE)[0]),self.rules.move_mech('move/에너지볼')[0])
  bad=deepcopy(selection);bad['adaptive_geography']['activation_environ']='산'
  with self.assertRaisesRegex(ValueError,'not adjacent'):SC.environ_selection_actual(bad)
  bad=deepcopy(prepared);bad['_environ_selection']['adaptive_geography']['actual_environ']='도시'
  bad['_environ_selection']=ENV.ED._sign({k:v for k,v in bad['_environ_selection'].items() if k!='sha256'})
  with self.assertRaisesRegex(ValueError,'effective facts'):ENV.mechanics(e,bad,self.rules.move_mech(ENV.NATURE)[0])
  before=foe.hp
  with patch.object(e,'d20',return_value=17):e.use_move(a,foe,ENV.NATURE,set_damage=True)
  self.assertLess(foe.hp,before)
  self.assertEqual((a.move_uses[ENV.NATURE],foe.stages['spd']),(1,-1))
  self.assertEqual((e.grid.terrain_types['0,3'],e.grid.slow),(['desert'],{(0,1),(0,2),(0,3)}))
  self.assertEqual(SC.as_if(e,a),row)
  e.end_encounter(round_elapsed_seconds=10)
  self.assertIsNone(SC.as_if(e,a))
  self.assertEqual(e.skill_roll(a,'생존',fixed=[1]*6).total,6)
  self.assertFalse(MOVE.ordinary_terrain(e,a,a.pos))
  self.assertEqual(ENV.prepare(e,a,self.rules.move(ENV.NATURE))['_environ_selection']['environ'],'사막')
  self.assertEqual(ENV.mechanics(e,prepared,self.rules.move_mech(ENV.NATURE)[0]),self.rules.move_mech('move/에너지볼')[0])

 def test_book_guide_stays_distinct_from_hb_all_current_terrain_and_keen_eye(self):
  w=FIX.scene(self.rules);e,a,p=(w[k] for k in ('engine','trainer','partner'))
  FIX.env(e,a,'forest','urban');FIX.battle(e,a)
  self.assertEqual(SC.edition(a,SC.GUIDE),'book')
  receipt=self.guide(e,a,terrain_name='forest')
  self.assertNotIn('edition',receipt)
  self.assertEqual(SC._branches(p),{'grassland_forest'})
  self.assertIn('은밀',GRANTS.effective_capabilities(p))
  self.assertFalse(SC.keen_eye(e,p))

 def test_hb_geography_reaches_r754_skills_naturewalk_and_environ_across_turns_then_ends_at_encounter_not_scene(self):
  w=self.world(adaptive=True,terrains=('wetland',));e,a,p,foe=(w[k] for k in ('engine','trainer','partner','foe'))
  e.survivalist_activity(a,'select_csv_terrains',clause_id=V.CSV_CLAUSES[1],terrains=['forest'],minutes=1,reason='actual R754 selected forest')
  MOVE.observe_cell_terrain(e,[(2,2),(3,2),(2,1)],['wetland'],'actual wetland cells')
  e.gm.set_move(a,ENV.NATURE,reason='actual learned Environ Move')
  e.observe_environment('actual',dict(gravity=1,pressure=1,air_available=True,medium='air',environ='늪지'),source=ENV.NATURE,reason='actual environment')
  self.rejected(e,lambda:self.adapt(e,a),'gain Initiative')
  FIX.battle(e,a)
  self.rejected(e,lambda:self.adapt(e,a,'cave'),'adjacent')
  row=self.adapt(e,a)
  self.assertEqual((row['edition'],a._action_history,a.budget['standard']),('csv_hb',['free'],1))
  self.assertEqual(e.skill_roll(a,'생존',fixed=[1]*6).total,8)
  self.assertTrue(MOVE.ordinary_terrain(e,a,(2,2)))
  selected=ENV.prepare(e,a,self.rules.move(ENV.NATURE))['_environ_selection']
  self.assertEqual((selected['environ'],selected['adaptive_geography']['actual_environ']),('숲','늪지'))
  self.assertEqual((V.current_environment(e,a)['terrains'],e.grid.terrain_types['2,2']),(('wetland',),['wetland']))
  FIX.next_turn(e,a,p,count=15)
  self.assertEqual(SC.as_if(e,a),row)
  self.assertIsNone(SC.as_if(e,p))
  self.adapt(e,a,'ocean',target=p)
  FIX.next_turn(e,p,foe,count=10)
  self.assertEqual(SC.as_if(e,p)['as_if_terrain'],'ocean')
  e.end_of_turn(foe);e.end_round();e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
  self.assertEqual(e.skill_roll(a,'생존',fixed=[1]*6).total,8)
  self.rejected(e,lambda:self.adapt(e,a,'ocean'),'already shaped')
  e.end_encounter(round_elapsed_seconds=10)
  self.assertEqual((SC.as_if(e,a),SC.as_if(e,p)),(None,None))
  self.assertEqual(e.skill_roll(a,'생존',fixed=[1]*6).total,6)
  FIX.battle(e,a)
  self.rejected(e,lambda:self.adapt(e,a),'once per Scene')
  e.end_scene(round_elapsed_seconds=10);FIX.battle(e,a)
  self.assertEqual(self.adapt(e,a)['as_if_terrain'],'forest')
  self.assertTrue(e.validate_state()['valid'])

 def test_hb_geography_uses_actual_subject_initiative_scene_three_and_nine_ring_edges(self):
  for actual in SC.CYCLE:
   self.assertEqual([t for t in SC.CYCLE if SC.adjacent(actual,t)], [t for t in SC.CYCLE if t in (SC.CYCLE[(SC.CYCLE.index(actual)-1)%9],SC.CYCLE[(SC.CYCLE.index(actual)+1)%9])])
  w=self.world(adaptive=True,terrains=('wetland',));e,a,p,foe=(w[k] for k in ('engine','trainer','partner','foe'))
  extras=[]
  for n in (2,3):
   actor=Combatant(self.rules,FIX.pokemon_spec(self.rules,a,'partner'+str(n)))
   e.gm.add_combatant(actor,pos=(3,n+1),side='party',reason='actual own Pokemon')
   FIX.env(e,actor,'wetland');extras.append(actor)
  FIX.battle(e,a)
  self.rejected(e,lambda:self.adapt(e,a,target=foe),'your own Pokemon')
  self.rejected(e,lambda:self.adapt(e,a,target=p),'gain Initiative')
  self.adapt(e,a)
  FIX.next_turn(e,a,p,count=15);self.adapt(e,a,'ocean',target=p)
  FIX.next_turn(e,p,extras[0],count=10);self.adapt(e,a,target=extras[0])
  self.assertEqual(FREQ.state(a)['activations'][SC.ADAPTIVE],{'kind':'scene','period':0,'used':3})
  FIX.next_turn(e,extras[0],extras[1],count=5)
  self.rejected(e,lambda:self.adapt(e,a,target=extras[1]),'Scene frequency exhausted')
  self.assertTrue(e.validate_state()['valid'])

 def test_hb_records_and_acquired_editions_restore_with_their_distinct_lifetimes(self):
  w=self.world(adaptive=True,terrains=('wetland','urban'));e,a,p=(w[k] for k in ('engine','trainer','partner'))
  FIX.battle(e,a);self.adapt(e,a,'forest',actual_terrain='wetland');self.guide(e,a)
  loaded,index=FIX.restore(self.rules,e);again=index[a.entity_id];mate=index[p.entity_id]
  self.assertEqual((SC.edition(again,SC.GUIDE),SC.as_if(loaded,again)['edition']),('csv_hb','csv_hb'))
  self.assertEqual({r['wilderness_guide']['branch'] for r in FIX.guide_rows(mate)},{'grassland_forest','urban'})
  loaded.end_of_turn(again)
  self.assertEqual(SC.as_if(loaded,again)['as_if_terrain'],'forest')
  self.assertEqual(len(FIX.guide_rows(mate)),2)
  loaded.end_encounter(round_elapsed_seconds=10)
  self.assertEqual((SC.as_if(loaded,again),FIX.guide_rows(mate)),(None,[]))
  self.assertTrue(loaded.validate_state()['valid'])


 def test_hb_guide_preserves_native_group_delivery_cheer_and_priority_payment(self):
  import action_points as AP,cheerleader as CHEER,moment_of_action as MOMENT
  w=self.world(ally=True,terrains=('forest','urban'));e,a,p,b=(w[k] for k in ('engine','trainer','partner','ally'))
  for source in (MOMENT.TRAINING,MOMENT.CLASS):
   ACQUIRE.acquire_static(e,a,source,acquisition_request_id='hb-guide-native/'+source)
  e.rulings.add_answer('cheerleader','Excited',reason='actual choice',scope='permanent')
  e.start_round(e.everyone);e.at_initiative_count(30);e.at_initiative_count(25)
  self.rejected(e,lambda:self.guide(e,a,communication={}),'per-ally')
  e.gm.observe_sensory_environment(a,b,paths={'auditory':False},present=True,reason='actual blocked Guide delivery')
  self.rejected(e,lambda:self.guide(e,a),'not delivered')
  e.gm.observe_sensory_environment(a,b,paths={'auditory':True},present=True,reason='actual restored Guide delivery')
  before=AP.available(a);receipt=self.guide(e,a)
  self.assertEqual((AP.available(a),a.pending_action_loss,receipt['count']),(before-1,{'standard':1},25))
  self.assertEqual(FREQ.state(a)['activations'][SC.GUIDE]['used'],1)
  for ally in (p,b):
   self.assertEqual(len(CHEER.live(ally,'Excited')),1)
   self.assertEqual(SC._branches(ally),{'grassland_forest','urban'})
   self.assertTrue(all(row['count_deadline']==(e.round_no+1,25) for row in SC._guide_rows(ally)))
  self.assertFalse(CHEER.live(a))
  self.assertTrue(e.validate_state()['valid'])
  loaded,index=FIX.restore(self.rules,e)
  self.assertTrue(loaded.validate_state()['valid'])
  self.assertEqual(SC._branches(index[p.entity_id]),{'grassland_forest','urban'})

 def weather_pokemon(self,e,a,name,side):
  import builder
  actor=Combatant(self.rules,builder.build_pokemon(self.rules,'이상해씨',5,name=name))
  e.gm.add_combatant(actor,pos=(7,4) if side=='wild' else (3,4),side=side,reason='actual weather Ability recipient')
  e.choose_growth_ability(actor,'creation','엽록소',reason='native birth Ability choice')
  e.gm.set_stat(actor,'spe',value=10,reason='actual Speed for weather benefit')
  if side==a.side:
   e.gm.observe_sensory_environment(a,actor,paths={'auditory':True},present=True,reason='actual Guide Order delivery')
  return actor

 def test_hb_weather_suppresses_enemy_chlorophyll_speed_and_initiative_until_same_count_then_restores(self):
  import ability_transitions as ABILITIES
  w=self.world(terrains=('desert',));e,a=w['engine'],w['trainer']
  foe=self.weather_pokemon(e,a,'weather-foe','wild');friend=self.weather_pokemon(e,a,'weather-friend','party')
  GRANTS.grant(foe,'abilities','도주','gm/weather-control','gm',rule_id='ability/도주');GRANTS.reconcile(e,foe)
  acquired=deepcopy(foe.abilities);e.change_stage(foe,'spe',1)
  e.gm.set_weather('sunny',rounds=None,reason='actual lasting sunny weather')
  self.assertEqual((foe.stages['spe'],friend.stages['spe']),(5,4))
  FIX.battle(e,a);FIX.audible_order(e,a);before=e.initiative_value(foe).value;receipt=self.guide(e,a)
  self.assertIn(foe.entity_id,receipt['weather_targets']);self.assertNotIn(friend.entity_id,receipt['weather_targets'])
  self.assertEqual((foe.stages['spe'],foe.staged('spe'),friend.stages['spe']),(1,12,4))
  self.assertLess(e.initiative_value(foe).value,before)
  self.assertEqual(foe.abilities,acquired);self.assertTrue(ABILITIES.active(foe,'ability/도주'))
  self.assertEqual(e.weather,'sunny')
  loaded,index=FIX.restore(self.rules,e);enemy=index[foe.entity_id]
  self.assertEqual((enemy.stages['spe'],enemy.abilities),(1,acquired))
  self.assertLess(loaded.initiative_value(enemy).value,before)
  self.assertTrue(loaded.validate_state()['valid'])
  e.end_of_turn(a);e.end_round();e.start_round(e.everyone)
  e.at_initiative_count(21);self.assertEqual(foe.stages['spe'],1)
  e.at_initiative_count(20);self.assertEqual(foe.stages['spe'],5)
  self.assertEqual(e.initiative_value(foe).value,before)
  self.assertEqual(foe.abilities,acquired);self.assertTrue(e.validate_state()['valid'])
  loaded.end_encounter(round_elapsed_seconds=10)
  self.assertFalse(SC.weather_ability_suppressed(loaded,enemy,'ability/엽록소'))
  self.assertEqual(enemy.abilities,acquired)

 def test_sunny_chlorophyll_start_round_preserves_stage_alias_without_prereading_stages(self):
  w=self.world(terrains=('desert',));e,a=w['engine'],w['trainer']
  foe=self.weather_pokemon(e,a,'weather-unread-foe','wild')
  raw_stages=vars(foe)['stages']
  e.gm.set_weather('sunny',rounds=None,reason='sunny before any lazy stage read')
  self.assertIs(vars(foe)['stages'],raw_stages)
  self.assertEqual(raw_stages['spe'],0)
  FIX.battle(e,a)
  self.assertIs(vars(foe)['stages'],raw_stages)
  self.assertEqual(foe.stages['spe'],4)
  self.assertTrue(e.validate_state()['valid'])

 def test_hb_weather_record_tampering_rejected_and_book_does_not_suppress_enemy_self_benefit(self):
  w=self.world(terrains=('desert',));e,a=w['engine'],w['trainer']
  foe=self.weather_pokemon(e,a,'weather-integrity-foe','wild')
  e.gm.set_weather('sunny',rounds=None,reason='actual sunny weather');FIX.battle(e,a);FIX.audible_order(e,a);self.guide(e,a)
  record=next(row for row in TIME.records(foe) if 'survivalist_weather' in row)
  old=record['count_deadline'];record['count_deadline']=(e.round_no+2,20)
  with self.assertRaisesRegex(ValueError,'one-round'):SC.validate_world(e)
  record['count_deadline']=old
  w=FIX.scene(self.rules);e,a=w['engine'],w['trainer'];FIX.env(e,a,'desert')
  foe=self.weather_pokemon(e,a,'book-weather-foe','wild')
  e.gm.set_weather('sunny',rounds=None,reason='Book control sunny');FIX.battle(e,a);FIX.audible_order(e,a)
  self.guide(e,a,terrain_name='desert')
  self.assertEqual(foe.stages['spe'],4)
  self.assertFalse(SC.weather_ability_suppressed(e,foe,'ability/엽록소'))
  self.assertTrue(e.validate_state()['valid'])

if __name__=='__main__':unittest.main()
