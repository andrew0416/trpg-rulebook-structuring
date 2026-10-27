"""Selected supplemental entity state, separate from ordinary Combatant.

These observation/query adapters validate sourced state invariants. They do not
execute creation, attacks, acquisition, surgery or ambiguous damage producers.
Pending source interpretations are returned by views, never certified as solved.
"""
from copy import deepcopy
from pathlib import Path
from math import isfinite
import hashlib
import json
import state_fields as F
import world_entities as W

import supplemental_state as SUPPLEMENTAL

KINDS={'pokebot','vehicle','vehicle_sections','augmentation_set','glyph','sentry','prime_unown','illusion'}
KINDS.update(SUPPLEMENTAL.FIELDS)
BASE={'id','kind','location','pos','provenance','source_profile','source_ids'}
FIELDS={
 'pokebot':{'size','base_stats','stats','level','hp','max_hp','injuries','types','gender','owner_id','controller_id','complexity','components','base_body','home_gravity','gravity_tolerance','destroyed','skills','complexity_grant','material'},
 'vehicle':{'stats','hp','max_hp','breaches','patched_breaches','breach_security','breach_capacity','owner_id','driver_id','passenger_ids','weapon_ids','destroyed','overland','breach_resistance_armor','native_vehicle'},
 'vehicle_sections':{'section_ids','owner_id'},
 'augmentation_set':{'actor_id','body_slots','installations','allow_added_parts','essence_enabled','capacity_grant','experimental_designs','augmentation_active','capacity_profile','essence_profile','essence_removals'},
 'glyph':{'creator_id','unown_id','creation_level','level','hp','max_hp','status','visible','channeling','flat_surface_id'},
 'prime_unown':{'creator_id','actor_id','joined','hidden_power_source_choice','hidden_power_source_policy'},
 'sentry':{'creator_id','actor_id','glyph_id','creation_level','hidden_power_id','created_at','created_in_encounter','status'},
 'illusion':{'creator_id','dimensions_cm','appearance','complexity','created_at','last_manipulated_at','anchor_location','focus_rank_limit','status','revealed_to'},
}
FIELDS.update(SUPPLEMENTAL.FIELDS)


def policy(e):
    path=Path(e.r.root)/'data/category2-special-state-policy.json'
    result=json.loads(path.read_text(encoding='utf-8'))
    for name,expected in result['source_hashes'].items():
        if hashlib.sha256((Path(e.r.root)/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('special entity source snapshot changed; review the state policy')
    return result


def _soft_augmentation_policy(e):
    path=Path(__file__).resolve().parents[1]/'data/augmentation-soft-profile-policy.json'
    value=json.loads(path.read_text(encoding='utf-8'))
    required={'schema_version','profile','clause_id','source_file','source_file_sha256','row','columns',
              'raw_cells_sha256','actor_kinds','base_capacity','external_installations_spend_capacity',
              'action_execution_category'}
    if set(value)!=required or value['schema_version']!=1 or value['profile']!='inventory_soft_capacity10_extended':
        raise ValueError('exact soft augmentation source profile required')
    if (value['clause_id']!='C2CSV/inventory:99:17' or value['row']!=99 or value['columns']!=[17,18,19,20]
            or value['actor_kinds']!=['pokemon','trainer'] or value['base_capacity']!=10
            or value['external_installations_spend_capacity'] is not True):
        raise ValueError('soft augmentation source policy changed')
    source=Path(e.r.root)/value['source_file']
    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=value['source_file_sha256']:
        raise ValueError('soft augmentation source file changed')
    return value


def _source(e,kind):
    if kind not in KINDS:raise ValueError('known special entity kind required')
    group='vehicle' if kind=='vehicle_sections' else 'augmentation' if kind=='augmentation_set' else kind
    p=policy(e)
    for source in p['sources'][group]:
        if e.r._selected_rule(source)!=source:
            raise ValueError('special entity requires its selected source: '+source)
    return p,group


def _ids(values,label):
    if not isinstance(values,list) or any(not isinstance(v,str) or not v.strip() for v in values) or len(set(values))!=len(values):
        raise ValueError(label+' must contain distinct identities')
    return values


def _actor(index,uid,label):
    W._text(uid,label)
    if uid not in index:raise ValueError(label+' must resolve to an actual actor')
    return index[uid]


def _optional_actor(index,row,key):
    if row.get(key) is not None:_actor(index,row[key],key)


def _bool(value,label):
    if type(value)is not bool:raise ValueError(label+' must be explicit boolean')


def _registry(e,proposed=None):
    result=dict(getattr(e,'_physical_objects',{}))
    if proposed is not None:result[proposed['id']]=proposed
    return result


def _object(registry,uid,kind=None):
    W._text(uid,'object reference')
    if uid not in registry:raise ValueError('object reference does not resolve: '+uid)
    result=registry[uid]
    if kind is not None and result.get('kind')!=kind:raise ValueError('object reference has the wrong entity kind')
    return result


def validate_pokebot(e,row,index,registry,p):
    size=p['pokebot_sizes'].get(row.get('size'))
    if size is None:raise ValueError('ordinary Pokebot size is small, medium or large')
    for name in ('base_stats','stats'):
        values=row.get(name)
        if not isinstance(values,dict) or set(values)!=set(F.STATS):raise ValueError('Pokebot six-stat block required')
        for val in values.values():F.integer(val,'Pokebot stat',0)
    if sum(row['base_stats'].values())!=size['base_total'] or max(row['base_stats'].values())>size['base_stat_max']:
        raise ValueError('ordinary size-specific Pokebot base allocation is invalid')
    if row.get('types')!=[] or row.get('gender') is not None:raise ValueError('Pokebot is intrinsically untyped and genderless')
    F.integer(row.get('level'),'Pokebot level',1,100)
    F.integer(row.get('hp'),'Pokebot HP');F.integer(row.get('max_hp'),'Pokebot maximum HP',1);F.integer(row.get('injuries'),'Pokebot injuries',0)
    grant=row.get('complexity_grant');limit=size['complexity_limit']
    if grant is not None:
        if not isinstance(grant,dict) or set(grant)!={'creator_id','source_id'} or grant['source_id']!='feat/실험용-ai':raise ValueError('sourced Experimental AI construction grant required')
        creator=_actor(index,grant['creator_id'],'Pokebot creator')
        import contest_features as FEATURES
        FEATURES.require(e,creator,grant['source_id']);limit+=2
    F.integer(row.get('complexity'),'Pokebot complexity',0,limit)
    if row['hp']>row['max_hp']:raise ValueError('Pokebot current HP exceeds its separate maximum')
    skills=row.get('skills')
    if not isinstance(skills,dict) or set(skills)!={'athletics','combat','acrobatics','stealth','perception','focus'}:raise ValueError('explicit special Pokebot skill ranks required')
    for value in skills.values():F.integer(value,'special Pokebot skill rank',0)
    if skills['athletics']+skills['combat']!=size['skill_pools']['athletics_combat'] or skills['acrobatics']+skills['stealth']!=size['skill_pools']['acrobatics_stealth']:raise ValueError('Pokebot base skill pools disagree with size')
    if skills['perception'] or skills['focus']:raise ValueError('baseline Pokebot Perception and Focus are unranked; module-granted skills need separate source projection')
    components=row.get('components')
    if not isinstance(components,list) or any(not isinstance(x,dict) for x in components):raise ValueError('actual component cost records required')
    _ids([c.get('instance_id') for c in components],'component identities')
    total=0
    for component in components:
        _object(registry,component['instance_id']);total+=F.integer(component.get('complexity'),'observed component complexity',0)
        W._text(component.get('source'),'component complexity source')
    if row['complexity']!=total:raise ValueError('Pokebot complexity must equal its component ledger')
    body={k:size[k] for k in ('land','power','high_jump','long_jump','weight_class')}
    if row.get('base_body')!=body:raise ValueError('Pokebot size-specific base body values differ from the selected source')
    F.integer(row.get('home_gravity'),'selected home gravity')
    if row.get('gravity_tolerance')!=row['home_gravity']+1:raise ValueError('baseline gravity tolerance is one step above home gravity')
    _bool(row.get('destroyed'),'Pokebot destroyed state')
    if row['hp']<=-2*row['max_hp'] and not row['destroyed']:raise ValueError('destruction threshold cannot be represented as an active Pokebot')
    for key in ('owner_id','controller_id'):_optional_actor(index,row,key)
    import pokebot_state as BOT
    projection=BOT.project(e,row,p,registry,index)
    import control_vehicle as CONTROL
    return {**CONTROL.body_view(row,projection),'component_projection':projection,'ordinary_complexity_limit':size['complexity_limit'],'stab':False,'magnetic_steel_only':True,'complexity_limit':limit,'base_capabilities':[{'id':x,'source_ids':p['sources']['pokebot']} for x in p['pokebot_base_capabilities']],'condition_immunity':{'all_except':p['pokebot_condition_exceptions'],'correction':'SPOL-028'},'gravity_range':[row['home_gravity']-1,row['home_gravity']+1],'unranked_skills':['perception','focus'],'ordinary_skill_fallback_allowed':False,'unresolved':[],'control_permission_checked':False,'component_acquisition_certified':False}


def validate_vehicle(e,row,index,registry,p):
    stats=row.get('stats')
    if not isinstance(stats,dict) or set(stats)!={'hp','def','spd'}:raise ValueError('vehicle has only HP, Defense and Special Defense stats')
    for val in stats.values():F.integer(val,'vehicle stat',0)
    for key in ('hp','max_hp','breaches','patched_breaches','breach_security','breach_capacity'):
        F.integer(row.get(key),key,None if key=='hp' else 1 if key in ('max_hp','breach_capacity') else 0)
    if row['hp']>row['max_hp']:raise ValueError('vehicle current HP exceeds its separate maximum')
    if row['patched_breaches']>row['breaches']:raise ValueError('patched breaches are a subset of actual breaches')
    _bool(row.get('destroyed'),'vehicle destroyed state')
    if (row['hp']<=-2*row['max_hp'] or row['breaches']>=2*row['breach_capacity']) and not row['destroyed']:
        raise ValueError('vehicle destruction threshold must produce destroyed state')
    F.integer(row.get('overland'),'vehicle own Overland',0)
    _bool(row.get('breach_resistance_armor'),'vehicle Breach Resistance Armor state')
    for key in ('owner_id','driver_id'):_optional_actor(index,row,key)
    for uid in _ids(row.get('passenger_ids'),'passenger identities'):_actor(index,uid,'passenger')
    for uid in _ids(row.get('weapon_ids'),'installed weapon identities'):_object(registry,uid)
    import vehicle_native as NATIVE
    NATIVE.validate_record(e,row)
    return vehicle_view(row)


def vehicle_view(row):
    import control_vehicle as CONTROL
    import repair_breach as BREACH
    return {**CONTROL.body_view(row),**BREACH.view(row),
        'overland':row['overland'],'driver_id':row.get('driver_id'),'breach_hp_marker_fraction':[1,4],'unresolved':[],'execution_references':['driver_speed_initiative_context_inference','repair_breach.damage','repair_breach.restoration'],
        'combat_adapter_available':False}


def validate_compartments(e,row,index,registry,p):
    sections=_ids(row.get('section_ids'),'vehicle section identities')
    if not sections:raise ValueError('a composite ship needs actual vehicle sections')
    rows=[_object(registry,uid,'vehicle') for uid in sections]
    for section in rows:validate_vehicle(e,section,index,registry,p)
    _optional_actor(index,row,'owner_id')
    capacity=sum(x['breach_capacity'] for x in rows)*2//3+4*sum(x['breach_resistance_armor'] for x in rows)
    contribution={x['id']:3*x['breach_capacity'] if x['destroyed'] else max(x['breaches'],x['breach_capacity'] if not vehicle_view(x)['operable'] else 0) for x in rows}
    breaches=sum(contribution.values())
    return {'section_ids':sections,'combined_max_hp':None,'combined_breach_capacity':capacity,'section_breach_contributions':contribution,'combined_breaches':breaches,'inoperable':breaches>=capacity,'destroyed':breaches>=2*capacity,'source_correction':'SPOL-062','unresolved':[]}


def validate_augmentation(e,row,index,registry,p):
    actor=_actor(index,row.get('actor_id'),'augmented actor')
    csv_essence=row.get('essence_profile')
    if csv_essence is not None:
        import csv_item_contract_policy as CSV
        if csv_essence!='C2CSV/inventory:100:17' or CSV.definition(e.r,clause_id=csv_essence) is None or row.get('essence_enabled') is not True:
            raise ValueError('CSV Essence requires its explicit selected source and enabled augmentation option')
    capacity_profile=row.get('capacity_profile')
    soft=None
    if capacity_profile is not None:
        soft=_soft_augmentation_policy(e)
        if capacity_profile!=soft['profile'] or actor.kind not in soft['actor_kinds']:
            raise ValueError('soft augmentation profile requires an actual Pokemon or Trainer owner')
    body=_ids(row.get('body_slots'),'observed body slots')
    if not set(body)<={'eyes','limbs','body','skin'}:raise ValueError('unknown augmentation body slot')
    _bool(row.get('allow_added_parts'),'selected added-body-part option');_bool(row.get('essence_enabled'),'selected essence option')
    installs=row.get('installations')
    if not isinstance(installs,list) or any(not isinstance(x,dict) for x in installs):raise ValueError('installed augmentation records required')
    _ids([x.get('instance_id') for x in installs],'augmentation instance identities')
    grant=row.get('capacity_grant');limit=10;multiple_slots=False;lost_grant=False
    if grant is not None:
        if not isinstance(grant,dict) or set(grant)!={'owner_id','source_id'} or grant['source_id']!='feat/효율-설치':raise ValueError('Efficient Installation source/owner grant required')
        owner=_actor(index,grant['owner_id'],'Efficient Installation source owner')
        import contest_features as FEATURES
        selected=e.r._selected_rule(grant['source_id'])==grant['source_id']
        eligible=actor is owner or actor.kind=='pokemon' and actor.spec.get('trainer_id')==owner.entity_id
        active=selected and FEATURES.owned(owner,grant['source_id']) and eligible
        if active:limit=12;multiple_slots=True
        else:
            established=getattr(e,'_physical_objects',{}).get(row['id'],{})
            if established.get('capacity_grant')!=grant:raise ValueError('a new capacity grant needs the actual currently eligible source owner')
            lost_grant=True
    slots=set();used=0;duplicates=[]
    for inst in installs:
        definition=p['augmentations'].get(inst.get('augmentation_id'))
        if definition is None:raise ValueError('unknown sourced augmentation definition')
        _object(registry,inst['instance_id'])
        external=inst.get('external',False);_bool(external,'external augmentation mounting')
        slot=definition['slot'];added=inst.get('added_body_part',False);_bool(added,'added body part')
        if slot is None and added:raise ValueError('slotless augmentation cannot create a missing body part')
        if slot is not None:
            if slot in slots:
                if not multiple_slots and not lost_grant:raise ValueError('two augmentations occupy the same body slot')
                duplicates.append(slot)
            slots.add(slot)
            if slot not in body:
                if not row['allow_added_parts'] or not added:raise ValueError('missing body part requires the explicitly selected added-part option')
            elif added:raise ValueError('existing body part cannot be claimed as an added part')
        used+=definition['capacity']*(2 if added else 1)
    if not row['essence_enabled'] and used>limit and not lost_grant:raise ValueError('ordinary augmentation capacity exceeded')
    if row['essence_enabled'] and '고스트' in (actor.types if csv_essence else actor.spec.get('types',[])) and installs:raise ValueError('Ghost type cannot retain cyberware under essence option')
    if csv_essence and used>10:raise ValueError('CSV Essence below zero has no defined source outcome')
    for other in registry.values():
        if other is not row and other.get('id')!=row['id'] and other.get('kind')=='augmentation_set' and other.get('actor_id')==row['actor_id']:
            raise ValueError('one authoritative augmentation state per actor')
        if other.get('id')!=row['id'] and other.get('kind')=='augmentation_set':
            if {x['instance_id'] for x in installs}.intersection(x['instance_id'] for x in other.get('installations',[])):
                raise ValueError('one physical augmentation cannot be installed in two actors')
    view=augmentation_view(row,used)
    import augmentation_moves as AUGMENT_MOVES
    view['move_grants']=AUGMENT_MOVES.projection(e,row,index,registry)
    view.update(capacity_limit=limit,remaining_capacity=limit-used,shock_used_capacity=max(0,used-(2 if multiple_slots else 0)),multiple_per_slot=multiple_slots,source_owner_available=not lost_grant)
    if soft is not None:
        view.update(capacity_profile=soft['profile'],base_capacity=soft['base_capacity'],
                    external_instance_ids=[inst['instance_id'] for inst in installs if inst.get('external',False)],
                    action_execution_category=soft['action_execution_category'])
    if row['essence_enabled'] and multiple_slots:view['unresolved'].append('C2SPECIAL-CONFLICT-essence-efficient-installation')
    if lost_grant and (used>limit or duplicates):view['unresolved'].append('C2SPECIAL-CONFLICT-lost-installation-owner')
    return view


def augmentation_view(row,used):
    essence=10-used if row['essence_enabled'] else None
    if row.get('essence_profile')=='C2CSV/inventory:100:17':
        return {'used_capacity':used,'remaining_capacity':10-used,'essence':essence,
            'base_injuries':3 if essence==0 else 1 if essence<=7 else 0,
            'aura_and_ghost_restricted':essence<=4,'ghost_weakness_steps':int(essence<=2),
            'effect_consumers_integrated':True,'creation_legality_certified':False,'unresolved':[]}
    return {'used_capacity':used,'remaining_capacity':10-used,'essence':essence,
        'base_hp_modifier':None if essence is not None and essence<0 else 0 if essence is None else -(1 if essence<=7 else 0)-(2 if essence==0 else 0),
        'aura_and_ghost_restricted':essence is not None and essence<=4,
        'ghost_weakness_steps':int(essence is not None and essence<=2),
        'effect_consumers_integrated':False,'creation_legality_certified':False,'unresolved':['C2SPECIAL-CONFLICT-negative-essence'] if essence is not None and essence<0 else []}


def _unown(e,actor):
    species=e.r.species.get(actor.spec.get('species'),{})
    if actor.kind!='pokemon' or species.get('name') not in ('안농','Unown'):raise ValueError('actual Unown actor identity required')


def validate_glyph(e,row,index,registry,p):
    creator=_actor(index,row.get('creator_id'),'glyph creator');unown=_actor(index,row.get('unown_id'),'glyph source Unown');_unown(e,unown)
    if creator.kind!='trainer':raise ValueError('glyph creator must be a trainer')
    for key in ('creation_level','level','max_hp'):F.integer(row.get(key),key,1)
    F.integer(row.get('hp'),'glyph current HP')
    if row['level']!=row['creation_level'] or row['max_hp']!=row['creation_level']:raise ValueError('glyph level and maximum HP equal recorded creator level')
    if row['hp']>row['max_hp']:raise ValueError('glyph current HP exceeds maximum')
    if row.get('status') not in ('active','sentry','deactivated','destroyed'):raise ValueError('unknown glyph state')
    _bool(row.get('visible'),'glyph visibility');_bool(row.get('channeling'),'glyph channeling')
    if row['channeling'] and (not row['visible'] or row['status']!='active'):raise ValueError('channeling requires an active visible glyph')
    if getattr(unown,'on_field',False):raise ValueError('glyph source Unown cannot simultaneously participate as a normal actor')
    _object(registry,row.get('flat_surface_id'))
    for other in registry.values():
        if other.get('kind')=='prime_unown' and row['unown_id'] in [other['actor_id'],*[x['member_id'] for x in other['joined']]]:raise ValueError('a Prime Unown member cannot be converted to a glyph')
        if other.get('kind')=='glyph' and other.get('id')!=row['id'] and other.get('unown_id')==row['unown_id']:
            raise ValueError('one consumed Unown cannot be used by multiple glyph identities')
    sentries=[x for x in registry.values() if x.get('kind')=='sentry' and x.get('glyph_id')==row['id'] and x.get('status')=='active']
    if row['status']=='sentry' and len(sentries)!=1:raise ValueError('sentry glyph requires exactly one active linked sentry record')
    if row['status']!='sentry' and sentries:raise ValueError('active sentry cannot reference a non-sentry glyph')
    import skill_modifiers as SKILL
    limit=SKILL.effective_rank(e.r,creator,'오컬트학')
    active=sum(x.get('kind')=='glyph' and x.get('creator_id')==row['creator_id'] and x.get('status') in ('active','sentry') for x in registry.values())
    if active>limit:raise ValueError('active glyphs exceed creator Occult rank')
    return {'active_glyph_limit':limit,'stats':None,'unresolved':[] if creator.level==row['creation_level'] else ['C2SPECIAL-CONFLICT-glyph-level-growth'],'creation_legality_certified':False}


def validate_sentry(e,row,index,registry,p):
    creator=_actor(index,row.get('creator_id'),'sentry creator');actor=_actor(index,row.get('actor_id'),'sentry actor');_unown(e,actor)
    glyph=_object(registry,row.get('glyph_id'),'glyph')
    F.integer(row.get('creation_level'),'sentry creation level',1)
    if actor.level!=row['creation_level']:raise ValueError('sentry actor level disagrees with recorded creator level')
    if glyph['creator_id']!=row['creator_id']:raise ValueError('sentry and glyph creators differ')
    W._text(row.get('hidden_power_id'),'copied Hidden Power identity')
    if actor.moves!=[row['hidden_power_id']] or row['hidden_power_id'] not in creator.moves:raise ValueError('sentry has exactly one instance of its creator Hidden Power')
    move=e.r.moves.get(row['hidden_power_id'],{})
    if move.get('name') not in ('잠재파워','Hidden Power'):raise ValueError('copied move is not a Hidden Power instance')
    if type(row.get('created_at')) not in (int,float) or not isfinite(row['created_at']) or not 0<=row['created_at']<=e.elapsed_seconds:raise ValueError('actual finite past creation time required')
    _bool(row.get('created_in_encounter'),'creation encounter context')
    if row.get('status') not in ('active','ended'):raise ValueError('unknown sentry state')
    if row['status']=='active':
        if glyph['status']!='sentry':raise ValueError('active sentry needs its glyph in sentry state')
        others=sum(x.get('kind')=='sentry' and x.get('creator_id')==row['creator_id'] and x.get('status')=='active' for x in registry.values())
        if others>1:raise ValueError('only one sentry may be active for one creator')
    elif getattr(actor,'on_field',False) or glyph['status']!='destroyed':raise ValueError('ended sentry must be off-field and its glyph destroyed')
    return {'expires_at':row['created_at']+300,'expires_at_encounter_end':True,'command_required':False,'unresolved':[],'activation_legality_certified':False}


def validate_prime_unown(e,row,index,registry,p):
    creator=_actor(index,row.get('creator_id'),'Prime Unown creator')
    actor=_actor(index,row.get('actor_id'),'Prime Unown actor');_unown(e,actor)
    # Letter Press itself is an Unown capability, not a trainer feature.  A
    # legacy trainer observer is provenance only; it never supplies the talent.
    if creator.kind!='trainer':_unown(e,creator)
    joined=row.get('joined')
    if not isinstance(joined,list) or not joined or any(not isinstance(x,dict) for x in joined):raise ValueError('Prime Unown has permanently joined members')
    definition=prime_definition(e.r,row);retain_all=definition['hidden_powers']=='all_additional'
    ids=_ids([actor.entity_id,*[x.get('member_id') for x in joined]],'Prime Unown member identities')
    bonuses={stat:0 for stat in F.STATS};moves=[]
    for number,part in enumerate(joined):
        if (set(part)-{'member_id','boosted_stat','hidden_power_id','damage_class','hidden_power_type','hidden_powers'}
                or not {'member_id','boosted_stat'}<=set(part)
                or retain_all and not {'hidden_power_id','damage_class'}<=set(part)
                or not retain_all and 'hidden_powers' not in part):raise ValueError('fixed joined-member source state required')
        member=_actor(index,part['member_id'],'joined Unown');_unown(e,member)
        if getattr(member,'on_field',False):raise ValueError('joined member cannot participate as a second actor')
        if part['boosted_stat'] not in F.STATS and not (number>=4 and part['boosted_stat'] is None):raise ValueError('first four joined Unown bonuses need a chosen base stat')
        if number<4:bonuses[part['boosted_stat']]+=5
        for power in _prime_powers(e.r,part,member,retain_all=retain_all):
            moves.append({'member_id':member.entity_id,**power})
    for other in registry.values():
        if other.get('id')!=row['id'] and other.get('kind')=='prime_unown':
            if set(ids).intersection([other['actor_id'],*[x['member_id'] for x in other['joined']]]):raise ValueError('one Unown identity cannot belong to two Prime Unown')
        if other.get('kind')=='glyph' and other.get('unown_id') in ids:raise ValueError('glyph-consumed Unown cannot join Prime Unown')
    return {'member_ids':ids,'counts_as_pokemon':1,'separable':False,'base_stat_bonuses':bonuses,'hidden_power_instances':moves,'underdog_available':False,'acquisition_execution_certified':False,
        'unresolved':['observe existing permanent Hidden Power type: '+x['member_id'] for x in moves if x['type'] is None]}


PRIME_SOURCE='capability/활자'
PRIME_KEY='prime_unown_state'
PRIME_MEMBER='prime_unown_member'
PRIME_PREFIX='prime-unown:'
PRIME_KR_SOURCE={'file':'input/ch10-index-reference.md','sha256':'c3a1d783b4f649f0f6e25a9443a90ca8079a6e036c42c6f8797e100127157abe'}
PRIME_EN_SOURCE={'file':'source-audit/unown-letter-press-indices-1.05.txt','sha256':'6f91819e1478361a6e6fd56b4026babe64b800e66b0b4efa2e8d31d7d16ac76c'}


def _prime_definitions():
    common={'bonus_additions':4,'bonus_value':5,'join_limit':None,'permanent_class_choice':True,
            'inseparable':True,'counts_as_pokemon':1,'loses_underdog':True}
    return {'korean_all_additional':dict(common,hidden_powers='all_additional',source=PRIME_KR_SOURCE),
            'english_optional_normal_limit':dict(common,hidden_powers='optional_normal_limit',source=PRIME_EN_SOURCE)}


def _prime_document():
    return {'schema':1,'id':'native/unown-letter-press','variants':[{
        'rule_id':PRIME_SOURCE,'source':PRIME_KR_SOURCE,
        'values':{'variant':{'$input':'source_text'},'definitions':_prime_definitions()},
        'inputs':{'source_text':{'type':'string','authority':'gm','decision_kind':'source_conflict',
            'choices':list(_prime_definitions()),
            'question':'Letter Press: Korean retains all member Hidden Powers in addition to the original list; English permits a chosen subset within the normal Move List limit. Which complete definition applies?'}}}]}


def prime_source_choices(rules):
    return __import__('source_policy').resolve(rules,_prime_document())


def prime_definition(rules,record):
    """Historical/default records keep Korean; explicit choices retain their complete definition."""
    from source_context import verified_source
    verified_source(rules,PRIME_KR_SOURCE,label='Letter Press')
    verified_source(rules,PRIME_EN_SOURCE,source_root='source-audit',label='English Letter Press')
    choice=record.get('hidden_power_source_choice');resolved=record.get('hidden_power_source_policy')
    if choice is None and resolved is None:return deepcopy(_prime_definitions()['korean_all_additional'])
    import root_resolution as ROOT,source_selection as SELECTION
    if (type(choice)is not dict or set(choice)!={'value','reason','scope'} or type(resolved)is not dict):
        raise ValueError('retained complete Letter Press source choice required')
    W._text(choice['reason'],'Letter Press source reason')
    document=_prime_document();values=SELECTION.policy_values(resolved['source_policy_binding'],document['variants'])
    selected=choice['value']
    if (selected not in values['definitions'] or resolved['status']!='PolicyValuesReady'
            or resolved['values']!={'variant':selected,'definitions':values['definitions']}
            or resolved['selected_id']!=PRIME_SOURCE or resolved['definition_hash']!=ROOT.fingerprint(document)
            or resolved['decision_scope']!=choice['scope']
            or resolved['inputs_hash']!=ROOT.fingerprint({'context':{},'decisions':{'source_text':choice},'state':{}})
            or resolved['decision_evidence']!=[{'input':'source_text','reason':choice['reason'],
                'decision_kind':'source_conflict','scope':choice['scope']}]):
        raise ValueError('retained Letter Press source decision changed')
    return deepcopy(values['definitions'][selected])


def _prime_snapshot(row):
    result={'id':row['id'],'actor_id':row['actor_id'],'source':PRIME_SOURCE,'joined':deepcopy(row['joined'])}
    for key in ('hidden_power_source_choice','hidden_power_source_policy'):
        if key in row:result[key]=deepcopy(row[key])
    return result


def _hidden_power(rules,mid):
    move=rules.moves.get(mid,{})
    return move.get('eng','').startswith('Hidden Power') or move.get('name','').startswith('잠재파워')


def _prime_powers(rules,part,member=None,*,retain_all=True):
    powers=part.get('hidden_powers')
    if powers is None:
        mid=part['hidden_power_id'];definition=rules.moves.get(mid,{})
        kind=part.get('hidden_power_type')
        if kind is None and mid!='move/잠재파워':kind=definition.get('type')
        if kind is None and member is not None:kind=member.spec.get('hidden_power_type')
        powers=[{'move_id':mid,'type':kind,'damage_class':part['damage_class']}]
    if not isinstance(powers,list) or retain_all and not powers:raise ValueError('explicit prior Hidden Power instances required')
    ids=[];result=[]
    for power in powers:
        if (type(power)is not dict or set(power)!={'move_id','type','damage_class'} or
                not _hidden_power(rules,power['move_id']) or power['damage_class'] not in ('physical','special')):
            raise ValueError('actual Hidden Power identity and permanent class required')
        if power['type'] is not None and power['type'] not in {m.get('type') for m in rules.moves.values()}:raise ValueError('observed existing Hidden Power type required')
        if power['move_id']!='move/잠재파워' and power['type']!=rules.move(power['move_id'])['type']:raise ValueError('typed Hidden Power source type cannot be changed')
        if member is not None and power['move_id'] not in member.moves:raise ValueError('every copied Hidden Power must be held by its actual member')
        if (member is not None and power['move_id']=='move/잠재파워' and member.spec.get('hidden_power_type') is not None
                and power['type']!=member.spec['hidden_power_type']):raise ValueError('observed Hidden Power type disagrees with the original member')
        if power['move_id'] in ids:raise ValueError('distinct prior Hidden Power identities required')
        ids.append(power['move_id']);result.append(deepcopy(power))
    if 'hidden_power_id' in part:
        if part['hidden_power_id'] not in ids:raise ValueError('primary Hidden Power must be included')
        if next(x for x in result if x['move_id']==part['hidden_power_id'])['damage_class']!=part.get('damage_class'):raise ValueError('primary permanent Hidden Power class disagrees')
    elif 'damage_class' in part or 'hidden_power_type' in part:raise ValueError('primary Hidden Power identity required with primary choices')
    if retain_all and member is not None and set(ids)!={mid for mid in member.moves if _hidden_power(rules,mid)}:raise ValueError('all prior member Hidden Powers require permanent choices')
    return result


def prime_instance_id(record,part,power):
    from base64 import urlsafe_b64encode
    payload=[record['id'],record['actor_id'],part['member_id'],power['move_id'],power['type'],power['damage_class']]
    return PRIME_PREFIX+urlsafe_b64encode(json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()).decode().rstrip('=')


def prime_instance(rules,mid):
    """A narrow move identity adapter; never adds a global move definition."""
    if not isinstance(mid,str) or not mid.startswith(PRIME_PREFIX):return None
    from base64 import urlsafe_b64decode
    try:values=json.loads(urlsafe_b64decode(mid[len(PRIME_PREFIX):]+'='*((-len(mid[len(PRIME_PREFIX):]))%4)))
    except Exception as exc:raise ValueError('invalid Prime Hidden Power identity') from exc
    if (not isinstance(values,list) or len(values)!=6 or any(not isinstance(v,str) or not v for v in values)
            or values[5] not in ('physical','special') or not _hidden_power(rules,values[3])
            or values[4] not in {m.get('type') for m in rules.moves.values()}):raise ValueError('exact Prime Hidden Power source identity required')
    row=dict(zip(('record_id','host_id','member_id','move_id','type','damage_class'),values))
    if prime_instance_id({'id':values[0],'actor_id':values[1]},{'member_id':values[2]}, {'move_id':values[3],'type':values[4],'damage_class':values[5]})!=mid:raise ValueError('noncanonical Prime Hidden Power identity')
    if rules._selected_rule(PRIME_SOURCE)!=PRIME_SOURCE:raise ValueError('selected Letter Press source required')
    rules._selected_rule(row['move_id'])
    return row


def prime_moves(rules,snapshot):
    result=[]
    retain_all=prime_definition(rules,snapshot)['hidden_powers']=='all_additional'
    for part in snapshot['joined']:
        for power in _prime_powers(rules,part,retain_all=retain_all):
            if power['type'] is not None:result.append(prime_instance_id(snapshot,part,power))
    return result


def _prime_append_only(old,new):
    if old.get('actor_id')!=new.get('actor_id') or len(new.get('joined',[]))<len(old['joined']):return False
    if any(old.get(key)!=new.get(key) for key in ('hidden_power_source_choice','hidden_power_source_policy')):return False
    for previous,proposed in zip(old['joined'],new['joined']):
        expected=deepcopy(previous)
        # Filling an unobserved pre-existing type is evidence enrichment.  It
        # cannot change a known type, member, stat or permanent damage class.
        if previous.get('hidden_power_type') is None and proposed.get('hidden_power_type') is not None:
            expected['hidden_power_type']=proposed['hidden_power_type']
        oldpowers=expected.get('hidden_powers');newpowers=proposed.get('hidden_powers')
        if oldpowers is not None and newpowers is not None and len(oldpowers)==len(newpowers):
            for prior,later in zip(oldpowers,newpowers):
                if prior.get('type') is None and later.get('type') is not None:prior['type']=later['type']
        if expected!=proposed:return False
    return True


def validate_prime_spec(rules,spec,*,moves=(),complete=False):
    snapshot=spec.get(PRIME_KEY)
    expected=[]
    if snapshot is not None:
        if (type(snapshot)is not dict or set(snapshot)-{'hidden_power_source_choice','hidden_power_source_policy'}!={'id','actor_id','source','joined'} or snapshot['actor_id']!=spec.get('id')
                or snapshot['source']!=PRIME_SOURCE or not isinstance(snapshot['joined'],list) or not snapshot['joined']):raise ValueError('actual Prime source snapshot required')
        if rules._selected_rule(PRIME_SOURCE)!=PRIME_SOURCE:raise ValueError('selected Letter Press source required')
        expected=prime_moves(rules,snapshot)
    import move_state as M
    present=M.effective_list(spec,'moves',moves)
    for mid in set([*present,*moves]):
        if prime_instance(rules,mid) is not None and mid not in expected:raise ValueError('Prime Hidden Power is not owned by this actual combined actor')
    sources=spec.get('state_grants',{}).get('sources',{})
    retain_all=snapshot is not None and prime_definition(rules,snapshot)['hidden_powers']=='all_additional'
    for mid in expected if complete and retain_all else [v for v in expected if v in present]:
        sid=PRIME_PREFIX+mid
        row=sources.get(sid)
        if (row is None or row.get('rule_id')!=PRIME_SOURCE or row.get('owner_id')!=spec['id'] or
                row.get('lifetime')!='permanent' or row.get('move_mode')!='learned' or row.get('grants',{}).get('moves')!=[mid]):
            raise ValueError('permanent Prime Hidden Power source grant missing')
    return expected


def prime_base_sources(rules,spec):
    snapshot=spec.get(PRIME_KEY)
    if snapshot is None:return []
    if snapshot.get('actor_id')!=spec.get('id') or snapshot.get('source')!=PRIME_SOURCE or rules._selected_rule(PRIME_SOURCE)!=PRIME_SOURCE:raise ValueError('actual Prime base source required')
    prime_definition(rules,snapshot)
    bonuses=dict.fromkeys(F.STATS,0)
    for part in snapshot['joined'][:4]:bonuses[part['boosted_stat']]+=5
    return [{'source':PRIME_PREFIX+snapshot['id'],'values':bonuses}]


def prime_member_host(e,actor):
    uid=actor if isinstance(actor,str) else W.actor_id(actor)
    for row in getattr(e,'_physical_objects',{}).values():
        if row.get('kind')=='prime_unown' and any(part['member_id']==uid for part in row['joined']):return row['actor_id']
    return None


def require_prime_independent(e,actor):
    if prime_member_host(e,actor) is not None:raise ValueError('joined Prime Unown member cannot act, be targeted or be placed independently')


def sync_prime_placements(e):
    """The existing roster keeps each identity; placement follows its one body."""
    index=W.actor_index(e)
    for row in getattr(e,'_physical_objects',{}).values():
        if row.get('kind')!='prime_unown':continue
        host=index[row['actor_id']];placement=host.spec.get('party_location')
        for part in row['joined']:
            member=index[part['member_id']]
            for owner in index.values():
                registered=owner.spec.get('pokemon_registry',{}).get(member.entity_id)
                if registered is None:continue
                registered['combined_into']=host.entity_id
                if placement is not None:
                    registered['location']=placement['location'];registered['destination']=deepcopy(placement.get('destination'))
                member.spec['party_location']=dict(deepcopy(registered),pokemon_id=member.entity_id)


def validate_prime_world(e,index=None):
    index=W.actor_index(e) if index is None else index
    expected={};members={}
    for row in getattr(e,'_physical_objects',{}).values():
        if row.get('kind')!='prime_unown':continue
        expected[row['actor_id']]=_prime_snapshot(row)
        for part in row['joined']:members[part['member_id']]={'record_id':row['id'],'host_id':row['actor_id']}
    for uid,actor in index.items():
        if actor.spec.get(PRIME_KEY)!=expected.get(uid) or actor.spec.get(PRIME_MEMBER)!=members.get(uid):raise ValueError('Prime source projection disagrees with actual permanent record')
        validate_prime_spec(e.r,actor.spec,moves=actor.moves,complete=True)
        if uid in members and actor.on_field:raise ValueError('joined member cannot participate as another Pokemon')
        for pid,row in actor.spec.get('pokemon_registry',{}).items():
            if row.get('combined_into')!=(members.get(pid) or {}).get('host_id'):raise ValueError('Prime party count projection differs from actual combined member')
            if pid in members:
                placement=index[members[pid]['host_id']].spec.get('party_location')
                if placement is not None and any(row.get(k)!=placement.get(k) for k in ('location','destination')):raise ValueError('absorbed Prime member placement must follow its actual host')
    return True


def _sync_prime(e,previous,reason):
    import state_grants as G,growth_stats as GROWTH
    index=W.actor_index(e)
    for row in getattr(e,'_physical_objects',{}).values():
        if row.get('kind')!='prime_unown':continue
        host=index[row['actor_id']]
        snapshot=_prime_snapshot(row)
        # Freeze explicit already-existing types into the permanent record once.
        for part in snapshot['joined']:
            if part.get('hidden_power_type') is None and 'hidden_powers' not in part and part.get('hidden_power_id')=='move/잠재파워':
                kind=index[part['member_id']].spec.get('hidden_power_type')
                if kind is not None:raise ValueError('record the existing permanent Hidden Power type in joined state explicitly')
        old=host.spec.get(PRIME_KEY)
        if old==snapshot:continue
        current=previous[host.entity_id]
        # Let the already-owned prerequisite-loss/refund path settle genuine
        # Underdog investments before adding the new base contribution.
        import underdog_edges as UNDERDOG
        host._prime_unown_loss_pending=True
        try:UNDERDOG.reconcile(e,host,reason='Letter Press permanently removes Underdog')
        finally:del host._prime_unown_loss_pending
        current=GROWTH.source_permanent(host)
        host.spec[PRIME_KEY]=snapshot
        if old is None or [(x['member_id'],x['boosted_stat']) for x in old['joined'][:4]]!=[(x['member_id'],x['boosted_stat']) for x in snapshot['joined'][:4]]:
            GROWTH.migrate_sources(host,current,source=PRIME_SOURCE,reason=reason,kind='prime_unown_join')
        prior=set(prime_moves(e.r,old)) if old is not None else set()
        retain_all=prime_definition(e.r,snapshot)['hidden_powers']=='all_additional'
        for mid in prime_moves(e.r,snapshot):
            sid=PRIME_PREFIX+mid
            if sid in host.spec.get('state_grants',{}).get('sources',{}):continue
            if not retain_all and mid in prior:continue
            # Korean additional instances are exempt; English instances pass
            # the ordinary learned Move List capacity before any commit.
            G._source(host,sid,'prime_unown',owner_id=host.entity_id,lifetime='permanent',rule_id=PRIME_SOURCE,tutor_points=0,move_mode='learned')
            G.grant_moves(host,[mid],sid,'prime_unown',owner_id=host.entity_id,lifetime='permanent',rule_id=PRIME_SOURCE)
        for part in row['joined']:
            member=index[part['member_id']]
            member.spec[PRIME_MEMBER]={'record_id':row['id'],'host_id':host.entity_id}
    sync_prime_placements(e)
    validate_prime_world(e,index)


def validate_record(e,row,registry=None):
    if not isinstance(row,dict) or row.get('kind') not in KINDS:raise ValueError('known special entity kind required')
    if set(row)-BASE-FIELDS[row['kind']]:raise ValueError('field does not belong to this special entity schema')
    W._text(row.get('id'),'special entity identity');F.location(row.get('location'))
    if 'pos' in row:
        actual=F.location(row['location']);alias=F.location({'kind':'grid','cell':row['pos']})
        if actual['kind']!='grid' or actual['cell']!=alias['cell']:raise ValueError('special body position alias disagrees with actual location')
    p,group=_source(e,row['kind']);index=W.actor_index(e)
    entities=W.entity_index(e)
    if (row['id'] in entities and row['id'] not in getattr(e,'_physical_objects',{})) or any(row['id'] in actor.spec.get('pokemon_registry',{}) for actor in index.values()):raise ValueError('special object identity collides with actor or reserve identity')
    if row.get('source_ids') is not None and row['source_ids']!=p['sources'][group]:raise ValueError('special entity source provenance changed')
    registry=_registry(e,row) if registry is None else registry
    import illusion_state as ILLUSION
    fn={**SUPPLEMENTAL.VALIDATORS,'pokebot':validate_pokebot,'vehicle':validate_vehicle,'vehicle_sections':validate_compartments,'augmentation_set':validate_augmentation,'glyph':validate_glyph,'sentry':validate_sentry,'prime_unown':validate_prime_unown,'illusion':ILLUSION.validate_record}[row['kind']]
    return fn(e,row,index,registry,p)


def observe_batch(e,records,*,reason):
    # Only augmentation graph changes need the coupled actor-grant commit.
    if isinstance(records,(list,tuple)) and any(isinstance(row,dict) and row.get('kind') in ('augmentation_set','prime_unown') for row in records):
        import state_grants as GRANTS,augmentation_moves as AUGMENT_MOVES
        actors=list(W.actor_index(e).values())
        if not actors:raise ValueError('actual augmented actor required')
        def apply(se,primary,*others):
            import growth_stats as GROWTH
            previous={uid:GROWTH.source_permanent(actor) for uid,actor in W.actor_index(se).items()
                if any(row.get('kind')=='prime_unown' and row.get('actor_id')==uid for row in records)}
            result=_observe_batch(se,records,reason=reason)
            if previous:_sync_prime(se,previous,reason)
            AUGMENT_MOVES.sync(se)
            import csv_item_capability_contracts as CSV_CAP
            for actor in W.actor_index(se).values():CSV_CAP.sync_essence(se,actor)
            return result
        return GRANTS.transition(e,actors[0],apply,participants=tuple(actors[1:]))
    return _observe_batch(e,records,reason=reason)


def _observe_batch(e,records,*,reason):
    """Validate linked observations together, then preserve all instance aliases."""
    W._text(reason,'GM observed special state reason')
    if not isinstance(records,(list,tuple)) or not records:raise ValueError('explicit observed special-state records required')
    if any(not isinstance(row,dict) for row in records):raise ValueError('special-state observations must be records')
    _ids([row.get('id') for row in records],'observed entity identities')
    registry=_registry(e);proposed=[]
    for record in records:
        row=deepcopy(record);p,group=_source(e,row.get('kind'))
        row.update(source_profile=e.r.ruleset.name,source_ids=p['sources'][group],provenance={'source':'gm/observation','reason':reason})
        old=registry.get(row['id'])
        if row.get('kind')=='prime_unown' and row.get('hidden_power_source_choice') is not None:
            choice=row['hidden_power_source_choice']
            if old is not None and old.get('hidden_power_source_choice')==choice:
                resolved=old.get('hidden_power_source_policy')
            else:
                resolved=__import__('source_policy').resolve(e.r,_prime_document(),decisions={'source_text':choice})
            if resolved is None or resolved['status']!='PolicyValuesReady':raise ValueError('complete Letter Press source decision required')
            if 'hidden_power_source_policy' in row and row['hidden_power_source_policy']!=resolved:raise ValueError('Letter Press source receipt changed')
            row['hidden_power_source_policy']=deepcopy(resolved)
        if old is not None:
            if old.get('kind')!=row['kind']:raise ValueError('one identity cannot change special entity schema')
            if old.get('destroyed') and not row.get('destroyed'):raise ValueError('observation cannot silently revive a destroyed special entity')
            immutable={'glyph':('creator_id','unown_id','creation_level','flat_surface_id'),'sentry':('creator_id','actor_id','glyph_id','creation_level','hidden_power_id','created_at','created_in_encounter'),'illusion':('creator_id','dimensions_cm','created_at')}
            if any(old.get(k)!=row.get(k) for k in immutable.get(old.get('kind'),())):raise ValueError('created source identity, choices and lifetime cannot be rewritten')
            if old.get('kind')=='glyph' and old.get('status') in ('destroyed','deactivated') and row.get('status')!=old['status']:raise ValueError('a consumed glyph identity cannot be reactivated')
            if old.get('kind')=='illusion' and old.get('status')=='dismissed' and row.get('status')!='dismissed':raise ValueError('a dismissed illusion identity cannot be restored')
            if old.get('kind')=='paired_forms' and any(old.get(k)!=row.get(k) for k in ('human_id','pokemon_id')):raise ValueError('permanent form membership cannot be rewritten')
            if old.get('kind')=='animated_golem' and any(old.get(k)!=row.get(k) for k in ('creator_id','creation_level','created_at','material_id','type','stats','max_hp')):raise ValueError('golem creation choices cannot be rewritten')
            if old.get('kind')=='animated_golem' and row.get('hp',0)>old.get('hp',0):raise ValueError('animated golem cannot be healed')
            if old.get('kind')=='prime_unown' and not _prime_append_only(old,row):raise ValueError('Prime Unown cannot split or rewrite permanent joined-member choices')
        proposed.append(row);registry[row['id']]=row
    derived={}
    for row in registry.values():
        if row.get('kind') in KINDS:derived[row['id']]=validate_record(e,row,registry)
    # Commit starts only after every linked current/proposed special record passes.
    import network_connection as NETWORK
    NETWORK.validate_world(e,W.actor_index(e),registry=registry)
    import control_remote as REMOTE
    REMOTE.validate_world(e,W.actor_index(e))
    actual=e.__dict__.setdefault('_physical_objects',{})
    results=[]
    for row in proposed:
        before=deepcopy(actual.get(row['id']));target=actual.setdefault(row['id'],{})
        target.clear();target.update(row)
        if target.get('kind')=='glyph' and target.get('status') in ('destroyed','deactivated'):
            __import__('rune_master').expire_glyph_bindings(e,target['id'])
        results.append({'entity':deepcopy(target),'state_view':derived[row['id']],'creation_legality_certified':False})
        e.gm._rec('special entity '+row['id'],before,target,reason)
    import control_remote as REMOTE
    REMOTE.boundary(e,'special_state_changed')
    return results


def observe(e,record,*,reason):
    """Record existing state; action/acquisition legality is not certified."""
    return observe_batch(e,[record],reason=reason)[0]


def view(e,entity_id):
    row=_object(getattr(e,'_physical_objects',{}),entity_id)
    return {'entity':deepcopy(row),'state_view':validate_record(e,row)}


def preflight_sentries(e):
    """Read-only boundary validation; return existing references for commit.

    A boundary caller retains this plan before changing the clock or encounter.
    Passing it to expire_sentries avoids any post-boundary fallible validation.
    """
    registry=getattr(e,'_physical_objects',{});index=W.actor_index(e);planned=[]
    for row in registry.values():
        if row.get('kind')=='animated_golem' and not row.get('destroyed'):
            validate_record(e,row,registry)
            planned.append((row,None,None,row['created_at']+86400))
            continue
        if row.get('kind')!='sentry' or row.get('status')!='active':continue
        validate_record(e,row,registry)
        glyph=registry[row['glyph_id']]
        validate_record(e,glyph,registry)
        planned.append((row,index[row['actor_id']],glyph,row['created_at']+300))
    return tuple(planned)


def expire_sentries(e,*,encounter_end=False,prepared=None):
    """Commit preflighted expiry from known clock/encounter boundary facts."""
    _bool(encounter_end,'encounter end observation')
    planned=preflight_sentries(e) if prepared is None else prepared
    expired=[]
    for row,actor,glyph,expires_at in planned:
        if row.get('kind')=='animated_golem':
            if not row['destroyed'] and e.elapsed_seconds>=expires_at:
                row['destroyed']=True;expired.append(row['id'])
            continue
        if row['status']=='active' and (e.elapsed_seconds>=expires_at or encounter_end):
            row['status']='ended';actor.on_field=False;glyph['status']='destroyed';glyph['channeling']=False
            __import__('rune_master').expire_glyph_bindings(e,glyph['id'])
            expired.append(row['id'])
    return expired
