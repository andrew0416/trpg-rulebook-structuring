"""Digital and linked-form state contracts; action execution stays with its owner."""
from copy import deepcopy
import state_fields as F
import world_entities as W
import arithmetic_policy as M
import skill_modifiers as SKILL

FIELDS={
 'digital_avatar':{'actor_id','network_id','integrity','max_integrity','temp_integrity','status','anchor_id','entry_basis','optional_trainer_stats','program_ids'},
 'digital_node':{'node_type','network_id','integrity','max_integrity','temp_integrity','status','anchor_id','controller_id','defense','evasion','data_state','bot_id'},
 'paired_forms':{'human_id','pokemon_id','active_id','sharing_rank'},
 'animated_golem':{'creator_id','creation_level','stats','type','material_id','hp','max_hp','created_at','destroyed'},
}

def _actor(index,uid,kind=None):
 W._text(uid,'actor reference')
 if uid not in index or (kind and index[uid].kind!=kind):raise ValueError('special entity actor reference does not resolve to required kind')
 return index[uid]

def _object(registry,uid,kind=None):
 W._text(uid,'object reference')
 if uid not in registry or (kind and registry[uid].get('kind')!=kind):raise ValueError('special entity object reference does not resolve to required kind')
 return registry[uid]

def _number(value,label):
 from math import isfinite
 if isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value) or value<0:raise ValueError(label+' requires finite nonnegative time')
 return value

def _integrity(row):
 F.integer(row.get('integrity'),'current integrity');F.integer(row.get('max_integrity'),'maximum integrity',1)
 if row['integrity']>row['max_integrity']:raise ValueError('integrity exceeds its separate maximum')
 if row.get('status') not in ('connected','disconnected','ejected','disabled'):raise ValueError('explicit digital connection state required')
 if row['status']=='connected' and row['integrity']<=0:raise ValueError('zero integrity requires ejection or disabled state')

def avatar_maximum(e,actor):
 tech=SKILL.effective_rank(e.r,actor,'기술학')
 return actor.level*(2 if actor.kind=='trainer' else 1)+M.ratio(actor.stats['hp']*tech,2)+10

def avatar(e,row,index,registry,p):
 actor=_actor(index,row.get('actor_id'));network=_object(registry,row.get('network_id'))
 if network['id']==row['id']:raise ValueError('avatar cannot be its own network')
 if any(x.get('kind')=='digital_avatar' and x['id']!=row['id'] and x.get('actor_id')==row['actor_id'] and x.get('status')=='connected' and row.get('status')=='connected' for x in registry.values()):raise ValueError('one real actor cannot have two connected avatars')
 _integrity(row);F.integer(row.get('temp_integrity'),'temporary integrity',0)
 if type(row.get('optional_trainer_stats')) is not bool:raise ValueError('digital trainer stat option must be explicit')
 if row['optional_trainer_stats'] and actor.kind!='trainer':raise ValueError('optional digital stat replacement applies only to trainers')
 tech=SKILL.rank(e.r,actor,'기술학')[2]
 effect_tech=SKILL.effective_rank(e.r,actor,'기술학');effect_focus=SKILL.effective_rank(e.r,actor,'집중')
 expected=avatar_maximum(e,actor)
 if row['max_integrity']!=expected:raise ValueError('maximum integrity uses Technology rank / 2 in place of HP multiplier 3')
 basis=row.get('entry_basis');anchor=row.get('anchor_id')
 if basis not in ('technology','interface','anchor','digital_avatar_edge'):raise ValueError('digital entry basis must be explicit')
 if basis=='technology' and tech<4:raise ValueError('independent technology entry requires Adept rank')
 if basis=='interface' and row['status']=='connected':
  import state_grants as GRANTS
  if not {SKILL.key(x) for x in GRANTS.effective_capabilities(actor)} & {SKILL.key(x) for x in ('접속','capability/접속','Wired')}:raise ValueError('interface entry requires actual sourced capability')
 if basis=='digital_avatar_edge' and not any(x in ('디지털-아바타','poke_edge/디지털-아바타','디지털 아바타') for x in actor.spec.get('poke_edges',actor.spec.get('edges',[]))):raise ValueError('avatar-edge entry requires actual learned edge')
 if basis=='anchor':
  parent=_object(registry,anchor,'digital_avatar')
  if parent['id']==row['id'] or parent.get('entry_basis')=='anchor':raise ValueError('anchor must independently qualify rather than form a circular chain')
  if parent['network_id']!=row['network_id']:raise ValueError('anchor and dependent must share a network')
  if row['status']=='connected' and parent['status']!='connected':raise ValueError('connected dependent requires a connected anchor')
  owner=_actor(index,parent['actor_id']);limit=SKILL.effective_rank(e.r,owner,'기술학')
  dependents=[x for x in registry.values() if x.get('kind')=='digital_avatar' and x.get('anchor_id')==anchor and x.get('status')=='connected']
  if len(dependents)>limit:raise ValueError('anchor ally capacity exceeds actual Technology rank')
 elif anchor is not None:raise ValueError('independent entry does not acquire an anchor relation')
 programs=row.get('program_ids')
 if not isinstance(programs,list) or any(not isinstance(uid,str) or not uid.strip() for uid in programs) or len(set(programs))!=len(programs):raise ValueError('distinct program instance identities required')
 for uid in programs:
  obj=_object(registry,uid)
  if obj.get('kind')!='item_instance':raise ValueError('digital programs require actual item instance identities')
 stats=deepcopy(actor.stats)
 if row['optional_trainer_stats']:stats.update(atk=3*effect_tech,spa=3*effect_tech,**{'def':3*effect_focus,'spd':3*effect_focus})
 return {'real_actor_id':actor.entity_id,'real_hp':actor.hp,'real_location':W.location_of(actor),'digital_stats':stats,'integrity_is_hp':False,'real_hp_zero_ejects':False,'physical_equipment_available':False,'program_ids':list(programs),'integrity_formula':{'hp_multiplier':[effect_tech,2],'level_multiplier':2 if actor.kind=='trainer' else 1,'constant':10},'anchor_ejection':{'ejected':True,'integrity_loss_fraction':[1,2]},'action_execution_category':[3,4,5]}

def node(e,row,index,registry,p):
 _object(registry,row.get('network_id'));_integrity(row)
 F.integer(row.get('temp_integrity',0),'temporary node Integrity',0)
 if row['network_id']==row['id']:raise ValueError('digital node cannot be its own network')
 kind=row.get('node_type')
 if kind not in ('server_core','data_snare','wall_of_thorns','active_ice'):raise ValueError('known sourced digital node required')
 for field in ('defense','evasion'):F.integer(row.get(field),'digital '+field,0)
 if row.get('controller_id') is not None:_actor(index,row['controller_id'])
 if kind=='data_snare' and (row['max_integrity']!=50 or row['defense'] or row['evasion']):raise ValueError('Data Snare has integrity 50 and no reduction/evasion')
 if kind=='wall_of_thorns' and row['max_integrity']!=25:raise ValueError('Wall of Thorns has integrity 25')
 anchor=row.get('anchor_id')
 if kind in ('server_core','data_snare') and anchor is not None:raise ValueError('core nodes do not depend on another core')
 if anchor==row['id']:raise ValueError('digital node cannot anchor itself')
 if anchor is not None:
  parent=_object(registry,anchor,'digital_node')
  if parent.get('node_type')!='server_core' or parent['network_id']!=row['network_id']:raise ValueError('node anchor must be a server core in the same network')
  if parent['status']!='connected' and row['status']=='connected':raise ValueError('disabled core cannot retain active defenses')
 if kind=='wall_of_thorns' and anchor is None:raise ValueError('Wall of Thorns must attach to an actual server core')
 if kind=='active_ice':_object(registry,row.get('bot_id'),'pokebot')
 elif row.get('bot_id') is not None:raise ValueError('only active ICE borrows a Pokebot model')
 if row.get('data_state') not in ('intact','corrupted','extracted','modified','not_applicable'):raise ValueError('explicit server data state required')
 if kind=='data_snare' and row['data_state']!='not_applicable':raise ValueError('false core cannot acquire real server data')
 return {'only_technology_targetable':kind=='wall_of_thorns','anchor_required':kind=='wall_of_thorns','integrity_is_hp':False,'core_integrity_75_is_hard_cap':False,'data_damage_and_extraction_are_distinct':True,'action_execution_category':[3,4,5]}

def forms(e,row,index,registry,p):
 human=_actor(index,row.get('human_id'),'trainer');pokemon=_actor(index,row.get('pokemon_id'),'pokemon')
 if row.get('active_id') not in (human.entity_id,pokemon.entity_id):raise ValueError('active form must be one of the linked forms')
 rank=F.integer(row.get('sharing_rank'),'power sharing rank',0,3)
 if any(x.get('kind')=='paired_forms' and x['id']!=row['id'] and set((row['human_id'],row['pokemon_id']))&set((x.get('human_id'),x.get('pokemon_id'))) for x in registry.values()):raise ValueError('one form cannot belong to two permanent beings')
 active=index[row['active_id']];other=pokemon if active is human else human
 if active.fainted and not other.fainted:raise ValueError('paired forms must default to the remaining conscious form')
 if other.on_field:raise ValueError('inactive form cannot be independently on field')
 return {'one_permanent_being':True,'hp_by_form':{human.entity_id:human.hp,pokemon.entity_id:pokemon.hp},'final_damage_applies_to_both':True,'external_gifts_available':False,'legendary_has_avatar_capabilities':True,'legendary_has_avatar_abilities':True,'legendary_has_avatar_moves':True,'avatar_has_legendary_abilities':rank>=1,'avatar_has_legendary_types':rank>=2,'avatar_has_legendary_moves':rank>=3,'growth_and_switch_execution_category':[3,5,6]}

def golem(e,row,index,registry,p):
 creator=_actor(index,row.get('creator_id'),'trainer');_object(registry,row.get('material_id'))
 F.integer(row.get('creation_level'),'golem allocation at creation',1,50)
 stats=row.get('stats')
 if not isinstance(stats,dict) or set(stats)!=set(F.STATS):raise ValueError('golem has an explicit six-stat allocation')
 for value in stats.values():F.integer(value,'golem allocation',0)
 if sum(stats.values())!=row['creation_level']:raise ValueError('golem stat points equal its creator level at creation')
 if row.get('type') not in e.r.mech('combat/type-chart')['attack_vs_defense']:raise ValueError('golem material requires an actual selected type')
 F.integer(row.get('hp'),'golem current HP');F.integer(row.get('max_hp'),'golem maximum HP',1)
 if row['hp']>row['max_hp']:raise ValueError('golem current HP exceeds its maximum')
 if type(row.get('destroyed')) is not bool:raise ValueError('explicit golem destroyed state required')
 created=_number(row.get('created_at'),'golem creation time')
 if created>e.elapsed_seconds:raise ValueError('golem cannot be created in the future')
 if (row['hp']<=0 or e.elapsed_seconds>=created+86400) and not row['destroyed']:raise ValueError('fainted or one-day golem must be destroyed')
 return {'creator_id':creator.entity_id,'size':'small','weight_class':1,'movement':{'land':4},'high_jump':0,'long_jump':0,'power':2,'capabilities':['sinker'],'struggle_type':row['type'],'oral_command_required':True,'healing_allowed':False,'expires_at':created+86400,'acquisition_execution_category':[3,6]}

VALIDATORS={'digital_avatar':avatar,'digital_node':node,'paired_forms':forms,'animated_golem':golem}

def require_actor_access(engine,actor,operation):
 """Fail before ordinary actor execution can violate special identity/state.

 Form-switch and final-damage coupling need their own native execution adapter;
 this boundary never treats the inactive body's independent HP as active HP.
 """
 import special_entities as SPECIAL
 if isinstance(actor,dict):
  if actor.get('kind')=='animated_golem':
   SPECIAL.validate_record(engine,actor)
   if operation=='heal':raise ValueError('Animate golems cannot recover HP')
   if actor.get('destroyed'):raise ValueError('destroyed Animate golem is unavailable')
   raise ValueError('Animate construct requires its object action adapter')
  return None
 uid=W.actor_id(actor)
 SPECIAL.require_prime_independent(engine,actor)
 registry=getattr(engine,'_physical_objects',{})
 for row in registry.values():
  if row.get('kind')=='paired_forms' and uid in (row.get('human_id'),row.get('pokemon_id')):
   SPECIAL.validate_record(engine,row)
   if row['active_id']!=uid:raise ValueError('inactive form cannot act or be independently targeted')
   if operation in ('take_damage','lose_hp'):
    raise ValueError('paired-form shared final damage requires its coupled HP adapter before ordinary damage')
   if operation in ('use_move','use_move_on') and (uid==row['pokemon_id'] or row['sharing_rank']):
    raise ValueError('paired-form shared capability/move availability requires its sourced action adapter')
   return row
 return None
