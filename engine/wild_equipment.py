"""PTK bait and actual capture-technique context, ch09:67-73/ch04:376-406.
Unspecified encounter selection and qualitative party-level match are GM facts.
A bait-distraction Standard replaces the real action; it never grants an action.
"""
from copy import deepcopy
from dataclasses import asdict
import common_checks as C
import turn as TURN
import action_lifecycle as ACTION

CAPTURE_SOURCE='ch04-trainer-classes/입문-클래스/포획전문가'
TECHNIQUES={'덫':'Snare','작업 도구':'Tools of the Trade'}

def _p():
 import pokemon_activities
 return pokemon_activities

def _selected(e,uid):
 if e.r._selected_rule(uid)!=uid:raise ValueError('selected wild-equipment source needs its own policy')

def _wild(e,target):
 P=_p();P._pokemon(target);P._text(target.spec.get('id'),'wild Pokemon identity')
 if not target.spec.get('wild',target.side=='wild') or target.spec.get('trainer_id') or target.spec.get('trainer') or target.captured or target.dead or target.fainted or target.hp<=0:raise ValueError('conscious unowned wild Pokemon required')
 if target not in list(e.everyone or [])+list(e.gm.everyone or []):raise ValueError('actual encountered Pokemon required')

def technique(e,actor,name):
 import capture_techniques as CAPTURE,trainer_feature_acquisition as TFA
 if any(row.get('adapter_id')==CAPTURE.ADAPTER for row in actor.spec.get(TFA.LEDGER_KEY,{}).values()):
  _selected(e,CAPTURE_SOURCE)
  return name in CAPTURE.selected(actor)
 choices=actor.spec.get('capture_techniques',[])
 if not isinstance(choices,list):raise ValueError('acquired Capture Techniques must be an explicit list')
 alias=TECHNIQUES[name]
 if name not in choices and alias not in choices:return False
 canonical=[next((name for name,alias in TECHNIQUES.items() if x in (name,alias)),x) for x in choices]
 if len(canonical)!=len(set(canonical)):raise ValueError('duplicate acquired Capture Techniques')
 _selected(e,CAPTURE_SOURCE);_selected(e,'class/포획전문가');P=_p();owned=actor.spec.get('feats',[])
 if not any(x in ('class/포획전문가','포획전문가','Capture Specialist') for x in list(actor.spec.get('classes',[]))+owned):raise ValueError('acquired Capture Specialist required')
 physical=[P._rank(e,actor,s) for s in ('곡예','육상','은신','생존')];social=[P._rank(e,actor,s) for s in ('교활','통찰')]
 if max(physical)<3 or max(social)<3:raise ValueError('Capture Specialist Novice physical and social prerequisites required')
 advanced='feat/고급-포획-테크닉';ranks=actor.spec.get('feat_ranks',{}).get(advanced,0);C.integer(ranks,'Advanced Capture Techniques rank',0,4)
 if ranks:
  _selected(e,advanced)
  if advanced not in owned and '고급 포획 테크닉' not in owned:raise ValueError('actual Advanced Capture Techniques required')
  required_rank=4 if ranks==2 else 5 if ranks>=3 else 0
  if required_rank and sum(r>=required_rank for r in physical+social)<(3 if ranks==4 else 2):raise ValueError('Advanced Capture Techniques prerequisites unmet')
 if len(choices)>2+2*ranks:raise ValueError('acquired capture technique allowance exceeded')
 return True

def comparable_party(e,actor,target,party,reason):
 P=_p();P._text(reason,'GM comparable party-level decision')
 if not isinstance(party,list) or not party or len({id(p) for p in party})!=len(party):raise ValueError('actual comparable trainer party required')
 import world_entities as WORLD,pokemon_party as PARTY
 actors=WORLD.require_actors(e,actor,target,*party)
 for member in party:P._pokemon(member);P._owner(actor,member);PARTY.require_participation(e,member,acting=False)
 registered=actor.spec.get('pokemon_registry')
 carried={uid for uid,row in registered.items() if row.get('location')=='carried'} if registered is not None else {uid for uid,p in actors.items() if p.kind=='pokemon' and p.spec.get('trainer_id')==actor.spec['id']}
 if {p.spec['id'] for p in party}!=carried:
  raise ValueError('comparable party must include the actual carried roster')
 return {'party_levels':{p.spec['id']:p.level for p in party},'target_level':target.level,'gm_level_match_reason':reason}

def attract(e,actor,*,phase,bait_id,target=None,party=None,level_match_reason=None,fixed=None,habitat=None):
 import state_grants as G,world_entities as WORLD
 if party is not None and not isinstance(party,list):raise ValueError('actual comparable trainer party required')
 participants=([target] if target is not None else [])+list(party or [])
 WORLD.require_actors(e,actor,*participants)
 return G.transition(e,actor,lambda se,sa,*ps:_attract(se,sa,phase=phase,bait_id=bait_id,
  target=ps[0] if target is not None else None,party=list(ps[1:] if target is not None else ps) if party is not None else None,
  level_match_reason=level_match_reason,fixed=fixed,habitat=habitat),participants=participants)

def _attract(e,actor,*,phase,bait_id,target=None,party=None,level_match_reason=None,fixed=None,habitat=None):
 import encounter_candidates as CANDIDATES
 P=_p();P._outside(e);P._text(bait_id,'placed bait identity');profile=CANDIDATES.equipment(e.r,'미끼')
 records=actor.spec.get('placed_bait',{});record=records.get(bait_id)
 if phase!='place' and habitat is not None and not (record and 'regional_candidates' not in record and phase=='select'):
  raise ValueError('regional bait habitat is fixed at placement')
 if phase=='place':
  if record is not None or target is not None or party is not None or fixed is not None or level_match_reason is not None:raise ValueError('fresh bait placement does not roll or select an encounter')
  pool=CANDIDATES.bait_pool(e.r,habitat)
  from crafting_activities import _inventory
  import state_grants as G,frequency as F
  alluring=actor.kind=='pokemon' and '매혹' in G.effective_capabilities(actor)
  if alluring:
   e.r._selected_rule('capability/매혹')
   if not F.activation_allowed(actor,'capability/매혹','하루',engine=e):raise ValueError('Alluring already used today')
   F.consume_activation(actor,'capability/매혹','하루',engine=e)
  else:
   key=_inventory(actor,'미끼',1)
   actor.spec['items'][key]-=1
  record={'id':bait_id,'source':profile['source'],'attraction_source':'capability/매혹' if alluring else profile['source'],'unit_price':profile['price'],'owner_id':actor.spec['id'],'placed_at':e.elapsed_seconds,'misses':0,'status':'placed','checks':[],'regional_candidates':pool}
  actor.spec.setdefault('placed_bait',{})[bait_id]=record
  return deepcopy(record)
 if not record or record.get('owner_id')!=actor.spec['id']:raise ValueError('actual placed bait required')
 if record.get('source')!=profile['source']:raise ValueError('placed bait source differs from the selected equipment')
 pool=record.get('regional_candidates')
 if pool is None and phase=='select':
  pool=CANDIDATES.bait_pool(e.r,habitat);record['regional_candidates']=pool
 if pool is not None:CANDIDATES.validate_pool(e.r,pool)
 if phase=='select':
  if record['status']!='awaiting_encounter' or target is not None or party is not None or fixed is not None or level_match_reason is not None:raise ValueError('successful attraction before random regional selection required')
  record['regional_selection']=CANDIDATES.select(e,pool,random_choice=True,previous=record.get('regional_selection'))
  return deepcopy(record)
 if phase=='wait':
  if record['status']!='placed' or target is not None or party is not None or level_match_reason is not None:raise ValueError('only placed bait can wait without choosing the encounter')
  if fixed is not None:C.integer(fixed,'bait attraction d20',1,20)
  import style_expert as STYLE
  bonus=tools_bonus(e,actor,'attraction')+STYLE.lure_bonus(actor)
  import capability_parameter_edges as PARAMETERS,state_grants as G
  if record.get('attraction_source')=='capability/매혹' and actor.kind=='pokemon' and '매혹' in G.effective_capabilities(actor):bonus+=PARAMETERS.enticing_bonus(actor)
  e.advance_time(900,[actor]);face=fixed if fixed is not None else e.d20();result={'natural':face,'bonus':bonus,'total':face+bonus,'dc':15,'at':e.elapsed_seconds};record['checks'].append(result)
  if face+bonus>=15:record['status']='awaiting_encounter'
  else:
   record['misses']+=1
   if record['misses']>=3:record['status']='consumed_without_encounter'
  return dict(deepcopy(record),captured=False)
 if phase!='encounter' or record['status']!='awaiting_encounter' or fixed is not None:raise ValueError('successful attraction before GM encounter selection required')
 _wild(e,target);CANDIDATES.require_target(e.r,pool,record.get('regional_selection'),target)
 record.update(status='encountered',target_id=target.spec['id'],**comparable_party(e,actor,target,party,level_match_reason))
 return dict(deepcopy(record),target=target,captured=False)

def lure_loss(e,actor,state,*,target,cause,lost,reason,party=None,level_match_reason=None):
 """The source says a lure may be lost; the actual event and outcome are GM facts."""
 import encounter_candidates as CANDIDATES
 P=_p();CANDIDATES.equipment(e.r,'루어');P._text(reason,'GM observed lure-loss reason')
 if state['attachment']!='루어' or type(lost) is not bool or cause not in ('line_broken','escaped'):raise ValueError('actual lure and explicit possible loss outcome required')
 if state.get('lure_loss') is not None:raise ValueError('possible lure loss already resolved')
 if cause=='escaped' and state['status']!='escaped':raise ValueError('actual fishing escape required before possible lure loss')
 if cause=='line_broken' and state['status']!='hooked':raise ValueError('actual hooked line required before an observed break')
 _wild(e,target)
 if state.get('target_id') not in (None,target.spec['id']):raise ValueError('lure loss target differs from the actual hooked Pokemon')
 pool=state.get('regional_candidates')
 if pool is not None:CANDIDATES.require_target(e.r,pool,state.get('regional_selection'),target)
 if state['source']=='item/미끼' and state.get('target_id') is None:
  state.update(comparable_party(e,actor,target,party,level_match_reason))
 elif party is not None or level_match_reason is not None:raise ValueError('party comparison already belongs to the actual hooked occurrence')
 state['target_id']=target.spec['id']
 state['lure_loss']={'cause':cause,'lost':lost,'reason':reason,'target_id':target.spec['id'],'at':e.elapsed_seconds,'source':'item/루어'}
 if cause=='line_broken':state['status']='line_broken'
 if lost:actor.spec['items']['루어']-=1
 return deepcopy(state)

def distract(e,actor,*,target,**roll_options):
 P=_p();_wild(e,target);_selected(e,'item/미끼')
 if target.spec.get('bait_distraction',{}).get('status')=='distracted':raise ValueError('target already has an unresolved bait distraction')
 from crafting_activities import _inventory
 key=_inventory(actor,'미끼',1);prepared=P._preflight(e,target,'집중',roll_options)
 if not TURN.spend(e,actor,'standard','미끼 던지기'):return False
 actor.spec['items'][key]-=1
 check=C.against_dc(e.skill_roll(target,'집중',**prepared),12)
 record={'source':'item/미끼','actor_id':actor.spec['id'],'target_id':target.spec['id'],'check':asdict(check),'status':'resisted' if check.passed else 'distracted','at':e.elapsed_seconds}
 target.spec['bait_distraction']=record
 return {'activity':'distract_bait','check':check,'status':record['status']}

def pending(actor):
 record=actor.spec.get('bait_distraction',{})
 return record.get('source')=='item/미끼' and record.get('target_id')==actor.spec.get('id') and record.get('status')=='distracted'

def replace_standard(e,actor):
 """Call only after native Standard permission and budget checks have passed."""
 if not pending(actor):return False
 if e.encounter_active and (actor.injuries>=5 and not __import__('taskmaster').ignores_acting_loss(actor)):raise ValueError('bait eating Standard needs a reviewed heavy-injury action adapter')
 budget=getattr(actor,'budget',None)
 if budget is not None:
  if budget.get('standard',0)<=0:return False
  budget['standard']-=1
 ACTION.record_action(e,actor,'standard');record=actor.spec['bait_distraction'];record.update(status='eaten',eaten_at=e.elapsed_seconds,eaten_round=e.round_no)
 e.log('    '+actor.name+': 다음 기본 행동을 미끼 먹기에 사용','item/미끼')
 return True

def snare_bonus(e,actor,target,*,conversion=None):
 if conversion is not None:
  if type(conversion) is not dict or set(conversion)!={'modifier','reason','scope'} or conversion['scope']!='this_capture_roll':raise ValueError('explicit GM Snare conversion modifier/reason/this_capture_roll scope required')
  C.integer(conversion['modifier'],'GM Snare capture modifier')
  if not isinstance(conversion['reason'],str) or not conversion['reason'].strip():raise ValueError('GM Snare conversion reason required')
 if not technique(e,actor,'덫'):
  if conversion is not None:raise ValueError('GM Snare conversion requires actual acquired Snare')
  return 0
 import capture_techniques as CAPTURE,trainer_feature_acquisition as TFA
 if any(row.get('adapter_id')==CAPTURE.ADAPTER for row in actor.spec.get(TFA.LEDGER_KEY,{}).values()):
  import capture_resolution as RESOLUTION
  RESOLUTION.bind_native(e.r)
  selected_conversion=e.r.mech('pokemon/capture-rate').get('ball_modifier_conversion')
  if conversion is None and selected_conversion!='구판 1d100 보정치의 부호를 뒤집고 5로 나눈다 (슈퍼볼 +2, 하이퍼볼 +3, 타이머볼 -1→+4, 포획전문가의 덫 +2)':
   raise ValueError('Book Snare requires explicit selected errata-ball-mod-conversion for modern capture; Book -10 action is separate')
 # Only native physical producers establish bait distraction or a real net.
 import net_capsule as NET
 return (2 if conversion is None else conversion['modifier']) if pending(target) or NET.active(target) is not None else 0

ACTIVITIES={'attract_bait':attract,'distract_bait':distract}

def tools_bonus(e,actor,kind):
 if kind not in ('accuracy','fishing_reel','attraction'):raise ValueError('unsupported Tools of the Trade check')
 return (4 if kind=='attraction' else 2) if technique(e,actor,'작업 도구') else 0
