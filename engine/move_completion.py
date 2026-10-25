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


def after_all(effect,rules=None,move=None):
    post_stage=False
    if rules is not None and move is not None:
        import post_resolution_stage_effects as POST_STAGE
        post_stage=POST_STAGE.owns(rules,move,effect)
    focus_after=rules is not None and __import__('declarative_move_contracts').after_all(rules,effect)
    return (focus_after or post_stage or field_effect(effect) or
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
        action=getattr(e,'_native_action_stack',[])
        if action and action[-1]['actor'] is actor and action[-1]['kind']=='move':
            rows[token]['native_action_frame']=action[-1]
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


def finish_target(e,token,actor,target,*,hit,dealt,effects=(),cancelled=False,hit_prevented=False):
    if token is None:return
    row=getattr(e,KEY)[token]
    if row['actor'] is not actor or target.entity_id not in row['started']:
        raise ValueError('actual target activation required for completion')
    cancelled=cancelled or row.get('drown_out',{}).get('cancelled',False)
    result={'hit':bool(hit) and not hit_prevented,'dealt':dealt,'cancelled':bool(cancelled)}
    if hit_prevented:result['hit_prevented']=True
    old=row['results'].get(target.entity_id)
    if old is not None:
        if old!=result:raise ValueError('completed target observation changed')
        return refresh(e,token)
    row['results'][target.entity_id]=result
    __import__('ace_trainer').after_target(e,row,target)
    if result['hit'] and not result['cancelled'] and row['move'].get('class') in ('물리','특수'):
        __import__('ace_trainer').after_damaging_hit(e,target,token)
    __import__('channeler').completion_hit(e,row,target)
    import optional_weapon_framework as FRAMEWORK
    if target.entity_id not in row.get('defense',{}) and target.entity_id not in row.get('recipient_aliases',{}):
        FRAMEWORK.observe_hit(e,row,actor,target)
    row['effects'].extend(x for x in effects if x not in row['effects'])
    return refresh(e,token)


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
        return refresh(e,token)
    profile=ACTIVATION._profile(e)
    if row['profile']!=profile or e.r._selected_rule(row['move_id'])!=row['move_id']:
        raise ValueError('selected move completion policy changed')
    hit=any(x['hit'] and not x['cancelled'] for x in row['results'].values())
    all_cancelled=all(x['cancelled'] for x in row['results'].values())
    # Ordinary self effects preserve their hit requirement; an explicitly
    # after-use counter also advances on a genuine miss, never a refusal.
    import post_resolution_stage_effects as POST_STAGE
    post=[x for x in row['post_effects'] if not all_cancelled and
          (hit or field_effect(x) or POST_STAGE.owns(e.r,row['move'],x) or
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
    except Exception:
        row['phase']='interrupted';raise
    row['effects'].extend(x for x in getattr(e,'_effect_dispatch_receipts',{}) if x not in before and x not in row['effects'])
    row['phase']='completion_effects'
    return refresh(e,token)


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
            if (row['phase'] not in ('completion_effects','complete') or not row['sealed'] or row['targets'] or
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
    for event in getattr(e,'_passive_events',{}).values():
        validate_return_continuation(e,event)
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
