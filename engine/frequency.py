"""Frequency lifetimes. Moves and feats deliberately have different daily rules.
Sources: ch03:585, ch10:223-224, ch07:750/754.
EOT and Scene turn intervals clarified against PTU 1.05 core p337; see data/frequency-source-review.json.
"""
import re
from copy import deepcopy
import action_points as AP

FORFEIT_SOURCES=frozenset(('feat/힘의-전달','feat/싸움꾼의-유능함','feat/융통-명령'))

def parse(raw):
    # ch03:585 grants One Time Use to features. Its lifetime is not a day,
    # scene or session; native moves intentionally keep this kind unsupported.
    if isinstance(raw,dict) and raw.get('kind')=='one_time':
        uses=raw.get('uses',1)
        if type(uses) is not int or uses!=1:raise ValueError('One Time Use has exactly one lifetime activation')
        return 'one_time',1
    text=str(raw.get('raw','') if isinstance(raw,dict) else raw or '')
    if re.match(r'^(?:일회용|One[ -]Time(?: Use)?)(?:$|\s|[–—-])',text.strip(),re.I):return 'one_time',1
    if isinstance(raw,dict) and raw.get('kind') in ('scene','daily','turn','every_other_turn','at_will','static'):
        uses=raw.get('uses')
        uses=1 if uses is None else uses
        if type(uses) is not int or uses<1:raise ValueError('frequency cap must be a positive whole number')
        return raw['kind'],uses
    m=re.search(r'(장면|하루|일일)\s*(?:당)?\s*[x×]?\s*(\d+)?',text)
    if m:return ('scene' if m.group(1)=='장면' else 'daily'),int(m.group(2) or 1)
    if '턴1회' in text or '턴 1회' in text:return 'every_other_turn',1
    if not text or text.startswith(('임의','항상','자유')):return 'at_will',1
    return 'unknown',1

def validate(c):
    """Read-only shared quota state contract; restoration rules remain distinct."""
    def count(value,label):
        if type(value) is not int or value<0:raise ValueError(label+' must be a nonnegative whole number')
    def mapping(value,label):
        if not isinstance(value,dict):raise ValueError(label+' must be a mapping')
        for key in value:
            if not isinstance(key,str) or not key.strip():raise ValueError(label+' requires source IDs')
        return value
    uses=mapping(c.move_uses,'move usage')
    for value in uses.values():count(value,'move usage')
    if 'move_uses' in c.spec:
        saved=mapping(c.spec['move_uses'],'saved move usage')
        for value in saved.values():count(value,'saved move usage')
        if saved!=uses:raise ValueError('runtime and saved move usage disagree')
    for value in mapping(c.spec.get('daily_feat_uses',{}),'legacy daily usage').values():count(value,'legacy daily usage')
    st=c.spec.get('frequency_state')
    if st is None:
        if 'frequency_state' in c.spec:raise ValueError('frequency state must be a mapping')
        return
    if not isinstance(st,dict):raise ValueError('frequency state must be a mapping')
    for key in ('day','scene','turn'):count(st.get(key),'frequency '+key)
    basis=st.get('daily_basis','day')
    if basis not in ('day','session'):raise ValueError('unknown daily frequency basis')
    if basis=='session':count(st.get('session'),'frequency session')
    for row in [*mapping(st.get('moves'),'move occurrence ledger').values(),*mapping(st.get('restored_move_occurrences',{}),'restored actual Move occurrences').values()]:
        if not isinstance(row,dict):raise ValueError('move occurrence must be a mapping')
        for key in ('day','scene','turn'):
            count(row.get(key),'move occurrence '+key)
            if row[key]>st[key]:raise ValueError('move occurrence is ahead of its calendar')
        if 'at_seconds' in row:count(row['at_seconds'],'move occurrence elapsed seconds')
        if 'session' in row:
            count(row['session'],'move occurrence session')
            if basis!='session' or row['session']>st['session']:
                raise ValueError('move occurrence is ahead of its actual session calendar')
    for row in mapping(st.get('activations'),'activation ledger').values():
        if not isinstance(row,dict):raise ValueError('activation must be a mapping')
        count(row.get('used'),'activation usage')
        kind=row.get('kind');period=row.get('period')
        if kind=='one_time':
            if period!='lifetime' or row['used']>1:raise ValueError('invalid lifetime activation')
        elif kind=='every_other_turn':
            if type(period) is not dict or set(period)!={'scene','turn','at_seconds'}:
                raise ValueError('EOT activation requires its actual owner-turn occurrence')
            for name in ('scene','turn'):
                count(period[name],'EOT activation '+name)
                if period[name]>st[name]:raise ValueError('EOT activation is ahead of its owner calendar')
            if period['at_seconds'] is not None:count(period['at_seconds'],'EOT activation time')
            if row['used']!=1:raise ValueError('EOT activation consumes one occurrence')
        elif kind=='turn':
            if type(period) is not dict or set(period)!={'owner','turn'} or type(period['owner']) is not str or not period['owner'].strip():
                raise ValueError('turn activation requires explicit owner and turn identity')
            count(period['turn'],'activation owner turn')
        elif kind in ('daily','scene'):
            if kind=='daily' and isinstance(period,list):
                if len(period)!=2 or period[0]!='session' or basis!='session':raise ValueError('invalid session activation period')
                count(period[1],'activation session')
                if period[1]>st['session']:raise ValueError('activation is ahead of its session')
            else:
                count(period,'activation period')
                if period>st['day' if kind=='daily' else 'scene']:raise ValueError('activation is ahead of its calendar')
        else:raise ValueError('unknown activation frequency kind')
    for value in mapping(st.get('lifetime_activations',{}),'lifetime receipts').values():
        count(value,'lifetime usage')
        if value>1:raise ValueError('invalid lifetime activation receipt')
    for row in st.get('move_forfeitures',[]):
        if type(row)is not dict or set(row)!={'source','move_id','kind','period','day','at_seconds','sha256'} or row['source'] not in FORFEIT_SOURCES or row['kind'] not in ('scene','daily'):raise ValueError('reviewed Move-use forfeiture required')
        if row['sha256']!=__import__('resolution_transaction').request_fingerprint({k:v for k,v in row.items() if k!='sha256'}):raise ValueError('Move-use forfeiture evidence changed')
        count(row['at_seconds'],'forfeiture time');count(row['day'],'forfeiture day')
    for mid,row in mapping(st.get('move_forfeiture_refreshes',{}),'Move forfeiture refreshes').items():
        if type(row)is not dict or set(row)!={'through','sha256'} or row['sha256']!=__import__('resolution_transaction').request_fingerprint({'through':row.get('through')}):
            raise ValueError('Move forfeiture refresh evidence changed')
        count(row['through'],'Move forfeiture refresh boundary')
        if row['through']>len(st.get('move_forfeitures',[])):raise ValueError('Move forfeiture refresh is ahead of its ledger')
    pending=st.get('session_move_refresh_pending',[])
    if not isinstance(pending,list) or any(not isinstance(x,str) or not x.strip() for x in pending) or len(set(pending))!=len(pending):
        raise ValueError('pending move restoration requires distinct source IDs')


def state(c):
    validate(c)
    return c.spec.setdefault('frequency_state',dict(day=0,scene=0,turn=0,moves={},activations={}))


def _session_composition_source(engine):
    import json
    from pathlib import Path
    from source_context import verified_source
    value=json.loads((Path(engine.r.root)/'data/session-move-composition-policy.json').read_text(encoding='utf-8'))
    if value.get('schema_version')!=1 or value.get('source')!='C11-154':
        raise ValueError('known session Move composition declaration required')
    for reference in value['references']:verified_source(engine.r,reference,label='session Move composition')
    return value


def _composition_decisions(value,source):
    if type(value)is not dict or not value or set(value)-set(source['choices']):
        raise ValueError('explicit separate Daily Move composition choices required')
    for key,decision in value.items():
        if (type(decision)is not dict or set(decision)!={'value','reason'}
                or not isinstance(decision['reason'],str) or not decision['reason'].strip()):
            raise ValueError('each composition choice requires its own value and reason')
        valid=(type(decision['value'])is bool if key=='boundary_daily_moves'
               else type(decision['value'])is str and decision['value'] in source['choices'][key])
        if not valid:raise ValueError('unknown Daily Move composition ruling')


def validate_session_policy(engine):
    """GM composition rulings are not fabricated source editions or rest events."""
    policy=getattr(engine,'_session_move_policy',None)
    if policy is None:return {}
    if not engine.session_frequency:raise ValueError('session Move composition requires the selected session campaign option')
    source=_session_composition_source(engine)
    if (type(policy)is not dict or set(policy)!={'version','authority','references','history'}
            or type(policy['version'])is not int or policy['version']!=1 or policy['authority']!='explicit_gm_composition'
            or policy['references']!=source['references'] or type(policy['history'])is not list or not policy['history']):
        raise ValueError('retained scoped GM session Move composition required')
    choices={};previous=-1
    for row in policy['history']:
        if (type(row)is not dict or set(row)!={'session_epoch','session_id','decisions'}
                or type(row['session_epoch'])is not int or not previous<=row['session_epoch']<=engine.session_epoch
                or (row['session_id'] is not None and row['session_id'] not in engine.session_ids_seen)):
            raise ValueError('actual campaign composition admission scope required')
        _composition_decisions(row['decisions'],source)
        if (row['session_id'] is None and row['session_epoch']!=0
                or row['session_id'] is not None and engine.session_ids_seen.index(row['session_id'])!=row['session_epoch']):
            raise ValueError('composition admission does not match its real committed session')
        if all(choices.get(key)==decision for key,decision in row['decisions'].items()):
            raise ValueError('duplicate campaign composition admission')
        choices.update(deepcopy(row['decisions']));previous=row['session_epoch']
    return choices


def prepare_session_policy(engine,decisions):
    if decisions is None:return None
    if not engine.session_frequency:raise ValueError('session campaign option required for Move composition')
    source=_session_composition_source(engine);_composition_decisions(decisions,source)
    return {'version':1,'authority':'explicit_gm_composition','references':deepcopy(source['references']),
            'history':[{'session_epoch':engine.session_epoch,'session_id':engine.session_id,'decisions':deepcopy(decisions)}]}


def choose_session_move_policy(engine,decisions):
    """Admit a current GM ruling without refreshing any existing usage."""
    import state_grants as G
    source=_session_composition_source(engine);_composition_decisions(decisions,source)
    def apply(e,_):
        current=validate_session_policy(e)
        if all(current.get(key)==decision for key,decision in decisions.items()):
            raise ValueError('same campaign composition ruling already admitted')
        before=deepcopy(getattr(e,'_session_move_policy',None))
        if before is None:e._session_move_policy=prepare_session_policy(e,decisions)
        else:
            e._session_move_policy=deepcopy(before)
            e._session_move_policy['history'].append({'session_epoch':e.session_epoch,'session_id':e.session_id,'decisions':deepcopy(decisions)})
        validate_session_policy(e)
        e.gm._rec('Daily Move session composition',before,e._session_move_policy,
                  '; '.join(key+': '+decision['reason'] for key,decision in decisions.items()))
        return deepcopy(e._session_move_policy)
    return G.transition(engine,None,apply,include_rulings=True)


def validate_session_binding(engine,c):
    """Read-only admission checks, shared by single and batch registration."""
    validate_session_policy(engine)
    st=c.spec.get('frequency_state',{})
    if not isinstance(st,dict):raise ValueError('frequency state must be a mapping')
    if not getattr(engine,'session_frequency',False):
        if st.get('daily_basis')=='session':
            raise ValueError('session frequency state requires its selected campaign policy')
        return
    validate(c)
    if st.get('daily_basis')=='session':return
    import resolution_transaction as TX
    from types import SimpleNamespace
    for obj in getattr(engine,'_physical_objects',{}).values():
        physical=obj.get('frequency_state')
        if not isinstance(physical,dict) or physical.get('calendar_owner_id')!=c.entity_id:continue
        if physical.get('sha256')!=TX.request_fingerprint({k:v for k,v in physical.items() if k!='sha256'}):
            raise ValueError('physical frequency state changed before session adoption')
        calendar={key:st.get(key,0) for key in ('day','scene','turn')}
        calendar.update(moves={},activations=physical.get('activations'))
        validate(SimpleNamespace(spec={'frequency_state':calendar},move_uses={}))


def bind_session(engine,c):
    """Bind without refreshing usage; finish admission checks before writes.

    Switching campaign policy or reconstructing an engine is not a witnessed
    session boundary. Preserve current usage when adopting the session ledger.
    """
    validate_session_binding(engine,c)
    if not getattr(engine,'session_frequency',False):return
    if c not in engine._time_actors:engine._time_actors.append(c)
    st=state(c)
    if st.get('daily_basis')=='session':return
    st['daily_basis']='session';st.setdefault('session',0)
    period=['session',st['session']]
    for entry in st['activations'].values():
        if entry.get('kind')=='daily' and entry.get('period')==st['day']:
            entry['period']=list(period)
    for key,used in c.spec.pop('daily_feat_uses',{}).items():
        old=st['activations'].get(key,{})
        active=old.get('used',0) if old.get('kind')=='daily' and old.get('period')==period else 0
        st['activations'][key]=dict(kind='daily',period=list(period),used=max(active,used))
    # A physical tool references this calendar, not its current holder. Adopt
    # its current-day quota at the same real policy boundary as actor quotas.
    for obj in getattr(engine,'_physical_objects',{}).values():
        physical=obj.get('frequency_state')
        if not isinstance(physical,dict) or physical.get('calendar_owner_id')!=c.entity_id:continue
        for entry in physical['activations'].values():
            if entry.get('kind')=='daily' and entry.get('period')==st['day']:
                entry['period']=list(period)
        _sign_physical(physical)


def activation_period(st,kind):
    if kind=='daily':
        return ['session',st['session']] if st.get('daily_basis')=='session' else st['day']
    return st['scene']


def refresh_session(engine,c):
    """Commit the selected future boundary, independently from physical rest."""
    bind_session(engine,c);st=state(c);st['session']+=1
    choices=validate_session_policy(engine)
    boundary=choices.get('boundary_daily_moves',{}).get('value')
    if boundary is not None:
        if boundary:
            for mid in list(c.move_uses):
                if mid in engine.r.moves and move_frequency(engine,mid,c)[0]=='daily':
                    c.move_uses.pop(mid,None)
        # Preserve the occurrence ledger: a new session does not end a Scene.
        st.pop('session_move_refresh_pending',None)
        c.spec['move_uses']=dict(c.move_uses)
        return
    # Keep spent daily Moves until an independently justified restoration. The
    # selected optional text does not settle whether a session alone replaces rest.
    pending=set(st.get('session_move_refresh_pending',[]))
    pending.update(mid for mid,used in c.move_uses.items() if used>0)
    st['session_move_refresh_pending']=sorted(pending)


def move_frequency(engine,mid,c=None):
    suppressed=__import__('condition_instances').csv_suppressed(c)
    def effective(pair):
        kind,count=pair
        if suppressed:
            if kind=='at_will':return 'every_other_turn',1
            if kind=='every_other_turn' or kind=='scene' and count==2:return 'scene',1
        return pair
    def vitamin(actor,move,pair):
        import vitamin_moves as VITAMINS
        return pair if suppressed else VITAMINS.frequency(actor,move,pair)
    created=__import__('coordinator').innovation_instance(engine.r,mid)
    if created and created['template']==3 and __import__('coordinator').source(engine.r,created['source_contract'],__import__('coordinator').INNOVATION)['innovation3_frequency']=='turn':return 'turn',1
    if c is not None:
        import move_permissions as PERMISSIONS
        c=PERMISSIONS.frequency_owner(engine,c,mid)
        if mid == 'move/잠재파워':
            import csv_item_capability_contracts as CSV_CAPABILITIES
            if CSV_CAPABILITIES.hidden_power_frequency(c, None) == 'At-Will':
                return effective(('at_will', 1))
    if c is not None:
        for effect in engine.r.move_mech(mid)[0].get("effects_exec", []):
            if effect.get("type")=="frequency_rule" and "if_ghost" in effect and "else" in effect:
                import class_move_grants as CLASS_MOVES
                ghost = "고스트" in c.types or CLASS_MOVES.uses_ghost_curse(c,mid)
                import vitamin_moves as VITAMINS
                import signature_moves as SIGNATURE
                return effective(SIGNATURE.frequency(c,mid,vitamin(c,mid,parse(effect["if_ghost"] if ghost else effect["else"]))))
    parsed=engine.r.moves_mech.get(mid,{}).get('header',{}).get('frequency')
    import vitamin_moves as VITAMINS
    import signature_moves as SIGNATURE
    return effective(SIGNATURE.frequency(c,mid,vitamin(c,mid,parse(parsed or engine.r.move(mid).get('frequency')))))

def move_allowed(engine,c,mid,*,outside_combat=None):
    # None preserves the low-level turn-ledger contract used by direct policy
    # callers. Runtime producers must declare their actual combat context.
    if outside_combat not in (None,True,False):raise ValueError('outside-combat frequency context must be explicit')
    if engine.r.move(mid).get('class')=='항상':
        return False,'상시 기술은 학습 상태이며 직접 발동하는 행동이 아님'
    kind,cap=move_frequency(engine,mid,c)
    if not __import__('focused_command').frequency_allowed(engine,c,kind):
        return False,'Focused Command permits only At-Will actions this round'
    if __import__('type_ace').frequency_exception(engine,c,mid):return True,''
    bind_session(engine,c)
    import boss_transitions as BOSS
    boss_decision=BOSS.move_allowed(engine,c,mid,kind,cap)
    if boss_decision is not None:return boss_decision
    import swarm_transitions as SWARM
    swarm_decision=SWARM.move_allowed(engine,c,mid,kind,cap)
    if swarm_decision is not None:return swarm_decision
    import combat_timing as TIMING
    if kind!='at_will' and any(record.get('at_will_moves_only') for record in TIMING.records(c)):
        return False,'위협하기 동안 임의 빈도 기술만 사용 가능'
    import combat_maneuvers as MANEUVERS
    allowed,reason=MANEUVERS.move_allowed(engine,c,engine.r.move(mid))
    if not allowed:return False,reason
    import move_permissions as PERMISSIONS
    usage_owner=PERMISSIONS.frequency_owner(engine,c,mid)
    st=state(usage_owner);last=st['moves'].get(mid,{})
    count=usage_owner.move_uses.get(mid,0)
    if kind in ('unknown','one_time'):return False,'빈도 조건 해석 필요'
    if (kind=='daily' and count>=cap and mid in st.get('session_move_refresh_pending',[])
            and 'boundary_daily_moves' not in validate_session_policy(engine)):
        return False,'세션 경계의 일일 기술 복원 조건 미해석'
    if kind in ('daily','scene') and count>=cap:return False,'사용 횟수 소진'
    if kind=='scene' and last.get('scene')==st['scene']:
        if outside_combat is True:
            used_at=last.get('at_seconds')
            if used_at is None:return False,'전투 밖 장면 기술의 마지막 사용 시각 미확인'
            if used_at>engine.elapsed_seconds:raise ValueError('move occurrence is ahead of the world clock')
            if engine.elapsed_seconds-used_at<10:return False,'전투 밖 장면 기술 10초 재사용 대기'
        elif st['turn']-last.get('turn',-2)<2:
            return False,'장면 기술은 연속된 턴에 반복 사용 불가'
    if kind=='daily' and last.get('scene')==st['scene']:
        return False,'일일 기술은 한 장면에 한 번'
    if kind=='turn' and last.get('scene')==st['scene'] and last.get('turn')==st['turn']:return False,'한 턴에 한 번'
    if kind=='every_other_turn':
        if outside_combat is not True:
            # Use turn identity, not last_move: taking another action or waiting
            # must not bypass the interval or permanently lock the move.
            if last.get('scene')==st['scene'] and st['turn']-last.get('turn',-2)<2:
                return False,'매 다른 턴 기술 재사용 대기'
            if not last and usage_owner.last_move==mid and not __import__('provocateur').refunded_latest(engine,usage_owner,mid):return False,'매 다른 턴 기술 재사용 대기'
        elif last:
            # Outside combat an EOT interval is the source's approximately
            # ten-second world-clock interval, independent of scene. Never infer time from a
            # turn counter, another action, or a save/load boundary.
            used_at=last.get('at_seconds')
            if used_at is None:return False,'전투 밖 턴1회 기술의 마지막 사용 시각 미확인'
            if used_at>engine.elapsed_seconds:raise ValueError('move occurrence is ahead of the world clock')
            if engine.elapsed_seconds-used_at<10:return False,'전투 밖 턴1회 기술 10초 재사용 대기'
    return True,''

def consume_move(engine,c,mid,*,outside_combat=None):
    if outside_combat not in (None,True,False):raise ValueError('outside-combat frequency context must be explicit')
    __import__('focused_command').record_fact(engine,c,mid,move_frequency(engine,mid,c)[0])
    import move_permissions as PERMISSIONS
    c=PERMISSIONS.frequency_owner(engine,c,mid)
    bind_session(engine,c)
    kind,_=move_frequency(engine,mid,c)
    st=state(c)
    c.move_uses[mid]=c.move_uses.get(mid,0)+1
    c.spec['move_uses']=dict(c.move_uses)
    st['moves'][mid]=dict(day=st['day'],scene=st['scene'],turn=st['turn'],at_seconds=engine.elapsed_seconds)
    if st.get('daily_basis')=='session':st['moves'][mid]['session']=st['session']
    import swarm_transitions as SWARM
    SWARM.record_move_use(engine,c,mid,kind)
    import boss_transitions as BOSS
    BOSS.record_move_use(engine,c,mid,kind)

def start_turn(c):
    state(c)['turn']+=1

def end_scene(engine,c):
    import duelist as DUELIST
    DUELIST.clear(engine,c,'scene_end')
    validate(c)
    st=state(c)
    AP.end_scene(c,request_id='scene:'+str(getattr(engine,'session_epoch',0))+':'+str(st['scene']))
    st['scene']+=1
    for mid in list(c.move_uses):
        if (mid in engine.r.moves or __import__('coordinator').innovation_instance(engine.r,mid) is not None) and move_frequency(engine,mid,c)[0]!='daily':
            c.move_uses.pop(mid,None)
    c.spec['move_uses']=dict(c.move_uses)
    c.last_move=None

def _lifetime_used(st,key):
    # Keep the once-ever receipt separate so a later temporary frequency change
    # cannot overwrite its history in the ordinary scene/day projection.
    ledger=st.get('lifetime_activations',{})
    if not isinstance(ledger,dict):raise ValueError('lifetime activation ledger must be a mapping')
    used=ledger.get(key,0)
    old=st['activations'].get(key,{})
    if old.get('kind')=='one_time':used=max(used,old.get('used',0))
    if type(used) is not int or used not in (0,1):raise ValueError('invalid One Time Use receipt')
    return used


def _declared_period(c,st,kind,frequency,engine):
    if kind!='turn':return activation_period(st,kind)
    import world_entities as WORLD
    if engine is None or type(frequency) is not dict:
        raise ValueError('turn quota requires an engine and explicit turn owner')
    owner_id=frequency.get('turn_owner_id')
    if type(owner_id) is not str or not owner_id.strip():raise ValueError('actual turn owner required')
    owner=WORLD.actor_index(engine).get(owner_id)
    if owner is None:raise ValueError('actual turn owner required')
    validate(owner)
    return {'owner':owner_id,'turn':owner.spec.get('frequency_state',{}).get('turn',0)}


def _eot_activation_allowed(st,old,engine,cap):
    if cap!=1:raise ValueError('EOT activation has exactly one use per eligible owner turn')
    if engine is None:raise ValueError('EOT activation requires its actual engine clock')
    if old.get('kind')!='every_other_turn':return True
    period=old['period'];used_at=period['at_seconds']
    if used_at is not None and used_at>engine.elapsed_seconds:
        raise ValueError('EOT activation is ahead of the world clock')
    if not engine.encounter_active:
        return used_at is not None and engine.elapsed_seconds-used_at>=10
    return period['scene']!=st['scene'] or st['turn']-period['turn']>=2


def activation_allowed(c,key,frequency,*,engine=None,action_actor=None):
    kind,cap=parse(frequency)
    if kind=='every_other_turn':
        if cap!=1:raise ValueError('EOT activation has exactly one use per eligible owner turn')
        if engine is None:raise ValueError('EOT activation requires its actual engine clock')
    if engine is not None and action_actor is not None and not __import__('focused_command').frequency_allowed(engine,action_actor,kind):return False
    if engine is not None:bind_session(engine,c)
    st=state(c);old=st['activations'].get(key,{})
    if kind=='one_time':return _lifetime_used(st,key)<1
    if kind=='every_other_turn':
        return _eot_activation_allowed(st,old,engine,cap)
    period=_declared_period(c,st,kind,frequency,engine)
    used=old.get('used',0) if old.get('kind')==kind and old.get('period')==period else 0
    # Import manual daily usage written by the previous engine version.
    if kind=='daily' and not old:used=max(used,c.spec.get('daily_feat_uses',{}).get(key,0))
    return kind not in ('daily','scene','turn') or used<cap

def consume_activation(c,key,frequency,*,engine=None,action_actor=None):
    kind,cap=parse(frequency)
    if kind=='every_other_turn':
        if cap!=1:raise ValueError('EOT activation has exactly one use per eligible owner turn')
        if engine is None:raise ValueError('EOT activation requires its actual engine clock')
    if engine is not None and action_actor is not None and not __import__('focused_command').frequency_allowed(engine,action_actor,kind):
        raise ValueError('Focused Command permits only At-Will actions this round')
    if engine is not None:bind_session(engine,c)
    if kind=='every_other_turn':
        st=state(c)
        if not _eot_activation_allowed(st,st['activations'].get(key,{}),engine,cap):
            raise ValueError('EOT activation is not available at this owner boundary')
    if engine is not None and action_actor is not None:__import__('focused_command').record_fact(engine,action_actor,key,kind)
    if kind=='one_time':
        st=state(c);used=_lifetime_used(st,key)
        if used:raise ValueError('One Time Use already consumed for this source')
        st.setdefault('lifetime_activations',{})[key]=1
        st['activations'][key]=dict(kind='one_time',period='lifetime',used=1)
        return
    if kind=='every_other_turn':
        period={'scene':st['scene'],'turn':st['turn'],
                'at_seconds':engine.elapsed_seconds}
        st['activations'][key]={'kind':kind,'period':period,'used':1}
        return
    if kind not in ('daily','scene','turn'):return
    st=state(c);period=_declared_period(c,st,kind,frequency,engine)
    old=st['activations'].get(key,{})
    used=old.get('used',0) if old.get('kind')==kind and old.get('period')==period else 0
    if kind=='daily' and not old:used=max(used,c.spec.get('daily_feat_uses',{}).get(key,0))
    st['activations'][key]=dict(kind=kind,period=period,used=used+1)

def new_day(c):
    # A new day restores daily feats/abilities, not daily Moves: those require
    # an eligible extended rest or a Pokemon Center.
    state(c)['day']+=1
    c.spec.pop('daily_feat_uses',None)
    __import__('researcher_fields').new_day(c)


def _sign_physical(row):
    import resolution_transaction as TX
    row['sha256']=TX.request_fingerprint({k:v for k,v in row.items() if k!='sha256'})


def physical_owner(engine,obj):
    """A transient native-quota view; the physical item alone owns its ledger.

    The world has actor calendars, not an engine day. An observed fixed calendar
    reference therefore supplies periods without making a new holder a reset.
    No calendar or activation projection is copied onto the holder's sheet.
    """
    import world_entities as W, resolution_transaction as TX
    from types import SimpleNamespace
    if type(obj) is not dict or getattr(engine,'_physical_objects',{}).get(obj.get('id')) is not obj:
        raise ValueError('physical frequency requires an actual registered object')
    row=obj.get('frequency_state')
    if (type(row) is not dict or set(row)!={'calendar_owner_id','activations','sha256'}
            or row['sha256']!=TX.request_fingerprint({k:v for k,v in row.items() if k!='sha256'})):
        raise ValueError('physical frequency state changed or is incomplete')
    W._text(row['calendar_owner_id'],'physical calendar owner identity')
    calendar=W.actor_index(engine).get(row['calendar_owner_id'])
    if calendar is None:raise ValueError('physical frequency requires its observed calendar owner')
    validate(calendar)
    observed=calendar.spec.get('frequency_state',{})
    native={k:observed.get(k,0) for k in ('day','scene','turn')}
    activations=deepcopy(row['activations'])
    if getattr(engine,'session_frequency',False):
        if observed.get('daily_basis')!='session':
            raise ValueError('physical frequency calendar requires its actual session binding')
        native.update(daily_basis='session',session=observed.get('session',0))
    elif observed.get('daily_basis')=='session':
        raise ValueError('physical session frequency requires its selected campaign policy')
    native.update(moves={},activations=activations)
    owner=SimpleNamespace(spec={'frequency_state':native},move_uses={})
    validate(owner)
    if any(value['kind']!='daily' for value in row['activations'].values()):
        raise ValueError('physical calendar adapter supports narrative daily activations only')
    return owner


def _physical_frequency(frequency):
    kind,cap=parse(frequency)
    if kind!='daily':raise ValueError('physical calendar adapter requires daily frequency')
    return cap


def bind_physical(engine,obj,calendar_owner,key,frequency,*,used):
    """Observe a real tool's current daily availability, never infer a refill."""
    import world_entities as W
    W.require_actors(engine,calendar_owner)
    if type(obj) is not dict or getattr(engine,'_physical_objects',{}).get(obj.get('id')) is not obj:
        raise ValueError('physical frequency requires an actual registered object')
    W.require_usable_object(obj)
    cap=_physical_frequency(frequency)
    if type(used) is not int or not 0<=used<=cap:
        raise ValueError('physical daily quota requires its observed usage')
    W._text(key,'physical activation source')
    if 'frequency_state' in obj:raise ValueError('physical frequency is already bound')
    bind_session(engine,calendar_owner)
    period=activation_period(state(calendar_owner),'daily')
    row={'calendar_owner_id':calendar_owner.entity_id,'activations':{
        key:{'kind':'daily','period':period,'used':used}}}
    _sign_physical(row);obj['frequency_state']=row
    physical_owner(engine,obj)


def physical_activation_allowed(engine,obj,key,frequency):
    _physical_frequency(frequency)
    return activation_allowed(physical_owner(engine,obj),key,frequency)


def consume_physical_activation(engine,obj,key,frequency):
    _physical_frequency(frequency)
    owner=physical_owner(engine,obj)
    if not activation_allowed(owner,key,frequency):raise ValueError('physical daily activation exhausted')
    consume_activation(owner,key,frequency)
    obj['frequency_state']['activations']=owner.spec['frequency_state']['activations']
    _sign_physical(obj['frequency_state'])

def restore_daily_moves(engine,c,center=False,*,request_id=None):
    bind_session(engine,c)
    st=state(c)
    choices=validate_session_policy(engine)
    previous_day=choices.get('extended_rest_previous_day',{}).get('value','game_day')
    def eligible(last):
        if center:return True
        if last is None:return False
        if previous_day=='previous_session':
            # Old records without a witnessed session remain unknown. Do not
            # infer their session from independent day or engine counters.
            return 'session' in last and last['session']<st.get('session',0)
        return last['day']<st['day']
    import recovery_receipts as RECOVERY
    def qualify():
        observed=[]
        for mid in c.move_uses:
            if mid not in engine.r.moves or move_frequency(engine,mid,c)[0]!='daily':continue
            last=last_spent_move_day(c,mid)
            observed.append({'move_id':mid,'last_use':deepcopy(last),'current_day':st['day'],
                             'eligible':bool(eligible(last)),
                             **({'current_session':st.get('session',0),'session_observed':'session' in (last or {})}
                                if previous_day=='previous_session' else {})})
        return {'eligible':True,'reason':'Pokemon Center' if center else 'qualified extended rest','moves':observed}
    def commit():
        for mid in list(c.move_uses):
            if mid not in engine.r.moves or move_frequency(engine,mid,c)[0]!='daily':continue
            last=last_spent_move_day(c,mid)
            if eligible(last):
                c.move_uses.pop(mid,None)
                _refresh_forfeitures(c,mid)
                if mid in st.get('session_move_refresh_pending',[]):st['session_move_refresh_pending'].remove(mid)
        c.spec['move_uses']=dict(c.move_uses)
    recovery_policy={'center':center}
    if not center and 'extended_rest_previous_day' in choices:
        recovery_policy['previous_day_ruling']=deepcopy(choices['extended_rest_previous_day'])
        recovery_policy['composition_scope']=deepcopy(engine._session_move_policy['history'][-1])
    receipt=RECOVERY.execute(c,resource='daily_move_uses',source='combat/resting',request_id=request_id,
        policy=recovery_policy,read=lambda:dict(c.move_uses),qualify=qualify,commit=commit)
    if request_id is not None:return receipt

def restore_all_moves(c):
    for mid in list(c.move_uses):_refresh_forfeitures(c,mid)
    c.move_uses.clear()
    c.spec['move_uses']={}
    st=state(c)
    st.setdefault('restored_move_occurrences',{}).update(deepcopy(st['moves']))
    st['moves'].clear()
    state(c).pop('session_move_refresh_pending',None)
    c.last_move=None


def declaration_key(engine,actor,target,source,action,declaration):
    """Validate an authored quota and derive a collision-free native usage key.

    Actor is the ledger owner. Optional dimensions distinguish actual targets,
    provider entities and declared actions; period remains in the native ledger.
    """
    import json
    import world_entities as WORLD
    WORLD.require_actors(engine,actor,target)
    if type(declaration) is not dict or not {'kind','uses','scope'}<=set(declaration):
        raise ValueError('frequency declaration requires kind, uses and scope')
    if set(declaration)-{'kind','uses','scope','provider_id','turn_owner_id'}:
        raise ValueError('unsupported frequency declaration fields')
    if declaration['kind'] not in ('at_will','scene','daily','one_time','turn'):
        raise ValueError('unsupported authored activation frequency')
    if type(declaration['uses']) is not int or declaration['uses']<1:
        raise ValueError('explicit positive whole frequency cap required')
    parse(declaration)
    scope=declaration['scope']
    if type(scope) is not list or any(v not in ('target','provider','action') for v in scope) or len(set(scope))!=len(scope):
        raise ValueError('frequency scope needs distinct known dimensions')
    if ('provider' in scope)!=('provider_id' in declaration):
        raise ValueError('provider scope requires exactly one actual provider identity')
    if type(source) is not str or not source.strip():raise ValueError('selected source identity required')
    if (declaration['kind']=='turn')!=('turn_owner_id' in declaration):
        raise ValueError('turn frequency requires exactly one explicit turn owner')
    dimensions={'source':source}
    if declaration['kind']=='turn':
        period=_declared_period(actor,{},'turn',declaration,engine)
        dimensions['turn_owner']=period['owner']
    if 'target' in scope:dimensions['target']=target.entity_id
    if 'provider' in scope:
        provider=declaration['provider_id']
        WORLD.entity_identity(engine,provider)
        dimensions['provider']=provider
    if 'action' in scope:
        from action_metadata import ActionCost
        dimensions['action']=sorted(action.components) if type(action) is ActionCost else action
    # Unscoped authored activation shares the existing native source pool.
    return source if not scope and declaration['kind']!='turn' else 'frequency-scope:'+json.dumps(dimensions,sort_keys=True,separators=(',',':'),ensure_ascii=False)


def restore_scene_use(engine,c,mid):
    return _restore_limited_use(engine,c,mid,'scene')


def restore_daily_use(engine,c,mid):
    """Restore ONE Daily use; the native occurrence archive also clears its lock."""
    return _restore_limited_use(engine,c,mid,'daily')


def _restore_limited_use(engine,c,mid,kind):
    import move_permissions as P
    c=P.frequency_owner(engine,c,mid)
    if move_frequency(engine,mid,c)[0]!=kind:raise ValueError(kind.title()+' Move restoration required')
    st=state(c);c.move_uses[mid]=max(0,c.move_uses.get(mid,0)-1);c.spec['move_uses']=dict(c.move_uses)
    if mid in st['moves']:st.setdefault('restored_move_occurrences',{})[mid]=deepcopy(st['moves'][mid])
    st['moves'].pop(mid,None)


def restore_eot(engine,c,mid):
    import move_permissions as P
    c=P.frequency_owner(engine,c,mid)
    if move_frequency(engine,mid,c)[0]!='every_other_turn':raise ValueError('EOT Move restoration required')
    state(c)['moves'].pop(mid,None)
    if c.last_move==mid:c.last_move=None


def forfeited_uses(c,mid):
    st=state(c)
    through=st.get('move_forfeiture_refreshes',{}).get(mid,{}).get('through',0)
    # Daily Moves do not refresh at midnight; their forfeited capacity remains
    # spent until an actual rest/Center/all-Move refresh, just like native uses.
    return sum(1 for row in st.get('move_forfeitures',[])[through:] if row['move_id']==mid
               and (row['kind']=='daily' or row['period']==activation_period(st,row['kind'])))


def _refresh_forfeitures(c,mid):
    st=c.spec.get('frequency_state',{});rows=st.get('move_forfeitures',[])
    if any(row['move_id']==mid for row in rows):
        row={'through':len(rows)};row['sha256']=__import__('resolution_transaction').request_fingerprint(row)
        st.setdefault('move_forfeiture_refreshes',{})[mid]=row


def preflight_restore_move_use(engine,c,mid):
    """Actual historical use and currently spent capacity are distinct facts."""
    import move_permissions as P
    owner=P.frequency_owner(engine,c,mid);validate(owner)
    kind,_=move_frequency(engine,mid,c)
    if mid not in c.moves or kind not in ('scene','daily'):raise ValueError('actual known Scene or Daily Move required')
    st=owner.spec.get('frequency_state',{})
    actual=[row for row in (st.get('moves',{}).get(mid),st.get('restored_move_occurrences',{}).get(mid)) if row is not None]
    if kind=='scene':actual=[row for row in actual if row['scene']==st.get('scene',0)]
    if not actual or owner.move_uses.get(mid,0)<1:
        raise ValueError('recipient Move must have an already used actual activation and spent capacity')
    return owner,kind


def preflight_forfeit_move(engine,c,mid,*,source):
    import move_permissions as P
    if source not in FORFEIT_SOURCES or engine.r._selected_rule(source)!=source:raise ValueError('reviewed Move-use forfeiture source required')
    owner=P.frequency_owner(engine,c,mid);validate(owner)
    kind,cap=move_frequency(engine,mid,c)
    if mid not in c.moves or kind not in ('scene','daily'):raise ValueError('actual known Scene or Daily Move required')
    if owner.move_uses.get(mid,0)>=cap:raise ValueError('donor Move uses exhausted')
    return owner,kind


def forfeit_move(engine,c,mid,*,source):
    owner,kind=preflight_forfeit_move(engine,c,mid,source=source)
    bind_session(engine,owner);st=state(owner)
    row={'source':source,'move_id':mid,'kind':kind,'period':deepcopy(activation_period(st,kind)),'day':st['day'],'at_seconds':engine.elapsed_seconds}
    row['sha256']=__import__('resolution_transaction').request_fingerprint(row)
    st.setdefault('move_forfeitures',[]).append(row)
    owner.move_uses[mid]=owner.move_uses.get(mid,0)+1;owner.spec['move_uses']=dict(owner.move_uses)
    return deepcopy(row)


def scene_move_was_used(c,mid):
    st=state(c)
    return any(row is not None and row['scene']==st['scene'] for row in
        (st['moves'].get(mid),st.get('restored_move_occurrences',{}).get(mid)))


def last_spent_move_day(c,mid):
    st=state(c);last=st['moves'].get(mid)
    days=([last['day']] if last else [])+[r['day'] for r in st.get('move_forfeitures',[]) if r['move_id']==mid]
    if not days:return None
    return deepcopy(last) if last is not None and last['day']==max(days) else {'day':max(days),'basis':'move_use_forfeiture'}
