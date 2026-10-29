"""One persisted completion boundary for an actual move's ordered targets.

Target returns and receipt-bound continuations are separate observations. Only
their real producer can start a target; refresh never repays or rerolls it.
"""
from copy import deepcopy
import root_resolution as R
import move_activation as ACTIVATION
KEY='_move_completions'


def field_effect(effect):
    """An explicitly adapted side effect owned by one area activation."""
    return isinstance(effect,dict) and effect.get('_activation_scope')=='field'


def field_effects(effects):
    return [effect for effect in effects if field_effect(effect)]


def recipient_result(row,target):
    """Actual hit consumers must not mistake a routed target return for a hit."""
    received=row.get('received',{}).get(target.entity_id)
    if received is not None:return received
    if target.entity_id in row.get('defense',{}):return None
    return row['results'].get(target.entity_id)


def event_move(e,event):
    """Prepared Move of this original target, also shared by its routed hits."""
    parent=e._passive_events[event['defense_parent']] if event.get('defense_parent') else event
    row=getattr(e,KEY)[parent['completion_id']]
    if 'target_moves' not in row:return row['move']
    move=row['target_moves'].get(parent['target'].entity_id)
    if move is None:raise ValueError('actual prepared target Move missing')
    return move


def actual_recipients(row):
    result={t.entity_id:t for t in row['targets'] if recipient_result(row,t) is not None}
    result.update({uid:entry['actor'] for uid,entry in row.get('received',{}).items()})
    return list(result.values())


def _substitute_application(target,receipt):
    import substitute as SUB
    rows=[(r,False) for r in target.coats]+[(r,True) for r in target.spec.get('effect_instance_history',[])]
    found=[(r,terminal) for r,terminal in rows if r.get('id')==receipt['coat_id'] and r.get('source')==SUB.SOURCE]
    if len(found)!=1:raise ValueError('actual Substitute damage coat required')
    coat,terminal=found[0];SUB.validate(target,coat,terminal=terminal)
    index=receipt['application_index']
    if type(index) is not int or not 0<=index<len(coat['applications']):
        raise ValueError('actual Substitute damage application required')
    return coat['applications'][index]


def record_substitute_damage(e,actor,target,completion_id,event_id,observation,*,native_context,move):
    """Keep the native coat damage separately from the prevented creature hit."""
    row=getattr(e,KEY,{}).get(completion_id);event=getattr(e,'_passive_events',{}).get(event_id)
    if row is None or row['phase']!='targets' or row['actor'] is not actor or native_context is None:
        raise ValueError('actual native Substitute damage producer required')
    __import__('heavy_injury_adapter').validate_native_receipt(e,native_context,actor,target,move)
    if event_id is not None:
        if (event is None or event['actor'] is not actor or event['target'] is not target
                or event['completion_id']!=completion_id or event['move_id']!=row['move_id']):
            raise ValueError('actual native Substitute event required')
    elif target not in row['targets'] or target.entity_id not in row['started']:
        raise ValueError('actual started Substitute recipient required')
    if type(observation.get('damage')) is not int or observation['damage']<0:
        raise ValueError('actual nonnegative Substitute damage required')
    import substitute as SUB
    coats=[r for r in [*target.coats,*target.spec.get('effect_instance_history',[])]
           if r.get('id')==observation['coat_id'] and r.get('source')==SUB.SOURCE]
    if len(coats)!=1:raise ValueError('actual native Substitute damage coat required')
    number=len(coats[0]['applications'])-1
    application=coats[0]['applications'][number]
    if (application['actor_id']!=actor.entity_id or application['holder_id']!=target.entity_id
            or application['move_id']!=row['move_id'] or application['damage']!=observation['damage']
            or application['after']!=observation['remaining_hp']):
        raise ValueError('actual just-applied Substitute damage required')
    receipt={'completion_id':completion_id,'event_id':event_id,'coat_id':observation['coat_id'],
             'application_index':number,'application':deepcopy(application)}
    records=row.setdefault('substitute_damage_receipts',{})
    previous=records.get(target.entity_id)
    if previous is not None and previous!=receipt:raise ValueError('native Substitute damage changed')
    records[target.entity_id]=deepcopy(receipt)
    if event is not None:event['substitute_damage']=deepcopy(receipt)
    return receipt


def substitute_damage(e,row,target,result):
    receipt=result.get('substitute_damage')
    if receipt is None:return 0
    if (type(receipt) is not dict or set(receipt)!={'completion_id','event_id','coat_id','application_index','application'}
            or receipt['completion_id']!=row['id'] or result['dealt']!=0 or result.get('hit_prevented') is not True):
        raise ValueError('separate prevented-hit Substitute damage receipt required')
    if row.get('substitute_damage_receipts',{}).get(target.entity_id)!=receipt:
        raise ValueError('Substitute damage receipt belongs to another native recipient')
    if receipt['event_id'] is not None:
        event=getattr(e,'_passive_events',{}).get(receipt['event_id'])
        if (event is None or event['actor'] is not row['actor'] or event['target'] is not target
                or event['completion_id']!=row['id'] or event['move_id']!=row['move_id']
                or event.get('substitute_damage')!=receipt):
            raise ValueError('Substitute damage receipt belongs to another native event')
    application=_substitute_application(target,receipt)
    if (application!=receipt['application'] or application['actor_id']!=row['actor'].entity_id
            or application['holder_id']!=target.entity_id or application['move_id']!=row['move_id']):
        raise ValueError('actual Substitute damage application changed')
    return application['damage']


def observed_damage(e,row,target,result):
    if result.get('cancelled'):return None
    if result.get('substitute_damage') is not None:return substitute_damage(e,row,target,result)
    return None if result.get('hit_prevented') else result['dealt']


def record_return(e,event_id,*,hit_prevented):
    """Native producer tail, after recipient listeners and reactive effects."""
    if event_id is None:return
    import passive_events as EVENTS
    event=e._passive_events[event_id];row=getattr(e,KEY)[event['completion_id']]
    if (event['phase']!='producer_return_boundary' or
            event['status'] not in ('applied','inapplicable') or type(hit_prevented) is not bool):
        raise ValueError('actual native recipient return required')
    facts={'event_id':event_id,'completion_id':row['id'],
           'attacker_id':event['actor'].entity_id,'recipient_id':event['target'].entity_id,
           'hit_prevented':hit_prevented,'observations':deepcopy(EVENTS.observations(e,event_id)),
           'turn_serial':event['actor'].custom_conditions.get('combat_turn_serial',0),
           'action_history':list(getattr(event['actor'],'_action_history',[]))}
    old=row.setdefault('native_returns',{}).get(event_id)
    if old is not None:
        if old['facts']!=facts:raise ValueError('native returned recipient facts changed')
        refresh(e,row['id'])
        return
    row['native_returns'][event_id]={'facts':facts,'fingerprint':R.fingerprint(facts)}
    import ace_trainer as ACE
    recipient=event['target'];actual=recipient_result(row,recipient)
    ACE.after_target(e,row,recipient)
    __import__('arcanist').after_target(e,row,recipient)
    if event.get('defense_parent') and actual and actual['hit'] and not actual.get('cancelled') and not hit_prevented:
        __import__('csv_item_form_contracts').move_hit(e,recipient,event_move(e,event))
    if actual and actual['hit'] and not actual.get('cancelled') and event_move(e,event).get('class') in ('물리','특수'):
        ACE.after_damaging_hit(e,recipient,row['id'])
    import ability_reaction_choices as REACTIONS
    REACTIONS.observe_return(e,event_id)
    import gleeful_interference as GLEEFUL
    GLEEFUL.after_move(e,row)
    __import__("roughneck").after_move(e,row)
    refresh(e,row['id'])


def require_returned_event(e,event_id,*,_recipient_only=False):
    """Join an observed recipient return to the finished whole Move.

    This read-only receipt does not select a reaction, its payment, or its
    priority. A recipient return alone can precede later targets and effects.
    """
    import passive_events as EVENTS
    import action_lifecycle as ACTION
    import move_defense_reactions as DEFENSE
    event=getattr(e,'_passive_events',{}).get(event_id)
    if (event is None or event.get('producer') not in
            ('Engine.use_move','Engine.use_move/defense-recipient') or
            event.get('phase')!='producer_return_boundary' or
            event.get('status') not in ('applied','inapplicable')):
        raise ValueError('actual returned Move event required')
    row=getattr(e,KEY,{}).get(event.get('completion_id'))
    if (row is None or row['actor'] is not event['actor'] or
            row['move_id']!=event['move_id'] or row['round']!=event['round'] or
            row['seconds']!=event['elapsed_seconds'] or (not _recipient_only and
            (row['phase']!='complete' or not row['sealed'] or
             set(row['results'])!={t.entity_id for t in row['targets']} or ACTION.pending_resolution_effects(e,row)))):
        raise ValueError('whole Move targets and completion effects must have returned')
    parent_id=event.get('defense_parent',event_id)
    parent=e._passive_events.get(parent_id)
    if (parent is None or parent['producer']!='Engine.use_move' or
            parent['completion_id']!=row['id'] or parent['actor'] is not row['actor'] or
            parent['target'] not in row['targets'] or (not _recipient_only and
            (parent['phase']!='producer_return_boundary' or parent['status'] not in ('applied','inapplicable')))):
        raise ValueError('actual parent Move return required')
    if event_id!=parent_id:
        received=row.get('received',{}).get(event['target'].entity_id)
        if (received is None or received['actor'] is not event['target'] or
                received['event_id']!=parent_id or received['child_event']!=event_id):
            raise ValueError('routed return requires the actual recipient receipt')
    observations=EVENTS.observations(e,event_id)
    if not observations or observations[-1]['stage']!='resolved':
        raise ValueError('native resolved Move observation required')
    returned=row.get('native_returns',{}).get(event_id)
    if returned is None:
        raise ValueError('native recipient producer tail has not returned')
    facts=returned['facts']
    if (returned['fingerprint']!=R.fingerprint(facts) or facts['event_id']!=event_id or
            facts['completion_id']!=row['id'] or facts['attacker_id']!=row['actor'].entity_id or
            facts['recipient_id']!=event['target'].entity_id or facts['observations']!=observations or
            type(facts['hit_prevented']) is not bool):
        raise ValueError('native recipient return facts changed')
    return {'event_id':event_id,'parent_event_id':parent_id,'completion_id':row['id'],
            'attacker_id':row['actor'].entity_id,'recipient_id':event['target'].entity_id,
            'move':DEFENSE._move_facts(event_move(e,event)),
            'targets':[target.entity_id for target in row['targets']],
            'results':deepcopy(row['results']),
            'effects':[{'source':e._effect_dispatch_receipts[token]['source_id'],
                        'occurrence':e._effect_dispatch_receipts[token]['occurrence'],
                        'fingerprint':e._effect_dispatch_receipts[token]['fingerprint'],
                        'status':e._effect_dispatch_receipts[token]['status'],
                        'actor_id':e._effect_dispatch_receipts[token]['actor'].entity_id,
                        'target_id':e._effect_dispatch_receipts[token]['target'].entity_id}
                       for token in row['effects']],
            'completed_at':row.get('completed_at'),'observations':deepcopy(observations),
            'native_return':deepcopy(facts)}


def require_hit_return(e,event_id,recipient,*,_recipient_only=False):
    """Require an actual hit recipient, not the original Intercept target."""
    import world_entities as WORLD
    WORLD.require_actors(e,recipient)
    receipt=require_returned_event(e,event_id,_recipient_only=_recipient_only)
    event=e._passive_events[event_id];row=getattr(e,KEY)[receipt['completion_id']]
    result=recipient_result(row,recipient)
    if (event['target'] is not recipient or result is None or not result['hit'] or
            result.get('cancelled') or receipt['native_return']['hit_prevented'] or event['hit'] is not True):
        raise ValueError('actual successful nonprevented recipient hit required')
    if recipient.entity_id in row.get('received',{}):
        if result['child_event']!=event_id:
            raise ValueError('use the actual routed recipient event')
    receipt['result']={key:result.get(key,False) for key in
                       ('hit','dealt','cancelled','hit_prevented')}
    receipt['result']['hit_prevented']=receipt['native_return']['hit_prevented']
    return receipt


def require_recipient_hit_return(e,event_id,recipient):
    """A returned hit may trigger Cavalier before other area recipients return."""
    return require_hit_return(e,event_id,recipient,_recipient_only=True)


def after_damage_self_stage(rules,move,effect):
    """Exact printed user stat costs, once after the applicable recipient damage."""
    if rules is None or not isinstance(move,dict) or not isinstance(effect,dict):return False
    sources={
        'move/용성군':('피해량 계산이후 사용자의 특수공격 전투단계를 -2만큼 하락시킵니다.',{'spa':-2}),
        'move/오버히트':('피해량 계산이후 사용자의 특수공격 전투단계가 -2만큼 하락합니다.',{'spa':-2}),
        'move/리프스톰':('피해량 계산이후 사용자의 특수공격 전투단계를 -2만큼 하락시킵니다.',{'spa':-2}),
        'move/플뢰르캐논':('피해량 계산 이후 사용자의 특수공격 전투단계가 -2만큼 하락합니다.',{'spa':-2}),
        'move/사이코부스트':('피해량 처리한 후사용자의 특수공격 전투단계가 -2만큼 하락한다.',{'spa':-2}),
        'move/v제너레이트':('사용자의 방어, 특수방어, 스피드 전투단계 모두 -1만큼 하락합니다.',{'def':-1,'spd':-1,'spe':-1}),
        'move/인파이트':('피해량 계산 이후 사용자의 방어, 특수방어 전투단계가 모두 -1씩 하락합니다.',{'def':-1,'spd':-1}),
        'move/엄청난힘':('엄청난힘을 사용하면 사용자의 공격과 방어 전투단계가 모두 -1만큼 하락합니다.',{'atk':-1,'def':-1}),
        'move/스케일노이즈':('스케일노이즈의 피해 굴림에 방어 스탯의 절반만큼 더합니다. 기술이 처리된 이후 사용자의 방어 전투단계가 -1만큼 하락합니다.',{'def':-1}),
    }
    mid=move.get('id')
    if mid not in sources:return False
    text,changes=sources[mid];stat=effect.get('stat')
    if stat not in changes:return False
    expected={'type':'stage_change','stat':stat,'delta':changes[stat],'target':'self'}
    if {key:value for key,value in effect.items() if not key.startswith('_')}!=expected:return False
    if rules._selected_rule(mid)!=mid or rules.move(mid).get('effect')!=text:
        raise ValueError('printed after-damage self-stage source changed')
    return True


def after_all(effect,rules=None,move=None):
    post_stage=False
    if rules is not None and move is not None:
        import post_resolution_stage_effects as POST_STAGE
        post_stage=POST_STAGE.owns(rules,move,effect)
    focus_after=rules is not None and __import__('declarative_move_contracts').after_all(rules,effect)
    sacrifice=rules is not None and move is not None and __import__('hp_setting_moves').after_all(rules,move,effect)
    local_mist=rules is not None and move is not None and __import__('misty_explosion').after_all(rules,move,effect)
    return (sacrifice or local_mist or focus_after or post_stage or after_damage_self_stage(rules,move,effect) or field_effect(effect) or
            (effect.get('type') in ('counter','stage_change') and effect.get('on')=='after use' and effect.get('target','self')=='self') or
            (effect.get('type')=='type_change' and effect.get('target','self')=='self'))


def start_target(e,actor,target,move,mm,scope):
    rows=getattr(e,KEY,None)
    if rows is None:rows={};setattr(e,KEY,rows)
    token=scope.get('completion_id') if scope else None
    if token is None:
        import world_entities as W
        memo={id(a):a for a in W.actor_index(e).values()}
        token='move-complete:'+str(len(rows)+1)
        targets=list(scope['targets']) if scope else [target]
        rows[token]={'id':token,'actor':actor,'move_id':move['id'],'targets':targets,
            'profile':ACTIVATION._profile(e),
            'move':deepcopy(move,memo),'post_effects':deepcopy([x for x in mm.get('effects_exec',[]) if after_all(x,e.r,move)]),
            'started':[],'target_moves':{},'results':{},'effects':[],'sealed':scope is None,'phase':'targets',
            'round':e.round_no,'seconds':e.elapsed_seconds,'turn_serial':actor.custom_conditions.get('combat_turn_serial',0),
            'full_turn':__import__('action_lifecycle').current_full_turn(e)}
        __import__('hp_setting_moves').begin_move(e,rows[token])
        action=getattr(e,'_native_action_stack',[])
        if action and action[-1]['actor'] is actor and action[-1]['kind']=='move':
            rows[token]['native_action_frame']=action[-1]
            action[-1]['completion_id']=token
        import cheerleader as CHEER
        rows[token]['cheerleader_support']=CHEER.support_snapshot(e,actor) if move.get('class')=='변화' else None
        __import__('coordinator').begin_move(e,rows[token])
        __import__("provocateur").begin_move(e,rows[token])
        __import__('hex_maniac').begin_move(e,rows[token])
        __import__('rogue').begin_move(e,rows[token])
        __import__('trickster').begin_move(e,rows[token])
        __import__("tumbler").begin_move(e,rows[token])
        __import__('focus_punch').begin_move(e,rows[token])
        __import__('ace_trainer').begin_move(e,rows[token])
        import duelist as DUELIST
        DUELIST.begin_move(e,rows[token])
        import style_expert as STYLE
        STYLE.begin_move(e,rows[token])
        __import__('arcanist').begin_move(e,rows[token])
        __import__('marksman').begin_move(e,rows[token])
        __import__('fortress').begin_move(e,rows[token])
        __import__('skirmisher').begin_move(e,rows[token])
        import move_coins as COINS
        COINS.begin(e,rows[token])
        import confusion_attacks as CONFUSION
        CONFUSION.begin(e,rows[token])
        import ice_lake as ICE_LAKE
        ICE_LAKE.bind_move(e,rows[token])
        import equipment_variant_contracts as EQUIPMENT_VARIANTS
        EQUIPMENT_VARIANTS.begin_move_use(e,actor,target,move['id'])
        if scope is not None:scope['completion_id']=token
    row=rows[token]
    if row['actor'] is not actor or row['move_id']!=move['id'] or target not in row['targets']:
        raise ValueError('actual move completion participant mismatch')
    if target.entity_id in row['started']:raise ValueError('move target already activated')
    row['started'].append(target.entity_id)
    if 'target_moves' in row:
        import world_entities as W
        memo={id(a):a for a in W.actor_index(e).values()}
        row['target_moves'][target.entity_id]=deepcopy(move,memo)
    __import__('battle_contest').bind_move(e,row)
    return token


def finish_target(e,token,actor,target,*,hit,dealt,effects=(),cancelled=False,hit_prevented=False,substitute_damage_receipt=None,_defer_completion=False):
    if type(_defer_completion) is not bool or (_defer_completion and not cancelled):
        raise ValueError('only an actual cancellation may defer its completion hooks')
    if token is None:return
    row=getattr(e,KEY)[token]
    if row['actor'] is not actor or target.entity_id not in row['started']:
        raise ValueError('actual target activation required for completion')
    cancelled=cancelled or row.get('drown_out',{}).get('cancelled',False)
    result={'hit':bool(hit) and not hit_prevented,'dealt':dealt,'cancelled':bool(cancelled)}
    if hit_prevented:result['hit_prevented']=True
    if substitute_damage_receipt is not None:
        result['substitute_damage']=deepcopy(substitute_damage_receipt)
        substitute_damage(e,row,target,result)
    old=row['results'].get(target.entity_id)
    if old is not None:
        if old!=result:raise ValueError('completed target observation changed')
        return row if _defer_completion else refresh(e,token)
    row['results'][target.entity_id]=result
    __import__('arcanist').after_target(e,row,target)
    __import__('ace_trainer').after_target(e,row,target)
    if result['hit'] and not result['cancelled'] and row['move'].get('class') in ('물리','특수'):
        __import__('ace_trainer').after_damaging_hit(e,target,token)
    __import__('channeler').completion_hit(e,row,target)
    import optional_weapon_framework as FRAMEWORK
    if target.entity_id not in row.get('defense',{}) and target.entity_id not in row.get('recipient_aliases',{}):
        FRAMEWORK.observe_hit(e,row,actor,target)
        if result['hit'] and not result['cancelled'] and not hit_prevented:
            __import__('csv_item_form_contracts').move_hit(e,target,row.get('target_moves',{}).get(target.entity_id,row['move']))
    row['effects'].extend(x for x in effects if x not in row['effects'])
    return row if _defer_completion else refresh(e,token)


def seal(e,scope,*,interrupted=False):
    token=scope.get('completion_id')
    if token is None or token not in getattr(e,KEY,{}):return
    row=getattr(e,KEY)[token];row['sealed']=True
    if interrupted and row['phase']=='complete' and __import__('combat_move_reactions').pending_for_completion(e,token):return row
    if interrupted:row['phase']='interrupted';return
    # Refused targets were never activated and have no attack to replay.
    for target in row['targets']:
        if target.entity_id not in row['started']:
            row['results'][target.entity_id]={'hit':False,'dealt':0,'cancelled':True}
    return refresh(e,token)


def defer(effects,ctx):
    import equipment_variant_contracts as EQUIPMENT_VARIANTS
    effects=EQUIPMENT_VARIANTS.filter_move_effects(ctx,effects)
    rules=ctx.get('engine').r if ctx.get('engine') is not None else None
    move=ctx.get('move')
    return [x for x in effects if not after_all(x,rules,move)] if ctx.get('move_completion') and not ctx.get('after_all_targets') else effects


def authorized(e,ctx):
    row=getattr(e,KEY,{}).get(ctx.get('move_completion'))
    return bool(row and row['phase']=='applying' and row['sealed'] and
                row['actor'] is ctx.get('attacker') and
                all(t.entity_id in row['results'] for t in row['targets']))


def self_stage_damage_ready(e,row):
    """Non-Smite effects require a hit; a real Substitute hit keeps user costs."""
    hit_only=row['move_id'] in ('move/인파이트','move/엄청난힘','move/스케일노이즈')
    for target in actual_recipients(row):
        result=recipient_result(row,target)
        if observed_damage(e,row,target,result) is None:continue
        if hit_only and not (result['hit'] or result.get('substitute_damage')):continue
        return True
    return False


def authorized_after_damage_self_stage(e,ctx,effect,source):
    row=getattr(e,KEY,{}).get(ctx.get('move_completion'))
    return bool(ctx.get('after_all_targets') and authorized(e,ctx) and
                source==row['move_id'] and ctx.get('move',{}).get('id')==source and
                any(ctx.get('target') is target for target in row['targets']) and
                after_damage_self_stage(e.r,row['move'],effect) and
                effect in row['post_effects'] and
                self_stage_damage_ready(e,row))


def authorized_field(e,ctx,effect):
    row=getattr(e,KEY,{}).get(ctx.get('move_completion'))
    return bool(field_effect(effect) and authorized(e,ctx) and
                any(candidate==effect for candidate in row.get('post_effects',())))


def apply_empty_field(e,actor,move,effects,cells):
    """Complete target-free field consequences without inventing a hit result."""
    effects=list(effects);cells=tuple(sorted(set(cells)))
    import ice_lake as ICE_LAKE
    ice=ICE_LAKE.empty_area_adopted(e,actor,move)
    if (not effects and not ice) or any(not field_effect(effect) for effect in effects):
        raise ValueError('empty area activation requires explicit field effects')
    if not cells:raise ValueError('empty area activation requires actual area cells')
    rows=getattr(e,KEY,None)
    if rows is None:rows={};setattr(e,KEY,rows)
    token='move-complete:'+str(len(rows)+1)
    if token in rows:raise ValueError('move completion identity collision')
    import world_entities as W
    memo={id(candidate):candidate for candidate in W.actor_index(e).values()}
    row={'id':token,'actor':actor,'move_id':move['id'],'targets':[],
         'profile':ACTIVATION._profile(e),
         'move':deepcopy(move,memo),'post_effects':deepcopy(effects),'started':[],
         'results':{},'effects':[],'sealed':True,'phase':'applying',
         'activation':'empty_area_field','field_cells':cells,
         'round':e.round_no,'seconds':e.elapsed_seconds,'turn_serial':actor.custom_conditions.get('combat_turn_serial',0),
            'full_turn':__import__('action_lifecycle').current_full_turn(e)}
    rows[token]=row
    action=getattr(e,'_native_action_stack',[])
    if action and action[-1]['actor'] is actor and action[-1]['kind']=='move':
        row['native_action_frame']=action[-1]
        action[-1]['completion_id']=token
    import optional_state_effect_contracts as OPTIONAL_STATE
    OPTIONAL_STATE.begin_move(e,actor,None,move,token)
    __import__('provocateur').begin_move(e,row)
    __import__('trickster').begin_move(e,row)
    ICE_LAKE.bind_move(e,row)
    import confusion_attacks as CONFUSION
    CONFUSION.begin(e,row)
    import reactive_ability_events as REACTIVE
    REACTIVE.begin_move(e,actor,actor,move,token)
    before=set(getattr(e,'_effect_dispatch_receipts',{}))
    import effects as FX
    try:
        result=FX.run_effects(e,actor,actor,effects,
            {'move_completion':token,'after_all_targets':True,'field_activation':True,
             'hit':None,'nat':None,'dealt':0,'move':move,'crit':False},move['id'])
        if result[1] or result.pending:
            raise ValueError('target-free field effects did not complete')
    except Exception:
        row['phase']='interrupted'
        raise
    row['effects'].extend(key for key in getattr(e,'_effect_dispatch_receipts',{})
                          if key not in before and key not in row['effects'])
    row['phase']='completion_effects'
    CONFUSION.finish(e,row)
    ICE_LAKE.observe_completion(e,row)
    row['phase']='complete';row['completed_at']=e.elapsed_seconds
    __import__('musician').after_empty_use(e,actor,row)
    __import__('juggler').after_move(e,row)
    __import__('trickster').after_move(e,row)
    __import__('native_switch_transfer').observe_move(e,row)
    return row


def refresh(e,token=None):
    import action_lifecycle as ACTION
    import effects as FX
    rows=getattr(e,KEY,{})
    if token is None:
        for key in list(rows):refresh(e,key)
        return
    row=rows[token]
    if row['phase']=='complete':
        __import__('native_switch_transfer').observe_move(e,row)
        __import__('battle_contest').complete_move(e,row)
        return row
    if row['phase'] in ('interrupted','applying'):return row
    if not row['sealed'] or any(t.entity_id not in row['results'] for t in row['targets']):return row
    if ACTION.pending_resolution_effects(e,row):return row
    if row['phase']=='completion_effects':
        import ice_lake as ICE_LAKE
        ICE_LAKE.observe_completion(e,row)
        import move_coins as COINS
        COINS.observe_completion(e,row)
        import stellar_tera_blast as STELLAR_TERA
        STELLAR_TERA.observe_completion(e,row)
        import confusion_attacks as CONFUSION
        CONFUSION.finish(e,row)
        import improvised_weapons as IMPROVISED
        IMPROVISED.observe_completion(e,row)
        row['phase']='complete';row['completed_at']=e.elapsed_seconds
        __import__('fortress').completed(e,row)
        __import__('skirmisher').after_move(e,row)
        issue_disruption_window(e,row)
        __import__('commander_orders').mark_complete(e,row)
        __import__('musician').after_completion(e,row)
        __import__('rogue').after_move(e,row)
        __import__('trickster').after_move(e,row)
        import duelist as DUELIST
        DUELIST.after_move(e,row)
        import cheerleader as CHEER
        CHEER.after_move(e,row)
        import gleeful_interference as GLEEFUL
        GLEEFUL.after_move(e,row)
        __import__("roughneck").after_move(e,row)
        import style_expert as STYLE
        STYLE.after_move(e,row)
        __import__('type_ace').after_move(e,row)
        __import__('ace_trainer').after_move(e,row)
        __import__('martial_artist').after_move(e,row)
        __import__('type_ace').clear_fire(e,row)
        __import__('type_ace').cleanup_permissions(e,row)
        __import__('provocateur').after_move(e,row)
        __import__('tumbler').after_move(e,row)
        __import__('jump_move_actions').completed(e,row['actor'],row['move'],row['id'])
        if row['move_id']==__import__('tumbler').ACROBATICS:row['actor'].spec.pop('tumbler_acrobatics_choice',None)
        __import__('combat_move_reactions').after_move(e,row)
        __import__('coordinator').after_move(e,row)
        __import__('commander_orders').after_completion(e,row)
        __import__('juggler').after_move(e,row)
        __import__('conquerors_march').after_move(e,row)
        __import__('native_switch_transfer').observe_move(e,row)
        __import__('ability_control_contracts').after_move(e,row['actor'],row['move'])
        __import__('marksman').after_complete(e,row)
        return refresh(e,token)
    profile=ACTIVATION._profile(e)
    if row['profile']!=profile or e.r._selected_rule(row['move_id'])!=row['move_id']:
        raise ValueError('selected move completion policy changed')
    hit=any(x['hit'] and not x['cancelled'] for x in row['results'].values())
    after_damage=self_stage_damage_ready(e,row)
    all_cancelled=all(x['cancelled'] for x in row['results'].values())
    # Ordinary self effects preserve their hit requirement; an explicitly
    # after-use counter also advances on a genuine miss, never a refusal.
    import post_resolution_stage_effects as POST_STAGE
    post=[x for x in row['post_effects'] if not all_cancelled and
          (hit or after_damage and after_damage_self_stage(e.r,row['move'],x) or __import__('hp_setting_moves').after_all(e.r,row['move'],x) or __import__('misty_explosion').after_all(e.r,row['move'],x) or field_effect(x) or POST_STAGE.owns(e.r,row['move'],x) or
           __import__('declarative_move_contracts').after_all(e.r,x) or
           x.get('on')=='after use' or x.get('on_miss'))]
    stage_post=[x for x in post if POST_STAGE.owns(e.r,row['move'],x)]
    post=[x for x in post if x not in stage_post]
    before=set(getattr(e,'_effect_dispatch_receipts',{}))
    row['phase']='applying'
    try:
        actor=row['actor'];target=row['targets'][-1]
        FX.run_effects(e,actor,target,post,{'move_completion':token,'after_all_targets':True,
            'hit':hit,'nat':None,'dealt':sum(x['dealt'] for x in row['results'].values()),
            'move':row['move'],'crit':False},row['move_id'])
        POST_STAGE.apply_completion(e,row,stage_post)
        recoil=recoil_effect(e,row)
        if recoil is not None:
            FX.run_effects(e,actor,target,[recoil],{'move_completion':token,
                'native_recoil':token,'after_all_targets':True,'hit':True,'nat':None,
                'attacker':actor,'target':target,'engine':e,
                'move':row['move'],'crit':False},row['move_id'])
    except Exception:
        row['phase']='interrupted';raise
    row['effects'].extend(x for x in getattr(e,'_effect_dispatch_receipts',{}) if x not in before and x not in row['effects'])
    row['phase']='completion_effects'
    return refresh(e,token)


def recoil_effect(e,row):
    """Printed Recoil multiplies damage dealt, once after all native recipients."""
    import re
    import arithmetic_policy as M
    text=str(e.r.move(row['move_id']).get('range',''))
    matches=re.findall(r'(?:반동|Recoil)\s+(\d+)\s*/\s*(\d+)',text,re.I)
    if not matches:return None
    if len(matches)!=1:raise ValueError('one exact printed Recoil fraction required')
    numerator,denominator=map(int,matches[0])
    if numerator<=0 or denominator<=0:raise ValueError('positive printed Recoil fraction required')
    if e.r._selected_rule('keyword/반동')!='keyword/반동':
        raise ValueError('selected Recoil keyword needs its own numeric policy')
    M.validate_source(e.r)
    # Smite misses deal damage; Recoil is not a target on-hit effect.
    damage=sum(amount for actor in actual_recipients(row)
               if (amount:=observed_damage(e,row,actor,recipient_result(row,actor))) is not None)
    amount=M.ratio(damage*numerator,denominator)
    return {'type':'hp_loss','target':'self','value':amount} if amount else None


def apply_recoil_loss(e,actor,effect,context):
    row=getattr(e,KEY,{}).get(context.get('native_recoil'))
    if (row is None or row['actor'] is not actor or row['phase']!='applying'
            or not authorized(e,context) or effect!=recoil_effect(e,row)
            or context.get('source_id')!=row['move_id']):
        raise ValueError('actual native all-recipient Recoil required')
    import effect_contracts as EC
    EC.validate_receipt(e,context['effect_receipt'],row['move_id'],
        context['effect_occurrence'],actor,context['target'],effect)
    import ability_transitions as ABILITIES
    passives=[*actor.modifiers,*actor.registry]
    for passive in passives:
        ignored=passive.get('type')=='ignore_effects' and passive.get('ignore_keyword') in ('반동','Recoil')
        immune=passive.get('type')=='immunity' and any(x in ('반동','Recoil') for x in
            (passive.get('to',[]) if isinstance(passive.get('to'),list) else [passive.get('to')]))
        if (ignored or immune) and ABILITIES.effect_active(actor,passive):
            source=passive.get('_rule_id')
            if not isinstance(source,str) or e.r._selected_rule(source)!=source:
                raise ValueError('selected native Recoil protection required')
            return
    e.lose_hp(actor,effect['value'],source='keyword/반동')


def validate_return_continuation(e,event):
    """The signed return declaration has either an executable tail or a return."""
    if 'return_fingerprint' not in event:return
    import passive_events as EVENTS
    row=getattr(e,KEY,{}).get(event.get('completion_id'));frame=event.get('continuation')
    EVENTS._bind_intent(e,event)
    if row is None:raise ValueError('native recipient return lacks its completion')
    if event['id'] in row.get('native_returns',{}):
        if frame is not None:raise ValueError('returned recipient retains executable continuation')
    elif (not isinstance(frame,dict) or frame.get('kind')!='recipient_return' or
            event['return_fingerprint']!=frame.get('fingerprint') or
            R.fingerprint(EVENTS._continuation_facts(e,event,frame))!=frame['fingerprint']):
        raise ValueError('native recipient return lost its authenticated continuation')


def validate_world(e,index):
    __import__('fortress').validate_world(e,index)
    __import__('hp_setting_moves').validate_world(e,index)
    __import__('coordinator').validate_world(e,index)
    __import__('ace_trainer').validate_world(e,index)
    __import__('aura_guardian').validate_world(e,index)
    __import__('focus_punch').validate_world(e,index)
    __import__("endure").validate(e,index)
    __import__("roughneck").validate_world(e,index)
    import confusion_attacks as CONFUSION
    CONFUSION.validate_actions(e,index)
    rows=getattr(e,KEY,{})
    if type(rows) is not dict:raise ValueError('move completion mapping required')
    validate_disruption_windows(e,index)
    for token,row in rows.items():
        import action_lifecycle as ACTION
        ACTION.move_frame(e,row)
        import confusion_attacks as CONFUSION
        CONFUSION.validate(row)
        if row.get('id')!=token or row.get('phase') not in ('targets','applying','completion_effects','complete','interrupted'):
            raise ValueError('identified move completion phase required')
        if index.get(row['actor'].entity_id) is not row['actor']:
            raise ValueError('actual move completion actor required')
        if row.get('activation')=='empty_area_field':
            misty_applying=__import__('misty_explosion').empty_applying(e,row)
            if (row['phase'] not in ('completion_effects','complete') and not misty_applying or not row['sealed'] or row['targets'] or
                    row['started'] or row['results'] or not row.get('field_cells') or
                    (not row.get('post_effects') and not row.get('_ice_lake')) or
                    any(not field_effect(effect) for effect in row['post_effects'])):
                raise ValueError('completed empty-area field activation evidence required')
            continue
        if not row['targets']:
            raise ValueError('actual move completion targets required')
        ids=[t.entity_id for t in row['targets']]
        if len(set(ids))!=len(ids) or any(index.get(t.entity_id) is not t for t in row['targets']):
            raise ValueError('distinct actual move completion targets required')
        if 'target_moves' in row and (set(row['target_moves'])!=set(row['started'])
                or any(move.get('id')!=row['move_id'] for move in row['target_moves'].values())):
            raise ValueError('prepared target Moves require their actual native starts')
        if not set(row['started'])<=set(ids) or not set(row['results'])<=set(ids):
            raise ValueError('move completion target evidence mismatch')
        if row['phase']=='complete' and (not row['sealed'] or set(row['results'])!=set(ids)):
            raise ValueError('completed move lacks actual target returns')
        for result in row['results'].values():
            if type(result['hit']) is not bool or type(result['cancelled']) is not bool or type(result['dealt']) is not int or result['dealt']<0:
                raise ValueError('actual move target result required')
        for uid,receipt in row.get('substitute_damage_receipts',{}).items():
            target=index.get(uid)
            if target is None:raise ValueError('actual Substitute recipient missing')
            result=recipient_result(row,target)
            if result is not None:
                if result.get('substitute_damage')!=receipt:raise ValueError('Substitute damage receipt missing from native result')
                substitute_damage(e,row,target,result)
            elif row['phase']=='complete':raise ValueError('completed Substitute damage lost its result')
    for event in getattr(e,'_passive_events',{}).values():
        validate_return_continuation(e,event)
        if event.get('substitute_damage') is not None:
            row=rows.get(event['completion_id'])
            result=None if row is None else recipient_result(row,event['target'])
            if result is not None:
                if result.get('substitute_damage')!=event['substitute_damage']:raise ValueError('Substitute damage receipt missing from native result')
                substitute_damage(e,row,event['target'],result)
            elif row is None or row['phase']=='complete':raise ValueError('completed Substitute damage lost its recipient result')
    pending_counts={}
    for pending in getattr(e,'delayed',[]):
        if not isinstance(pending,dict) or pending.get('kind')!='attack' or pending.get('src')!='delayed_attack':
            continue
        token=pending.get('completion_id');row=rows.get(token)
        if row is None:
            raise ValueError('delayed attack requires its actual move completion')
        actor=pending.get('attacker');target=pending.get('who')
        if (row['actor'] is not actor or pending.get('move_id')!=row['move_id'] or
                not any(candidate is target for candidate in row['targets'])):
            raise ValueError('delayed attack completion participant mismatch')
        target_id=getattr(target,'entity_id',None)
        if (row['phase']!='targets' or target_id not in row['started'] or
                target_id in row['results']):
            raise ValueError('pending delayed attack completion phase mismatch')
        mm,_=e.r.move_mech(row['move_id'])
        if not any(effect.get('type')=='delayed_attack' for effect in mm.get('effects_exec',[])):
            raise ValueError('delayed attack queue requires a delayed move completion')
        key=(token,target_id)
        pending_counts[key]=pending_counts.get(key,0)+1
        if pending_counts[key]!=1:
            raise ValueError('duplicate delayed attack completion queue')
    expected=set()
    for token,row in rows.items():
        if row['phase']!='targets':continue
        mm,_=e.r.move_mech(row['move_id'])
        if not any(effect.get('type')=='delayed_attack' for effect in mm.get('effects_exec',[])):
            continue
        expected.update((token,target_id) for target_id in row['started']
                        if target_id not in row['results'])
    if set(pending_counts)!=expected:
        raise ValueError('delayed attack completion requires exactly one pending queue per target')
    __import__('battle_contest').validate_world(e,index)


# A completion owns its trigger window; this actor field is only a live index.
DISRUPTION_WINDOWS = '_type_ace_disruption_windows'


def _disruption_owner(e, actor):
    import type_ace as TA
    return TA.owner(e, actor, TA.uid('Disruption Order'))


def _bug_hit(row):
    return (row.get('phase') == 'complete' and row.get('sealed') and
            row.get('move', {}).get('type') == '벌레' and any(
            result and result.get('hit') and not result.get('cancelled')
            for result in (recipient_result(row, t) for t in actual_recipients(row))))


def _window(e, row, *, legacy=False):
    import frequency as F
    boundary = row.get('skirmisher_boundary', {})
    value = {'version': 1, 'completion_id': row['id'],
             'full_turn': row.get('full_turn'),
             'seconds': boundary.get('seconds', e.elapsed_seconds),
             'scene': boundary.get('scene', F.state(row['actor'])['scene']),
             'closed_by': None, 'legacy': legacy}
    if legacy:
        history = list(getattr(row['actor'], '_action_history', []))
        before = boundary.get('history')
        related = row.get('trickster_maneuvers', [])
        # Old saves did not retain every action's parent. Only the exact current
        # native trigger plus its actual paid Trickster children proves migration.
        current = getattr(e, '_trickster_trigger', None) == row['id']
        explained = (isinstance(before, list) and history == before + ['free'] * len(related))
        if not current or not explained:
            value['closed_by'] = {'reason': 'legacy trigger lineage unavailable'}
    return value


def _window_current(e, row, window):
    import action_lifecycle as A, frequency as F
    return (window['full_turn'] == A.current_full_turn(e) and
            window['seconds'] == e.elapsed_seconds and
            window['scene'] == F.state(row['actor'])['scene'])


def _window_index(e, actor):
    value = actor.custom_conditions.get(DISRUPTION_WINDOWS)
    if value is None:
        return None
    if (type(value) is not list or any(type(token) is not str for token in value) or
            len(value) != len(set(value))):
        raise ValueError('native Disruption window index required')
    rows = getattr(e, KEY, {})
    for token in value:
        row = rows.get(token)
        if (row is None or row.get('actor') is not actor or
                'disruption_window' not in row or row['disruption_window'].get('closed_by') is not None):
            raise ValueError('Disruption index must reference its actual open completion')
    return value


def _legacy_windows(e, actor):
    # Only called once when a pre-window actor first records a native action.
    # Modern actors have an index even when it is empty.
    return [(row, _window(e, row, legacy=True)) for row in getattr(e, KEY, {}).values()
            if row.get('actor') is actor and _bug_hit(row) and 'disruption_window' not in row]


def issue_disruption_window(e, row):
    if not _bug_hit(row) or _disruption_owner(e, row['actor']) is None:
        return
    if 'disruption_window' in row:
        return
    actor = row['actor']
    ids = _window_index(e, actor)
    if ids is None:
        ids = []; actor.custom_conditions[DISRUPTION_WINDOWS] = ids
    row['disruption_window'] = _window(e, row)
    ids.append(row['id'])


def require_disruption_window(e, row):
    if not _bug_hit(row):
        raise ValueError('Disruption requires its actual native Bug hit')
    window = row.get('disruption_window')
    if window is None:
        window = _window(e, row, legacy=True)
    else:
        ids = _window_index(e, row['actor'])
        if ids is None or (window.get('closed_by') is None and row['id'] not in ids):
            raise ValueError('actual indexed Disruption trigger required')
    if window.get('closed_by') is not None or not _window_current(e, row, window):
        raise ValueError('Disruption Order requires its current native hit trigger window')
    return window


def completion_origins(e):
    """Only live native frames and issued source scopes identify a causal parent."""
    result = []
    rows = getattr(e, KEY, {})
    for grant in getattr(e, '_action_grants', ()):
        if len(grant) == 6 and grant[5] == 'native_completion_reaction':
            row = rows.get(grant[3])
            if row is None or row['actor'] is not grant[2]:
                raise ValueError('native completion reaction identity changed')
            result.append(row['id'])
            result.extend(row.get('native_action_frame', {}).get('trigger_origins', ()))
    for frame in getattr(e, '_native_action_stack', ()):
        validate_trigger_frame(e, frame)
        result.extend(frame.get('trigger_origins', ()))
        row = rows.get(frame.get('completion_id'))
        if row is not None and row.get('native_action_frame') is frame and row['phase'] == 'complete':
            result.append(row['id'])
    # A native Interrupt may resume without the issuing Python scope.
    interrupts = getattr(e, '_initiative_interrupts', {})
    for frame in interrupts.get('frames', ()):
        window = interrupts.get('windows', {}).get(frame.get('window_id'), {})
        trigger = window.get('trigger', {})
        if trigger.get('kind') == 'duelist_overflow':
            _, receipt = __import__('duelist').overflow_trigger(e, trigger['overflow_id'], allow_completed=True)
            parent = receipt.get('origin', {}).get('completion')
            if parent in rows:
                result.append(parent)
                result.extend(rows[parent].get('native_action_frame', {}).get('trigger_origins', ()))
    return list(dict.fromkeys(result))


def bind_trigger_frame(e, frame):
    # A live parent is context, not permission to start an arbitrary child.
    # Exact child declarations are issued by checked reaction producers. Moves
    # additionally enter through already authenticated Move grants/Interrupts.
    issued = []
    granted = False
    for grant in getattr(e, '_action_grants', ()):
        if len(grant) != 6:
            continue
        if grant[5] == 'native_completion_reaction':
            scope = grant[4]
            child = scope.get('child')
            if (child is not None and not scope['child_issued'] and child[0] is frame['actor'] and
                    child[1:] == (frame['kind'], frame['source'])):
                issued.append(scope)
        elif grant[1] is frame['actor'] and grant[3] == frame['source']:
            granted = granted or (frame['kind'] == 'move' and grant[5] != 'native_maneuver_child' or
                       frame['kind'] == 'maneuver' and grant[5] == 'native_maneuver_child')
    selected = __import__('initiative_interrupts').selected_move_frame(e, frame['actor'])
    interrupted = (frame['kind'] == 'move' and selected is not None and
                   selected[1]['move_id'] == frame['source'])
    if not (issued or granted or interrupted):
        return
    origins = completion_origins(e)
    if not origins:
        return
    for scope in issued:scope['child_issued'] = True
    frame['trigger_origins'] = origins
    for token in origins:
        row = getattr(e, KEY, {})[token]
        children = row.setdefault('trigger_children', [])
        if not any(child is frame for child in children):
            children.append(frame)


def validate_trigger_frame(e, frame):
    origins = frame.get('trigger_origins')
    if 'trigger_recorded' in frame and type(frame['trigger_recorded']) is not bool:
        raise ValueError('native trigger action observation must be boolean')
    if origins is None:
        return
    if type(origins) is not list or any(type(token) is not str for token in origins) or len(origins) != len(set(origins)):
        raise ValueError('distinct actual native trigger ancestors required')
    for token in origins:
        row = getattr(e, KEY, {}).get(token)
        if (row is None or row.get('native_action_frame') is frame or
                not any(child is frame for child in row.get('trigger_children', ()))):
            raise ValueError('native child must retain its actual issuing completion')


def _trigger_payment(e, actor, kind, source, move):
    """Prove this payment, not every action occurring inside its callback."""
    protected, payments = [], []
    rows = getattr(e, KEY, {})
    for grant in getattr(e, '_action_grants', ()):
        if len(grant) != 6 or grant[5] != 'native_completion_reaction':
            continue
        scope = grant[4]
        key = (actor.entity_id, kind)
        if (source is not None and source == scope['source'] and kind == 'free' and
                (actor is grant[1] or actor is grant[2]) and key not in scope['payments']):
            row = rows[grant[3]]
            protected.extend((row['id'], *row.get('native_action_frame', {}).get('trigger_origins', ())))
            payments.append((scope, 'payments', key))
    stack = getattr(e, '_native_action_stack', ())
    frame = stack[-1] if stack else None
    if frame is not None:
        validate_trigger_frame(e, frame)
        actual_move = move is not None and frame['source'] == move.get('id')
        granted_move = kind == 'free' and frame.get('trigger_granted_payment') is True
        if (frame['actor'] is actor and frame['kind'] == 'move' and
                (actual_move or granted_move) and not frame.get('trigger_move_paid')):
            protected.extend(frame.get('trigger_origins', ()))
            payments.append((frame, 'trigger_move_paid', True))
        # A native maneuver's optional reroll is a separate Free payment. Its
        # actual pending roll must belong to that maneuver's saved request list.
        import skill_feature_actions as SF, skill_maneuver_actions as SM
        if source in (SF.MONKEY, SF.MONKEY_CSV) and kind == 'free' and frame['kind'] == 'maneuver':
            owner = frame['actor']
            active = owner.custom_conditions.get(SM.ACTIVE)
            receipt = owner.custom_conditions.get(SM.RECEIPTS, {}).get(active, {})
            if receipt.get('basis', {}).get('source') == frame['source'] and receipt.get('stage') == 'skill':
                for participant, request, feature, roll_id in receipt.get('requests', ()):
                    if participant is not actor or feature != source:
                        continue
                    observed = SF.event(e, actor, roll_id)
                    key = (source, roll_id)
                    if (observed is not None and observed.state == 'pending' and
                            observed.feature == source and observed.request == request and
                            key not in frame.get('trigger_feature_payments', ())):
                        protected.extend(frame.get('trigger_origins', ()))
                        payments.append((frame, 'trigger_feature_payments', key))
    return set(protected), payments


def prepare_trigger_action(e, actor, kind, *, source=None, move=None):
    import world_entities as W
    protected, payments = _trigger_payment(e, actor, kind, source, move)
    plan = []
    for actor in W.actor_index(e).values():
        ids = _window_index(e, actor)
        if ids is None:
            if _disruption_owner(e, actor) is None:
                continue
            materialize = _legacy_windows(e, actor)
            active = [(row, window) for row, window in materialize if window['closed_by'] is None]
        else:
            materialize = []
            active = [(getattr(e, KEY)[token], getattr(e, KEY)[token]['disruption_window']) for token in ids]
        closed = [row['id'] for row, window in active
                  if row['id'] not in protected or not _window_current(e, row, window)]
        plan.append((actor, materialize, closed))
    return plan, payments


def commit_trigger_action(e, prepared, actor, kind):
    # Consume only after the ordinary owner actually appended its action.
    plan, payments = prepared
    for owner, field, value in payments:
        if field == 'trigger_move_paid':
            owner[field] = value
            owner.pop('trigger_granted_payment', None)
        else:
            owner.setdefault(field, []).append(value)
    for frame in getattr(e, '_native_action_stack', ()):
        if frame.get('trigger_origins'):frame['trigger_recorded']=True
    for owner, materialize, closed in plan:
        ids = owner.custom_conditions.setdefault(DISRUPTION_WINDOWS, [])
        for prior, window in materialize:
            row=getattr(e, KEY)[prior['id']]
            row['disruption_window'] = window
            if window['closed_by'] is None and row['id'] not in ids:
                ids.append(row['id'])
        for token in closed:
            row = getattr(e, KEY)[token]
            row['disruption_window']['closed_by'] = {
                'reason': 'actual unrelated action or boundary', 'actor_id': actor.entity_id,
                'action_index': len(actor._action_history) - 1,
                'turn_serial': actor.custom_conditions.get('combat_turn_serial', 0)}
            if token in ids:
                ids.remove(token)


def validate_disruption_windows(e, index):
    rows = getattr(e, KEY, {})
    for actor in index.values():
        _window_index(e, actor)
    for token, row in rows.items():
        window = row.get('disruption_window')
        if window is not None:
            if (type(window) is not dict or set(window) != {'version','completion_id','full_turn','seconds','scene','closed_by','legacy'} or
                    window['version'] != 1 or window['completion_id'] != token or not _bug_hit(row) or
                    window['full_turn'] != row.get('full_turn') or type(window['legacy']) is not bool):
                raise ValueError('actual native Disruption window provenance required')
            boundary = row.get('skirmisher_boundary', {})
            if window['seconds'] != boundary.get('seconds') or window['scene'] != boundary.get('scene'):
                raise ValueError('Disruption window timing differs from its native completion')
            closed = window['closed_by']
            if closed is not None:
                if type(closed) is not dict or closed.get('reason') not in ('legacy trigger lineage unavailable','actual unrelated action or boundary'):
                    raise ValueError('actual Disruption closure required')
                if 'actor_id' in closed:
                    actor = index.get(closed['actor_id'])
                    if actor is None or type(closed.get('action_index')) is not int or closed['action_index'] < 0:
                        raise ValueError('actual closing action actor/index required')
            elif token not in (row['actor'].custom_conditions.get(DISRUPTION_WINDOWS) or ()):
                raise ValueError('open Disruption window lost its actual index')
        children = row.get('trigger_children', ())
        if not isinstance(children, (list, tuple)) or len({id(frame) for frame in children}) != len(children):
            raise ValueError('distinct actual native child frames required')
        for frame in children:
            if type(frame) is not dict or index.get(getattr(frame.get('actor'), 'entity_id', None)) is not frame.get('actor'):
                raise ValueError('actual native trigger child actor required')
            if token not in frame.get('trigger_origins', ()):
                raise ValueError('native trigger parent and child links disagree')
            validate_trigger_frame(e, frame)


def disruption_frame_interested(e, actor):
    return _disruption_owner(e, actor) is not None or bool(completion_origins(e))


def finish_trigger_frame(e, frame):
    """A rejected, unobserved attempt cannot leave a durable child claim."""
    if frame.get('trigger_recorded') or frame.get('id') is not None or frame.get('deferred'):
        return
    for token in frame.pop('trigger_origins', ()):
        row=getattr(e,KEY)[token]
        children=row.get('trigger_children',[])
        children[:]=[child for child in children if child is not frame]
        if not children:row.pop('trigger_children',None)


def history_watermark(e):
    """Bound the existing len(rows)+1 native ID allocator without dict ordering."""
    rows=getattr(e,KEY,{})
    if set(rows)!={'move-complete:'+str(i) for i in range(1,len(rows)+1)}:return None
    return {'sequence':len(rows),'pending':[key for key,row in rows.items() if row['phase']!='complete']}


def after_history_watermark(e, boundary):
    current=history_watermark(e)
    if current is None or boundary is None or current['sequence']<boundary['sequence']:return None
    rows=getattr(e,KEY,{})
    if any(key not in rows for key in boundary['pending']):return None
    keys=boundary['pending']+['move-complete:'+str(i) for i in range(boundary['sequence']+1,current['sequence']+1)]
    return [rows[key] for key in keys]
