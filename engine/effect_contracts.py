"""Native effect-dispatch adapter over shared root truth and fingerprint types.

A handler name is not proof of field support. Control fields have explicit
owners; unsupported execution and unresolved predicates remain different
outcomes. Receipts bind real actors and effect occurrences, not caller labels.
"""
from dataclasses import dataclass
from copy import deepcopy
from contextlib import contextmanager
import root_resolution as ROOT
import common_checks as C
import effect_lifetimes as LIFE

CONTROL=frozenset(('target','on','turns','scope','while','until','duration','repeat','at','when','trigger','optional','on_miss','on_natural_roll_min','on_natural_roll','if_weather','on_ko','if','except','limit'))
CONDITION=frozenset(('on_miss','on_natural_roll_min','on_natural_roll','if_weather','on_ko','if'))
ANNOTATIONS=frozenset(('note','confidence'))
SCHEMAS={
 'forced_movement':{'distance','direction','stop_cells','allow_fainted'},
 'push':{'meters'},
 'stage_change':{'stat','delta','base','linked_to'},'stat_mod':{'stat','value','min','multiplier'},
 'apply_status':{'status','parameters'},'apply_status_random':{'options'},'cure_status':{'status'},'cure_all_status':set(),
 'heal':{'amount','fraction_of_max','replaces'},'hp_loss':{'value','unpreventable'},'self_hp_set':{'self_hp','unpreventable'},
 'temp_hp':{'value'},'set_weather':{'weather','rounds'},'field_effect':{'field','rounds','effect'},
 'skill_check_mod':{'value'},'damage_reduction':{'value'},'evasion_mod':{'value'},'accuracy_mod':{'value'},'save_mod':{'value'},
 'initiative':{'delta','set_to','multiplier','priority'},'initiative_multiplier':{'value'},'drain':{'fraction'},'reset_stages':set(),
 'consume_buff':{'buff','ignore_conditions'},'never_miss':set(),'grant_move':{'moves'},
 'type_change':{'add_type','lose_type','set_type','fallback','single_type'},
 'size_change':{'to'},
}
# Field creation, hazard cleanup and repeat locks are owned by their user.
SELF_DEFAULT=frozenset(('damage_reduction','save_mod','type_change','grant_ability','ability_change','size_change','heal_injury','consume_buff','counter','self_hp_set','drain','grant_move','destroy_hazards','field_effect','repeat_each_turn'))

@dataclass(frozen=True)
class Issue:
 category:str
 field:str
 detail:str

class EffectContractError(ValueError):
 def __init__(self,source,index,issue):
  self.source_id=source;self.effect_index=index;self.issue=issue
  super().__init__(f'{issue.category}: {source}[{index}] {issue.field}: {issue.detail}')

@dataclass(frozen=True)
class Outcome:
 source_id:str
 occurrence:str
 status:str
 reason:object=None
 receipt:object=None

class BatchResult(tuple):
 def __new__(cls,done,held,outcomes=()):
  result=tuple.__new__(cls,(done,held));result.outcomes=tuple(outcomes);return result
 def __getnewargs__(self):return (self[0],self[1],self.outcomes)
 def __deepcopy__(self,memo):
  result=BatchResult(self[0],self[1]);memo[id(self)]=result
  result.outcomes=deepcopy(self.outcomes,memo)
  # Staging and commit already map the owning engine in their shared memo.
  # An isolated batch copy still borrows its existing live engine.
  if hasattr(self,'engine'):result.engine=memo.get(id(self.engine),self.engine)
  return result
 @property
 def pending(self):
  rows=getattr(getattr(self,'engine',None),'_effect_dispatch_receipts',{})
  def unresolved(outcome):
   row=rows.get(outcome.receipt,{})
   child=row.get('result')
   if isinstance(child,BatchResult):return bool(child.pending)
   return row.get('status',outcome.status) in ('condition_unknown','awaiting_input','unsupported_execution','unresolved_source','execution_failed','deferred_suffix')
  return tuple(x for x in self.outcomes if unresolved(x))

def source_id(engine,src):
 if not isinstance(src,str) or not src:raise ValueError('actual effect source identity required')
 raw=src.split(' (',1)[0]
 if raw in engine.r.units:return raw
 if '/' in raw:
  prefix,name=raw.split('/',1)
  try:
   resolved=engine.r.selection.resolve_name(name,(prefix+'/',))
   if resolved in engine.r.units:return resolved
  except (ValueError,KeyError):pass
 # Non-catalog GM and environmental producers retain their complete identity.
 return raw

def recipients(actor,target,effect):
 if effect.get('on')=='after use' and effect.get('type') in ('counter','type_change','stage_change') and effect.get('target','self')=='self':
  return (actor,)
 default='self' if effect.get('type') in SELF_DEFAULT else 'target'
 selected=effect.get('target',effect.get('on',default))
 if 'target' in effect and 'on' in effect and effect['target']!=effect['on']:raise ValueError('conflicting effect target and on selectors')
 if selected=='self':return (actor,)
 if selected=='target':return (target,)
 if selected in ('both','self and target') and effect.get('type') in {'stage_change','stat_mod','apply_status','apply_status_random','cure_status','cure_all_status','heal','hp_loss','temp_hp','evasion_mod','accuracy_mod','reset_stages','save_mod'}:return tuple(dict.fromkeys((actor,target)))
 raise ValueError('explicit native target-set binding required for '+str(selected))

def hit_recipients(engine,actor,target,effect,source):
 """Resolve supported native per-hit selectors without widening their source."""
 if source=='feat/왕복-여행':
  import native_switch_transfer as SWITCH
  if effect==SWITCH.ROUND_EFFECT:return (target,)
 if (source=='move/천둥차기'
       and effect=={'type':'stage_change','stat':'def','delta':-1,'target':'all_targets'}):
  # The native activation dispatches this declaration once per actual hit.
  return (target,)
 if effect.get('type')=='apply_coat' and effect.get('target')=='all in burst':
  return (target,)
 if effect.get('target')=='all_targets':
  import native_area_hit_effects as AREA_HIT
  return AREA_HIT.preflight(engine,actor,target,effect,source)
 return recipients(actor,target,effect)

def inspect(engine,actor,target,effect,source,index=0):
 import effects as FX
 if not isinstance(effect,dict) or not isinstance(effect.get('type'),str):return Issue('unsupported_execution','type','typed effect record required')
 kind=effect['type']
 if kind=='pledge' and 'rainbow_observed' in effect:
  import pledge_state as PLEDGE
  try:PLEDGE.prepare(engine,actor,target,effect,source)
  except (ValueError,TypeError,KeyError) as ex:return Issue('unresolved_source','pledge_rainbow',str(ex))
  return None
 if kind=='ability_transition':
  import ability_transitions as ABILITY_TRANSITIONS
  try:ABILITY_TRANSITIONS.preflight(engine,actor,target,effect,source)
  except (ValueError,TypeError,KeyError) as ex:return Issue('unresolved_source','ability_transition',str(ex))
  return None
 if kind=='initiative':
  import blessing_effects as BLESSINGS
  if BLESSINGS.definition(engine.r,source) is not None:
   try:BLESSINGS.preflight(engine,actor,effect,source)
   except ValueError as ex:return Issue('unresolved_source','team_initiative',str(ex))
   return None
 if kind=='repeat_each_turn':
  import forced_move_lock as FORCED_MOVE
  try:
   if source not in engine.r.moves or not FORCED_MOVE.manages(engine,source):
    raise ValueError('repeat-each-turn needs the exact forced Move choice consumer')
   if set(effect)-{'type','until','_src'}:
    raise ValueError('repeat-each-turn has unsupported control fields')
  except (ValueError,TypeError,KeyError) as ex:return Issue('unsupported_execution','lifetime',str(ex))
  return None
 if kind in ('zone','ally_struggle','copy_move','random_move','repeat_last_move'):return Issue('unsupported_execution','type','native source-bound execution consumer is not implemented for '+kind)
 if 'except' in effect and kind!='never_miss':return Issue('unsupported_execution','except','exception predicate requires a registered native consumer')
 if 'turns' in effect and kind not in ('grounding','delayed_attack'):return Issue('unsupported_execution','turns','turn-count lifetime has no declared native owner for '+kind)
 if kind not in FX.HANDLERS and kind not in FX.JUDGEMENT_TYPES|FX.ENGINE_TYPES:return Issue('unsupported_execution','type','no executable or deferred native consumer for '+kind)
 try:
  if kind=='blessing':
   import blessing_effects as BLESSINGS
   targets=(actor,) if BLESSINGS.definition(engine.r,source) is not None else recipients(actor,target,effect)
  elif kind=='counter' and effect.get('on')=='after use':targets=(actor,)
  elif (kind=='reset_stages' and source=='move/흑안개'
        and effect=={'type':'reset_stages','target':'all',
                    '_src':'인카운터에 존재하는 모든 포켓몬과 트레이너의 전투단계를 기본상태로 되돌린다(보통 0).'}):
   import weapon_actions as WEAPONS
   if not WEAPONS.is_field(WEAPONS.range_spec(engine,engine.r.move(source))):
    return Issue('unresolved_source','target','Haze requires its selected Field range')
   targets=tuple(WEAPONS.field_members(engine))
  else:targets=hit_recipients(engine,actor,target,effect,source)
 except ValueError as ex:return Issue('unsupported_execution','target',str(ex))
 for field in ('scope','when','trigger','at','optional'):
  if field in effect and not (kind=='free_maneuver' and field=='optional') and not (kind=='reaction_shield' and field=='trigger' and effect[field]=='user hit by a move'):return Issue('unresolved_source' if field=='optional' else 'unsupported_execution',field,'source-specific '+field+' adapter required; field cannot be ignored')
 if kind in SCHEMAS:
  unknown={k for k in effect if not k.startswith('_')}-({'type'}|CONTROL|ANNOTATIONS|SCHEMAS[kind])
  if unknown:return Issue('unsupported_execution',sorted(unknown)[0],'field has no declared handler owner')
 if 'on_natural_roll' in effect and effect['on_natural_roll']!='even':return Issue('unsupported_execution','on_natural_roll','only exact even-natural predicate is supported')
 if 'on_natural_roll_min' in effect and type(effect['on_natural_roll_min']) is not int:return Issue('unsupported_execution','on_natural_roll_min','integer natural threshold required')
 if 'limit' in effect and effect['limit'] not in ('once_per_scene','once_per_scene_per_target'):
  import alternate_move_modes as ALTERNATE
  import post_resolution_stage_effects as POST_STAGE
  move=engine.r.move(source) if source in engine.r.moves else None
  if move is None or not (ALTERNATE.owns(engine.r,move,effect) or
                          POST_STAGE.owns(engine.r,move,effect)):
   return Issue('unsupported_execution','limit','explicit frequency policy required')
 if kind=='blessing':
  import blessing_effects as BLESSINGS
  try:BLESSINGS.preflight(engine,actor,effect,source)
  except ValueError as ex:return Issue('unresolved_source','blessing',str(ex))
 if kind=='clear_field' and any('blessing' in str(x) for x in effect.get('remove',[])):
  import blessing_effects as BLESSINGS
  try:BLESSINGS.preflight_clear(engine,source,actor)
  except ValueError as ex:return Issue('unresolved_source','blessing_removal',str(ex))
 if kind=='swap_field_sides':
  import hazard_state as HAZARDS
  import blessing_effects as BLESSINGS
  # A Field activation anchors on its user; the exchange uses the actual
  # opposing battlefield side, not that non-recipient anchor.
  try:BLESSINGS.preflight_swap(engine,actor,HAZARDS.opponent(engine,actor,preflight=True),source)
  except ValueError as ex:return Issue('unresolved_source','blessing_exchange',str(ex))
 if kind=='apply_coat':
  import coat_effects as COATS
  try:COATS.preflight(engine,actor,target,effect,source)
  except ValueError as ex:return Issue('unresolved_source','coat',str(ex))
 if kind=='custom_condition':
  import custom_condition_effects as CUSTOM
  try:CUSTOM.prepare(engine,actor,target,effect,source)
  except ValueError as ex:return Issue('unresolved_source','custom_condition',str(ex))
 if kind=='remove_coats' or (kind=='clear_field' and any('coat' in str(x) for x in effect.get('remove',[]))):
  import coat_effects as COATS
  affected=targets if kind=='remove_coats' else (getattr(engine,'everyone',None) or [actor,target])
  try:COATS.preflight_clear(engine,affected,source=source,applied_by=actor)
  except ValueError as ex:return Issue('unresolved_source','coat_removal',str(ex))
 if kind=='switch_out':
  import native_switch_transfer as SWITCH
  try:SWITCH.inspect(engine,actor,target,effect,source)
  except ValueError as ex:return Issue('unresolved_source','native_switch',str(ex))
 if kind=='next_roll_bonus':
  import roll_effects as ROLLS
  try:ROLLS.preflight(engine,actor,target,effect,source)
  except ValueError as ex:return Issue('unresolved_source','roll_components',str(ex))
 if kind=='next_attack_modifier':
  import event_effects as EVENTS
  try:EVENTS.preflight(engine,actor,effect,source)
  except ValueError as ex:return Issue('unresolved_source','future_effect',str(ex))
 if kind=='steal_buff':
  import food_effects as FOOD
  try:FOOD.transfer_live_preflight(engine,actor,target,source)
  except ValueError as ex:return Issue('unresolved_source','food_transfer',str(ex))
 if kind=='grant_move':
  import state_grants as GRANTS
  import move_state as MOVES_STATE
  try:
   moves=GRANTS.move_grants(engine.r,effect)
   import move_permissions as PERMISSIONS
   if PERMISSIONS.form_policy(engine.r,source):raise ValueError('temporary form moves require the native paid form activation')
   for recipient in targets:
    registration=getattr(recipient,'_state_registration_source',None)
    key=registration or 'preflight:effect:'+source+':'+str(index)
    MOVES_STATE.preflight_move_grants(recipient,moves,key,'passive' if registration else 'effect',dict(owner_id=actor.entity_id,lifetime='while_registered' if registration else 'until_source_ends',rule_id=source,tutor_points=0))
  except (ValueError,TypeError,KeyError) as ex:return Issue('unresolved_source','moves',str(ex))
 if kind=='never_miss':
  try:never_miss_allowed(engine,actor,target,effect,dict(attacker=actor,target=target,engine=engine))
  except EffectContractError as ex:return ex.issue
 if kind=='stage_change' and (type(effect.get('delta')) is not int or effect.get('stat') not in ('atk','def','spa','spd','spe','acc','eva','all') or effect.get('base')):return Issue('unsupported_execution','stage_change','integer combat-stage delta and supported stat required; base is a distinct source policy')
 if kind=='stat_mod' and ('multiplier' in effect or type(effect.get('value')) is not int):return Issue('unsupported_execution','stat_mod','native stat consumer requires integer additive value')
 if kind in ('damage_reduction','evasion_mod','accuracy_mod','save_mod') and type(effect.get('value')) is not int:return Issue('unsupported_execution','value','native modifier requires integer value')
 if kind=='heal':
  if 'fraction_of_max' in effect:
   value=effect['fraction_of_max']
   if not isinstance(value,(list,tuple)) or len(value)!=2 or any(type(x) is not int for x in value) or value[1]<=0:return Issue('unsupported_execution','fraction_of_max','integer numerator and positive denominator required')
  elif 'amount' not in effect:return Issue('unsupported_execution','amount','native healing amount required')
 if kind=='apply_status' and not isinstance(effect.get('status'),str):return Issue('unsupported_execution','status','one named condition required')
 if kind in ('initiative','initiative_multiplier'):
  import initiative_derivation as INITIATIVE
  try:
   INITIATIVE.selected(engine.r,source)
   INITIATIVE.operation(effect)
  except (ValueError,TypeError,KeyError) as ex:return Issue('unsupported_execution','initiative',str(ex))
 if kind=='apply_status':
  import condition_instances as CONDITIONS
  if effect.get('status')=='조이기':
   import vortex_state as VORTEX
   try:VORTEX.escape_bonus(effect.get('parameters'))
   except ValueError as ex:return Issue('unsupported_execution','parameters',str(ex))
  elif 'parameters' in effect and effect.get('status') not in CONDITIONS.SUPPORTED:return Issue('unsupported_execution','parameters','this condition has no parameter consumer')
  if effect.get('status') in CONDITIONS.SUPPORTED:
   try:
    for recipient in targets:CONDITIONS.prepare(engine,recipient,effect['status'],parameters=effect.get('parameters'),applied_by=actor)
   except (ValueError,KeyError) as ex:return Issue('unresolved_source','condition_parameters',str(ex))
 if LIFE.declared(effect):
  try:
   for recipient in targets:LIFE.prepare(engine,actor,recipient,effect,source)
  except LIFE.TimingAmbiguous as ex:return Issue('unresolved_source','lifetime',str(ex))
  except (LIFE.TimingUnsupported,ValueError) as ex:return Issue('unsupported_execution','lifetime',str(ex))
 return None

def item_issue(engine,actor,target,effect,source):
 """The item producer owns only these exact native payloads, before payment."""
 import effects as FX
 import restorative_items as REST
 kind=effect.get('type')
 native={'revive':{'hp','target'},'stat_base_mod':{'stat','value','vitamin','target'},'exp_gain':{'value','target','note'},'stage_reset':{'target'},'tag':{'tag'}}
 if source in ('item/크리티컬-커터','item/이펙트가드'):
  expected=engine.r.item_effects(source)[0]
  if effect not in expected:return Issue('unresolved_source','source','native X payload differs from selected source')
  REST.selected(engine,source)
  return None
 if kind in native:
  if source not in engine.r.selection.units or engine.r._selected_rule(source)!=source:return Issue('unresolved_source','source','selected item source required')
  if set(effect)-({'type'}|native[kind]):return Issue('unsupported_execution','payload','native item consumer does not own extra fields')
  if effect not in engine.r.item_effects(source)[0]:return Issue('unresolved_source','source','native item payload differs from selected source')
  if effect.get('target','target')!='target':return Issue('unsupported_execution','target','item native consumer requires actual recipient')
  if kind=='revive' and not (type(effect.get('hp')) is int or effect.get('hp')=='max_hp/2'):return Issue('unsupported_execution','hp','revive expression has no native consumer')
  if kind=='stat_base_mod' and (effect.get('vitamin') is not True or effect.get('stat') not in target.stats or type(effect.get('value')) is not int):return Issue('unsupported_execution','vitamin','native vitamin stat and integer delta required')
  if kind=='tag' and effect.get('tag')!='한약':return Issue('unsupported_execution','tag','item tag has no declared consumer')
  return None
 normalized=dict(effect)
 if kind=='heal' and 'value' in normalized and 'amount' not in normalized:normalized['amount']=normalized.pop('value')
 return inspect(engine,actor,target,normalized,source)

def require(engine,actor,target,effects,src,consumer=None):
 source=source_id(engine,src)
 for index,effect in enumerate(effects):
  issue=item_issue(engine,actor,target,effect,source) if consumer=='items.use_item' else inspect(engine,actor,target,effect,source,index)
  if consumer not in (None,'items.use_item'):raise ValueError('unregistered native effect consumer')
  if issue is not None:raise EffectContractError(source,index,issue)
 return source

def condition(engine,effect,ctx,*,source=None):
 import effects as FX
 import effects_ext as EXT
 checks=[]
 def known(value):return ROOT.TRUE if value else ROOT.FALSE
 hit=ctx.get('hit')
 import move_completion as COMPLETE
 if COMPLETE.field_effect(effect) and ctx.get('after_all_targets'):
  checks.append(ROOT.TRUE if COMPLETE.authorized_field(engine,ctx,effect) else ROOT.Predicate(ROOT.Truth.UNKNOWN,'actual field activation completion'))
 elif __import__('declarative_move_contracts').after_all(engine.r,effect):
  checks.append(ROOT.TRUE if COMPLETE.authorized(engine,ctx) else ROOT.Predicate(ROOT.Truth.UNKNOWN,'actual all-target completion'))
 elif 'native_action' in ctx:
  import action_lifecycle as ACTION
  checks.append(ACTION.post_action_condition(engine,ctx,source))
 elif effect.get('type') in ('counter','type_change','stage_change') and effect.get('on')=='after use':
  checks.append(ROOT.TRUE if COMPLETE.authorized(engine,ctx) else ROOT.Predicate(ROOT.Truth.UNKNOWN,'actual all-target completion'))
 elif type(hit) is not bool:checks.append(ROOT.Predicate(ROOT.Truth.UNKNOWN,'actual hit observation'))
 else:checks.append(known(not hit if effect.get('on_miss') else hit))
 nat=ctx.get('nat')
 if 'on_natural_roll_min' in effect:
  import combat_precision_features as CPF
  face=CPF.effect_natural(engine,ctx['attacker'],ctx.get('move'),nat,actual_damage_type=ctx.get('actual_damage_type'))
  checks.append(ROOT.Predicate(ROOT.Truth.UNKNOWN,'actual natural accuracy observation') if face is None else known(face>=__import__('combat_modifiers').incoming_status_threshold(ctx['target'],effect.get('status'),effect['on_natural_roll_min'])))
 if effect.get('on_natural_roll')=='even':checks.append(ROOT.Predicate(ROOT.Truth.UNKNOWN,'actual natural accuracy observation') if nat is None else known(nat%2==0))
 if effect.get('if_weather'):checks.append(known(FX.weather_matches(engine,effect['if_weather'],ctx.get('attacker'))))
 if effect.get('on_ko'):checks.append(ROOT.Predicate(ROOT.Truth.UNKNOWN,'actual attributable KO observation') if 'ko' not in ctx else known(ctx['ko']))
 text=effect.get('if')
 import event_effects as EVENTS
 if text is not None and not EVENTS.future_predicate(engine.r,source,effect):
  if not isinstance(text,str):checks.append(ROOT.Predicate(ROOT.Truth.UNKNOWN,'typed source condition'))
  else:
   try:
    if source=='move/벌레먹기' and effect.get('type')=='steal_buff' and text=='target has or consumed one this scene':
     import food_effects as FOOD
     result=FOOD.theft_condition(ctx['target'])
    else:result=condition_text(engine,ctx['attacker'],ctx['target'],text,ctx)
   except (KeyError,TypeError,AttributeError):result=None
   checks.append(ROOT.Predicate(ROOT.Truth.UNKNOWN,'condition: '+text) if result is None else known(result))
 return ROOT.conjunction(*checks)

def issue_receipt(engine,source,actor,target,effect,index):
 seq=getattr(engine,'_effect_dispatch_sequence',0)+1;engine._effect_dispatch_sequence=seq
 occurrence='effect:'+str(seq)+':'+str(index);token=object()
 row={'receipt':token,'source_id':source,'occurrence':occurrence,'actor':actor,'target':target,'effect':deepcopy(effect),'fingerprint':ROOT.fingerprint(effect),'status':'dispatching'}
 if not hasattr(engine,'_effect_dispatch_receipts'):engine._effect_dispatch_receipts={}
 engine._effect_dispatch_receipts[token]=row
 return occurrence,token

def validate_receipt(engine,receipt,source,occurrence,actor,target,effect):
 try:row=getattr(engine,'_effect_dispatch_receipts',{}).get(receipt)
 except TypeError:raise ValueError('opaque dispatcher receipt required')
 if not row or row['receipt'] is not receipt or row['source_id']!=source or row['occurrence']!=occurrence or row['actor'] is not actor or row['target'] is not target or row['fingerprint']!=ROOT.fingerprint(effect):raise ValueError('effect receipt source, occurrence, actors or payload mismatch')
 if 'turn_end_owner' in row or 'turn_end_close' in row:
  import action_lifecycle as ACTION
  ACTION.validate_turn_end_closures(engine)
 return True

def finish(engine,receipt,status,result=None):
 row=engine._effect_dispatch_receipts[receipt];row['status']=status;row['result']=result


def validate_condition_request(engine,row,*,completed=False):
 request=row.get('condition_request')
 if type(request) is not dict or set(request)!={'context','profile','boundary'}:
  raise ValueError('actual suspended condition request required')
 ctx=request['context']
 if (type(ctx) is not dict or ctx.get('attacker') is not row['actor']
     or ctx.get('target') is not row['target'] or ctx.get('engine') is not engine
     or type(request['profile']) is not str or type(request['boundary']) is not tuple
     or len(request['boundary'])!=6):raise ValueError('condition request lost its actual producer context')
 if completed:
  reply=row.get('condition_reply');result=row.get('condition_result')
  if (row['effect'].get('if')!='target was asleep' or 'target_was_asleep' in ctx
      or type(reply) is not dict or set(reply)!={'target_was_asleep','reason'}
      or type(reply['target_was_asleep']) is not bool or type(reply['reason']) is not str or not reply['reason'].strip()
      or type(result) is not dict or result.get('receipt') is not row['receipt']
      or result.get('status') not in ('completed','awaiting_input')):
   raise ValueError('condition result lacks its actual accepted fact and dispatch')
 return request


def retain_suffix(engine,receipt,source,actor,target,effects,ctx):
 """Bind a blocked suffix to the original occurrence, never to a new attack."""
 if not effects:return None
 occurrence,token=issue_receipt(engine,source,actor,target,{'type':'_deferred_batch','effects':effects},0)
 row=engine._effect_dispatch_receipts[token]
 row.update(status='deferred_suffix',blocked_on=receipt,effects=deepcopy(effects),context=freeze_context(engine,ctx),profile=source_profile(engine,source),boundary=boundary(engine,actor,target),resumed=False)
 engine._effect_dispatch_receipts[receipt]['continuation']=token
 return Outcome(source,occurrence,'deferred_suffix','waiting for preceding effect completion',token)


def condition_text(engine,actor,target,text,ctx):
 import effects as FX
 import re
 import equipment_protection as PROTECTION
 if text=='dealt damage':
  dealt=ctx.get('dealt')
  return dealt>0 if type(dealt) is int and dealt>=0 else None
 if text in FX.KNOWN_IF:
  if text=='super_effective' and 'multiplier' not in ctx:return None
  if text=='crit' and 'crit' not in ctx:return None
  return FX.KNOWN_IF[text](ctx)
 import class_move_grants as CLASS_MOVES
 def ghost_for_move():return '고스트' in actor.types or CLASS_MOVES.uses_ghost_curse(actor,ctx.get('move'))
 exact={
 'user is 고스트':ghost_for_move,'user is ghost':ghost_for_move,
 'user not 고스트':lambda:not ghost_for_move(),
 'target is ally':lambda:None if getattr(target,'side',None) is None or getattr(actor,'side',None) is None else target.side==actor.side,
 'target was asleep':lambda:ctx.get('target_was_asleep'),
 'target paralyzed':lambda:'마비' in target.conditions,'target is poisoned':lambda:bool({'독','맹독'} & target.conditions),
 'target has a status':lambda:bool(target.conditions-{'기절'}),'target has status':lambda:bool(target.conditions-{'기절'}),
 'user holds no item':lambda:PROTECTION.itemless_for_move(engine,actor,ctx.get('move')),'user holds nothing':lambda:PROTECTION.itemless_for_move(engine,actor,ctx.get('move')),
 'target holds nothing':lambda:not __import__('held_equipment').any_held(target),
 'user has >= 1 injury':lambda:actor.injuries>=1,'user current HP <= half':lambda:actor.hp*2<=actor.base_max_hp,
 'target HP above 50%':lambda:target.hp*2>target.base_max_hp,'target HP below half':lambda:target.hp*2<target.base_max_hp,
 'weather effect active':lambda:bool(__import__('effects').effective_weather(engine,actor)),
 'sunny weather':lambda:FX.weather_matches(engine,'sunny',actor),'in sunny':lambda:FX.weather_matches(engine,'sunny',actor),
 'rain weather':lambda:FX.weather_matches(engine,'rain',actor),'in rain':lambda:FX.weather_matches(engine,'rain',actor),'hit':lambda:ctx.get('hit'),
 'single target':lambda:None if 'actual_targets' not in ctx else len(ctx['actual_targets'])==1,
 }
 if text in exact:return exact[text]()
 match=re.fullmatch(r'user is (.+)',text)
 if match:
  import type_state as TYPES
  if match[1] in TYPES.allowed_types(engine.r):return match[1] in actor.types
 match=re.fullmatch(r'stockpile\s*(==|>=)\s*([0-9]+)',text)
 if match:
  actual=actor.counters.get('stockpile',0);threshold=int(match[2]);return actual==threshold if match[1]=='==' else actual>=threshold
 return None


def freeze_context(engine,ctx):
 memo={id(engine):engine,id(engine.r):engine.r}
 def preserve(value):
  if hasattr(value,'conditions') and hasattr(value,'stats'):memo[id(value)]=value
  elif isinstance(value,dict):
   for child in value.values():preserve(child)
  elif isinstance(value,(list,tuple)):
   for child in value:preserve(child)
 preserve(ctx)
 # Dispatcher capability tokens remain the actual original objects.
 for token in getattr(engine,'_effect_dispatch_receipts',{}):memo[id(token)]=token
 return deepcopy(ctx,memo)


def never_miss_allowed(engine,actor,target,effect,ctx):
 """Unknown exceptions cannot be negated into an automatic hit."""
 import effects as FX
 if effect.get('if_weather') and not FX.weather_matches(engine,effect['if_weather'],actor):return False
 condition=True if 'if' not in effect else condition_text(engine,actor,target,effect['if'],ctx)
 exception=False if 'except' not in effect else condition_text(engine,actor,target,effect['except'],ctx)
 if condition is None or exception is None:
  field='if' if condition is None else 'except'
  raise EffectContractError(ctx.get('source_id','effect/never_miss'),0,Issue('unresolved_source',field,'never-miss predicate has no actual truth value'))
 return condition is True and exception is False


def source_profile(engine,source):
 if source in engine.r.selection.units:
  selected=engine.r._selected_rule(source)
  if source in engine.r.moves:payload=engine.r.move_mech(source)
  elif source in engine.r.items_mech:payload=engine.r.item_effects(source)
  else:payload=engine.r.selection.units[source]
  return ROOT.fingerprint({'source':selected,'payload':payload})
 return ROOT.fingerprint({'explicit_non_catalog_producer':source})


def boundary(engine,actor,target):
 def lifetime(c):
  state=c.spec.get('frequency_state',{})
  return (state.get('scene',0),state.get('day',0),state.get('turn',0))
 return (getattr(engine,'round_no',None),getattr(engine,'elapsed_seconds',None),getattr(engine,'encounter_active',None),getattr(engine,'_active_turn_actor',None),lifetime(actor),lifetime(target))


def ensure_clear(engine):
 """A mandatory suffix cannot be bypassed by a new action or time boundary.

 Optional child grants without a suffix retain their source-owned close-window
 policy. Other unrelated historical unsupported effects do not become a global
 world lock merely because they have an audit receipt.
 """
 import clock_invocations as CLOCK
 CLOCK.ensure_clear(engine)
 import equipment_actions as EQUIPMENT
 EQUIPMENT.ensure_clear(engine)
 import held_equipment as HELD
 import world_entities as WORLD
 for actor in WORLD.actors(engine):HELD.require_resolved(actor)
 rows=getattr(engine,'_effect_dispatch_receipts',{})
 allowed=getattr(engine,'_effect_resuming_receipt',None)
 for token,row in rows.items():
  if 'blocked_on' not in row:continue
  child=row.get('result')
  pending=bool(child.pending) if isinstance(child,BatchResult) else row.get('status') in ('deferred_suffix','awaiting_input','unresolved_source','unsupported_execution','execution_failed')
  if not pending:continue
  if allowed is not None and (token is allowed or row.get('blocked_on') is allowed):continue
  raise ValueError('unfinished required effect suffix must resolve before a new action or time/scene boundary')
 return True


@contextmanager
def resuming(engine,receipt):
 rows=getattr(engine,'_effect_dispatch_receipts',{})
 try:row=rows[receipt]
 except (KeyError,TypeError):raise ValueError('registered opaque effect receipt required for resuming')
 if row.get('receipt') is not receipt:raise ValueError('actual effect receipt identity required')
 previous=getattr(engine,'_effect_resuming_receipt',None)
 if previous is not None and previous is not receipt:
  # Nested suffix execution is a child of the already admitted continuation.
  preceding=rows.get(previous,{})
  if preceding.get('continuation') is not receipt and row.get('blocked_on') is not previous:raise ValueError('unrelated effect cannot borrow another continuation scope')
 engine._effect_resuming_receipt=receipt
 try:yield
 finally:
  if previous is None:delattr(engine,'_effect_resuming_receipt')
  else:engine._effect_resuming_receipt=previous


def validate_continuation(engine,preceding_receipt):
 """Read-only suffix validation, usable before child acceptance or mutation."""
 rows=getattr(engine,'_effect_dispatch_receipts',{})
 try:preceding=rows[preceding_receipt]
 except (KeyError,TypeError):raise ValueError('actual dispatcher receipt required for continuation')
 token=preceding.get('continuation')
 if token is None:return None
 row=rows[token]
 if source_profile(engine,row['source_id'])!=row['profile']:raise ValueError('effect source profile changed before continuation')
 if ROOT.fingerprint({'type':'_deferred_batch','effects':row['effects']})!=row['fingerprint']:raise ValueError('deferred effect payload changed')
 if boundary(engine,row['actor'],row['target'])!=row['boundary']:raise ValueError('effect continuation lifetime boundary changed')
 return row

