"""Bide: an authenticated after-hit Reaction and its next-turn loss release."""
from copy import deepcopy
import common_checks as C
import attack_damage_history as HISTORY
SOURCE='move/참기'
KEY='bide_pending'


def pending(actor):return actor.spec.get(KEY)


def clear(engine,actor):
 row=actor.spec.pop(KEY,None)
 if row and row.get('permission'):
  import state_grants as G
  G.revoke(actor,row['permission'],engine=engine)


def resolving(engine,actor,source):
 return source==SOURCE and getattr(engine,'_bide_release_actor',None) is actor


def authorized(engine,actor,target,source):
 return resolving(engine,actor,source) and pending(actor) is not None and engine._active_turn_actor is actor


def project(engine,actor,move,mechanics):
 if move['id']!=SOURCE:return move,mechanics
 from source_context import verified_source
 verified_source(engine.r,{'file':'input/db/moves.csv','sha256':'ab83f872e5eca67a41db7d126b842f0165437e0fa70bb77ddad832a0b7396c93'},label='Bide')
 if getattr(engine,'_bide_declaring_actor',None) is actor:return dict(move,_retrospective_hp_loss=0),{'effects_exec':[],'never_miss':True}
 row=pending(actor)
 if not resolving(engine,actor,SOURCE) or row is None:raise ValueError('Bide requires its actual completed damaging hit Reaction')
 amount=sum(HISTORY.amount(r) for r in HISTORY.records(actor) if r['sequence']>row['damage_sequence'] and r.get('application_kind','damage')=='damage')
 return dict(move,_retrospective_hp_loss=amount),{'never_miss':True,'effects_exec':[{'type':'hp_loss','value':amount,'target':'target'}]}


def reaction(engine,actor,event_id,*,trainer=None,ranked=None,payment='current',effect=None,flourish=False):
 import initiative_interrupts as I,world_entities as W,state_grants as G,move_completion as COMPLETE
 import style_expert as STYLE,action_points as AP
 W.require_actors(engine,actor)
 trigger=I._trigger(engine,{'kind':'move','event_id':event_id});event=engine._passive_events[event_id]
 returned=COMPLETE.require_returned_event(engine,event_id)
 row=engine._move_completions[event['completion_id']]
 hit=COMPLETE.recipient_result(row,actor)
 if row['move']['class'] not in ('물리','특수') or not hit or not hit['hit'] or hit.get('cancelled') or actor.fainted:
  raise ValueError('Bide requires the actual surviving recipient of a damaging Move Hit')
 if pending(actor):raise ValueError('Bide already awaiting its next actual turn')
 if payment not in ('current','next'):raise ValueError('explicit existing reaction current/next payment required')
 if (effect or flourish) and trainer is None:raise ValueError('actual Style Trainer required')
 if ranked is not None:
  if trainer is None or ranked!=STYLE.RANKED['강인함']:raise ValueError('actual Tough Tumble source required')
  STYLE.require(engine,trainer,actor,ranked,'강인함')
  if __import__('acquired_features').feature_rank(trainer,ranked)<2:raise ValueError('Bide needs actual Tough Tumble Rank2')
  if STYLE.CF.poffin_dice(engine,trainer,actor,'강인함',STYLE.CF.style_expert(engine,trainer))<3:raise ValueError('three Poffin dice required')
 elif SOURCE not in actor.moves:raise ValueError('actual learned Bide or acquired ranked permission required')
 participants=() if trainer is None else (trainer,)
 def apply(e,p,*owners):
  a=owners[0] if owners else None
  permission=None
  style=STYLE.special_scope(e,a,p,SOURCE,effect=effect,flourish=flourish) if effect or flourish else None
  if ranked:
   if AP.available(a)<1:raise ValueError('Tough Tumble requires 1 AP')
   AP.spend(a,1);permission='bide-permission:'+p.entity_id+':'+event_id
   G.grant_moves(p,[SOURCE],permission,'feature',owner_id=a.entity_id,lifetime='scene',rule_id=ranked,mode='permission')
  request={'id':'bide:'+p.entity_id+':'+event_id,'actor_id':p.entity_id,'source':SOURCE,'priority':0,
   'mode':'reaction','payment':payment,'budget':{'standard':1},'clock':'none'}
  result=I.queue(e,[request],trigger={'kind':'move','event_id':event_id})
  window=result['window_id'];I.begin(e,window,request['id'])
  before=p.move_uses.get(SOURCE,0);e._bide_declaring_actor=p
  try:e.use_move_on(p,e._move_completions[e._passive_events[event_id]['completion_id']]['actor'],SOURCE,e.everyone)
  finally:del e._bide_declaring_actor
  if p.move_uses.get(SOURCE,0)!=before+1:raise ValueError('Bide Reaction native activation refused')
  p.spec[KEY]={'source':SOURCE,'event_id':event_id,'damage_sequence':len(HISTORY.records(p)),
   'turn':p.custom_conditions.get('combat_turn_serial',0),'epoch':e._party_encounter_epoch,'permission':permission,'style':style}
  I.finish(e)
  return deepcopy(p.spec[KEY])
 return G.transition(engine,actor,apply,participants=participants,include_rulings=True)


def release(engine,actor,target):
 import state_grants as G,world_entities as W
 W.require_actors(engine,actor,target)
 row=pending(actor)
 if row is None or row['epoch']!=engine._party_encounter_epoch or engine._active_turn_actor is not actor or actor.custom_conditions.get('combat_turn_serial',0)!=row['turn']+1:
  raise ValueError('Bide releases only during its next available actual owner turn')
 def apply(e,p,t):
  e._bide_release_actor=p
  style=p.spec[KEY].get('style')
  if style:e._style_move_scope=style
  before=set(getattr(e,'_move_completions',{}))
  try:
   result=e.use_move_on(p,t,SOURCE,e.everyone)
   if not any(key not in before and row['actor'] is p and row['move_id']==SOURCE and row['phase']=='complete' for key,row in e._move_completions.items()):
    raise ValueError('Bide release requires actual completed native activation')
  finally:
   del e._bide_release_actor
   if style:del e._style_move_scope
  old=p.spec.pop(KEY)
  if old['permission']:G.revoke(p,old['permission'],engine=e)
  return result
 return G.transition(engine,actor,apply,participants=(target,),include_rulings=True)
