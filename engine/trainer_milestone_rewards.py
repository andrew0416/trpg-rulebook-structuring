"""Source-bound trainer milestone choices and permanent stat reward allocation.

Ordinary points require recorded attained levels; special choices require an
observed threshold. Choice spending for Edges/General Features is
not inferred here; their qualified acquisition consumer remains separate.
"""
from copy import deepcopy
import resolution_transaction as TX

KEY='trainer_milestone_rewards'
STATS={'hp','atk','def','spa','spd','spe'}
# Allocation scope 0 is reserved for ordinary per-level points, never a milestone.
OPTIONS={5:('stats','general_feat'),10:('stats','edges'),20:('stats','edges'),
         30:('stats','edges','general_feat'),40:('stats','edges','general_feat')}
END={5:10,10:20,20:30,30:40,40:50}


def observed(actor):
    thresholds={};levels=set()
    for event_id,event in actor.spec.get('trainer_progression_events',{}).items():
        result=event['result'];attained=result['attained_levels'];levels.update(attained)
        if 'special_reward_levels' not in result:continue
        expected=[level for level in attained if level in OPTIONS]
        if result['special_reward_levels']!=expected:raise ValueError('special reward thresholds disagree with growth event')
        for level in expected:
            if str(level) in thresholds:raise ValueError('special trainer milestone was attained twice')
            thresholds[str(level)]=event_id
    return thresholds,levels


def _earned(level,levels):
    return (2 if level==5 else 0)+sum(level<n<=END[level] and n%2==0 for n in levels)


def ordinary_earned(actor):
    levels=set()
    for event in actor.spec.get('trainer_progression_events',{}).values():
        result=event['result']
        if 'stat_reward_levels' not in result:continue
        awarded=result['stat_reward_levels']
        if awarded!=result['attained_levels'] or levels.intersection(awarded):
            raise ValueError('ordinary stat reward levels disagree with unique growth events')
        levels.update(awarded)
    return len(levels)


def _amounts(stats,ordinary=False):
    allowed=STATS if ordinary else {'atk','spa'}
    if type(stats) is not dict or not stats or not set(stats)<=allowed or (not ordinary and set(stats)!=allowed) or any(type(v) is not int or v<0 for v in stats.values()) or sum(stats.values())<=0:
        raise ValueError('positive allocation within allowed stats required')
    return sum(stats.values())


def validate(actor):
    thresholds,levels=observed(actor);ordinary=ordinary_earned(actor);ledger=actor.spec.get(KEY)
    if ledger is None:return
    if actor.kind!='trainer' or type(ledger) is not dict or set(ledger)!={'version','choices','allocations'} or type(ledger['version']) is not int or ledger['version']!=1:
        raise ValueError('invalid trainer milestone reward ledger')
    choices=ledger['choices'];allocations=ledger['allocations']
    if type(choices) is not dict or type(allocations) is not dict:raise ValueError('milestone choices and allocations must be mappings')
    for key,row in choices.items():
        if key not in thresholds or type(row) is not dict or set(row)!={'event_id','option','reason'}:
            raise ValueError('observed milestone choice required')
        if row['event_id']!=thresholds[key] or row['option'] not in OPTIONS[int(key)] or type(row['reason']) is not str or not row['reason'].strip():
            raise ValueError('invalid milestone choice provenance')
    spent={key:0 for key in choices};spent['0']=0
    for request_id,row in allocations.items():
        if type(request_id) is not str or not request_id.strip() or type(row) is not dict or set(row)!={'intent','request','result'}:
            raise ValueError('milestone allocation request required')
        request=row['request'];result=row['result']
        if type(request) is not dict or set(request)!={'level','stats','reason'} or TX.request_fingerprint(request)!=row['intent']:
            raise ValueError('milestone allocation request changed')
        key=str(request['level']);stats=request['stats']
        if type(request['level']) is not int or (key!='0' and (key not in choices or choices[key]['option']!='stats')):raise ValueError('chosen stat milestone required')
        _amounts(stats,ordinary=key=='0')
        if type(request['reason']) is not str or not request['reason'].strip():raise ValueError('allocation reason required')
        if type(result) is not dict or set(result)!={'request_id','level','stats','patch'} or result['request_id']!=request_id or result['level']!=request['level'] or result['stats']!=stats:
            raise ValueError('milestone allocation result changed')
        patch=result['patch']
        from trainer_entitlements import SOURCE
        if type(patch) is not dict or patch.get('entity_id')!=actor.entity_id or patch.get('source')!=SOURCE or patch.get('reason')!=request['reason']:
            raise ValueError('native milestone stat patch provenance required')
        before=patch.get('before',{}).get('stats');after=patch.get('after',{}).get('stats')
        if type(before) is not dict or type(after) is not dict or set(before)!=set(after) or set(before)!={'hp','atk','def','spa','spd','spe'}:raise ValueError('native stat patch evidence required')
        if any(type(v) is not int for v in [*before.values(),*after.values()]) or any(after[stat]-before[stat]!=stats.get(stat,0) for stat in before):
            raise ValueError('milestone allocation disagrees with native stat change')
        spent[key]+=sum(stats.values())
    if any(amount>(ordinary if key=='0' else _earned(int(key),levels)) for key,amount in spent.items()):raise ValueError('milestone allocation exceeds earned points')
    seen=set()
    for request_id,row in actor.spec.get('trainer_milestone_acquisitions',{}).items():
        request=row.get('request',{});key=str(request.get('level'))
        if key not in choices or choices[key]['option']!='general_feat' or key in seen or row.get('intent')!=TX.request_fingerprint(request):raise ValueError('one actual chosen General Feature milestone spend required')
        seen.add(key)
        result=row.get('result',{})
        if result.get('feature_id')!=request.get('feature') or result.get('request_id')!=request_id+'/acquisition':raise ValueError('milestone must consume its actual acquired Feature receipt')
        actual=__import__('trainer_feature_acquisition')._static_records(actor)
        if not any(record['static_acquisition']==result for _,record,_ in actual):raise ValueError('milestone acquired Feature receipt missing')


def acquire_general_feature(engine,actor,level,feature,*,request_id,selection=None,rank=None):
    """Spend one chosen General Feature bonus on a qualified real acquisition."""
    _admit(engine,actor)
    request={'level':level,'feature':feature,'selection':deepcopy(selection),'rank':rank}
    old=TX.replay_result(actor.spec.get('trainer_milestone_acquisitions',{}),request_id,request,fingerprint_field='intent')
    if old is not None:return old['result']
    choice=actor.spec.get(KEY,{}).get('choices',{}).get(str(level))
    if type(level)is not int or choice is None or choice['option']!='general_feat':raise ValueError('actual chosen General Feature milestone required')
    if any(row['request']['level']==level for row in actor.spec.get('trainer_milestone_acquisitions',{}).values()):raise ValueError('General Feature milestone already spent')
    unit=engine.r.selection.units.get(feature,{})
    regular=feature.startswith('feat/') and unit.get('source',{}).get('file')=='ch03-skills-edges-feats.md'
    if not regular and not __import__('hobbyist').counts_as_general(engine.r,feature):raise ValueError('this reward grants only a General Feature; Hobbyist is the printed Class exception')
    import state_grants as G,trainer_feature_acquisition as T
    def apply(e,a):
        result=T.acquire_static(e,a,feature,acquisition_request_id=request_id+'/acquisition',selection=selection,rank=rank)
        # Keep the immutable native receipt, not the transient status response.
        result={k:v for k,v in result.items() if k!='status'}
        a.spec.setdefault('trainer_milestone_acquisitions',{})[request_id]={'intent':TX.request_fingerprint(request),'request':deepcopy(request),'result':deepcopy(result)}
        return deepcopy(result)
    return G.transition(engine,actor,apply)


def _admit(engine,actor):
    import world_entities as W
    import trainer_entitlements as E
    if W.actor_index(engine).get(actor.entity_id) is not actor or actor.r is not engine.r or actor.kind!='trainer':raise ValueError('actual registered trainer required')
    E._source(engine.r);E.validate(actor);validate(actor)


def pending(engine,actor):
    _admit(engine,actor);thresholds,levels=observed(actor)
    ledger=actor.spec.get(KEY,{'choices':{},'allocations':{}});result=[]
    for key,event_id in thresholds.items():
        level=int(key);choice=ledger['choices'].get(key)
        row={'level':level,'event_id':event_id,'options':list(OPTIONS[level]),'choice':deepcopy(choice)}
        if choice and choice['option']=='stats':
            spent=sum(sum(r['request']['stats'].values()) for r in ledger['allocations'].values() if r['request']['level']==level)
            row.update(earned=_earned(level,levels),spent=spent,available=_earned(level,levels)-spent,allowed_stats=['atk','spa'])
        elif choice:
            row.update(reward_kind='edge' if choice['option']=='edges' else 'general_feat',count=2 if choice['option']=='edges' else 1,status='pending_qualified_choice')
        else:row['status']='pending_branch_choice'
        result.append(row)
    return result


def choose(engine,actor,level,option,*,reason):
    _admit(engine,actor);thresholds,_=observed(actor)
    if type(level) is not int or str(level) not in thresholds or option not in OPTIONS[level]:raise ValueError('observed milestone and allowed option required')
    if type(reason) is not str or not reason.strip():raise ValueError('milestone choice reason required')
    row={'event_id':thresholds[str(level)],'option':option,'reason':reason}
    old=actor.spec.get(KEY,{}).get('choices',{}).get(str(level))
    if old is not None:
        if old!=row:raise ValueError('milestone choice already recorded with different input')
        return deepcopy(old)
    import state_grants as G
    def apply(e,c):
        c.spec.setdefault(KEY,{'version':1,'choices':{},'allocations':{}})['choices'][str(level)]=deepcopy(row)
        validate(c);return deepcopy(row)
    return G.transition(engine,actor,apply)


def growth_points(engine,actor):
    _admit(engine,actor)
    earned=ordinary_earned(actor)
    spent=sum(sum(row['request']['stats'].values()) for row in actor.spec.get(KEY,{}).get('allocations',{}).values() if row['request']['level']==0)
    return {'earned':earned,'spent':spent,'available':earned-spent,'allowed_stats':sorted(STATS)}


def allocate_growth(engine,actor,stats,*,request_id,reason):
    return _allocate(engine,actor,0,stats,request_id=request_id,reason=reason)


def allocate(engine,actor,level,stats,*,request_id,reason):
    if type(level) is not int or level not in OPTIONS:raise ValueError('known special milestone level required')
    return _allocate(engine,actor,level,stats,request_id=request_id,reason=reason)


def _allocate(engine,actor,level,stats,*,request_id,reason):
    _admit(engine,actor)
    if type(level) is not int:raise ValueError('integer milestone level required')
    _amounts(stats,ordinary=level==0)
    if type(reason) is not str or not reason.strip():raise ValueError('allocation reason required')
    request={'level':level,'stats':stats,'reason':reason}
    replay=TX.replay_result(actor.spec.get(KEY,{}).get('allocations',{}),request_id,request,fingerprint_field='intent')
    if replay is not None:return replay['result']
    reward=growth_points(engine,actor) if level==0 else next((row for row in pending(engine,actor) if row['level']==level),{})
    if sum(stats.values())>reward.get('available',0):raise ValueError('insufficient chosen milestone stat points')
    import state_grants as G
    import state_fields as F
    import trainer_entitlements as E
    def apply(e,c):
        updated=deepcopy(c.spec['stats'])
        for stat,amount in stats.items():updated[stat]+=amount
        patch=F.base_patch(c,{'stats':updated},reason=reason,source=E.SOURCE)
        result={'request_id':request_id,'level':level,'stats':deepcopy(stats),'patch':patch}
        c.spec.setdefault(KEY,{'version':1,'choices':{},'allocations':{}})['allocations'][request_id]={'intent':TX.request_fingerprint(request),'request':deepcopy(request),'result':deepcopy(result)}
        validate(c);return deepcopy(result)
    return G.transition(engine,actor,apply)
