"""PTK ch05:5-17: campaign carrying policy, actual ownership and storage.

A roster is ownership proof, not permission to command or take another turn.
Six is the conventional, explicitly selected campaign policy, not anatomy.
All records live on actual combatant specs and survive normal GM snapshots.
"""
from copy import deepcopy
import common_checks as C
import world_entities as WORLD

SOURCE='ch05-pokemon/기본-포켓몬-규칙-및-소개'

def _source(e):
 if e.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected carrying policy source requires its own adapter')

def _identity(actor):
 return WORLD.actor_id(actor)

def _text(value,label):
 if not isinstance(value,str) or not value.strip():raise ValueError(label+' required')
 return value

def _outside(e):
 import pokemon_activities as P
 P._outside(e)

def _policy(actor):
 policy=actor.spec.get('pokemon_party_policy')
 if not policy:raise ValueError('campaign carrying and storage policy must be established')
 return policy

def _destination(value):
 if not isinstance(value,dict) or value.get('kind') not in ('center','professor'):raise ValueError('actual Center or associated professor storage required')
 return {'kind':value['kind'],'id':_text(value.get('id'),'storage identity')}

def configure(e,actor,*,mode,reason,roster,storage=None,limit=None,exceptions=None):
 import state_grants as G
 if not isinstance(roster,(list,tuple)):raise ValueError('complete explicit owned roster required')
 return G.transition(e,actor,lambda se,sa,*sr:_configure(se,sa,mode=mode,reason=reason,roster=sr,
                     storage=storage,limit=limit,exceptions=exceptions),participants=tuple(roster))


def _configure(e,actor,*,mode,reason,roster,storage=None,limit=None,exceptions=None):
 """The explicit ordered roster determines which Pokemon travel with the trainer."""
 import pokemon_activities as P
 P._trainer(actor);_outside(e);owner=_identity(actor);_text(reason,'GM campaign policy reason')
 if e.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected carrying policy source requires its own adapter')
 if mode not in ('standard','unlimited','custom'):raise ValueError('explicit campaign carrying policy required')
 if mode=='standard':
  if limit not in (None,6):raise ValueError('standard policy is six')
  limit=6
 elif mode=='unlimited':
  if limit is not None:raise ValueError('unlimited policy has no numeric cap')
 else:C.integer(limit,'GM campaign limit',0)
 destination=_destination(storage) if storage is not None else None
 if limit is not None and destination is None:raise ValueError('finite party limit requires an actual overflow destination')
 if not isinstance(roster,(list,tuple)):raise ValueError('complete explicit owned roster required')
 WORLD.actor_index(e,[actor,*roster])
 ids=[_identity(t) for t in roster]
 if len(set(ids))!=len(ids) or len({id(t) for t in roster})!=len(roster):raise ValueError('distinct actual roster Pokemon required')
 known={_identity(t) for t in WORLD.actors(e) if t.kind=='pokemon' and t.spec.get('trainer_id')==owner}
 existing=actor.spec.get('pokemon_registry',{})
 metadata={uid:deepcopy(row) for uid,row in existing.items() if row.get('sheet_pending') is True}
 old=set(existing)-set(metadata)
 if not (known|old).issubset(ids):raise ValueError('roster omits previously registered or currently known owned Pokemon')
 exceptions=exceptions or {}
 if not isinstance(exceptions,dict) or not set(exceptions).issubset(ids):raise ValueError('carry exceptions must identify actual roster Pokemon')
 for t in roster:
  P._pokemon(t);P._owner(actor,t)
 import downtime as GROWTH
 history=GROWTH.owned_species(e,actor,extra=roster)
 for uid,exc in exceptions.items():
  if not isinstance(exc,dict) or exc.get('kind') not in ('sale','gm'):raise ValueError('specific sale or GM carry exception required; eggs are separate records')
  _text(exc.get('reason'),'GM carry exception reason')
 policy={'mode':mode,'limit':limit,'storage':destination,'reason':reason,'exceptions':deepcopy(exceptions),'source':'input/ch05-pokemon.md:5-17'}
 registry=metadata;count=0
 for row in registry.values():
  if row['location']=='storage':
   if not destination:raise ValueError('registered reserve Pokemon still needs an actual storage destination')
   row['destination']=deepcopy(destination)
 for t,uid in zip(roster,ids):
  import special_entities as SPECIAL
  combined=SPECIAL.prime_member_host(e,t)
  exempt=uid in exceptions
  place='carried' if exempt or limit is None or count<limit else 'storage'
  if place=='carried' and not exempt and combined is None:count+=1
  registry[uid]={'owner_id':owner,'location':place,'destination':destination if place=='storage' else None,'exception':deepcopy(exceptions.get(uid))}
  if combined is not None:registry[uid]['combined_into']=combined
 import marsupial_state as MARSUPIAL
 MARSUPIAL.constrain_roster(e,roster,registry)
 actor.spec['pokemon_party_policy']=policy;actor.spec['pokemon_registry']=registry
 actor.spec['pokemon_registry_revision']=actor.spec.get('pokemon_registry_revision',0)+1
 for t,uid in zip(roster,ids):
  t.spec['party_location']=dict(deepcopy(registry[uid]),pokemon_id=uid)
  if registry[uid]['location']=='storage':t.on_field=False
 import special_entities as SPECIAL
 SPECIAL.sync_prime_placements(e)
 MARSUPIAL.sync(e)
 actor.spec['caught_species']=history
 import move_state as MOVES
 MOVES.project_owner_slot_features(actor,roster)
 for pokemon in roster:MOVES.validate_actor(pokemon)
 return deepcopy(registry)

def _carried(actor,exclude=None):
 exceptions=_policy(actor)['exceptions']
 return sum(uid!=exclude and row.get('location')=='carried' and uid not in exceptions and not row.get('combined_into') for uid,row in actor.spec.get('pokemon_registry',{}).items())

def preflight_capture(e,trainer,target,*,acquisition='capture'):
 """Prepare placement before ball cost; no policy never undoes actual capture."""
 _source(e)
 policy=trainer.spec.get('pokemon_party_policy');owner=trainer.spec.get('id');uid=target.spec.get('id')
 if acquisition not in ('capture','hatch'):raise ValueError('actual acquisition producer required')
 if not policy or not owner or not uid:
  plan={'location':'pending','owner_id':owner,'pokemon_id':uid,'reason':'campaign roster placement or persistent identity is not established'}
 else:
  if uid in trainer.spec.get('pokemon_registry',{}):raise ValueError('captured Pokemon already appears in this ownership registry')
  limit=policy['limit'];place='carried' if limit is None or _carried(trainer)<limit else 'storage'
  plan={'location':place,'owner_id':owner,'pokemon_id':uid,'destination':deepcopy(policy.get('storage')) if place=='storage' else None,'revision':trainer.spec.get('pokemon_registry_revision',0)}
 if target.spec.get('species'):
  import downtime as GROWTH
  plan['first_species']=GROWTH.prepare_first_owned_species(e,trainer,target.spec['species'],producer=acquisition)
 return plan

def project_current_owner(e,pokemon):
 """Project acquired continuous owner effects after actual world registration."""
 WORLD.require_actors(e,pokemon)
 import class_passive_combat as CLASS_PASSIVE
 owner=CLASS_PASSIVE._owner(e,pokemon)
 import move_state as MOVES
 MOVES.project_owner_slot_features(owner,(pokemon,))
 CLASS_PASSIVE.register_all(e,pokemon)
 import static_trainer_modifiers as STATIC_MODIFIERS
 STATIC_MODIFIERS.register_all(e,owner,(pokemon,))
 import items as ITEMS
 ITEMS.project_owned_pokemon_features(e,owner,(pokemon,))
 MOVES.validate_actor(pokemon)


def _finish_acquisition(e,trainer,target,plan):
 _source(e)
 owner=trainer.spec.get('id');uid=target.spec.get('id')
 if plan.get('owner_id')!=owner or plan.get('pokemon_id')!=uid:raise ValueError('capture placement identities changed')
 if plan.get('location')!='pending' and plan.get('revision')!=trainer.spec.get('pokemon_registry_revision',0):raise ValueError('capture roster changed after preflight')
 import state_grants as G
 def apply(staged,actor,pokemon):
  if 'first_species' in plan:
   import downtime as GROWTH
   GROWTH.commit_first_owned_species(staged,actor,plan['first_species'])
   if pokemon.spec['species']!=plan['first_species']['species']:
    pokemon.spec['species']=plan['first_species']['species']
  row={k:deepcopy(v) for k,v in plan.items() if k not in ('revision','pokemon_id','first_species')}
  pokemon.spec['party_location']=dict(row,pokemon_id=uid)
  if row['location']!='carried':pokemon.on_field=False
  if owner:pokemon.spec['trainer_id']=owner
  if owner and plan.get('source')=='hatch':
   import move_state as MOVES
   MOVES.project_owner_slot_features(actor,(pokemon,))
   MOVES.validate_actor(pokemon)
  if owner and uid:
   actor.spec.setdefault('pokemon_registry',{})[uid]=row
   actor.spec['pokemon_registry_revision']=actor.spec.get('pokemon_registry_revision',0)+1
  if owner and plan.get('source')!='hatch':project_current_owner(staged,pokemon)
  import special_entities as SPECIAL
  SPECIAL.sync_prime_placements(staged)
  import marsupial_state as MARSUPIAL
  MARSUPIAL.finish_birth_placement(staged)
  return deepcopy(row)
 # Birth already owns an outer transaction and registers the newborn after
 # this placement. Its temporarily hatched egg cannot enter a nested world
 # validation until that actual newborn has been added to the live roster.
 if plan.get('source')=='hatch':return apply(e,trainer,target)
 return G.transition(e,trainer,apply,participants=(target,))

def finish_capture(e,trainer,target,plan):
 if not target.captured:raise ValueError('only an actual successful capture registers ownership')
 return _finish_acquisition(e,trainer,target,plan)

def preflight_hatch(e,trainer,target,egg):
 """Actual hatch acquires ownership under the same explicit carrying policy."""
 if target.kind!='pokemon' or target.spec.get('trainer_id')!=trainer.entity_id:raise ValueError('hatched Pokemon must belong to this trainer')
 import pokemon_entities as EGGS
 EGGS.validate_world(e)
 registry=trainer.spec.get('pokemon_registry',{})
 if not isinstance(registry,dict):raise ValueError('owned Pokemon registry must be a mapping')
 C.integer(trainer.spec.get('pokemon_registry_revision',0),'ownership registry revision',0)
 policy=trainer.spec.get('pokemon_party_policy')
 if policy is not None:
  if not isinstance(policy,dict) or policy.get('mode') not in ('standard','custom','unlimited'):raise ValueError('actual campaign carrying policy required')
  limit=policy.get('limit')
  if policy['mode']=='unlimited':
   if limit is not None:raise ValueError('unlimited carrying policy cannot have a limit')
  else:
   C.integer(limit,'campaign carrying limit',0)
   if policy['mode']=='standard' and limit!=6:raise ValueError('standard carrying limit must be six')
   _destination(policy.get('storage'))
  if not isinstance(policy.get('exceptions'),dict):raise ValueError('carrying exceptions must be a mapping')
 entry=EGGS.egg_index(e).get(egg.get('entity_id'))
 if entry is None or entry[0] is not trainer or entry[1] is not egg or egg['hatched']:raise ValueError('actual unhatched owned egg required before hatch placement')
 plan=preflight_capture(e,trainer,target,acquisition='hatch')
 plan.update(source='hatch',egg_entity_id=egg['entity_id'])
 return plan

def finish_hatch(e,trainer,target,plan,egg):
 if target.kind!='pokemon' or target.spec.get('trainer_id')!=trainer.entity_id:raise ValueError('hatched Pokemon owner changed')
 if egg.get('hatched') is not True or egg.get('pokemon_id')!=target.entity_id or egg.get('entity_id')!=plan.get('egg_entity_id') or egg.get('owner_id')!=trainer.entity_id:raise ValueError('actual successful hatch and matching egg are required')
 return _finish_acquisition(e,trainer,target,plan)


def place(e,actor,*,target,location,swap=None):
 import pokemon_activities as P
 P._trainer(actor);_outside(e);P._pokemon(target);P._owner(actor,target)
 import special_entities as SPECIAL
 SPECIAL.require_prime_independent(e,target)
 if swap is not None:SPECIAL.require_prime_independent(e,swap)
 import marsupial_state as MARSUPIAL
 targets=[t for t in MARSUPIAL.group(e,target) if t.spec.get('trainer_id')==actor.entity_id]
 swaps=[] if swap is None else [t for t in MARSUPIAL.group(e,swap) if t.spec.get('trainer_id')==actor.entity_id]
 _source(e)
 policy=_policy(actor);uid=_identity(target);registry=actor.spec.get('pokemon_registry',{})
 if uid not in registry:raise ValueError('actual registered Pokemon required')
 if location not in ('carried','storage'):raise ValueError('explicit carried or storage location required')
 if location=='storage' and not policy.get('storage'):raise ValueError('actual storage destination required')
 if swap is not None:
  P._pokemon(swap);P._owner(actor,swap);sid=_identity(swap)
  if swap is target or location!='carried' or registry.get(sid,{}).get('location')!='carried' or not policy.get('storage'):raise ValueError('withdrawal swap needs another currently carried Pokemon and storage')
 else:sid=None
 removing={t.entity_id for t in targets+swaps}
 count=sum(pid not in removing and row.get('location')=='carried' and pid not in policy['exceptions'] and not row.get('combined_into') for pid,row in registry.items())
 needed=sum(t.entity_id not in policy['exceptions'] for t in targets)
 if location=='carried' and policy['limit'] is not None and count+needed>policy['limit']:raise ValueError('carrying limit requires an explicit deposit or permitted exception')
 updates=[(t,t.entity_id,location) for t in targets]+[(t,t.entity_id,'storage') for t in swaps]
 for t,pid,where in updates:
  row={'owner_id':_identity(actor),'location':where,'destination':deepcopy(policy.get('storage')) if where=='storage' else None,'exception':deepcopy(policy['exceptions'].get(pid))}
  registry[pid]=row;t.spec['party_location']=dict(deepcopy(row),pokemon_id=pid)
  if where=='storage':t.on_field=False
 actor.spec['pokemon_registry_revision']=actor.spec.get('pokemon_registry_revision',0)+1
 SPECIAL.sync_prime_placements(e)
 MARSUPIAL.sync(e)
 return deepcopy(registry[uid])

def registry(e,actor,**unused):
 """Digitally inspect ownership without granting combat participation."""
 _identity(actor)
 return {'trainer_id':actor.spec['id'],'pokemon':deepcopy(actor.spec.get('pokemon_registry',{})),
         'eggs':deepcopy(actor.spec.get('eggs',[])),'policy':deepcopy(actor.spec.get('pokemon_party_policy'))}

def require_participation(e,pokemon,*,acting=True):
 if pokemon.kind!='pokemon':return
 import marsupial_state as MARSUPIAL
 if acting:MARSUPIAL.require_independent(e,pokemon)
 import special_entities as SPECIAL
 SPECIAL.require_prime_independent(e,pokemon)
 import csv_item_form_contracts as CSV_FORMS
 CSV_FORMS.require_independent(e,pokemon)
 record=pokemon.spec.get('party_location')
 if record is None:
  for owner in WORLD.actors(e):
   if owner.kind=='trainer' and pokemon.spec.get('id') in owner.spec.get('pokemon_registry',{}):raise ValueError('registered Pokemon lacks its actual placement record')
  return # Legacy imports have no resolved carrying policy.
 _source(e)
 if record.get('owner_id')!=pokemon.spec.get('trainer_id') or record.get('pokemon_id')!=pokemon.spec.get('id'):raise ValueError('Pokemon placement identity does not match ownership')
 if record.get('location')!='carried':raise ValueError('stored or unresolved-placement Pokemon cannot take a combat action')
 owners=[t for t in WORLD.actor_index(e,[pokemon]).values() if t.kind=='trainer' and t.spec.get('id')==record['owner_id']]
 if len(owners)!=1:raise ValueError('one actual owner registry must be available for this managed Pokemon')
 row=owners[0].spec.get('pokemon_registry',{}).get(pokemon.spec['id'])
 if row is None or row!={k:v for k,v in record.items() if k!='pokemon_id'}:raise ValueError('Pokemon placement disagrees with actual owner registry')


def register_reserve(e,actor,*,pokemon_id,species,location,reason):
 """Register GM-established owned reserves without inventing battle statistics."""
 import pokemon_activities as P
 from builder import species_lookup
 P._trainer(actor);_outside(e);_source(e);policy=_policy(actor)
 owner=_identity(actor);_text(pokemon_id,'reserve Pokemon identity');_text(reason,'GM established ownership/transport reason')
 sp=species_lookup(e.r,species)
 import downtime as GROWTH
 history=GROWTH.owned_species(e,actor,species=(sp['id'],))
 if pokemon_id in actor.spec.get('pokemon_registry',{}) or pokemon_id in WORLD.entity_index(e,extra=(actor,)):raise ValueError('reserve identity already exists; configure the actual actor instead')
 if location not in ('storage','sale_transport'):raise ValueError('statless reserve is stored or carried for a declared sale')
 if location=='storage' and not policy.get('storage'):raise ValueError('actual reserve storage destination required')
 row={'owner_id':owner,'species':sp['id'],'location':location,'destination':deepcopy(policy.get('storage')) if location=='storage' else None,
      'exception':{'kind':'sale','reason':reason} if location=='sale_transport' else None,'ownership_reason':reason,'sheet_pending':True}
 actor.spec.setdefault('pokemon_registry',{})[pokemon_id]=row
 actor.spec['pokemon_registry_revision']=actor.spec.get('pokemon_registry_revision',0)+1
 actor.spec['caught_species']=history
 return deepcopy(row)


def transfer(e,actor,*,target,new_owner,reason,request_id):
 import state_grants as GRANTS
 return GRANTS.transition(e,actor,lambda se,sa,st,sn:_transfer(se,sa,target=st,new_owner=sn,reason=reason,request_id=request_id),
                          participants=(target,new_owner),include_rulings=True)


def _transfer(e,actor,*,target,new_owner,reason,request_id):
 """Observed out-of-encounter ownership transfer; no command/side grants.

 Only source-tracked owner effects are removable here. Untracked former-owner
 effects reject the transfer before any relation or tutor-point change.
 """
 import resolution_transaction as REQUESTS
 import pokemon_activities as P
 import state_grants as GRANTS
 import special_entities as SPECIAL
 SPECIAL.require_prime_independent(e,target)
 _text(request_id,'transfer request identity');_text(reason,'GM transfer reason')
 source_owner=_identity(actor);destination_owner=_identity(new_owner);uid=_identity(target)
 payload={'pokemon_id':uid,'old_owner_id':source_owner,'new_owner_id':destination_owner,'reason':reason}
 signature=REQUESTS.request_fingerprint(payload)
 receipts=getattr(e,'_world_relation_receipts',{})
 receipt=REQUESTS.replay_result(receipts,request_id,payload,fingerprint_field='payload_sha256')
 if receipt is not None:
  if target.spec.get('trainer_id')!=destination_owner:raise ValueError('replayed transfer no longer matches the actual owner')
  return deepcopy(receipt)
 P._trainer(actor);P._trainer(new_owner);P._pokemon(target);P._owner(actor,target);_outside(e);_source(e)
 if actor is new_owner:raise ValueError('ownership transfer requires a different trainer')
 WORLD.actor_index(e,[actor,new_owner,target])
 registry=actor.spec.get('pokemon_registry',{})
 row=registry.get(uid);placement=target.spec.get('party_location')
 if row is None or placement!={**row,'pokemon_id':uid}:raise ValueError('actual old owner registry and placement must agree')
 policy=_policy(new_owner)
 if uid in new_owner.spec.get('pokemon_registry',{}):raise ValueError('new owner already registered this Pokemon')
 for owner in WORLD.actors(e):
  if owner is not actor and owner is not new_owner and uid in owner.spec.get('pokemon_registry',{}):raise ValueError('third-party registry already claims this Pokemon')
 if target.spec.get('pending_disobedience'):raise ValueError('resolve pending command before ownership transfer')
 # No silent loss of unidentified your-Pokemon effects or AP bindings.
 former_effect_fields=('grooming','training_credit','pushed_skill')
 former_cleanup={}
 for field in former_effect_fields:
  value=target.spec.get(field)
  if isinstance(value,dict) and value.get('trainer_id')==source_owner:
   if field in ('grooming','training_credit'):
    if value.get('source')!='edge/미용사':raise ValueError('untracked former-owner grooming effect')
    if e.r._selected_rule('edge/미용사')!='edge/미용사':raise ValueError('selected grooming effect needs its own transfer cleanup')
   else:
    import researcher_features as RF
    if value.get('source')!=RF.SOURCE or value.get('feature')!=RF.SKILL_TRAINER:raise ValueError('untracked former-owner training effect')
    RF.source(e)
   former_cleanup[field]=deepcopy(value)

 # Completed jobs are historical participant evidence, not live owner effects.
 # Keep their canonical credit aliases while removing actual your-Pokemon grants.
 import activity_jobs as JOBS
 completed_credits=target.custom_conditions.get(JOBS.CREDITS,{})
 if completed_credits:JOBS.validate_world(e,WORLD.actor_index(e))
 historical_credit_ids={id(row) for row in completed_credits.values() if row['owner_id']==source_owner}
 def owner_reference(value,seen):
  if value is actor:return True
  if id(value) in historical_credit_ids:return False
  if id(value) in seen:return False
  seen.add(id(value))
  if isinstance(value,dict):
   if value.get('_state_source') in target.spec.get('state_grants',{}).get('sources',{}):return False # tracked source cleanup
   if value.get('owner_id')==source_owner or value.get('trainer_id')==source_owner:return True
   return any(owner_reference(v,seen) for v in value.values())
  if isinstance(value,(list,tuple,set)):return any(owner_reference(v,seen) for v in value)
  return False
 for field in ('buffs','custom_conditions','modifiers','registry','coats','blessings'):
  if owner_reference(getattr(target,field,None),set()):raise ValueError('untracked former-owner effect requires a source-specific cleanup adapter')
 place='carried' if policy['limit'] is None or _carried(new_owner)<policy['limit'] else 'storage'
 if place=='storage' and not policy.get('storage'):raise ValueError('actual new owner overflow storage required')
 new_row={'owner_id':destination_owner,'location':place,'destination':deepcopy(policy.get('storage')) if place=='storage' else None,'exception':None}
 old_registry=deepcopy(registry);old_registry.pop(uid)
 new_registry=deepcopy(new_owner.spec.get('pokemon_registry',{}));new_registry[uid]=new_row
 # All relationship validation precedes the sourced grant cleanup commit.
 import pokemon_entities as ENTITIES
 loyalty_plan=ENTITIES.prepare_loyalty_transfer(target,source_owner,destination_owner,reason=reason,at=e.elapsed_seconds)
 import vitamin_capacity as VITAMIN_CAPACITY
 vitamin_acquisition=VITAMIN_CAPACITY.prepare_transfer(e,target,new_owner)
 import downtime as GROWTH
 old_history=GROWTH.owned_species(e,actor)
 new_history=GROWTH.owned_species(e,new_owner,species=(target.spec['species'],) if target.spec.get('species') else ())
 target.spec['trainer_id']=destination_owner
 import move_state as MOVES
 MOVES.project_owner_slot_features(new_owner,(target,))
 # Revoke checks the final owner grants after removing every old-owner source.
 cleanup=GRANTS.preview_owner_revoke(target,source_owner)
 import grant_payments as PAYMENTS
 groups=cleanup.get('group_refunds',[])
 if cleanup['sources']:
  PAYMENTS.settle_sources(e,target,cleanup['sources'],groups,reason,
                         legacy_refund=cleanup['tutor_points_refunded']-sum(row['amount'] for row in groups))
 cleanup=dict(cleanup,reason=reason)
 for field in former_cleanup:target.spec.pop(field)
 cleanup['legacy_owner_effects_removed']=former_cleanup
 actor.spec['pokemon_registry']=old_registry
 new_owner.spec['pokemon_registry']=new_registry
 actor.spec['pokemon_registry_revision']=actor.spec.get('pokemon_registry_revision',0)+1
 new_owner.spec['pokemon_registry_revision']=new_owner.spec.get('pokemon_registry_revision',0)+1
 actor.spec['caught_species']=old_history;new_owner.spec['caught_species']=new_history
 actor.spec.get('pokemon_party_policy',{}).get('exceptions',{}).pop(uid,None)
 VITAMIN_CAPACITY.commit_transfer(e,target,new_owner,vitamin_acquisition)
 target.spec.update(loyalty_plan)
 import legendary_commands as LEGENDARY
 LEGENDARY.boundary(e,'trainer_relationship_changed')
 if 'trainer' in target.spec:target.spec['trainer']=new_owner.name
 target.spec['party_location']={**deepcopy(new_row),'pokemon_id':uid}
 target.on_field=False
 import class_passive_combat as CLASS_PASSIVE
 CLASS_PASSIVE.register_all(e,target)
 import static_trainer_modifiers as STATIC_MODIFIERS
 STATIC_MODIFIERS.register_all(e,new_owner,(target,))
 import items as ITEMS
 ITEMS.project_owned_pokemon_features(e,new_owner,(target,))
 MOVES.validate_actor(target)
 SPECIAL.sync_prime_placements(e)
 import marsupial_state as MARSUPIAL
 MARSUPIAL.finish_birth_placement(e)
 receipt={**payload,'request_id':request_id,'payload_sha256':signature,'placement':deepcopy(new_row),'cleanup':cleanup,'source':'input/ch05-pokemon.md:13,215','creation_legality_certified':False}
 e.__dict__.setdefault('_world_relation_receipts',{})[request_id]=deepcopy(receipt)
 e.gm._rec('Pokemon ownership',source_owner,destination_owner,reason,target)
 return receipt
