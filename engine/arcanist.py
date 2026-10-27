"""Arcanist choices consume the native acquisition, weapon and Move owners."""
from copy import deepcopy
from functools import wraps
from hashlib import sha256
from pathlib import Path
import csv
import json

import common_checks as C
import state_grants as G
import world_entities as W

CLASS='supp-fantasy/아케니스트'
TRAINING='feat/아케인-훈련'; META='feat/메타매직'; AUTHENTIC='feat/옛마법'
SIGNATURE='feat/시그니처-조작'; RECOUP='feat/에너지-재충전'; INVEST='feat/영혼-투자'
BOOK_SHA='a51f5d6592bc1ff12b380f47398db93426b53c58c210810f5041b29eb64b2266'
CSV_SHA='4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd'
FEATURES={TRAINING:(511,515),CLASS:(666,668),META:(670,675),AUTHENTIC:(677,682),
          SIGNATURE:(684,691),RECOUP:(693,698),INVEST:(700,705)}
CSV_ROWS={CLASS:559,META:560,AUTHENTIC:561,SIGNATURE:562,RECOUP:564,INVEST:565}
CLAUSES={TRAINING:'FAN-063',CLASS:'FAN-082',META:'FAN-083',AUTHENTIC:'FAN-084',
         SIGNATURE:'FAN-085',RECOUP:'FAN-086',INVEST:'FAN-087'}
RANK1=('energy_finesse','warp_energy','directed_barrier','power_overdrive')
RANK2=('berserk_blow','energy_link','enlarged_power','lock_of_fate')
RANKS={**dict.fromkeys(RANK1,1),**dict.fromkeys(RANK2,2)}
DEFINITIONS={u:{'span':list(s),'catalog_span':[657,706] if u==CLASS else list(s),
    'clause_id':CLAUSES[u],'class_template':CLASS,'minimum_level':0,'skill':None,
    'ranked':u==SIGNATURE,'max_rank':2,'source_choices':['supplement','local_csv'],
    'source':{'file':'input/supp-fantasy.md','sha256':BOOK_SHA}} for u,s in FEATURES.items()}
ARM='arcanist_manipulation_choice'; MARK='_arcanist_manipulation'; BIND='arcanist_soul_investment'
QUOTA={'kind':'scene','uses':2}


def records(actor,feature=None,active=False):
    import trainer_feature_acquisition as T
    return [r for _,r in T.static_family_acquisitions(actor,FEATURES,feature,active=active)]


def acquired(actor,feature):
    rows=records(actor,feature,True)
    return rows[-1] if rows else None


def source(rules,feature,edition,rank=None):
    from source_context import verified_source
    if feature not in FEATURES or edition not in ('supplement','local_csv'):
        raise ValueError('exact Arcanist Feature and edition required')
    if rules._selected_rule(feature)!=feature or feature in rules.ruleset.unit_versions:
        raise ValueError('selected Arcanist source needs its own adapter')
    verified_source(rules,{'file':'input/supp-fantasy.md','sha256':BOOK_SHA},label='Arcanist supplement')
    result={'edition':edition,'file':'input/supp-fantasy.md','sha256':BOOK_SHA,'span':list(FEATURES[feature])}
    if edition=='local_csv':
        if feature==TRAINING:raise ValueError('Arcane Training uses its reviewed supplement source')
        row=563 if feature==SIGNATURE and rank==2 else CSV_ROWS[feature]
        verified_source(rules,{'file':'input/db/feats.csv','sha256':CSV_SHA},label='Arcanist CSV')
        with (Path(rules.root)/'input/db/feats.csv').open(encoding='utf-8-sig',newline='') as stream:
            cells=list(csv.reader(stream))[row-1]
        rules.ruleset.require({'id':'C2CSV/input/db/feats.csv:R'+str(row)+':main',
                              'source':{'file':'db/feats.csv','record_span':[row,row]}})
        result.update(file='input/db/feats.csv',sha256=CSV_SHA,row=row,
                      cells_sha256=sha256(json.dumps(cells,ensure_ascii=False,separators=(',',':')).encode()).hexdigest())
    return result


def static_source(rules,feature):
    source(rules,feature,'supplement')
    unit=rules.selection.units[feature]['source']
    if unit.get('file')!='supp-fantasy.md' or unit.get('lines')!=DEFINITIONS[feature]['catalog_span']:
        raise ValueError('exact Arcanist catalog span required')
    return {'file':'input/supp-fantasy.md','sha256':BOOK_SHA,'clause_id':CLAUSES[feature],'span':list(FEATURES[feature])}


def acquisition_snapshot(e,actor,feature,rank,selection):
    import acquired_features as A,skill_modifiers as S,elemental_connection as E
    expected={'edition','manipulation'} if feature==SIGNATURE else {'edition'}
    if type(selection)is not dict or set(selection)!=expected:raise ValueError('explicit Arcanist edition and printed selection required')
    if feature==SIGNATURE:
        if type(rank)is not int or rank not in (1,2) or selection['manipulation'] not in RANKS or RANKS[selection['manipulation']]>rank:
            raise ValueError('Signature chooses a manipulation at or below the purchased rank')
    elif rank is not None:raise ValueError('only Signature Manipulations is Ranked')
    parent=(META if rank==1 else AUTHENTIC) if feature==SIGNATURE else TRAINING if feature==CLASS else CLASS
    mystic=any(E.matches(x,E.MYSTIC) for field in ('edges','feats') for x in actor.spec.get(field,()))
    return {'selection':deepcopy(selection),'source':source(e.r,feature,selection['edition'],rank),
            'rank_number':rank,'occult':S.rank(e.r,actor,'오컬트학')[2],
            'parent':None if feature==TRAINING else parent,
            'parent_owned':feature==TRAINING or bool(A.owned_rule_count(actor,parent)),
            'arcane_edge':mystic or bool(E.choices(e,actor))}


def qualification(actor,feature,snapshot,prerequisite_source):
    import acquisition_qualification as Q
    if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'selection','source','rank_number','occult','parent','parent_owned','arcane_edge'}:
        raise ValueError('exact Arcanist acquisition observations required')
    s=snapshot;chosen=s['selection'];rank=s['rank_number']
    expected={'edition','manipulation'} if feature==SIGNATURE else {'edition'}
    if type(chosen)is not dict or set(chosen)!=expected:raise ValueError('exact Arcanist acquisition selection required')
    if s['source']!=source(actor.r,feature,chosen['edition'],rank):raise ValueError('Arcanist acquisition source changed')
    if feature==SIGNATURE and (type(rank)is not int or rank not in (1,2) or chosen['manipulation'] not in RANKS or RANKS[chosen['manipulation']]>rank):
        raise ValueError('Signature manipulation exceeds acquired rank')
    minimum={TRAINING:3,CLASS:0,META:4,AUTHENTIC:5,SIGNATURE:0,RECOUP:5,INVEST:6}[feature]
    C.integer(s['occult'],'acquired Occult Education rank',1)
    if type(s['parent_owned'])is not bool or type(s['arcane_edge'])is not bool:raise ValueError('actual Arcanist prerequisite observations required')
    parent=(META if rank==1 else AUTHENTIC) if feature==SIGNATURE else TRAINING if feature==CLASS else CLASS
    if s['parent']!=(None if feature==TRAINING else parent):raise ValueError('printed Arcanist parent changed')
    return Q.require(feature,'native','acquire',[
        Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
        Q.check('parent','prerequisite',s['parent_owned'],'printed Arcanist parent required'),
        Q.check('occult','prerequisite',s['occult']>=minimum,'printed Arcanist Occult rank required'),
        Q.check('arcane_edge','prerequisite',feature!=TRAINING or s['arcane_edge'],'Elemental Connection or Mystic Senses required')])


def after_acquire(e,actor,feature,sid):
    G.stat(actor,'spa',1,sid,operation_id='acquisition_stat_tag')


def validate_acquisition(actor,record,sid,active):
    if active and actor.spec.get(G.KEY,{}).get('stat_sources',{}).get('spa',{}).get('sources',{}).get(sid,{}).get('acquisition_stat_tag')!={'delta':1,'minimum':None}:
        raise ValueError('actual Arcanist Special Attack tag required')


def require(e,actor,feature,*,available=True):
    W.require_actors(e,actor)
    row=acquired(actor,feature)
    if row is None:raise ValueError('actual acquired Arcanist Feature required: '+feature)
    source(e.r,feature,row['snapshot']['selection']['edition'],row['snapshot']['rank_number'])
    __import__('trainer_feature_acquisition').validate_actor(actor)
    if available and (actor.fainted or actor.dead or actor.captured or not actor.on_field):raise ValueError('available actual Arcanist required')


def arm(e,actor,move_id,manipulation,*,signature_rank=None,range_mode=None,link_policy='korean_all'):
    """Choose the next native Special attack; this declaration spends nothing."""
    if manipulation not in RANKS:raise ValueError('one printed Power Manipulation required')
    require(e,actor,META if RANKS[manipulation]==1 else AUTHENTIC)
    if signature_rank is not None:
        if type(signature_rank)is not int or signature_rank not in (1,2):raise ValueError('actual Signature rank required')
        matches=[r for r in records(actor,SIGNATURE,True) if r['snapshot']['rank_number']==signature_rank and r['snapshot']['selection']['manipulation']==manipulation]
        if len(matches)!=1:raise ValueError('actual matching acquired Signature selection required')
    if range_mode not in (None,'burst1','cone2','close_blast2','line4','two_targets4') or (range_mode is not None)!=(manipulation=='warp_energy'):
        raise ValueError('Warp Energy needs one printed replacement range')
    if link_policy not in ('korean_all','english_next'):raise ValueError('exact S-001 Energy Link policy required')
    move_id=e.r.move_id(move_id)
    if move_id not in actor.moves:raise ValueError('actual known triggering Move required')
    row={'actor_id':actor.entity_id,'move_id':move_id,'manipulation':manipulation,'signature_rank':signature_rank,
         'range_mode':range_mode,'link_policy':link_policy}
    return G.transition(e,actor,lambda se,a:a.spec.update({ARM:deepcopy(row)}))


def choice(e,actor,move):
    marker=move.get(MARK)
    if marker is None:return None
    if type(marker)is not dict or set(marker)!={'actor_id','move_id','manipulation','signature_rank','range_mode','link_policy'} or marker['actor_id']!=actor.entity_id or marker['move_id']!=move['id'] or marker['manipulation'] not in RANKS:
        raise ValueError('actual native Power Manipulation identity required')
    actual=actor.spec.get(ARM)
    completed=[r.get('arcanist',{}).get('choice') for r in getattr(e,'_move_completions',{}).values() if r['actor'] is actor and r['move_id']==move['id']]
    if marker!=actual and marker not in completed:raise ValueError('Power Manipulation lost its actual native choice')
    return marker


def prepare(e,actor,move):
    row=actor.spec.get(ARM)
    if row is None:
        # Later recipients use the live native group, never an old saved Move.
        scope=next((s for s in reversed(getattr(e,'_move_activation_scopes',())) if s['actor']is actor and s['move_id']==move['id']),None)
        completion=getattr(e,'_move_completions',{}).get(scope.get('completion_id')) if scope else None
        if completion:row=completion.get('arcanist',{}).get('choice')
    if row is None or row['move_id']!=move['id']:return move
    require(e,actor,META if RANKS[row['manipulation']]==1 else AUTHENTIC)
    if move.get('class')!='특수':raise ValueError('Power Manipulation requires an actual Special Move')
    out=deepcopy(move);out[MARK]=deepcopy(row)
    return out


def event_interested(e,actor,target,move):
    """Retain real producer returns for our costs and actual linked hits."""
    import combat_timing as T
    return bool(move.get(MARK) or move.get('class')=='특수' and acquired(actor,RECOUP)
                or any('arcanist_link' in row for row in T.records(target)))


def range_spec(e,actor,move,rng):
    if actor is None:return rng
    row=choice(e,actor,move)
    if not row:return rng
    kind=row['manipulation'];out=deepcopy(rng)
    if kind=='warp_energy':
        if rng.get('shape') not in ('cone','line','burst','blast','close_blast'):raise ValueError('Warp Energy requires an actual area Move')
        mode=row['range_mode']
        out={k:v for k,v in out.items() if k not in ('shape','size','targets','origin')}
        out.update({'burst1':{'origin':'self','shape':'burst','size':1},'cone2':{'origin':'self','shape':'cone','size':2},
                    'close_blast2':{'origin':'self','shape':'close_blast','size':2},'line4':{'origin':'self','shape':'line','size':4},
                    'two_targets4':{'origin':4,'targets':2}}[mode])
    elif kind=='enlarged_power':
        if rng.get('shape') in ('burst','blast','close_blast','cone','line'):
            out['size']=C.integer(rng.get('size'),'actual area size',1)+1
        elif rng.get('targets')==1 and rng.get('origin')=='melee':out.update(origin='self',shape='burst',size=1);out.pop('targets',None)
        elif rng.get('targets')==1 and type(rng.get('origin'))is int:out.update(shape='blast',size=2);out.pop('targets',None)
        else:raise ValueError('Enlarged Power requires one target or an actual area Move')
    elif kind=='berserk_blow' and (rng.get('targets')!=1 or rng.get('shape')):
        raise ValueError('Berserk Blow requires an actual one-target Move')
    return out


def _timed(e,holder,payload,source):
    import combat_timing as T
    row={'source':source,'count_deadline':(e.round_no+1,T.current(e)),'encounter_end':True,**payload}
    T.install(e,holder,row)
    return row


def begin_move(e,completion):
    actor=completion['actor'];move=completion['move'];row=choice(e,actor,move)
    if row is None:return
    import frequency as F,action_points as AP,turn as TURN
    kind=row['manipulation'];feature=META if RANKS[kind]==1 else AUTHENTIC
    require(e,actor,feature)
    signature=row['signature_rank']
    key=feature if signature is None else SIGNATURE+':rank:'+str(signature)
    quota=QUOTA if signature is None or RANKS[kind]==1 else {'kind':'scene','uses':1}
    if signature is not None:
        if not any(r['snapshot']['rank_number']==signature and r['snapshot']['selection']['manipulation']==kind for r in records(actor,SIGNATURE,True)):
            raise ValueError('actual matching Signature acquisition required')
    limited=feature==AUTHENTIC or signature is not None
    if limited and not F.activation_allowed(actor,key,quota,engine=e):raise ValueError('Power Manipulation Scene frequency exhausted')
    ap=1 if feature==META and signature is None else 0
    if AP.available(actor)<ap:raise ValueError('available Metamagic AP required')
    if kind=='energy_finesse':
        import optional_weapon_framework as FW
        entry=actor.custom_conditions.get('equipped_weapons',{}).get(move.get('_weapon_attack',{}).get('key'))
        mm=e.r.move_mech(move['id'])[0]
        if not entry or not FW.profile_for_weapon(e,actor,entry['weapon'])['arcane'] or move['id'] not in FW.policy(e.r)['arcane_moves'] or not _effect_range(mm):
            raise ValueError('Energy Finesse needs a real Arcane Weapon Move with Effect Range')
    if not TURN.spend(e,actor,'swift',feature):raise ValueError('Power Manipulation needs a Swift Action')
    payment=actor.ap_account.charge(ap,retain_receipt=True) if ap else None
    before=deepcopy(F.state(actor)['activations'].get(key))
    if limited:F.consume_activation(actor,key,quota,engine=e)
    completion['arcanist']={'choice':deepcopy(row),'key':key,'activation_before':before,'limited':limited,
        'ap':ap,'payment':payment,'recouped':False,'overdrive_paid':False,'applied_hits':[],'tick':e.tick(actor),
        'move_uses_before':actor.move_uses.get(move['id'],0),
        'move_occurrence_before':deepcopy(F.state(actor)['moves'].get(move['id'])),'last_move_before':actor.last_move}
    completion['arcanist']['cost_proof']=__import__('root_resolution').fingerprint(_cost_facts(completion))
    actor.spec.pop(ARM,None)
    if kind=='directed_barrier':
        _timed(e,actor,{'arcanist_barrier':{'completion':completion['id'],'targets':[t.entity_id for t in completion['targets']],
            'value':e.tick(actor)}},META)


def _effect_range(mm):
    return any(key in effect for effect in (mm,*mm.get('effects_exec',()))
               for key in ('on_natural_roll','on_natural_roll_min'))


def effect_natural(e,actor,move,natural,*,face=None):
    row=choice(e,actor,move)
    return 1000 if row and row['manipulation']=='energy_finesse' and (natural if face is None else face)%2==0 else natural


def critical_bonus(e,actor,move):
    row=choice(e,actor,move)
    return 3 if row and row['manipulation']=='berserk_blow' else 0


def forbids(e,move,category):
    marker=move.get(MARK)
    if marker is None:return False
    actor=W.actor_index(e).get(marker.get('actor_id')) if type(marker)is dict else None
    if actor is None:raise ValueError('Lock of Fate lost its actual attacker')
    row=choice(e,actor,move)
    return bool(row and row['manipulation']=='lock_of_fate' and category in ('intercept','dodge','parry','shield','avoid_hit'))


def _completion(e,actor,move):
    rows=[r for r in getattr(e,'_move_completions',{}).values() if r['actor']is actor and r['move_id']==move['id'] and
          r.get('arcanist',{}).get('choice')==move.get(MARK) and r['phase']=='targets']
    if len(rows)!=1:raise ValueError('one actual active Arcanist Move completion required')
    return rows[0]


def overdrive(e,actor,move,*,actual):
    row=choice(e,actor,move)
    if not row or row['manipulation']!='power_overdrive':return 0
    state=_completion(e,actor,move)['arcanist']
    if actual and not state['overdrive_paid']:
        # A native HP listener may itself commit a transition. Mark the same
        # retained completion before that nested commit, not a stale local dict.
        state['overdrive_paid']=True
        e.lose_hp(actor,state['tick'],source=META,unpreventable=True)
    import skill_modifiers as S
    return state['tick']+S.rank(e.r,actor,'오컬트학')[2]


def reduction(e,attacker,target):
    import combat_timing as T
    return max([r['arcanist_barrier']['value'] for r in T.records(target) if 'arcanist_barrier'in r and attacker.entity_id in r['arcanist_barrier']['targets']]+[0])


def after_target(e,completion,target):
    import move_completion as COMPLETE
    state=completion.get('arcanist');result=COMPLETE.recipient_result(completion,target)
    if not state or not result or not result['hit'] or result['cancelled'] or result.get('hit_prevented') or target.entity_id in state['applied_hits']:return
    state['applied_hits'].append(target.entity_id)
    kind=state['choice']['manipulation'];actor=completion['actor']
    if kind=='berserk_blow':_timed(e,target,{'statuses':['취약']},AUTHENTIC)
    if kind=='energy_link':
        _timed(e,target,{'arcanist_link':{'completion':completion['id'],'type':completion['move']['type'],
            'policy':state['choice']['link_policy'],'consumed':False}},AUTHENTIC)


def link_damage(e,attacker,target,move,*,actual):
    """Resolve only the next actual Normal hit, not preview/range/accuracy checks."""
    import combat_timing as T
    if move.get('type')!='노말' or move.get('class') not in ('물리','특수'):return move,False
    links=[r for r in T.records(target) if 'arcanist_link'in r]
    if not links or links[-1]['arcanist_link']['consumed']:return move,False
    # A new link replaces the previous link's conversion for this hit.
    record=links[-1];link=record['arcanist_link'];out=deepcopy(move)
    boost=link['type']=='노말'
    if not boost:out['type']=link['type']
    if actual and (not boost or link['policy']=='english_next'):
        link['consumed']=True
    return out,boost


def _require_native_misses(e,row):
    import move_completion as COMPLETE
    returns=row.get('native_returns',{})
    if not returns:raise ValueError('Recoup Energy requires actual native producer returns, not claimed miss results')
    for event_id in returns:
        receipt=COMPLETE.require_returned_event(e,event_id)
        event=e._passive_events[event_id]
        accuracy=next((r['facts'] for r in receipt['native_return']['observations'] if r['stage']=='accuracy'),{})
        if event.get('hit')is not False or accuracy.get('hit')is not False or receipt['native_return']['hit_prevented']:
            raise ValueError('Recoup Energy requires actual native misses, not a prevented hit')


def recoup(e,actor,completion_id):
    require(e,actor,RECOUP)
    import move_completion as COMPLETE
    row=getattr(e,'_move_completions',{}).get(completion_id)
    if (not row or row['actor']is not actor or row['phase']!='complete' or row['move'].get('class')!='특수'
            or not row['results'] or any(r['hit'] or r['cancelled'] or r.get('hit_prevented') for r in row['results'].values())
            or any((COMPLETE.recipient_result(row,t)or{}).get('hit') for t in COMPLETE.actual_recipients(row))
            or row.get('arcanist_recouped') or row['round']!=e.round_no or row['turn_serial']!=actor.custom_conditions.get('combat_turn_serial',0)):
        raise ValueError('Recoup Energy requires this actual completed Special Move missing every target')
    if row.get('arcanist'):validate_completion(row)
    _require_native_misses(e,row)
    import frequency as F,turn as TURN,action_points as AP
    def apply(se,a):
        current=se._move_completions[completion_id]
        if not F.activation_allowed(a,RECOUP,QUOTA,engine=se):raise ValueError('Recoup Energy Scene frequency exhausted')
        if not TURN.spend(se,a,'free',RECOUP):raise ValueError('Recoup Energy needs a Free Action')
        F.consume_activation(a,RECOUP,QUOTA,engine=se)
        mid=current['move_id'];kind=F.move_frequency(se,mid,a)[0]
        if kind=='scene':F.restore_scene_use(se,a,mid)
        elif kind=='daily':F.restore_daily_use(se,a,mid)
        elif kind=='every_other_turn':F.restore_eot(se,a,mid)
        state=current.get('arcanist')
        if state:
            if state['payment']:a.ap_account.refund_spend(state['payment'])
            if state['limited']:
                activations=F.state(a)['activations']
                live=activations.get(state['key'])
                if not live or live['kind']!='scene' or live['period']!=F.activation_period(F.state(a),'scene') or live['used']<1:
                    raise ValueError('Recoup Energy needs the same-period actual manipulation use')
                live['used']-=1
                if not live['used']:
                    if state['activation_before'] is None:activations.pop(state['key'],None)
                    elif state['activation_before']['period']!=live['period']:
                        activations[state['key']]=deepcopy(state['activation_before'])
            state['recouped']=True
        current['arcanist_recouped']=True
        return {'completion':completion_id,'restored_move':mid}
    return G.transition(e,actor,apply)


def binding(e,actor,uid=None):
    row=actor.spec.get(BIND)
    if row is None or uid is not None and row['instance']!=uid:raise ValueError('actual Soul Investment binding required')
    require(e,actor,INVEST,available=False)
    if actor.spec.get('ap_bound',{}).get(row['instance'])!=2:raise ValueError('Soul Investment AP binding changed')
    return row


def invest(e,actor,novice,expert):
    import optional_weapon_framework as FW,temporary_ap as TEMP,turn as TURN
    require(e,actor,INVEST)
    if BIND in actor.spec:raise ValueError('only one Soul Investment may be Bound')
    bond=actor.spec.get(FW.BONDS,{}).get('arcane')
    if not bond:raise ValueError('actual current Soul Bond weapon required')
    _,profile=FW.object_profile(e,bond['instance_id'])
    mids=[e.r.move_id(novice),e.r.move_id(expert)];policy=FW.policy(e.r)['arcane_moves']
    if any(policy.get(mid,{}).get('rank')!=rank for mid,rank in zip(mids,(3,5))) or any(mid in actor.moves for mid in mids):
        raise ValueError('one new Novice and one new Expert Arcane Weapon Move required; no duplicate Move instances')
    if any(policy[mid]['forms'] and profile['kind'] not in policy[mid]['forms'] for mid in mids):raise ValueError('Soul Investment must respect Arcane Move weapon form')
    TEMP.preflight_binding(actor,2,'arcanist')
    def apply(se,a):
        if not TURN.spend(se,a,'extended',INVEST):raise ValueError('Soul Investment needs an Extended Action')
        serial=C.integer(a.spec.get('arcanist_investment_serial',0),'Soul Investment serial',0)+1
        a.spec['arcanist_investment_serial']=serial
        uid=INVEST+':'+a.entity_id+':'+str(serial)
        a.ap_account.charge(2,mode='bind',instance_id=uid,temporary_binding_owner='arcanist')
        a.spec[BIND]={'instance':uid,'instance_id':bond['instance_id'],'moves':mids,'source':INVEST}
        reconcile_investment(se,a)
        return deepcopy(a.spec[BIND])
    return G.transition(e,actor,apply)


def reconcile_investment(e,actor,*,unequipped=None):
    row=actor.spec.get(BIND)
    if row is None:return
    import optional_weapon_framework as FW
    current=actor.spec.get(FW.BONDS,{}).get('arcane')
    if not current or current['instance_id']!=row['instance_id']:
        return end_binding(e,actor,row)
    entries=[entry for entry in actor.custom_conditions.get('equipped_weapons',{}).values() if entry is not unequipped and entry.get('instance_id')==row['instance_id']]
    sid=row['instance']+':weapon'
    for entry in actor.custom_conditions.get('equipped_weapons',{}).values():
        for mid in entry.pop('arcanist_investment_grants',[]):
            if mid in entry['available_moves']:entry['available_moves'].remove(mid)
    if not entries:
        if sid in actor.spec.get(G.KEY,{}).get('sources',{}):G.revoke(actor,sid,engine=e)
        return
    if len(entries)!=1:raise ValueError('Soul Investment requires one actual equipped Soul Bond')
    entry=entries[0];FW.validate_loadout(e,actor,entry['weapon'])
    profile=FW.object_profile(e,row['instance_id'])[1]
    for mid in row['moves']:
        forms=FW.policy(e.r)['arcane_moves'][mid]['forms']
        if forms and profile['kind'] not in forms:raise ValueError('Soul Investment must respect Arcane Move weapon form')
        if mid not in entry['available_moves']:entry['available_moves'].append(mid)
    entry['arcanist_investment_grants']=list(row['moves'])
    G.grant_moves(actor,row['moves'],sid,'feature',owner_id=actor.entity_id,lifetime='while_equipped',rule_id=INVEST,mode='permission')


def end_binding(e,actor,row):
    import action_points as AP
    sid=row['instance']+':weapon'
    for entry in actor.custom_conditions.get('equipped_weapons',{}).values():
        for mid in entry.pop('arcanist_investment_grants',[]):
            if mid in entry['available_moves']:entry['available_moves'].remove(mid)
    if sid in actor.spec.get(G.KEY,{}).get('sources',{}):G.revoke(actor,sid,engine=e)
    AP.release_binding(actor,row['instance'],expected_amount=2)
    actor.spec.pop(BIND)


def release_investment(e,actor):
    import turn as TURN
    binding(e,actor)
    def apply(se,a):
        if not TURN.spend(se,a,'free',INVEST):raise ValueError('ending Soul Investment needs an own-turn Free Action')
        end_binding(se,a,a.spec[BIND])
    return G.transition(e,actor,apply)


def before_revoke(e,actor,sources):
    ledger=actor.spec.get(G.KEY,{}).get('sources',{})
    if any(ledger.get(sid,{}).get('static_acquisition',{}).get('feature_id')==INVEST for sid in sources):
        end_binding(e,actor,actor.spec[BIND])


def _cost_facts(completion):
    state=completion['arcanist'];payment=deepcopy(state['payment'])
    if payment:payment.pop('refunded',None)
    return {'completion':completion['id'],'actor':completion['actor'].entity_id,'move_id':completion['move_id'],
            'round':completion['round'],'turn_serial':completion['turn_serial'],
            **{k:deepcopy(state[k]) for k in ('choice','key','activation_before','limited','ap','tick','move_uses_before','move_occurrence_before','last_move_before')},'payment':payment}


def validate_completion(completion):
    state=completion['arcanist'];choice=state['choice']
    if state['cost_proof']!=__import__('root_resolution').fingerprint(_cost_facts(completion)):
        raise ValueError('Arcanist activation/payment receipt changed')
    if choice!=completion['move'].get(MARK) or choice['actor_id']!=completion['actor'].entity_id or choice['move_id']!=completion['move_id']:
        raise ValueError('Arcanist activation lost its actual Move')
    expected_ap=int(RANKS[choice['manipulation']]==1 and choice['signature_rank']is None)
    if state['ap']!=expected_ap or bool(state['payment'])!=bool(expected_ap) or (expected_ap and (state['payment']['amount']!=1 or state['payment']['refunded']!=state['recouped'])):
        raise ValueError('Arcanist actual spend/refund receipt changed')
    if any(type(state[k])is not bool for k in ('limited','recouped','overdrive_paid')):raise ValueError('Arcanist native completion flags changed')


def validate_temporary_refund(e,actor,grant,index):
    ref={'grant_id':grant['id'],'index':index,'amount':grant['payments'][index]['amount']}
    matches=[r for r in getattr(e,'_move_completions',{}).values() if r['actor']is actor and
             r.get('arcanist',{}).get('recouped') and ref in (r['arcanist'].get('payment')or{}).get('temporary',())]
    if len(matches)!=1:raise ValueError('refunded temporary AP requires its actual unique native Recoup completion')
    validate_completion(matches[0]);_require_native_misses(e,matches[0])


def validate_world(e,index):
    import optional_weapon_framework as FW,combat_timing as T
    import move_completion as COMPLETE
    for completion in getattr(e,'_move_completions',{}).values():
        if completion.get('arcanist'):validate_completion(completion)
    for actor in index.values():
        row=actor.spec.get(BIND)
        if row is not None:
            if type(row)is not dict or set(row)!={'instance','instance_id','moves','source'} or row['source']!=INVEST:raise ValueError('Soul Investment identity changed')
            binding(e,actor)
            if actor.spec.get(FW.BONDS,{}).get('arcane',{}).get('instance_id')!=row['instance_id']:raise ValueError('Soul Investment lost its actual Soul Bond')
            FW.object_profile(e,row['instance_id'],usable=False)
            if type(row['moves'])is not list or len(row['moves'])!=2 or len(set(row['moves']))!=2 or any(FW.policy(e.r)['arcane_moves'].get(mid,{}).get('rank')!=rank for mid,rank in zip(row['moves'],(3,5))):
                raise ValueError('Soul Investment lost its actual printed Move choices')
        for timed in T.records(actor):
            for key in ('arcanist_barrier','arcanist_link'):
                if key not in timed:continue
                data=timed[key];completion=getattr(e,'_move_completions',{}).get(data.get('completion'))
                if not completion or not completion.get('arcanist'):raise ValueError('Arcanist timed effect lost its native completion')
                if key=='arcanist_barrier' and (actor is not completion['actor'] or data['targets']!=[t.entity_id for t in completion['targets']] or data['value']!=completion['arcanist']['tick']):raise ValueError('Directed Barrier target/DR source changed')
                if key=='arcanist_link' and (actor not in COMPLETE.actual_recipients(completion) or data['type']!=completion['move']['type'] or data['policy']!=completion['arcanist']['choice']['link_policy'] or type(data['consumed'])is not bool):raise ValueError('Energy Link source changed')


def atomic_move(fn):
    @wraps(fn)
    def run(e,actor,*args,**kwargs):
        import combat_timing as T
        interested=hasattr(actor,'spec') and bool(actor.spec.get(ARM))
        interested=interested or any(any('arcanist_link'in r or 'arcanist_barrier'in r for r in T.records(a)) for a in W.actor_index(e).values())
        if not interested or getattr(e,'_arcanist_atomic',False):return fn(e,actor,*args,**kwargs)
        pending=[]
        def apply(se,a):
            copied_args,copied_kwargs=G._stage_transition_payload(e,se,(args,kwargs))
            se._arcanist_atomic=True
            try:return fn(se,a,*copied_args,**copied_kwargs)
            except Exception as error:
                if G.record_native_pending(se,error,pending):return None
                raise
            finally:del se._arcanist_atomic
        result=G.transition(e,actor,apply,include_grid=e.grid is not None,include_rulings=True)
        if pending:
            exception,event_id=pending[0];raise exception(event_id)
        return result
    return run
