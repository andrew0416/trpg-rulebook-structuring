"""C11-108/111: explicit sample adoption over the existing weather owner."""
from copy import deepcopy
from pathlib import Path
import hashlib,json,math,sys,unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Engine,Rules,Combatant
from builder import build_pokemon,build_trainer
from grid import Grid
from state_codec import StateCodecError
import weather_state as W,nicolette_gym as GYM,effects as FX,effects_ext as EXT
import combat_timing as CLOCK,turn as TURN,ability_state_projection as P
import ability_native_actions as NATIVE,ability_transitions as AB,items as ITEMS


class NicoletteWeatherTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

 def pokemon(self,e,identity,*,species='이상해씨',abilities=(),trainer=None,moves=(),types=None,pos=(6,3),side='party',name=None):
  extra={'id':identity}
  if trainer is not None:
   extra.update(trainer_id=trainer.entity_id,loyalty=2,
    loyalty_relations={trainer.entity_id:{'value':2,'reason':'GM-established test relationship permits actual native commands'}})
  if types is not None:extra['types']=list(types)
  c=Combatant(e.r,build_pokemon(e.r,species,40,name=name or identity,moves=list(moves),abilities=list(abilities),pos=pos,side=side,extra=extra))
  e.gm.add_combatant(c);return c

 def fixture(self,*,adopt=True,ground=True):
  e=Engine(self.r,seed=419);e.grid=Grid(24,24)
  trainer=Combatant(self.r,build_trainer(self.r,'Nicolette',40,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),pos=(1,1),side='gym',extra={'id':'sample/nicolette'}))
  e.gm.add_combatant(trainer)
  # Imported legal six-Move selection for these state checks, not full-sheet construction.
  printed=['move/'+m for m in ('웨더볼','눈보라','병상첨병','전격파','에너지볼')]
  rudolf=self.pokemon(e,'sample/rudolf',species='캐스퐁',abilities=('기분파','부유','눈퍼트리기'),trainer=trainer,moves=printed+['move/모래바람'],pos=(3,3),side='gym')
  target=self.pokemon(e,'sample/target',moves=('move/안개제거','move/쾌청','move/비바라기'),types=('노말',))
  if adopt:
   GYM.configure_weather(e,trainer,gm_id='gm/sample',reason='printed winter mountain adopted',winter=True)
   GYM.configure_rudolf(e,rudolf,gm_id='gm/sample',reason='actual sample individual observed',ground_weather_ball=ground)
  return e,trainer,rudolf,target

 def turn(self,e,c,count=12):
  if e._active_turn_actor is not None:e.end_of_turn(e._active_turn_actor)
  e.start_round(e.everyone);e.start_of_turn(c,initiative_count=count)

 def layer(self,e,t,r):
  self.turn(e,r)
  prompts=[];original=EXT._prompt
  def observe(actual,effect,text,src=None,attacker=None,target=None):
   result=original(actual,effect,text,src,attacker,target)
   prompts.append(dict(effect=deepcopy(effect),text=text,source=src,log=deepcopy(actual.log_lines[-8:])))
   return result
  try:
   with patch.object(EXT,'_prompt',observe):
    return GYM.use_climate_control(e,t,r,gm_id='gm/sample',reason='actual sampled Climate Control selected before native Sandstorm')
  except Exception as error:
   error.add_note('Actual native prompts/log: '+json.dumps(prompts,ensure_ascii=False,default=str));raise

 def restore(self,e):return Engine.import_state(self.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
 def find(self,e,c):return next(x for x in e.everyone if x.entity_id==c.entity_id)

 def test_exact_printed_sources_and_frozen_included_state_children(self):
  source=(ROOT/GYM.AP_REFERENCE['file']).read_bytes()
  self.assertEqual(hashlib.sha256(source).hexdigest(),GYM.AP_REFERENCE['sha256'])
  lines=source.decode('utf-8').splitlines()
  self.assertIn('얼음/땅',lines[2142]);self.assertIn('두 라운드',lines[2149]);self.assertIn('모래폭풍',lines[2150])
  self.assertEqual(hashlib.sha256((ROOT/GYM.CLIMATE_REFERENCE['file']).read_bytes()).hexdigest(),GYM.CLIMATE_REFERENCE['sha256'])
  rows=json.loads((ROOT/'data/verification/category2-core-clause-status.json').read_text(encoding='utf-8'))['clause_mappings']
  expected={'C11-108':'7c28294214f6c7ab438bd91da591d010220678e3cd9fc7ba094d58a85a1339fe','C11-111':'51df98302eacc369fe7b12351f8d61989f8f25fc1856c5c8f28db303e0a5585e'}
  for key,digest in expected.items():
   row=next(r for r in rows if r['clause_id']==key)
   self.assertEqual(hashlib.sha256(row['source_statement'].encode()).hexdigest(),digest)

 def test_adoption_binds_actual_individual_and_does_not_infer_from_name_or_species(self):
  e,t,r,target=self.fixture(adopt=False)
  other=self.pokemon(e,'ordinary/rudolf',species='캐스퐁',abilities=('기분파',),trainer=t,name='Rudolf',pos=(4,4),side='gym')
  before=e.export_state()
  with self.assertRaises(ValueError):GYM.configure_weather(e,t,gm_id='gm/sample',reason='not winter',winter=False)
  self.assertEqual(e.export_state(),before)
  GYM.configure_weather(e,t,gm_id='gm/sample',reason='winter source adopted',winter=True)
  with self.assertRaises(ValueError):GYM.configure_rudolf(e,target,gm_id='gm/sample',reason='wrong individual')
  GYM.configure_rudolf(e,r,gm_id='gm/sample',reason='actual unique individual',ground_weather_ball=True)
  self.layer(e,t,r)
  self.assertEqual(r.types,['얼음','땅']);self.assertEqual(other.types,['얼음'])
  e.activate_ability_state(other,'ability/기분파',choice='바위',reason='ordinary Forecast chooses the actual independent Sandstorm')
  self.assertEqual(other.types,['바위']);self.assertEqual(r.types,['얼음','땅'])
  self.assertTrue(e.validate_state()['valid'])

 def test_native_climate_control_preserves_original_hail_and_pays_only_native_move(self):
  e,t,r,target=self.fixture();original=deepcopy(e._weather_state['active']);history=deepcopy(e._weather_state['history'])
  storm=self.layer(e,t,r)
  self.assertEqual(e._weather_state['active'],original);self.assertEqual(e._weather_state['history'],history)
  self.assertEqual((storm['source_id'],storm['origin'],storm['actor_id'],storm['duration'],storm['deadline_count']),('move/모래바람','move',r.entity_id,5,12))
  self.assertEqual(storm['climate_control']['hail_id'],original['id']);self.assertEqual(storm['climate_control']['producer_id'],r.entity_id)
  self.assertEqual(r.budget['standard'],0);self.assertTrue(r.move_uses)
  self.assertEqual(W.effective_weathers(e),('hail','sandstorm'));self.assertEqual((e.weather,e.weather_rounds),('hail',None))
  self.assertFalse(hasattr(e,'_nicolette_climate_control_scope'));self.restore(e)

 def test_climate_control_rejects_wrong_actual_actor_gm_and_failed_native_move_atomically(self):
  e,t,r,target=self.fixture();self.turn(e,r)
  for actual,producer,gm in [(target,r,'gm/sample'),(t,target,'gm/sample'),(t,r,'gm/other')]:
   before=e.export_state()
   with self.assertRaises(ValueError):GYM.use_climate_control(e,actual,producer,gm_id=gm,reason='rejected source binding')
   self.assertEqual(e.export_state(),before)
  e.use_move(r,r,'move/모래바람');before=e.export_state()
  # The ordinary Move really replaced the Hail; an observation cannot revive it.
  with self.assertRaises(ValueError):GYM.use_climate_control(e,t,r,gm_id='gm/sample',reason='no live adopted Hail')
  self.assertEqual(e.export_state(),before)
  e,t,r,target=self.fixture();self.turn(e,r);r.budget['standard']=0;before=e.export_state()
  with self.assertRaises(ValueError):GYM.use_climate_control(e,t,r,gm_id='gm/sample',reason='native Move cannot complete')
  self.assertEqual(e.export_state(),before)

 def test_layer_expires_at_native_five_round_original_count_without_ending_hail(self):
  e,t,r,target=self.fixture();storm=self.layer(e,t,r);hail_id=e._weather_state['active']['id']
  e.end_of_turn(r)
  for _ in range(5):e.start_round(e.everyone)
  CLOCK.at_count(e,13);self.assertEqual(W.effective_weathers(e),('hail','sandstorm'))
  n=self.restore(e);CLOCK.at_count(n,12);nr=self.find(n,r)
  self.assertEqual(W.effective_weathers(n),('hail',));self.assertEqual(nr.types,['얼음'])
  self.assertEqual(n._weather_state['active']['id'],hail_id);self.assertIsNone(n._weather_state['active']['deadline_round'])
  self.assertEqual([(x['id'],x['end_reason']) for x in n._weather_state['history']],[(storm['id'],'duration expired')])
  self.assertIsNone(W.sample_weather_ball_type(n,nr,self.r.move('move/웨더볼')))

 def test_actual_defog_suppresses_exact_two_round_count_and_restores_same_occurrences(self):
  e,t,r,target=self.fixture();storm=self.layer(e,t,r);e.end_of_turn(r)
  e.start_of_turn(target,initiative_count=10);e.use_move(target,target,'move/안개제거')
  hail=deepcopy(e._weather_state['active']);deadline=storm['deadline_round']
  self.assertEqual(W.effective_weathers(e),());self.assertIsNone(e.weather);self.assertEqual(r.types,['노말'])
  self.assertEqual(e._weather_state['history'],[]);self.assertEqual(e._weather_state['layers'][0]['deadline_round'],deadline)
  e.end_of_turn(target);e.start_round(e.everyone);e.start_round(e.everyone);CLOCK.at_count(e,11)
  self.assertIsNone(e.weather)
  n=self.restore(e);CLOCK.at_count(n,10);nr=self.find(n,r)
  self.assertEqual(n._weather_state['active'],hail);self.assertEqual(W.effective_weathers(n),('hail','sandstorm'))
  self.assertEqual(nr.types,['얼음','땅']);self.assertEqual(n._weather_state['history'],[])
  import frequency as FREQ
  nt=self.find(n,target)
  self.assertEqual(nt.move_uses['move/안개제거'],1)
  self.assertEqual(FREQ.move_allowed(n,nt,'move/안개제거',outside_combat=False),(False,'일일 기술은 한 장면에 한 번'))
  fresh=self.pokemon(n,'defog/fresh-owner',moves=('move/안개제거',),pos=(9,3))
  n.start_of_turn(fresh,initiative_count=9);n.use_move(fresh,fresh,'move/안개제거')
  self.assertEqual(fresh.move_uses['move/안개제거'],1)
  self.assertEqual(n._weather_state['nicolette']['suppression']['deadline_round'],n.round_no+2)
  self.assertEqual(n._weather_state['nicolette']['suppression']['deadline_count'],9)

 def test_cloud_nine_observation_requires_actual_active_owner_and_two_completed_rounds(self):
  e,t,r,target=self.fixture();cloud=self.pokemon(e,'cloud/owner',abilities=('날씨부정',),pos=(8,3))
  before=e.export_state()
  with self.assertRaises(ValueError):GYM.observe_weather_negation(e,target,source_id='ability/날씨부정',gm_id='gm/sample',reason='not owned')
  self.assertEqual(e.export_state(),before)
  GYM.observe_weather_negation(e,cloud,source_id='ability/날씨부정',gm_id='gm/sample',reason='actual completed external Cloud Nine')
  observation=e._weather_state['nicolette']['suppression']
  self.assertEqual((observation['actor_id'],observation['gm_id'],observation['hail_id']),(cloud.entity_id,'gm/sample',e._weather_state['active']['id']))
  self.assertIsNone(e.weather);e.start_round(e.everyone);e.end_round();self.assertIsNone(e.weather)
  before=e.export_state()
  self.assertEqual(GYM.observe_weather_negation(e,cloud,source_id='ability/날씨부정',gm_id='gm/sample',reason='same sustained passive observed again'),observation)
  self.assertEqual(e.export_state(),before)
  e.start_round(e.everyone);self.assertIsNone(e.weather);e.end_round();self.assertEqual(e.weather,'hail')
  self.assertEqual(r.types,['얼음']);n=self.restore(e);nc=self.find(n,cloud);before=n.export_state()
  self.assertEqual(GYM.observe_weather_negation(n,nc,source_id='ability/날씨부정',gm_id='gm/sample',reason='same completed passive after expiry and fresh restore'),observation)
  self.assertEqual(n.export_state(),before);self.assertEqual(n.weather,'hail')

 def test_actual_air_lock_sustain_cannot_extend_printed_sample_two_round_limit(self):
  e,t,r,target=self.fixture();air=self.pokemon(e,'air/owner',abilities=('에어록',),pos=(8,3))
  self.turn(e,air);e.activate_ability(air,'에어록',(air,{'mode':'start'}));self.assertIsNone(e.weather)
  e.end_of_turn(air);e.end_round();e.start_round(e.everyone);e.start_of_turn(air,initiative_count=12)
  e.activate_ability(air,'에어록',(air,{'mode':'sustain'}));e.end_of_turn(air);e.end_round()
  e.start_round(e.everyone);CLOCK.at_count(e,13);self.assertIsNone(e.weather)
  e.start_of_turn(air,initiative_count=12);e.activate_ability(air,'에어록',(air,{'mode':'sustain'}))
  self.assertEqual(e.weather,'hail');self.assertIsNone(NATIVE.weather_locked(e));self.assertEqual(r.types,['얼음'])
  self.assertTrue(air.spec[NATIVE.KEY]['ability/에어록']['air_lock']);self.restore(e)

 def test_normal_native_weather_replaces_both_and_never_revives_expired_hail(self):
  e,t,r,target=self.fixture();self.layer(e,t,r);hail_id=e._weather_state['active']['id']
  e.end_of_turn(r);e.start_of_turn(target,initiative_count=10);e.use_move(target,target,'move/쾌청')
  self.assertEqual(W.effective_weathers(e),('sunny',));self.assertEqual(e._weather_state['layers'],[])
  self.assertEqual(r.types,['불꽃']);self.assertFalse(W.sample_hail_live(e))
  e.end_of_turn(target)
  for _ in range(6):e.start_round(e.everyone);e.end_round()
  self.assertIsNone(e.weather);self.assertEqual(r.types,['노말'])
  self.assertEqual(sum(x['id']==hail_id for x in e._weather_state['history']),1);self.restore(e)

 def test_ground_weather_ball_uses_native_db_stab_type_effectiveness_and_immunity(self):
  for boundary in ('normal','single_hail','suppressed','simultaneous'):
   with self.subTest(weather=boundary):
    e,t,r,target=self.fixture(adopt=boundary!='normal')
    if boundary in ('suppressed','simultaneous'):self.layer(e,t,r)
    if boundary=='suppressed':
     e.end_of_turn(r);e.start_of_turn(target,initiative_count=10);e.use_move(target,target,'move/안개제거')
    ball=W.prepare_sample_move(e,r,self.r.move('move/웨더볼'))
    expected=10 if boundary in ('single_hail','simultaneous') else 5
    actual_type='얼음' if boundary=='single_hail' else ball['type']
    if actual_type in r.types:expected+=math.floor(e.formula('stab'))
    self.assertEqual(e.damage_base(r,ball,target=target),expected)
    self.assertEqual(FX.cond_ok(e,{'if':'weather effect active'},{'attacker':r,'target':target,'hit':True})[0],boundary in ('single_hail','simultaneous'))
    self.assertEqual(ball['damage_base'],5)
    self.assertEqual(ball['type'],'땅' if boundary=='simultaneous' else '노말')
  original=Engine.damage_base
  for target_types,immune in [(('전기',),False),(('비행',),True)]:
   with self.subTest(types=target_types):
    e,t,r,target=self.fixture();self.layer(e,t,r)
    e.gm.set_types(target,list(target_types),reason='actual target type for native Ground consumer')
    self.turn(e,r);seen=[]
    def inspect(actual,a,move,**kw):
     result=original(actual,a,move,**kw)
     if move['id']=='move/웨더볼':seen.append((move['type'],list(a.types),result))
     return result
    before=target.hp
    with patch.object(Engine,'damage_base',inspect):e.use_move(r,target,'move/웨더볼',situational=100,set_damage=True)
    self.assertTrue(seen);self.assertTrue(all(x==('땅',['얼음','땅'],10+math.floor(e.formula('stab'))) for x in seen),seen)
    if immune:self.assertEqual(target.hp,before)
    else:self.assertLess(target.hp,before)
    self.assertEqual(self.r.move('move/웨더볼')['type'],'노말');self.restore(e)

 def test_ground_option_is_exact_and_forecast_loss_and_reacquisition_uses_native_owner(self):
  e,t,r,target=self.fixture(ground=False);self.layer(e,t,r);ball=self.r.move('move/웨더볼')
  self.assertIs(W.prepare_sample_move(e,r,ball),ball)
  GYM.configure_rudolf(e,r,gm_id='gm/sample',reason='explicit printed Ground option adopted',ground_weather_ball=True)
  self.assertEqual(W.prepare_sample_move(e,r,ball)['type'],'땅')
  self.assertIs(W.prepare_sample_move(e,target,ball),ball)
  ordinary=self.r.move('move/전격파');self.assertIs(W.prepare_sample_move(e,r,ordinary),ordinary)
  e.gm.set_ability(r,'기분파',add=False,reason='actual Forecast loss');self.assertNotEqual(r.types,['얼음','땅'])
  e.gm.set_ability(r,'기분파',reason='actual Forecast reacquisition');self.assertEqual(r.types,['얼음','땅'])
  GYM.observe_weather_negation(e,self.pokemon(e,'cloud/second',abilities=('날씨부정',),pos=(9,4)),source_id='ability/날씨부정',gm_id='gm/sample',reason='actual completed negation')
  self.assertIs(W.prepare_sample_move(e,r,ball),ball);self.assertEqual(r.types,['노말']);self.restore(e)

 def test_actual_damage_accuracy_save_and_capture_consumers_observe_both_and_suppression(self):
  e,t,r,target=self.fixture();self.layer(e,t,r);before=target.hp
  e.end_of_turn(r);e.start_of_turn(target,initiative_count=10)
  self.assertEqual(before-target.hp,2*e.tick(target));self.assertEqual(r.types,['얼음','땅'])
  blizzard=self.r.move('move/눈보라');mm=self.r.move_mech(blizzard['id'])[0]
  self.assertTrue(EXT.accuracy_hook(e,r,target,blizzard,mm,{'attacker':r,'target':target,'move':blizzard})[3])
  self.assertEqual(TURN.weather_save_mod(e,'얼음',target),-2)
  for ball,expected in [('헤일-볼',4),('샌드볼',4),('썬-볼',0),('레인-볼',0)]:self.assertEqual(ITEMS.ball_modifier(e,ball,t,target)[0],expected)
  e.use_move(target,target,'move/안개제거');after=target.hp
  self.assertFalse(EXT.accuracy_hook(e,r,target,blizzard,mm,{'attacker':r,'target':target,'move':blizzard})[3])
  self.assertEqual(TURN.weather_save_mod(e,'얼음',target),0)
  for ball in ('헤일-볼','샌드볼','썬-볼','레인-볼'):self.assertEqual(ITEMS.ball_modifier(e,ball,t,target)[0],0)
  TURN.weather_turn_start(e,target);self.assertEqual(target.hp,after)
  e.gm.set_weather('rain',reason='ordinary replacement ends the suppressed sample')
  for ball,expected in [('헤일-볼',0),('샌드볼',0),('썬-볼',0),('레인-볼',4)]:self.assertEqual(ITEMS.ball_modifier(e,ball,t,target)[0],expected)
  self.restore(e)

 def test_codec_snapshot_and_source_tampering_preserve_occurrences_and_reject_corruption(self):
  e,t,r,target=self.fixture();self.layer(e,t,r);e.gm.snapshot('layered')
  e.gm.set_weather('rain',reason='normal replacement');e.gm.restore('layered',reason='restore actual adopted sourced state')
  self.assertEqual(r.types,['얼음','땅']);n=self.restore(e);self.assertEqual(n._weather_state,e._weather_state)
  for mutation in ('source','actor','hail','deadline','type'):
   corrupt=self.restore(e);value=corrupt._weather_state
   if mutation=='source':value['layers'][0]['climate_control']['reference']['sha256']='0'*64
   elif mutation=='actor':value['layers'][0]['actor_id']=target.entity_id
   elif mutation=='hail':value['nicolette']['hail_id']=True
   elif mutation=='deadline':value['layers'][0]['deadline_round']+=1
   else:self.find(corrupt,r)._types=['얼음']
   with self.assertRaises(StateCodecError):corrupt.export_state()

 def test_ordinary_forecast_native_sandstorm_rule_uses_existing_turn_owner_and_exact_authority(self):
  e,t,r,target=self.fixture(adopt=False);self.turn(e,r)
  e.use_move(r,r,'move/모래바람')
  self.assertNotIn('nicolette',e._weather_state);self.assertEqual(e.weather,'sandstorm')
  self.assertEqual(r.types,['바위']);self.assertEqual(r.budget['standard'],0);self.assertTrue(r.move_uses)
  self.assertFalse(e.gm_prompts);self.assertEqual(e._weather_state['active']['actor_id'],r.entity_id)
  e.end_of_turn(r);before=target.hp;e.start_of_turn(target,initiative_count=10)
  self.assertEqual(before-target.hp,e.tick(target));self.assertTrue(e.validate_state()['valid'])
  exact={'type':'rule','note':'모래바람 동안 땅·바위·강철이 아닌 포켓몬은 턴 시작 시 소량의 체력(tick) 손실'}
  for boundary in ('altered_rule','external_source','different_producer','ended_occurrence','gm_hook'):
   with self.subTest(boundary=boundary):
    n=self.restore(e);nr=self.find(n,r);nt=self.find(n,target);actor=nr;source='move/모래바람';effect=deepcopy(exact)
    if boundary=='altered_rule':effect['note']+=' + unrelated GM rule'
    elif boundary=='external_source':source='move/쾌청'
    elif boundary=='different_producer':actor=nt
    elif boundary=='ended_occurrence':n.gm.set_weather(None,reason='ordinary clear actually ends the Sandstorm')
    if boundary!='gm_hook':self.assertIsNone(W.native_sandstorm_rule_owner(n,actor,source,effect))
    hooks=deepcopy(n.rulings.hooks)
    if boundary=='gm_hook':n.rulings.add_hook('before_effect',lambda value,ctx:dict(value,note='GM changed rule requires an actual answer'),reason='actual before_effect mutation',scope='scene')
    try:
     result=FX.run_effects(n,actor,actor,[effect],{'hit':True},source)
     self.assertEqual(result[1],1);self.assertTrue(n.gm_prompts)
     if boundary=='gm_hook':self.assertEqual(n.gm_prompts[-1]['effect']['note'],'GM changed rule requires an actual answer')
    finally:n.rulings.hooks=hooks
