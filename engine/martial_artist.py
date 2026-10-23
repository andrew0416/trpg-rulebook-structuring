"""Martial Artist consumers of native acquisition, actions, maneuvers and Move completion.

Optional reactions are armed before the actual event; only that native event
opens a scoped, one-use child action. Declarations remain public scripting APIs.
The class Ability and ranked Move acquisitions keep their existing owners.
"""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import json
import common_checks as C
import state_grants as G

_data=json.loads((Path(__file__).resolve().parents[1]/'data/martial-artist-definitions.json').read_text(encoding='utf8'))
DEFINITIONS=_data['features']; FEATURES=set(DEFINITIONS)
CLASS='class/무술가';TRAINING='feat/무술-훈련';KUNG='feat/내-쿵푸는-강해';ACHIEVEMENT='feat/무공';SECOND='feat/추가-공격'
ROCK='move/바위깨기';FOCUS='move/기충전';ARMED='martial_artist_armed';TAG='martial_artist_tag';WRESTLE='martial_artist_wrestlemania'
MANEUVERS={'maneuver/붙잡기','maneuver/밀기','maneuver/걸기','maneuver/무장해제'}


def records(a,feature=None,active=False):
 import trainer_feature_acquisition as T
 return [r['static_acquisition'] for _,r,live in T._static_records(a) if r['static_acquisition']['feature_id'] in FEATURES and (feature is None or r['static_acquisition']['feature_id']==feature) and (not active or live)]


def acquired(a,feature):
 rows=records(a,feature,True)
 if len(rows)>1 and feature!=TRAINING:raise ValueError('one actual Martial Artist Feature acquisition required')
 return rows[0] if rows else None


def acquisition_snapshot(e,a,feature,rank=None,moves=None):
 import trainer_feature_acquisition as T,acquired_features as A
 parents=[r['acquisition_request_id'] for r in a.spec.get(T.LEDGER_KEY,{}).values() if r['feature_id']==CLASS]
 snapshot={'parents':parents,'ability':T.martial_ability(a),'training_rank':A.owned_rule_count(a,TRAINING)}
 if feature==TRAINING:
  import skill_modifiers as S
  if type(moves) is not list or len(moves)!=2:raise ValueError('Martial Training selects exactly two Moves')
  snapshot.update(rank_number=rank,moves=[e.r.move_id(m) for m in moves],combat=S.rank(e.r,a,'전투')[2])
 return snapshot


def qualification(a,feature,snapshot,prerequisite_source):
 import trainer_feature_acquisition as T,acquisition_qualification as Q
 fields={'parents','ability','training_rank'}|({'rank_number','moves','combat'} if feature==TRAINING else set())
 if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!=fields:raise ValueError('exact Martial Artist acquisition observations required')
 known={r['acquisition_request_id'] for r in a.spec.get(T.LEDGER_KEY,{}).values() if r['feature_id']==CLASS}
 if type(snapshot['parents']) is not list or not snapshot['parents'] or not set(snapshot['parents'])<=known:raise ValueError('actual Martial Artist class acquisition required')
 if snapshot['ability'] not in _data['styles']:raise ValueError('actual chosen Martial Artist Ability required')
 C.integer(snapshot['training_rank'],'acquired Martial Training rank',0,3)
 checks=[Q.check('trainer','prerequisite',a.kind=='trainer','actual Trainer required')]
 if feature==TRAINING:
  C.integer(snapshot['rank_number'],'Martial Training rank',1,3)
  C.integer(snapshot['combat'],'Combat rank',0)
  if snapshot['training_rank']!=snapshot['rank_number']-1:raise ValueError('Martial Training must acquire its next rank')
  checks.append(Q.check('combat','prerequisite',snapshot['combat']>={1:3,2:5,3:6}[snapshot['rank_number']],'Martial Training printed Combat prerequisite required'))
 if feature==KUNG:checks.append(Q.check('training','prerequisite',snapshot['training_rank']>=1,'Martial Training Rank 1 required'))
 return Q.require(feature,'native','acquire',checks)


def style(a):
 import trainer_feature_acquisition as T
 if acquired(a,ACHIEVEMENT) is None:return None
 return _data['styles'][T.martial_ability(a)]


def require(e,a,feature=ACHIEVEMENT,achievement=None):
 import world_entities as W,trainer_feature_acquisition as T
 W.require_actors(e,a)
 if a.kind!='trainer' or acquired(a,feature) is None:raise ValueError('actual acquired Martial Artist Feature required: '+feature)
 T.martial_ability(a)
 if achievement is not None and style(a)!=achievement:raise ValueError('the chosen Martial Artist Ability does not grant '+achievement)
 return acquired(a,feature)


def arm(e,a,reaction,*,move=None,target=None,options=None):
 """Choose an optional reaction before its native trigger; no action/AP spent here."""
 feature=SECOND if reaction=='second_strike' else KUNG if reaction=='kung_fu' else ACHIEVEMENT
 require(e,a,feature,None if feature!=ACHIEVEMENT else reaction)
 if reaction not in ('kung_fu','second_strike','pummeling_momentum','bend_like_the_willow','soft_landing'):raise ValueError('unknown Martial Artist reaction')
 row={}
 if reaction=='second_strike':
  mid=e.r.move_id(move)
  if mid not in (ROCK,'struggle'):raise ValueError('Second Strike chooses Rock Smash or Struggle')
  row['move_id']=mid
 elif move is not None:raise ValueError('only Second Strike chooses a reaction Move')
 if target is not None:
  import world_entities as W
  W.require_actors(e,target)
  if reaction!='pummeling_momentum' or target is a or target.side==a.side:raise ValueError('Pummeling Momentum requires an actual foe')
  row['target_id']=target.entity_id
 if options is not None:
  if reaction!='bend_like_the_willow' or type(options) is not dict or not set(options)<=MANEUVERS:raise ValueError('Willow needs options for actual printed maneuvers')
  row['options']=deepcopy(options)
 return G.transition(e,a,lambda se,c:c.spec.setdefault(ARMED,{}).update({reaction:row}))


def disarm(e,a,reaction):
 return G.transition(e,a,lambda se,c:c.spec.get(ARMED,{}).pop(reaction,None))


def _pay(e,a,amount,source,action='free'):
 import action_points as AP,action_lifecycle as A,turn as T
 if AP.available(a)<amount:raise ValueError('Martial Achievement requires available AP')
 if action=='free':A.triggered_free_action(e,a,source)
 elif not T.spend(e,a,action,source):raise ValueError('Martial Achievement requires its '+action+' action')
 if amount:AP.spend(a,amount)


@contextmanager
def scope(e,a,source,mid,targets,**extra):
 previous=getattr(e,'_martial_artist_scope',None)
 e._martial_artist_scope={'actor':a,'source':source,'move_id':mid,'targets':tuple(targets),**extra}
 try:yield e._martial_artist_scope
 finally:
  if previous is None:vars(e).pop('_martial_artist_scope',None)
  else:e._martial_artist_scope=previous


def move_authority(e,a,t,mid,source):
 s=getattr(e,'_martial_artist_scope',None)
 if not s or s['actor'] is not a or s['source']!=source or s['move_id']!=mid or not any(x is t for x in s['targets']):return False
 if source not in FEATURES:return False
 require(e,a,source)
 return True


def _move(e,a,t,mid,source,*,effect_range=0):
 import action_lifecycle as A
 sid='martial-use:'+a.entity_id+':'+source
 with scope(e,a,source,mid,(t,),effect_range=effect_range):
  if mid not in a.moves and mid!='struggle':G.grant_moves(a,[mid],sid,'feature',owner_id=a.entity_id,lifetime='scene',rule_id=source,mode='permission')
  try:
   with A.move_grant(e,a,t,mid,source=source,kind='free') as token:
    return e.use_move(a,t,mid,free_action=True,count_use=True,_action_grant=token)
  finally:
   if sid in a.spec.get(G.KEY,{}).get('sources',{}):G.revoke(a,sid,engine=e)


def opportunity(e,a,t,ordinary):
 if 'kung_fu' not in a.spec.get(ARMED,{}) or acquired(a,KUNG) is None:return ordinary()
 require(e,a,KUNG)
 return _move(e,a,t,ROCK,KUNG,effect_range=2)


def effect_range(e,a,move):
 s=getattr(e,'_martial_artist_scope',None)
 return move.get('_martial_effect_range',s.get('effect_range',0) if s and s['actor'] is a and s['move_id']==move.get('id') else 0)


def prepare(e,a,move):
 bonus=effect_range(e,a,move)
 return dict(move,_martial_effect_range=bonus) if bonus else move


def _punch(e,a,move):
 import ability_transitions as A,equipment_variant_contracts as E
 return A.active(a,'ability/철주먹') and move.get('id') in E._punch_moves(e.r)


def after_move(e,row):
 """One actual completed Move, so Double Strike/Five Strike cannot double-credit."""
 import move_completion as MC
 a=row['actor'];tag=a.spec.get(TAG)
 hits=[t for t in MC.actual_recipients(row) if MC.recipient_result(row,t).get('hit') and not MC.recipient_result(row,t).get('cancelled') and t.side!=a.side]
 if tag and any(t.entity_id==tag['target_id'] for t in hits):
  tag['hit_turn']=a.custom_conditions.get('combat_turn_serial',0);_seal_tag(tag)
 if style(a)!='pummeling_momentum':return
 import skill_modifiers as S,action_points as AP
 choice=a.spec.get(ARMED,{}).get('pummeling_momentum')
 for t in hits:
  result=MC.recipient_result(row,t)
  event=getattr(e,'_passive_events',{}).get(result.get('child_event') or result.get('event_id'))
  move=MC.event_move(e,event) if event is not None else row.get('target_moves',{}).get(t.entity_id,row['move'])
  if not _punch(e,a,move):continue
  if tag and t.entity_id==tag['target_id']:
   rank=S.effective_rank(e.r,a,'전투')
   amount=max(tag['bonus'],min(rank,tag['bonus']+1))
   # The rank caps this gain; a withdrawn rank provider does not end an earned bonus.
   if amount!=tag['bonus'] or not {'earned_rank','legacy_validation'}.intersection(tag):
    _observe_gain(row,tag,amount,rank)
   _seal_tag(tag);continue
  if choice is None or choice.get('target_id',t.entity_id)!=t.entity_id or AP.available(a)<1:continue
  _pay(e,a,1,ACHIEVEMENT)
  tag={'target_id':t.entity_id,'bonus':1,'hit_turn':a.custom_conditions.get('combat_turn_serial',0),'completion_id':row['id'],'acquisition':acquired(a,ACHIEVEMENT)['request_id']}
  _observe_gain(row,tag,1,S.effective_rank(e.r,a,'전투'))
  _seal_tag(tag);a.spec[TAG]=tag;a.spec[ARMED].pop('pummeling_momentum',None);choice=None


def bonus(a,t):
 row=a.spec.get(TAG)
 return row['bonus'] if row and t is not None and row['target_id']==t.entity_id and style(a)=='pummeling_momentum' else 0


def end_turn(e,a):
 row=a.spec.get(TAG)
 if row and row['hit_turn']!=a.custom_conditions.get('combat_turn_serial',0):a.spec.pop(TAG,None)
 a.spec.pop(WRESTLE,None)


def maneuver_failed(e,a,t,source,*,opposed):
 """Called at the real failed accuracy/opposed phase, before another action."""
 if source not in MANEUVERS or a.side==t.side:return
 # The immediate attacker follow-up is armed once; nested reactions cannot loop.
 second=a.spec.get(ARMED,{}).get('second_strike')
 if opposed and second is not None and acquired(a,SECOND):
  a.spec[ARMED].pop('second_strike')
  _move(e,a,t,second['move_id'],SECOND)
 willow=t.spec.get(ARMED,{}).get('bend_like_the_willow')
 if willow is None or style(t)!='bend_like_the_willow' or not e.adjacent(a,t):return
 options=willow.get('options',{}).get(source)
 if options is None:return
 import action_points as AP
 if AP.available(t)<2:return
 t.spec[ARMED].pop('bend_like_the_willow');_pay(e,t,2,ACHIEVEMENT)
 with scope(e,t,ACHIEVEMENT,source,(a,),maneuver=True):
  if source=='maneuver/붙잡기':e.grapple(t,a,**options)
  elif source=='maneuver/밀기':e.push(t,a,**options)
  elif source=='maneuver/걸기':e.trip(t,a,**options)
  else:e.disarm(t,a,**options)


def spend_maneuver(e,a,t,source,ordinary='standard'):
 import action_lifecycle as A,turn as T
 cost=maneuver_cost(e,a,t,source,ordinary)
 if cost=='free' and ordinary!='free':
  A.triggered_free_action(e,a,source);return True
 return T.spend(e,a,cost,source)


def maneuver_cost(e,a,t,source,ordinary='standard'):
 s=getattr(e,'_martial_artist_scope',None)
 return 'free' if s and s.get('maneuver') and move_authority(e,a,t,source,ACHIEVEMENT) else ordinary


def heightened_intensity(e,a):
 require(e,a,achievement='heightened_intensity')
 def apply(se,c):
  _pay(se,c,2,ACHIEVEMENT,'shift')
  return _move(se,c,c,FOCUS,ACHIEVEMENT)
 return G.transition(e,a,apply,include_rulings=True)


def wrestlemania(e,a):
 require(e,a,achievement='wrestlemania')
 import grapple_state as GS
 row=GS.relation(e,a)
 if row is None or not GS._turn(e,a,row):raise ValueError('Wrestlemania requires Dominance at actual turn start')
 serial=a.custom_conditions['combat_turn_serial']
 if a.spec.get(WRESTLE)==serial:raise ValueError('Wrestlemania is already active this turn')
 def apply(se,c):
  _pay(se,c,1,ACHIEVEMENT,'swift');c.spec[WRESTLE]=serial
 return G.transition(e,a,apply)


def grapple_pair(e,a,actions):
 require(e,a,achievement='wrestlemania')
 if a.spec.get(WRESTLE)!=a.custom_conditions.get('combat_turn_serial'):raise ValueError('activate Wrestlemania this turn first')
 if type(actions) is not list or len(actions)!=2 or any(type(x) is not dict for x in actions):raise ValueError('choose two different grappling effects')
 kinds=[x.get('kind') for x in actions]
 if len(set(kinds))!=2 or not set(kinds)<={'secure','attack','drag','end'} or kinds[0]=='end':raise ValueError('choose two different executable dominant grappling effects')
 def apply(se,c):
  import turn as T
  if not T.spend(se,c,'full',ACHIEVEMENT):raise ValueError('Wrestlemania pair requires one Full Action')
  with scope(se,c,ACHIEVEMENT,'grapple_pair',(),grapple_pair=True):
   import grapple_state as GS
   results=[]
   for choice in actions:
    relation=GS.relation(se,c)
    if relation is None:break  # A first effect may end the Grapple by fainting a participant.
    result=se.grapple_action(c,**deepcopy(choice))
    if result is False or isinstance(result,C.PendingDecision):raise ValueError('selected Wrestlemania effect must resolve')
    results.append(result)
   return results
 return G.transition(e,a,apply,include_rulings=True,include_grid=True)


def grapple_action_cost(e,a):
 s=getattr(e,'_martial_artist_scope',None)
 return 'free' if s and s['actor'] is a and s.get('grapple_pair') else 'full'


def soft_landing_fall(e,a,**options):
 require(e,a,achievement='soft_landing')
 if options.get('meters',0)<=0:raise ValueError('actual positive fall distance required')
 def apply(se,c):
  _pay(se,c,1,ACHIEVEMENT)
  with scope(se,c,ACHIEVEMENT,'fall',(),fall=True):return se.falling_damage(c,**options)
 return G.transition(e,a,apply,include_rulings=True)


def fall_reduction(e,a):
 s=getattr(e,'_martial_artist_scope',None)
 if not s or s['actor'] is not a or not s.get('fall'):return 0
 import skill_modifiers as S,arithmetic_policy as M
 return M.ratio(S.effective_rank(e.r,a,'전투'),2)


def miss_effects(e,a,move,effects):
 if move.get('id') not in ('move/점프킥','move/무릎차기') or 'soft_landing' not in a.spec.get(ARMED,{}) or style(a)!='soft_landing':return effects
 import action_points as AP
 loss=[x for x in effects if x.get('type')=='hp_loss' and x.get('target')=='self' and x.get('on_miss')]
 if not loss or AP.available(a)<1:return effects
 _pay(e,a,1,ACHIEVEMENT);a.spec[ARMED].pop('soft_landing')
 return [x for x in effects if x not in loss]


def whirlwind_strikes(e,a,targets):
 require(e,a,achievement='whirlwind_strikes')
 import world_entities as W
 if type(targets) not in (list,tuple) or not targets or len({id(t) for t in targets})!=len(targets):raise ValueError('distinct adjacent Whirlwind foes required')
 W.require_actors(e,a,*targets)
 if any(t is a or t.side==a.side or not e.adjacent(a,t) or not t.on_field or t.fainted for t in targets):raise ValueError('Whirlwind targets must be actual adjacent foes')
 def apply(se,c,*foes):
  import action_lifecycle as A,move_activation as M,combat_timing as T
  count=T.current(se);_pay(se,c,1,ACHIEVEMENT,'full')
  T.install(se,c,{'source':ACHIEVEMENT,'martial_whirlwind':True,'count_deadline':(se.round_no+1,count),'encounter_end':True})
  total=0
  with scope(se,c,ACHIEVEMENT,ROCK,foes):
   with M.open_scope(se,c,ROCK,foes,shared=False,primary=foes[0]) as (activation,accuracy):
    for i,t in enumerate(foes):
     with A.move_grant(se,c,t,ROCK,source=ACHIEVEMENT if i==0 else 'same_move_activation',kind='free' if i==0 else None) as token:
      result=se.use_move(c,t,ROCK,count_use=i==0,free_action=i==0,_action_grant=token,_activation=activation,_shared_accuracy=accuracy)
     total+=result
     if M.note_result(se,activation,result):break
  return total
 return G.transition(e,a,apply,participants=tuple(targets),include_rulings=True)


def unflanked(a):
 import combat_timing as T
 return any(x.get('martial_whirlwind') for x in T.records(a)) and style(a)=='whirlwind_strikes'


def withdraw(e,a,feature):
 if feature not in FEATURES and feature!=CLASS:return
 if feature in (ACHIEVEMENT,CLASS):
  a.spec.pop(TAG,None);a.spec.pop(WRESTLE,None)
  import combat_timing as T
  for row in list(T.records(a)):
   if row.get('martial_whirlwind'):T.expire(e,a,row)
 for key in list(a.spec.get(ARMED,{})):
  if feature==CLASS or feature==SECOND and key=='second_strike' or feature==KUNG and key=='kung_fu' or feature==ACHIEVEMENT and key not in ('second_strike','kung_fu'):a.spec[ARMED].pop(key)


def validate(e):
 import world_entities as W,skill_modifiers as S,move_completion as MC
 index=W.actor_index(e)
 for a in index.values():
  armed=a.spec.get(ARMED,{})
  if type(armed) is not dict:raise ValueError('Martial Artist arming must be a mapping')
  for key,row in armed.items():
   if type(row) is not dict:raise ValueError('Martial Artist reaction declaration required')
   feature=KUNG if key=='kung_fu' else SECOND if key=='second_strike' else ACHIEVEMENT
   require(e,a,feature,None if feature!=ACHIEVEMENT else key)
   if key=='second_strike' and (set(row)!={'move_id'} or row['move_id'] not in (ROCK,'struggle')):raise ValueError('Second Strike reaction choice changed')
   if key=='pummeling_momentum' and ('target_id' in row and row['target_id'] not in index):raise ValueError('Pummeling foe is missing')
  tag=a.spec.get(TAG)
  if tag is not None:
   require(e,a,achievement='pummeling_momentum')
   fields={'target_id','bonus','hit_turn','completion_id','acquisition','fingerprint'}
   if set(tag) not in (fields,fields|{'earned_rank'},fields|{'legacy_validation'}) or tag['target_id'] not in index or tag['acquisition']!=acquired(a,ACHIEVEMENT)['request_id']:raise ValueError('Pummeling Momentum provenance changed')
   import root_resolution as R
   if tag['fingerprint']!=R.fingerprint({k:v for k,v in tag.items() if k!='fingerprint'}):raise ValueError('Pummeling Momentum observation changed')
   if 'legacy_validation' in tag:
    legacy=tag['legacy_validation']
    if type(legacy) is not dict or set(legacy)!={'tag','rank_at_load'} or type(legacy['tag']) is not dict or set(legacy['tag'])!=fields:raise ValueError('Pummeling legacy validation changed')
    original=legacy['tag'];cap=C.integer(original['bonus'],'Pummeling accepted legacy bonus',1)
    C.integer(legacy['rank_at_load'],'Pummeling legacy rank at load',cap)
    if original['fingerprint']!=R.fingerprint({k:v for k,v in original.items() if k!='fingerprint'}):raise ValueError('Pummeling legacy fingerprint changed')
    if any(tag[k]!=original[k] for k in fields-{'fingerprint','hit_turn'}):raise ValueError('Pummeling legacy validation changed')
   else:
    cap=C.integer(tag['earned_rank'],'Pummeling earned rank',1) if 'earned_rank' in tag else S.effective_rank(e.r,a,'전투')
   C.integer(tag['bonus'],'Pummeling Momentum bonus',1,cap);C.integer(tag['hit_turn'],'Pummeling hit turn',0)
   completed=getattr(e,'_move_completions',{}).get(tag['completion_id'])
   result=MC.recipient_result(completed,index[tag['target_id']]) if completed is not None else None
   if completed is None or completed['phase']!='complete' or completed['actor'] is not a or not result or not result.get('hit') or result.get('cancelled'):raise ValueError('Pummeling Momentum requires its actual completed hit')
   if 'earned_rank' not in tag and TAG in completed:raise ValueError('Pummeling Momentum earned-rank observation missing')
   if 'earned_rank' in tag:
    observation=completed.get(TAG)
    expected={k:tag[k] for k in ('target_id','bonus','completion_id','acquisition','earned_rank')}
    if observation!=expected:raise ValueError('Pummeling Momentum earned-rank observation changed')
  if WRESTLE in a.spec:
   require(e,a,achievement='wrestlemania');C.integer(a.spec[WRESTLE],'Wrestlemania actual turn',1)


def _seal_tag(row):
 import root_resolution as R
 row['fingerprint']=R.fingerprint({k:v for k,v in row.items() if k!='fingerprint'})


def _observe_gain(completed,tag,amount,rank):
 # Keep the native producer's observation after rank providers are changed or withdrawn.
 C.integer(amount,'Pummeling Momentum bonus',1,rank)
 tag.pop('legacy_validation',None)
 tag.update(bonus=amount,earned_rank=rank,completion_id=completed['id'])
 completed[TAG]={k:tag[k] for k in ('target_id','bonus','completion_id','acquisition','earned_rank')}


def upgrade_legacy(e):
 """At load only, retain an old tag that passes its original current-rank bound."""
 import world_entities as W,skill_modifiers as S
 tags=[(a,a.spec[TAG]) for a in W.actor_index(e).values() if TAG in a.spec and
       type(a.spec[TAG]) is dict and not {'earned_rank','legacy_validation'}.intersection(a.spec[TAG])]
 if not tags:return
 validate(e)
 for actor,tag in tags:
  # This proves acceptance at load, not the unrecorded rank of a past gain.
  tag['legacy_validation']={'tag':deepcopy(tag),'rank_at_load':S.effective_rank(e.r,actor,'전투')}
  _seal_tag(tag)
