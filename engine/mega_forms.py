"""Scene-owned Mega forms over the shared stat, type, ability and equipment state."""
from copy import deepcopy
from pathlib import Path
import hashlib,json
import state_grants as G,ability_transitions as AB,world_entities as W

SOURCE='ch05-pokemon/메가진화'
DELTA='capability/델타진화'
KEY='mega_form'
STATS=('hp','atk','def','spa','spd','spe')
HEIR='feat/계승자'


import resolution_transaction as _FINGERPRINTS

def install(rules):
    rules.mega_form_policy=json.loads((Path(rules.root)/'data/mega-form-policy.json').read_text(encoding='utf-8'))


def require(rules):
    if rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Mega source requires its own form contract')


def uncontrolled(engine,pokemon):
    """C03-128 changes command treatment, never the actual loyalty relationship."""
    if KEY not in pokemon.spec:return False
    import acquired_features as ACQUIRED,trainer_feature_acquisition as FEATURES
    FEATURES._static_source(engine.r,HEIR)
    index=W.require_actors(engine,pokemon)
    validate_world(engine,index)
    trainer=index.get(pokemon.spec.get('trainer_id'))
    if trainer is None or trainer.kind!='trainer':raise ValueError('actual current Trainer required for Mega command authority')
    return ACQUIRED.owned_rule_count(trainer,HEIR)==0


def state(engine,create=False):
    value=getattr(engine,'_mega_state',None)
    if value is None:
        value={'version':1,'sequence':0,'definitions':{},'stone_bindings':{},'uses':{}}
        if create:engine._mega_state=value
    if not isinstance(value,dict) or set(value)!={'version','sequence','definitions','stone_bindings','uses'} or value['version']!=1 or type(value['sequence'])is not int or value['sequence']<0:
        raise ValueError('invalid Mega world state')
    return value


def signature(row):return _FINGERPRINTS.json_fingerprint(row, sort_keys=True, compact=False, allow_nan=True)


def stone_exception(rules,row):
    """The exact Delta Evolution source changes only Rayquaza's Stone gate."""
    exception=row.get('stone_exception')
    if exception is None:return None
    if (not isinstance(exception,dict) or exception.get('rule_id')!=DELTA or
        exception.get('required_move')!='move/화룡점정' or row.get('id')!='mega/레쿠쟈' or
        row.get('base_species')!='pokemon/레쿠쟈' or row.get('origin')!='catalog' or
        row.get('source')!='learnset/레쿠쟈' or row.get('stone_rules')!=[] or row.get('ability')!='ability/도주-playtest'):
        raise ValueError('only the exact Rayquaza Delta Evolution source waives a Mega Stone')
    if rules._selected_rule(DELTA)!=DELTA or rules._selected_rule(exception['required_move'])!=exception['required_move']:
        raise ValueError('selected Delta Evolution and Dragon Ascent sources required')
    import csv,io,source_context as SOURCES
    reference=exception.get('source_reference',{})
    content=SOURCES.verified_source(rules,reference,label='Delta Evolution')
    if reference.get('file')!='input/ch10-index-reference.md' or reference.get('line')!=31:
        raise ValueError('Delta Evolution needs its exact source statement locator')
    statement=content.decode('utf-8-sig').splitlines()[30]
    if hashlib.sha256(statement.encode('utf-8')).hexdigest()!=reference.get('line_sha256'):
        raise ValueError('Delta Evolution source statement changed')
    for key,filename,record,span,label in (
        ('learnset_reference','input/db/learnsets.csv',419,[11971,12005],'레쿠쟈'),
        ('move_reference','input/db/moves.csv',283,[303,303],'화룡점정'),
        ('ability_reference','input/db/abilities.csv',88,[172,173],'도주 [Playtest]')):
        reference=exception.get(key,{})
        content=SOURCES.verified_source(rules,reference,label='Delta Evolution '+key)
        if reference.get('file')!=filename or reference.get('record')!=record or reference.get('line_span')!=span:
            raise ValueError('Delta Evolution needs its actual CSV record locator')
        raw=b''.join(content.splitlines(keepends=True)[span[0]-1:span[1]])
        if hashlib.sha256(raw).hexdigest()!=reference.get('record_sha256'):
            raise ValueError('Delta Evolution exact CSV record changed')
        reader=csv.reader(io.StringIO(content.decode('utf-8-sig'),newline=''))
        cells=next(cells for number,cells in enumerate(reader,1) if number==record)
        if cells[0]!=label:raise ValueError('Delta Evolution CSV identity changed')
        if key=='learnset_reference' and (row.get('source_record_span')!=[record,record] or cells[-1]!='메가진화\n'+row.get('source_note','')):
            raise ValueError('Delta Evolution form note does not match its actual CSV record')
    return {'rule_id':DELTA,'move_id':exception['required_move']}


def validate_definition(rules,row):
    require(rules)
    if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not row['id'].startswith('mega/') or row.get('base_species') not in rules.species:
        raise ValueError('Mega definition needs its actual base species and stable identity')
    changes=row.get('stat_changes')
    if not isinstance(changes,dict) or not changes or any(k not in STATS[1:] or type(v)is not int for k,v in changes.items()):raise ValueError('Mega changes use whole non-HP statistic points')
    if row.get('origin')=='custom':
        if sum(changes.values())!=10 or not isinstance(row.get('reason'),str) or not row['reason'].strip():raise ValueError('custom Mega definition needs net+10 and its actual GM decision')
    elif row.get('origin')!='catalog':raise ValueError('explicit Mega definition origin required')
    if row.get('types') is not None:
        import type_state as TYPES
        TYPES.validate_types(rules,row['types'],label='Mega form types')
        if not row['types']:raise ValueError('a declared Mega typing must be nonempty')
    if not isinstance(row.get('ability'),str) or not row['ability'].startswith('ability/') or row['ability'] not in rules.selection.units:raise ValueError('Mega definition needs an actual ability source')
    if stone_exception(rules,row) is None:
        if not isinstance(row.get('stone_rules'),list) or not row['stone_rules'] or any(x not in rules.selection.units for x in row['stone_rules']):raise ValueError('Mega definition needs its actual stone rules')
    return row


def definition(engine,form_id):
    row=state(engine)['definitions'].get(form_id) or engine.r.mega_form_policy['forms'].get(form_id)
    if row is None:raise ValueError('source-resolved Mega form definition required')
    return validate_definition(engine.r,row)


def define(engine,form_id,*,base_species,stat_changes,ability,types=None,reason):
    from builder import species_lookup
    row={'id':form_id,'base_species':species_lookup(engine.r,base_species)['id'],'stat_changes':deepcopy(stat_changes),'ability':AB.ability_id(engine.r,ability),'types':deepcopy(types),'stone_rules':[engine.r.mega_form_policy['generic_stone_rule']],'origin':'custom','source':SOURCE,'reason':reason}
    validate_definition(engine.r,row)
    if form_id in state(engine)['definitions'] or form_id in engine.r.mega_form_policy['forms']:raise ValueError('Mega definition identities are immutable; use a new identity')
    state(engine,True)['definitions'][form_id]=row
    return deepcopy(row)


def bind_stone(engine,instance_id,form_id,*,reason):
    row=definition(engine,form_id);obj=getattr(engine,'_physical_objects',{}).get(instance_id)
    if row.get('stone_exception') is not None:raise ValueError('Delta Evolution does not bind a Mega Stone')
    if not isinstance(reason,str) or not reason.strip() or not obj or obj.get('kind')!='item_instance':raise ValueError('actual inspected Mega Stone instance and reason required')
    allowed=row['stone_rules']+[engine.r.mega_form_policy['generic_stone_rule']]
    if obj.get('item_rule_id') not in allowed:raise ValueError('this physical stone belongs to another form')
    if instance_id in state(engine)['stone_bindings']:raise ValueError('Mega Stone form identity already observed')
    state(engine,True)['stone_bindings'][instance_id]={'form_id':form_id,'definition_sha256':signature(row),'reason':reason}
    return deepcopy(state(engine)['stone_bindings'][instance_id])


def natural_alternatives(engine,pokemon,*,known=None):
    species=engine.r.species[pokemon.spec['species']]['name'];known=set(AB.known(pokemon) if known is None else known);result=[]
    for name in sum(engine.r.learnsets.get(species,{}).get('abilities',{}).values(),[]):
        try:
            uid=AB.ability_id(engine.r,name);engine.r.selection.require_supported_version(uid)
        except (ValueError,KeyError):continue
        if uid not in known and uid not in result:result.append(uid)
    return result


def equipped(actor,key):
    rows=getattr(actor,'_item_reg',{});matches=[(k,v) for k,v in rows.items() if key in (k,v.get('instance_id'))]
    if len(matches)!=1:raise ValueError('one actual equipped item instance must be selected')
    return matches[0]


def locked(engine,actor,*,instance_id=None,registration_key=None):
    row=actor.spec.get(KEY)
    return bool(row and (instance_id is not None and row.get('stone_instance')==instance_id or registration_key is not None and row.get('stone_registration')==registration_key))


ALLOCATION_FIELDS=('kind','species','nature','vitamin_bonus','capabilities','learned_poke_edges','stat_relation_exempt')


def allocation_context(pokemon):
    return {key:deepcopy(pokemon.spec[key]) for key in ALLOCATION_FIELDS if key in pokemon.spec}


def validate_stat_record(rules,form,base,sheet,context):
    """One activation/restore contract; HP alone gets the Mega relation exception."""
    import builder as B,pokemon_stat_edges as EDGES,state_fields as F
    if not isinstance(context,dict) or not set(context)<=set(ALLOCATION_FIELDS) or context.get('kind')!='pokemon' or context.get('species')!=form['base_species']:
        raise ValueError('Mega allocation context must describe the actual base species')
    if not isinstance(base,dict) or set(base)!=set(STATS) or any(type(v)is not int or v<F.stat_minimum(context,k) for k,v in base.items()):
        raise ValueError('Mega activation stat baseline missing')
    if sheet is None:return dict(form['stat_changes'])
    if not isinstance(sheet,dict) or set(sheet)!=set(STATS) or any(type(v)is not int or v<F.stat_minimum(context,k) for k,v in sheet.items()):
        raise ValueError('complete second-sheet statistics required')
    if sheet['hp']!=base['hp'] or sum(sheet.values())!=sum(base.values())+sum(form['stat_changes'].values()):
        raise ValueError('Mega second sheet preserves HP and the actual total allocated stat points')
    species_base=B.species_lookup(rules,context['species'])['base_stats']
    mega_base={k:v+form['stat_changes'].get(k,0) for k,v in species_base.items()}
    adjusted=B.allocation_base(rules,context,base_stats=mega_base)
    if any(sheet[k]<adjusted[k] for k in STATS):raise ValueError('Mega second sheet is below its adjusted base statistics')
    exemptions=EDGES.exemptions(rules,context)|{'hp'}
    for hi in STATS:
        for lo in STATS:
            if hi not in exemptions and lo not in exemptions and adjusted[hi]>adjusted[lo] and sheet[hi]<=sheet[lo]:
                raise ValueError('Mega second sheet violates non-HP base relations')
    return {k:sheet[k]-base[k] for k in STATS[1:] if sheet[k]!=base[k]}


def activation_plan(engine,trainer,pokemon,form_id,*,ring,stone=None,actor,replacement_ability=None,second_sheet=None):
    require(engine.r);validate_world(engine,W.actor_index(engine));row=definition(engine,form_id)
    index=W.actor_index(engine)
    if index.get(trainer.entity_id)is not trainer or index.get(pokemon.entity_id)is not pokemon:raise ValueError('actual registered Trainer and Pokemon required')
    if trainer.kind!='trainer' or pokemon.kind!='pokemon' or pokemon.spec.get('trainer_id')!=trainer.entity_id:raise ValueError('Mega activation requires the actual Trainer of this Pokemon')
    if pokemon.spec.get('species')!=row['base_species']:raise ValueError('Mega form does not match this Pokemon species')
    if KEY in pokemon.spec or trainer.entity_id in state(engine)['uses']:raise ValueError('Trainer already used Mega Evolution in this Scene')
    if actor not in (trainer,pokemon) or engine._active_turn_actor is not actor:raise ValueError('Mega Evolution uses the actual Pokemon or Trainer turn')
    exception=stone_exception(engine.r,row)
    if exception is not None:
        import move_state as MOVES
        if exception['move_id'] not in MOVES.known(engine.r,{'moves':MOVES.owned_list(pokemon.spec,'moves')}):
            raise ValueError('Delta Evolution requires this Rayquaza to know Dragon Ascent')
    ring_key,ring_row=equipped(trainer,ring)
    if (ring_row.get('item_id')!=engine.r.mega_form_policy['ring_rule'] and
            not __import__('z_moves').mega_ring(engine.r,ring_row.get('item_id')) or
            ring_row.get('slots')!=['장신구']):raise ValueError('actual accessory-slot Mega Ring required')
    ring_id=ring_row.get('instance_id');stone_id=stone_key=None
    equipment=[(ring_id,ring_row,trainer)]
    if exception is None:
        stone_key,stone_row=equipped(pokemon,stone)
        if not stone_row.get('held_slot'):raise ValueError('Mega Stone must actually be held')
        stone_id=stone_row.get('instance_id');equipment.append((stone_id,stone_row,pokemon))
    if any(not item_id for item_id,_,_ in equipment):raise ValueError('Mega link requires actual physical equipment identities')
    for item_id,item_row,holder in equipment:
        obj=getattr(engine,'_physical_objects',{}).get(item_id)
        if not obj or obj.get('equipped_by')!=holder.entity_id or obj.get('item_rule_id')!=item_row['item_id']:raise ValueError('Mega equipment registration and physical holder disagree')
        W.require_usable_object(obj)
        if engine.r._selected_rule(item_row['item_id'])!=item_row['item_id']:raise ValueError('selected Mega equipment rule changed')
    if any(x['ring_instance']==ring_id for x in state(engine)['uses'].values()):raise ValueError('this Mega Ring already supports a form for this Scene')
    if exception is None:
        binding=state(engine)['stone_bindings'].get(stone_id)
        if binding:
            if binding['form_id']!=form_id or binding['definition_sha256']!=signature(row):raise ValueError('actual stone is bound to another form')
        elif stone_row['item_id'] not in row['stone_rules'] or row['origin']=='custom':raise ValueError('actual generic Mega Stone needs its observed species/form binding')
    ability=row['ability'];known=set(AB.known(pokemon))
    if ability in known:
        if replacement_ability is None:raise ValueError('duplicate Mega ability requires an explicit naturally available unowned replacement')
        ability=AB.ability_id(engine.r,replacement_ability)
        if ability not in natural_alternatives(engine,pokemon):raise ValueError('Mega replacement must be naturally obtainable and currently unowned')
    elif replacement_ability is not None:raise ValueError('Mega ability replacement applies only to a duplicate')
    engine.r.selection.require_supported_version(ability)
    base=deepcopy(pokemon.spec['stats']);context=allocation_context(pokemon)
    changes=validate_stat_record(engine.r,row,base,second_sheet,context)
    if getattr(pokemon,'form',None) or getattr(pokemon,'custom_conditions',{}).get('transformed'):raise ValueError('an existing form needs its own explicit composition before Mega Evolution')
    plan={'definition':form_id,'definition_sha256':signature(row),'trainer_id':trainer.entity_id,'pokemon_id':pokemon.entity_id,'ring_instance':ring_id,'stone_instance':stone_id,'stone_registration':stone_key,'ability':ability,'duplicate_replacement':replacement_ability is not None,'known_at_activation':list(known),'natural_alternatives':natural_alternatives(engine,pokemon) if replacement_ability is not None else [],'stat_changes':changes,'base_stats_at_activation':base,'allocation_context':context,'second_sheet':deepcopy(second_sheet),'types':deepcopy(row['types']),'actor_id':actor.entity_id,'source':SOURCE,'ends':'scene'}
    if exception is not None:plan['stone_exception']=exception
    return plan


def activate(engine,trainer,pokemon,form_id,*,ring,stone=None,actor=None,replacement_ability=None,second_sheet=None):
    import turn as TURN,passive_events as PASSIVE,effect_contracts as CONTRACTS
    PASSIVE.ensure_clear(engine);CONTRACTS.ensure_clear(engine)
    actor=engine._active_turn_actor if actor is None else actor
    plan=activation_plan(engine,trainer,pokemon,form_id,ring=ring,stone=stone,actor=actor,replacement_ability=replacement_ability,second_sheet=second_sheet)
    def apply(e,c,t,payer):
        if not TURN.spend(e,payer,'swift','Mega Evolution'):raise ValueError('Mega Evolution requires an available actual Swift action')
        current=state(e,True);current['sequence']+=1;sid='mega:'+str(current['sequence']);record=deepcopy(plan);record['grant_source']=sid
        record['action_index']=len(getattr(payer,'_action_history',[]))-1
        G._source(c,sid,'mega_form',rule_id=SOURCE,producer_id=t.entity_id,lifetime='scene')
        for stat,delta in record['stat_changes'].items():G.stat(c,stat,delta,sid)
        if record['types'] is not None:G.type_operation(c,'set',record['types'],sid)
        G.grant(c,'abilities',AB.label(e.r,record['ability']),sid,'mega_form',rule_id=SOURCE,lifetime='scene')
        G.scalar(c,'form',form_id,sid);G.materialize(c,'abilities');G.reconcile(e,c)
        c.spec[KEY]=record;current['uses'][t.entity_id]={'trainer_id':t.entity_id,'pokemon_id':c.entity_id,'ring_instance':record['ring_instance'],'grant_source':sid}
        validate_world(e,W.actor_index(e));e.log(c.name+' Mega Evolution: '+form_id,SOURCE)
        return deepcopy(record)
    return G.transition(engine,pokemon,apply,participants=(trainer,actor))


def prepare_scene(engine):
    validate_world(engine,W.actor_index(engine))
    for c in W.actor_index(engine).values():
        if KEY in c.spec:G.preflight_revoke(c,c.spec[KEY]['grant_source'])


def end_scene(engine):
    index=W.actor_index(engine);prepare_scene(engine)
    targets=[c for c in index.values() if KEY in c.spec]
    if not targets:return
    def apply(e,first,*others):
        for c in (first,*others):
            row=c.spec[KEY];G.revoke(c,row['grant_source'],engine=e);c.spec.pop(KEY)
        state(e,True)['uses'].clear();validate_world(e,W.actor_index(e))
    G.transition(engine,targets[0],apply,participants=tuple(targets[1:]))


def validate_world(engine,index):
    current=state(engine);require(engine.r) if current['uses'] or current['definitions'] or current['stone_bindings'] else None
    if any(not isinstance(current[k],dict) for k in ('definitions','stone_bindings','uses')):raise ValueError('Mega state maps required')
    for fid,row in current['definitions'].items():
        if row.get('id')!=fid or row.get('origin')!='custom' or fid in engine.r.mega_form_policy['forms']:raise ValueError('invalid custom Mega identity')
        validate_definition(engine.r,row)
    for item_id,row in current['stone_bindings'].items():
        form=definition(engine,row.get('form_id'));obj=getattr(engine,'_physical_objects',{}).get(item_id)
        if form.get('stone_exception') is not None:raise ValueError('Delta Evolution cannot own a Stone binding')
        if not obj or obj.get('kind')!='item_instance' or obj.get('item_rule_id') not in form['stone_rules']+[engine.r.mega_form_policy['generic_stone_rule']] or row.get('definition_sha256')!=signature(form) or not row.get('reason'):raise ValueError('invalid actual Mega Stone binding')
    seen=set();rings=set()
    for c in index.values():
        row=c.spec.get(KEY);sources=c.spec.get(G.KEY,{}).get('sources',{});owned={k:v for k,v in sources.items() if v.get('kind')=='mega_form'}
        if row is None:
            if owned:raise ValueError('orphan Mega form contribution')
            continue
        if not isinstance(row,dict):raise ValueError('Mega form must be a source record')
        form=definition(engine,row.get('definition'));sid=row.get('grant_source');trainer=index.get(row.get('trainer_id'));use=current['uses'].get(row.get('trainer_id'))
        if c.kind!='pokemon' or not trainer or trainer.kind!='trainer' or row.get('pokemon_id')!=c.entity_id or c.spec.get('species')!=form['base_species'] or row.get('source')!=SOURCE or row.get('ends')!='scene' or row.get('definition_sha256')!=signature(form):raise ValueError('Mega form origin/lifetime changed')
        if set(owned)!={sid} or use!={'trainer_id':trainer.entity_id,'pokemon_id':c.entity_id,'ring_instance':row.get('ring_instance'),'grant_source':sid}:raise ValueError('Mega form and Trainer scene use disagree')
        if trainer.entity_id in seen or row['ring_instance'] in rings:raise ValueError('Mega Trainer or physical Ring supports duplicate forms')
        seen.add(trainer.entity_id);rings.add(row['ring_instance'])
        try:sequence=int(sid.removeprefix('mega:'))
        except (AttributeError,ValueError):raise ValueError('invalid Mega activation identity')
        if not 1<=sequence<=current['sequence']:raise ValueError('Mega sequence changed')
        exception=stone_exception(engine.r,form)
        if exception is not None:
            # Knowing the move admits activation, not a new continuous lifetime.
            if row.get('stone_exception')!=exception or row.get('stone_instance') is not None or row.get('stone_registration') is not None:
                raise ValueError('Delta Evolution activation must have its exact Stone exception and no Stone link')
        else:
            if row.get('stone_exception') is not None:raise ValueError('ordinary Mega form cannot waive its Stone')
            import fashionista as FASHIONISTA
            obj=getattr(engine,'_physical_objects',{}).get(row['stone_instance'])
            if FASHIONISTA.wardrobe_holds(engine,c,row.get('stone_instance')):
                # ch04:2031-2033: a Mega Evolved Chic Pokemon stays Mega Evolved with its Stone stored in the wardrobe.
                stone_rule=obj.get('item_rule_id') if obj else None
                if not obj or obj.get('kind')!='item_instance':raise ValueError('stored Mega Stone physical identity changed')
            else:
                _,stone=equipped(c,row.get('stone_registration'))
                if stone.get('instance_id')!=row.get('stone_instance') or not stone.get('held_slot'):raise ValueError('active Mega Stone was removed or substituted')
                if not obj or obj.get('equipped_by')!=c.entity_id or obj.get('item_rule_id')!=stone.get('item_id'):raise ValueError('active Mega Stone physical holder changed')
                stone_rule=stone['item_id']
            binding=current['stone_bindings'].get(row['stone_instance'])
            if binding:
                if binding['form_id']!=row['definition'] or binding['definition_sha256']!=signature(form):raise ValueError('active Mega Stone belongs to another form')
            elif stone_rule not in form['stone_rules'] or form['origin']=='custom':raise ValueError('active Mega Stone has no actual matching form affinity')
        ring=getattr(engine,'_physical_objects',{}).get(row['ring_instance'])
        if not ring or (ring.get('item_rule_id')!=engine.r.mega_form_policy['ring_rule'] and
                not __import__('z_moves').mega_ring(engine.r,ring.get('item_rule_id'))):raise ValueError('actual activation Ring identity changed')
        ability=row.get('ability');known=row.get('known_at_activation')
        if not isinstance(known,list) or any(not isinstance(x,str) or x not in engine.r.selection.units for x in known) or len(set(known))!=len(known) or ability in known or row.get('types')!=form['types'] or type(row.get('duplicate_replacement'))is not bool:raise ValueError('Mega granted duplicate ability or wrong type')
        if row.get('duplicate_replacement'):
            alternatives=natural_alternatives(engine,c,known=known)
            if form['ability'] not in known or row.get('natural_alternatives')!=alternatives or ability not in alternatives:raise ValueError('Mega replacement lacks actual natural choice evidence')
        elif ability!=form['ability'] or form['ability'] in known:raise ValueError('Mega ability differs from definition')
        base=row.get('base_stats_at_activation');sheet=row.get('second_sheet');changes=row.get('stat_changes')
        if changes!=validate_stat_record(engine.r,form,base,sheet,row.get('allocation_context')):raise ValueError('Mega stat changes differ from its validated allocation')
        grant=owned[sid]
        if grant.get('rule_id')!=SOURCE or grant.get('producer_id')!=trainer.entity_id or grant.get('lifetime')!='scene' or grant.get('grants')!={'abilities':[AB.label(engine.r,ability)]}:raise ValueError('Mega shared ability contribution changed')
        st=c.spec[G.KEY]
        for stat in STATS:
            actual=st.get('stat_sources',{}).get(stat,{}).get('sources',{}).get(sid)
            expected={'0':{'delta':changes[stat],'minimum':None}} if stat in changes else None
            if actual!=expected:raise ValueError('Mega shared stat contribution changed')
        expected={'mode':'set','values':row['types'],'fallback':None} if row['types'] is not None else None
        if st.get('type_sources',{}).get('sources',{}).get(sid)!=expected:raise ValueError('Mega shared type contribution changed')
        scalar=st.get('scalar_sources',{}).get('form',{})
        if scalar.get('sources',{}).get(sid)!=row['definition'] or c.form!=scalar.get('visible') or c.form!=next(reversed(scalar['sources'].values())):raise ValueError('Mega visible form contribution changed')
        for stat,values in st.get('stat_sources',{}).items():
            if c.stats[stat]!=values['visible'] or c.stats[stat]!=G._stat_value(values,c.spec['stats'][stat]):raise ValueError('Mega current statistics disagree with shared source projection')
        types=st.get('type_sources')
        if types and (c._types!=types['visible'] or c._types!=G._type_value(types,c.spec.get('types',[]))):raise ValueError('Mega current types disagree with shared source projection')
        if c.abilities!=G.effective(c,'abilities'):raise ValueError('Mega current abilities disagree with shared source projection')
    if set(current['uses'])!=seen:raise ValueError('orphan Trainer Mega scene use')
    return True

