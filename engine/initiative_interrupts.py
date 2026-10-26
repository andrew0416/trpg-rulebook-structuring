"""Declared reaction precedence, native action frames and stable future debts.

The caller supplies a selected source's policy. Actual Engine turn/move
occurrences supply the trigger. A reaction is not an owner-turn clock event;
a borrowed whole turn is, and its future slot is settled exactly once.
"""
from copy import deepcopy
import action_resources as RESOURCES
import common_checks as C
import initiative_derivation as DERIVE
import world_entities as WORLD
import state_grants as GRANTS
import root_resolution as ROOT

KEY = '_initiative_interrupts'


def _signature(trigger,rows):
    fields = {'turn':('kind','actor_id','serial','round'),'move':('kind','event_id'),
              'reaction':('kind','window_id','request_id'),'accuracy':('kind','event_id'),
              'between':('kind','round','schedule_cursor','closure_sequence','epoch'),
              'duelist_overflow':('kind','overflow_id'),'native_accuracy':('kind','event_id')}[trigger['kind']]
    definition = [{k:(v.entity_id if k=='actor' else v) for k,v in row.items() if k not in ('status','receipt')} for row in rows]
    return ROOT.fingerprint({'trigger':{k:trigger[k] for k in fields},'requests':definition})

def _state(engine):
    state = getattr(engine,KEY,None)
    if state is None:
        state = {'version':1,'sequence':0,'windows':{},'frames':[],'loans':{}}
        setattr(engine,KEY,state)
    return state


def frame(engine):
    state = getattr(engine,KEY,None)
    return state['frames'][-1] if state and state['frames'] else None


def suspended_owner(engine):
    state = getattr(engine,KEY,None)
    return state['frames'][0]['parent'] if state and state['frames'] else None


def require_clear(engine):
    state = getattr(engine,KEY,None)
    if state and (state['frames'] or any(w['cursor']<len(w['requests']) for w in state['windows'].values())):
        raise ValueError('initiative reaction window must finish before this boundary')


def between_trigger(engine):
    """Observe an actual scheduled between-turn boundary, without granting actions."""
    schedule = getattr(engine,'_initiative_schedule',None)
    if (not engine.encounter_active or engine.round_start_seconds is None
            or engine._active_turn_actor is not None or frame(engine)
            or not schedule or schedule['status']!='active'
            or schedule['round']!=engine.round_no or schedule['open_slot'] is not None):
        raise ValueError('actual scheduled between-turn boundary required')
    return {'kind':'between','round':engine.round_no,'schedule_cursor':schedule['cursor'],
            'closure_sequence':len(engine._turn_closures),
            'epoch':getattr(engine,'_party_encounter_epoch',0)}


def between_frame(engine):
    """Whether the current stack descends from a native between-turn window."""
    state = getattr(engine,KEY,None)
    if not state or not state['frames']:return False
    first = state['frames'][0]
    return first['parent'] is None and state['windows'][first['window_id']]['trigger']['kind']=='between'


def _trigger(engine, raw):
    if type(raw) is not dict:
        raise ValueError('actual native reaction trigger required')
    if raw.get('kind')=='duelist_overflow' and set(raw)=={'kind','overflow_id'}:
        import duelist as DUELIST
        DUELIST.overflow_trigger(engine,raw['overflow_id'])
        return dict(raw,owner=engine._active_turn_actor,round=engine.round_no)
    if raw.get('kind')=='between':
        if raw!=between_trigger(engine):
            raise ValueError('between-turn declaration differs from the actual schedule boundary')
        return dict(raw,owner=None)
    owner = engine._active_turn_actor
    if owner is None and raw.get('kind')=='accuracy' and set(raw)=={'kind','event_id'}:
        import move_defense_reactions as DEFENSE,focus_punch as FOCUS
        proof=FOCUS.reaction_origin(engine,raw['event_id'],live=True)
        if proof is not None:
            result=DEFENSE.authorize_trigger(engine,raw['event_id'])
            return dict(result,owner=None,round_end_source=proof)
    if owner is None:
        raise ValueError('reaction window requires an actual suspended owner turn')
    if raw.get('kind')=='reaction' and set(raw)=={'kind','window_id','request_id'}:
        current = frame(engine)
        if (not current or current['status']!='open' or current['actor'] is not owner
                or raw['window_id']!=current['window_id'] or raw['request_id']!=current['request_id']):
            raise ValueError('nested trigger differs from the actual open reaction occurrence')
        return dict(raw,owner=owner,round=engine.round_no)
    if raw.get('kind')=='turn' and set(raw)=={'kind','actor_id','serial','round'}:
        if (raw['actor_id']!=owner.entity_id or raw['serial']!=owner.custom_conditions.get('combat_turn_serial',0)
                or raw['round']!=engine.round_no):
            raise ValueError('reaction trigger differs from the actual owner turn')
        C.integer(raw['serial'],'actual reaction owner turn',1)
        C.integer(raw['round'],'actual reaction round',1)
        return dict(raw,owner=owner)
    if raw.get('kind')=='native_accuracy' and set(raw)=={'kind','event_id'}:
        return __import__('move_defense_reactions').authorize_native_accuracy(engine,raw['event_id'])
    if raw.get('kind')=='accuracy' and set(raw)=={'kind','event_id'}:
        import move_defense_reactions as DEFENSE
        result=DEFENSE.authorize_trigger(engine,raw['event_id'])
        if result['owner'] is not owner:raise ValueError('accuracy defense suspended owner changed')
        return result
    if raw.get('kind')=='move' and set(raw)=={'kind','event_id'}:
        import passive_events as EVENTS
        event = engine._passive_events.get(raw['event_id'])
        if (event is None or event['producer']!='Engine.use_move' or event['actor'] is not owner
                or event['round']!=engine.round_no or event['phase']!='producer_return_boundary'
                or event['status'] not in ('applied','inapplicable')):
            raise ValueError('reaction window needs the completed actual move occurrence')
        observations = EVENTS.observations(engine,event['id'])
        if not observations or observations[-1]['stage']!='resolved':
            raise ValueError('native resolved move observation required')
        import move_completion as COMPLETE
        returned=COMPLETE.require_returned_event(engine,event['id'])
        return dict(raw,owner=owner,round=engine.round_no,observations=deepcopy(observations),
                    move_return=returned,move_return_fingerprint=ROOT.fingerprint(returned))
    raise ValueError('known native turn/move trigger fields required')


def _loan_location(engine,actor):
    schedule = getattr(engine,'_initiative_schedule',None)
    if not schedule or schedule['status']!='active':
        raise ValueError('whole-turn borrowing requires actual stable schedule slots')
    matches = [(key,row) for key,row in schedule['slots'].items() if row['actor'] is actor]
    if len(matches)!=1:
        raise ValueError('borrower must own one actual participant slot')
    key,row = matches[0]
    if row['turn']=='open' or actor is engine._active_turn_actor:
        raise ValueError('cannot borrow the currently open owner turn')
    due = engine.round_no if row['turn']=='ready' else engine.round_no+1
    state = getattr(engine,KEY,None)
    if state and any(x['status']=='owed' and x['slot']==key and x['due_round']==due for x in state['loans'].values()):
        raise ValueError('future slot has already been borrowed')
    return key,row['role'],due


def _switch_location(engine,actor,source=None):
    if source==__import__('juggler').FIRST:return __import__('juggler').first_location(engine,actor)
    import party_actions as PARTY
    proof=PARTY.switch_lock(engine,actor)
    if proof is None:raise ValueError('next-round Interrupt loan requires the actual voluntary League switch lock')
    PARTY.validate_switch_lock(engine,actor,proof)
    schedule=getattr(engine,'_initiative_schedule',None)
    if not schedule or schedule['status']!='active' or schedule['round']!=engine.round_no:
        raise ValueError('switch Interrupt requires its actual stable native schedule')
    slot=next((key for key,row in schedule['slots'].items() if row['actor'] is actor),None)
    if slot is None or schedule['open_slot']==slot:
        raise ValueError('switch Interrupt requires its actual unopened or consumed Pokemon slot')
    trainer=proof['trainer'];state=getattr(engine,KEY,None)
    due=[] if state is None else [loan for loan in state['loans'].values() if loan['status']=='owed'
        and loan['due_round']==engine.round_no+1]
    if any(loan['slot']==slot or loan['actor'] is actor for loan in due):
        raise ValueError('this actual Pokemon/slot already borrowed its next-round turn')
    if sum(loan.get('trainer_id')==trainer.entity_id for loan in due)>=PARTY.command_limit(engine,trainer):
        raise ValueError('this trainer has no unborrowed next-round command unit')
    return {'slot':slot,'role':schedule['slots'][slot]['role'],'due_round':engine.round_no+1,
            'trainer_id':trainer.entity_id,'encounter_epoch':proof['scope'][0],
            'switch_request_id':proof['request_id']}


def _move_request(engine,actor,row,evidence):
    """Only the real source consumer may request a selected Interrupt Move."""
    import move_defense_reactions as DEFENSE
    import combat_move_reactions as REACTIONS
    if row['source']==__import__('juggler').FIRST:
        __import__('juggler').first_request(engine,actor,row);return
    if row.get('move_id') in REACTIONS.SOURCES:
        REACTIONS.authorize_request(engine,actor,row,evidence);return
    if evidence['kind']=='duelist_overflow':
        import duelist as DUELIST
        DUELIST.validate_interrupt(engine,evidence,dict(row,actor=actor))
        return
    if evidence['kind']=='native_accuracy':
        DEFENSE.authorize_native_splash(engine,evidence['event_id'],actor,row);return
    if evidence['kind']!='accuracy' or row['move_id']!=row['source']:
        raise ValueError('Interrupt Move requires its actual source-authenticated accuracy consumer')
    DEFENSE.authorize_move_interrupt(engine,evidence['event_id'],actor,row['move_id'])


def selected_move_frame(engine,actor):
    current=frame(engine)
    if not current or current['actor'] is not actor or current['status']!='open':return None
    window=getattr(engine,KEY)['windows'][current['window_id']]
    row=window['requests'][window['cursor']]
    return (current,row) if 'move_id' in row else None


def require_selected_move(engine,actor,move_id):
    selected=selected_move_frame(engine,actor)
    if selected is not None and move_id!=selected[1]['move_id']:
        raise ValueError('Interrupt frame permits only its actual selected Move')


def require_move_cost(engine,actor,kind,move,*,movement=False):
    """TURN calls this before payment, including Free and compound requests."""
    selected=selected_move_frame(engine,actor)
    if selected is None:return
    current,row=selected
    expected='shift' if row['source']==__import__('tumbler').SPLASH else 'standard'
    if (kind!=expected or movement or not isinstance(move,dict) or move.get('id')!=row['move_id']
            or getattr(actor,'_action_history',[])[current['history_start']:]):
        raise ValueError('Interrupt permits exactly one native selected Standard Move and no other action')


def require_recorded_action(engine,actor,kind,*,triggered_source=None):
    """Also close native Free producers which do not pass through TURN.spend."""
    selected=selected_move_frame(engine,actor)
    if selected is None:return
    current,row=selected
    if kind=='free' and __import__('jump_move_actions').triggered_free_allowed(engine,actor,row,triggered_source):return
    expected='shift' if row['source']==__import__('tumbler').SPLASH else 'standard'
    if (kind!=expected or actor.budget.get(expected)!=0
            or getattr(actor,'_action_history',[])[current['history_start']:]):
        raise ValueError('Interrupt records only its first actually paid selected Standard Move')


def _completed_move(engine,current,row):
    receipts=[receipt for key,receipt in getattr(engine,'_move_completions',{}).items()
        if key not in current['completion_ids_before'] and receipt['actor'] is current['actor']]
    if (len(receipts)!=1 or receipts[0]['move_id']!=row['move_id'] or receipts[0]['phase']!='complete'
            or receipts[0]['round']!=engine.round_no
            or getattr(current['actor'],'_action_history',[])[current['history_start']:]!=__import__('jump_move_actions').interrupt_actions(engine,row)):
        raise ValueError('Interrupt needs exactly its actually completed native selected Move')
    return receipts[0]['id']


def command_debts(engine,trainer):
    """One source receipt reduces the trainer pool once, even after settlement."""
    import party_actions as PARTY
    state=getattr(engine,KEY,None)
    return sum(loan.get('mode')=='switch_interrupt' and loan['status'] in ('owed','settled')
        and loan['trainer_id']==trainer.entity_id and loan['encounter_epoch']==PARTY.scope(engine)[0]
        and loan['due_round']==engine.round_no for loan in (() if state is None else state['loans'].values()))


def queue(engine,candidates,*,trigger,order=None):
    """Unknown precedence/clock/payment stays pending before actions or RNG."""
    import passive_events as EVENTS, heavy_injury_adapter as HEAVY
    EVENTS.ensure_clear(engine); HEAVY.ensure_clear(engine)
    evidence = _trigger(engine,trigger)
    if type(candidates) is not list or not candidates:
        raise ValueError('nonempty sourced reaction declarations required')
    index = WORLD.actor_index(engine); planned = []; missing = []; ids = set()
    for raw in candidates:
        required = {'id','actor_id','source','priority','mode','payment','budget','clock'}
        if type(raw) is not dict or not required<=set(raw) or set(raw)-required-{'settlement_clock','debt_policy','move_id'}:
            raise ValueError('exact sourced reaction fields required')
        uid = raw['id']
        if type(uid) is not str or not uid.strip() or uid in ids:
            raise ValueError('distinct reaction request identities required')
        ids.add(uid)
        actor = index.get(raw['actor_id'])
        WORLD.require_actors(engine,actor)
        if raw['mode']!='borrow_turn':__import__('ability_control_contracts').admit(engine,actor,'interrupt',trigger=evidence)
        DERIVE.selected(engine.r,raw['source'])
        absent = [key for key in ('priority','mode','payment','clock') if raw[key] is None]
        if absent:
            missing.extend(uid+':'+key for key in absent)
            continue
        C.integer(raw['priority'],'reaction priority')
        row = deepcopy(raw); row.pop('actor_id'); row['actor'] = actor; row['status']='ready'
        if 'move_id' in raw:_move_request(engine,actor,raw,evidence)
        if raw['mode']=='reaction':
            if raw['clock']!='none' or raw['payment'] not in ('current','next') or 'settlement_clock' in raw:
                raise ValueError('reaction requires explicit current/next payment and no owner clock')
            if raw['budget']=={}:
                __import__('juggler').free_reaction(engine,actor,raw)
                row['budget']={}
            else:row['budget'] = RESOURCES.loss(raw['budget'])
            row['debt_policy'] = raw.get('debt_policy','hold')
            if row['debt_policy'] not in ('hold','coalesce'):
                raise ValueError('explicit hold/coalesce future action-loss conjunction required')
        elif raw['mode']=='duelist_interrupt':
            if (set(raw)!=required|{'move_id'} or raw['source']!='feat/기회-포착' or raw['payment']!='none'
                    or raw['clock']!='none' or raw['budget']!={'standard':1} or evidence['kind']!='duelist_overflow'):
                raise ValueError('Seize grants only its actual selected Standard attack Interrupt')
        elif raw['mode']=='switch_interrupt':
            if (set(raw)!=required|{'move_id'} or raw['payment']!='future_turn' or raw['clock']!='none'
                    or raw['budget']!={'standard':1}):
                raise ValueError('switch Interrupt requires one selected Standard Move and a no-clock future turn loan')
            row.update(_switch_location(engine,actor,row['source']));row['settlement_clock']='none'
        elif raw['mode']=='borrow_turn':
            if 'move_id' in raw:raise ValueError('whole-turn borrowing cannot impersonate an Interrupt Move')
            if 'debt_policy' in raw:
                raise ValueError('action-loss conjunction does not govern whole-turn rights')
            if raw.get('settlement_clock') is None:
                missing.append(uid+':settlement_clock')
                continue
            if (raw['clock']!='owner_turn' or raw['payment']!='future_turn' or raw['budget'] is not None
                    or raw['settlement_clock'] not in ('none','owner_turn')):
                raise ValueError('whole-turn loan requires native budget and explicit future clock policy')
            row['slot'],row['role'],row['due_round'] = _loan_location(engine,actor)
        else:
            raise ValueError('known sourced reaction or whole-turn loan mode required')
        planned.append(row)
    if missing:
        return {'status':'pending','required':missing,'consumed':False}
    if order is None:
        if len({row['priority'] for row in planned})!=len(planned):
            return {'status':'pending','required':['explicit simultaneous reaction order'],'consumed':False}
        planned.sort(key=lambda row:row['priority'],reverse=True)
    else:
        if type(order) is not list or len(order)!=len(set(order)) or set(order)!=ids:
            raise ValueError('exact explicit simultaneous reaction order required')
        by_id = {row['id']:row for row in planned}; planned = [by_id[uid] for uid in order]
        if any(a['priority']<b['priority'] for a,b in zip(planned,planned[1:])):
            raise ValueError('explicit reaction order contradicts declared priority')
    loans = [(row['slot'],row['due_round']) for row in planned if row['mode'] in ('borrow_turn','switch_interrupt')]
    if len(loans)!=len(set(loans)):
        raise ValueError('one future turn right cannot support two queued whole-turn loans')
    def apply(staged,_,*actual):
        state = _state(staged); index = {c.entity_id:c for c in actual}
        rows = [dict(row,actor=index[row['actor'].entity_id]) for row in planned]
        staged_evidence = _trigger(staged,trigger)
        signature = _signature(trigger,rows)
        for window in state['windows'].values():
            if window['signature']==signature:
                return {'status':'already_queued','window_id':window['id']}
        if any(w['parent'] is staged._active_turn_actor and w['cursor']<len(w['requests'])
               and not any(f['window_id']==w['id'] for f in state['frames']) for w in state['windows'].values()):
            raise ValueError('one boundary already has an unresolved reaction window')
        state['sequence'] += 1; key = 'initiative-window:'+str(state['sequence'])
        state['windows'][key] = {'id':key,'signature':signature,'trigger':staged_evidence,
                                'parent':staged._active_turn_actor,'round':staged.round_no,
                                'requests':rows,'cursor':0}
        return {'status':'queued','window_id':key,'order':[row['id'] for row in rows]}
    return GRANTS.transition(engine,None,apply,participants=tuple({id(row['actor']):row['actor'] for row in planned}.values()))


def is_borrow_start(engine,actor):
    current = frame(engine)
    return bool(current and current['mode']=='borrow_turn' and current['status']=='starting' and current['actor'] is actor)


def borrow_started(engine,actor):
    if not is_borrow_start(engine,actor):
        raise ValueError('actual starting borrowed frame required')
    engine._active_turn_actor = actor
    frame(engine)['status'] = 'open'


def begin(engine,window_id,request_id):
    import passive_events as EVENTS, heavy_injury_adapter as HEAVY, effect_contracts as EFFECTS
    EVENTS.ensure_clear(engine); HEAVY.ensure_clear(engine); EFFECTS.ensure_clear(engine)
    validate_world(engine,WORLD.actor_index(engine))
    def apply(staged,_):
        state = _state(staged); window = state['windows'].get(window_id)
        if not window or window['round']!=staged.round_no or window['parent'] is not staged._active_turn_actor:
            raise ValueError('reaction belongs to another actual suspended owner/boundary')
        if window['cursor']==len(window['requests']):
            raise ValueError('reaction window already completed')
        row = window['requests'][window['cursor']]
        if row['id']!=request_id or row['status']!='ready':
            raise ValueError('reaction does not own the next unconsumed priority position')
        if window['trigger']['kind']=='between':
            # A queued declaration cannot be replayed at a later schedule boundary.
            raw={k:v for k,v in window['trigger'].items() if k!='owner'}
            if window['cursor']:
                # Earlier requests can close their borrowed native turns while
                # the same queue still owns this unchanged schedule boundary.
                raw['closure_sequence']=len(staged._turn_closures)
            _trigger(staged,raw)
        actor = row['actor']; WORLD.require_actors(staged,actor)
        if row['mode']!='borrow_turn':__import__('ability_control_contracts').admit(staged,actor,'interrupt',trigger=window['trigger'])
        if actor.dead or actor.fainted or not actor.on_field or actor.captured:
            raise ValueError('reaction owner no longer eligible')
        if 'move_id' in row:_move_request(staged,actor,row,window['trigger'])
        backup = deepcopy(getattr(actor,'budget',None)); loan = None
        if row['mode']=='reaction':
            if row['budget']=={}:
                __import__('juggler').free_reaction(staged,actor,row)
            elif row['payment']=='current':
                if getattr(actor,'budget',None) is None:
                    raise ValueError('reaction current payment requires an actual prior action budget')
                components = [kind for kind,amount in row['budget'].items() for _ in range(amount)]
                backup = RESOURCES.plan_cost(actor.budget,components)
                if backup is None:
                    raise ValueError('reaction cannot pay its declared current action cost')
            else:
                owed = RESOURCES.pending(actor)
                if owed and (row['debt_policy']!='coalesce' or owed!=row['budget']):
                    raise ValueError('distinct next-action reaction costs require explicit conjunction')
                RESOURCES.schedule(actor,row['budget'])
        elif row['mode']=='switch_interrupt':
            if any(row[k]!=v for k,v in _switch_location(staged,actor,row['source']).items()):
                raise ValueError('switch Interrupt source/ownership/binding changed since declaration')
            loan_id=window_id+':'+row['id']
            loan={k:row[k] for k in ('source','actor','slot','role','due_round','settlement_clock',
                'trainer_id','encounter_epoch','switch_request_id','move_id')}
            loan.update(id=loan_id,window_id=window_id,request_id=row['id'],mode='switch_interrupt',
                borrow_round=staged.round_no,status='owed',move_completion=None,settlement=None)
            state['loans'][loan_id]=loan
        elif row['mode']=='borrow_turn':
            location = _loan_location(staged,actor)
            if location!=(row['slot'],row['role'],row['due_round']):
                raise ValueError('borrowed future turn binding changed since declaration')
            loan_id = window_id+':'+row['id']
            loan = {'id':loan_id,'window_id':window_id,'request_id':row['id'],
                    'source':row['source'],'actor':actor,'slot':row['slot'],'role':row['role'],
                    'borrow_round':staged.round_no,'due_round':row['due_round'],
                    'settlement_clock':row['settlement_clock'],'status':'owed','borrow_closure':None,'settlement':None}
            state['loans'][loan_id] = loan
        current = {'window_id':window_id,'request_id':request_id,'actor':actor,'parent':staged._active_turn_actor,
                   'mode':row['mode'],'status':'starting','backup_budget':backup,
                   'history_start':len(getattr(actor,'_action_history',[])),'loan_id':None if loan is None else loan['id']}
        state['frames'].append(current); row['status']='open'
        if 'move_id' in row:current['completion_ids_before']=list(getattr(staged,'_move_completions',{}))
        if row['mode']=='borrow_turn':
            staged._active_turn_actor = None
            cursor = getattr(staged,'_initiative_cursor',None)
            count = cursor['count'] if cursor and cursor['round']==staged.round_no else None
            staged.start_of_turn(actor,initiative_count=count)
            current['history_start']=0
        else:
            staged._active_turn_actor = actor
            actor.budget = {kind:row['budget'].get(kind,0) for kind in RESOURCES.KINDS}
            if row['mode']=='duelist_interrupt':
                # Keep the real unspent Swift eligibility used by Exhaust.
                # The selected-Move guards still authorize only one Standard.
                actor.budget['swift']=1 if backup is None else backup['swift']
            current['status']='open'
        return status(staged)
    return GRANTS.transition(engine,None,apply,include_rulings=True)


def permission(engine,actor):
    state = getattr(engine,KEY,None)
    current = frame(engine)
    if current:
        return current['actor'] is actor and current['status']=='open'
    schedule = getattr(engine,'_initiative_schedule',None)
    if schedule and schedule['open_slot'] is not None:
        loan = _due(engine,schedule['open_slot'])
        if loan and schedule['slots'][schedule['open_slot']]['actor'] is actor:
            return False
    return not state or all(w['cursor']==len(w['requests']) for w in state['windows'].values())


def preflight_native_end(engine,actor):
    current = frame(engine)
    if current:
        if (current['actor'] is not actor or current['mode']!='borrow_turn'
                or not getattr(engine,'_initiative_interrupt_finishing',False)):
            raise ValueError('finish the actual initiative reaction frame explicitly')
    else:
        require_clear(engine)


def borrow_closed(engine,actor):
    current = frame(engine)
    if not current or current['mode']!='borrow_turn' or current['actor'] is not actor:
        return False
    sequence = len(engine._turn_closures)+1
    engine._turn_closures.append({'actor':actor,'round':engine.round_no,'sequence':sequence,
                                 'kind':'borrowed','loan_id':current['loan_id'],
                                 'turn_serial':actor.custom_conditions['combat_turn_serial']})
    _state(engine)['loans'][current['loan_id']]['borrow_closure'] = sequence
    current['status']='closing'; engine._active_turn_actor=None
    return True


def finish(engine):
    import passive_events as EVENTS, heavy_injury_adapter as HEAVY, effect_contracts as EFFECTS, maneuver_grants as MANEUVERS
    EVENTS.ensure_clear(engine); HEAVY.ensure_clear(engine); EFFECTS.ensure_clear(engine)
    def apply(staged,_):
        state = _state(staged); current = frame(staged)
        if not current or current['status']!='open' or staged._active_turn_actor is not current['actor']:
            raise ValueError('actual open reaction frame required')
        actor = current['actor']; window = state['windows'][current['window_id']]
        row = window['requests'][window['cursor']]
        if row['id']!=current['request_id']:
            raise ValueError('reaction frame differs from its actual priority position')
        ancestors={frame['window_id'] for frame in state['frames'][:-1]}
        if any(w['parent'] is actor and w is not window and w['id'] not in ancestors
               and w['cursor']<len(w['requests']) for w in state['windows'].values()):
            raise ValueError('nested reaction window has not finished')
        MANEUVERS.check_end(staged,actor)
        if current['mode']=='borrow_turn':
            staged._initiative_interrupt_finishing=True
            try:
                staged.end_of_turn(actor)
            finally:
                del staged._initiative_interrupt_finishing
        if 'move_id' in row:
            completion=_completed_move(staged,current,row)
            if row['source']==__import__('juggler').FIRST:
                proof=__import__('juggler').first_request(staged,actor,row)
                if [t.entity_id for t in staged._move_completions[completion]['targets']]!=[proof['target_id']]:raise ValueError('First Blood needs its actually selected native target')
            if current['mode']=='switch_interrupt':state['loans'][current['loan_id']]['move_completion']=completion
        row['receipt'] = {'actor':actor,'round':staged.round_no,'parent':current['parent'],
                          'remaining_budget':deepcopy(actor.budget),
                          'actions':deepcopy(getattr(actor,'_action_history',[])[current['history_start']:]),
                          'loan_id':current['loan_id']}
        if 'move_id' in row:row['receipt']['move_completion']=completion
        if row['mode']=='reaction' and row['payment']=='next' and row['budget']:
            row['receipt']['recipient_loss']={'status':'owed','budget':deepcopy(row['budget'])}
        row['status']='completed'; window['cursor'] += 1
        actor.budget = current['backup_budget']
        staged._active_turn_actor = current['parent']
        state['frames'].pop()
        if row['source']==__import__('juggler').FIRST:
            owner=__import__('party_actions').owner(staged,actor)
            __import__('juggler').state(owner).pop('first_request',None)
        return status(staged)
    return GRANTS.transition(engine,None,apply,include_rulings=True)


def settle_action_losses(engine,actor,owed):
    """Attach an actual budget reset to its completed next-paid reactions."""
    if not owed or getattr(engine,'_active_turn_actor',None) is not actor:return
    state=getattr(engine,KEY,None)
    for window in (() if not state else state['windows'].values()):
        for row in window['requests']:
            if row['status']!='completed' or row['actor'] is not actor:continue
            receipt=row['receipt'].get('recipient_loss')
            if not receipt or receipt['status']!='owed' or receipt['budget']!=owed:continue
            receipt.update(status='paid',round=engine.round_no,turn=actor.custom_conditions['combat_turn_serial'])


def paid_standard(engine,actor):
    """Observe real Standard/Full cost settlement without inventing an action."""
    state=getattr(engine,KEY,None)
    for window in (() if not state else state['windows'].values()):
        for row in window['requests']:
            if row['status']!='completed' or row['actor'] is not actor:continue
            receipt=row['receipt'];paid=receipt.get('recipient_loss',{})
            if (paid.get('status')=='paid' and paid.get('round')==engine.round_no
                    and paid.get('turn')==actor.custom_conditions.get('combat_turn_serial')
                    and paid['budget'].get('standard',0)>0
                    and any(kind in ('standard','full') for kind in receipt['actions'])):return True
    return False


def decline(engine,window_id,request_id,*,source,reason):
    """A declared pass closes an unused offer, without paying or refunding."""
    DERIVE.selected(engine.r,source)
    if type(reason) is not str or not reason.strip():
        raise ValueError('explicit reaction decline reason required')
    def apply(staged,_):
        state = _state(staged); window = state['windows'].get(window_id)
        if (not window or window['round']!=staged.round_no or window['parent'] is not staged._active_turn_actor
                or window['cursor']==len(window['requests'])):
            raise ValueError('actual suspended reaction offer required')
        row = window['requests'][window['cursor']]
        if row['id']!=request_id or row['source']!=source or row['status']!='ready':
            raise ValueError('only the next unused sourced reaction offer may be declined')
        row['status']='skipped'
        row['receipt']={'actor':row['actor'],'parent':window['parent'],'round':staged.round_no,
                        'reason':reason,'actions':[],'paid':False,'loan_id':None}
        window['cursor'] += 1
        return status(staged)
    return GRANTS.transition(engine,None,apply)


def _due(engine,slot):
    state = getattr(engine,KEY,None)
    rows = [] if not state else [row for row in state['loans'].values()
        if row['status']=='owed' and row['slot']==slot and row['due_round']==engine.round_no]
    if len(rows)>1:
        raise ValueError('conflicting future turn debts require explicit conjunction')
    return rows[0] if rows else None


def preflight_round(engine,schedule):
    state = getattr(engine,KEY,None)
    for loan in (() if not state else state['loans'].values()):
        if loan['status']!='owed':continue
        if loan['due_round']<schedule['round']:
            raise ValueError('cannot advance past an unpaid borrowed turn')
        if loan['due_round']==schedule['round']:
            row = schedule['slots'].get(loan['slot'])
            if row is None or row['role']!=loan['role']:
                raise ValueError('future schedule must preserve the actual borrowed slot right')
            if loan.get('mode')=='switch_interrupt':_switch_owner(engine,loan,row['actor'])


def _switch_owner(engine,loan,actor):
    import party_actions as PARTY
    trainer=PARTY.owner(engine,actor)
    if (actor.kind!='pokemon' or trainer is None or trainer.entity_id!=loan['trainer_id']
            or actor.spec.get('trainer_id')!=loan['trainer_id']
            or loan['encounter_epoch']!=PARTY.scope(engine)[0]):
        raise ValueError('switch Interrupt debt must retain its actual trainer command pool and encounter')


def preflight_replacement(engine,slot,actor):
    state=getattr(engine,KEY,None)
    for loan in (() if state is None else state['loans'].values()):
        if loan.get('mode')=='switch_interrupt' and loan['status']=='owed' and loan['slot']==slot:
            _switch_owner(engine,loan,actor)


def preflight_ordinary(engine,slot):
    loan = _due(engine,slot)
    if loan and loan['settlement_clock']=='none':
        raise ValueError('borrowed turn requires settlement without a second owner turn')


def after_budget_reset(engine,actor):
    if frame(engine):return
    schedule = getattr(engine,'_initiative_schedule',None)
    if not schedule:return
    key = next((key for key,row in schedule['slots'].items() if row['actor'] is actor),None)
    loan = _due(engine,key)
    if loan:
        actor.budget = dict.fromkeys(RESOURCES.KINDS,0)


def ordinary_closed(engine,slot,actor):
    loan = _due(engine,slot)
    if loan:
        if loan['settlement_clock']!='owner_turn':
            raise ValueError('borrowed slot did not declare an owner-turn settlement')
        loan['status']='settled'
        loan['settlement']={'actor':actor,'round':engine.round_no,'slot':slot,'clock':'owner_turn',
                            'closure_sequence':len(engine._turn_closures)+1}


def settle(engine):
    """Consume a borrowed slot; no activation, reset, RNG or owner clock."""
    require_clear(engine)
    def apply(staged,_):
        import initiative_schedule as SCHEDULE
        schedule = getattr(staged,'_initiative_schedule',None)
        if not schedule or schedule['status']!='active' or staged._active_turn_actor is not None:
            raise ValueError('actual unopened future slot required')
        step = SCHEDULE._current(schedule)
        if not step or step['kind']!='turn':
            raise ValueError('declarations must precede borrowed-turn settlement')
        loan = _due(staged,step['slot'])
        complete=loan and (loan.get('move_completion') if loan.get('mode')=='switch_interrupt' else loan['borrow_closure'])
        if not loan or loan['settlement_clock']!='none' or complete is None:
            raise ValueError('actual completed borrowed turn with no-clock settlement required')
        row = schedule['slots'][step['slot']]; actor = row['actor']
        if loan.get('mode')=='switch_interrupt':_switch_owner(staged,loan,actor)
        if row['turn']!='ready':
            raise ValueError('future turn right has already been consumed')
        loan['status']='settled'
        loan['settlement']={'actor':actor,'round':staged.round_no,'slot':step['slot'],'clock':'none',
                            'schedule_cursor':schedule['cursor']}
        outcome='switch_interrupt_settled' if loan.get('mode')=='switch_interrupt' else 'borrow_settled'
        schedule['records'].append(dict(step,actor=actor,outcome=outcome,loan_id=loan['id']))
        schedule['cursor'] += 1; row['turn']='closed'
        staged._ordinary_turn_rounds[actor]=staged.round_no
        return SCHEDULE.status(staged)
    return GRANTS.transition(engine,None,apply)


def validate_settlement(engine,schedule,record):
    state = getattr(engine,KEY,None)
    loan = None if not state else state['loans'].get(record['loan_id'])
    if (not loan or loan['status']!='settled' or loan['settlement_clock']!='none'
            or loan['due_round']!=schedule['round'] or loan['slot']!=record['slot']
            or loan['settlement']['actor'] is not record['actor']):
        raise ValueError('schedule settlement lacks its actual completed future loan')
    expected='switch_interrupt_settled' if loan.get('mode')=='switch_interrupt' else 'borrow_settled'
    if record['outcome']!=expected:raise ValueError('whole-turn and action-only Interrupt settlements must retain their actual source kind')


def _validate_move_completion(engine,row,receipt):
    completion=getattr(engine,'_move_completions',{}).get(receipt.get('move_completion'))
    if (completion is None or completion['actor'] is not row['actor'] or completion['move_id']!=row['move_id']
            or completion['phase']!='complete' or completion['round']!=receipt['round']
            or receipt['actions']!=__import__('jump_move_actions').interrupt_actions(engine,row)):
        raise ValueError('selected Interrupt receipt lost its real completed native Move')
    if row['source']==__import__('juggler').FIRST:
        proof=__import__('juggler').first_request(engine,row['actor'],row,historical=True)
        if [t.entity_id for t in completion['targets']]!=[proof['target_id']]:raise ValueError('First Blood completed target evidence changed')


def _validate_switch_loan(engine,index,loan,window,request):
    import party_actions as PARTY
    fields=('source','actor','slot','role','due_round','settlement_clock','trainer_id',
        'encounter_epoch','switch_request_id','move_id')
    if (request is None or request['mode']!='switch_interrupt'
            or any(request[k]!=loan[k] for k in fields) or loan['settlement_clock']!='none'
            or loan['due_round'] not in ((loan['borrow_round'],loan['borrow_round']+1) if loan['source']==__import__('juggler').FIRST else (loan['borrow_round']+1,)) or window['round']!=loan['borrow_round']):
        raise ValueError('switch Interrupt loan differs from its actual selected action-only declaration')
    trainer=index.get(loan['trainer_id'])
    if loan['source']==__import__('juggler').FIRST:__import__('juggler').validate_first_loan(engine,index,loan)
    else:PARTY.validate_switch_lock(engine,loan['actor'],{'trainer':trainer,
        'request_id':loan['switch_request_id'],'scope':[loan['encounter_epoch'],loan['borrow_round']]})
    if loan['status'] not in ('owed','settled','cancelled'):raise ValueError('known switch Interrupt loan disposition required')
    completion=loan['move_completion']
    if completion is None:
        if not any(f['loan_id']==loan['id'] for f in getattr(engine,KEY)['frames']):
            raise ValueError('uncompleted switch Interrupt requires its actual open native action frame')
    elif request['status']!='completed' or request['receipt'].get('move_completion')!=completion:
        raise ValueError('switch Interrupt loan lost its native Move completion receipt')
    if loan['status']=='owed':
        _switch_owner(engine,loan,loan['actor'])
        if loan['settlement'] is not None or loan['due_round']<engine.round_no:
            raise ValueError('switch Interrupt debt cannot pass its actual next-round boundary')
        schedule=getattr(engine,'_initiative_schedule',None)
        if schedule and schedule['round']==loan['due_round']:
            row=schedule['slots'].get(loan['slot'])
            if row is None or row['role']!=loan['role']:raise ValueError('switch debt slot was dropped or rebound')
            _switch_owner(engine,loan,row['actor'])
    elif loan['status']=='settled':
        receipt=loan['settlement']
        if (completion is None or receipt['slot']!=loan['slot'] or receipt['round']!=loan['due_round']
                or receipt['clock']!='none' or index.get(receipt['actor'].entity_id) is not receipt['actor']):
            raise ValueError('switch debt settlement requires its actual no-clock next-round slot')
    else:
        receipt=loan.get('cancel_receipt',{})
        if (completion is None or loan['settlement'] is not None or receipt.get('producer')!='Engine.end_encounter'
                or type(receipt.get('round')) is not int or not loan['borrow_round']<=receipt['round']<=engine.round_no):
            raise ValueError('switch debt cancellation requires its actual encounter-end boundary')


def status(engine):
    state = getattr(engine,KEY,None)
    current = frame(engine)
    return {'status':'open' if current else 'ready' if state and any(w['cursor']<len(w['requests']) for w in state['windows'].values()) else 'clear',
            'active_actor_id':None if current is None else current['actor'].entity_id,
            'frames':0 if state is None else len(state['frames']),
            'owed_turns':[] if state is None else [{'id':x['id'],'slot':x['slot'],'due_round':x['due_round']} for x in state['loans'].values() if x['status']=='owed']}


def end_encounter(engine):
    require_clear(engine)
    state = getattr(engine,KEY,None)
    if state:
        for loan in state['loans'].values():
            if loan['status']=='owed':
                loan['status']='cancelled'
                loan['cancel_receipt']={'producer':'Engine.end_encounter','round':engine.round_no,
                                        'elapsed_seconds':engine.elapsed_seconds}


def _validate_world(engine,index):
    state = getattr(engine,KEY,None)
    if state is None:return True
    if state.get('version')!=1:
        raise ValueError('known initiative interrupt version required')
    C.integer(state['sequence'],'reaction window sequence',0)
    if state['sequence']!=len(state['windows']):
        raise ValueError('reaction windows require exact native sequence')
    for key,window in state['windows'].items():
        parent=window['parent'];between=window['trigger']['kind']=='between'
        overflow=window['trigger']['kind']=='duelist_overflow'
        round_end=window['trigger'].get('round_end_source') is not None
        if round_end:
            if window['trigger']['kind']!='accuracy' or parent is not None or __import__('focus_punch').reaction_origin(engine,window['trigger']['event_id'],live=False)!=window['trigger']['round_end_source']:raise ValueError('actual no-owner round-end Move reaction origin required')
        if (key!=window['id'] or (between and parent is not None)
                or (not between and not overflow and not round_end and (parent is None or index.get(parent.entity_id) is not parent))
                or (overflow and parent is not None and index.get(parent.entity_id) is not parent)):
            raise ValueError('reaction window requires its actual suspended owner')
        C.integer(window['round'],'reaction round',1,engine.round_no)
        cursor = C.integer(window['cursor'],'reaction cursor',0,len(window['requests']))
        if window['signature']!=_signature(window['trigger'],window['requests']):
            raise ValueError('reaction declaration changed after its actual priority decision')
        if window['trigger']['owner'] is not window['parent'] or window['trigger']['round']!=window['round']:
            raise ValueError('reaction trigger differs from actual window owner/round')
        if overflow:
            import duelist as DUELIST
            DUELIST.overflow_trigger(engine,window['trigger']['overflow_id'],allow_completed=True)
        elif between:
            trigger=window['trigger']
            if set(trigger)!={'kind','round','schedule_cursor','closure_sequence','epoch','owner'}:
                raise ValueError('between-turn trigger has unknown fields')
            C.integer(trigger['closure_sequence'],'between-turn closure',0,len(engine._turn_closures))
            C.integer(trigger['schedule_cursor'],'between-turn schedule cursor',0)
            C.integer(trigger['epoch'],'between-turn encounter epoch',0,getattr(engine,'_party_encounter_epoch',0))
            if cursor<len(window['requests']):
                schedule=getattr(engine,'_initiative_schedule',None)
                if (not schedule or schedule['status']!='active' or schedule['round']!=window['round']
                        or schedule['cursor']!=trigger['schedule_cursor'] or schedule['open_slot'] is not None
                        or trigger['epoch']!=getattr(engine,'_party_encounter_epoch',0)):
                    raise ValueError('open between-turn window lost its actual schedule boundary')
        elif window['trigger']['kind']=='move':
            import passive_events as EVENTS
            ev = engine._passive_events.get(window['trigger']['event_id'])
            if not ev or ev['actor'] is not window['parent'] or EVENTS.observations(engine,ev['id'])!=window['trigger']['observations']:
                raise ValueError('reaction move observation changed')
            if 'move_return' in window['trigger']:
                import move_completion as COMPLETE
                returned=COMPLETE.require_returned_event(engine,ev['id'])
                if (window['trigger']['move_return']!=returned or
                        window['trigger'].get('move_return_fingerprint')!=ROOT.fingerprint(returned)):
                    raise ValueError('reaction lost its whole Move return receipt')
        elif window['trigger']['kind']=='accuracy':
            event=engine._passive_events.get(window['trigger']['event_id'])
            import move_defense_reactions as DEFENSE
            defense=None if event is None else DEFENSE._defense(engine,event)
            if (event is None or (not round_end and event['actor'] is not window['parent']) or defense is None or
                    defense['fingerprint']!=window['trigger']['defense_fingerprint']):
                raise ValueError('reaction accuracy declaration changed')
        elif window['trigger']['kind']=='native_accuracy':
            event=__import__('move_defense_reactions').native_event(engine,window['trigger']['event_id'])
            native_defense=event.get(__import__('move_defense_reactions').NATIVE_DEFENSE)
            if native_defense is None or native_defense['facts']!=window['trigger']['facts'] or event['actor'] is not parent:raise ValueError('native Attack reaction source changed')
        elif window['trigger']['kind']=='reaction':
            parent_window = state['windows'].get(window['trigger']['window_id'])
            parent_request = None if not parent_window else next((r for r in parent_window['requests'] if r['id']==window['trigger']['request_id']),None)
            if not parent_request or parent_request['actor'] is not window['parent'] or parent_request['status'] not in ('open','completed'):
                raise ValueError('nested reaction lacks its actual parent occurrence')
        priorities = []
        for n,row in enumerate(window['requests']):
            actor = row['actor']; DERIVE.selected(engine.r,row['source'])
            if index.get(actor.entity_id) is not actor:
                raise ValueError('reaction owner must resolve to its actual actor')
            priorities.append(C.integer(row['priority'],'reaction priority'))
            expected = 'completed' if n<cursor else 'open' if any(f['window_id']==key and f['request_id']==row['id'] for f in state['frames']) else 'ready'
            if row['status']!=expected and not (n<cursor and row['status']=='skipped'):
                raise ValueError('reaction progress differs from its actual completed frames')
            if row['status']=='skipped' and (row['receipt'].get('paid') is not False or row['receipt']['actions'] or row['receipt']['loan_id'] is not None):
                raise ValueError('declined reaction cannot contain payment or action/turn grant')
            if n<cursor and (row['receipt']['actor'] is not actor or row['receipt']['parent'] is not window['parent']):
                raise ValueError('reaction receipt requires its actual actor and resumed owner')
            if 'move_id' in row:
                import move_defense_reactions as DEFENSE
                if row['source']==__import__('juggler').FIRST:__import__('juggler').first_request(engine,actor,row,historical=True)
                elif overflow:
                    import duelist as DUELIST
                    DUELIST.validate_interrupt(engine,window['trigger'],row)
                elif row['move_id'] in __import__('combat_move_reactions').SOURCES:__import__('combat_move_reactions').validate_request(engine,window,row)
                else:DEFENSE.validate_move_interrupt_request(engine,window,row)
                if row['status']=='completed':_validate_move_completion(engine,row,row['receipt'])
        if any(a<b for a,b in zip(priorities,priorities[1:])):
            raise ValueError('reaction order contradicts declared precedence')
    previous = suspended_owner(engine)
    for current in state['frames']:
        if current['status']!='open' or current['parent'] is not previous:
            raise ValueError('reaction frame stack lost actual suspended continuation')
        window = state['windows'][current['window_id']]
        row = window['requests'][window['cursor']]
        if row['id']!=current['request_id'] or row['actor'] is not current['actor']:
            raise ValueError('reaction frame is not its next actual priority request')
        previous = current['actor']
    if state['frames'] and engine._active_turn_actor is not previous:
        raise ValueError('active turn differs from actual reaction owner')
    for key,loan in state['loans'].items():
        DERIVE.selected(engine.r,loan['source'])
        if key!=loan['id'] or index.get(loan['actor'].entity_id) is not loan['actor']:
            raise ValueError('future loan must preserve its actual borrower')
        window = state['windows'].get(loan['window_id'])
        request = None if not window else next((r for r in window['requests'] if r['id']==loan['request_id']),None)
        if loan.get('mode')=='switch_interrupt':
            _validate_switch_loan(engine,index,loan,window,request)
            continue
        if (not request or request['mode']!='borrow_turn' or request['actor'] is not loan['actor']
                or any(request[k]!=loan[k] for k in ('source','slot','role','due_round','settlement_clock'))):
            raise ValueError('future loan differs from its actual sourced reaction declaration')
        C.integer(loan['borrow_round'],'borrow round',1,engine.round_no)
        C.integer(loan['due_round'],'borrowed future round',loan['borrow_round'],loan['borrow_round']+1)
        if loan['status'] not in ('owed','settled','cancelled') or loan['settlement_clock'] not in ('none','owner_turn'):
            raise ValueError('known future loan payment policy required')
        sequence = loan['borrow_closure']
        if sequence is not None:
            C.integer(sequence,'borrow closure',1,len(engine._turn_closures))
            closure = engine._turn_closures[sequence-1]
            if closure.get('kind')!='borrowed' or closure.get('loan_id')!=key or closure['actor'] is not loan['actor']:
                raise ValueError('future debt lacks its actual borrowed native turn closure')
        elif not any(f['loan_id']==key for f in state['frames']):
            raise ValueError('future debt lacks its actual open borrowed turn')
        if loan['status']=='settled':
            receipt = loan['settlement']
            if sequence is None or receipt['slot']!=loan['slot'] or receipt['round']!=loan['due_round'] or receipt['clock']!=loan['settlement_clock']:
                raise ValueError('future loan settlement differs from its actual due boundary')
            if index.get(receipt['actor'].entity_id) is not receipt['actor']:
                raise ValueError('future settlement recipient must resolve')
            if receipt['clock']=='owner_turn':
                closure = engine._turn_closures[C.integer(receipt['closure_sequence'],'settlement closure',1,len(engine._turn_closures))-1]
                if closure['actor'] is not receipt['actor'] or closure['round']!=receipt['round'] or closure.get('kind')=='borrowed':
                    raise ValueError('future debt settlement lacks its actual ordinary owner closure')
        elif loan['status']=='cancelled':
            receipt = loan.get('cancel_receipt',{})
            if (sequence is None or loan['settlement'] is not None or receipt.get('producer')!='Engine.end_encounter'
                    or type(receipt.get('round')) is not int or not loan['borrow_round']<=receipt['round']<=engine.round_no):
                raise ValueError('cancelled loan lacks its actual native encounter-end boundary')
        elif loan['settlement'] is not None or loan['due_round']<engine.round_no:
            raise ValueError('future debt was changed or advanced past without settlement')
    return True


def validate_world(engine,index):
    try:
        return _validate_world(engine,index)
    except (KeyError,TypeError,AttributeError,IndexError) as exc:
        raise ValueError('malformed actual initiative interrupt state') from exc
