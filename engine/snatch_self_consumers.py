"""Exact native Self consumers that reuse the authenticated Snatch route."""
from contextlib import contextmanager

MINIMIZE='move/작아지기'
ROOST='move/날개쉬기'
ROOST_TYPE={'type':'type_change','lose_type':'비행','target':'self',
            'if':'user is 비행','until':"start of user's next turn"}
PROFILES={
 MINIMIZE:[
  {'type':'evasion_mod','value':4,'target':'self','until':'encounter_end'},
  {'type':'size_change','to':'Small','target':'self','until':'encounter_end'},
  {'type':'grant_capability','capability':'수축성'}],
 ROOST:[{'type':'heal','fraction_of_max':[1,2],'target':'self'},ROOST_TYPE],
}


def semantic(effect):
 return {key:value for key,value in effect.items() if not key.startswith('_')}


def preflight(e,args):
 source=args['move']['id']
 if source=='move/웅크리기':
  import defense_curl as CURL
  if [semantic(x) for x in args['mm'].get('effects_exec',[])]!=[CURL.definition(e.r)['raw']]:
   raise ValueError('Snatch Defense Curl requires its exact selected native declaration')
  if any(key in args['mm'] for key in ('drain','zone','set_up_move')):
   raise ValueError('Snatch Defense Curl contains an unsupported native consumer')
  CURL.selected(e.r,args['attacker'].spec.get(CURL.CHOICE))
  return True
 if source not in PROFILES:return False
 if e.r._selected_rule(source)!=source:
  raise ValueError('Snatch Self consumer requires its reviewed selected source')
 if [semantic(x) for x in args['mm'].get('effects_exec',[])]!=PROFILES[source]:
  raise ValueError('Snatch Self consumer requires its exact native effect declarations')
 if any(key in args['mm'] for key in ('drain','zone','set_up_move')):
  raise ValueError('Snatch Self source contains an unsupported native consumer')
 # Minimize's grant is learned ownership metadata, consumed by
 # move_capabilities. Its native no-op never transfers learning to the thief.
 return True


@contextmanager
def completion_scope(e,row,target,effects):
 import combat_move_reactions as R,move_completion as MC,move_defense_reactions as D
 if row['move_id']!=ROOST or not effects:
  yield target
  return
 route=R.snatch_route(e,row['actor'],target,row['move_id'],row['id'])
 if route is None:
  yield target
  return
 _,state,recipient=route
 if [semantic(effect) for effect in effects]!=[ROOST_TYPE]:
  raise ValueError('Snatch Roost requires its exact native post-resolution declaration')
 if (not MC.authorized(e,{'move_completion':row['id'],'attacker':row['actor']})
     or state['phase']!='complete'):
  raise ValueError('Snatch Roost needs its actual completed recipient boundary')
 # Reuse the existing execution scope solely around the native post dispatcher.
 # A context flag or a completed receipt alone cannot open this scope.
 with D._recipient_scope(e,(state['event_id'],row['actor'].entity_id,recipient.entity_id)):
  yield recipient


def condition_user(e,ctx,source,effect):
 actor=ctx['attacker']
 if source!=ROOST or semantic(effect)!=ROOST_TYPE:return actor
 recipient=__import__('combat_move_reactions').snatch_recipient(
  e,actor,ctx['target'],source,ctx)
 return actor if recipient is None else recipient


def lifetime_user(e,actor,target,source,effect):
 if source!=ROOST or semantic(effect)!=ROOST_TYPE:return actor
 recipient=__import__('combat_move_reactions').snatch_recipient(e,actor,target,source)
 return actor if recipient is None else recipient


def lifetime_recipients(e,receipt,record):
 """Validate durable provenance without authorizing a fresh effect dispatch."""
 import effect_contracts as C,combat_move_reactions as R
 effect=e._effect_dispatch_receipts[receipt]
 ordinary=C.recipients(effect['actor'],effect['target'],effect['effect'])
 if effect['source_id']!=ROOST or semantic(effect['effect'])!=ROOST_TYPE:
  return ordinary
 matches=[]
 for row in getattr(e,'_move_completions',{}).values():
  owned=set(row['effects'])|{key for result in row.get('received',{}).values() for key in result['effects']}
  if receipt not in owned:continue
  route=R.snatch_route(e,effect['actor'],effect['target'],effect['source_id'],row['id'])
  if route is not None:matches.append(route)
 if not matches:return ordinary
 if len(matches)!=1:raise ValueError('Snatch lifetime has ambiguous native completion ownership')
 row,state,recipient=matches[0]
 if (effect['target'] is not recipient or record.get('turn_owner') is not recipient
     or state['phase']!='complete'):
  raise ValueError('Snatch lifetime recipient or turn owner differs from its native receipt')
 return (recipient,)

