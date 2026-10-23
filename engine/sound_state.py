"""Voluntary silence is shared state, not a numeric Stealth bonus."""
from copy import deepcopy
import state_grants as G
import skill_modifiers as S
KEY='sound_preference'
EVENT='last_sound_event'
DEFINITIONS={'dead_silent':('capability/숨죽이기',('숨죽이기','Dead Silent')),
             'stealth':('capability/은밀',('은밀','Stealth'))}
ACTIVITIES=('movement','ranged_attack','melee_attack','other')


def sources(actor):
 names={S.key(x) for x in G.effective_capabilities(actor)};result={}
 for name,(source,aliases) in DEFINITIONS.items():
  if names.intersection(S.key(x) for x in aliases):
   if actor.r._selected_rule(source)!=source:raise ValueError('selected silence capability needs its own policy')
   result[name]=source
 return result


def validate(actor):
 row=actor.spec.get(KEY)
 if row is not None:
  if not isinstance(row,dict) or set(row)!={'quiet','reason'} or type(row['quiet']) is not bool or not isinstance(row['reason'],str) or not row['reason'].strip():raise ValueError('explicit voluntary sound preference required')
 event=actor.spec.get(EVENT)
 if event is not None:
  if not isinstance(event,dict) or set(event)!={'actor_id','activity','move_id','suppressed','source'} or event['actor_id']!=actor.entity_id or event['activity'] not in ACTIVITIES or type(event['suppressed']) is not bool:raise ValueError('valid native sound observation required')
  if event['source'] not in (None,*(x[0] for x in DEFINITIONS.values())):raise ValueError('sound source mismatch')
  if event['suppressed']!=(event['source'] is not None):raise ValueError('sound suppression needs its actual source')
  if event['activity']=='movement' and event['move_id'] is not None:raise ValueError('movement observation cannot invent a Move')
  if event['activity']!='movement' and (not isinstance(event['move_id'],str) or not event['move_id']):raise ValueError('actual Move identity required')
 return row


def projection(actor):
 row=validate(actor);owned=sources(actor);quiet=bool(row and row['quiet'])
 all_sound=owned.get('dead_silent') if quiet else None
 movement=all_sound or (owned.get('stealth') if quiet else None)
 return {'entity_id':actor.entity_id,'quiet_requested':quiet,
         'all_sounds':all_sound,'breathing':all_sound,'heartbeat':all_sound,
         'movement':movement,'ranged_attack':all_sound,'sources':owned,
         'last_event':deepcopy(actor.spec.get(EVENT))}


def choose(engine,actor,enabled,*,reason):
 import world_entities as W
 if W.actor_index(engine).get(actor.entity_id) is not actor:raise ValueError('registered actor required')
 if type(enabled) is not bool or not isinstance(reason,str) or not reason.strip():raise ValueError('explicit quiet choice and reason required')
 if enabled and not sources(actor):raise ValueError('actual silence capability required')
 validate(actor)
 before=deepcopy(actor.spec.get(KEY));actor.spec[KEY]={'quiet':enabled,'reason':reason}
 engine.gm._rec('voluntary silence',before,actor.spec[KEY],reason,actor)
 return projection(actor)


def observe(engine,actor,activity,move_id=None):
 if activity not in ACTIVITIES:raise ValueError('known native sound activity required')
 if KEY not in actor.spec:return
 view=projection(actor)
 source=view['movement'] if activity=='movement' else view['ranged_attack'] if activity=='ranged_attack' else view['all_sounds']
 actor.spec[EVENT]={'actor_id':actor.entity_id,'activity':activity,'move_id':move_id,'suppressed':source is not None,'source':source}


def prepare_move(engine,actor,move):
 if KEY not in actor.spec:return None
 projection(actor)
 import weapon_actions as W
 rng=W.range_spec(engine,move,actor);origin=rng.get('origin')
 activity='melee_attack' if origin=='melee' else 'ranged_attack' if type(origin) is int and origin>0 else 'other'
 return activity
