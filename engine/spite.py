"""Spite uses the actual completed hit's Move identity, never last_move."""
import common_checks as C
SOURCE='move/원한'


def trigger(engine,actor,event_id):
 import move_completion as COMPLETE
 import initiative_interrupts as I
 I._trigger(engine,{'kind':'move','event_id':event_id})
 event=engine._passive_events.get(event_id)
 if not event or event['phase']!='producer_return_boundary' or event['round']!=engine.round_no or event['status'] not in ('applied','inapplicable'):
  raise ValueError('Spite requires its actual completed native hit event')
 COMPLETE.require_returned_event(engine,event_id)
 row=engine._move_completions[event['completion_id']];hit=COMPLETE.recipient_result(row,actor)
 if not hit or not hit['hit'] or hit.get('cancelled') or actor.fainted or actor.dead:raise ValueError('actual surviving Spite hit recipient required')
 return event,row


def project(engine,actor,target,move,mechanics):
 if move['id']!=SOURCE:return move,mechanics
 frame=getattr(engine,'_spite_trigger',None)
 if frame is None or frame[0] is not actor:raise ValueError('Spite requires its actual authenticated hit trigger')
 _,row=trigger(engine,actor,frame[1])
 if target is not row['actor']:raise ValueError('Spite targets the attacker of its actual triggering Move')
 return move,{'effects_exec':[{'type':'apply_status','status':'사슬묶기','target':'target','parameters':{'move_id':row['move_id']}}]}


def use(engine,trainer,pokemon,event_id,*,policy=None,effect=None,flourish=False):
 import style_expert as STYLE,state_grants as G,action_points as AP,action_lifecycle as ACTION
 import world_entities as W
 W.require_actors(engine,trainer,pokemon)
 STYLE.require(engine,trainer,pokemon,STYLE.RANKED['강인함'],'강인함')
 if STYLE.CF.poffin_dice(engine,trainer,pokemon,'강인함',STYLE.CF.style_expert(engine,trainer))<3:raise ValueError('three Poffin dice required')
 event,row=trigger(engine,pokemon,event_id)
 if policy is None:return C.PendingDecision('Tough Tumble Standard vs Spite Free/no Command requires an explicit source precedence ruling',basis={'class':'PTU117','move':'PTU379','choices':['standard_override','printed_free']})
 if policy not in ('standard_override','printed_free'):raise ValueError('explicit Spite action precedence policy required')
 if policy=='standard_override' and engine._active_turn_actor is not pokemon:raise ValueError('Standard override needs an actual current owner turn or separately authorized Standard reaction')
 def apply(e,a,p):
  actual=trigger(e,p,event_id)[1];target=actual['actor']
  if AP.available(a)<1:raise ValueError('Tough Tumble costs 1 AP')
  AP.spend(a,1);sid='spite-permission:'+p.entity_id+':'+event_id
  G.grant_moves(p,[SOURCE],sid,'feature',owner_id=a.entity_id,lifetime='scene',rule_id=STYLE.RANKED['강인함'],mode='permission')
  style=STYLE.special_scope(e,a,p,SOURCE,effect=effect,flourish=flourish) if effect or flourish else None
  if style:e._style_move_scope=style
  e._spite_trigger=(p,event_id)
  before=p.move_uses.get(SOURCE,0)
  try:
   if policy=='printed_free':
    with ACTION.move_grant(e,p,target,SOURCE,kind='free',source=SOURCE) as grant:
     result=e.use_move(p,target,SOURCE,free_action=True,_action_grant=grant)
   else:result=e.use_move(p,target,SOURCE)
   if p.move_uses.get(SOURCE,0)!=before+1:raise ValueError('native Spite activation refused')
   return result
  finally:
   if style:del e._style_move_scope
   del e._spite_trigger;G.revoke(p,sid,engine=e)
 return G.transition(engine,trainer,apply,participants=(pokemon,),include_rulings=True)
