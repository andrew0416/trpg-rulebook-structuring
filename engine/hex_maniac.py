"""Hex Maniac choices over acquired sources, native activations and frequency."""
from copy import deepcopy
import common_checks as C
import state_grants as G

CLASS='class/오컬트마니아';STUDIES='feat/오컬트-마니아-연구'
DIFFUSE='feat/확산되는-통증';MALEDICTION='feat/악담';GRAND='feat/위대한-마법'
HEX='move/병상첨병';SPITE='move/원한';CURSE='move/저주'
BODY='ability/저주받은바디';OMEN='ability/징조'
SOURCE_SHA256='a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'
FEATURES={CLASS:(2894,2896),STUDIES:(2898,2913),DIFFUSE:(2917,2922),MALEDICTION:(2924,2929),GRAND:(2931,2936)}
DEFINITIONS={u:{'span':list(span),'catalog_span':[2885,2885] if u==CLASS else [2898,2915] if u==STUDIES else list(span),
 'clause_id':'input/ch04-trainer-classes.md:'+str(span[0])+'-'+str(span[1]),
 'parent':None if u==CLASS else CLASS if u==STUDIES else STUDIES,
 'ranked':u==STUDIES,'stat_tags':['hp']} for u,span in FEATURES.items()}
STATUS_MOVES={'move/이상한빛':'혼란',CURSE:'저주','move/최면술':'잠듦',SPITE:'사슬묶기','move/도깨비불':'화상'}


def records(actor,feature=None,active=False):
 import trainer_feature_acquisition as T
 return [r['static_acquisition'] for _,r,live in T._static_records(actor)
  if r['static_acquisition']['feature_id'] in FEATURES and (feature is None or r['static_acquisition']['feature_id']==feature) and (not active or live)]


def acquired(actor,feature):
 rows=records(actor,feature,True)
 return rows[-1] if rows else None


def acquisition_snapshot(e,actor,feature,rank,selection):
 import skill_modifiers as SK,class_move_grants as MOVES
 if feature==CLASS:
  if type(selection)is not dict or set(selection)!={'ability'} or selection['ability'] not in (BODY,OMEN):raise ValueError('select exactly Cursed Body or Omen')
 elif feature==STUDIES:
  if type(selection)is not dict or set(selection)!={'moves'}:raise ValueError('select exactly two Studies Moves')
  allowed=[mid for level,mids in MOVES.RANKED[STUDIES].items() if level<=rank for mid in mids]
  selection={'moves':MOVES._pair(e.r,selection['moves'],allowed)}
  previous=[mid for row in records(actor,STUDIES,True) for mid in row['snapshot']['selection']['moves']]
  if set(selection['moves'])&set(previous):raise ValueError('Studies learns distinct Moves at every rank')
 elif selection is not None:raise ValueError('this Hex Maniac Feature has no selection')
 parent=DEFINITIONS[feature]['parent']
 return {'rank':SK.rank(e.r,actor,'오컬트학')[2],'rank_number':rank if feature==STUDIES else None,
  'parents':[r['request_id'] for r in records(actor,parent,True)] if parent else [],
  'studies_rank':actor.spec.get('feat_ranks',{}).get(STUDIES,0),'selection':deepcopy(selection)}


def qualification(actor,feature,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'rank','rank_number','parents','studies_rank','selection'}:raise ValueError('actual Hex Maniac acquisition observations required')
 C.integer(snapshot['rank'],'actual Occult Education rank',1,6)
 C.integer(snapshot['studies_rank'],'actual Studies prerequisite rank',0,3)
 rank=snapshot['rank_number'];selection=snapshot['selection'];parent=DEFINITIONS[feature]['parent']
 if feature==CLASS:
  if type(selection)is not dict or set(selection)!={'ability'} or selection['ability'] not in (BODY,OMEN):raise ValueError('exact printed Ability selection required')
 elif feature==STUDIES:
  import class_move_grants as MOVES
  C.integer(rank,'actual Studies rank',1,3)
  allowed={actor.r.move_id(mid) for level,mids in MOVES.RANKED[STUDIES].items() if level<=rank for mid in mids}
  if type(selection)is not dict or set(selection)!={'moves'} or type(selection['moves'])is not list or len(selection['moves'])!=2 or len(set(selection['moves']))!=2 or not set(selection['moves'])<=allowed:raise ValueError('exact two printed rank-eligible Studies Moves required')
 elif selection is not None:raise ValueError('unselected Hex Maniac Feature')
 if feature!=STUDIES and rank is not None:raise ValueError('unranked Hex Maniac Feature')
 known={r['request_id'] for r in records(actor,parent)} if parent else set()
 minimum=3 if feature==CLASS else 6 if feature==GRAND else 5 if feature==MALEDICTION or feature==STUDIES and rank==3 else 0
 return Q.require(feature,'native','acquire',[
  Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
  Q.check('parent','prerequisite',parent is None or bool(snapshot['parents']) and set(snapshot['parents'])<=known,'actual acquired parent required'),
  Q.check('studies','prerequisite',feature not in (DIFFUSE,MALEDICTION,GRAND) or snapshot['studies_rank']>=(3 if feature==GRAND else 1),'printed Studies prerequisite rank required'),
  Q.check('rank','prerequisite',snapshot['rank']>=minimum,'printed Occult Education rank required')])


def after_acquire(e,actor,feature,sid):
 selection=G.state(actor)['sources'][sid]['static_acquisition']['snapshot']['selection']
 G.stat(actor,'hp',1,sid,operation_id='acquisition_stat_tag')
 if feature==CLASS:
  ability=selection['ability']
  if e.r._selected_rule(ability)!=ability:raise ValueError('exact selected Hex Maniac Ability required')
  name=G.ability_grant(e.r,{'grant_ability':e.r.selection.units[ability]['title']},CLASS)
  G.grant(actor,'abilities',name,sid,'feature',owner_id=actor.entity_id,lifetime='while_owned',rule_id=CLASS)
  e.register_abilities_one(actor,name)
 if feature==STUDIES:__import__('class_move_grants').register_all(e,actor)


def validate_acquisition(actor,record,sid,active):
 if not active:return
 state=actor.spec.get(G.KEY,{})
 if state.get('stat_sources',{}).get('hp',{}).get('sources',{}).get(sid,{}).get('acquisition_stat_tag')!={'delta':1,'minimum':None}:raise ValueError('actual Hex Maniac HP stat tag required')
 feature=record['feature_id'];chosen=record['snapshot']['selection']
 if feature==CLASS:
  name=G.ability_grant(actor.r,{'grant_ability':actor.r.selection.units[chosen['ability']]['title']},CLASS)
  if name not in state['sources'][sid].get('grants',{}).get('abilities',[]):raise ValueError('actual chosen Hex Maniac Ability source required')
 if feature==STUDIES:
  rank=record['snapshot']['rank_number'];choices=actor.spec.get('feature_choices',{}).get(STUDIES,[])
  if len(choices)<rank or choices[rank-1]!=chosen['moves']:raise ValueError('actual Studies selection projection changed')


def require(e,actor,feature):
 __import__('world_entities').require_actors(e,actor)
 if e.r._selected_rule(feature)!=feature or not acquired(actor,feature):raise ValueError('actual acquired Hex Maniac Feature required: '+feature)
 __import__('trainer_feature_acquisition').validate_actor(actor)


def studies_moves(actor):
 sid='feature:'+actor.entity_id+':'+STUDIES
 row=actor.spec.get(G.KEY,{}).get('sources',{}).get(sid,{})
 if not acquired(actor,STUDIES) or row.get('class_move_projection')!=1:return set()
 return set(row.get('grants',{}).get('moves',[]))


def _status_move(e,actor,mid):
 require(e,actor,STUDIES)
 if mid not in studies_moves(actor) or e.r.move(mid)['class']!='변화':raise ValueError('actual Studies-granted Status Move required')


def _swift(e,actor,source,ap):
 import action_points as AP,turn as TURN
 if AP.available(actor)<ap:raise ValueError('Hex Maniac requires available AP')
 if not TURN.spend(e,actor,'swift',source):raise ValueError('Hex Maniac requires available Swift Action')
 AP.charge(actor,ap)


def _event(e,event_id):
 import move_completion as COMPLETE,initiative_interrupts as INTERRUPTS
 receipt=COMPLETE.require_returned_event(e,event_id)
 event=e._passive_events[event_id];parent=event.get('defense_parent',event_id)
 INTERRUPTS._trigger(e,{'kind':'move','event_id':parent})
 return receipt,e._move_completions[receipt['completion_id']]


def attack_interested(e,actor,target,move):
 import ability_transitions as ABILITY
 return bool((move['id']==HEX and acquired(actor,GRAND)) or ABILITY.active(target,BODY)
  or SPITE in studies_moves(target) or any(acquired(c,MALEDICTION) for c in e.everyone))


def _enemy(a,b):return bool(a.side and b.side and a.side!=b.side)


def malediction_trigger(e,actor,event_id):
 require(e,actor,MALEDICTION)
 receipt,row=_event(e,event_id)
 import move_completion as COMPLETE,body_state as BODY
 results=[COMPLETE.recipient_result(row,t) for t in COMPLETE.actual_recipients(row)]
 if not _enemy(actor,row['actor']) or not BODY.in_range(e,actor,row['actor'],5):raise ValueError('Malediction requires an actual enemy within five metres')
 if not results or any(r is None or r['hit'] or r.get('cancelled') for r in results):raise ValueError('Malediction requires the actual attack to miss every target')
 if row['move'].get('class') not in ('물리','특수','변화'):raise ValueError('actual attack required')
 return receipt,row


def move_authority(e,actor,target,mid,source):
 frame=getattr(e,'_hex_maniac_move',None)
 if not frame or frame['actor'] is not actor or frame['move_id']!=mid or target not in frame['targets'] or source!=frame['source']:return False
 if source==MALEDICTION:
  _,row=malediction_trigger(e,actor,frame['event_id'])
  return target is row['actor'] or frame.get('diffuse') and target is frame['targets'][1]
 return False


def diffuse_spite_authority(e,actor,target):
 frame=getattr(e,'_hex_maniac_move',None)
 return bool(frame and frame['actor'] is actor and frame['move_id']==SPITE and frame.get('diffuse') and len(frame['targets'])==2 and target is frame['targets'][1])


def free_activation(e,actor,target,mid):
 frame=getattr(e,'_hex_maniac_move',None)
 return bool(frame and frame['actor'] is actor and frame['move_id']==mid and frame['targets'][0] is target
  and (move_authority(e,actor,target,mid,MALEDICTION) or mid==SPITE and frame['source']==SPITE))


def skip_additional_self_cost(e,actor,effect,ctx):
 frame=getattr(e,'_hex_maniac_move',None)
 if not (frame and frame['actor'] is actor and frame['move_id']==CURSE and frame['diffuse']
  and ctx.get('target') is frame['targets'][1] and effect.get('target')=='self'
  and effect.get('value')=='max_hp/3' and effect.get('unpreventable') is True):return False
 scope=__import__('move_activation').current_scope(e,actor,ctx['target'],CURSE)
 if scope is None or scope['index']!=2:raise ValueError('actual additional Curse target required')
 return True


def use(e,actor,target,move_id,*,diffuse_target=None,malediction_event=None,spite_event=None,boost=False,set_damage=False):
 import frequency as F,weapon_actions as WEAPON,class_move_grants as MOVES,body_state as BODY
 import move_activation as ACTIVATION,action_lifecycle as ACTION
 mid=e.r.move_id(move_id);__import__('world_entities').require_actors(e,actor,target,*(() if diffuse_target is None else (diffuse_target,)))
 if type(boost)is not bool:raise ValueError('explicit boolean Hex boost selection required')
 if mid not in studies_moves(actor):raise ValueError('actual Studies-granted Move required')
 if boost and mid!=HEX:raise ValueError('Hex boost belongs only to Hex')
 targets=[target] if diffuse_target is None else [target,diffuse_target]
 if len({id(t) for t in targets})!=len(targets):raise ValueError('Diffuse Pain requires one distinct additional target')
 if diffuse_target is not None:require(e,actor,DIFFUSE);_status_move(e,actor,mid)
 if malediction_event is not None:
  _,row=malediction_trigger(e,actor,malediction_event);_status_move(e,actor,mid)
  if target is not row['actor']:raise ValueError('Malediction targets its actual triggering enemy')
  if mid==SPITE:__import__('spite').trigger(e,actor,malediction_event)
 if mid==SPITE:
  if spite_event is None:raise ValueError('Spite requires its actual user hit event')
  _,row=__import__('spite').trigger(e,actor,spite_event)
  if target is not row['actor']:raise ValueError('Spite targets its actual attacking source')
 elif spite_event is not None:raise ValueError('Spite event belongs only to Spite')
 native=e.r.move(mid);native,_=MOVES.prepare_curse(e,actor,target,native,e.r.move_mech(mid)[0])
 reach=WEAPON.range_spec(e,native,actor).get('origin')
 for t in targets:
  if type(reach)is int and not BODY.in_range(e,actor,t,reach,move=native):raise ValueError('actual Move range applies to every Hex Maniac target')
  WEAPON.validate_target(e,actor,t,native)
 def apply(staged,a,*recipients):
  import turn as TURN
  if not F.move_allowed(staged,a,mid,outside_combat=not staged.encounter_active)[0]:raise ValueError('actual Move frequency exhausted')
  if diffuse_target is not None:_swift(staged,a,DIFFUSE,2)
  source=MALEDICTION if malediction_event is not None else SPITE if mid==SPITE else None
  key=MALEDICTION+':event:'+str(malediction_event)
  if malediction_event is not None:
   if a.counters.get(key):raise ValueError('Malediction event already consumed')
   if not F.activation_allowed(a,MALEDICTION,{'kind':'scene','uses':2},engine=staged):raise ValueError('Malediction Scene frequency exhausted')
  staged._hex_maniac_move={'actor':a,'move_id':mid,'targets':recipients,'source':source,'event_id':malediction_event,'diffuse':diffuse_target is not None,'boost':boost}
  if mid==SPITE:staged._spite_trigger=(a,spite_event)
  before=set(getattr(staged,'_move_completions',{}))
  try:
   total=0
   with ACTIVATION.open_scope(staged,a,mid,recipients,shared=False,primary=recipients[0],options={'set_damage':set_damage}) as (activation,accuracy):
    for index,t in enumerate(recipients):
     if index:
      with ACTION.move_grant(staged,a,t,mid,source='same_move_activation') as grant:total+=staged.use_move(a,t,mid,count_use=False,_activation=activation,_action_grant=grant,set_damage=set_damage)
     elif source:
      with ACTION.move_grant(staged,a,t,mid,source=source,kind='free') as grant:total+=staged.use_move(a,t,mid,free_action=True,_action_grant=grant,_activation=activation,set_damage=set_damage)
     else:total+=staged.use_move(a,t,mid,_activation=activation,set_damage=set_damage)
     if index==0 and not activation.get('started'):raise ValueError('actual Hex Maniac Move activation refused')
   rows=[r for key,r in staged._move_completions.items() if key not in before]
   if not rows or any(r['phase']!='complete' for r in rows):raise ValueError('actual whole Hex Maniac activation must complete')
   if malediction_event is not None:
    F.consume_activation(a,MALEDICTION,{'kind':'scene','uses':2},engine=staged);a.counters[key]=1
   return total
  finally:
   del staged._hex_maniac_move
   if mid==SPITE:del staged._spite_trigger
 return G.transition(e,actor,apply,participants=tuple(targets),include_rulings=True)


def choose_boost(e,actor,target,move):
 if move['id']!=HEX:return True
 frame=getattr(e,'_hex_maniac_move',None)
 if frame and frame['actor'] is actor and frame['move_id']==HEX:return frame['boost']
 answer=e.rulings.decide({'type':'hex_damage_boost','unit':HEX,'actor':actor.name,'target':target.name,'text':'Choose the once-per-Scene Hex damage increase, or decline.'})
 if answer not in (None,True,False):raise ValueError('Hex requires an explicit boolean damage boost choice')
 return answer is True


def begin_move(e,row):
 if row['move_id']!=HEX:return
 import frequency as F
 actor=row['actor'];st=F.state(actor)
 row['hex_frequency_before']={'count':actor.move_uses.get(HEX),'last':deepcopy(st['moves'].get(HEX))}


def record_boost(e,actor,target,move,plan,event_id):
 if move['id']!=HEX or not any(r.get('contract')=='scene_once_afflicted_target' for r in plan['applied']):return
 event=getattr(e,'_passive_events',{}).get(event_id)
 if event is None:return
 row=e._move_completions[event['completion_id']]
 row.setdefault('hex_boosted_recipients',[]).append(target.entity_id)


def grand(e,actor,target,event_id,recover_move):
 import move_completion as COMPLETE,frequency as F
 require(e,actor,GRAND);__import__('world_entities').require_actors(e,target)
 receipt,row=_event(e,event_id);COMPLETE.require_hit_return(e,event_id,target)
 if row['actor'] is not actor or row['move_id']!=HEX or not _enemy(actor,target):raise ValueError('Grand Hex requires this actual Hex hit against an enemy')
 mid=e.r.move_id(recover_move);_status_move(e,actor,mid)
 status=STATUS_MOVES.get(mid)
 if status is None or status not in target.conditions:raise ValueError('chosen Studies Move must inflict a currently held target status')
 if status=='사슬묶기' and not __import__('condition_instances').records(target,status):raise ValueError('actual Disabled Move instance required')
 key=GRAND+':'+target.entity_id;frequency={'kind':'scene','uses':1}
 if not F.activation_allowed(actor,key,frequency,engine=e):raise ValueError('Grand Hex target already used this Scene')
 if row.get('grand_hex_activated'):raise ValueError('Grand Hex hit event already consumed')
 state=actor.spec.get('frequency_state',{});kind=F.move_frequency(e,mid,actor)[0]
 if kind=='scene':
  if actor.move_uses.get(mid,0)<=0:raise ValueError('Grand Hex requires an actually expended Move use')
 elif kind=='every_other_turn':
  if mid not in state.get('moves',{}):raise ValueError('Grand Hex requires an actually expended EOT occurrence')
 else:raise ValueError('Grand Hex needs a recoverable Studies Move frequency')
 def apply(staged,a,t):
  _swift(staged,a,GRAND,1)
  kind=F.move_frequency(staged,mid,a)[0]
  if kind=='scene':F.restore_scene_use(staged,a,mid)
  elif kind=='every_other_turn':F.restore_eot(staged,a,mid)
  else:raise ValueError('Grand Hex needs a recoverable Studies Move frequency')
  actual=staged._move_completions[row['id']]
  boosted=t.entity_id in actual.get('hex_boosted_recipients',[])
  if boosted:
   before=actual['hex_frequency_before'];st=F.state(a)
   if before['count'] is None:a.move_uses.pop(HEX,None)
   else:a.move_uses[HEX]=before['count']
   a.spec['move_uses']=dict(a.move_uses)
   if before['last'] is None:st['moves'].pop(HEX,None)
   else:st['moves'][HEX]=deepcopy(before['last'])
  F.consume_activation(a,key,frequency,engine=staged)
  actual['grand_hex_activated']={'target_id':t.entity_id,'recovered_move':mid,'hex_frequency_refunded':boosted}
  return deepcopy(actual['grand_hex_activated'])
 return G.transition(e,actor,apply,participants=(target,),include_rulings=True)


def ability_registration(rules,name):
 for uid in (BODY,OMEN):
  unit=rules.selection.units[uid]
  if name in (uid,unit['title'],unit.get('eng')):
   if rules._selected_rule(uid)!=uid:raise ValueError('selected Hex Maniac Ability requires its own adapter')
   return {'name':unit['title'],'source_id':uid,'equivalent_source_ids':[uid]}
 return None


def activate_ability(e,actor,ability,target,*,event_id=None):
 import ability_transitions as ABILITY,frequency as F,turn as TURN,body_state as BODY_STATE
 reg=ability_registration(e.r,ability);source=reg['source_id']
 __import__('world_entities').require_actors(e,actor,target)
 if not ABILITY.active(actor,source):raise ValueError('actual active acquired Ability required')
 if source==BODY:
  receipt,row=_event(e,event_id);__import__('move_completion').require_hit_return(e,event_id,actor)
  if target is not row['actor'] or row['move'].get('class') not in ('물리','특수'):raise ValueError('Cursed Body requires the actual damaging Move hit and attacker')
  mid=row['move_id']
 else:
  if event_id is not None:raise ValueError('Omen has no hit trigger')
  if not BODY_STATE.in_range(e,actor,target,5):raise ValueError('Omen requires an actual target within five metres')
 def apply(staged,a,t):
  if not F.activation_allowed(a,source,{'kind':'scene','uses':1},engine=staged):raise ValueError('Ability Scene frequency exhausted')
  if source==BODY:__import__('action_lifecycle').triggered_free_action(staged,a,source)
  elif not TURN.spend(staged,a,'swift',source):raise ValueError('Ability action unavailable')
  if source==BODY:staged.apply_status(t,'사슬묶기',source=source,parameters={'move_id':mid},applied_by=a)
  else:__import__('combat_timing').install(staged,t,{'source':source,'attacker':a,'accuracy_modifier':-2,'encounter_end':True})
  F.consume_activation(a,source,{'kind':'scene','uses':1},engine=staged)
  return {'source':source,'target_id':t.entity_id,**({'move_id':mid,'event_id':event_id} if source==BODY else {'accuracy_modifier':-2})}
 return G.transition(e,actor,apply,participants=(target,),include_rulings=True)
