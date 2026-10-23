"""Source-bound equipment choices and native two-target Trick execution.

Choices are facts about an actual effect occurrence. They never supply a hit,
trigger, source, frequency exemption or a replacement item instance.
"""
from copy import deepcopy
import common_checks as C
import effect_contracts as CONTRACTS
import items as ITEMS
import state_grants as G
import world_entities as W
import equipment_protection as PROTECTION
import held_equipment as HELD

RECORDS="_equipment_choices"
TRICK="_equipment_trick_activation"
MOVE_EFFECTS={
 "move/바꿔치기":{"type":"swap_items","between":["self","target"]},
 "move/탁쳐서떨구기":{"type":"item_drop","slot":"held or accessory","choose":"user"},
 "move/도둑질":{"type":"steal_item","if":"user holds nothing","slot":"held or accessory"},
 "move/쪼아대기":{"type":"steal_item","if":"user holds nothing","slot":"held or accessory"},
 "move/탐내기":{"type":"steal_item","if":"user holds nothing","slot":"held or accessory"},
 "move/기프트패스":{"type":"give_item","to":"target","if":"target holds nothing"},
 "move/불태우기":{"type":"incinerate_equipment"},
 "move/트릭":{"type":"swap_items","between":["two targets"],"requires":"hit both (no roll for self/consenting ally)"},
}
REACTIONS={"ability/나쁜손버릇":"on_hit_received","ability/매지션":"on_hit_dealt"}
REACTION_EFFECT={"type":"equipment_reaction"}

def _semantic(effect):return {k:v for k,v in effect.items() if not k.startswith("_")}

def require_source(e,source,effect):
    if e.r._selected_rule(source)!=source:raise ValueError("equipment action requires its actual selected source")
    expected=MOVE_EFFECTS.get(source,REACTION_EFFECT if source in REACTIONS else None)
    if expected is None or _semantic(effect)!=expected:raise ValueError("equipment payload differs from reviewed source")
    if source in REACTIONS:
        trigger="hit by melee attack" if source=="ability/나쁜손버릇" else "user hits target"
        selected=[_semantic(x) for x in e.r.ability_effects[source.split("/",1)[1]]]
        if selected!=[{"type":"trigger","text":trigger},REACTION_EFFECT]:raise ValueError("reaction selected effects differ from reviewed trigger and transfer")

def pending(e):
    return [row for c in W.actors(e) for row in c.custom_conditions.get(RECORDS,{}).values() if row["status"]=="awaiting_input"]

def ensure_clear(e):
    allowed=getattr(e,"_effect_resuming_receipt",None)
    for row in pending(e):
        if row["receipt"] is allowed:continue
        # Existing use_move_on owns an active target group. Finish observing its
        # hits before asking each victim; this grants no unrelated/new action.
        if row["source"]=="move/불태우기" and any(scope["move_id"]==row["source"] and scope["actor"] is row["actor"] and row["target"] in scope["targets"] for scope in getattr(e,"_move_activation_scopes",())):continue
        raise ValueError("resolve the actual equipment choice before another action or time boundary")

def _options(target,mode):
    slots=("held","주요손","주로쓰는손","반대손","주로 쓰는 손","반대 손","mainhand","offhand") if mode=="incinerate" else ("held",) if mode=="reaction" else ("held","장신구")
    return slots,ITEMS.equipment_options(target,slots)

def _issue(e,actor,target,effect,ctx,mode):
    source=ctx["source_id"];receipt=ctx["effect_receipt"];occurrence=ctx["effect_occurrence"]
    require_source(e,source,effect)
    CONTRACTS.validate_receipt(e,receipt,source,occurrence,actor,target,effect)
    slots,options=_options(target,mode)
    if mode in ("steal","reaction") and HELD.any_held(actor):return None
    if mode!="incinerate":
        operation="drop" if mode=="drop" else "transfer"
        statuses=[(row,PROTECTION.status(e,target,row,operation)) for row in options]
        import fashionista as FASHIONISTA
        if mode=="drop":statuses=[(row,FASHIONISTA.protection(e,target,row,"effect_drop") or status) for row,status in statuses]
        for row,status in statuses:
            # The actual printed trigger: the armed Style is Eternal keeps the item and pays now.
            if status["status"]=="blocked" and status.get("source")==FASHIONISTA.STYLE:FASHIONISTA.keep(e,target,status,operation="effect_drop" if mode=="drop" else operation,source=source)
        options=[row for row,status in statuses if status["status"]!="blocked"]
    if not options:return None
    if mode in ("steal","drop") and len(options)==1 and PROTECTION.status(e,target,options[0],"drop" if mode=="drop" else "transfer")["status"]=="allowed":
        if mode=="drop":ITEMS.drop_equipment(e,target,[options[0]["key"]],slots=slots,source=source)
        else:ITEMS.transfer_equipment(e,target,actor,options[0]["key"],slots=slots)
        return None
    records=actor.custom_conditions.setdefault(RECORDS,{})
    if occurrence in records:return records[occurrence]["pending"]
    chooser=target if mode=="incinerate" else actor
    note=C.PendingDecision("Choose drop or one tick of HP loss" if mode=="incinerate" else "Choose whether to use this triggered Free action" if mode=="reaction" else "Choose one actual equipment instance",basis={"choice_id":occurrence,"source":source,"chooser_id":chooser.entity_id,"options":deepcopy(options),"choices":["drop","hp_loss"] if mode=="incinerate" else ["accept","decline"] if mode=="reaction" else None})
    records[occurrence]={"id":occurrence,"receipt":receipt,"source":source,"effect":deepcopy(effect),"actor":actor,"target":target,"chooser":chooser,"mode":mode,"slots":slots,"options":options,"actor_held":deepcopy(HELD.entries(actor)),"boundary":CONTRACTS.boundary(e,actor,target),"profile":CONTRACTS.source_profile(e,source),"status":"awaiting_input","pending":note,"declaration":None}
    row=records[occurrence]
    if mode in ("steal","drop") and _dual_choice(target,options):
        worn=[x for x in options if not x['held']]
        if not worn:return _held_pending(row,{})
        row['pending']=C.PendingDecision('Choose worn equipment or the held-item category; its actual holder chooses the held instance',basis={'choice_id':occurrence,'chooser_id':actor.entity_id,'options':[{'key':'held-group','held':True},*deepcopy(worn)]})
        return row['pending']
    if mode in ("steal","drop") and len(options)==1:
        return resolve(e,actor,occurrence,selection=options[0]["key"])
    return note

def _finish_choice(e,row,result,declaration):
    row.update(status="completed",declaration=declaration,result=result)
    CONTRACTS.finish(e,row["receipt"],"completed",result)
    return result

def _consent_pending(row):
    remaining=[c for c in row["permission_holders"] if row["permissions"].get(c.entity_id) is None]
    row["chooser"]=remaining[0]
    row["pending"]=C.PendingDecision("The actual Leek holder chooses whether to permit this removal",basis={"choice_id":row["id"],"source":row["source"],"protection_source":"ability/대파의달인","chooser_id":row["chooser"].entity_id,"requested":deepcopy(row["requested_declaration"]),"choices":["consent","refuse"]})
    return row["pending"]

def _dual_choice(holder,options):
    return bool(HELD.capacity(holder)['sources']) and sum(bool(x.get('held')) for x in options)>1


def _held_pending(row,requested):
    row.update(phase='held_selection',chooser=row['target'],requested_declaration=deepcopy(requested))
    row['pending']=C.PendingDecision('The actual holder chooses which held instance this source affects',basis={'choice_id':row['id'],'source':row['source'],'chooser_id':row['chooser'].entity_id,'options':[deepcopy(x) for x in row['options'] if x['held']]})
    return row['pending']


def _pair_pending(row):
    remaining=[c for c in row['pair'] if row['pair_selections'].get(c.entity_id)=='pending']
    row.update(phase='exchange_selection',chooser=remaining[0])
    row['pending']=C.PendingDecision('Each affected holder selects one actual held instance for this exchange',basis={'choice_id':row['id'],'source':row['source'],'chooser_id':row['chooser'].entity_id,'options':ITEMS.equipment_options(row['chooser'],('held',))})
    return row['pending']


def exchange_dispatch(e,actor,first,second,effect,ctx,*,swap=True):
    source=ctx['source_id'];require_source(e,source,effect)
    parent_target=ctx['target'];occurrence=ctx['effect_occurrence']
    CONTRACTS.validate_receipt(e,ctx['effect_receipt'],source,occurrence,actor,parent_target,effect)
    pair=(first,second);options=[ITEMS.equipment_options(c,('held',)) for c in pair]
    selections={c.entity_id:None if not choices or not swap and c is second else choices[0]['key'] if len(choices)==1 else 'pending' for c,choices in zip(pair,options)}
    row={'id':occurrence,'receipt':ctx['effect_receipt'],'source':source,'effect':deepcopy(effect),'actor':actor,'target':parent_target,'chooser':actor,'mode':'exchange','pair':list(pair),'swap':swap,'pair_options':options,'pair_selections':selections,'actor_held':deepcopy(HELD.entries(actor)),'slots':('held',),'options':[],'boundary':CONTRACTS.boundary(e,actor,parent_target),'profile':CONTRACTS.source_profile(e,source),'status':'awaiting_input','declaration':None}
    if 'pending' in selections.values():
        actor.custom_conditions.setdefault(RECORDS,{})[occurrence]=row
        return _pair_pending(row)
    holdings=[(c,ITEMS.selected_equipment(c,selections[c.entity_id],('held',))) for c in pair if selections[c.entity_id] is not None]
    protections=[(c,PROTECTION.status(e,c,item,'exchange' if swap else 'give')) for c,item in holdings]
    if any(x['status']=='blocked' for c,x in protections):
        import fashionista as FASHIONISTA
        for c,x in protections:
            if x['status']=='blocked' and x.get('source')==FASHIONISTA.STYLE:FASHIONISTA.keep(e,c,x,operation='exchange' if swap else 'give',source=source)
        ctx['equipment_result']={'changed':False,'blocked_by':[x for c,x in protections if x['status']=='blocked']};return None
    requiring=list(dict.fromkeys(c for c,x in protections if x['status']=='needs_consent'))
    if not requiring:
        ctx['equipment_result']=ITEMS.exchange_items(e,first,second,swap=swap,first_selection=selections[first.entity_id],second_selection=selections[second.entity_id]);return None
    row.update(phase='removal_consent',requested_declaration={},permission_holders=requiring,permissions={c.entity_id:None for c in requiring})
    actor.custom_conditions.setdefault(RECORDS,{})[occurrence]=row
    return _consent_pending(row)


def dispatch(e,a,t,effect,ctx):
    source=ctx.get("source_id")
    if source=="move/트릭":
        require_source(e,source,effect)
        context=a.custom_conditions.get(TRICK)
        if not context or t not in context["targets"]:raise ValueError("Trick requires its actual two-target activation")
        context["hits"][t.entity_id]=True
        return None
    if effect["type"]=="incinerate_equipment":return _issue(e,a,t,effect,ctx,"incinerate")
    return _issue(e,a,t,effect,ctx,"drop" if effect["type"]=="item_drop" else "steal")

def resolve(e,chooser,choice_id,*,selection=None,choice=None,accept=None,consent=None):
    rows=[row for c in W.actors(e) for key,row in c.custom_conditions.get(RECORDS,{}).items() if key==choice_id]
    if len(rows)!=1 or rows[0]['chooser'] is not chooser:raise ValueError('actual equipment choice owner required')
    row=rows[0];declaration={'selection':selection,'choice':choice,'accept':accept,'consent':consent}
    if row['status']=='completed':
        if declaration!=row['declaration']:raise ValueError('completed equipment choice cannot change')
        return row['result']
    actor,target=row['actor'],row['target'];mode=row['mode']
    require_source(e,row['source'],row['effect'])
    CONTRACTS.validate_receipt(e,row['receipt'],row['source'],row['id'],actor,target,row['effect'])
    if CONTRACTS.boundary(e,actor,target)!=row['boundary'] or CONTRACTS.source_profile(e,row['source'])!=row['profile']:raise ValueError('equipment choice source or lifetime changed')
    if mode=='exchange':unchanged=[ITEMS.equipment_options(c,('held',)) for c in row['pair']]==row['pair_options']
    else:
        options=ITEMS.equipment_options(target,row['slots'])
        if mode!='incinerate':options=[x for x in options if PROTECTION.status(e,target,x,'drop' if mode=='drop' else 'transfer')['status']!='blocked']
        unchanged=options==row['options']
    if not unchanged or HELD.entries(actor)!=row['actor_held']:raise ValueError('equipment changed after the actual hit')
    def nochange(result):
        with CONTRACTS.resuming(e,row['receipt']):
            CONTRACTS.validate_continuation(e,row['receipt']);_finish_choice(e,row,result,declaration)
            import effects as FX
            FX.resume_effects(e,row['receipt'])
        return result
    phase=row.get('phase')
    if phase=='removal_consent':
        if type(consent) is not bool or any(x is not None for x in (selection,choice,accept)):raise ValueError('actual holder must explicitly consent or refuse')
        if not consent:return nochange({'changed':False,'refused_by':chooser.entity_id})
        row['permissions'][chooser.entity_id]=True
        if any(x is None for x in row['permissions'].values()):return _consent_pending(row)
        requested=row['requested_declaration'];selection=requested.get('selection');choice=requested.get('choice');accept=requested.get('accept')
    elif phase=='held_selection':
        if selection is None or any(x is not None for x in (choice,accept,consent)):raise ValueError('choose one actual held instance')
        selected=ITEMS.selected_equipment(target,selection,('held',));row['selected_key']=selected['key'];row['phase']='selected'
        requested=row['requested_declaration'];choice=requested.get('choice');accept=requested.get('accept')
        selection=selected['key'] if mode in ('drop','steal') else None
    elif phase=='exchange_selection':
        if selection is None or any(x is not None for x in (choice,accept,consent)):raise ValueError('choose one actual exchange instance')
        selected=ITEMS.selected_equipment(chooser,selection,('held',));row['pair_selections'][chooser.entity_id]=selected['key']
        if 'pending' in row['pair_selections'].values():return _pair_pending(row)
        row['phase']='selected';selection=None
    elif consent is not None:raise ValueError('consent requires actual pending holder decision')
    if mode in ('drop','steal'):
        if choice is not None or accept is not None:raise ValueError('select one actual equipment instance')
        if _dual_choice(target,row['options']) and row.get('selected_key') is None:
            if selection=='held-group':return _held_pending(row,declaration)
            selected=ITEMS.selected_equipment(target,selection,row['slots'])
            if selected['held']:raise ValueError('the affected holder chooses the actual held instance')
        selected=ITEMS.selected_equipment(target,selection,row['slots'])
        removals=[(target,selected,'drop' if mode=='drop' else 'transfer')]
    elif mode=='incinerate':
        if choice not in ('drop','hp_loss') or selection is not None or accept is not None:raise ValueError('affected actor chooses drop or HP loss')
        if choice=='drop' and _dual_choice(target,row['options']) and row.get('selected_key') is None:return _held_pending(row,declaration)
        drops=[x for x in row['options'] if not x['held'] or not row.get('selected_key') or x['key']==row['selected_key']]
        row['drop_keys']=[x['key'] for x in drops]
        removals=[(target,x,'drop') for x in drops] if choice=='drop' else []
    elif mode=='exchange':
        removals=[(c,ITEMS.selected_equipment(c,row['pair_selections'][c.entity_id],('held',)),'exchange' if row['swap'] else 'give') for c in row['pair'] if row['pair_selections'][c.entity_id] is not None]
    else:
        if type(accept) is not bool or selection is not None or choice is not None:raise ValueError('triggered Free action requires accept or decline')
        if accept and _dual_choice(target,row['options']) and row.get('selected_key') is None:return _held_pending(row,declaration)
        selected=next((x for x in row['options'] if x['key']==row.get('selected_key')),row['options'][0])
        removals=[(target,selected,'transfer')] if accept else []
    protections=[(holder,PROTECTION.status(e,holder,item,operation)) for holder,item,operation in removals]
    if any(x['status']=='blocked' for holder,x in protections):
        if mode=='incinerate':raise PROTECTION.ProtectedEquipment('protected equipment cannot be dropped; choose sourced HP alternative')
        return nochange({'changed':False,'blocked_by':[x for holder,x in protections if x['status']=='blocked']})
    if row.get('phase')!='removal_consent':
        requiring=list(dict.fromkeys(holder for holder,x in protections if x['status']=='needs_consent'))
        approved={holder.entity_id:True for holder in requiring if holder is chooser and mode=='incinerate'}
        if requiring:
            requested={'selection':selection,'choice':choice,'accept':accept,'consent':None}
            row.update(permission_holders=requiring,permissions={holder.entity_id:approved.get(holder.entity_id) for holder in requiring},requested_declaration=requested)
            if any(value is None for value in row['permissions'].values()):row['phase']='removal_consent';return _consent_pending(row)
    import frequency as FREQ
    if mode=='reaction' and accept:
        if actor.fainted or actor.abilities_suppressed or row['source'].split('/',1)[1] not in actor.abilities:raise ValueError('reaction ability no longer available')
        if not FREQ.activation_allowed(actor,row['source'],e.r.ability_freq.get(row['source'].split('/',1)[1]),engine=e):raise ValueError('reaction frequency exhausted')
    def apply(staged,actual,other):
        saved=actual.custom_conditions[RECORDS][choice_id]
        consent_by=tuple(c for c in saved.get('permission_holders',()) if saved.get('permissions',{}).get(c.entity_id) is True)
        if mode=='drop':result=ITEMS.drop_equipment(staged,other,[selection],slots=row['slots'],consent_by=consent_by,source=row['source'])
        elif mode=='steal':result=ITEMS.transfer_equipment(staged,other,actual,selection,slots=row['slots'],consent_by=consent_by)
        elif mode=='exchange':
            first,second=saved['pair'];selected=saved['pair_selections']
            result=ITEMS.exchange_items(staged,first,second,swap=saved['swap'],consent_by=consent_by,first_selection=selected[first.entity_id],second_selection=selected[second.entity_id])
        elif mode=='incinerate':
            if choice=='drop':result=ITEMS.drop_equipment(staged,other,saved['drop_keys'],slots=row['slots'],consent_by=consent_by,source=row['source'])
            else:
                import attack_damage_history as HISTORY
                amount=staged.tick_loss(other)
                HISTORY.received_loss(staged,other,amount,source=saved['source'],move=staged.r.move(saved['source']))
                result={'hp_loss':amount,'applications':1}
        elif not accept:result={'accepted':False,'changed':False}
        else:
            import action_lifecycle as ACTION
            if not ACTION.status_permission(staged,actual,'free',new_action=True):raise ValueError('reaction Free action not permitted')
            chosen=saved.get('selected_key') or saved['options'][0]['key']
            result=ITEMS.transfer_equipment(staged,other,actual,chosen,slots=('held',),consent_by=consent_by)
            ACTION.record_action(staged,actual,'free');FREQ.consume_activation(actual,row['source'],staged.r.ability_freq.get(row['source'].split('/',1)[1]),engine=staged);result['accepted']=True
        saved=actual.custom_conditions[RECORDS][choice_id]
        return _finish_choice(staged,saved,result,declaration)
    with CONTRACTS.resuming(e,row['receipt']):
        CONTRACTS.validate_continuation(e,row['receipt']);result=G.transition(e,actor,apply,participants=(target,))
        import effects as FX
        FX.resume_effects(e,row['receipt'])
    return result


def offer_reaction(e,actor,event,target,source):
    if target is None or event.get("event")!=REACTIONS[source]:return None
    name=source.split("/",1)[1]
    if actor.fainted or actor.abilities_suppressed or name not in actor.abilities or HELD.any_held(actor) or not HELD.any_held(target):return None
    move=event.get("move")
    if not isinstance(move,dict) or move.get("id") not in e.r.moves:return None
    if source=="ability/나쁜손버릇" and "근접" not in str(move.get("range","")):return None
    if source=="ability/매지션":
        actual=move.get("_actual_targets")
        if actual is None or len(actual)!=1 or actual[0] is not target or move.get("class") not in ("물리","특수"):return None
        # A one-victim area move is still not a single-target attack.
        if "대상 1" not in str(move.get("range","")):return None
    import frequency as FREQ
    if not FREQ.activation_allowed(actor,source,e.r.ability_freq.get(name),engine=e):return None
    require_source(e,source,REACTION_EFFECT)
    occurrence,receipt=CONTRACTS.issue_receipt(e,source,actor,target,REACTION_EFFECT,0)
    note=_issue(e,actor,target,REACTION_EFFECT,{"source_id":source,"effect_receipt":receipt,"effect_occurrence":occurrence},"reaction")
    if note is None:
        CONTRACTS.finish(e,receipt,"completed")
        return None
    row=actor.custom_conditions[RECORDS][occurrence]
    row["native_trigger"]={"event":event["event"],"move_id":move["id"],"actual_targets":[c.entity_id for c in move.get("_actual_targets",())],"melee":"근접" in str(move.get("range",""))}
    CONTRACTS.finish(e,receipt,"awaiting_input",note)
    return note

def trick_context(e,actor,target,move_id):
    if move_id!="move/트릭":return None
    row=actor.custom_conditions.get(TRICK)
    if row is None or row.get("status")!="executing" or target not in row["targets"]:raise ValueError("Trick requires use_move_on and two explicit actual targets")
    scopes=getattr(e,"_move_activation_scopes",())
    if not any(s["actor"] is actor and s["move_id"]==move_id and tuple(s["targets"])==tuple(row["targets"]) for s in scopes):raise ValueError("Trick has no live native target activation")
    return row

def record_accuracy(e,actor,target,move,hit,natural):
    import held_item_reactions as HELD_REACTIONS
    HELD_REACTIONS.after_accuracy(e,actor,target,move,hit,natural)
    row=trick_context(e,actor,target,move["id"])
    if row is not None:
        row["hits"][target.entity_id]=bool(hit)
        row.setdefault("observations",{})[target.entity_id]={"hit":bool(hit),"natural":natural,"automatic":target.entity_id in row["consenting"]}

def automatic_accuracy(e,actor,target,move):
    row=trick_context(e,actor,target,move["id"])
    return bool(row and target.entity_id in row["consenting"])

def use_trick(e,actor,primary,everyone,options=None):
    CONTRACTS.ensure_clear(e)
    if options is None or "targets" not in options:
        return C.PendingDecision("Choose exactly two actual Trick targets and explicitly identify consenting allies",basis={"source":"move/트릭","required":["targets","consenting"]})
    if set(options)-{"targets","consenting"}:raise ValueError("unknown Trick option; hits and exemptions are source-owned")
    targets=tuple(options["targets"]);consenting=tuple(options.get("consenting",()))
    if len(targets)!=2 or targets[0] is targets[1] or primary not in targets:raise ValueError("Trick requires two distinct actual targets including primary")
    index=W.actor_index(e)
    if any(index.get(c.entity_id) is not c or c not in everyone for c in (actor,)+targets):raise ValueError("Trick targets must be actual current actors")
    if any(c not in targets for c in consenting) or len({id(c) for c in consenting})!=len(consenting):raise ValueError("consent must identify each selected actor once")
    for c in consenting:
        if c is not actor and (actor.side is None or c.side is None or actor.side!=c.side):raise ValueError("automatic Trick accuracy requires self or an explicitly consenting actual ally")
    # Self-target has the source's automatic hit. Allies never acquire inferred consent.
    consent_ids={c.entity_id for c in consenting}|{c.entity_id for c in targets if c is actor}
    require_source(e,"move/트릭",MOVE_EFFECTS["move/트릭"])
    import weapon_actions as WEAPONS
    move=e.r.move("move/트릭")
    from grid import cheb
    for target in targets:
        if cheb(actor.pos,target.pos)>5:raise ValueError("Trick target lies outside its actual range")
        if e.grid is not None and e.grid.blocked(actor.pos,target.pos):raise ValueError("Trick line of sight is blocked")
        WEAPONS.validate_target(e,actor,target,move,allow_approach=False)
    rng_after=[]
    def apply(staged,a,*actual_targets):
        import move_activation as ACTIVATION
        import action_lifecycle as ACTION
        context={"status":"executing","targets":actual_targets,"consenting":sorted(consent_ids),"hits":{},"source":"move/트릭"}
        a.custom_conditions[TRICK]=context
        try:
            with ACTIVATION.open_scope(staged,a,"move/트릭",actual_targets,shared=False) as (activation,accuracy):
                for i,target in enumerate(actual_targets):
                    if i==0:staged.use_move(a,target,"move/트릭",_activation=activation)
                    else:
                        with ACTION.move_grant(staged,a,target,"move/트릭",source="same_move_activation") as grant:
                            staged.use_move(a,target,"move/트릭",count_use=False,_activation=activation,_action_grant=grant)
                    if i==0 and not activation.get("started"):return {"status":"not_activated","changed":False}
            hits={c.entity_id:context["hits"].get(c.entity_id) for c in actual_targets}
            result={"changed":False}
            if all(hits.values()):
                effect=MOVE_EFFECTS["move/트릭"]
                occurrence,token=CONTRACTS.issue_receipt(staged,"move/트릭",a,actual_targets[0],effect,0)
                ctx={"source_id":"move/트릭","effect_receipt":token,"effect_occurrence":occurrence,"target":actual_targets[0]}
                note=exchange_dispatch(staged,a,*actual_targets,effect,ctx,swap=True)
                result=ctx.get("equipment_result",note)
                CONTRACTS.finish(staged,token,"awaiting_input" if isinstance(note,C.PendingDecision) else "completed",result)
            receipt={"source":"move/트릭","targets":[c.entity_id for c in actual_targets],"consenting":sorted(consent_ids),"hits":hits,"observations":context.get("observations",{}),"result":result}
            a.custom_conditions.setdefault("_equipment_trick_history",[]).append(receipt)
            rng_after.append(staged.rng.getstate())
            return receipt
        finally:a.custom_conditions.pop(TRICK,None)
    result=G.transition(e,actor,apply,participants=targets)
    if rng_after:e.rng.setstate(rng_after[0])
    return result
