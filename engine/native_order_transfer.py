"""Pass existing native Order instances without issuing, paying or refreshing them."""
from copy import deepcopy
import common_checks as C
import combat_timing as TIME
import state_grants as G
import world_entities as W

KEY='native_order_handoff'
SOURCES=('move/배턴터치','feat/태그-인')


def origin_id(record,holder):
    history=record.get(KEY)
    if history is None:return holder.entity_id
    if type(history)is not dict or set(history)-{'instance_id','origin_id','holder_id','events','turn_anchor'} or not {'instance_id','origin_id','holder_id','events'}<=set(history) or not history['events']:
        raise ValueError('actual Order handoff history required')
    previous=history['origin_id'];at=0
    for event in history['events']:
        if (set(event)!={'source','from_id','to_id','at','from_turn','to_turn','recall_id','trainer_id','clock'}
                or event['source'] not in SOURCES or event['from_id']!=previous or event['to_id']==previous):
            raise ValueError('Order handoff must continue the original instance ownership')
        at=C.integer(event['at'],'Order handoff time',at)
        C.integer(event['from_turn'],'original holder turn',0);C.integer(event['to_turn'],'new holder turn',0)
        previous=event['to_id']
    if previous!=history['holder_id'] or previous!=holder.entity_id:
        raise ValueError('Order handoff does not identify its actual holder')
    _turn_anchor(record)
    return history['origin_id']


def origin(engine,holder,record):
    result=W.actor_index(engine).get(origin_id(record,holder))
    if result is None:raise ValueError('original Order recipient is missing')
    return result


def observe(engine,outgoing,incoming,record,source,recall_id,*,clock=None):
    first=origin_id(record,outgoing)
    row=record.setdefault(KEY,{'instance_id':instance_id(record,outgoing),
        'origin_id':first,'holder_id':outgoing.entity_id,'events':[]})
    row['events'].append({'source':source,'from_id':outgoing.entity_id,'to_id':incoming.entity_id,
        'at':engine.elapsed_seconds,'from_turn':outgoing.custom_conditions.get('combat_turn_serial',0),
        'to_turn':incoming.custom_conditions.get('combat_turn_serial',0),'recall_id':recall_id,
        'trainer_id':outgoing.spec['trainer_id'],'clock':deepcopy(clock or {'phase':'independent','shift':0})})
    if clock and clock.get('anchor') is not None:row['turn_anchor']=deepcopy(clock['anchor'])
    row['holder_id']=incoming.entity_id


def instance_id(record,holder):
    if KEY in record:return record[KEY]['instance_id']
    for key in ('id','instance','effect_occurrence','duelist_use',G.TAG):
        if record.get(key):return record[key]
    for key,fields in (('wilderness_guide',('owner_id','sequence')),
                       ('conquerors_march',('issuer_id','order_id')),
                       ('chronicler_profiling',('owner_id','issued_round','issued_serial')),
                       ('fashionista_dress',('owner_id','round','count'))):
        if key in record:
            return ':'.join([key,holder.entity_id,*[str(record[key][field]) for field in fields]])
    if 'go_fight_win_use' in record:return record['go_fight_win_use']+':evasion:'+holder.entity_id
    if record.get('optional_clause_id')=='ERRATA-056':
        return ':'.join(['ERRATA-056',record['optional_owner_id'],holder.entity_id,
                         str(record['optional_created_round']),str(record['optional_created_count'])])
    raise ValueError('Order handoff needs its actual source-owned instance identity')


def plan_ids(engine,outgoing,incoming,*,scope='orders',identifiers=None):
    preflight(engine,outgoing,incoming,scope=scope,identifiers=identifiers)
    return live_ids(outgoing,scope=scope,engine=engine,identifiers=identifiers)


def _general(engine,actor,scope,identifiers=None):
    import commander_orders as COMMANDER
    rows=COMMANDER.live(engine,actor) if engine is not None else [row for row in COMMANDER.records(actor) if not row['ended']]
    return [row for row in rows if (scope=='orders' or row['feature']==COMMANDER.BRACE)
            and (identifiers is None or row['id'] in identifiers)]


def live_ids(outgoing,*,scope='orders',engine=None,identifiers=None):
    import training_features as TRAINING,cheerleader as CHEER
    import class_passive_combat as CLASS,combat_precision_features as PINPOINT
    state=CLASS._state(outgoing);sustains={} if state is None else state['sustains']
    pinpoint=outgoing.custom_conditions.get(PINPOINT.KEY);timed=_timed(outgoing)
    rows=list(sustains.values())
    if scope=='orders':rows.extend([*timed,*[row for row in TRAINING.records(outgoing) if row.get('mode')=='orders'],
          *[row for row in CHEER.live(outgoing) if row['source']==CHEER.GO_FIGHT_WIN]])
    if pinpoint:rows.append(pinpoint)
    rows.extend(_general(engine,outgoing,scope,identifiers))
    return [instance_id(row,outgoing) for row in rows if identifiers is None or instance_id(row,outgoing) in identifiers]


def _open_turn(engine,actor):
    import initiative_interrupts as INTERRUPTS
    state=getattr(engine,INTERRUPTS.KEY,None)
    frames=[] if state is None else state['frames']
    if (not engine.encounter_active or engine.round_start_seconds is None
            or not (engine._active_turn_actor is actor or any(frame['parent'] is actor for frame in frames))):
        raise ValueError('eligible Order turn already closed; no live benefit can be renewed')
    borrowed=next((frame for frame in reversed(frames) if frame['actor'] is actor and frame['mode']=='borrow_turn'),None)
    return {'actor_id':actor.entity_id,'round':engine.round_no,
        'turn_serial':actor.custom_conditions.get('combat_turn_serial',0),
        'after_closure':len(engine._turn_closures),'loan_id':None if borrowed is None else borrowed['loan_id']}


def _turn_anchor(record):
    history=record.get(KEY,{})
    anchor=None
    for event in history.get('events',[]):
        clock=event['clock']
        if clock['phase']=='active':
            if type(clock.get('anchor'))is not dict:
                raise ValueError('active Order clock requires its native turn anchor')
            if anchor is None:anchor=clock['anchor']
            elif clock['anchor']!=anchor:
                raise ValueError('repeated Order handoff changed its original active turn anchor')
        elif anchor is not None:
            raise ValueError('active Order handoff cannot return to an unanchored clock')
    if (anchor is None and 'turn_anchor' in history
            or anchor is not None and history.get('turn_anchor')!=anchor):
        raise ValueError('Order turn anchor differs from its authenticated active clock')
    return anchor


def active_window(engine,holder,record):
    anchor=_turn_anchor(record)
    if anchor is None:return False
    actor=W.actor_index(engine).get(anchor['actor_id'])
    if actor is None:return False
    for closure in engine._turn_closures[anchor['after_closure']:]:
        if (closure['actor'] is actor and closure['round']==anchor['round']
                and closure.get('loan_id')==anchor['loan_id']):return False
    if actor.custom_conditions.get('combat_turn_serial',0)!=anchor['turn_serial']:return False
    try:current=_open_turn(engine,actor)
    except ValueError:return False
    return all(current[key]==anchor[key] for key in ('actor_id','round','turn_serial','loan_id'))


def clock_owner(engine,holder,record):
    anchor=_turn_anchor(record)
    if anchor is None:return holder
    actor=W.actor_index(engine).get(anchor['actor_id'])
    if actor is None:raise ValueError('original active Order turn owner missing')
    return actor


def on_eligible_turn(engine,holder,record,serial):
    if _turn_anchor(record) is not None:return active_window(engine,holder,record)
    return holder.custom_conditions.get('combat_turn_serial',0)==serial


def _clock_plan(engine,outgoing,incoming,record):
    anchor=_turn_anchor(record)
    if anchor is not None:
        if not active_window(engine,outgoing,record):raise ValueError('expired original Order turn cannot be transferred again')
        return {'phase':'active','shift':0,'deadline':anchor['turn_serial'],'anchor':deepcopy(anchor)}
    deadline=None
    if record.get('turn_owner') is outgoing:deadline=record.get('turn_deadline')
    if record.get('turn_owner_id')==outgoing.entity_id and record.get('lifetime')=='next_turn_end':deadline=record['deadline']
    policy=record.get('lifetime_policy')
    if policy is not None and record.get('lifetime_target') is outgoing:
        until=policy.get('until',{})
        if until.get('event')=='turn_end' and until.get('owner')=='target':deadline=policy['started_turns']['target']+until['after']
    if deadline is None:return {'phase':'independent','shift':0}
    serial=outgoing.custom_conditions.get('combat_turn_serial',0)
    if serial<deadline:
        shift=incoming.custom_conditions.get('combat_turn_serial',0)-serial
        return {'phase':'pending','shift':shift,'from_deadline':deadline,'to_deadline':deadline+shift}
    if serial!=deadline:raise ValueError('closed eligible Order turn cannot be renewed')
    return {'phase':'active','shift':0,'deadline':deadline,'anchor':_open_turn(engine,outgoing)}


def plan_clocks(engine,outgoing,incoming,*,scope='orders',identifiers=None):
    result={identity:{'phase':'independent','shift':0} for identity in plan_ids(engine,outgoing,incoming,scope=scope,identifiers=identifiers)}
    if scope=='orders':
        for record in _timed(outgoing):
            if identifiers is None or instance_id(record,outgoing) in identifiers:result[instance_id(record,outgoing)]=_clock_plan(engine,outgoing,incoming,record)
    for record in _general(engine,outgoing,scope,identifiers):result[instance_id(record,outgoing)]=_clock_plan(engine,outgoing,incoming,record)
    return result


def require_switch_proof(engine,event,identity,*,kind='orders'):
    """Join the exact moved instance to its actual native switch producer."""
    import effect_contracts as CONTRACTS
    if event['source']=='move/배턴터치':
        matches=[]
        for token,row in getattr(engine,'_effect_dispatch_receipts',{}).items():
            proof=row.get('native_switch')
            if not isinstance(proof,dict) or proof.get('recall_id')!=event['recall_id']:continue
            if (row['source_id']!=event['source'] or proof.get('source')!=event['source']
                    or row['actor'].entity_id!=event['from_id']):continue
            CONTRACTS.validate_receipt(engine,token,row['source_id'],row['occurrence'],row['actor'],row['target'],row['effect'])
            completion=getattr(engine,'_move_completions',{}).get(proof.get('move_completion'))
            if completion is None or completion['actor'] is not row['actor'] or completion['move_id']!=row['source_id']:
                raise ValueError('Baton handoff lost its actual native Move producer')
            if completion['phase']=='complete' and token not in completion['effects']:
                raise ValueError('Baton handoff receipt is not part of the completed native Move')
            scoped=row.get('status')=='dispatching' and any(value is token for value in getattr(engine,'_native_switch_receipts',()))
            if not scoped and row.get('status')!='completed':continue
            if not scoped and (not proof.get('recalled') or not proof.get('sent')):continue
            matches.append(proof)
    else:
        trainer=W.actor_index(engine).get(event['trainer_id'])
        matches=[] if trainer is None else [use for use in trainer.spec.get('native_switch_feature_uses',[])
            if use.get('source')=='feat/태그-인' and use.get('recall_id')==event['recall_id']
            and use.get('paid_ap')==1 and (use.get('phase')=='completed' or
                use.get('phase')=='sending' and getattr(engine,'_native_tag_in_use',None) is use)]
    if len(matches)!=1:raise ValueError('Order handoff requires exactly one actual native switch occurrence')
    proof=matches[0]
    from native_switch_transfer import seal
    if proof.get('integrity')!=seal(proof):raise ValueError('native switch handoff result changed')
    __import__('native_switch_policy').validate(engine,proof['contract'])
    if (proof.get('outgoing_id')!=event['from_id'] or proof.get('incoming_id')!=event['to_id']
            or proof.get('sent_at',proof.get('at'))!=event['at']
            or proof.get('from_turn')!=event['from_turn'] or proof.get('to_turn')!=event['to_turn']
            or identity not in (proof.get('transfer') or {}).get(kind,[])):
        raise ValueError('native switch occurrence does not prove this exact instance handoff')
    if kind=='orders' and event['clock']!=(proof.get('transfer') or {}).get('clocks',{}).get(identity):
        raise ValueError('Order clock phase differs from the actual native handoff')
    return proof


def original_policy(record):
    """Undo only the observed holder-clock offsets; paid source policy stays immutable."""
    plan=deepcopy(record.get('lifetime_policy',record.get('policy')))
    for event in record.get(KEY,{}).get('events',[]):
        plan['started_turns']['target']-=event['clock']['shift']
    return plan


def lifetime_contract(engine,holder,record,producer):
    original=origin(engine,holder,record)
    contract=producer.get('lifetime_contracts',{}).get(original.entity_id)
    if KEY not in record:return contract
    if record['source']!='C2CSV/input/db/feats.csv:R91:main':
        raise ValueError('this declared Order lifetime has no selected transfer adapter')
    if contract is None or original_policy(record)!=contract['policy']:
        raise ValueError('transferred Order changed its original lifetime')
    return dict(contract,policy=record.get('lifetime_policy',record.get('policy')))


def _check_source(outgoing,incoming,key):
    old=outgoing.spec.get(G.KEY,{});new=incoming.spec.get(G.KEY,{})
    if key in new.get('sources',{}) or key in new.get('effects',{}):raise ValueError('transferred source identity collision')
    receipt=old.get('effects',{}).get(key,{})
    if receipt.get('listeners'):raise ValueError('Order projection listener transfer requires its native listener owner')
    special=[kind for kind in ('type_sources','weight_sources','overlays')
             if key in old.get(kind,{}).get('sources',{}) or key in old.get(kind,{})]
    if special:raise ValueError('Order projection needs the actual '+','.join(special)+' transfer owner')
    from state_fields import stat_minimum
    for field,row in old.get('stat_sources',{}).items():
        if key not in row['sources']:continue
        proposed=deepcopy(new.get('stat_sources',{}).get(field,{
            'base_offset':incoming.stats[field]-incoming.spec['stats'][field],'sources':{}}))
        if key in proposed['sources']:raise ValueError('transferred stat source identity collision')
        proposed['sources'][key]=deepcopy(row['sources'][key])
        if G._stat_value(proposed,incoming.spec['stats'][field])<stat_minimum(incoming.spec,field):
            raise ValueError('transferred Order projection makes its actual recipient statistic invalid')


def _move_source(engine,outgoing,incoming,key):
    """Move only this admitted instance's tracked contributions, never a whole registry."""
    _check_source(outgoing,incoming,key)
    old=G.state(outgoing);new=G.state(incoming)
    receipt=old['effects'].get(key,{})
    numbers={field:(row['sources'][key],row['bounds']) for field,row in old['numbers'].items() if key in row['sources']}
    sets={field:list(row['sources'][key]) for field,row in old['sets'].items() if key in row['sources']}
    scalars={field:deepcopy(row['sources'][key]) for field,row in old['scalar_sources'].items() if key in row['sources']}
    rows={field:[row for row in getattr(outgoing,field) if isinstance(row,dict) and row.get(G.TAG)==key] for field in receipt.get('rows',[])}
    import combat_stage_sources as CS
    stage=outgoing.spec.get(CS.STATE,{}).get('base',{}).get(key)
    stats={field:deepcopy(row['sources'][key]) for field,row in old.get('stat_sources',{}).items() if key in row['sources']}
    source=old['sources'].pop(key,None)
    G.remove_owned(engine,outgoing,key)
    if source is not None:new['sources'][key]=source
    for field,(delta,bounds) in numbers.items():G.numeric(incoming,field,delta,key,bounds=bounds)
    for field,values in sets.items():
        for value in values:G.set_member(incoming,field,value,key)
    for field,value in scalars.items():G.scalar(incoming,field,value,key)
    for field,operations in stats.items():
        for operation_id,operation in operations.items():G.stat(incoming,field,operation['delta'],key,minimum=operation['minimum'],operation_id=operation_id)
    for field,values in rows.items():getattr(incoming,field).extend(values)
    if receipt:new['effects'][key]=receipt
    if stage:
        for stat,delta in stage['deltas'].items():CS.add_base(incoming,key,stat,delta,source=stage['source'],ends=stage['ends'])


def _timed(actor):
    import chronicler as CHRONICLE,survivalist_class as GUIDE,duelist as DUELIST
    import conquerors_march as MARCH,directive_features as DIRECTOR,fashionista as DRESS
    sources={CHRONICLE.PROFILING,GUIDE.GUIDE,DUELIST.EXPEND,DUELIST.MANUAL,MARCH.FEATURE,DIRECTOR.SOURCE,DRESS.DRESS}
    return [row for row in TIME.records(actor) if row.get('source') in sources or 'go_fight_win_use' in row or row.get('optional_clause_id')=='ERRATA-056']


def require_supported_orders(outgoing):
    admitted={id(row) for row in _timed(outgoing)}
    for row in TIME.records(outgoing):
        unit=outgoing.r.selection.units.get(row.get('source'),{})
        if id(row) not in admitted and not row.get('grant_source','').startswith('training-order:') and any('지시' in tag or tag=='Orders' for tag in unit.get('tags',[])):
            # Brace's consumed Standard/Status benefit is not its sustained Stratagem.
            if 'commander_brace_dr' in row:continue
            raise ValueError('live Order source requires its exact native transfer adapter: '+str(row.get('source')))


def preflight(engine,outgoing,incoming,*,scope='orders',identifiers=None):
    import class_passive_combat as CLASS,combat_precision_features as PINPOINT
    import training_features as TRAINING
    if scope not in ('orders','stratagems'):raise ValueError('reviewed Baton transfer scope required')
    if scope=='orders':TRAINING.preflight_transfer(engine,outgoing,incoming,identifiers=identifiers)
    state=CLASS._state(outgoing)
    sustains={} if state is None else {uid:row for uid,row in state['sustains'].items()
        if identifiers is None or instance_id(row,outgoing) in identifiers}
    pinpoint=PINPOINT.binding(engine,outgoing)
    if pinpoint and identifiers is not None and instance_id(pinpoint,outgoing) not in identifiers:pinpoint=None
    general=_general(engine,outgoing,scope,identifiers)
    import commander_orders as COMMANDER
    if sustains or pinpoint or any(row['feature']==COMMANDER.BRACE for row in general):CLASS._require_stratagem_slot(incoming)
    for row in general:
        if any(other['feature']==row['feature'] for other in COMMANDER.live(engine,incoming)):
            raise ValueError('replacement already has the source-owned general Order')
        origin_id(row,outgoing);_clock_plan(engine,outgoing,incoming,row)
    for uid,row in sustains.items():
        CLASS._active(engine,outgoing,uid)
        _check_source(outgoing,incoming,row['instance'])
    if scope=='stratagems':return sustains,pinpoint,[]
    incoming_timed=_timed(incoming)
    import chronicler as CHRONICLE,survivalist_class as GUIDE,duelist as DUELIST
    import conquerors_march as MARCH,fashionista as DRESS
    exclusive={CHRONICLE.PROFILING,GUIDE.GUIDE,MARCH.FEATURE,DRESS.DRESS}
    timed=[row for row in _timed(outgoing) if identifiers is None or instance_id(row,outgoing) in identifiers]
    for row in timed:
        # Preserve the source adapters' actual occupancy rules.
        if any(other['source']==row['source'] and (row['source'] in exclusive or
               row['source']==DUELIST.MANUAL and other.get('duelist_mode')==row.get('duelist_mode'))
               for other in incoming_timed):
            raise ValueError('replacement already has the source-owned Order: '+row['source'])
        origin_id(row,outgoing)
        _clock_plan(engine,outgoing,incoming,row)
        if row.get('turn_owner') is outgoing:
            for field in ('turn_deadline','turn_start_deadline'):
                if field in row and row[field]<outgoing.custom_conditions.get('combat_turn_serial',0):
                    raise ValueError('expired own-turn Order cannot be passed')
        if 'fashionista_dress' in row:
            for key in row['fashionista_dress']['registration_keys']:
                if key in getattr(incoming,'_item_reg',{}):raise ValueError('replacement Dress projection collides')
                registration=outgoing._item_reg[key]
                if any(r.get('item_id')==registration['item_id'] for r in getattr(incoming,'_item_reg',{}).values()):
                    raise ValueError('replacement already benefits from the projected item')
                for sid in dict.fromkeys((registration['state_source'],*registration['effect_sources'])):
                    _check_source(outgoing,incoming,sid)
        for key in [row.get('grant_source')]:
            if key:_check_source(outgoing,incoming,key)
    if identifiers is None:require_supported_orders(outgoing)
    return sustains,pinpoint,timed


def transfer(engine,outgoing,incoming,*,source,recall_id,scope='orders',identifiers=None):
    import class_passive_combat as CLASS,combat_precision_features as PINPOINT
    import training_features as TRAINING
    sustains,pinpoint,timed=preflight(engine,outgoing,incoming,scope=scope,identifiers=identifiers)
    clocks={instance_id(row,outgoing):_clock_plan(engine,outgoing,incoming,row) for row in timed}
    moved=TRAINING.transfer(engine,outgoing,incoming,source=source,recall_id=recall_id,identifiers=identifiers) if scope=='orders' else []
    import cheerleader as CHEER,effect_instances as INSTANCES
    for row in list(CHEER.live(outgoing)) if scope=='orders' else []:
        if row['source']!=CHEER.GO_FIGHT_WIN:continue
        if identifiers is not None and instance_id(row,outgoing) not in identifiers:continue
        observe(engine,outgoing,incoming,row,source,recall_id)
        INSTANCES.transfer(engine,outgoing,incoming,row,source=source)
        outgoing.spec[CHEER.KEY].remove(row);incoming.spec.setdefault(CHEER.KEY,[]).append(row)
        moved.append(row['id'])
    for uid,row in list(sustains.items()):
        observe(engine,outgoing,incoming,row,source,recall_id)
        _move_source(engine,outgoing,incoming,row['instance'])
        row['target_id']=incoming.entity_id
        receiving=CLASS._state(incoming,create=True)
        receiving['serial']=max(receiving['serial'],CLASS._state(outgoing)['serial'])
        receiving['sustains'][uid]=CLASS._state(outgoing)['sustains'].pop(uid)
        moved.append(row['instance'])
    if pinpoint:
        observe(engine,outgoing,incoming,pinpoint,source,recall_id)
        pinpoint['target']=incoming
        incoming.custom_conditions[PINPOINT.KEY]=outgoing.custom_conditions.pop(PINPOINT.KEY)
        moved.append(pinpoint['instance'])
    for row in timed:
        clock=clocks[instance_id(row,outgoing)]
        observe(engine,outgoing,incoming,row,source,recall_id,clock=clock)
        difference=clock['shift']
        if row.get('turn_owner') is outgoing and clock['phase']=='pending':
            row['turn_owner']=incoming
            for key in ('turn_deadline','turn_start_deadline'):
                if key in row:row[key]+=difference
            if 'chronicler_profiling' in row:
                row['chronicler_profiling']['active_serial']+=difference
        if row.get('lifetime_target') is outgoing and clock['phase']=='pending':
            row['lifetime_target']=incoming
            row['lifetime_policy']['started_turns']['target']+=difference
        if row.get('grant_source'):_move_source(engine,outgoing,incoming,row['grant_source'])
        if 'fashionista_dress' in row:
            for key in row['fashionista_dress']['registration_keys']:
                registration=outgoing._item_reg[key]
                for sid in dict.fromkeys((registration['state_source'],*registration['effect_sources'])):_move_source(engine,outgoing,incoming,sid)
                if not hasattr(incoming,'_item_reg'):incoming._item_reg={}
                incoming._item_reg[key]=outgoing._item_reg.pop(key)
        TIME.records(outgoing).remove(row)
        incoming.custom_conditions.setdefault(TIME.KEY,[]).append(row)
        if 'fashionista_dress' in row:
            for key in row['fashionista_dress']['registration_keys']:
                __import__('csv_item_physical_contracts').projection_transferred(engine,incoming,incoming._item_reg[key])
        moved.append(instance_id(row,incoming))
    import commander_orders as COMMANDER
    general=_general(engine,outgoing,scope,identifiers)
    general_clocks={row['id']:_clock_plan(engine,outgoing,incoming,row) for row in general}
    moved.extend(COMMANDER.transfer_baton(engine,outgoing,incoming,[row['id'] for row in general],
        source=source,recall_id=recall_id,scope=scope,clocks=general_clocks))
    engine.time_actors([incoming])
    # Source and lifetime must be placed together before Manual's Ability reader runs.
    for actor in (outgoing,incoming):
        for field in G.LIST_FIELDS:G.materialize(actor,field)
    return moved


def validate_world(engine,index):
    import class_passive_combat as CLASS,combat_precision_features as PINPOINT
    for holder in index.values():
        state=CLASS._state(holder)
        import training_features as TRAINING
        import cheerleader as CHEER
        import commander_orders as COMMANDER
        rows=[*_timed(holder),*holder.custom_conditions.get('effect_lifetime_history',[]),
              *CHEER.live(holder),*CHEER.history(holder),
              *[row for row in TRAINING.records(holder) if row.get('mode')=='orders'],*COMMANDER.records(holder)]
        if state:rows.extend(state['sustains'].values())
        if PINPOINT.KEY in holder.custom_conditions:rows.append(holder.custom_conditions[PINPOINT.KEY])
        for row in rows:
            if KEY not in row:continue
            original=origin(engine,holder,row)
            if original.kind!='pokemon' or holder.kind!='pokemon':raise ValueError('Order transfer requires actual Pokemon holders')
            for event in row[KEY]['events']:
                old=index.get(event['from_id']);new=index.get(event['to_id'])
                if old is None or new is None or event['trainer_id'] not in index:
                    raise ValueError('Order transfer historical participants are missing')
                recall=next((r['fact'] for r in old.spec.get('native_recall_history',[]) if r['id']==event['recall_id']),None)
                if event['at']>engine.elapsed_seconds or recall is None or recall['trainer_id']!=event['trainer_id']:
                    raise ValueError('Order transfer requires its actual native recall and original Trainer')
                require_switch_proof(engine,event,row[KEY]['instance_id'])
            if row in _timed(holder) and row[KEY].get('turn_anchor') is not None and not active_window(engine,holder,row):
                raise ValueError('live transferred Order outlived its original eligible turn')
            if row in _timed(holder):
                clock=row[KEY]['events'][-1]['clock']
                if clock['phase'] in ('pending','active'):
                    owner=clock_owner(engine,holder,row)
                    expected=clock.get('to_deadline',clock.get('deadline'))
                    if 'turn_owner' in row and (row['turn_owner'] is not owner or row.get('turn_deadline')!=expected):
                        raise ValueError('Order timer lost its actual pending or already-open turn boundary')
                    policy=row.get('lifetime_policy')
                    if policy is not None and (row.get('lifetime_target') is not owner
                            or policy['started_turns']['target']+policy['until']['after']!=expected):
                        raise ValueError('Order lifetime lost its actual target-turn boundary')
            if row in COMMANDER.records(holder):
                clock=row[KEY]['events'][-1]['clock']
                if clock['phase'] in ('pending','active'):
                    owner=clock_owner(engine,holder,row)
                    if row['turn_owner_id']!=owner.entity_id or row['deadline']!=clock.get('to_deadline',clock.get('deadline')):
                        raise ValueError('general Order lost its actual target-turn boundary')
    return True
