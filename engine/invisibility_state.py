"""Source-owned voluntary invisibility on the existing world clock.

The source's approximately four minutes is represented as 240 known seconds.
Unknown partial rounds remain bounded uncertainty, never zero elapsed time.
"""
from copy import deepcopy
import state_grants as G
import skill_modifiers as S
import elapsed_time as TIME
KEY='invisibility_state'
SOURCE='capability/투명'
DURATION=240
RECOVERY=120


def validate(actor):
 row=actor.spec.get(KEY)
 if row is None:return None
 fields={'source','clock_anchor','unknown_index','elapsed_base','ended_elapsed','reason'}
 if not isinstance(row,dict) or set(row) not in (fields,fields|{'duration_seconds'}) or row['source']!=SOURCE:raise ValueError('valid invisibility source state required')
 for name in ('clock_anchor','unknown_index','elapsed_base'):
  if type(row[name]) is not int or row[name]<0:raise ValueError('nonnegative invisibility clock required')
 duration=row.get('duration_seconds',DURATION)
 if type(duration)is not int or duration not in (240,480):raise ValueError('reviewed invisibility duration required')
 if duration==480:
  import invisibility_edge as EDGE
  if not EDGE.records(actor):raise ValueError('extended invisibility history needs an investment receipt')
 end=row['ended_elapsed']
 if end is not None and (type(end) is not int or not 0<=end<duration or end>row['elapsed_base']):raise ValueError('valid manual invisibility end required')
 if not isinstance(row['reason'],str) or not row['reason'].strip():raise ValueError('invisibility reason required')
 if actor.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected invisibility variant needs its own policy')
 return row


def elapsed_bounds(engine,actor):
 row=validate(actor)
 if row is None:return None
 return TIME.bounds(engine,row['clock_anchor'],row['unknown_index'],row['elapsed_base'],label='invisibility clock')


def projection(engine,actor):
 bounds=elapsed_bounds(engine,actor)
 if bounds is None:return {'phase':'ready','active':False,'elapsed_bounds':None,'ready_after_elapsed':None,'source':None}
 row=actor.spec[KEY];low,high=bounds;end=row['ended_elapsed']
 boundary=row.get('duration_seconds',DURATION) if end is None else end
 ready=boundary*2+RECOVERY
 def phase(t):return 'active' if end is None and t<boundary else 'cooldown' if t<ready else 'ready'
 phases={phase(low),phase(high)};current=phases.pop() if len(phases)==1 else 'uncertain'
 active=False if end is not None or low>=boundary else True if high<boundary else None
 return {'phase':current,'active':active,
         'elapsed_bounds':[low,high],'ready_after_elapsed':ready,'source':SOURCE}


def registered(engine,actor,reason):
 import world_entities as W
 if W.actor_index(engine).get(actor.entity_id)is not actor:raise ValueError('actual registered actor required')
 if not isinstance(reason,str) or not reason.strip():raise ValueError('explicit invisibility reason required')


def change(engine,actor,enabled,*,reason):
 registered(engine,actor,reason)
 if type(enabled)is not bool:raise ValueError('explicit invisibility choice required')
 def apply(e,c):
  import turn as TURN
  view=projection(e,c);old=deepcopy(c.spec.get(KEY))
  if enabled:
   if view['phase']!='ready':raise ValueError('invisibility is active, cooling down or has unresolved time')
   if not {S.key('투명'),S.key('Invisibility')}.intersection(S.key(x) for x in G.effective_capabilities(c,only=('투명','Invisibility'))):raise ValueError('actual Invisibility capability required')
   if c.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected invisibility variant needs its own policy')
   if not TURN.spend(e,c,'shift','invisibility activation'):raise ValueError('invisibility Shift unavailable')
   import invisibility_edge as EDGE
   duration=EDGE.duration(c)
   c.spec[KEY]={'duration_seconds':duration,'source':SOURCE,'clock_anchor':e.elapsed_seconds,'unknown_index':len(e.unresolved_time_intervals),'elapsed_base':0,'ended_elapsed':None,'reason':reason}
  else:
   if view['phase']!='active':raise ValueError('active invisibility required')
   low,high=view['elapsed_bounds']
   if low!=high:raise ValueError('observe actual invisibility elapsed time before manual end')
   if not TURN.spend(e,c,'free','invisibility end'):raise ValueError('invisibility Free action unavailable')
   c.spec[KEY].update(clock_anchor=e.elapsed_seconds,unknown_index=len(e.unresolved_time_intervals),elapsed_base=low,ended_elapsed=low,reason=reason)
  e.gm._rec('invisibility',old,deepcopy(c.spec[KEY]),reason,c)
  return projection(e,c)
 return G.transition(engine,actor,apply)


def observe_elapsed(engine,actor,seconds,*,reason):
 registered(engine,actor,reason)
 bounds=elapsed_bounds(engine,actor)
 if bounds is None or type(seconds)is not int or not bounds[0]<=seconds<=bounds[1]:raise ValueError('observed invisibility time must fit known elapsed bounds')
 old=deepcopy(actor.spec[KEY])
 actor.spec[KEY].update(clock_anchor=engine.elapsed_seconds,unknown_index=len(engine.unresolved_time_intervals),elapsed_base=seconds,reason=reason)
 engine.gm._rec('invisibility elapsed observation',old,deepcopy(actor.spec[KEY]),reason,actor)
 return projection(engine,actor)


def require_move(engine,actor):
 active=projection(engine,actor)['active']
 if active is not False:raise ValueError('invisibility prevents Moves or needs elapsed-time resolution')


def preflight_forced_end(engine,actor):
 """A real capability loss ends the existing activation at its actual time."""
 view=projection(engine,actor)
 if view['active']is False:return False
 low,high=view['elapsed_bounds']
 if low!=high:raise ValueError('observe actual invisibility elapsed time before forced capability loss')
 return True


def force_end(engine,actor,*,reason):
 """No voluntary action cost; retain the native activation and cooldown."""
 registered(engine,actor,reason)
 if not preflight_forced_end(engine,actor):return False
 old=deepcopy(actor.spec[KEY]);elapsed=elapsed_bounds(engine,actor)[0]
 actor.spec[KEY].update(clock_anchor=engine.elapsed_seconds,unknown_index=len(engine.unresolved_time_intervals),
     elapsed_base=elapsed,ended_elapsed=elapsed,reason=reason)
 engine.gm._rec('invisibility capability lost',old,deepcopy(actor.spec[KEY]),reason,actor)
 return True


def accuracy_penalty(engine,actor):
 active=projection(engine,actor)['active']
 if active is None:raise ValueError('invisibility accuracy needs elapsed-time resolution')
 import body_modes as BODY_MODES
 return 4 if active or BODY_MODES.flat(actor) else 0

