"""Source-owned shared-team Blessings and native optional damage responses.

One record lives under its creator; beneficiary side is a separate history.
No per-beneficiary copies, automatic spending or invented Scene expiry.
"""
from pathlib import Path
from types import SimpleNamespace
import hashlib,json,math
import common_checks as C
import effect_instances as E
import arithmetic_policy as M
import world_entities as W

KIND='team_blessing'
HISTORY='effect_instance_history'
DAMAGE_SEQUENCE='blessing_damage_sequence'
RESPONSE_SEQUENCE='blessing_response_sequence'
CLEAR='move/안개제거'
SWAP='move/코트체인지'


def policy(rules):
    result=getattr(rules,'_blessing_effect_policy',None)
    if result is None:
        result=json.loads((Path(rules.root)/'data/blessing-effect-policy.json').read_text(encoding='utf-8'))
        for file,digest in result['source_files'].items():
            if hashlib.sha256((Path(rules.root)/file).read_bytes()).hexdigest()!=digest:raise ValueError('Blessing source changed: '+file)
        rules._blessing_effect_policy=result
    return result


def definition(rules,source):
    import weather_blessings as WEATHER
    weather=WEATHER.definition(rules,source)
    if weather is not None:return weather
    row=policy(rules)['sources'].get(source)
    if row is not None and rules._selected_rule(source)!=source:raise ValueError('selected Blessing source changed')
    return row


def side(record):return record['scope_history'][-1]['side']
def continuous(record):return record['effect']['kind']=='team_initiative_bonus'
def remaining(record):
    limit=record[E.KEY]['capacity']['limit']
    if record.get('sage_conversions'):limit=min([limit,*[x['capacity'] for x in record['sage_conversions']]])
    used=sum(x['charged'] if 'facts' in x else x['selected'] for x in record['decisions'])
    return None if continuous(record) else max(0,limit-used) if record.get('sage_conversions') else limit-used

def effective_source(record):
    return record['sage_conversions'][-1]['move_id'] if record.get('sage_conversions') else record['source']


def beneficiaries(engine,actor,kind=None):
    """Actual team membership is independent of the instance's storage owner."""
    index=checked(engine)
    if index.get(actor.entity_id) is not actor:raise ValueError('Blessing beneficiary must be an actual world actor')
    return [(owner,r) for owner in index.values() for r in live(owner)
            if side(r)==actor.side and (kind is None or r['effect']['kind']==kind)]


def removal_source(rules,source):
    return source in policy(rules)['removal_sources'] and rules._selected_rule(source)==source


def _removed(rules,event):
    return (event.get('kind')=='blessing_removed' and removal_source(rules,event.get('source'))
            and isinstance(event.get('actor_id'),str))


def live(actor):
    if not isinstance(actor.blessings,list):raise ValueError('Blessing storage must be a list')
    result=[]
    for row in actor.blessings:
        if isinstance(row,dict) and E.KEY in row:E.stored_family(row,KIND);result.append(row)
    return result


def validate_record(actor,record,*,terminal=False):
    E.validate(record,actor=actor,terminal=terminal)
    if record.get('sage_conversions'):return _validate_converted(actor,record,terminal=terminal)
    definition_row=definition(actor.r,record['source']);m=record[E.KEY]
    if definition_row is None or record['effect']!=definition_row['payload']:raise ValueError('Blessing payload differs from selected source')
    if m['kind']!=KIND or m['capacity']!={'bucket':'team_blessing','source':record['source'],'limit':definition_row['capacity']}:raise ValueError('Blessing shared capacity changed')
    if m['lifetime']!={'boundary':definition_row['lifetime']}:raise ValueError('Blessing cannot invent a Scene or creator expiry')
    if len(m['ownership'])!=1 or m.get('applied_by_actor_id')!=actor.entity_id:raise ValueError('Blessing storage remains under its actual creator')
    scope=record.get('scope_history')
    if not isinstance(scope,list) or not scope:raise ValueError('Blessing actual team scope required')
    at=record['at'];previous=None
    for i,event in enumerate(scope):
        if not isinstance(event,dict):raise ValueError('typed Blessing scope event required')
        at=C.integer(event.get('at'),'Blessing scope time',at);E.text(event.get('side'),'actual beneficiary side')
        E.text(event.get('actor_id'),'scope source actor')
        if i==0:
            if event.get('kind')!='created' or event['actor_id']!=actor.entity_id or event.get('source')!=record['source'] or at!=record['at']:raise ValueError('Blessing original scope/source changed')
        elif event.get('kind')!='side_exchange' or event.get('source')!=SWAP or event.get('from_side')!=previous or event['side']==previous:raise ValueError('Blessing scope transfer must continue its actual history')
        previous=event['side']
    if record.get('creation_weather')!=definition_row['creation_weather']:raise ValueError('Blessing creation weather eligibility missing')
    decisions=record.get('decisions')
    if not isinstance(decisions,list):raise ValueError('Blessing decisions must be observed records')
    import weather_blessings as WEATHER
    if WEATHER.is_weather(record):
        WEATHER.validate_record(actor,record,terminal=terminal)
        return
    if continuous(record):
        if decisions:raise ValueError('continuous Blessing cannot acquire damage uses')
        if terminal:
            end=m['end_event']
            if m['state']!='expired':raise ValueError('continuous Blessing cannot be consumed')
            if end!={'kind':'encounter_end'} and not _removed(actor.r,end):raise ValueError('continuous Blessing ending source missing')
        return
    if record['effect']['kind'] not in ('team_damage_resistance','team_damage_effectiveness'):
        _validate_responses(actor,record,terminal=terminal)
        return
    seen=set();at=record['at']
    for event in decisions:
        if not isinstance(event,dict) or type(event.get('selected')) is not bool:raise ValueError('explicit Blessing activation decision required')
        at=C.integer(event.get('at'),'Blessing response time',at)
        who=E.text(event.get('target_id'),'actual damaged recipient');E.text(event.get('attacker_id'),'actual damage attacker')
        seq=C.integer(event.get('sequence'),'actual damage sequence',1)
        uid=who+':blessing-damage:'+str(seq)
        if event.get('event_id')!=uid or uid in seen:raise ValueError('Blessing response must belong to one distinct actual damage event')
        seen.add(uid)
        C.integer(event.get('scope_index'),'Blessing response scope',0,len(scope)-1)
        if event.get('side')!=scope[event['scope_index']]['side'] or event['at']<scope[event['scope_index']]['at']:raise ValueError('Blessing used by a different team')
        if event.get('move_class') not in definition_row['payload']['classes']:raise ValueError('Blessing damage class mismatch')
        E.text(event.get('move_id'),'actual damaging Move');E.text(event.get('move_type'),'actual damage type')
        C.integer(event.get('damage_before'),'observed incoming damage',1);C.integer(event.get('damage_after'),'observed selected damage',0)
        before=event.get('multiplier_before');after=event.get('multiplier_after')
        if type(before) not in (int,float) or type(after) not in (int,float):raise ValueError('typed Blessing multiplier required')
        expected=_damage_multiplier(actor.r,record,before) if event['selected'] else before
        if expected is None or after!=expected:raise ValueError('Blessing resistance step changed')
        formula=event.get('formula')
        if not isinstance(formula,dict):raise ValueError('actual damage formula observation required')
        C.integer(formula.get('after_defense'),'damage after defense',1);C.integer(formula.get('adjustment'),'observed final adjustment')
        other=formula.get('other_multiplier')
        if type(other) not in (int,float) or not math.isfinite(other) or other<0:raise ValueError('actual other multiplier required')
        if event['damage_before']!=max(0,M.product(formula['after_defense'],before,other)+formula['adjustment']) or event['damage_after']!=max(0,M.product(formula['after_defense'],after,other)+formula['adjustment']):raise ValueError('Blessing damage observation changed')
    left=remaining(record)
    if left<0:raise ValueError('Blessing shared uses exceeded')
    if not terminal and left==0:raise ValueError('exhausted Blessing must be archived')
    if terminal:
        end=m['end_event']
        if m['state']=='consumed':
            if left!=0 or not decisions or end!={'kind':'blessing_exhausted','event_id':decisions[-1]['event_id']}:raise ValueError('Blessing ending differs from actual last shared use')
        elif not _removed(actor.r,end):raise ValueError('Blessing removal source missing')


def _validate_responses(actor,record,*,terminal):
    kinds={'team_critical_guard':'critical_guard','team_critical_boost':'critical_boost',
           'team_stage_guard':'stage_guard','team_status_guard':'status_received'}
    seen=set();at=record['at'];scope=record['scope_history']
    for event in record['decisions']:
        fields={'event_id','sequence','at','actor_id','target_id','side','scope_index','kind','selected','charged','facts'}
        if not isinstance(event,dict) or set(event)!=fields or type(event['selected']) is not bool or type(event['charged']) is not bool:
            raise ValueError('typed actual Blessing response required')
        at=C.integer(event['at'],'Blessing response time',at)
        E.text(event['actor_id'],'actual Blessing beneficiary');E.text(event['target_id'],'actual response target')
        seq=C.integer(event['sequence'],'actual response sequence',1)
        if event['event_id']!=event['actor_id']+':blessing-response:'+str(seq) or event['event_id'] in seen:raise ValueError('distinct issued Blessing response required')
        seen.add(event['event_id'])
        i=C.integer(event['scope_index'],'Blessing response scope',0,len(scope)-1)
        if event['side']!=scope[i]['side'] or at<scope[i]['at']:raise ValueError('Blessing response has a different actual team')
        arctic=event['kind']=='arctic_zeal' and record['source']=='move/흰안개' and isinstance(record.get('arctic_zeal'),dict)
        if (not arctic and event['kind']!=kinds.get(record['effect']['kind'])) or not isinstance(event['facts'],dict):raise ValueError('Blessing response differs from its payload')
        facts=event['facts']
        if arctic:
            if facts.get('mode') not in ('weaken','stage','damage_reduction') or event['selected'] is not True or event['charged'] is not True:raise ValueError('printed paid Arctic Zeal response required')
            if facts['mode']=='stage' and facts.get('stat') not in ('def','spd'):raise ValueError('Arctic Zeal Defense or Special Defense required')
            if facts['mode']=='damage_reduction' and facts.get('move_id') not in actor.r.moves:raise ValueError('actual incoming Arctic Zeal damage required')
        elif event['kind']=='stage_guard':
            if set(facts)!={'delta'}:raise ValueError('actual stage loss required')
            C.integer(facts['delta'],'actual blocked stage loss',None,-1)
        elif event['kind'] in ('critical_guard','critical_boost'):
            if facts.get('move_id') not in actor.r.moves:raise ValueError('actual critical Move required')
            if event['kind']=='critical_boost':
                C.integer(facts.get('scene'),'actual Dragon Cheer Scene',0)
                if facts.get('actor_kind') not in ('pokemon','trainer') or not isinstance(facts.get('actor_types'),list):raise ValueError('actual Dragon Cheer beneficiary type required')
                eligible=facts['actor_kind']=='pokemon' and '드래곤' in facts['actor_types']
                if type(facts.get('dragon_first_free')) is not bool or facts['dragon_first_free'] and not eligible:raise ValueError('Dragon Cheer free use requires an actual Dragon Pokemon')
        elif event['kind']=='status_received':
            if set(facts)!={'condition','condition_source','turn_serial'} or 'condition/'+str(facts['condition']) not in actor.r.units:raise ValueError('actual received Status required')
            C.integer(facts['turn_serial'],'actual next personal turn',0)
        if event['charged']!=event['selected']:
            if not (record['effect']['kind']=='team_critical_boost' and event['selected'] and not event['charged'] and event['facts'].get('dragon_first_free') is True):raise ValueError('Blessing capacity exception lacks source authority')
    left=remaining(record)
    if left<0 or not terminal and left==0:raise ValueError('Blessing capacity exhausted without archive')
    if terminal:
        m=record[E.KEY];end=m['end_event']
        if m['state']=='consumed':
            if left!=0 or not record['decisions'] or end!={'kind':'blessing_exhausted','event_id':record['decisions'][-1]['event_id']}:raise ValueError('Blessing exhaustion differs from final actual response')
        elif not _removed(actor.r,end):raise ValueError('Blessing removal source missing')


def validate_world(engine,index):
    duplicate=set();identities=set();dragon_events=[]
    for actor in index.values():
        if DAMAGE_SEQUENCE in actor.spec:C.integer(actor.spec[DAMAGE_SEQUENCE],'Blessing damage sequence',0)
        if RESPONSE_SEQUENCE in actor.spec:C.integer(actor.spec[RESPONSE_SEQUENCE],'Blessing response sequence',0)
        records=[(r,False) for r in live(actor)]+[(r,True) for r in actor.spec.get(HISTORY,[]) if isinstance(r,dict) and isinstance(r.get(E.KEY),dict) and r[E.KEY].get('kind')==KIND]
        for r,terminal in records:
            validate_record(actor,r,terminal=terminal)
            if 'arctic_zeal' in r:
                proof=r['arctic_zeal'];issuer=index.get(proof.get('owner_id'))
                import type_ace as TA
                acquisitions=[] if issuer is None else TA.records(issuer,TA.uid('Arctic Zeal'))
                completed=getattr(engine,'_move_completions',{}).get(proof.get('completion_id'))
                if proof.get('pokemon_id')!=actor.entity_id or not any(x['request_id']==proof.get('acquisition') for x in acquisitions) or completed is None or completed['actor'] is not actor or completed['move_id']!='move/흰안개':raise ValueError('Arctic Zeal Blessing requires actual acquired extra Mist completion')
            if r['id'] in identities:raise ValueError('one Blessing instance cannot appear twice')
            identities.add(r['id'])
            if C.integer(actor.spec.get(E.SEQUENCE,0),'actual Blessing origin sequence',0)<r[E.KEY]['sequence']:raise ValueError('actual Blessing origin issuance missing')
            if terminal and r[E.KEY]['ended_at']>engine.elapsed_seconds:raise ValueError('Blessing ending is in the future')
            if not terminal:
                key=(side(r),r['source'])
                if continuous(r) and not engine.encounter_active:raise ValueError('encounter Blessing survived encounter end')
                if key in duplicate and definition(engine.r,r['source'])['stacking']!='same_source_nonstacking':raise ValueError('same-source team Blessing composition is unresolved')
                duplicate.add(key)
            for event in r['scope_history']:
                if event['actor_id'] not in index or event['at']>engine.elapsed_seconds:raise ValueError('Blessing scope source is missing or in future')
            for event in r['decisions']:
                if 'facts' in event:
                    who=index.get(event['actor_id'])
                    if who is None or event['target_id'] not in index or event['at']>engine.elapsed_seconds:raise ValueError('Blessing response participant/time invalid')
                    if who.spec.get(RESPONSE_SEQUENCE,0)<event['sequence']:raise ValueError('actual Blessing response issuance missing')
                    if event['kind']=='critical_boost' and event['selected']:
                        dragon_events.append(event)
                    continue
                target=index.get(event['target_id'])
                if target is None or event['attacker_id'] not in index or event['at']>engine.elapsed_seconds:raise ValueError('Blessing damage source is missing or in future')
                if target.spec.get(DAMAGE_SEQUENCE,0)<event['sequence']:raise ValueError('actual Blessing damage issuance missing')
            if terminal and r[E.KEY]['state']=='expired' and r[E.KEY]['end_event'].get('kind')=='blessing_removed' and r[E.KEY]['end_event']['actor_id'] not in index:raise ValueError('actual Blessing removal actor missing')

    free_seen=set()
    for event in sorted(dragon_events,key=lambda e:(e['actor_id'],e['sequence'])):
        facts=event['facts'];key=(event['actor_id'],facts['scene'])
        eligible=facts['actor_kind']=='pokemon' and '드래곤' in facts['actor_types']
        free=eligible and key not in free_seen
        if facts['dragon_first_free']!=free or event['charged']==free:raise ValueError('Dragon Cheer first Scene use changed')
        if eligible:free_seen.add(key)
    import weather_blessings as WEATHER
    WEATHER.validate_world(engine,index)
    pools={r['id']:r for owner in index.values() for r in live(owner)+owner.spec.get(HISTORY,[]) if isinstance(r,dict) and r.get(E.KEY,{}).get('kind')==KIND}
    for actor in index.values():
        for ignore in actor.spec.get('blessing_status_ignores',[]):
            if set(ignore)!={'instance_id','event_id','creator_id','condition','turn_serial'}:raise ValueError('exact received Status ignore receipt required')
            record=pools.get(ignore['instance_id'])
            decision=None if record is None else next((d for d in record['decisions'] if d['event_id']==ignore['event_id']),None)
            if decision is None or decision.get('kind')!='status_received' or not decision['selected'] or decision['actor_id']!=actor.entity_id or decision['facts']['condition']!=ignore['condition'] or decision['facts']['turn_serial']+1!=ignore['turn_serial'] or record[E.KEY]['applied_by_actor_id']!=ignore['creator_id']:raise ValueError('Status ignore requires its actual selected Safeguard receipt')


def checked(engine):
    index=W.actor_index(engine);validate_world(engine,index);return index


def preflight(engine,actor,effect,source):
    row=definition(engine.r,source)
    if row is None:return False
    if {k:v for k,v in effect.items() if not k.startswith('_')}!=row['raw']:raise ValueError('Blessing extraction differs from reviewed source')
    index=checked(engine)
    if index.get(actor.entity_id) is not actor:raise ValueError('Blessing creator must be an actual world participant')
    team=E.text(getattr(actor,'side',None),'actual creator side')
    import effects as FX
    if row['creation_weather'] and not FX.weather_matches(engine,row['creation_weather'],actor):raise ValueError('Aurora Veil requires actual hail at creation')
    if row['lifetime']=='encounter_end' and not engine.encounter_active:raise ValueError('encounter Blessing requires an actual encounter')
    for owner in index.values():
        if row['stacking']!='same_source_nonstacking' and any(side(r)==team and r['source']==source for r in live(owner)):raise ValueError('same-source team Blessing composition is unresolved')
        if owner.side==team and any(isinstance(r,dict) and E.KEY not in r and r.get('name')==row.get('name',row['raw'].get('name')) for r in owner.blessings):raise ValueError('legacy Blessing cannot be silently merged with a new shared pool')
    return True


def grant(engine,actor,effect,source):
    if not preflight(engine,actor,effect,source):return False
    row=definition(engine.r,source)
    record=E.create(engine,actor,kind=KIND,source=source,payload=row['payload'],capacity={'bucket':'team_blessing','source':source,'limit':row['capacity']},lifetime={'boundary':row['lifetime']},applied_by=actor)
    record.update(scope_history=[{'kind':'created','side':actor.side,'source':source,'actor_id':actor.entity_id,'at':engine.elapsed_seconds}],creation_weather=row['creation_weather'],decisions=[])
    actor.blessings.append(record);engine.time_actors([actor]);validate_record(actor,record)
    detail=('initiative '+str(row['payload']['amount'])+'; no stacking; until encounter end') if continuous(record) else str(row['capacity'])+' shared uses'
    engine.log('    '+row.get('name',row['raw'].get('name'))+': team '+actor.side+' '+detail+' ('+record['id']+')',source)
    return True


def select_damage(engine,event):
    """Optional responses to an actual hit, after its original damage dice once."""
    if event.get('blessing_processed'):return event['damage']
    event['blessing_processed']=True
    potential=min(event['damage'],max(0,event['target'].hp-1)) if event.get('damage_floor') else event['damage']
    if potential<=0:return event['damage']
    index=checked(engine);target=event['target'];attacker=event['attacker'];move=event['move']
    if reaction_blocked(engine,attacker,move):return event['damage']
    candidates=[(c,r) for c in index.values() for r in live(c)
                if r['effect']['kind'] in ('team_damage_resistance','team_damage_effectiveness')
                and side(r)==(attacker.side if r['effect']['kind']=='team_damage_effectiveness' else target.side)
                and move['class'] in r['effect']['classes']
                and not (r['effect']['kind']=='team_damage_resistance' and __import__('commander_orders').perfect_for_move(engine,attacker,move))]
    if not candidates:return event['damage']
    if index.get(target.entity_id) is not target or index.get(attacker.entity_id) is not attacker:raise ValueError('Blessing damage needs actual world participants')
    seq=C.integer(target.spec.get(DAMAGE_SEQUENCE,0),'actual damage sequence',0)+1
    target.spec[DAMAGE_SEQUENCE]=seq;uid=target.entity_id+':blessing-damage:'+str(seq)
    import damage_reactions as R
    for owner,r in candidates:
        if move.get('id')=='move/깨트리기' and r['source'] in ('move/리플렉터','move/빛의장막'):
            __import__('priority_actions')._move(engine.r,move['id']);continue
        if event['damage']<=0:break
        before=event['damage'];mult=event['damage_formula']['multiplier'];after_mult=_damage_multiplier(engine.r,r,mult)
        if after_mult is None:raise ValueError('Blessing resistance requires a supported actual multiplier')
        f=event['damage_formula'];reduced=max(0,M.product(f['after_defense'],after_mult,f['other_multiplier'])+f['adjustment'])
        beneficiary=attacker if r['effect']['kind']=='team_damage_effectiveness' else target
        answer=engine.rulings.decide({'type':'team_blessing','unit':r['source'],'instance_id':r['id'],'event_id':uid,'actor':beneficiary.name,'actor_id':beneficiary.entity_id,'attacker':attacker.name,'move':move['id'],'damage':min(before,max(0,target.hp-1)) if event.get('damage_floor') else before,'resisted_damage':min(reduced,max(0,target.hp-1)) if event.get('damage_floor') else reduced,'remaining':remaining(r),'text':'공유 축복을 이 피해에 사용합니까?'})
        selected=answer is True
        observation={'event_id':uid,'sequence':seq,'at':engine.elapsed_seconds,'target_id':target.entity_id,'attacker_id':attacker.entity_id,'side':side(r),'scope_index':len(r['scope_history'])-1,'move_id':move['id'],'move_type':event['actual_damage_type'],'move_class':move['class'],'selected':selected,'damage_before':before,'damage_after':reduced if selected else before,'multiplier_before':mult,'multiplier_after':after_mult if selected else mult,'formula':{k:f[k] for k in ('after_defense','other_multiplier','adjustment')}}
        r['decisions'].append(observation)
        if selected:
            event['damage']=reduced;f['multiplier']=after_mult
            next_mult=R.resistance_multiplier(engine,after_mult)
            event['resisted_damage']=None if next_mult is None else max(0,M.product(f['after_defense'],next_mult,f['other_multiplier'])+f['adjustment'])
            event['context']['multiplier']=after_mult
            engine.log('    shared Blessing '+r['id']+': '+str(before)+' -> '+str(reduced)+'; remaining '+str(remaining(r)),r['source'])
            __import__('sage').blessing_selected(engine,owner,beneficiary,r,observation)
        if remaining(r)==0:
            E.archive(engine,owner,r,state='consumed',event={'kind':'blessing_exhausted','event_id':uid});owner.blessings.remove(r)
        else:validate_record(owner,r)
    return event['damage']


def preflight_clear(engine,source,actor):
    index=checked(engine)
    if not any(live(c) for c in index.values()):return
    if not removal_source(engine.r,source) or index.get(actor.entity_id) is not actor:raise ValueError('shared Blessing removal requires its actual reviewed source')


def clear(engine,source,actor):
    preflight_clear(engine,source,actor)
    for owner in W.actor_index(engine).values():
        for record in list(live(owner)):
            E.archive(engine,owner,record,state='expired',event={'kind':'blessing_removed','source':source,'actor_id':actor.entity_id})
            owner.blessings.remove(record)


def preflight_swap(engine,actor,target,source):
    index=checked(engine)
    if not any(live(c) for c in index.values()):return
    if source!=SWAP or engine.r._selected_rule(source)!=source or index.get(actor.entity_id) is not actor or index.get(target.entity_id) is not target or actor.side==target.side:raise ValueError('shared Blessing exchange requires two actual opposing sides and reviewed source')


def swap(engine,actor,target,source):
    preflight_swap(engine,actor,target,source)
    sides={actor.side:target.side,target.side:actor.side}
    for owner in W.actor_index(engine).values():
        for record in live(owner):
            old=side(record)
            if old in sides:record['scope_history'].append({'kind':'side_exchange','from_side':old,'side':sides[old],'source':source,'actor_id':actor.entity_id,'at':engine.elapsed_seconds})


def initiative_contributions(engine,actor):
    """Read team contributions; equal source instances do not duplicate a bonus."""
    index=checked(engine)
    if not any(continuous(r) for owner in index.values() for r in live(owner)):return ()
    if index.get(actor.entity_id) is not actor:raise ValueError('initiative beneficiary must be an actual world actor')
    grouped={}
    for owner in index.values():
        for record in live(owner):
            if continuous(record) and side(record)==actor.side:
                entry=grouped.setdefault(record['source'],{'source':record['source'],'amount':record['effect']['amount'],'instances':[]})
                entry['instances'].append(record['id'])
    return tuple(grouped.values())


def end_encounter(engine):
    index=checked(engine)
    for owner in index.values():
        for record in list(live(owner)):
            if record[E.KEY]['lifetime']['boundary']=='encounter_end':
                E.archive(engine,owner,record,state='expired',event={'kind':'encounter_end'})
                owner.blessings.remove(record)


def owns_timing(rules,effect,source):
    row=definition(rules,source) if effect.get('type')=='initiative' else None
    return row is not None and row['payload']['kind']=='team_initiative_bonus'


def _damage_multiplier(rules,record,multiplier):
    if record['effect']['kind']=='team_damage_resistance':
        import damage_reactions as R
        return R.resistance_multiplier(SimpleNamespace(r=rules),multiplier)
    if multiplier==0:return 0
    import weather_blessings as WEATHER
    return WEATHER.shifted(rules,multiplier,'offense')


def reaction_blocked(engine,attacker,move):
    """Existing exact no-Blessing-response operators apply to either origin."""
    if move.get('id')=='move/레이징불':
        return engine.r._selected_rule(move['id'])==move['id']
    if attacker.abilities_suppressed:return False
    import effects_ext as EXT
    active={engine.r.ability_alias.get(a,a) for a in attacker.abilities}
    for name in active:
        for effect in engine.r.ability_effects.get(name,[]):
            if effect.get('type')!='ignore_effects':continue
            if effect.get('no_blessing_reactions'):
                engine.r._selected_rule('ability/'+name)
                return True
            if 'blessings' in effect.get('ignore_reactions',[]) and effect.get('moves')=='melee' and '근접' in EXT.keywords_for(attacker,move):
                engine.r._selected_rule('ability/'+name)
                return True
    return False


def registration(rules,value):
    for source,row in policy(rules)['sources'].items():
        if row.get('manual_activation') and value in (source,row['name']):
            if rules._selected_rule(source)!=source:raise ValueError('selected Blessing Ability changed')
            return {'name':row['name'],'source_id':source,'equivalent_source_ids':[source]}
    return None


def deferred_registration(rules,effect):
    return registration(rules,effect.get('_rule_id') or effect.get('_ability')) is not None


def activate(engine,actor,ability,target):
    """Pay the Ability's printed activation, then issue the same team instance."""
    import frequency as F,turn as TURN,state_grants as G,partial_entities as P
    reg=registration(engine.r,ability)
    if reg is None:raise ValueError('reviewed Blessing Ability required')
    source=reg['source_id'];row=definition(engine.r,source)
    W.require_actors(engine,actor,target);P.require_complete(actor,'Blessing Ability')
    if target is not actor:raise ValueError('team Blessing is anchored on its actual creator')
    if __import__('commander_orders').blocks_blessing(engine,actor):raise ValueError('Perfect Aim target cannot activate Blessings for this attack')
    if actor.abilities_suppressed or actor.fainted or not actor.on_field:raise ValueError('actual available unsuppressed Blessing Ability required')
    if not any((registration(engine.r,x) or {}).get('source_id')==source for x in actor.abilities):raise ValueError('actual acquired Blessing Ability required')
    if engine.r.ability_effects.get(reg['name'])!=[row['raw']]:raise ValueError('Blessing Ability extraction changed')
    preflight(engine,actor,row['raw'],source)
    def apply(e,who):
        act=row['manual_activation'];key='ability:'+reg['name']
        if not F.activation_allowed(who,key,act['frequency'],engine=e):raise ValueError('Blessing Ability frequency exhausted')
        if not TURN.spend(e,who,act['action'],reg['name']):raise ValueError('Blessing Ability action unavailable')
        F.consume_activation(who,key,act['frequency'],engine=e)
        grant(e,who,row['raw'],source)
        record=live(who)[-1]
        return {'source':source,'effect_id':record['id'],'remaining':remaining(record)}
    return G.transition(engine,actor,apply)


def _respond(engine,beneficiary,target,kind,facts):
    """One actual existing native hook commits one selected shared use."""
    if __import__('commander_orders').ignore_defensive(engine,target,beneficiary):return False
    for owner,record in beneficiaries(engine,beneficiary,kind):
        answer=engine.rulings.decide({'type':'team_blessing','unit':record['source'],
            'instance_id':record['id'],'actor_id':beneficiary.entity_id,
            'target_id':target.entity_id,'remaining':remaining(record),'facts':facts,
            'text':'공유 축복을 이 실제 사건에 사용합니까?'})
        selected=answer is True;charged=selected
        observation=dict(facts)
        if kind=='team_critical_boost':
            scene=beneficiary.spec.get('frequency_state',{}).get('scene',0)
            observation.update(scene=scene,actor_kind=beneficiary.kind,actor_types=list(beneficiary.types),dragon_first_free=False)
            # The first activation by this Pokemon in this Scene is free,
            # shared across casts, rather than an unlimited per-pool reset.
            records=[r for c in checked(engine).values() for r in live(c)+c.spec.get(HISTORY,[])
                     if isinstance(r,dict) and r.get('source')=='move/드래곤옐']
            first=not any(d.get('actor_id')==beneficiary.entity_id and d.get('selected') and d.get('facts',{}).get('scene')==scene and d.get('facts',{}).get('actor_kind')=='pokemon' and '드래곤' in d.get('facts',{}).get('actor_types',[]) for r in records for d in r.get('decisions',[]))
            if selected and beneficiary.kind=='pokemon' and '드래곤' in beneficiary.types and first:
                observation['dragon_first_free']=True;charged=False
        seq=C.integer(beneficiary.spec.get(RESPONSE_SEQUENCE,0),'Blessing response issuance',0)+1
        beneficiary.spec[RESPONSE_SEQUENCE]=seq
        uid=beneficiary.entity_id+':blessing-response:'+str(seq)
        record['decisions'].append({'event_id':uid,'sequence':seq,'at':engine.elapsed_seconds,
            'actor_id':beneficiary.entity_id,'target_id':target.entity_id,'side':beneficiary.side,
            'scope_index':len(record['scope_history'])-1,'kind':{'team_critical_guard':'critical_guard','team_critical_boost':'critical_boost','team_stage_guard':'stage_guard','team_status_guard':'status_received'}[kind],
            'selected':selected,'charged':charged,'facts':observation})
        if selected:
            __import__('sage').blessing_selected(engine,owner,beneficiary,record,record['decisions'][-1])
            if kind=='team_status_guard':
                beneficiary.spec.setdefault('blessing_status_ignores',[]).append({'instance_id':record['id'],'event_id':uid,'creator_id':owner.entity_id,'condition':facts['condition'],'turn_serial':facts['turn_serial']+1})
        if remaining(record)==0:
            E.archive(engine,owner,record,state='consumed',event={'kind':'blessing_exhausted','event_id':uid})
            owner.blessings.remove(record)
        else:validate_record(owner,record)
        if selected:return True
    return False

def status_received(engine,actor,condition,*,source=None,applied_by=None):
    if condition=='기절' or condition not in actor.conditions:return False
    if applied_by is not None and source in engine.r.moves and reaction_blocked(engine,applied_by,engine.r.move(source)):return False
    answer=_respond(engine,actor,applied_by or actor,'team_status_guard',{'condition':condition,'condition_source':source,'turn_serial':actor.custom_conditions.get('combat_turn_serial',0)})
    if not getattr(engine,'_native_move_resolution_depth',0):__import__('sage').finish_blessings(engine)
    return answer

def ignored(actor,condition):
    serial=actor.custom_conditions.get('combat_turn_serial',0)
    return any(r['condition']==condition and r['turn_serial']==serial for r in actor.spec.get('blessing_status_ignores',[])) and actor.custom_conditions.get('blessing_ignore_turn_open') is True

def effective_conditions(actor):
    result={c for c in actor.conditions if not ignored(actor,c)}
    if __import__('defense_curl').slowed(actor) and not ignored(actor,'둔화'):result.add('둔화')
    return result

def _validate_converted(actor,record,*,terminal):
    """Validate each real decision against the type active when it occurred."""
    from copy import deepcopy
    import sage as S
    base=definition(actor.r,record['source']);meta=record[E.KEY]
    if record['source'] not in S.MOVES or meta['applied_by_actor_id']!=actor.entity_id or meta['capacity']!={'bucket':'team_blessing','source':record['source'],'limit':base['capacity']}:raise ValueError('Divine Wind preserves original Sage Move creator and pool')
    if meta['lifetime']!={'boundary':base['lifetime']}:raise ValueError('Divine Wind cannot change lifetime')
    conversions=record['sage_conversions'];cursor=0;source=record['source'];indices=[]
    for event in conversions:
        if set(event)!={'source','move_id','decision_index','capacity','at','acquisition','scene'} or event['source']!=S.WIND or event['move_id'] not in S.MOVES or event['move_id']==source:raise ValueError('distinct typed Divine Wind conversion required')
        cursor=C.integer(event['decision_index'],'conversion actual consumed-history boundary',cursor,len(record['decisions']))
        C.integer(event['at'],'conversion time',record['at']);C.integer(event['scene'],'conversion Scene',0)
        if event['capacity']!=definition(actor.r,event['move_id'])['capacity'] or not any(r['request_id']==event['acquisition'] for r in S.records(actor,S.WIND)):raise ValueError('actual Divine Wind acquisition/capacity required')
        indices.append((cursor,event['move_id']));source=event['move_id']
    if record['effect']!=definition(actor.r,source)['payload']:raise ValueError('converted Blessing payload differs from last selected type')
    seen=set()
    for i,event in enumerate(record['decisions']):
        source=record['source']
        for index,selected in indices:
            if index<=i:source=selected
        uid=event['event_id']
        if uid in seen:raise ValueError('one actual Blessing event cannot be consumed twice')
        seen.add(uid)
        clone=deepcopy(record);clone.pop('sage_conversions');clone['source']=source;row=definition(actor.r,source)
        clone['effect']=deepcopy(row['payload']);clone['decisions']=[deepcopy(event)]
        clone[E.KEY]['state']='active';clone[E.KEY].pop('ended_at',None);clone[E.KEY].pop('end_event',None)
        clone[E.KEY]['capacity']={'bucket':'team_blessing','source':source,'limit':row['capacity']}
        clone[E.KEY]['ownership'][0]['source']=source;clone['scope_history'][0]['source']=source
        validate_record(actor,clone)
    if not record['decisions']:
        clone=deepcopy(record);clone.pop('sage_conversions');clone['source']=source;row=definition(actor.r,source)
        clone['effect']=deepcopy(row['payload']);clone[E.KEY]['state']='active';clone[E.KEY].pop('ended_at',None);clone[E.KEY].pop('end_event',None)
        clone[E.KEY]['capacity']={'bucket':'team_blessing','source':source,'limit':row['capacity']};clone[E.KEY]['ownership'][0]['source']=source;clone['scope_history'][0]['source']=source
        validate_record(actor,clone)
    if not terminal and remaining(record)==0:raise ValueError('converted exhausted pool must be archived')
    if terminal:
        end=meta['end_event']
        if meta['state']=='consumed':
            if remaining(record)!=0 or end.get('kind') not in ('blessing_exhausted','divine_wind_capacity'):raise ValueError('converted pool actual exhaustion required')
        elif not _removed(actor.r,end):raise ValueError('actual converted pool removal required')

def convert_sage(engine,actor,move_id):
    from copy import deepcopy
    import sage as S
    result=[];row=definition(engine.r,move_id)
    for record in list(live(actor)):
        if record['source'] not in S.MOVES or effective_source(record)==move_id:continue
        record.setdefault('sage_conversions',[]).append({'source':S.WIND,'move_id':move_id,'decision_index':len(record['decisions']),'capacity':row['capacity'],'at':engine.elapsed_seconds,'acquisition':S.acquired(actor,S.WIND)['request_id'],'scene':__import__('frequency').state(actor)['scene']})
        record['effect']=deepcopy(row['payload']);result.append(record['id'])
        if remaining(record)==0:
            E.archive(engine,actor,record,state='consumed',event={'kind':'divine_wind_capacity','source':S.WIND});actor.blessings.remove(record)
        else:validate_record(actor,record)
    return result


def critical(engine,actor,target,move,hit,crit):
    if not hit or reaction_blocked(engine,actor,move):return crit,False
    if crit and _respond(engine,target,actor,'team_critical_guard',{'move_id':move['id']}):return False,True
    if not crit and move['class'] in ('물리','특수') and _respond(engine,actor,target,'team_critical_boost',{'move_id':move['id']}):return True,True
    return crit,False


def stage_guard(engine,actor,delta):
    if delta>=0:return False
    inflictor=getattr(engine,'_inflictor',None)
    for scope in reversed(getattr(engine,'_event_use_scopes',())):
        if scope.get('actor') is inflictor and scope.get('move_id') is not None:
            if reaction_blocked(engine,inflictor,engine.r.move(scope['move_id'])):return False
            break
    # Conditions may have no actor inflictor; do not invent one.
    target=inflictor or actor
    return _respond(engine,actor,target,'team_stage_guard',{'delta':delta})


def spend_arctic(engine,beneficiary,target,instance_id,facts):
    """Spend the existing Mist pool; its ordinary stage-guard uses share capacity."""
    import type_ace as TA
    if __import__('commander_orders').ignore_defensive(engine,target,beneficiary):
        raise ValueError('Perfect Aim target cannot activate defensive Blessings')
    selected=next(((owner,r) for owner,r in beneficiaries(engine,beneficiary,'team_stage_guard') if r['id']==instance_id and 'arctic_zeal' in r),None)
    if selected is None or '얼음' not in beneficiary.types:raise ValueError('actual Ice beneficiary and Arctic Zeal Mist pool required')
    owner,record=selected
    if facts.get('mode') not in ('weaken','stage','damage_reduction'):raise ValueError('printed Arctic Zeal response required')
    seq=C.integer(beneficiary.spec.get(RESPONSE_SEQUENCE,0),'Blessing response issuance',0)+1
    beneficiary.spec[RESPONSE_SEQUENCE]=seq;uid=beneficiary.entity_id+':blessing-response:'+str(seq)
    record['decisions'].append({'event_id':uid,'sequence':seq,'at':engine.elapsed_seconds,'actor_id':beneficiary.entity_id,'target_id':target.entity_id,'side':beneficiary.side,'scope_index':len(record['scope_history'])-1,'kind':'arctic_zeal','selected':True,'charged':True,'facts':dict(facts)})
    if remaining(record)==0:
        E.archive(engine,owner,record,state='consumed',event={'kind':'blessing_exhausted','event_id':uid});owner.blessings.remove(record)
    else:validate_record(owner,record)
    return True
