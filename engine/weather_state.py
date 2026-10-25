"""Sourced battlefield weather, including the explicitly adopted Nicolette sample."""
from copy import deepcopy
RULE='combat/weather'
KEY='_weather_state'
KINDS={'sunny','rain','sandstorm','hail'}


def native_sandstorm_rule_owner(engine,actor,source_id,effect):
 """The exact core rule is already installed by its actual weather producer."""
 if source_id!='move/모래바람' or effect!={'type':'rule','note':'모래바람 동안 땅·바위·강철이 아닌 포켓몬은 턴 시작 시 소량의 체력(tick) 손실'}:
  return None
 import homebrew_weather as HOME,world_entities as WORLD
 if HOME.enabled(engine.r) or engine.r._selected_rule(source_id)!=source_id or engine.r._selected_rule(RULE)!=RULE:
  return None
 if not hasattr(engine,KEY) or WORLD.actor_index(engine).get(actor.entity_id) is not actor:return None
 value=state(engine)
 return next((record for record in ([value['active']] if value['active'] else [])+value.get('layers',[])
  if record['weather']=='sandstorm' and record['origin']=='move'
  and record['source_id']==source_id and record['actor_id']==actor.entity_id),None)

def validate(engine,index=None):
 state=getattr(engine,KEY,None)
 if state is None:return
 if type(state) is not dict or set(state) not in ({'version','sequence','active','natural','history'},{'version','sequence','active','natural','history','layers'},{'version','sequence','active','natural','history','layers','nicolette'}) or state['version']!=1 or type(state['sequence']) is not int or state['sequence']<0 or type(state['history']) is not list:
  raise ValueError('invalid weather state envelope')
 natural=state['natural']
 if natural is not None:
  if type(natural) is not dict or set(natural)!={'description','equivalent','reason','round'} or not isinstance(natural['description'],str) or not natural['description'].strip() or natural['equivalent'] not in KINDS|{None} or not isinstance(natural['reason'],str) or (natural['equivalent'] is not None and not natural['reason'].strip()):
   raise ValueError('natural weather equivalence requires an explicit GM reason')
 active=state['active']
 layers=state.get('layers',[])
 if type(layers) is not list:raise ValueError('weather layers must be sourced occurrences')
 records=[*state['history'],*([active] if active else []),*layers]
 for record in records:
  if type(record) is not dict or record.get('weather') not in KINDS or record.get('origin') not in ('move','ability','gm','natural','encounter') or not isinstance(record.get('source_id'),str) or not record['source_id'] or type(record.get('id')) is not int or not 1<=record['id']<=state['sequence']:
   raise ValueError('invalid sourced weather record')
  duration=record.get('duration');deadline=record.get('deadline_round');count=record.get('deadline_count')
  start=record.get('started_round')
  if type(start) is not int or not 0<=start<=engine.round_no:raise ValueError('invalid weather creation round')
  if duration is not None and (type(duration) is not int or duration<=0 or type(deadline) is not int or deadline<0):raise ValueError('invalid weather duration')
  if duration is not None and deadline!=start+duration:raise ValueError('weather deadline differs from its sourced duration')
  if duration is None and (deadline is not None or count is not None):raise ValueError('indefinite weather cannot have a deadline')
  if count is not None and type(count) is not int:raise ValueError('invalid weather initiative count')
  item_extension=record.get('item_extension')
  extensions=record.get('trickster_extensions',[])
  if type(extensions) is not list or any(type(x) is not dict or set(x)!={'source','completion','trainer_id','added'} or x['source']!=__import__('trickster').ENCORE or x['added']!=2 or not isinstance(x['completion'],str) or not isinstance(x['trainer_id'],str) for x in extensions) or len({x['completion'] for x in extensions})!=len(extensions):raise ValueError('actual Encore weather extensions required')
  added=2*len(extensions)
  if added and (duration is None or duration<=added):raise ValueError('Encore extends only an actual finite Weather occurrence')
  if item_extension is not None:
   import weather_duration_items as DURATION_ITEMS
   DURATION_ITEMS.validate(item_extension,actor_id=record.get('actor_id'),weather=record['weather'],duration=duration-added)
  import homebrew_weather as HOME_WEATHER
  HOME_WEATHER.validate_record(engine,record,active=record is active,index=index)
  if record['origin']=='ability':__import__('ability_native_actions').validate_weather_record(engine,record,index=index)
  elif 'ability_activation_id' in record:raise ValueError('non-Ability weather cannot claim an Ability activation')
 if len({r['id'] for r in records})!=len(records):raise ValueError('duplicate weather occurrence')
 if 'nicolette' in state:
  import nicolette_gym as GYM
  GYM.validate_weather(engine,state,index=index)
 visible=None if _suppressed(state) else active
 if visible is None:
  if engine.weather is not None or engine.weather_rounds is not None:raise ValueError('weather values lack an active sourced occurrence')
 else:
  if visible['weather']!=engine.weather:raise ValueError('weather differs from its active source')
  if visible['duration'] is None:
   if engine.weather_rounds is not None:raise ValueError('indefinite natural weather gained a timer')
  elif type(engine.weather_rounds) is not int or not 1<=engine.weather_rounds<=visible['duration']:raise ValueError('invalid remaining weather rounds')
  if visible['origin']=='natural' and (natural is None or natural['equivalent']!=visible['weather']):raise ValueError('natural effect lacks its GM classification')

def state(engine):
 validate(engine)
 if not hasattr(engine,KEY):setattr(engine,KEY,{'version':1,'sequence':0,'active':None,'natural':None,'history':[]})
 return getattr(engine,KEY)


def extend_from_completion(engine,actor,completion,turns):
 import trickster as T
 if turns!=2 or completion['actor'] is not actor or completion['phase']!='complete':raise ValueError('actual Encore Weather completion required')
 s=state(engine)
 rows=[r for r in ([s['active']] if s['active'] else [])+s.get('layers',[]) if r.get('actor_id')==actor.entity_id and r['source_id']==completion['move_id'] and r['started_round']==completion['round']]
 if len(rows)!=1 or rows[0]['duration'] is None:raise ValueError('Encore requires the actual finite Weather activated by this Move')
 row=rows[0];trainer=T.owner(engine,actor,T.ENCORE)
 row.setdefault('trickster_extensions',[]).append({'source':T.ENCORE,'completion':completion['id'],'trainer_id':trainer.entity_id,'added':2})
 row['duration']+=2;row['deadline_round']+=2
 if row is s['active'] and engine.weather_rounds is not None:engine.weather_rounds+=2
 validate(engine)
 return row['id']

def effective_state(engine,actor,*,include_virtual=True):
 """Actor-local weather; passive effects exclude Booster, retaining Umbrella."""
 validate(engine)
 value=deepcopy(getattr(engine,KEY,{'version':1,'sequence':0,'active':None,'natural':None,'history':[]}))
 if _suppressed(value):value['active']=None;value['layers']=[]
 import field_effects as FIELD
 local=FIELD.local_weather_for(engine,actor)
 if local is not None:value['active']=local;value['layers']=[]
 active=value.get('active')
 actual=active.get('weather') if isinstance(active,dict) else None
 import csv_item_physical_contracts as CSV_ITEMS
 effective=CSV_ITEMS.effective_environment(engine,actor,actual,include_virtual=include_virtual)
 if include_virtual:
  virtual=__import__('type_ace').virtual_weather(engine,actor)
  if virtual is not None:effective={'비':'rain','쾌청':'sunny','모래바람':'sandstorm','싸라기눈':'hail'}[virtual];value['layers']=[]
 local_item=actor.spec.get(CSV_ITEMS.ACTOR_STATE,{}).get('booster_environment') if include_virtual else None
 if isinstance(local_item,dict) and local_item.get('value') in ('비','쾌청','모래바람','싸라기눈'):value['layers']=[]
 if effective is None:value['active']=None;value['layers']=[]
 elif isinstance(active,dict):value['active']=dict(active,weather=effective,local_to_actor=effective!=actual)
 elif include_virtual and __import__('type_ace').virtual_weather(engine,actor) is not None:
  value['active']={'weather':effective,'origin':'feature','source_id':next(u for u in __import__('type_ace').STRATAGEMS if __import__('type_ace').sustained(engine,actor,u) and __import__('type_ace').DEFINITIONS[u]['english'] in ('Sunlight Within','Desert Heart','Polar Vortex','Fishbowl Technique')),'local_to_actor':True}
 else:value['active']={'weather':effective,'source_id':'item/부스트에너지','origin':'item-local','duration':None,'local_to_actor':True}
 return value


def effective_weathers(engine,actor=None,*,include_virtual=True):
 """All live source occurrences; the ordinary single-weather API stays primary."""
 if actor is None and not hasattr(engine,KEY):
  weather=getattr(engine,'weather',None)
  return () if weather is None else (weather,)
 value=state(engine) if actor is None else effective_state(engine,actor,include_virtual=include_virtual)
 if actor is None and _suppressed(value):return ()
 active=value.get('active')
 return tuple(dict.fromkeys(r['weather'] for r in ([active] if active else [])+value.get('layers',[])))


def _suppressed(value):
 return bool(value.get('nicolette',{}).get('suppression'))


def sample_hail_live(engine):
 value=getattr(engine,KEY,{})
 sample=value.get('nicolette')
 return bool(sample and value.get('active') and value['active']['id']==sample['hail_id'])


def _sync_primary(engine):
 value=getattr(engine,KEY)
 record=None if _suppressed(value) else value['active']
 engine.weather=None if record is None else record['weather']
 engine.weather_rounds=None if record is None else record['duration']


def suppress_sample(engine,*,source_id,reason,actor=None,gm_id=None):
 """Observe this sample's printed two-round negation, retaining real deadlines."""
 if not sample_hail_live(engine):return False
 value=state(engine)
 if engine.r._selected_rule(source_id)!=source_id:raise ValueError('selected weather-negation source required')
 if not isinstance(reason,str) or not reason.strip():raise ValueError('weather-negation observation reason required')
 if source_id=='ability/날씨부정':
  import world_entities as WORLD,ability_transitions as AB,nicolette_gym as GYM,resolution_transaction as TX
  WORLD.require_actors(engine,actor)
  if gm_id!=value['nicolette']['gm_id'] or not actor.on_field or actor.fainted or source_id not in AB.known(actor) or not AB.active(actor,source_id):
   raise ValueError('completed Cloud Nine observation requires its actual active owner and adopted GM')
  intent=GYM.cloud_nine_intent(value['nicolette'],actor.entity_id)
  if TX.replay_result(value['nicolette']['cloud_nine'],actor.entity_id,intent,fingerprint_field='intent_fingerprint') is not None:return True
 cursor=getattr(engine,'_initiative_cursor',None)
 if engine.round_start_seconds is not None and (not cursor or cursor.get('round')!=engine.round_no):
  raise ValueError('weather suppression in an open round requires its actual initiative count')
 value['nicolette']['suppression']={'source_id':source_id,'reason':reason,
  'started_round':engine.round_no,'deadline_round':engine.round_no+2,
  'deadline_count':None if engine.round_start_seconds is None else cursor['count'],
  'actor_id':None if actor is None else actor.entity_id,'gm_id':gm_id,'hail_id':value['nicolette']['hail_id']}
 if source_id=='ability/날씨부정':
  receipt={'suppression':value['nicolette']['suppression']}
  TX.bind_request_intent(receipt,intent)
  value['nicolette']['cloud_nine'][actor.entity_id]=receipt
 _sync_primary(engine)
 __import__('ability_state_projection').weather_changed(engine)
 engine.log('Adopted mountain weather suppressed for two rounds',source_id)
 return True


def sample_negation_complete(engine,source_id):
 """A sustained Air Lock cannot extend this adopted sample's two-round limit."""
 return sample_hail_live(engine) and not _suppressed(getattr(engine,KEY))


def rudolf_types(engine,actor):
 value=getattr(engine,KEY,{})
 sample=value.get('nicolette',{})
 if sample.get('rudolf_id')==actor.entity_id and {'hail','sandstorm'}<=set(effective_weathers(engine,actor)):
  return ['얼음','땅']
 return None


def sample_weather_ball_type(engine,actor,move):
 if move.get('id')!='move/웨더볼':return None
 sample=getattr(engine,KEY,{}).get('nicolette',{})
 if sample.get('rudolf_id')==actor.entity_id and sample.get('ground_weather_ball') and rudolf_types(engine,actor):return '땅'
 return None


def prepare_sample_move(engine,actor,move):
 """Project only the adopted Rudolf's explicit Ground option before native DB/STAB."""
 chosen=sample_weather_ball_type(engine,actor,move)
 if chosen is None:return move
 import nicolette_gym as GYM,world_entities as WORLD
 WORLD.require_actors(engine,actor);GYM._ap_source(engine.r)
 if engine.r._selected_rule(move['id'])!=move['id']:raise ValueError('selected Rudolf Weather Ball source required')
 return dict(move,type=chosen)


def prepare_weather_ball(engine,actor,move,selected=None):
 """Select the sourced weather type before native costs and type overrides."""
 if move.get('id')!='move/웨더볼':
  if selected is not None:raise ValueError('weather type choice belongs only to Weather Ball')
  return move
 if '_weather_ball_type' in move:
  if selected not in (None,move['_weather_ball_type']):
   raise ValueError('prepared Weather Ball type changed')
  return move
 from source_context import verified_source
 verified_source(engine.r,{'file':'input/db/moves.csv','sha256':'ab83f872e5eca67a41db7d126b842f0165437e0fa70bb77ddad832a0b7396c93'},label='Weather Ball')
 if engine.r._selected_rule(move['id'])!=move['id']:raise ValueError('selected Weather Ball source required')
 prepared=prepare_sample_move(engine,actor,move)
 sample=prepared['type'] if prepared is not move else None
 mapping={'sunny':'불꽃','rain':'물','hail':'얼음','sandstorm':'바위'}
 choices=[sample] if sample else list(dict.fromkeys(mapping[w] for w in effective_weathers(engine,actor) if w in mapping)) or ['노말']
 if selected is None:
  if len(choices)!=1:raise ValueError('multiple weather types require an explicit Weather Ball type before Move cost')
  selected=choices[0]
 if selected not in choices:raise ValueError('Weather Ball type must match an actual effective weather')
 return dict(move,type=selected,_weather_ball_type=selected)


def prepare(engine,weather,rounds,source_id,origin,reason='',*,actor=None,policy=None):
 import homebrew_weather as HOME_WEATHER
 weather=HOME_WEATHER.canonical_weather(engine.r,weather)
 engine.r.mech(RULE)
 if weather not in KINDS:raise ValueError('explicit supported mechanical weather required')
 import nicolette_gym as GYM
 GYM.climate_scope(engine,weather,source_id,origin,actor)
 import ability_native_actions as NATIVE
 holder=NATIVE.weather_locked(engine)
 if holder is not None:raise ValueError('Air Lock holds normal weather: '+holder.entity_id)
 if origin not in ('move','ability','gm','natural','encounter') or not isinstance(source_id,str) or not source_id:raise ValueError('weather needs its producer and rule source')
 activation_id=NATIVE.weather_contract(engine,actor,source_id,weather,rounds) if origin=='ability' else None
 if not isinstance(reason,str):raise ValueError('weather reason must be text')
 import homebrew_weather as HOME_WEATHER
 override=HOME_WEATHER.require_request(engine,weather,rounds,source_id,origin,policy)
 reapplication=None
 if policy is not None:
  validate(engine)
  if origin!='move':raise ValueError('homebrew weather lifetime requires a native Move')
  reapplication=HOME_WEATHER.preflight(engine,weather,rounds,source_id,actor,policy)
 if rounds is None:
  if origin=='move' and policy is None:raise ValueError('move weather requires a finite duration')
 elif type(rounds) is not int or rounds<=0:raise ValueError('weather rounds must be a positive integer')
 import weather_duration_items as DURATION_ITEMS
 rounds,item_extension=DURATION_ITEMS.extend(actor,weather,rounds,origin)
 cursor=getattr(engine,'_initiative_cursor',None)
 count=None
 if rounds is not None and engine.round_start_seconds is not None:
  if not cursor or cursor.get('round')!=engine.round_no:raise ValueError('timed weather in an open round requires the current initiative count')
  count=cursor['count']
 result={'weather':weather,'source_id':source_id,'origin':origin,'reason':reason,'started_round':engine.round_no,'duration':rounds,'deadline_round':None if rounds is None else engine.round_no+rounds,'deadline_count':count}
 if activation_id is not None:result['ability_activation_id']=activation_id
 if item_extension is not None:result['item_extension']=item_extension
 if policy is not None:result.update(policy=deepcopy(policy),started_seconds=engine.elapsed_seconds)
 if override is not None:result.update(policy_override=override,started_seconds=engine.elapsed_seconds)
 if reapplication is not None:result['reapplication']=reapplication
 return result

def clear(engine,*,source_id=RULE,reason='cleared'):
 import environment_change as EC
 if EC.has_pending(engine) and not getattr(engine,'_environment_change_depth',0):
  return EC.run(engine,None,lambda e,c:clear(e,source_id=source_id,reason=reason))
 s=state(engine);old=s['active']
 if source_id in ('move/안개제거','ability/날씨부정','ability/에어록') and suppress_sample(engine,source_id=source_id,reason=reason):return deepcopy(old)
 for layer in s.get('layers',[]):
  __import__('researcher_fields').weather_ended(engine,layer)
  s['history'].append(dict(layer,ended_round=engine.round_no,end_source=source_id,end_reason=reason))
 if 'layers' in s:s['layers']=[]
 if old is not None:
  __import__('researcher_fields').weather_ended(engine,old)
  import weather_blessings as BLESSINGS
  BLESSINGS.retire(engine,old,source_id,reason)
 if old is not None:s['history'].append(dict(old,ended_round=engine.round_no,end_source=source_id,end_reason=reason))
 s['active']=None;engine.weather=None;engine.weather_rounds=None
 if 'nicolette' in s:s['nicolette']['suppression']=None
 import ability_state_projection as PROJECTION
 PROJECTION.weather_changed(engine)
 return deepcopy(old)

def set_weather(engine,weather,*,rounds=5,source_id=RULE,origin='gm',actor=None,reason='',policy=None):
 import homebrew_weather as HOME_WEATHER
 weather=HOME_WEATHER.canonical_weather(engine.r,weather)
 import environment_change as EC
 if EC.has_pending(engine) and not getattr(engine,'_environment_change_depth',0):
  return EC.run(engine,actor,lambda e,c:set_weather(e,weather,rounds=rounds,source_id=source_id,origin=origin,actor=c,reason=reason,policy=policy))
 if weather in (None,'none'):
  return clear(engine,source_id=source_id,reason=reason or 'cleared')
 record=prepare(engine,weather,rounds,source_id,origin,reason,actor=actor,policy=policy)
 import nicolette_gym as GYM
 scope=GYM.climate_scope(engine,weather,source_id,origin,actor)
 if scope is not None:
  s=state(engine)
  for old in s['layers']:s['history'].append(dict(old,ended_round=engine.round_no,end_source=source_id,end_reason='replaced'))
  s['sequence']+=1;record.update(id=s['sequence'],actor_id=actor.entity_id)
  record['climate_control']={'source':scope['source'],'reference':deepcopy(scope['reference']),
   'trainer_id':scope['trainer'].entity_id,'producer_id':actor.entity_id,'hail_id':scope['hail_id'],
   'occurrence_id':record['id'],'gm_id':scope['gm_id'],'reason':scope['reason']}
  s['layers']=[record]
  __import__('ability_state_projection').weather_changed(engine)
  engine.log('Weather sandstorm layered by adopted Climate Control',GYM.CLIMATE_SOURCE)
  return deepcopy(record)
 layered=__import__('researcher_fields').temperature_control_layer(engine,actor,record)
 if layered is not None:return layered
 clear(engine,source_id=source_id,reason='replaced')
 s=state(engine)
 s['sequence']+=1;record.update(id=s['sequence'],actor_id=None if actor is None else actor.entity_id)
 s['active']=record;engine.weather=weather;engine.weather_rounds=record['duration']
 if policy is not None:
  import weather_blessings as BLESSINGS
  BLESSINGS.grant(engine,actor,record)
 import ability_state_projection as PROJECTION
 PROJECTION.weather_changed(engine)
 engine.log('Weather '+weather+' from '+source_id,RULE)
 return deepcopy(record)

def observe_natural(engine,description,*,treat_as=None,reason=''):
 import homebrew_weather as HOME_WEATHER
 treat_as=HOME_WEATHER.canonical_weather(engine.r,treat_as)
 import environment_change as EC
 if EC.has_pending(engine) and not getattr(engine,'_environment_change_depth',0):
  return EC.run(engine,None,lambda e,c:observe_natural(e,description,treat_as=treat_as,reason=reason))
 if not isinstance(description,str) or not description.strip():raise ValueError('natural weather observation required')
 if treat_as not in KINDS|{None} or not isinstance(reason,str) or (treat_as is not None and not reason.strip()):raise ValueError('GM weather equivalence requires a reason')
 if treat_as is not None:prepare(engine,treat_as,None,RULE,'natural',reason)
 if not hasattr(engine,KEY) and engine.weather is not None:raise ValueError('classify existing unsourced weather before adding natural observations')
 s=state(engine)
 if treat_as is not None:
  set_weather(engine,treat_as,rounds=None,source_id=RULE,origin='natural',reason=reason)
 elif s['active'] and s['active']['origin']=='natural':clear(engine,reason='natural equivalence removed')
 s['natural']={'description':description,'equivalent':treat_as,'reason':reason,'round':engine.round_no}
 return deepcopy(s['natural'])

def boundary(engine,*,count=None,round_end=False):
 import field_effects as FIELD
 FIELD.local_boundary(engine,round_end=round_end)
 import ability_native_actions as NATIVE
 NATIVE.weather_boundary(engine,round_end=round_end)
 if not hasattr(engine,KEY):return False
 s=state(engine);record=s['active']
 changed=False
 for layer in list(s.get('layers',[])):
  if _expired(engine,layer,count=count,round_end=round_end):
   __import__('researcher_fields').weather_ended(engine,layer)
   s['layers'].remove(layer)
   s['history'].append(dict(layer,ended_round=engine.round_no,end_source=RULE,end_reason='duration expired'))
   changed=True
 suppression=s.get('nicolette',{}).get('suppression')
 if suppression and _expired(engine,suppression,count=count,round_end=round_end):
  s['nicolette']['suppression']=None;_sync_primary(engine);changed=True
 if changed:__import__('ability_state_projection').weather_changed(engine)
 if not record or record['duration'] is None:return True
 deadline=record['deadline_round'];at=record['deadline_count']
 expired=engine.round_no>deadline or engine.round_no==deadline and (round_end or at is not None and count is not None and count<=at)
 if expired:
  if __import__('researcher_fields').promote_layer(engine):engine.log('Weather duration expired',RULE);return True
  clear(engine,reason='duration expired');engine.log('Weather duration expired',RULE)
 else:
  include_current=at is None and not round_end and engine.round_start_seconds is not None
  engine.weather_rounds=max(1,deadline-engine.round_no+int(include_current))
 return True


def _expired(engine,record,*,count=None,round_end=False):
 if record.get('deadline_round') is None:return False
 deadline=record['deadline_round'];at=record['deadline_count']
 return engine.round_no>deadline or engine.round_no==deadline and (round_end or at is not None and count is not None and count<=at)
