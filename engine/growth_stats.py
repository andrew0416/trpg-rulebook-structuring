"""Growth allocation plans retain points as they are actually invested."""

def sourced_base(base, sources=(), *, allow_negative=False):
    """Compose admitted species-base contributions before Nature and investment."""
    from builder import STATS
    from common_checks import integer
    import composition_derive as C
    if type(base) is not dict or set(base)!=set(STATS):raise ValueError('complete species baseline required')
    seen=set()
    for row in sources:
        if type(row) is not dict or set(row) not in ({'source','values'},{'source','values','signed'}) or type(row['source']) is not str or not row['source'] or row['source'] in seen:
            raise ValueError('distinct admitted base source required')
        if 'signed' in row and row['signed'] is not True:raise ValueError('signed base contribution must be explicitly enabled')
        if type(row['values']) is not dict or set(row['values'])!=set(STATS):raise ValueError('complete source base contribution required')
        for value in row['values'].values():integer(value,'source contribution',None if allow_negative or row.get('signed') else 0)
        seen.add(row['source'])
    result={}
    for stat in STATS:
        integer(base[stat],'species baseline',0)
        rows=[{'id':row['source'],'source':row['source'],'value':row['values'][stat]} for row in sources]
        result[stat]=C.derive(base[stat],rows,[{'law':'add','contributors':[r['id'] for r in rows]}] if rows else [])['value']
        if not allow_negative and any(row.get('signed') for row in sources) and result[stat] < 1:
            raise ValueError('signed sourced Base Stat must remain at least 1')
    return result


def allocate(base, points, strategy="balanced", nature=None, rules=None, *, excluded=(), relation_exempt=(), base_sources=(), point_budgets=(), investment=None, fixed_point_sources=()):
    from builder import STATS,STRATEGY,nature_base
    if type(points) is not int or points < 0:
        raise ValueError("stat points must be a nonnegative integer")
    adjusted = nature_base(sourced_base(base,base_sources), nature, rules)
    for stat in excluded:
        adjusted[stat] = base[stat]
    explicit=investment is not None
    investment=dict.fromkeys(STATS,0) if investment is None else dict(investment)
    if explicit:compose(base,investment,points=points,nature=nature,rules=rules,excluded=excluded,relation_exempt=relation_exempt,base_sources=base_sources,point_sources=fixed_point_sources)
    fixed=sourced_base(dict.fromkeys(STATS,0),fixed_point_sources,allow_negative=True)
    stats = {stat:adjusted[stat]+investment[stat]+fixed[stat] for stat in STATS}
    from common_checks import integer
    extras={};phases=[] if explicit else [(None,points)]
    for row in point_budgets:
        if type(row) is not dict or set(row)!={'source','points'} or type(row['source']) is not str or not row['source'] or row['source'] in extras:
            raise ValueError('distinct source-owned point budget required')
        integer(row['points'],'source-owned point budget')
        extras[row['source']]=dict.fromkeys(STATS,0);phases.append((row['source'],row['points']))
    weights = {st: max(1, adjusted[st]) * STRATEGY.get(strategy, {}).get(st, 1.0) for st in STATS}
    pairs = [(hi, lo) for hi in STATS for lo in STATS if adjusted[hi] > adjusted[lo] and hi not in relation_exempt and lo not in relation_exempt]
    for source,budget in phases:
        step=1 if budget>=0 else -1
        for _ in range(abs(budget)):
            candidates = [st for st in STATS if st not in excluded and
                          stats[st]+step>=adjusted[st] and
                          all(stats[hi] + step*int(st == hi) > stats[lo] + step*int(st == lo) for hi, lo in pairs)]
            if not candidates:
                raise ValueError("no legal stat allocation under the selected exceptions")
            chosen = (max if step>0 else min)(candidates, key=lambda st: weights[st] / (stats[st] - adjusted[st] + 1))
            stats[chosen] += step
            (investment if source is None else extras[source])[chosen] += step
    return compose(base,investment,points=points,nature=nature,rules=rules,
                   excluded=excluded,relation_exempt=relation_exempt,strategy=strategy,base_sources=base_sources,
                   point_sources=[{'source':source,'values':values} for source,values in extras.items()]+list(fixed_point_sources))


def compose(base, investment, *, points, nature=None, rules=None, excluded=(), relation_exempt=(), strategy=None, relation_bounds=(), base_sources=(), point_sources=()):
    """Compose explicitly supplied investment; never derive it from totals."""
    from builder import STATS,nature_base
    from common_checks import integer
    integer(points,'investment budget',0)
    if type(base) is not dict or set(base)!=set(STATS) or type(investment) is not dict or set(investment)!=set(STATS):
        raise ValueError('complete species baseline and explicit investment required')
    excluded=tuple(excluded);relation_exempt=tuple(relation_exempt)
    if set(excluded)-set(STATS) or set(relation_exempt)-set(STATS):raise ValueError('unknown allocation exception')
    for stat in STATS:
        integer(base[stat],'species baseline',0);integer(investment[stat],'investment',0)
        if stat in excluded and investment[stat]:raise ValueError('investment into excluded stat')
    if sum(investment.values())!=points:raise ValueError('explicit investment budget mismatch')
    effective_base=sourced_base(base,base_sources)
    adjusted=nature_base(effective_base,nature,rules)
    for stat in excluded:adjusted[stat]=base[stat]
    bonus=sourced_base(dict.fromkeys(STATS,0),point_sources,allow_negative=True)
    if any(investment[stat]+bonus[stat]<0 for stat in STATS):raise ValueError('source reduction exceeds actual invested points')
    if any(bonus[stat] for stat in excluded):raise ValueError('source investment into excluded stat')
    stats={stat:adjusted[stat]+investment[stat]+bonus[stat] for stat in STATS}
    from copy import deepcopy
    bounds={}
    for bound in relation_bounds:
        if type(bound) is not dict or set(bound)!={'higher','lower','minimum_gap','provider'}:
            raise ValueError('explicit historical relation bound required')
        hi,lo=bound['higher'],bound['lower']
        if hi not in STATS or lo not in STATS or adjusted[hi]<=adjusted[lo] or (hi,lo) in bounds:
            raise ValueError('distinct actual base relation required')
        integer(bound['minimum_gap'],'historical relation gap',maximum=0)
        if type(bound['provider']) is not dict or not bound['provider'].get('source'):
            raise ValueError('historical relation provider required')
        bounds[hi,lo]=bound['minimum_gap']
    for hi in STATS:
        for lo in STATS:
            if hi not in relation_exempt and lo not in relation_exempt and adjusted[hi]>adjusted[lo] and stats[hi]-stats[lo]<bounds.get((hi,lo),1):
                raise ValueError('explicit investment violates base relations')
    return {'species_base':dict(base),'nature_base':adjusted,
            'nature_delta':{stat:adjusted[stat]-effective_base[stat] for stat in STATS},
            'investment':dict(investment),'points':points,'stats':stats,
            'excluded':list(excluded),'relation_exempt':list(relation_exempt),'strategy':strategy,
            **({'relation_bounds':deepcopy(list(relation_bounds))} if relation_bounds else {}),
            **({'base_sources':deepcopy(list(base_sources))} if base_sources else {}),
            **({'point_sources':deepcopy(list(point_sources))} if point_sources else {})}


def retained_relation_bounds(rules,previous,nature,investment):
    """Preserve only attained source-backed gaps when retaining investment."""
    from builder import STATS,nature_base
    from copy import deepcopy
    if investment!=previous['investment']:return []
    providers={(b['higher'],b['lower']):b['provider'] for b in previous.get('relation_bounds',())}
    for event in previous.get('growth_events',()):
        provider=event.get('provider') or {}
        chosen={st for st in provider.get('stat_ace_branches',()) if event['investment_delta'][st]}
        for hi in STATS:
            for lo in STATS:
                if ((hi in chosen or lo in chosen) and previous['nature_base'][hi]>previous['nature_base'][lo]
                        and previous['stats'][hi]-previous.get('contributions',{}).get('vitamins',{}).get(hi,0)<=previous['stats'][lo]-previous.get('contributions',{}).get('vitamins',{}).get(lo,0)):providers[hi,lo]=provider
    adjusted=nature_base(sourced_base(previous['species_base'],previous.get('base_sources',())),nature,rules)
    bonus=sourced_base(dict.fromkeys(STATS,0),previous.get('point_sources',()),allow_negative=True)
    totals={st:adjusted[st]+investment[st]+bonus[st] for st in STATS}
    return [{'higher':hi,'lower':lo,'minimum_gap':totals[hi]-totals[lo],'provider':deepcopy(provider)}
        for (hi,lo),provider in providers.items() if adjusted[hi]>adjusted[lo] and totals[hi]<=totals[lo]]


def nature_plan(engine,actor,nature,*,investment=None):
    """Non-consuming proposal; source authorization/cost belongs to its caller."""
    from builder import species_lookup,STATS
    import pokemon_stat_edges as EDGES
    from actor_templates import has_soulless
    current=project_actor(engine,actor)
    if actor.spec.get('form_allocations'):
        return form_nature_plan(engine,actor,nature,investment=investment)
    chosen=current['permanent']['investment'] if investment is None else investment
    plan=compose(species_lookup(engine.r,actor.spec['species'])['base_stats'],chosen,
        points=sum(current['permanent']['investment'].values()),nature=nature,rules=engine.r,
        excluded=('hp',) if has_soulless(actor.spec) else (),relation_exempt=EDGES.exemptions(engine.r,actor.spec),relation_bounds=retained_relation_bounds(engine.r,current['permanent'],nature,chosen),base_sources=EDGES.base_sources(engine.r,actor.spec),point_sources=EDGES.point_sources(engine.r,actor.spec))
    vitamins=current['permanent']['contributions']['vitamins']
    baseline={stat:plan['stats'][stat]+vitamins[stat] for stat in STATS}
    import state_grants as G
    effective=G.prepare_stat_baseline(actor,baseline)
    return {'actor_id':actor.entity_id,'nature':nature,'allocation':plan,'vitamins':vitamins,
            'permanent_stats':baseline,'effective_stats':effective,'consumed':False}


def increment(rules, spec, points=1, strategy=None, choice=None, *, growth_context=None, _base_stats=None):
    from builder import STATS,STRATEGY,allocation_base
    if type(points) is not int or points < 0:
        raise ValueError("stat points must be a nonnegative integer")
    if choice is not None and choice not in STATS:
        raise ValueError(f"unknown stat choice: {choice}")
    base = allocation_base(rules, spec, base_stats=_base_stats)
    result = dict(spec["stats"])
    invested = dict.fromkeys(STATS,0)
    import pokemon_stat_edges as STAT_EDGES
    exempt = STAT_EDGES.exemptions(rules,spec)
    provider = STAT_EDGES.levelup_provider(rules,spec,growth_context)
    weights = {st: max(1, base[st]) * STRATEGY.get(strategy or spec.get("strategy", "balanced"), {}).get(st, 1.0) for st in STATS}
    for _ in range(points):
        def allowed(st):
            if provider is not None and ((st=='hp' and provider['source']=='class/불굴의-투지') or st in provider.get('stat_ace_branches',[])):return True
            trial = dict(result)
            trial[st] += 1
            return all(trial[lo] - trial[hi] <= max(-1, result[lo] - result[hi])
                for hi in STATS for lo in STATS if base[hi] > base[lo] and hi not in exempt and lo not in exempt)
        from actor_templates import has_soulless
        candidates = [st for st in STATS if allowed(st) and not (st == "hp" and has_soulless(spec))]
        if choice is not None and choice not in candidates:
            raise ValueError(f"stat choice {choice} violates base relations; allowed: {candidates}")
        chosen = choice or max(candidates, key=lambda st: weights[st] / max(1, result[st] - base[st] + 1))
        result[chosen] += 1
        invested[chosen] += 1
    return {'before':dict(spec['stats']),'stats':result,'investment_delta':invested,
            'points':points,'choice':choice,'provider':provider if provider and (invested['hp'] or any(invested[st] for st in provider.get('stat_ace_branches',[]))) else None,
            'relation_exempt':list(exempt),'base':base}



def project(rules,spec):
    """Reconstruct only directly observed investments, never inverse totals."""
    from copy import deepcopy
    from builder import STATS,allocation_base
    from common_checks import integer
    if 'form_growth_allocations' in spec:return form_projection(rules,spec)
    initial=spec.get('initial_allocation')
    offset=0
    migrations=spec.get('allocation_migrations',[])
    if migrations:
        migration=migrations[-1]
        if migration['species']!=spec['species']:raise ValueError('allocation migration species mismatch')
        initial=migration['plan']
        offset=integer(migration['growth_event_offset'],'growth event offset',0,len(spec.get('growth_investment_events',[])))
    if type(initial) is not dict:raise ValueError('explicit initial investment evidence required')
    import pokemon_stat_edges as EDGES
    if initial.get('base_sources',[])!=EDGES.base_sources(rules,spec):raise ValueError('changed base source requires explicit allocation migration')
    point_sources=EDGES.point_sources(rules,spec)
    if initial.get('point_sources',[])!=point_sources:raise ValueError('changed point source requires explicit allocation migration')
    investment=deepcopy(initial['investment'])
    for stat in STATS:integer(investment[stat],'initial investment',0)
    if sum(investment.values())!=initial['points']:raise ValueError('initial investment budget mismatch')
    vitamins={stat:integer(spec.get('vitamin_bonus',{}).get(stat,0),'vitamin contribution') for stat in STATS}
    base=allocation_base(rules,spec)
    nature_base={stat:base[stat]-vitamins[stat] for stat in STATS}
    if nature_base!=initial['nature_base']:raise ValueError('changed species/nature requires explicit allocation migration')
    events=spec.get('growth_investment_events',[])[offset:]
    for event in events:
        delta=event['investment_delta']
        for stat in STATS:integer(delta[stat],'growth investment',0)
        if sum(delta.values())!=event['points']:raise ValueError('growth investment budget mismatch')
        for stat in STATS:investment[stat]+=delta[stat]
    bonus=sourced_base(dict.fromkeys(STATS,0),point_sources,allow_negative=True)
    stats={stat:nature_base[stat]+investment[stat]+vitamins[stat]+bonus[stat] for stat in STATS}
    if stats!=spec['stats']:raise ValueError('untracked permanent stat changes require explicit reconciliation')
    return {'species_base':deepcopy(initial['species_base']),'nature_base':nature_base,
            'nature_delta':deepcopy(initial['nature_delta']),'investment':investment,
            'contributions':{'vitamins':vitamins,**({'bonus_points':bonus,'point_sources':deepcopy(point_sources)} if point_sources else {})},'stats':stats,'growth_events':deepcopy(events),'allocation_migrations':deepcopy(migrations),
            **{key:deepcopy(initial[key]) for key in ('relation_bounds','base_sources','point_sources') if key in initial}}


def project_actor(engine,actor):
    """Permanent investment, ordered source operations and stages stay separate."""
    from copy import deepcopy
    import world_entities as W,state_grants as G
    W.require_actors(engine,actor)
    if getattr(actor,'_nonadditive_stats',None):raise ValueError('stat exchange requires its explicit projection policy')
    permanent=project(engine.r,actor.spec)
    state=actor.spec.get(G.KEY,{})
    if any(key.startswith('stats.') for key in state.get('numbers',{})):
        raise ValueError('legacy observed stat contribution requires explicit raw-source import')
    rows=state.get('stat_sources',{});sources=state.get('sources',{})
    effective=dict(permanent['stats']);trace={}
    for field,row in rows.items():
        if row['base_offset']!=0:raise ValueError('unattributed stat offset requires explicit source import')
        value=effective[field];operations=[]
        for source_id,entries in row['sources'].items():
            source=sources.get(source_id)
            if not source or not source.get('rule_id'):raise ValueError('actual stat source evidence required')
            engine.r._selected_rule(source['rule_id'])
            for operation_id,operation in entries.items():
                before=value;value+=operation['delta']
                if operation['minimum'] is not None:value=max(operation['minimum'],value)
                operations.append({'source_id':source_id,'rule_id':source['rule_id'],'operation_id':operation_id,
                    'operation':deepcopy(operation),'before':before,'after':value})
        if value!=row['visible']:raise ValueError('stat source projection differs from recorded visible result')
        effective[field]=value;trace[field]=operations
    if effective!=actor.stats:raise ValueError('untracked effective stat change requires explicit reconciliation')
    return {'permanent':permanent,'source_operations':trace,'effective_stats':effective,
            'combat_stages':deepcopy(actor.stages),'consumed':False}


def commit_nature(engine,actor,target,nature,*,investment,source,reason,ap_cost,hp_policy,request_id):
    """Application-authorized change; explicit payment and HP policy are required.

    Source selection is provenance, not certification of a named feature's
    acquisition or permission. Feature adapters must perform that admission.
    """
    from copy import deepcopy
    import world_entities as W,state_grants as G,resolution_transaction as TX
    import action_points as AP,arithmetic_policy as M,bandages as BANDAGES
    from common_checks import integer
    W.require_actors(engine,actor,target);engine.r._selected_rule(source)
    if type(reason) is not str or not reason.strip():raise ValueError('explicit nature change reason required')
    integer(ap_cost,'declared nature change AP cost',0)
    if hp_policy not in ('preserve_fraction','preserve_damage'):raise ValueError('explicit supported HP policy required')
    intent={'actor_id':actor.entity_id,'target_id':target.entity_id,'nature':nature,'investment':investment,
            'source':source,'reason':reason,'ap_cost':ap_cost,'hp_policy':hp_policy}
    records=target.spec.get('nature_change_receipts',{})
    prior=TX.replay_result(records,request_id,intent,fingerprint_field='intent')
    if prior is not None:return dict(prior['result'],replayed=True)
    signature=TX.request_fingerprint(intent)
    def apply(e,payer,changed):
        if changed.kind!='pokemon':raise ValueError('actual Pokemon nature target required')
        proposal=nature_plan(e,changed,nature,investment=investment)
        old_nature=changed.spec.get('nature');old_stats=deepcopy(changed.spec['stats'])
        old_hp=changed.hp;old_max=max(1,changed.base_max_hp)
        AP.charge(payer,ap_cost,mode='spend')
        if 'form_plans' in proposal:
            old_forms=deepcopy(changed.spec['form_growth_allocations'])
            changed.spec.setdefault('form_growth_history',[]).append({'kind':'nature','previous':old_forms,'nature':nature,'source':source,'reason':reason})
            changed.spec['form_growth_allocations']['plans']=deepcopy(proposal['form_plans'])
            changed.spec['form_growth_allocations']['nature']=nature
            changed.spec['form_allocations']['forms']=deepcopy(proposal['form_stats'])
        changed.spec['nature']=nature;changed.spec['stats']=deepcopy(proposal['permanent_stats'])
        changed.stats=deepcopy(proposal['effective_stats']);G.commit_stat_baseline(changed)
        changed.spec.setdefault('allocation_migrations',[]).append({'kind':'nature','species':changed.spec['species'],
            'level':changed.level,'previous_nature':old_nature,'nature':nature,'previous_stats':old_stats,
            'source':source,'reason':reason,'plan':deepcopy(proposal['allocation']),
            'growth_event_offset':len(changed.spec.get('growth_investment_events',[]))})
        maximum=changed.base_max_hp
        proposed=M.ratio(old_hp*maximum,old_max) if hp_policy=='preserve_fraction' else (0 if old_hp<=0 else max(0,min(maximum,old_hp+maximum-old_max)))
        import keep_fighting as KEEP
        changed.hp=KEEP.replace_hp(e,changed,old_hp,proposed,source=source,loss_kind='nature_change',amount=max(0,old_hp-proposed))
        BANDAGES.on_hp_change(e,changed,old_hp,changed.hp)
        changed._state_revision=getattr(changed,'_state_revision',0)+1
        import mixed_sweeper as MIXED
        MIXED.reconcile(e,changed,reason='actual permanent nature and investment change')
        result={'status':'NatureChanged','actor_id':payer.entity_id,'target_id':changed.entity_id,
                'previous_nature':old_nature,'nature':nature,'source':source,'ap_paid':ap_cost,
                'hp_policy':hp_policy,'projection':project_actor(e,changed)}
        changed.spec.setdefault('nature_change_receipts',{})[request_id]={'intent':signature,'result':deepcopy(result)}
        return dict(result,replayed=False)
    import keep_fighting as KEEP
    interested=KEEP.interested(engine,target)
    return G.transition(engine,actor,apply,participants=(target,),include_rulings=interested,include_grid=interested and engine.grid is not None)


def configure_forms(engine,actor,declarations,*,active,source):
    """Bind explicitly authored per-form bases and investments to native forms."""
    from copy import deepcopy
    from builder import STATS
    import state_grants as G,form_allocations as FORMS,pokemon_stat_edges as EDGES
    from actor_templates import has_soulless
    current=project_actor(engine,actor)['permanent']
    if type(declarations) is not dict or not declarations or active not in declarations:raise ValueError('named explicit form investments required')
    budget=sum(current['investment'].values());vitamins=current['contributions']['vitamins']
    plans={};forms={}
    for name,declaration in declarations.items():
        if type(declaration) is not dict or set(declaration)!={'species_base','investment'}:raise ValueError('explicit form base and investment required')
        plan=compose(declaration['species_base'],declaration['investment'],points=budget,nature=actor.spec.get('nature'),rules=engine.r,
            excluded=('hp',) if has_soulless(actor.spec) else (),relation_exempt=EDGES.exemptions(engine.r,actor.spec),base_sources=EDGES.base_sources(engine.r,actor.spec),point_sources=EDGES.point_sources(engine.r,actor.spec,form=name))
        plans[name]=plan;forms[name]={stat:plan['stats'][stat]+vitamins[stat] for stat in STATS}
    record={'plans':plans,'level':actor.level,'nature':actor.spec.get('nature'),'source':source,'budget':budget}
    if 'form_growth_allocations' in actor.spec and actor.spec['form_growth_allocations']!=record:
        raise ValueError('recorded form investments require explicit migration')
    def apply(e,c):
        FORMS._configure_staged(e,c,forms,active=active,source=source)
        c.spec['form_growth_allocations']=deepcopy(record)
        form_projection(e.r,c.spec)
        return deepcopy(record)
    return G.transition(engine,actor,apply)


def evolution_forms(rules,spec,declarations,*,points,point_budgets=()):
    """Prepare a complete explicit form migration before native evolution commits."""
    from copy import deepcopy
    from builder import STATS
    import pokemon_stat_edges as EDGES
    from actor_templates import has_soulless
    current=form_projection(rules,spec)
    old=spec['form_growth_allocations']
    if type(declarations) is not dict or set(declarations)!=set(old['plans']):
        raise ValueError('explicit evolution investment for every existing form required')
    plans={};forms={}
    for name,row in declarations.items():
        if type(row) is not dict or set(row)!={'species_base','investment'}:
            raise ValueError('explicit evolved form base and investment required')
        import mixed_sweeper as MIXED
        plan=allocate(row['species_base'],points,investment=row['investment'],point_budgets=point_budgets,fixed_point_sources=MIXED.point_sources(rules,spec,form=name),
            nature=spec.get('nature'),rules=rules,excluded=('hp',) if has_soulless(spec) else (),
            relation_exempt=EDGES.exemptions(rules,spec),strategy=spec.get('strategy','balanced'),base_sources=EDGES.base_sources(rules,spec))
        plans[name]=plan
        forms[name]={stat:plan['stats'][stat]+current['contributions']['vitamins'][stat] for stat in STATS}
    import form_allocations as FORMS
    FORMS.validate_hp(dict(spec['form_allocations'],forms=forms))
    record=dict(deepcopy(old),plans=plans,budget=points)
    return {'record':record,'forms':forms,'active':spec['form_allocations']['active']}


def form_projection(rules,spec):
    from copy import deepcopy
    from builder import STATS
    from common_checks import integer
    import pokemon_stat_edges as EDGES
    record=spec['form_growth_allocations'];forms=spec.get('form_allocations',{})
    if record['level']!=spec['level'] or record['nature']!=spec.get('nature'):raise ValueError('all-form growth/nature migration required')
    if record['source']!=forms.get('source'):raise ValueError('form growth source mismatch')
    rules._selected_rule(record['source'])
    if set(record['plans'])!=set(forms.get('forms',{})):raise ValueError('complete form investment records required')
    vitamins={stat:integer(spec.get('vitamin_bonus',{}).get(stat,0),'vitamin contribution') for stat in STATS}
    projections={}
    for name,plan in record['plans'].items():
        checked=compose(plan['species_base'],plan['investment'],points=record['budget'],nature=record['nature'],rules=rules,
            excluded=plan['excluded'],relation_exempt=plan['relation_exempt'],strategy=plan['strategy'],relation_bounds=plan.get('relation_bounds',()),base_sources=EDGES.base_sources(rules,spec),point_sources=EDGES.point_sources(rules,spec,form=name))
        if checked!=plan:raise ValueError('form allocation evidence mismatch')
        stats={stat:plan['stats'][stat]+vitamins[stat] for stat in STATS}
        if stats!=forms['forms'][name]:raise ValueError('untracked form baseline contribution change')
        bonus=sourced_base(dict.fromkeys(STATS,0),plan.get('point_sources',()),allow_negative=True)
        projections[name]=dict(deepcopy(plan),stats=stats,contributions={'vitamins':deepcopy(vitamins),**({'bonus_points':bonus,'point_sources':deepcopy(plan['point_sources'])} if plan.get('point_sources') else {})},growth_events=[],allocation_migrations=[])
    active=forms['active']
    if spec['stats']!=projections[active]['stats']:raise ValueError('active form investment projection mismatch')
    return dict(projections[active],form=active,form_source=record['source'])


def form_nature_plan(engine,actor,nature,*,investment=None):
    from copy import deepcopy
    from builder import STATS
    import state_grants as G,form_allocations as F,pokemon_stat_edges as E
    from actor_templates import has_soulless
    current=form_projection(engine.r,actor.spec)
    record=actor.spec['form_growth_allocations'];names=set(record['plans'])
    if investment is not None and (type(investment) is not dict or set(investment)!=names):
        raise ValueError('explicit investment for every configured form required')
    plans={};forms={};vitamins=current['contributions']['vitamins']
    for name,old in record['plans'].items():
        chosen=old['investment'] if investment is None else investment[name]
        plan=compose(old['species_base'],chosen,points=record['budget'],nature=nature,rules=engine.r,
        excluded=('hp',) if has_soulless(actor.spec) else (),relation_exempt=E.exemptions(engine.r,actor.spec),relation_bounds=retained_relation_bounds(engine.r,old,nature,chosen),base_sources=E.base_sources(engine.r,actor.spec),point_sources=E.point_sources(engine.r,actor.spec,form=name))
        plans[name]=plan;forms[name]={stat:plan['stats'][stat]+vitamins[stat] for stat in STATS}
    proposed=deepcopy(actor.spec[F.KEY]);proposed['forms']=forms;F.validate(actor,proposed)
    for stats in forms.values():G.prepare_stat_baseline(actor,stats)
    active=proposed['active'];baseline=forms[active]
    return {'actor_id':actor.entity_id,'nature':nature,'allocation':plans[active],'vitamins':vitamins,
            'permanent_stats':baseline,'effective_stats':G.prepare_stat_baseline(actor,baseline),
            'form_plans':plans,'form_stats':forms,'consumed':False}


def increment_forms(rules,spec,points=1,strategy=None,choice=None,*,growth_context=None):
    """Add fresh points to every declared form before committing any of them."""
    from copy import deepcopy
    from builder import STATS
    current=form_projection(rules,spec)
    record=spec['form_growth_allocations'];plans={};forms={};increments={}
    vitamins=current['contributions']['vitamins']
    for name,old in record['plans'].items():
        candidate=deepcopy(spec);candidate['stats']=deepcopy(spec['form_allocations']['forms'][name])
        added=increment(rules,candidate,points,strategy,choice,growth_context=growth_context,_base_stats=old['species_base'])
        investment={stat:old['investment'][stat]+added['investment_delta'][stat] for stat in STATS}
        # Keep only the attained gap, never a blanket future relation waiver.
        bounds={(b['higher'],b['lower']):deepcopy(b) for b in old.get('relation_bounds',[])}
        if added['provider'] is not None:
            for hi in STATS:
                for lo in STATS:
                    gap=added['stats'][hi]-vitamins[hi]-added['stats'][lo]+vitamins[lo]
                    if old['nature_base'][hi]>old['nature_base'][lo] and gap<1:
                        if gap<bounds.get((hi,lo),{}).get('minimum_gap',1):
                            bounds[hi,lo]={'higher':hi,'lower':lo,'minimum_gap':gap,'provider':deepcopy(added['provider'])}
        plan=compose(old['species_base'],investment,points=record['budget']+points,
            nature=spec.get('nature'),rules=rules,excluded=old['excluded'],
            relation_exempt=added['relation_exempt'],strategy=strategy or old['strategy'],relation_bounds=list(bounds.values()),base_sources=old.get('base_sources',()),point_sources=old.get('point_sources',()))
        baseline={stat:plan['stats'][stat]+vitamins[stat] for stat in STATS}
        if baseline!=added['stats']:raise ValueError('form increment projection mismatch')
        plans[name]=plan;forms[name]=baseline;increments[name]=added
    import form_allocations as FORMS
    FORMS.validate_hp(dict(spec['form_allocations'],forms=forms))
    active=spec['form_allocations']['active']
    return dict(increments[active],form_plans=plans,form_stats=forms,form_increments=increments)


def apply_vitamin(actor,stat,*,source,delta=1):
    """Apply an admitted Vitamin or suppressant inside its consumption transaction."""
    from copy import deepcopy
    import state_fields as F,state_grants as G,form_allocations as FORMS
    from builder import STATS
    if stat not in STATS:raise ValueError('known Vitamin stat required')
    if type(delta) is not int or delta not in (-1,1):raise ValueError('one sourced permanent stat point required')
    from common_checks import integer
    bonuses=actor.spec.get('vitamin_bonus',{})
    if not isinstance(bonuses,dict) or set(bonuses)-set(STATS):raise ValueError('actual permanent Vitamin stat contributions required')
    for value in bonuses.values():integer(value,'permanent Vitamin stat contribution')
    forms=None
    if 'form_growth_allocations' in actor.spec:
        form_projection(actor.r,actor.spec)
        forms=deepcopy(actor.spec[FORMS.KEY])
        for baseline in forms['forms'].values():
            baseline[stat]+=delta
            G.prepare_stat_baseline(actor,baseline)
        FORMS.validate(actor,forms)
    baseline=dict(actor.spec['stats']);baseline[stat]+=delta
    F.base_patch(actor,{'stats':baseline},reason='consumed vitamin '+source,source=source)
    bonuses=actor.spec.setdefault('vitamin_bonus',{})
    bonuses[stat]=bonuses.get(stat,0)+delta
    if forms is not None:
        actor.spec[FORMS.KEY]=forms
        form_projection(actor.r,actor.spec)


def import_investment(engine,actor,investment,*,source,reason,request_id):
    """Bind declared current investment to an untracked legacy actor, without inventing past events."""
    from copy import deepcopy
    from builder import STATS,species_lookup,calc
    from actor_templates import has_soulless
    from common_checks import integer
    import world_entities as W,state_grants as G,resolution_transaction as TX
    import pokemon_stat_edges as E,arithmetic_policy as M
    W.require_actors(engine,actor);engine.r._selected_rule(source)
    if type(reason) is not str or not reason.strip():raise ValueError('explicit investment import reason required')
    intent={'actor_id':actor.entity_id,'investment':investment,'source':source,'reason':reason}
    prior=TX.replay_result(actor.spec.get('growth_import_receipts',{}),request_id,intent,fingerprint_field='intent')
    if prior is not None:return dict(prior['result'],replayed=True)
    signature=TX.request_fingerprint(intent)
    def apply(e,c):
        if c.kind!='pokemon':raise ValueError('Pokemon investment import required')
        if any(c.spec.get(key) for key in ('initial_allocation','allocation_migrations','form_allocations','form_growth_allocations')):
            raise ValueError('existing allocation evidence requires its explicit migration path')
        budget=M.floor(calc(e.r.mech('pokemon/stat-build')['stat_points'],{'level':c.level}))
        plan=compose(species_lookup(e.r,c.spec['species'])['base_stats'],investment,
            points=budget,nature=c.spec.get('nature'),rules=e.r,
            excluded=('hp',) if has_soulless(c.spec) else (),relation_exempt=E.exemptions(e.r,c.spec),base_sources=E.base_sources(e.r,c.spec),point_sources=E.point_sources(e.r,c.spec))
        vitamins={stat:integer(c.spec.get('vitamin_bonus',{}).get(stat,0),'vitamin contribution') for stat in STATS}
        if {stat:plan['stats'][stat]+vitamins[stat] for stat in STATS}!=c.spec['stats']:
            raise ValueError('declared investment does not match actual permanent statistics')
        c.spec.setdefault('allocation_migrations',[]).append({'kind':'explicit_import',
            'species':c.spec['species'],'level':c.level,'source':source,'reason':reason,
            'plan':deepcopy(plan),'growth_event_offset':len(c.spec.get('growth_investment_events',[]))})
        projection=project_actor(e,c)
        c._state_revision=getattr(c,'_state_revision',0)+1
        result={'status':'InvestmentImported','actor_id':c.entity_id,'source':source,'projection':projection}
        c.spec.setdefault('growth_import_receipts',{})[request_id]={'intent':signature,'result':deepcopy(result)}
        return dict(result,replayed=False)
    return G.transition(engine,actor,apply)


def source_permanent(actor):
    from copy import deepcopy
    candidate=actor.spec
    if 'form_growth_allocations' in candidate and candidate['form_growth_allocations']['level']!=actor.level:
        candidate=deepcopy(candidate);candidate['level']=candidate['form_growth_allocations']['level']
    return project(actor.r,candidate)


def source_plans(rules,spec,current):
    from copy import deepcopy
    import state_fields as F,pokemon_stat_edges as E
    from actor_templates import has_soulless
    old=spec.get('form_growth_allocations',{}).get('plans')
    if old is None:old={'base':current}
    output={};vitamins=current['contributions']['vitamins']
    for name,previous in old.items():
        plan=compose(previous['species_base'],previous['investment'],points=sum(previous['investment'].values()),
            nature=spec.get('nature'),rules=rules,excluded=('hp',) if has_soulless(spec) else (),
            relation_exempt=E.exemptions(rules,spec),strategy=previous.get('strategy',spec.get('strategy','balanced')),
            relation_bounds=previous.get('relation_bounds',()),base_sources=E.base_sources(rules,spec),point_sources=E.point_sources(rules,spec,form=name))
        output[name]={'plan':plan,'stats':{stat:plan['stats'][stat]+vitamins[stat] for stat in F.STATS}}
    if len({r['stats']['hp'] for r in output.values()})!=1:raise ValueError('Source point allocations require shared HP base')
    return output


def migrate_sources(actor,current,*,source,reason,kind):
    from copy import deepcopy
    import state_fields as F
    prepared=source_plans(actor.r,actor.spec,current)
    if 'form_growth_allocations' in actor.spec:
        record=actor.spec['form_growth_allocations']
        actor.spec.setdefault('form_growth_history',[]).append({'kind':kind,'previous':deepcopy(record),'source':source,'reason':reason})
        record['plans']={name:r['plan'] for name,r in prepared.items()};record['level']=actor.level
        actor.spec['form_allocations']['forms']={name:r['stats'] for name,r in prepared.items()};active=actor.spec['form_allocations']['active']
    else:active='base'
    chosen=prepared[active]
    actor.spec.setdefault('allocation_migrations',[]).append({'kind':kind,'species':actor.spec['species'],'level':actor.level,
        'source':source,'reason':reason,'plan':deepcopy(chosen['plan']),'growth_event_offset':len(actor.spec.get('growth_investment_events',[]))})
    F.base_patch(actor,{'stats':chosen['stats']},source=source,reason=reason);actor.hp=min(actor.hp,actor.base_max_hp)


