"""Ephemeral producer authority for one native move's target/accuracy group.

Shared dictionaries are data, never authority. Only the live use_move_on scope
can bind the actor, selected move, ordered targets and cost/frequency boundary.
"""
from contextlib import contextmanager
from copy import deepcopy
import root_resolution as R

def _profile(e):
 return R.fingerprint({'profile':e.r.ruleset.profile,'choices':e.r.ruleset.variant_choices,'versions':e.r.ruleset.unit_versions})

def _lifetime(e):
 return (getattr(e,'_root_common_epoch',0),e.encounter_active,e.round_no,
         getattr(e,'_active_turn_actor',None),getattr(e,'session_epoch',0),len(getattr(e,'_turn_closures',())))


def _transition_lifetime(e):
 """Comparable boundary across an atomic staged graph."""
 root,active,round_no,turn_actor,session,closures=_lifetime(e)
 return (root,active,round_no,getattr(turn_actor,'entity_id',None),session,closures)

@contextmanager
def open_scope(e,actor,move_id,targets,*,shared,primary=None,options=None,_prepaid=None):
 targets=tuple(targets)
 if not targets or len({id(t) for t in targets})!=len(targets):raise ValueError('distinct actual move targets required')
 activation={};accuracy={'targets':targets} if shared else None
 scope={'actor':actor,'move_id':move_id,'targets':targets,'primary':primary,
        'activation':activation,'accuracy':accuracy,'index':0,
        'profile':_profile(e),'lifetime':_lifetime(e),'options':dict(options or {}),'total':0}
 import type_ace as TA
 declaration=TA.scope(e,actor,{'id':move_id})
 if declaration is not None:scope['type_ace']=declaration
 import martial_artist as MARTIAL
 if MARTIAL.move_authority(e,actor,targets[0],move_id,MARTIAL.ACHIEVEMENT):scope['martial_artist']={'source':MARTIAL.ACHIEVEMENT,'extra_move':True}
 import style_expert as STYLE
 declaration=STYLE.scope(e,actor,{'id':move_id})
 if declaration is not None:
  scope['style_expert']=dict(declaration,target_ids=[target.entity_id for target in targets])
 import stat_ace as STAT
 converted=STAT.scope(e,actor,{'id':move_id})
 if converted is not None and _prepaid is None:
  scope['stat_maneuver']=dict(converted)
 if _prepaid is not None:
  import pass_moves as PASS
  PASS.activation_authority(e,actor,move_id,targets,_prepaid)
  scope['prepaid_pass']=_prepaid
  activation['started']=True
 import conditional_damage_base as CONDITIONAL_DB,bide as BIDE
 if CONDITIONAL_DB.round_end_authorized(actor,primary,move_id) or BIDE.authorized(e,actor,primary,move_id):
  scope['paid_resolution']=True
 if not hasattr(e,'_move_activation_scopes'):e._move_activation_scopes=[]
 e._move_activation_scopes.append(scope)
 try:
  yield activation,accuracy
 except BaseException as error:
  import move_completion as COMPLETE
  if not suspend(e,scope,error):COMPLETE.seal(e,scope,interrupted=True)
  raise
 else:
  import move_completion as COMPLETE
  if not scope.get('chain',{}).get('awaiting_choice'):
   COMPLETE.seal(e,scope,interrupted=bool(scope.get('interrupted')))
 finally:
  e._move_activation_scopes[:]=[s for s in e._move_activation_scopes if s is not scope]
  if not e._move_activation_scopes:del e._move_activation_scopes


def note_result(e,activation,dealt):
 matches=[s for s in getattr(e,'_move_activation_scopes',()) if s['activation'] is activation]
 if len(matches)!=1:raise ValueError('result needs its live native activation')
 scope=matches[0];scope['total']+=dealt
 scope['interrupted']=bool(scope['actor'].fainted or scope['actor'].dead)
 return scope['interrupted']


def _continuation_facts(scope,event_id):
 import move_defense_reactions as DEFENSE
 return DEFENSE._move_facts(dict(scope,event_id=event_id))


def suspend(e,scope,error):
 import passive_events as PASSIVE
 if type(error) is not PASSIVE.PassiveEventPending or e._passive_pending!=error.event_id:return False
 event=e._passive_events.get(error.event_id)
 if event is None:return False
 while event.get('defense_parent'):event=e._passive_events[event['defense_parent']]
 if event.get('completion_id')!=scope.get('completion_id'):
  event=__import__('conquerors_march').counter_parent(e,event,scope['completion_id'])
  if event is None:return False
 elif not event.get('continuation'):return False
 row=e._move_completions[scope['completion_id']]
 import world_entities as WORLD
 memo={id(actor):actor for actor in WORLD.actor_index(e).values()}
 if 'prepaid_pass' in scope:
  import pass_moves as PASS
  PASS.suspend(e,scope)
 snapshot=deepcopy(scope,memo)
 if 'prepaid_pass' in snapshot:
  getattr(e,PASS.KEY)[snapshot['prepaid_pass']['event_id']]=snapshot['prepaid_pass']['receipt']
 # Geometry is bound before the ally is pushed, not recalculated from it later.
 if snapshot['accuracy'] is not None and snapshot['options'].get('aim') is None:
  import weapon_actions as WEAPON
  move=event['continuation']['args']['move'] if event.get('continuation') else __import__('move_completion').event_move(e,event)
  shape=WEAPON.range_spec(e,move,scope['actor']).get('shape')
  snapshot['options']['aim']=scope['actor'].pos if shape=='burst' else scope['primary'].pos
 row['activation_continuation']={'scope':snapshot,'event_id':event['id'],
   'fingerprint':R.fingerprint(_continuation_facts(snapshot,event['id']))}
 return True


def resume_after_event(e,event,result):
 row=getattr(e,'_move_completions',{}).get(event.get('completion_id'))
 saved=None if row is None else row.get('activation_continuation')
 if saved is None or saved.get('choice') or saved['event_id']!=event['id'] or event['phase']!='producer_return_boundary':return result
 if getattr(e,'_resuming_move_activation',False):return result
 # A listener status is not the completed recipient's damage result. Check
 # the native target receipt before consuming the saved continuation.
 returned=row['results'].get(event['target'].entity_id)
 if (returned is None or type(result) is not int or result<0 or
     returned['dealt']!=result):
  raise ValueError('native target return required before activation resume')
 scope=saved['scope']
 if saved['fingerprint']!=R.fingerprint(_continuation_facts(scope,event['id'])):
  raise ValueError('native target group changed during wait')
 if scope['lifetime'][1:]!=_lifetime(e)[1:] or scope['profile']!=_profile(e):
  raise ValueError('native target group boundary changed')
 # The world codec intentionally revokes ephemeral producer epochs. Only this
 # authenticated saved continuation may issue a new live scope after restore.
 scope['lifetime']=_lifetime(e)
 row.pop('activation_continuation')
 scope['total']+=result
 previous=getattr(e,'_move_activation_scopes',None)
 e._move_activation_scopes=[scope];e._resuming_move_activation=True
 import move_completion as COMPLETE,action_lifecycle as ACTION
 try:
  if 'chain' in scope:
   import dynamic_chain_moves as CHAIN
   return CHAIN.advance(e,scope)
  if 'prepaid_pass' in scope:
   import pass_moves as PASS
   return PASS.resume(e,scope,event,result)
  while scope['index']<len(scope['targets']):
   if scope['actor'].fainted or scope['actor'].dead:
    COMPLETE.seal(e,scope,interrupted=True)
    return scope['total']
   target=scope['targets'][scope['index']]
   with ACTION.move_grant(e,scope['actor'],target,scope['move_id'],source='same_move_activation') as grant:
    dealt=e.use_move(scope['actor'],target,scope['move_id'],count_use=False,
     _activation=scope['activation'],_shared_accuracy=scope['accuracy'],_action_grant=grant,**scope['options'])
   scope['total']+=dealt
  COMPLETE.seal(e,scope,interrupted=bool(scope['actor'].fainted or scope['actor'].dead))
  return scope['total']
 except BaseException as error:
  if not suspend(e,scope,error):COMPLETE.seal(e,scope,interrupted=True)
  raise
 finally:
  del e._resuming_move_activation
  if previous is None:del e._move_activation_scopes
  else:e._move_activation_scopes=previous


def validate_continuations(e,index):
 for key,row in getattr(e,'_move_completions',{}).items():
  saved=row.get('activation_continuation')
  if saved is None:continue
  if saved.get('choice'):
   import dynamic_chain_moves as CHAIN
   CHAIN.validate_choice(e,row,saved,index)
   continue
  scope=saved['scope'];event=e._passive_events.get(saved['event_id'])
  if (event is None or event.get('completion_id')!=key or scope['completion_id']!=key or
      scope['actor'] is not row['actor'] or list(scope['targets'])!=row['targets'] or
      not 0<scope['index']<=len(scope['targets']) or (scope['targets'][scope['index']-1] is not event['target'] and
       not __import__('conquerors_march').pair_wait_index(e,row,event,scope)) or
      saved['fingerprint']!=R.fingerprint(_continuation_facts(scope,event['id']))):
   raise ValueError('native suspended target group lacks its actual producer: '+str({
    'completion':key,'scope_completion':scope.get('completion_id'),
    'event_completion':None if event is None else event.get('completion_id'),
    'index':scope['index'],'targets':[a.entity_id for a in scope['targets']],
    'declared':[a.entity_id for a in row['targets']],
    'event_target':None if event is None else event['target'].entity_id,
    'actor_matches':scope['actor'] is row['actor'],
    'fingerprint_matches':event is not None and saved['fingerprint']==R.fingerprint(_continuation_facts(scope,event['id']))}))
  if any(index.get(actor.entity_id) is not actor for actor in scope['targets']):
   raise ValueError('native target group lost an actual target')
  converted=scope.get('stat_maneuver')
  if converted is not None:
   if (converted.get('pokemon') is not scope['actor'] or converted.get('move_id')!=scope['move_id']
       or index.get(converted['trainer'].entity_id) is not converted['trainer']
       or converted['proof'] not in converted['trainer'].spec.get('stat_maneuver_uses',())):
    raise ValueError('native suspended Stat Maneuver lost its paid producer')
 return True

def verify(e,actor,target,move_id,activation,accuracy,*,count_use,free_action):
 import native_area_hit_effects as AREA_HIT
 AREA_HIT.require_activation(e,actor,target,move_id,activation,accuracy)
 import equipment_variant_contracts as EQUIPMENT_VARIANTS
 EQUIPMENT_VARIANTS.preflight_move(e,actor,move_id,count_use=count_use)
 if activation is None and accuracy is None:return
 matches=[s for s in getattr(e,'_move_activation_scopes',()) if s['activation'] is activation and s['accuracy'] is accuracy]
 if len(matches)!=1:raise ValueError('shared roll/activation needs actual native producer authority')
 s=matches[0];index=s['index']
 if (s['actor'] is not actor or s['move_id']!=move_id or index>=len(s['targets'])
     or s['targets'][index] is not target or _profile(e)!=s['profile'] or _lifetime(e)!=s['lifetime']):
  raise ValueError('move activation actor/target/order/profile mismatch')
 prepaid=s.get('prepaid_pass')
 if prepaid is not None:
  import pass_moves as PASS
  PASS.activation_authority(e,actor,move_id,s['targets'],prepaid)
 paid=s.get('paid_resolution',False)
 if paid:
  import conditional_damage_base as CONDITIONAL_DB,bide as BIDE
  if not (CONDITIONAL_DB.round_end_authorized(actor,target,move_id) or BIDE.authorized(e,actor,target,move_id)):
   raise ValueError('paid resolution lost its actual native declaration')
 ace=s.get('type_ace',{})
 extra=bool(index==0 and (ace.get('extra_move') or s.get('martial_artist',{}).get('extra_move')))
 extra=extra or bool(index==0 and __import__('hex_maniac').free_activation(e,actor,target,move_id))
 extra=extra or bool(index==0 and __import__('rune_master').move_authority(e,actor,target,move_id,'feat/폭발-룬'))
 expected_use=index==0 and prepaid is None and not paid and not(extra and ace.get('ignore_frequency'))
 if free_action is not extra or count_use is not expected_use:raise ValueError('shared activation cannot alter its cost/frequency boundary')
 if accuracy is not None and tuple(accuracy.get('targets',()))!=s['targets']:raise ValueError('shared target set changed')
 if index==0 and ((activation!={'started':True} if prepaid is not None else bool(activation)) or (accuracy is not None and set(accuracy)!={'targets'})):raise ValueError('producer observation cannot be prefilled')
 s['index']+=1


def effect_contributions(method):
 """A native call owns transient event contributions; input dictionaries do not."""
 from functools import wraps
 @wraps(method)
 def execute(e,actor,target,move_id,*args,**kwargs):
  scope={'actor':actor,'target':target,'move_id':None,'contributions':[]}
  scopes=getattr(e,'_event_use_scopes',None)
  if scopes is None:scopes=[];e._event_use_scopes=scopes
  scopes.append(scope)
  try:return method(e,actor,target,move_id,*args,**kwargs)
  finally:
   scopes[:]=[x for x in scopes if x is not scope]
   if not scopes:del e._event_use_scopes
 return execute


def _require_started_event_use(e,actor,target,move_id,*,scope_error,move_error=None,move_id_required=False):
 """Inspect the bound native call without changing its scope or authority.

 The optional mode retains indexed lookup (and KeyError) for a missing Move;
 the alternate mode retains its read-through .get rejection.
 """
 scopes=getattr(e,'_event_use_scopes',())
 if not scopes or scopes[-1].get('actor') is not actor or scopes[-1].get('target') is not target:
  raise ValueError(scope_error)
 current=scopes[-1]
 actual=current['move_id'] if move_id_required else current.get('move_id')
 if actual!=move_id:raise ValueError(scope_error if move_error is None else move_error)
 return current


def current_scope(e,actor,target,move_id):
 """Return only the verified, started native target group for this consumer."""
 return next((s for s in reversed(getattr(e,'_move_activation_scopes',[]))
  if s['actor'] is actor and s['move_id']==move_id and s['activation'].get('started')
  and 0<s['index']<=len(s['targets']) and s['targets'][s['index']-1] is target),None)


@contextmanager
def open_empty_field_scope(e,actor,move_id,cells,effects,*,move=None):
 """Issue authority only inside the native target-free area producer."""
 token=object();scope={'token':token,'actor':actor,'move_id':move_id,
  'cells':tuple(sorted(set(cells))),'effects':deepcopy(list(effects)),
  'profile':_profile(e),'lifetime':_lifetime(e)}
 import ice_lake as ICE_LAKE
 if not scope['cells'] or (not scope['effects'] and (move is None or move.get('id')!=move_id or not ICE_LAKE.empty_area_adopted(e,actor,move))):
  raise ValueError('actual empty area cells and field effects required')
 scopes=getattr(e,'_empty_field_activation_scopes',None)
 if scopes is None:scopes=[];e._empty_field_activation_scopes=scopes
 scopes.append(scope)
 try:yield token
 finally:
  scopes[:]=[candidate for candidate in scopes if candidate is not scope]
  if not scopes:del e._empty_field_activation_scopes


def verify_empty_field(e,actor,move,mm,token):
 """Bind a target-free use_move continuation to its actual area declaration."""
 import area_targets as AREA
 scope=require_empty_field_scope(e,actor,move.get('id'),token)
 effects=AREA.empty_field_effects(mm)
 cells=tuple(sorted(AREA.cells(e,actor,move)))
 if (scope['cells']!=cells or scope['effects']!=effects or
     tuple(move.get('_actual_targets',()))):
  raise ValueError('empty area activation actor/rule/geometry/profile mismatch')
 return scope


def require_empty_field_scope(e,actor,move_id,token):
 """Reject public/forged continuation tokens before any target-only gate."""
 matches=[scope for scope in getattr(e,'_empty_field_activation_scopes',())
          if scope['token'] is token]
 if len(matches)!=1:raise ValueError('empty area activation needs actual native producer authority')
 scope=matches[0]
 if (scope['actor'] is not actor or scope['move_id']!=move_id or
     scope['profile']!=_profile(e) or scope['lifetime']!=_lifetime(e)):
  raise ValueError('empty area activation actor/rule/geometry/profile mismatch')
 return scope


def activate_empty_area(e,actor,move,mm,*,weapon_id=None,struggle_choice=None,aim=None,appendage_id=None,set_damage=False,versatile_stat=None):
 """Atomically execute one mapped area Move that has no creature targets."""
 import area_targets as AREA
 import state_grants as G
 # A damaging Move may aim only at terrain; its damage mode has no recipient.
 # Status-only field declarations still reject a damage request before payment.
 if set_damage and move.get('class') not in ('물리','특수'):
  raise ValueError('empty area activation has no accuracy or damage declaration')
 effects=AREA.empty_field_effects(mm)
 import ice_lake as ICE_LAKE
 if not effects and not ICE_LAKE.empty_area_adopted(e,actor,move):return None
 if e.grid is None:raise ValueError('empty area activation requires an actual map')
 cells=tuple(sorted(AREA.cells(e,actor,move)))
 move_id=move['id'];profile=_profile(e);lifetime=_transition_lifetime(e)
 effect_declaration=deepcopy(effects)
 def apply(staged,staged_actor):
  if _profile(staged)!=profile or _transition_lifetime(staged)!=lifetime:
   raise ValueError('empty area activation source boundary changed')
  try:
   with open_empty_field_scope(staged,staged_actor,move_id,cells,effect_declaration,move=move) as token:
    return staged.use_move(staged_actor,staged_actor,move_id,
       _field_activation=token,weapon_id=weapon_id,
        struggle_choice=struggle_choice,aim=aim,appendage_id=appendage_id,versatile_stat=versatile_stat)
  except Exception as error:
   # A HeavyPending is a committed activation prefix, as on the ordinary
   # targeted path. Return a plain marker so the atomic graph can publish its
   # action/frequency and pending packet before the public exception resumes.
   import heavy_injury_adapter as HEAVY
   if type(error) is HEAVY.HeavyPending:
    return ('empty_field_heavy_pending',error.event_id)
   raise
 result=G.transition(e,actor,apply,include_grid=True)
 if (type(result) is tuple and len(result)==2
     and result[0]=='empty_field_heavy_pending'):
  import heavy_injury_adapter as HEAVY
  raise HEAVY.HeavyPending(result[1])
 return result


def paid_move_permission(engine, actor, target, move, mm):
    """Common admission before a native producer pays one Move's cost.

    Target geometry, physical-only composition limits and native hit effects
    remain with their actual producers. This grants no prepaid authority.
    """
    import turn as TURN
    import frequency as FREQ
    import action_lifecycle as ACTION
    import pokemon_party as PARTY, party_actions as COMMANDS, pokemon_understanding as BODY
    import pokemon_activities as POKEMON
    import partial_entities as PARTIAL, invisibility_state as INVISIBILITY
    import supplemental_state as SUPPLEMENTAL, actor_templates as TEMPLATES
    import vision_impairment as VISION, field_effects as FIELD_EFFECTS
    PARTIAL.require_complete(actor,'use_move');INVISIBILITY.require_move(engine,actor)
    SUPPLEMENTAL.require_actor_access(engine,actor,'use_move');TEMPLATES.require_ordinary(actor,'use_move')
    VISION.require_move(engine,actor,move)
    blocked=FIELD_EFFECTS.native_move_block_reason(engine,move['id'],actor)
    if blocked:raise ValueError(blocked)
    if not engine.encounter_active or engine._active_turn_actor is not actor:
        raise ValueError('paid Move requires the actual open own turn')
    import confusion_attacks as CONFUSION
    CONFUSION.preflight(engine,actor,move)
    import temporary_hp as TEMP
    TEMP.ensure_certain(engine,actor)
    PARTY.require_participation(engine,actor);COMMANDS.require_command(engine,actor,move['id'])
    BODY.require_activity(engine,actor,'move')
    if POKEMON.obedience_gate(engine,actor,target,move['id']) is not True:
        raise ValueError('paid Move needs the actual Pokemon obedience decision')
    if not actor.on_field or actor.captured or not TURN.can_act(engine,actor):
        raise ValueError('paid Move user cannot act')
    if not ACTION.ordinary_permission(engine,actor):raise ValueError('paid Move action unavailable')
    import move_permissions as PERMISSIONS
    import setup_move_state as SETUP
    import homebrew_weather as WEATHER
    import conditional_damage_base as CONDITIONAL
    import capability_actions as CAPABILITIES
    PERMISSIONS.require_native_move(engine,actor,move['id'])
    SETUP.require_native_scope(engine,actor,move['id'])
    WEATHER.require_actor(engine,actor,move['id'])
    if CONDITIONAL.action_locked(actor) and not CONDITIONAL.resolving(actor,move['id']):
        raise ValueError('paid Move is blocked by the native reserved action')
    kind=TURN.action_kind_of_move(engine,actor,move,mm)
    if not CAPABILITIES.action_permission(engine,actor,kind,move['id']):
        raise ValueError('paid Move capability action unavailable')
    allowed,why=FREQ.move_allowed(engine,actor,move['id'],outside_combat=False)
    if not allowed:raise ValueError(why)
    return kind
