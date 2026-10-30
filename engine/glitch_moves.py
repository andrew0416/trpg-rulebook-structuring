"""Printed Error Moves; their native consumers do not require a teaching class."""
from copy import deepcopy
import csv
import io
import combat_timing as TIME
import effect_contracts as CONTRACTS
import world_entities as W

ACCESS='move/액세스-거부'; SHOCK='move/폴리곤-쇼크'; BLUE='move/블루-스크린'
DRAIN='move/데이터-드레인'; REND='move/대규모-할퀴기'; WAVE='move/방해-웨이브'
PULSE='move/버그-파동'; STRIKE='move/버그-스트라이크'; PAIN='move/고통-교환'; TELE='move/순간이동-충격'
ROWS={mid:949+i for i,mid in enumerate((ACCESS,SHOCK,BLUE,DRAIN,REND,WAVE,PULSE,STRIKE,PAIN,TELE))}
BOOK={BLUE:107,DRAIN:109,REND:111,WAVE:113,PULSE:113,STRIKE:115,PAIN:117,TELE:119}
CSV={'file':'input/db/moves.csv','sha256':'ab83f872e5eca67a41db7d126b842f0165437e0fa70bb77ddad832a0b7396c93'}
SUPPLEMENT={'file':'input/supp-polygon.md','sha256':'99c41c5de006f3cc0e5d57f1f3e498aa019c557d36f21e938f777b25be253f0e'}
VERSIONS=('glitch-csv','glitch-supplement')
STATS=('atk','def','spa','spd','spe')


def supports_version(rules,mid):
    if mid not in ROWS:return False
    version=rules.ruleset.unit_versions.get(mid)
    if version not in (None,*VERSIONS):raise ValueError('explicit reviewed Error Move edition required')
    if version=='glitch-supplement' and mid not in BOOK:raise ValueError('this Error Move has no printed supplement definition')
    return True


def selected(rules,mid):
    if mid not in ROWS or rules.selection.require_supported_version(mid,True)!=mid:raise ValueError('exact Error Move identity required')
    supports_version(rules,mid)
    from source_context import verified_source
    content=verified_source(rules,CSV,label='Error Move CSV')
    record=list(csv.reader(io.StringIO(content.decode('utf-8-sig'),newline='')))[ROWS[mid]-1]
    raw=rules.moves[mid]
    if (raw.get('_source',{}).get('record_span')!=[ROWS[mid]]*2 or raw['name']!=record[0]
            or raw['effect'].replace('\r\n','\n')!=record[7].replace('\r\n','\n')
            or raw['frequency']!=record[4] or raw['range']!=record[6]):
        raise ValueError('Error Move selected catalog differs from its actual CSV record')
    edition=rules.ruleset.unit_versions.get(mid) or 'glitch-csv'
    if edition=='glitch-supplement':
        lines=verified_source(rules,SUPPLEMENT,label='Error Move supplement').decode('utf-8-sig').splitlines()
        if raw['name']+':' not in lines[BOOK[mid]-1]:raise ValueError('exact supplement Move paragraph required')
    return edition


def definition(rules,move):
    mid=move['id']
    if mid not in ROWS:return move
    edition=selected(rules,mid);result=deepcopy(move)
    if edition=='glitch-supplement':
        changes={DRAIN:{'damage_base':10},REND:{'frequency':'임의'},PULSE:{'damage_base':8,'range':'6, 대상 1','keywords':[]},STRIKE:{'damage_base':8}}
        result.update(changes.get(mid,{}))
    result['_glitch_move_source']={'edition':edition,'record':ROWS[mid],**({'line':BOOK[mid]} if edition=='glitch-supplement' else {})}
    return result


def declaration(rules,mid):
    return {'type':'glitch_move','move_id':mid,'edition':selected(rules,mid),'target':'target'}


def mechanics(rules,mid,mm):
    if mid not in ROWS:return mm
    return {'effects_exec':[declaration(rules,mid)]}


def after_all(rules,move,effect):
    return bool(move and move.get('id') in (PAIN,TELE) and effect==declaration(rules,move['id']))


def preflight(e,a,t,effect,source):
    if source not in ROWS or effect!=declaration(e.r,source):raise ValueError('exact selected Error Move effect required')
    W.require_actors(e,a,t)
    if source in (ACCESS,SHOCK):
        if not e.encounter_active:raise ValueError('one-round Error Move requires an actual encounter')
        TIME.current(e)
    if source==TELE and not isinstance(a.spec.get(TELE_DIRECTION),dict):raise ValueError('Teleport Crash requires an explicit declared direction before use')
    if source==PAIN:_pain_plan(e,t)   # refuse unowned status histories before any cost


def access_rows(actor):
    return [row for row in TIME.records(actor) if row.get('glitch_move',{}).get('source')==ACCESS]


def _timed(e,a,t,effect,ctx,statuses):
    import trainer_feature_acquisition as T
    source=ctx['source_id'];count=TIME.current(e)
    proof={'source':source,'actor_id':a.entity_id,'target_id':t.entity_id,'round':e.round_no,'count':count,'occurrence':ctx['effect_occurrence']}
    proof['integrity']=T._digest('glitch-move-duration/v1',proof)
    proof['receipt']=ctx['effect_receipt']
    TIME.install(e,t,{'source':source,'effect_contract':True,'encounter_end':True,'count_deadline':(e.round_no+1,count),'statuses':statuses,'glitch_move':proof})


def validate_world(e,index):
    import trainer_feature_acquisition as T
    for target in index.values():
        for row in TIME.records(target):
            proof=row.get('glitch_move')
            if proof is None:continue
            if (set(proof)!={'source','actor_id','target_id','round','count','occurrence','integrity','receipt'}
                    or proof['source'] not in (ACCESS,SHOCK) or proof['actor_id'] not in index or proof['target_id']!=target.entity_id):raise ValueError('actual timed Error Move participants required')
            facts={k:v for k,v in proof.items() if k not in ('integrity','receipt')}
            if proof['integrity']!=T._digest('glitch-move-duration/v1',facts):raise ValueError('timed Error Move application changed')
            source=proof['source'];effect=declaration(e.r,source)
            CONTRACTS.validate_receipt(e,proof['receipt'],source,proof['occurrence'],index[proof['actor_id']],target,effect)
            if (row.get('source')!=source or row.get('effect_contract') is not True or row.get('encounter_end') is not True
                    or tuple(row.get('count_deadline',()))!=(proof['round']+1,proof['count'])
                    or row.get('statuses')!=(['둔화'] if source==ACCESS else ['실명','취약'])):raise ValueError('timed Error Move lifetime changed')


def _disable(e,a,t,source,*,single=False):
    import condition_instances as CONDITIONS
    mid=t.last_move
    if mid is None:return
    e.r.move(mid)
    if single:
        for row in list(CONDITIONS.records(t,'사슬묶기')):
            if row['source']==source and row['effect']['move_id']!=mid:CONDITIONS.end(e,t,row,{'kind':'condition_cure','condition':'사슬묶기'})
    e.apply_status(t,'사슬묶기',source=source,parameters={'move_id':mid},applied_by=a)


def resolve(e,a,t,effect,ctx):
    source=ctx['source_id'];preflight(e,a,t,effect,source)
    CONTRACTS.validate_receipt(e,ctx.get('effect_receipt'),source,ctx.get('effect_occurrence'),a,t,effect)
    if source in (PAIN,TELE):
        import move_completion as COMPLETE
        if not COMPLETE.authorized(e,ctx):raise ValueError('actual all-target Error Move completion required')
        row=getattr(e,COMPLETE.KEY)[ctx['move_completion']]
        if row['move_id']!=source or row['actor'] is not a:raise ValueError('Error Move completion identity changed')
        return pain_swap(e,a,row,ctx) if source==PAIN else tele_crash(e,a,row,ctx)
    frame=__import__('attack_damage_history').native_recipient(e,a,t,ctx)
    if frame is None:raise ValueError('actual native Error Move hit required')
    if source==ACCESS:return _timed(e,a,t,effect,ctx,['둔화'])
    if source==SHOCK:return _timed(e,a,t,effect,ctx,['실명','취약'])
    if source==BLUE:return _disable(e,a,t,source)
    edition=effect['edition'];natural=ctx.get('nat')
    threshold={DRAIN:19 if edition=='glitch-supplement' else 17,REND:17,PULSE:19 if edition=='glitch-supplement' else 18,STRIKE:18 if edition=='glitch-supplement' else 19}.get(source)
    if threshold is not None:
        if type(natural)is not int or not 1<=natural<=20:raise ValueError('actual native accuracy face required')
        if natural<threshold:return None
    if source in (DRAIN,STRIKE):
        e.apply_status(t,'억압',source=source,applied_by=a)   # a truthy handler return would read as an unsupported execution note
        return None
    if source==PULSE:return _disable(e,a,t,source,single=edition=='glitch-csv')
    if source in (REND,WAVE):
        import effects as FX
        selected=e.rng.sample(STATS,2 if source==WAVE else 1)
        e._effect_dispatch_receipts[ctx['effect_receipt']]['glitch_random_stats']=selected
        FX.apply_stage_changes(e,a,t,{stat:-1 for stat in selected},source_id=source,context=ctx)
        return None
    raise ValueError('unknown selected Error Move consumer')


# ---------------------------------------------------------------------------
# Composition additions (2026-10-30): the author's module ended at resolve()
# and referenced selected_targets, pain_swap and tele_crash without defining
# them. The additions below keep the engine hook safe for every other Move and
# implement the two completion consumers with explicit, pre-cost refusals for
# compositions this source does not yet own. Nothing here claims execution.
# ---------------------------------------------------------------------------

TELE_DIRECTION='tele_crash_direction'
PAIN_PLAIN=('화상','얼음','마비','독','혼란','난동')      # plain presence flags without an owning record
PAIN_INSTANCE=('사슬묶기','헤롱헤롱','풀죽음','억압')     # condition_instances rows re-granted with their parameters


def selected_targets(e,attacker,move,candidates,primary):
    """Pain Swap: the user names up to two actual distinct recipients (printed 6m, 대상 2)."""
    if move.get('id')!=PAIN:return None
    import body_state as BODY,body_modes as MODES,setup_move_state as SETUP,marsupial_state as MARSUPIAL
    selected=[t for t in candidates if t is not attacker]
    if not selected or selected[0] is not primary or len(selected)>2:
        raise ValueError('Pain Swap requires its actual primary and at most two named recipients')
    if len({id(t) for t in selected})!=len(selected):raise ValueError('distinct actual Pain Swap recipients required')
    W.require_actors(e,attacker,*selected)
    for t in selected:
        if (t.fainted or t.captured or not MARSUPIAL.target_present(t,engine=e) or not MODES.target_visible(e,attacker,t)
                or not SETUP.targetable(t,engine=e,attacker=attacker,move=move)):
            raise ValueError('every named Pain Swap recipient must be an actual eligible target')
        if e.grid is not None and not BODY.in_range(e,attacker,t,6,move=move):
            raise ValueError('Pain Swap recipients must be within the printed six metres')
        _pain_plan(e,t)   # every named recipient's status history must be transferable before any cost
    return selected


def declare_tele_crash(e,actor,direction,*,reason):
    """The source does not say who picks the direction; record one explicit choice before use."""
    import state_grants as G
    W.require_actors(e,actor);G._text(reason,'actual Teleport Crash direction reason')
    if (not isinstance(direction,(list,tuple)) or len(direction)!=2 or any(type(x)is not int or x not in (-1,0,1) for x in direction)
            or tuple(direction)==(0,0)):raise ValueError('explicit unit Teleport Crash direction required')
    row={'direction':[int(direction[0]),int(direction[1])],'reason':reason}
    return G.transition(e,actor,lambda se,c:(c.spec.__setitem__(TELE_DIRECTION,dict(row)),deepcopy(row))[1])


def _pain_plan(e,target):
    """Per-condition transfer plan, or a refusal naming the owner this source lacks."""
    import status_sets as STATUS,condition_instances as CONDITIONS
    plan=[]
    for condition in STATUS.afflictions(target):
        rows=CONDITIONS.records(target,condition)
        legacy=CONDITIONS.legacy_sources(target,condition)
        if legacy:raise ValueError('Pain Swap cannot move a status owned by a timed effect record: '+condition)
        if condition in PAIN_INSTANCE:
            if len(rows)!=1 and condition!='사슬묶기':raise ValueError('Pain Swap needs one actual sourced instance: '+condition)
            for row in rows:
                effect=row['effect']
                if condition=='억압' and row.get('applied_round') is not None:
                    raise ValueError('Pain Swap cannot preserve an ordinary one-round Suppressed deadline; GM ruling required')
                plan.append({'condition':condition,'parameters':{'move_id':effect['move_id']} if condition=='사슬묶기' else None,
                             'applied_by_id':effect.get('beloved_id') if condition=='헤롱헤롱' else row.get(__import__('effect_instances').KEY,{}).get('applied_by_actor_id')})
        elif condition in PAIN_PLAIN:
            if rows:raise ValueError('Pain Swap cannot preserve a variant condition history: '+condition)
            plan.append({'condition':condition,'parameters':None,'applied_by_id':None})
        else:
            raise ValueError('Pain Swap has no reviewed transfer owner for this condition: '+condition)
    return plan


def _pain_apply(e,actor,target,plan,index):
    applied=[]
    for item in plan:
        beloved=index.get(item['applied_by_id']) if item['applied_by_id'] else None
        if item['condition']=='헤롱헤롱':
            if beloved is None or beloved is target:raise ValueError('Pain Swap cannot infatuate a recipient with itself; GM ruling required')
            result=e.apply_status(target,item['condition'],source=PAIN,applied_by=beloved)
        else:
            result=e.apply_status(target,item['condition'],source=PAIN,parameters=item['parameters'],applied_by=actor)
        applied.append({'condition':item['condition'],'applied':bool(result)})
    return applied


def pain_swap(e,actor,row,ctx):
    """Exchange the actual status afflictions of the two named recipients once, after both results."""
    import move_completion as COMPLETE
    receipt=e._effect_dispatch_receipts[ctx['effect_receipt']]
    if 'pain_swap' in receipt:return None   # second post-effect call for the same completion
    targets=list(row['targets'])
    if len(targets)!=2 or targets[0] is targets[1]:raise ValueError('Pain Swap needs exactly two actual distinct recipients')
    results=[COMPLETE.recipient_result(row,t) for t in targets]
    if not all(r and r['hit'] and not r.get('cancelled') for r in results):
        receipt['pain_swap']={'swapped':False,'reason':'both recipients must be actually hit'};return None
    index=W.actor_index(e)
    plans=[_pain_plan(e,t) for t in targets]
    for t,plan in zip(targets,plans):
        for item in plan:e.cure_status(t,item['condition'])
    applied=[_pain_apply(e,actor,targets[0],plans[1],index),_pain_apply(e,actor,targets[1],plans[0],index)]
    receipt['pain_swap']={'swapped':True,'from':{t.entity_id:[x['condition'] for x in plan] for t,plan in zip(targets,plans)},
                          'applied':{targets[0].entity_id:applied[0],targets[1].entity_id:applied[1]}}
    return None


def _relocate(e,target,destination,*,event):
    """Instant placement with the same post-position owners gm.set_position runs; no GM record."""
    import actor_templates as TEMPLATES,survivalist_features as SURVIVAL,body_modes as BODY_MODES,effect_lifetime_policy as LIFETIMES
    if not TEMPLATES.multipart_can_place(e,target,tuple(destination)):raise ValueError('multipart Teleport Crash recipient needs a whole reposition ruling')
    target.pos=tuple(destination)
    SURVIVAL.position_changed(e,target,event=event)
    BODY_MODES.sync_shadows(e);LIFETIMES.reconcile(e)
    __import__('ability_exchange_contracts').refresh(e);__import__('ability_control_contracts').refresh(e)
    __import__('marksman').watch_state(e,target)


def tele_crash(e,actor,row,ctx):
    """After use, the actual recipient teleports 1d6+3 m in the declared direction (CSV r958 / supplement l119)."""
    import move_completion as COMPLETE,body_state as BODY,roll_pools as POOLS
    receipt=e._effect_dispatch_receipts[ctx['effect_receipt']]
    if 'tele_crash' in receipt:return None
    targets=list(row['targets'])
    if len(targets)!=1:raise ValueError('Teleport Crash needs its one actual recipient')
    target=targets[0];result=COMPLETE.recipient_result(row,target)
    choice=actor.spec.get(TELE_DIRECTION)
    if not isinstance(choice,dict) or 'direction' not in choice:raise ValueError('Teleport Crash requires an explicit declared direction before use')
    direction=tuple(choice['direction'])
    if not (result and result['hit'] and not result.get('cancelled')):
        receipt['tele_crash']={'teleported':False,'reason':'recipient was not actually hit'};actor.spec.pop(TELE_DIRECTION,None);return None
    if e.grid is None:raise ValueError('Teleport Crash displacement needs a mapped scene')
    if not target.on_field or target.captured:raise ValueError('Teleport Crash recipient is not an actual field body')
    face=POOLS.die(e.rng,6);distance=face+3
    origin=tuple(target.pos);destination=(origin[0]+direction[0]*distance,origin[1]+direction[1]*distance)
    if not e.grid.inside(destination) or not BODY.can_place(e,target,destination,origin=None):
        # Not invented: the paid Move stands, nobody moves, and the GM adjudicates the landing (a pending decision, not an exception object in a receipt).
        actor.spec.pop(TELE_DIRECTION,None)
        receipt['tele_crash']={'teleported':False,'roll':face,'distance':distance,'direction':list(direction),'from':list(origin),'to':list(destination),'reason':'destination outside the map or blocked; GM must adjudicate the landing'}
        return __import__('common_checks').PendingDecision('Teleport Crash landing is outside the map or blocked; GM must adjudicate the landing')
    _relocate(e,target,destination,event='Teleport Crash')
    actor.spec.pop(TELE_DIRECTION,None)
    receipt['tele_crash']={'teleported':True,'roll':face,'distance':distance,'direction':list(direction),'from':list(origin),'to':list(destination),'reason':choice['reason']}
    e.log('    '+target.name+': 순간이동 충격 '+str(distance)+'m → '+str(destination),TELE)
    return None
