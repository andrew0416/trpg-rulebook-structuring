"""Bound AP connects admitted effects to their actual native ending owners.

Native bundles use the existing effect dispatcher and combat-timing records.
The legacy import adapter still supports one explicitly reconciled modifier.
Neither path infers feature ownership or an unknown source's ending policy.
Source: ch06:80-82, PTU221.
"""
from dataclasses import dataclass
import copy
import action_points as AP
import turn as TURN
import heavy_injury_adapter as HEAVY

@dataclass(frozen=True)
class Result:
    status: str
    reason: str
    instance_id: str
    released_ap: int = 0
    performed_free_action: bool = False


def _result(status, reason, instance_id):
    return Result(status, reason, instance_id)


def _ledger(actor):
    try:
        return AP.ActionPointAccount(actor).identified_bindings()
    except ValueError:
        return None


def _modifier_supported(modifier):
    # This subset lives exclusively in Combatant.modifiers; it has no immediate
    # stat mutation or on-end callback to undo. No arbitrary effect handlers.
    return (type(modifier) is dict and modifier.get('type') == 'damage_roll_mod'
            and set(modifier) <= {'type', 'value', 'move_type'}
            and type(modifier.get('value')) is int
            and ('move_type' not in modifier or type(modifier['move_type']) is str))


def inert_history(actor):
    """Recognize only the closed, nonbehavioral single-modifier release receipt."""
    records=getattr(actor,'_ap_bound_effects',{})
    if type(records) is not dict:return False
    for uid,row in records.items():
        if (type(uid) is not str or type(row) is not dict
                or set(row)!={'amount','expected_modifier','ending_method','source_ref','adapter','state','end_event'}
                or row['state']!='ended' or row['adapter']!='single_damage_roll_modifier_v1'
                or type(row['amount']) is not int or row['amount']<=0
                or not _modifier_supported(row['expected_modifier'])
                or row['ending_method']!='none_specified' or type(row['source_ref']) is not str or not row['source_ref']
                or type(row['end_event']) is not dict or set(row['end_event'])!={'id','instance_id','round','action'}):return False
        event=row['end_event']
        if (type(event['id']) is not str or not event['id'] or event['instance_id']!=uid
                or type(event['round']) is not int or event['round']<0 or event['action']!='free'
                or uid in actor.spec.get('ap_bound',{})):return False
    return True


def adopt(engine, actor, instance_id, *, modifier, ending_method, source_ref):
    """Import identity for an existing binding; does not activate/grant anything.

    Caller must have reviewed that this instance consists solely of this live
    modifier and that ending_method is explicit reviewed metadata. This function
    verifies accounting/ownership, not truth of a feature translation. Unknown
    metadata must be passed as 'unknown', never inferred as 'none_specified'.
    """
    HEAVY.ensure_clear(engine)
    if getattr(engine, '_league_runtime', None) is not None:
        return _result('pending', 'league_lifetime_import_outside_supported_scope', instance_id)
    if actor.kind != 'trainer' or type(instance_id) is not str or not instance_id:
        return _result('rejected', 'trainer_and_explicit_instance_id_required', instance_id)
    if ending_method not in ('none_specified', 'specified', 'unknown') or type(source_ref) is not str or not source_ref.strip():
        return _result('pending', 'reviewed_ending_metadata_required', instance_id)
    records = getattr(actor, '_ap_bound_effects', {})
    if instance_id in records:
        return _result('rejected', 'instance_id_already_registered', instance_id)
    bound = _ledger(actor)
    if bound is None or instance_id not in bound:
        return _result('pending', 'matching_existing_accounted_binding_required', instance_id)
    if not _modifier_supported(modifier) or sum(m is modifier for m in actor.modifiers) != 1:
        return _result('pending', 'one_live_supported_modifier_required', instance_id)
    if any(v.get('state') == 'active' and v.get('modifier') is modifier for v in records.values()):
        return _result('rejected', 'modifier_already_owned_by_binding', instance_id)
    actors = list(getattr(engine, 'everyone', []) or []) + list(getattr(engine.gm, 'everyone', []) or [])
    if any(other is not actor and any(m is modifier for m in other.modifiers) for other in actors):
        return _result('pending', 'shared_modifier_ownership_unresolved', instance_id)
    records = dict(records)
    records[instance_id] = dict(owner=actor, amount=bound[instance_id], modifier=modifier,
        expected_modifier=copy.deepcopy(modifier), ending_method=ending_method,
        source_ref=source_ref, adapter='single_damage_roll_modifier_v1', state='active', end_event=None)
    actor._ap_bound_effects = records
    return _result('adopted', 'identity_attached_without_resource_or_effect_change', instance_id)


def release(engine, actor, instance_id, *, event_id):
    record=getattr(actor,'_ap_bound_effects',{}).get(instance_id) if type(instance_id)is str else None
    if record and record.get('adapter')=='native_effect_bundle_v1' and getattr(engine,'_league_runtime',None)is None:
        import state_grants as GRANTS
        return GRANTS.transition(engine,actor,
            lambda staged,owner:_release(staged,owner,instance_id,event_id=event_id))
    return _release(engine,actor,instance_id,event_id=event_id)


def _release(engine, actor, instance_id, *, event_id):
    """End exactly one adopted instance as an own-turn Free Action, or hold it."""
    HEAVY.ensure_clear(engine)
    if getattr(engine, '_league_runtime', None) is not None:
        return _result('pending', 'league_free_action_integration_unreviewed', instance_id)
    if type(instance_id) is not str or not instance_id or type(event_id) is not str or not event_id:
        return _result('rejected', 'explicit_instance_and_event_id_required', instance_id)
    records = getattr(actor, '_ap_bound_effects', {})
    record = records.get(instance_id)
    if record is None:
        return _result('pending', 'effect_instance_identity_missing', instance_id)
    if record.get('state') != 'active':
        return _result('rejected', 'effect_already_ended', instance_id)
    if record.get('owner') is not actor or actor.kind != 'trainer':
        return _result('rejected', 'effect_instance_owner_mismatch', instance_id)
    if any(v.get('end_event', {}).get('id') == event_id for v in records.values() if v.get('end_event')):
        return _result('rejected', 'event_id_already_used', instance_id)
    if record.get('ending_method') == 'specified':
        return _result('rejected', 'specified_end_method_requires_its_own_path', instance_id)
    if record.get('ending_method') != 'none_specified':
        return _result('pending', 'absence_of_end_method_not_established', instance_id)
    bound = _ledger(actor)
    if bound is None or bound.get(instance_id) != record.get('amount'):
        return _result('pending', 'binding_accounting_mismatch', instance_id)
    bundle=record.get('adapter')=='native_effect_bundle_v1'
    if bundle:
        try:_live_bundle(engine,actor,instance_id,record)
        except ValueError as exc:return _result('pending',str(exc),instance_id)
    mod = record.get('modifier')
    if not bundle and (record.get('adapter') != 'single_damage_roll_modifier_v1' or not _modifier_supported(mod)
            or mod != record.get('expected_modifier') or sum(m is mod for m in actor.modifiers) != 1):
        return _result('pending', 'effect_runtime_identity_or_plan_mismatch', instance_id)
    # Public passive registration can add an alias after adoption. Revalidate
    # the same single-owner premise immediately before any Free action/refund.
    actors = list(getattr(engine, 'everyone', []) or []) + list(getattr(engine.gm, 'everyone', []) or [])
    if not bundle and any(other is not actor and any(m is mod for m in other.modifiers) for other in actors):
        return _result('pending', 'shared_modifier_ownership_unresolved', instance_id)
    if not engine.encounter_active:
        return _result('pending', 'own_turn_evidence_not_available_outside_encounter', instance_id)
    if (engine._active_turn_actor is not actor or engine.round_start_seconds is None
            or engine._ordinary_turn_rounds.get(actor) != engine.round_no or actor.budget is None):
        return _result('rejected', 'own_open_turn_required', instance_id)
    if actor.fainted or actor.hp <= 0 or actor.captured or not actor.on_field:
        return _result('rejected', 'actor_cannot_take_supported_free_action', instance_id)
    if actor.conditions & {'잠듦', '얼음'}:
        return _result('rejected', 'free_action_blocked_by_condition', instance_id)
    if getattr(actor, '_turn_start_decisions_pending', False) or getattr(actor, '_turn_action_limit', None):
        return _result('pending', 'free_action_permission_unresolved', instance_id)
    # All removal/accounting checks precede the ordinary action commit. There
    # is no arbitrary callback or source feature handler after this point.
    if not TURN.spend(engine, actor, 'free', 'manual Bound AP release'):
        return _result('pending', 'ordinary_free_action_not_committed', instance_id)
    if bundle:
        import combat_timing as TIMING
        amount=record['amount']
        event=dict(id=event_id,instance_id=instance_id,round=engine.round_no,action='free',kind='manual_bound_ap_release')
        for part in list(record['components']):
            TIMING.expire(engine,part['holder'],part['record'],ending='ended',event=event)
        return Result('released','effect_ended_and_its_AP_unbound',instance_id,amount,True)
    actor.modifiers[:] = [m for m in actor.modifiers if m is not mod]
    actor.ap_account.release_binding(instance_id,expected_amount=record['amount'])
    record['state'] = 'ended'
    record['end_event'] = dict(id=event_id, instance_id=instance_id, round=engine.round_no, action='free')
    # Ended receipts require no live ownership references. Keeping only passive
    # data preserves duplicate protection without introducing future observers.
    del record['owner']
    del record['modifier']
    return Result('released', 'effect_ended_and_its_AP_unbound', instance_id, record['amount'], True)


def activate_modifier(engine,actor,instance_id,*,amount,modifier,ending_method,source_ref):
    """Activate an admitted single-modifier binding atomically.

    Source selection/application admission belongs to the caller. The supported
    lifetime is the same exact-instance contract used by imported bindings.
    """
    if not _modifier_supported(modifier):raise ValueError('unsupported bound AP modifier')
    if ending_method not in ('none_specified','specified','unknown'):
        raise ValueError('explicit bound AP ending metadata required')
    import state_grants as GRANTS
    def apply(staged,owner):
        owner.ap_account.charge(amount,mode='bind',instance_id=instance_id,temporary_binding_owner='bound_ap')
        live=copy.deepcopy(modifier)
        owner.modifiers.append(live)
        result=adopt(staged,owner,instance_id,modifier=live,
                     ending_method=ending_method,source_ref=source_ref)
        if result.status!='adopted':raise ValueError('bound AP activation: '+result.reason)
        return result
    return GRANTS.transition(engine,actor,apply)


def prepare_effects(engine,actor,target,effects,*,ending_method,source_ref):
    """Resolve only already supported, reversible native lifetime payloads."""
    if ending_method not in ('none_specified','specified','unknown'):
        raise ValueError('explicit bound AP ending metadata required')
    if ending_method=='unknown':raise ValueError('bound AP ending method remains unknown')
    if type(source_ref)is not str or not source_ref.strip():raise ValueError('bound AP source required')
    if type(effects)is not list or not effects:raise ValueError('nonempty bound effect bundle required')
    if ending_method=='none_specified' and len(effects)==1 and _modifier_supported(effects[0]):
        return None  # Preserve the admitted legacy single-modifier API and receipts.
    import effect_lifetimes as LIFE
    import effect_contracts as CONTRACTS
    prepared=[]
    for effect in effects:
        if type(effect)is not dict or effect.get('type') not in LIFE.KINDS:
            raise ValueError('bound effect requires its supported native lifetime owner')
        if any(k in effect for k in (*CONTRACTS.CONDITION,'repeat','optional','limit','when','trigger','at')):
            raise ValueError('bound bundle needs unconditional reversible native effects')
        value=copy.deepcopy(effect)
        if ending_method=='none_specified':
            if LIFE.declared(value):raise ValueError('default ending cannot override a specified lifetime')
            value['until']='source_ended'
        elif not LIFE.declared(value) or value.get('until')=='source_ended':
            raise ValueError('specified ending requires an actual native lifetime declaration')
        issue=CONTRACTS.inspect(engine,actor,target,value,source_ref)
        if issue is not None:raise ValueError('bound effect: '+issue.detail)
        prepared.append(value)
    return prepared


def activate_effects(engine,actor,target,instance_id,*,amount,effects,ending_method,source_ref):
    prepared=prepare_effects(engine,actor,target,effects,ending_method=ending_method,source_ref=source_ref)
    if prepared is None:
        return activate_modifier(engine,actor,instance_id,amount=amount,modifier=effects[0],
                                 ending_method=ending_method,source_ref=source_ref)
    import state_grants as GRANTS
    import combat_timing as TIMING
    import effect_contracts as CONTRACTS
    import effect_lifetimes as LIFE
    import effects as FX
    import world_entities as W
    W.require_actors(engine,actor,target)
    if getattr(engine,'_league_runtime',None)is not None:raise ValueError('League bound effect integration remains pending')
    def apply(staged,owner,recipient):
        records=getattr(owner,'_ap_bound_effects',{})
        if instance_id in records:raise ValueError('bound effect identity already registered')
        owner.ap_account.charge(amount,mode='bind',instance_id=instance_id,temporary_binding_owner='bound_ap')
        result=FX.run_effects(staged,owner,recipient,prepared,{'hit':True},source_ref)
        if len(result.outcomes)!=len(prepared) or any(row.status!='completed' for row in result.outcomes):
            raise ValueError('bound effect bundle did not complete')
        components=[]
        for effect,outcome in zip(prepared,result.outcomes):
            for holder in CONTRACTS.recipients(owner,recipient,effect):
                live=[row for row in TIMING.records(holder) if row.get('effect_receipt')==outcome.receipt]
                if len(live)!=1:raise ValueError('bound effect needs one actual lifetime record per recipient')
                producer=staged._effect_dispatch_receipts[outcome.receipt]
                plan=LIFE.prepare(staged,owner,holder,producer['effect'],source_ref)
                if not plan or any(live[0].get(key)!=value for key,value in plan.items()):
                    raise ValueError('bound effect differs from its native installation plan')
                producer.setdefault('bound_lifetime_contracts',{})[holder.entity_id]=GRANTS._stage_transition_payload(
                    staged,staged,_native_contract(live[0]))
                live[0]['ap_binding']={'owner':owner,'instance_id':instance_id}
                components.append({'holder':holder,'record':live[0]})
        records=dict(records)
        records[instance_id]=dict(owner=owner,amount=amount,components=components,
            ending_method=ending_method,source_ref=source_ref,adapter='native_effect_bundle_v1',state='active',end_event=None)
        owner._ap_bound_effects=records
        _live_bundle(staged,owner,instance_id,records[instance_id])
        return _result('adopted','native_effects_and_exact_AP_reservation_activated',instance_id)
    return GRANTS.transition(engine,actor,apply,participants=(target,))


def _native_contract(record):
    # Only native installation bookkeeping may change while this reversible
    # payload lives. Keep its actual payload, grant and every clock in the
    # completed producer, following the existing lifetime_contracts convention.
    return {key:value for key,value in record.items() if key not in
            ('effect_receipt','effect_occurrence','owned_statuses','installing','ap_binding')}


def _live_bundle(engine,owner,instance_id,binding):
    import combat_timing as TIMING
    import effect_contracts as CONTRACTS
    import effect_lifetimes as LIFE
    import world_entities as W
    index=W.require_actors(engine,owner)
    if binding.get('owner')is not owner or binding.get('state')!='active' or owner.kind!='trainer':
        raise ValueError('actual active trainer binding required')
    if _ledger(owner) is None or _ledger(owner).get(instance_id)!=binding.get('amount'):
        raise ValueError('binding accounting mismatch')
    parts=binding.get('components')
    if type(parts)is not list or not parts or len({id(p['record']) for p in parts})!=len(parts):
        raise ValueError('distinct live bound effect components required')
    for part in parts:
        holder,record=part['holder'],part['record']
        if index.get(holder.entity_id)is not holder or holder.r is not engine.r:
            raise ValueError('actual bound effect holder required')
        link=record.get('ap_binding',{})
        if link.get('owner')is not owner or link.get('instance_id')!=instance_id:
            raise ValueError('bound effect ownership mismatch')
        if sum(row is record for row in TIMING.records(holder))!=1:
            raise ValueError('exact live bound effect record required')
        if any(other is not holder and any(row is record for row in TIMING.records(other)) for other in index.values()):
            raise ValueError('shared bound effect ownership unresolved')
        producer=getattr(engine,'_effect_dispatch_receipts',{}).get(record.get('effect_receipt'))
        if (not producer or producer.get('status')!='completed' or producer.get('actor')is not owner
                or producer.get('source_id')!=binding['source_ref'] or record.get('source')!=binding['source_ref']
                or holder not in CONTRACTS.recipients(owner,producer['target'],producer['effect'])):
            raise ValueError('bound effect needs its actual completed producer')
        CONTRACTS.validate_receipt(engine,record['effect_receipt'],record['source'],record['effect_occurrence'],
                                   owner,producer['target'],producer['effect'])
        expected=producer.get('bound_lifetime_contracts',{}).get(holder.entity_id)
        if expected is None or _native_contract(record)!=expected:
            raise ValueError('bound effect payload or native ending differs from its producer')
        owned=record.get('owned_statuses')
        if type(owned)is not set or not owned<=set(record.get('statuses',[])):
            raise ValueError('bound effect can end only its declared native statuses')
        effect=producer['effect'];field=LIFE.FIELDS.get(effect['type'])
        if field and record.get(field)!=effect['value']:raise ValueError('bound effect payload changed')
        grant=record.get('grant_source')
        if grant:
            if effect['type']=='damage_roll_mod':
                owned=[row for row in holder.modifiers if row.get('_state_source')==grant]
                expected={k:effect[k] for k in ('type','value','move_type') if k in effect}
                if len(owned)!=1 or {k:v for k,v in owned[0].items() if k!='_state_source'}!=expected:
                    raise ValueError('exact live bound modifier required')
            for other in index.values():
                for row in other.modifiers:
                    if row.get('_state_source')==grant and other is not holder:
                        raise ValueError('shared bound modifier ownership unresolved')
    return binding


def preflight_expire(engine,holder,record,*,event):
    link=record.get('ap_binding')
    if link is None:return
    owner=link.get('owner');instance_id=link.get('instance_id')
    binding=getattr(owner,'_ap_bound_effects',{}).get(instance_id)
    if not binding or binding.get('adapter')!='native_effect_bundle_v1':
        raise ValueError('native bound effect reservation required')
    _live_bundle(engine,owner,instance_id,binding)
    import temporary_ap as TEMP_AP
    funding_end=TEMP_AP.funding_ending(owner,instance_id,event)
    if binding['ending_method']=='none_specified' and event.get('kind')!='manual_bound_ap_release' and not funding_end:
        raise ValueError('default bound AP ending requires its own-turn Free Action')
    if not any(part['holder']is holder and part['record']is record for part in binding['components']):
        raise ValueError('bound effect is outside its actual reservation')


def effect_ended(engine,holder,record,*,event):
    link=record.get('ap_binding')
    if link is None:return
    owner=link['owner'];instance_id=link['instance_id']
    binding=owner._ap_bound_effects[instance_id]
    binding['components'][:]=[part for part in binding['components'] if part['record']is not record]
    record.pop('ap_binding')
    if binding['components']:return
    owner.ap_account.release_binding(instance_id,expected_amount=binding['amount'])
    binding.update(state='ended',end_event=copy.deepcopy(event))
    del binding['owner'];del binding['components']
