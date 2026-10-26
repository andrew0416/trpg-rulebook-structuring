"""Four source contracts; effective abilities remain owned by state_grants.

Move evidence lives in the existing native completion. Faint evidence lives on
the actual fainted sheet. Neither is an alternative ability collection.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import ability_transitions as A
import state_grants as G
import combat_timing as TIME
import world_entities as W
import static_equipment_contracts as STATIC

RECEIVER='ability/리시버'
MUMMY='ability/미라-playtest'
GAS='ability/화학변화가스'
ENTRAIN='move/동료만들기'
TAG='ability_exchange'
FAINTS='ability_exchange_faint_events'
EDITION='ability_exchange_source_editions'
AURA_PROOFS='ability_exchange_aura_proofs'
LIVE_PROOF='ability_exchange_live_proof'


def install(rules):
    policy=json.loads((Path(rules.root)/'data/ability-exchange-policy.json').read_text(encoding='utf-8'))
    if policy.get('schema_version')!=1:raise ValueError('reviewed ability-exchange policy required')
    for path,digest in policy['source_files'].items():
        if hashlib.sha256((Path(rules.root)/path).read_bytes()).hexdigest()!=digest:
            raise ValueError('ability-exchange source changed: '+path)
    rules.ability_exchange_policy=policy
    rows=json.loads((Path(rules.root)/'output/entities/abilities.json').read_text(encoding='utf-8'))
    if isinstance(rows,dict):rows=rows.get('entities',rows.get('abilities',[]))
    rules.ability_exchange_triggered={r['id'] for r in rows if r.get('trigger')}


def source(rules,value):
    for uid,row in rules.ability_exchange_policy['contracts'].items():
        if value in row['aliases']:return uid
    return None


def registration(rules,value):
    uid=source(rules,value)
    if uid is None or uid==ENTRAIN:return None
    selected='ability/화학변화가스-2' if value in ('화학변화가스-2','ability/화학변화가스-2') else uid
    if rules._selected_rule(selected)!=selected:raise ValueError('ability-exchange source is not selected')
    row=rules.ability_exchange_policy['contracts'][uid]
    return {'name':row['name'],'source_id':selected,
            'equivalent_source_ids':[GAS,'ability/화학변화가스-2'] if uid==GAS else [uid]}


def operation_mode(rules,uid):
    uid=source(rules,uid)
    return None if uid is None else rules.ability_exchange_policy['contracts'][uid]['mode']


def handled(rules,uid):return registration(rules,uid) is not None


def _on_field(c):return bool(c.on_field and not c.fainted and not c.dead)


def _pool(c):
    return [uid for uid in A.project_components(c) if A.active(c,uid)]


def _basic(c):
    if c.kind!='pokemon':return []
    import growth_milestones as GROWTH
    return [A.ability_id(c.r,x) for x in GROWTH.natural_abilities(c.r,c.spec,pools=('기본 특성',))]


def _request(c,uid,target):return c.spec.get(A.CHOICES,{}).get(A.key(uid,target))


def _edition(c):
    # A Core Mummy passed by an actual replacement retains its source edition.
    for row in reversed(list(c.spec.get(G.KEY,{}).get('sources',{}).values())):
        if row.get(TAG) and MUMMY in row.get('ability_operation',{}).get('add',[]):
            return row.get('edition') or 'playtest'
    return c.spec.get(EDITION,{}).get(MUMMY,'playtest')


def select(engine,actor,target,uid,*,ability=None,allies=(),reason,edition=None):
    uid=source(engine.r,uid)
    if uid not in (RECEIVER,MUMMY,ENTRAIN):raise ValueError('exchange source requires an actual selectable trigger')
    index=W.actor_index(engine)
    if any(index.get(c.entity_id) is not c for c in (actor,target,*allies)):
        raise ValueError('actual registered exchange participants required')
    if not isinstance(reason,str) or not reason.strip():raise ValueError('actual exchange choice reason required')
    if edition is not None and uid!=MUMMY:raise ValueError('edition applies only to Mummy')
    variant=edition or _edition(actor)
    if variant not in ('core','playtest'):raise ValueError('explicit Mummy core or playtest edition required')
    if uid!=ENTRAIN and (not _on_field(actor) or not A.active(actor,uid)):
        raise ValueError('actual active exchange ability required before its trigger')
    if uid==MUMMY and edition is not None:
        if engine.encounter_active and edition!=_edition(actor):raise ValueError('select Mummy edition before encounter')
        if not engine.encounter_active:
            if target is not actor or allies or ability is not None:raise ValueError('pre-encounter Mummy source edition configuration takes no trigger choice')
            actor.spec.setdefault(EDITION,{})[MUMMY]=edition
            actor.spec.get(A.CHOICES,{}).pop(A.key(MUMMY,actor),None)
            return {'source':MUMMY,'edition':edition}
    branch='copy'
    owner=actor
    recipients=[]
    if uid==RECEIVER:
        if not actor.side or target.side!=actor.side:raise ValueError('Receiver requires an actual ally')
        if target is actor:
            branch='bequeath'
            if len(allies)!=1 or allies[0] is actor or allies[0].side!=actor.side or not _on_field(allies[0]):
                raise ValueError('one other allied on-field Receiver recipient required')
            recipients=[allies[0].entity_id]
        else:
            branch='receive';owner=target
            if allies or not _on_field(target):raise ValueError('one live on-field ally faint trigger required')
    elif allies:raise ValueError('only Receiver bequeath chooses an ally')
    if uid==MUMMY and target is not actor:raise ValueError('Mummy choice belongs to the actual user, not attacker')
    if uid==MUMMY and variant=='core':
        if ability is not None:raise ValueError('Core Mummy replaces all attacker abilities without a selected one')
        chosen=None
    else:
        chosen=A.ability_id(engine.r,ability) if ability is not None else None
        pool=_pool(owner)
        if uid==RECEIVER and branch=='bequeath':pool=[x for x in pool if x in _basic(actor)]
        if chosen is None or chosen not in pool:raise ValueError('choose one actual active eligible ability')
        A.component_definitions(engine.r,chosen)
    record={'source':uid,'target_id':target.entity_id,'ability_id':chosen,'allies':recipients,
            'reason':reason,'branch':branch,'edition':variant if uid==MUMMY else None}
    if uid in (RECEIVER,MUMMY):
        import frequency as F
        usage=uid+(':'+branch if uid==RECEIVER else ':'+variant)
        frequency='장면' if uid==RECEIVER else engine.r.ability_exchange_policy['mummy_editions'][variant]['frequency']
        if not F.activation_allowed(actor,usage,frequency,engine=engine,action_actor=actor):raise ValueError('exchange source frequency exhausted')
    actor.spec.setdefault(A.CHOICES,{})[A.key(uid,target)]=record
    return deepcopy(record)


def activate(engine,actor,name,target):
    raise ValueError('exchange ability requires its actual native trigger; choose before the event')


def interested(engine,actor=None,target=None):
    return any(any(r.get('source') in (RECEIVER,MUMMY,ENTRAIN) for r in c.spec.get(A.CHOICES,{}).values())
               or A.active(c,GAS) for c in W.actors(engine))


def _gas_sources(c):
    return {k:v for k,v in c.spec.get(G.KEY,{}).get('sources',{}).items()
            if v.get(TAG) and v.get('gas_block') is True}


def admit_trigger(engine,actor,uid):
    canonical=source(engine.r,uid)
    if canonical is None:
        try:canonical=A.ability_id(engine.r,uid)
        except (ValueError,KeyError):return True
    triggered=canonical in (RECEIVER,MUMMY) or canonical in engine.r.ability_exchange_triggered
    return not (triggered and _gas_sources(actor))


def preflight_move(engine,actor,target,move,mm):
    if move['id']==ENTRAIN:
        request=_request(actor,ENTRAIN,target)
        if not request or request['ability_id'] not in _pool(actor):
            raise ValueError('Entrainment requires a current active donor ability choice')
        if not engine.encounter_active:raise ValueError('Entrainment requires an actual encounter')
    if move['id'] in engine.r.ability_exchange_policy['gas_moves'] and A.active(actor,GAS):TIME.current(engine)
    return mm


def _pay(engine,c,uid,*,branch=None,edition=None,allow_faint=False):
    import frequency as F
    import action_lifecycle as ACTION
    import reactive_ability_events as REACTIVE
    usage=uid+(':'+branch if branch else ':'+edition if edition else '')
    frequency='장면' if uid==RECEIVER else engine.r.ability_exchange_policy['mummy_editions'][edition]['frequency']
    if not admit_trigger(engine,c,uid):return False
    if not allow_faint and not REACTIVE._reaction_allowed(engine,c):return False
    if allow_faint and c.dead:return False
    if not F.activation_allowed(c,usage,frequency,engine=engine,action_actor=c):return False
    ACTION.record_action(engine,c,'free')
    F.consume_activation(c,usage,frequency,engine=engine,action_actor=c)
    return True


def _application(engine,parent,source_id,owner,recipient,operation,*,edition=None,ends=(),deadline=None,selection=None,branch=None):
    rows=parent.setdefault(TAG,[])
    app={'id':parent['id']+':exchange:'+str(len(rows)+1),'source':source_id,
         'owner':owner,'recipient':recipient,'operation':deepcopy(operation),
         'edition':edition,'ends':list(ends),'deadline':deepcopy(deadline),'selection':deepcopy(selection),'branch':branch,
         'facts':{'round':engine.round_no,'count':getattr(engine,'_initiative_cursor',{}).get('count'),
                  'turn':recipient.custom_conditions.get('combat_turn_serial',0),'owner_pool':_pool(owner),
                  'recipient_pool':_pool(recipient),'owner_side':owner.side,'recipient_side':recipient.side,
                  'owner_edition':_edition(owner)},
         'components':{uid:list(A.component_definitions(owner.r,uid)) for uid in operation['remove']+operation['add']}}
    rows.append(app)
    parent.setdefault('ability_exchange_proofs',{})[app['id']]=_proof(app)
    return app


def _proof(app):
    import root_resolution as ROOT
    return ROOT.fingerprint({k:(v.entity_id if k in ('owner','recipient') else v) for k,v in app.items()})


def _live_proof(row,record=None):
    import root_resolution as ROOT
    timing=None if record is None else {k:(v.entity_id if k=='turn_owner' else v) for k,v in record.items()
                                       if k not in ('owned_statuses','installing',LIVE_PROOF)}
    return ROOT.fingerprint({'source':row,'timing':timing})


def _validate_live_receipts(index):
    # Check the last genuine emission before observing a changed world. Refresh
    # must never launder a forged operation/clock into the now-correct value.
    for actor in index.values():
        sources=actor.spec.get(G.KEY,{}).get('sources',{})
        proofs=actor.spec.get(AURA_PROOFS,{})
        aura={key:row for key,row in sources.items() if row.get(TAG)=='aura'}
        if not isinstance(proofs,dict) or set(proofs)!=set(aura):raise ValueError('Gas aura lacks its actual source emission receipt')
        for key,row in aura.items():
            if proofs[key]!=_live_proof(row):raise ValueError('Gas aura source differs from actual emission receipt')
        for record in TIME.records(actor):
            if TAG not in record:continue
            row=sources.get(record.get('grant_source'))
            if row is None or record.get(LIVE_PROOF)!=_live_proof(row,record):raise ValueError('ability exchange source or clock differs from its native receipt')


def _grant(engine,app):
    c=app['recipient'];key=app['id']+':'+c.entity_id
    gas=app['source']==GAS
    G._source(c,key,'effect',owner_id=app['owner'].entity_id,rule_id=app['source'],
              lifetime='ability_exchange',**{TAG:app['id']},edition=app['edition'],
              ability_operation=deepcopy(app['operation']),gas_block=gas)
    record={'source':app['source'],'grant_source':key,TAG:app['id'],'effect_contract':True,
            'ends':list(app['ends']),'encounter_end':True}
    deadline=app['deadline']
    if deadline:
        if deadline['kind']=='turn':record.update(turn_owner=c,turn_deadline=deadline['value'])
        else:record['count_deadline']=list(deadline['value'])
    TIME.install(engine,c,record)
    record[LIVE_PROOF]=_live_proof(c.spec[G.KEY]['sources'][key],record)
    G.materialize(c,'abilities');G.reconcile(engine,c)


def _defensive_operation(engine,c):
    ignored=list(_gas_sources(c))
    projected=A.project_components(c,ignored_sources=ignored)
    remove=[uid for uid in projected if uid in engine.r.trickster_defensive and not A.protected(engine.r,uid)]
    return {'kind':'suppress','remove':remove,'add':[]}


def resolved_hit(engine,actor,target,move,completion_id,*,hit_prevented=False,contact=None):
    import reactive_ability_events as REACTIVE
    import move_completion as MC
    row=REACTIVE._completion(engine,actor,target,move,completion_id)
    result=MC.recipient_result(row,target)
    if hit_prevented or not result or not result.get('hit') or result.get('cancelled'):return
    contact=REACTIVE._melee(move) if contact is None else contact
    if type(contact) is not bool or (contact and not REACTIVE._melee(move)):
        raise ValueError('exchange contact must belong to its actual melee hit')
    mark=row.setdefault('ability_exchange_hits',[])
    if target.entity_id in mark:return
    mark.append(target.entity_id)
    if move['id']==ENTRAIN:
        request=_request(actor,ENTRAIN,target)
        if not request or request['ability_id'] not in _pool(actor):raise ValueError('stale native Entrainment donor choice')
        chosen=request['ability_id']
        if not A.protected(engine.r,chosen) and not STATIC.blocks_ability_change(engine,target,actor):
            app=_application(engine,row,ENTRAIN,actor,target,{'kind':'copy','remove':[],'add':[chosen]},
                             edition=_edition(actor) if chosen==MUMMY else None,selection=request,
                             deadline={'kind':'turn','value':target.custom_conditions.get('combat_turn_serial',0)+3})
            _grant(engine,app)
        actor.spec.get(A.CHOICES,{}).pop(A.key(ENTRAIN,target),None)
    if (A.active(actor,GAS) and move['id'] in engine.r.ability_exchange_policy['gas_moves']
            and not STATIC.blocks_ability_change(engine,target,actor)):
        app=_application(engine,row,GAS,actor,target,_defensive_operation(engine,target),
                         deadline={'kind':'count','value':[engine.round_no+1,TIME.current(engine)]})
        _grant(engine,app)
    request=_request(target,MUMMY,target)
    if request and A.active(target,MUMMY) and contact:
        edition=request['edition'];chosen=request['ability_id'];pool=_pool(target)
        if edition!=_edition(target):raise ValueError('stale Mummy request differs from actual fixed source edition')
        if edition=='playtest' and chosen not in pool:raise ValueError('stale Mummy user ability choice')
        if _pay(engine,target,MUMMY,edition=edition):
            if edition=='core':
                recipient=actor
                operation={'kind':'replace','remove':[x for x in _pool(actor) if not A.protected(engine.r,x)],'add':[MUMMY]}
                ends=engine.r.ability_exchange_policy['mummy_editions'][edition]['ends']
            else:
                recipient=target;operation={'kind':'suppress','remove':[chosen],'add':[]};ends=engine.r.ability_exchange_policy['mummy_editions'][edition]['ends']
            if ((edition=='core' or not A.protected(engine.r,chosen))
                    and not STATIC.blocks_ability_change(engine,recipient,target)):
                _grant(engine,_application(engine,row,MUMMY,target,recipient,operation,edition=edition,ends=ends,selection=request))
            target.spec.get(A.CHOICES,{}).pop(A.key(MUMMY,target),None)


def before_faint(engine,c):
    if c.fainted:return None
    if not engine.encounter_active:return None
    candidates=[]
    for owner in W.actors(engine):
        target=c
        request=_request(owner,RECEIVER,target)
        if request and A.active(owner,RECEIVER) and owner.on_field and not owner.dead:
            candidates.append({'owner':owner,'request':deepcopy(request),'active':_pool(owner),
                               'trigger_allowed':admit_trigger(engine,owner,RECEIVER)})
    if not candidates:return None
    return {'active':_pool(c),'basic':_basic(c),'on_field':bool(c.on_field),'candidates':candidates,'mummy_edition':_edition(c),'side':c.side}


def fainted(engine,c,snapshot):
    if snapshot is None:return
    if not c.fainted or c.hp>0:raise ValueError('actual newly fainted native producer required')
    rows=c.spec.setdefault(FAINTS,[])
    event={'id':c.entity_id+':faint:'+str(len(rows)+1),'actor':c,'round':engine.round_no,
           'hp':c.hp,'snapshot':snapshot}
    rows.append(event)
    for candidate in snapshot['candidates']:
        owner=candidate['owner'];request=candidate['request'];branch=request['branch'];chosen=request['ability_id']
        if not candidate['trigger_allowed'] or not snapshot['on_field']:continue
        if branch=='bequeath':
            recipient=W.actor_index(engine).get(request['allies'][0])
            valid=owner is c and recipient is not None and _on_field(recipient) and recipient.side==owner.side and chosen in snapshot['active'] and chosen in snapshot['basic']
        else:
            recipient=owner
            valid=owner is not c and _on_field(owner) and owner.side==c.side and chosen in snapshot['active']
        if not valid:raise ValueError('Receiver selection is stale at the actual faint boundary')
        if _pay(engine,owner,RECEIVER,branch=branch,allow_faint=owner is c):
            if not A.protected(engine.r,chosen) and not STATIC.blocks_ability_change(engine,recipient,owner):
                app=_application(engine,event,RECEIVER,owner,recipient,{'kind':'copy','remove':[],'add':[chosen]},
                                 edition=snapshot['mummy_edition'] if chosen==MUMMY else None,
                                 ends=['encounter'],branch=branch,selection=request)
                _grant(engine,app)
            owner.spec.get(A.CHOICES,{}).pop(A.key(RECEIVER,c),None)


def _auras(engine,index):
    import body_state as BODY
    expected={}
    if not engine.encounter_active:return expected
    for owner in index.values():
        if not _on_field(owner) or not A.active(owner,GAS):continue
        for recipient in index.values():
            if recipient is owner or not _on_field(recipient) or not BODY.in_range(engine,owner,recipient,1):continue
            if STATIC.blocks_ability_change(engine,recipient,owner):continue
            key='ability-exchange:gas:'+owner.entity_id+':'+recipient.entity_id
            expected[(recipient.entity_id,key)]=(owner,_defensive_operation(engine,recipient))
    return expected


def refresh(engine):
    index=W.actor_index(engine)
    _validate_live_receipts(index)
    expected=_auras(engine,index)
    for actor in index.values():
        sources=actor.spec.get(G.KEY,{}).get('sources',{})
        changed=False
        for key,row in list(sources.items()):
            if row.get(TAG)!='aura':continue
            wanted=expected.get((actor.entity_id,key))
            if wanted is None:
                actor.spec[AURA_PROOFS].pop(key);G.revoke(actor,key,engine=engine);changed=True
            elif row['ability_operation']!=wanted[1]:
                row['ability_operation']=deepcopy(wanted[1]);actor.spec[AURA_PROOFS][key]=_live_proof(row);changed=True
        for (recipient_id,key),(owner,operation) in expected.items():
            if recipient_id!=actor.entity_id or key in sources:continue
            G._source(actor,key,'effect',owner_id=owner.entity_id,rule_id=GAS,lifetime='source_aura',
                      **{TAG:'aura'},ability_operation=operation,gas_block=True)
            actor.spec.setdefault(AURA_PROOFS,{})[key]=_live_proof(actor.spec[G.KEY]['sources'][key])
            changed=True
        for key,row in _gas_sources(actor).items():
            if row.get(TAG)=='aura':continue
            operation=_defensive_operation(engine,actor)
            if row['ability_operation']!=operation:
                row['ability_operation']=operation
                record=next(r for r in TIME.records(actor) if r.get('grant_source')==key)
                record[LIVE_PROOF]=_live_proof(row,record);changed=True
        if changed:G.materialize(actor,'abilities');G.reconcile(engine,actor)


def end(engine,actor,event):
    for record in list(TIME.records(actor)):
        if TAG in record and event in record['ends']:TIME.expire(engine,actor,record)


def _timing(app):
    result={'source':app['source'],'grant_source':app['id']+':'+app['recipient'].entity_id,
            TAG:app['id'],'effect_contract':True,'ends':app['ends'],'encounter_end':True}
    if app['deadline']:
        if app['deadline']['kind']=='turn':result.update(turn_owner=app['recipient'],turn_deadline=app['deadline']['value'])
        else:result['count_deadline']=app['deadline']['value']
    return result


def _validate_application(engine,parent,app,number,index):
    if app['id']!=parent['id']+':exchange:'+str(number) or parent.get('ability_exchange_proofs',{}).get(app['id'])!=_proof(app):
        raise ValueError('ability exchange differs from its native producer proof')
    if any(index.get(app[k].entity_id) is not app[k] for k in ('owner','recipient')):
        raise ValueError('ability exchange actual participants required')
    source_id=app['source'];op=app['operation'];facts=app['facts'];selection=app['selection']
    if source_id in (ENTRAIN,RECEIVER):
        chosen=selection['ability_id']
        if op!={'kind':'copy','remove':[],'add':[chosen]} or A.protected(engine.r,chosen):raise ValueError('one actual transferable ability copy required')
        if source_id==ENTRAIN:
            if chosen not in facts['owner_pool'] or app['ends'] or app['deadline']!={'kind':'turn','value':facts['turn']+3}:raise ValueError('Entrainment three actual recipient turns required')
        elif app['ends']!=['encounter'] or app['deadline'] is not None:raise ValueError('Receiver encounter lifetime required')
    elif source_id==MUMMY:
        if MUMMY not in facts['owner_pool'] or app['edition'] not in ('core','playtest') or app['edition']!=facts['owner_edition']:raise ValueError('Mummy active producer and fixed source edition required')
        if app['edition']=='core':
            expected={'kind':'replace','remove':[x for x in facts['recipient_pool'] if not A.protected(engine.r,x)],'add':[MUMMY]}
            ends=['encounter']
        else:
            chosen=selection['ability_id'];expected={'kind':'suppress','remove':[chosen],'add':[]};ends=['scene_end','recall']
            if chosen not in facts['owner_pool'] or A.protected(engine.r,chosen):raise ValueError('PT Mummy requires one transferable user ability')
        if op!=expected or app['ends']!=ends or app['deadline'] is not None:raise ValueError('Mummy operation or source lifetime mismatch')
    elif source_id==GAS:
        if GAS not in facts['owner_pool'] or app['ends'] or type(facts['count']) is not int or app['deadline']!={'kind':'count','value':[facts['round']+1,facts['count']]}:raise ValueError('Gas one full round requires native hit count')
        if op['kind']!='suppress' or op['add'] or any(x not in engine.r.trickster_defensive or A.protected(engine.r,x) for x in op['remove']):raise ValueError('Gas disables only transferable printed Defensive components')
    else:raise ValueError('unreviewed ability exchange application')
    if set(app['components'])!=set(op['remove']+op['add']):raise ValueError('ability exchange component evidence incomplete')
    for uid,components in app['components'].items():
        if components!=list(A.component_definitions(engine.r,uid)):raise ValueError('ability exchange component contract changed')


def validate_world(engine,index):
    import move_completion as MC
    _validate_live_receipts(index)
    expected={}
    for token,row in getattr(engine,'_move_completions',{}).items():
        for number,app in enumerate(row.get(TAG,[]),1):
            _validate_application(engine,row,app,number,index)
            source_id=app['source'];owner=app['owner'];recipient=app['recipient']
            target=recipient if source_id!=MUMMY or app['edition']=='playtest' else owner
            result=MC.recipient_result(row,target)
            if (not result or not result.get('hit') or result.get('cancelled') or target.entity_id not in row.get('ability_exchange_hits',[])):
                raise ValueError('ability exchange requires actual unprevented native hit')
            if source_id==ENTRAIN:
                if row['move_id']!=ENTRAIN or row['actor'] is not owner or app['operation']['kind']!='copy':raise ValueError('Entrainment producer mismatch')
            elif source_id==GAS:
                if row['actor'] is not owner or row['move_id'] not in engine.r.ability_exchange_policy['gas_moves']:raise ValueError('Gas native move producer mismatch')
            elif source_id==MUMMY:
                if owner is not target or (app['edition']=='core' and recipient is not row['actor']) or not __import__('reactive_ability_events')._melee(row['move']):raise ValueError('Mummy actual melee participants required')
            else:raise ValueError('unreviewed move ability exchange')
            expected[(recipient.entity_id,app['id']+':'+recipient.entity_id)]=app
    for actor in index.values():
        for number,event in enumerate(actor.spec.get(FAINTS,[]),1):
            if event['id']!=actor.entity_id+':faint:'+str(number) or event['actor'] is not actor or event['hp']>0:raise ValueError('Receiver actual faint occurrence required')
            for sequence,app in enumerate(event.get(TAG,[]),1):
                _validate_application(engine,event,app,sequence,index)
                chosen=app['operation']['add'];request=app['selection'];owner=app['owner'];recipient=app['recipient']
                snapshot=event['snapshot']
                if app['source']!=RECEIVER or chosen!=[request['ability_id']] or chosen[0] not in snapshot['active']:raise ValueError('Receiver donor differs from actual faint snapshot')
                candidates=[x for x in snapshot['candidates'] if x['owner'] is owner and x['request']==request and x['trigger_allowed'] and RECEIVER in x['active']]
                if len(candidates)!=1 or not snapshot['on_field'] or app['facts']['owner_side']!=snapshot['side'] or not snapshot['side']:raise ValueError('Receiver lacks actual allied faint trigger eligibility')
                if app['branch']=='bequeath':
                    if owner is not actor or chosen[0] not in snapshot['basic'] or request['allies']!=[recipient.entity_id]:raise ValueError('Receiver requires own actual Basic and chosen on-field ally')
                elif recipient is not owner or owner is actor:raise ValueError('Receiver receive participant mismatch')
                expected[(recipient.entity_id,app['id']+':'+recipient.entity_id)]=app
    auras=_auras(engine,index)
    for actor in index.values():
        editions=actor.spec.get(EDITION,{})
        if not isinstance(editions,dict) or set(editions)-{MUMMY} or any(x not in ('core','playtest') for x in editions.values()):raise ValueError('exact pre-encounter Mummy source edition required')
        for key,request in actor.spec.get(A.CHOICES,{}).items():
            if request.get('source') not in (RECEIVER,MUMMY,ENTRAIN):continue
            fields={'source','target_id','ability_id','allies','reason','branch','edition'}
            uid=request['source'];chosen=request['ability_id'];allies=request['allies']
            if set(request)!=fields or key!=uid+'@'+str(request['target_id']) or not isinstance(request['reason'],str) or not request['reason'].strip():raise ValueError('exchange choice contains untrusted event facts')
            if not isinstance(allies,list) or any(not isinstance(x,str) or not x for x in allies) or len(allies)!=len(set(allies)):raise ValueError('exchange choice requires explicit distinct recipient identities')
            if uid==RECEIVER:
                if request['branch'] not in ('receive','bequeath') or request['edition'] is not None or len(allies)!=(1 if request['branch']=='bequeath' else 0):raise ValueError('Receiver branch selection shape differs from source')
            elif request['branch']!='copy' or allies or (uid==MUMMY and request['edition'] not in ('core','playtest')) or (uid==ENTRAIN and request['edition'] is not None):raise ValueError('exchange source choice shape differs from contract')
            if chosen is None:
                if uid!=MUMMY or request['edition']!='core':raise ValueError('one selected exchange ability required')
            elif not isinstance(chosen,str) or A.ability_id(engine.r,chosen)!=chosen:raise ValueError('canonical selected exchange ability required')
        sources=actor.spec.get(G.KEY,{}).get('sources',{})
        live={key:row for key,row in sources.items() if TAG in row}
        timer_rows=[row for row in TIME.records(actor) if TAG in row]
        timers={row['grant_source']:row for row in timer_rows}
        if len(timers)!=len(timer_rows):raise ValueError('duplicate ability exchange lifetime record')
        for key,row in live.items():
            if row[TAG]=='aura':
                item=auras.get((actor.entity_id,key))
                fields={'kind','grants','owner_id','rule_id','lifetime',TAG,'ability_operation','gas_block'}
                if set(row)!=fields or row['kind']!='effect' or row['grants'] or row['rule_id']!=GAS or row['lifetime']!='source_aura' or item is None or row.get('owner_id')!=item[0].entity_id or row.get('ability_operation')!=item[1] or row.get('gas_block') is not True:raise ValueError('Gas aura lacks exact actual active source and observed adjacency')
                continue
            app=expected.get((actor.entity_id,key))
            if app is None or row[TAG]!=app['id'] or index.get(app['owner'].entity_id) is not app['owner'] or index.get(app['recipient'].entity_id) is not actor:raise ValueError('ability exchange lacks actual producer provenance')
            fields={'kind','grants','owner_id','rule_id','lifetime',TAG,'edition','ability_operation','gas_block'}
            if set(row)!=fields or row['kind']!='effect' or row['grants'] or row['lifetime']!='ability_exchange':raise ValueError('ability exchange has unreviewed additional grants or lifetime')
            for uid,components in app['components'].items():
                if components!=list(A.component_definitions(engine.r,uid)):raise ValueError('ability exchange component contract changed')
            operation=_defensive_operation(engine,actor) if app['source']==GAS else app['operation']
            if row.get('ability_operation')!=operation or row.get('owner_id')!=app['owner'].entity_id or row.get('rule_id')!=app['source'] or row.get('edition')!=app['edition'] or row.get('gas_block')!=(app['source']==GAS):raise ValueError('ability exchange source-owned contribution mismatch')
            record=timers.pop(key,None)
            if record is None or {k:v for k,v in record.items() if k not in ('owned_statuses','installing',LIVE_PROOF)}!=_timing(app) or record.get('owned_statuses') or record.get('installing') is not False:raise ValueError('ability exchange exact lifetime required')
        if timers:raise ValueError('ability exchange timer lacks its owned contribution')
        if live and actor.abilities!=G.effective(actor,'abilities'):raise ValueError('ability exchange projection mismatch')
    live_aura={(c.entity_id,k) for c in index.values() for k,r in c.spec.get(G.KEY,{}).get('sources',{}).items() if r.get(TAG)=='aura'}
    if live_aura!=set(auras):raise ValueError('Gas aura boundary was not reconciled')
    return True
