"""C09-087: actual expert burn, native Focus, source-owned five-minute loss.

English p302 supplies <= and both-required eligibility; Korean source remains
unchanged. No action cost is stated. This boundary records an identified GM
observation of the real burn, then resumes the same native compound checks.
"""
from copy import deepcopy
import cleanse_tags as TAG
import common_checks as C
import skill_modifiers as S
import skill_feature_actions as SKILLS
import state_grants as G
import world_entities as W
import invisibility_state as INVISIBILITY
import elapsed_time as TIME

KEY='cleanse_tag_burn'
CLAUSE='C09-087'
DURATION=300
INVISIBLE=('투명','Invisibility')
PHASING=('Phasing','통과','페이징')
LOST=list(INVISIBLE+PHASING)
POLICY={'eligibility':'both_required','focus':'not_exceed_power','active_invisibility':'end_and_native_cooldown'}


def _names(values):return {S.key(value.removeprefix('capability/')) for value in values}


def _eligible(values):
    names=_names(values)
    return bool(names&_names(INVISIBLE)) and bool(names&_names(PHASING))


def _range(engine,actor,target,reach):
    """Radial source text has no line-of-sight or wall exception."""
    import body_state as BODY
    a,b=W.location_of(actor),W.location_of(target)
    if a['kind']!='grid' or b['kind']!='grid' or a.get('map_id')!=b.get('map_id'):
        raise ValueError('observe actual Cleanse Tag range before burning')
    return min(max(abs(x[i]-y[i]) for i in (0,1)) for x in BODY.at_position(actor) for y in BODY.at_position(target))<=reach


def _options(instance_id,event_id,actor,options):
    options=deepcopy(options)
    if type(options)is not dict or set(options)-{'fixed','mods','penalty_count','fixed_penalties','helper_rank','helper_bonus','skill_context','skill_stunt','feature','feature_options'}:
        raise ValueError('native Focus options required; totals and caller roll IDs forbidden')
    token=TAG._hash([TAG.ITEM,CLAUSE,instance_id,event_id,actor.entity_id])
    options['roll_id']='cleanse-burn:'+token+':focus'
    return options


def _saved(options):return {k:v for k,v in options.items() if k!='feature_options'}


def _source_id(row,actor_id):return row['sequence_id']+':loss:'+actor_id


def _basis(row):
    return dict(source=TAG.ITEM,clause=CLAUSE,instance_id=row['instance_id'],event_id=row['event_id'],
        intent_sha256=TAG._hash({k:v for k,v in row.items() if k not in ('sha256','status','resolved_at','resolved_unknown_index','targets')}),
        targets_sha256=TAG._hash({uid:{k:v for k,v in target.items() if k not in ('result','elapsed_observations')} for uid,target in row['targets'].items()}))


def _access(engine,actor,obj):
    W.require_physical_access(obj)
    if obj.get('equipped_by') or obj.get('carrier_id') not in (None,actor.entity_id):
        raise ValueError('actual user must physically access this unequipped tag')
    barrier=obj.get(TAG.BARRIER)
    if barrier and barrier['observations'][barrier['current']]['attached']:
        raise ValueError('remove actual surface attachment before burning')
    if not obj.get('carrier_id'):
        distance=W.distance_known(actor,obj)
        if distance is None or distance>1:raise ValueError('actual tag must be within physical reach of the burner')


def burn(engine,actor,instance_id,*,event_id,reason,checks=None):
    """Observe one actual burn; checks maps every eligible actor ID to options.

    Validate every initial declaration before the real tag is destroyed or dice
    are exposed. Once burned, the same receipt survives later observed-choice
    errors and resumes without requiring the original to remain usable.
    """
    W.require_actors(engine,actor);TAG._text(instance_id);TAG._text(event_id);TAG._text(reason)
    TAG.definition(engine.r)
    TAG.PRODUCTS.validate_world(engine,W.actor_index(engine))
    validate_world(engine,W.actor_index(engine))
    obj=getattr(engine,'_physical_objects',{}).get(instance_id)
    if obj is None:raise ValueError('actual original Cleanse Tag required')
    old=obj.get(KEY)
    if old is not None:
        if old['event_id']!=event_id or old['actor_id']!=actor.entity_id or old['reason']!=reason:
            raise ValueError('resume the same observed Cleanse Tag burn')
        if old['status']!='pending':raise ValueError('same tag has already been burned')
        targets=[W.actor_index(engine)[uid] for uid in old['targets']]
    else:
        TAG.level(engine,instance_id);_access(engine,actor,obj)
        rank=S.effective_rank(engine.r,actor,'오컬트학')
        if rank<5:raise ValueError('current Expert Occult Education required')
        if any(other.get(KEY,{}).get('event_id')==event_id for other in getattr(engine,'_physical_objects',{}).values()):
            raise ValueError('actual burn observation identity already used')
        targets=[]
        for c in W.actor_index(engine).values():
            if c.kind not in ('trainer','pokemon'):continue
            values=G.effective_capabilities(c)
            if _eligible(values) and _range(engine,actor,c,30):targets.append(c)
        targets.sort(key=lambda c:c.entity_id)
    checks={} if checks is None else checks
    if type(checks)is not dict:raise ValueError('per-actor native Focus declarations required')
    expected={c.entity_id for c in targets}
    if set(checks)-expected:raise ValueError('only actual eligible targets make this Focus check')
    if set(checks)!=expected:return C.PendingDecision('actual Focus declarations required for every Cleanse Tag target')
    plans=[];saved={}
    for c in targets:
        options=_options(instance_id,event_id,c,checks[c.entity_id]);saved[c.entity_id]=_saved(options)
        if old is not None and saved[c.entity_id]!=old['targets'][c.entity_id]['skill_options']:
            raise ValueError('cannot change observed Cleanse Tag Focus declaration')
        SKILLS.prepared_for_sequence(engine,c,'집중',options)
        # A loss can only end an existing activation at an observed instant.
        INVISIBILITY.preflight_forced_end(engine,c)
        plans.append((c,'집중',options))
    if old is None:
        token=TAG._hash([TAG.ITEM,CLAUSE,instance_id,event_id])
        row=dict(source=TAG.ITEM,clause=CLAUSE,instance_id=instance_id,event_id=event_id,
            actor_id=actor.entity_id,reason=reason,rank_at_burn=rank,policy=deepcopy(POLICY),
            original=deepcopy(obj[TAG.PROFILE]),power=obj[TAG.PROFILE]['level'],
            sequence_id='cleanse-burn:'+token,status='pending',burned_at=engine.elapsed_seconds,
            resolved_at=None,resolved_unknown_index=None,targets={c.entity_id:dict(kind=c.kind,location=deepcopy(W.location_of(c)),
                capabilities=G.effective_capabilities(c),skill_options=saved[c.entity_id],result=None) for c in targets})
        TAG._seal(row)
        def begin(e,user):
            body=e._physical_objects[instance_id]
            body[KEY]=deepcopy(row)
            if body.get('carrier_id'):
                import capability_actions as CAP
                remaining=[x for x in user.spec['_carried_load']['objects'] if x['id']!=instance_id]
                CAP.set_carried(e,user,remaining,'actual held Cleanse Tag burned')
            W.finish_physical_use(e,body,'destroyed',dict(source=TAG.ITEM,by_actor_id=user.entity_id,
                at=e.elapsed_seconds,cleanse_burn_event_id=event_id))
            e.gm._rec('Cleanse Tag actual burn',None,body[KEY],reason,user)
            return deepcopy(body[KEY])
        old=G.transition(engine,actor,begin)
    sequence_id=old['sequence_id']
    basis=_basis(old)
    def resolve(rolls):
        def apply(e,user,*subjects):
            row=e._physical_objects[instance_id][KEY];index=W.actor_index(e)
            for uid,roll in zip(row['targets'],rolls):
                c=index[uid];lost=roll.total<=row['power']
                row['targets'][uid]['result']=dict(total=roll.total,lost=lost)
                if lost:
                    INVISIBILITY.force_end(e,c,reason='actual Cleanse Tag burn '+event_id)
                    G.capability_loss(e,c,_source_id(row,uid),LOST,rule_id=TAG.ITEM,receipt=sequence_id,duration=DURATION)
            row.update(status='complete',resolved_at=e.elapsed_seconds,resolved_unknown_index=len(e.unresolved_time_intervals));TAG._seal(row)
            validate_world(e,index)
            e.gm._rec('Cleanse Tag Focus resolution',None,row,reason,user)
            return deepcopy(row)
        return G.transition(engine,actor,apply,participants=tuple(targets))
    return SKILLS.sequence(engine,sequence_id,basis,plans,resolve)


def observe_loss_elapsed(engine,actor,source_id,seconds,*,reason):
    W.require_actors(engine,actor);TAG._text(reason)
    validate_world(engine,W.actor_index(engine))
    row=G.capability_losses(actor).get(source_id)
    if row is None or row['rule_id']!=TAG.ITEM:raise ValueError('actual Cleanse Tag loss required')
    low,high=TIME.bounds(engine,row['clock_anchor'],row['unknown_index'],row['elapsed_base'],label='Cleanse loss clock')
    C.integer(seconds,'observed Cleanse loss time',low,high)
    def apply(e,c):
        value=G.capability_losses(c)[source_id];old=deepcopy(value)
        value.update(clock_anchor=e.elapsed_seconds,unknown_index=len(e.unresolved_time_intervals),elapsed_base=seconds,elapsed_bounds=[seconds,seconds])
        body=next(obj for obj in e._physical_objects.values() if obj.get(KEY,{}).get('sequence_id')==value['receipt'])
        burn=body[KEY];burn['targets'][c.entity_id].setdefault('elapsed_observations',[]).append(dict(
            clock_anchor=e.elapsed_seconds,unknown_index=len(e.unresolved_time_intervals),elapsed_base=seconds,reason=reason))
        TAG._seal(burn)
        e.gm._rec('Cleanse loss elapsed',old,value,reason,c)
        return [seconds,seconds]
    return G.transition(engine,actor,apply)


def validate_world(engine,index=None):
    index=W.actor_index(engine) if index is None else index
    G.validate_capability_losses(engine,index)
    found=set();events=set()
    for uid,obj in getattr(engine,'_physical_objects',{}).items():
        row=obj.get(KEY)
        if row is None:continue
        TAG.definition(engine.r);TAG._verified(row)
        if set(row)!={'source','clause','instance_id','event_id','actor_id','reason','rank_at_burn','policy','original','power','sequence_id','status','burned_at','resolved_at','resolved_unknown_index','targets','sha256'}:
            raise ValueError('original Cleanse burn receipt fields required')
        if (row['source'],row['clause'],row['instance_id'],row['policy'],row['original'],row['power'])!=(TAG.ITEM,CLAUSE,uid,POLICY,obj.get(TAG.PROFILE),obj.get(TAG.PROFILE,{}).get('level')):
            raise ValueError('Cleanse burn original source or Power changed')
        TAG._text(row['event_id']);TAG._text(row['reason']);C.integer(row['rank_at_burn'],'historical expert rank',5,6)
        if row['event_id'] in events or row['actor_id'] not in index:raise ValueError('one actual burn event and user required')
        events.add(row['event_id'])
        expected_sequence='cleanse-burn:'+TAG._hash([TAG.ITEM,CLAUSE,uid,row['event_id']])
        if row['sequence_id']!=expected_sequence:raise ValueError('original burn sequence identity changed')
        C.integer(row['burned_at'],'actual burn time',0,engine.elapsed_seconds)
        if row['status'] not in ('pending','complete'):raise ValueError('native burn lifecycle required')
        if row['status']=='pending' and (row['resolved_at']is not None or row['resolved_unknown_index']is not None):raise ValueError('unfinished burn has no resolved time')
        if row['status']=='complete':
            C.integer(row['resolved_at'],'actual Focus resolution time',row['burned_at'],engine.elapsed_seconds)
            C.integer(row['resolved_unknown_index'],'actual Focus resolution clock',0,len(engine.unresolved_time_intervals))
        if obj.get('destroyed')!=dict(source=TAG.ITEM,by_actor_id=row['actor_id'],at=row['burned_at'],cleanse_burn_event_id=row['event_id']):
            raise ValueError('actual original burned tag terminal evidence required')
        requests=[]
        for actor_id,target in row['targets'].items():
            c=index.get(actor_id)
            if c is None or target['kind'] not in ('trainer','pokemon') or not _eligible(target['capabilities']):raise ValueError('original both-capability target required')
            if set(target)-{'kind','location','capabilities','skill_options','result','elapsed_observations'}:raise ValueError('original Focus target fields required')
            options=target['skill_options'];expected=_options(uid,row['event_id'],c,{k:v for k,v in options.items() if k!='roll_id'})
            if options!=expected:raise ValueError('original native Focus identity changed')
            event=SKILLS.event(engine,c,options['roll_id'])
            request=SKILLS._request(engine,c,'집중',options)
            requests.append((c,request,options.get('feature'),options['roll_id']))
            if event is not None and (event.request!=request or event.skill!=S.skill_id(engine.r.skill_policy,'집중')):
                raise ValueError('actual original native Focus event required')
            source_id=_source_id(row,actor_id);loss=G.capability_losses(c).get(source_id)
            if row['status']=='pending':
                if target['result']is not None or loss is not None:raise ValueError('unfinished Focus cannot own a result or loss')
                continue
            if event is None or event.state!='final' or target['result']!=dict(total=event.final.total,lost=event.final.total<=row['power']):
                raise ValueError('Cleanse burn result differs from actual native Focus')
            if not target['result']['lost']:
                if loss is not None:raise ValueError('successful Focus cannot own capability loss')
                continue
            if loss is None or (loss['values'],loss['rule_id'],loss['receipt'],loss['duration'])!=(LOST,TAG.ITEM,row['sequence_id'],DURATION):
                raise ValueError('failed Focus must own the exact two-capability loss')
            initial=dict(clock_anchor=row['resolved_at'],unknown_index=row['resolved_unknown_index'],elapsed_base=0)
            observations=target.get('elapsed_observations',[])
            if observations:
                previous=initial
                for observation in observations:
                    if set(observation)!={'clock_anchor','unknown_index','elapsed_base','reason'}:raise ValueError('actual elapsed observation receipt required')
                    TAG._text(observation['reason'])
                    from types import SimpleNamespace
                    historical=SimpleNamespace(elapsed_seconds=observation['clock_anchor'],unresolved_time_intervals=engine.unresolved_time_intervals[:observation['unknown_index']])
                    low,high=TIME.bounds(historical,previous['clock_anchor'],previous['unknown_index'],previous['elapsed_base'],label='original observed loss time')
                    C.integer(observation['elapsed_base'],'actual observed loss time',low,high)
                    TIME.bounds(engine,observation['clock_anchor'],observation['unknown_index'],observation['elapsed_base'],label='observed Cleanse loss clock')
                    previous=observation
                initial=observations[-1]
            if any(loss[k]!=initial[k] for k in ('clock_anchor','unknown_index','elapsed_base')):
                raise ValueError('capability loss no longer follows its actual native start or observation')
            found.add((actor_id,source_id))
        run=getattr(engine,'_skill_sequences',{}).get(row['sequence_id'])
        if run is not None:
            if run['basis']!=_basis(row) or run['requests']!=tuple(requests):raise ValueError('burn must use the original compound native Focus sequence')
        elif row['status']=='complete' and row['targets']:raise ValueError('actual burn Focus sequence missing')
    for c in index.values():
        for source_id,loss in G.capability_losses(c).items():
            if loss['rule_id']==TAG.ITEM and (c.entity_id,source_id) not in found:raise ValueError('orphaned Cleanse Tag capability loss')
    return True
