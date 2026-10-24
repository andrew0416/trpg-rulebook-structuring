"""PTK source-specific skill identity and owned-edge bonuses.

Ruleset selection and actor ownership precede arithmetic. edge_choices holds
one category string for Categoric Inclination, and one pair per acquired Skill
Enhancement. Caller mods contains only other, already resolved modifiers.
This does not auto-interpret other conditional gear/feature effects.
"""
import arithmetic_policy as M
from collections import Counter
import re
import common_checks as checks
import composition_derive as COMPOSITION

# ch03:130: Survival is also Education; its Body category remains unchanged.
EDUCATION_SKILLS=frozenset(('general education','medical education','occult education',
                            'pokemon education','technology education','survival'))

def key(value):
    if not isinstance(value,str) or not value.strip():
        raise ValueError('nonempty skill/choice identity required')
    return re.sub(r'[\s_-]+','',value).casefold()

def skill_id(policy, name, *, required=False):
    normalized=key(name)
    for uid,record in policy['skills'].items():
        if normalized in {key(alias) for alias in record['aliases']}:
            return uid
    if required:raise ValueError('unknown PTK skill: '+str(name))
    return normalized  # Existing explicitly named custom skills remain supported.

def _declared_ranks(rules):
    ranks=rules.mech('gameplay/skill-rank-dice')['by_rank_name']
    if type(ranks) is not dict or not ranks:raise ValueError('nonempty declared skill rank table required')
    numbers=set();aliases={}
    def alias(value,name):
        if type(value) is not str or not value.strip():raise ValueError('nonempty declared skill rank name required')
        token=value.casefold()
        if token in aliases and aliases[token]!=name:raise ValueError('conflicting declared skill rank aliases')
        aliases[token]=name
    for name,data in ranks.items():
        if type(data) is not dict:raise ValueError('declared skill rank record required')
        number=checks.integer(data.get('rank'),'declared skill rank',1)
        if number in numbers:raise ValueError('conflicting declared numeric skill ranks')
        numbers.add(number)
        if type(data.get('dice')) is not str or not re.fullmatch(r'[1-9][0-9]*d6',data['dice']):
            raise ValueError('declared skill rank requires a positive d6 pool')
        alias(name,name)
        if 'eng' in data:alias(data['eng'],name)
    for value,name in rules.skill_policy['rank_aliases'].items():
        if name in ranks:alias(value,name)
    return ranks,aliases


def rank(rules, actor, skill):
    policy=rules.skill_policy
    target=skill_id(policy,skill)
    supplied=[v for k,v in actor.spec.get('skills',{}).items() if skill_id(policy,k)==target]
    ranks,aliases=_declared_ranks(rules)
    def normalize(value):
        if type(value) is int:
            matches=[name for name,data in ranks.items() if data['rank']==value]
            if len(matches)!=1:raise ValueError('unresolved ordinary numeric skill rank')
            return matches[0]
        if not isinstance(value,str):raise ValueError('unresolved skill rank')
        name=aliases.get(value.casefold())
        if name is None:raise ValueError('unresolved skill rank: '+value)
        return name
    import csv_item_form_contracts as CSV_FORMS
    projected=CSV_FORMS.skill_pool_projection(actor,target)
    if actor.kind=='pokemon' and (supplied or projected is not None):
        # Pokemon species pools retain their dice-rank and constant contract.
        pools=[]
        for value in supplied:
            match=re.fullmatch(r'\s*([1-9][0-9]*)d6\s*([+-]\s*[0-9]+)?\s*',value) if isinstance(value,str) else None
            if match:pools.append((int(match[1]),int((match[2] or '0').replace(' ',''))))
            else:
                name=normalize(value)
                pools.append((int(ranks[name]['dice'][:-2]),0))
        if len(set(pools))>1:raise ValueError('conflicting Pokemon skill pool aliases')
        dice_count,modifier=projected if projected is not None else pools[0]
        import baby_templates as BABY
        dice_count=max(1,dice_count-BABY.skill_rank_penalty(actor))
        return '포켓몬 스킬',str(dice_count)+'d6',dice_count
    names={normalize(v) for v in supplied} or {normalize('미숙')}
    if len(names)!=1:raise ValueError('conflicting skill aliases in actor sheet')
    name=names.pop()
    data=ranks[name]
    if actor.kind=='pokemon':
        import baby_templates as BABY
        dice_count=max(1,int(data['dice'][:-2])-BABY.skill_rank_penalty(actor))
        name=next((rank_name for rank_name,row in ranks.items() if row['dice']==str(dice_count)+'d6'),name)
        return name,str(dice_count)+'d6',dice_count
    return name,data['dice'],data['rank']

def edge_id(policy, name):
    if not isinstance(name,str):raise ValueError('edge ownership must use an ID or name')
    for uid,record in policy['edges'].items():
        if name==uid or key(name) in {key(x) for x in record['aliases']}:return uid
    return None

def validate_csv_source(rules, record, names):
    """Explicit CSV IDs retain their provenance while sharing an equal body policy."""
    source=record.get('equivalent_csv_source')
    if not source or source['id'] not in names:return
    from pathlib import Path
    from hashlib import sha256
    import csv
    cache=getattr(rules,'_skill_csv_sources',set())
    identity=(source['id'],source['sha256'])
    if identity not in cache:
        path=Path(rules.root)/source['file']
        if sha256(path.read_bytes()).hexdigest()!=source['sha256']:
            raise ValueError('skill CSV source changed; review required')
        with path.open(encoding='utf-8-sig',newline='') as handle:rows=list(csv.reader(handle))
        if rows[source['record']-1]!=source['cells']:
            raise ValueError('skill CSV definition differs from reviewed source')
        cache=set(cache);cache.add(identity);rules._skill_csv_sources=cache
    rules.ruleset.require({'id':source['id'],'source':{'file':source['file'].removeprefix('input/'),'record_span':[source['record'],source['record']]}})
    if source['id'] in rules.ruleset.unit_versions:
        raise ValueError('skill CSV version needs its own reviewed policy')


GLITCH_SOURCE='C2CSV/input/db/edges.csv:R75:main'
GLITCH_BODY_SOURCE='feat/버그의-존재'
GLITCH_OWNERSHIP_SOURCES = {
    key(name): source
    for source, alias in (
        (GLITCH_SOURCE, '버그화'),
        (GLITCH_BODY_SOURCE, '버그의 존재'),
    )
    for name in (source, alias)
}


def glitch_modifier(rules,actor,context):
    """The host classifies this concrete check as dealing with a Glitch phenomenon."""
    owned = actor.spec.get('edges', [])
    if not isinstance(owned, (list, tuple)):
        raise ValueError('edge ownership must be a list')
    acquisitions = [GLITCH_OWNERSHIP_SOURCES[key(name)]
                    for name in owned if key(name) in GLITCH_OWNERSHIP_SOURCES]
    if not acquisitions:
        return ()
    if len(acquisitions) != 1 or actor.kind != 'trainer':
        raise ValueError('Glitch Edge requires one actual trainer acquisition')
    source = acquisitions[0]
    if rules._selected_rule(source) != source:
        raise ValueError('selected Glitch Edge source required')
    if not isinstance(context, dict) or context.get('purpose') != 'glitch_phenomenon':
        return ()
    if set(context) != {'purpose', 'reason'} or type(context['reason']) is not str or not context['reason'].strip():
        raise ValueError('explicit GM Glitch check purpose and reason required')
    return ((source, 2, context['reason']),)


def modifiers(rules, actor, skill, additional, *, skill_context=None):
    checks.integer(additional,'modifier')
    policy=rules.skill_policy
    target=skill_id(policy,skill)
    owned=actor.spec.get('edges',[])
    if not isinstance(owned,(list,tuple)):raise ValueError('edge ownership must be a list')
    counts=Counter(edge_id(policy,n) for n in owned)
    choices=actor.spec.get('edge_choices',{})
    if not isinstance(choices,dict):raise ValueError('edge choices must be a mapping')
    chosen={}
    for name,value in choices.items():
        uid=edge_id(policy,name)
        if uid is None:continue # Other features are outside this adapter.
        if uid in chosen:raise ValueError('duplicate aliases for an edge choice')
        if not counts[uid]:raise ValueError('skill bonus choice requires acquired edge')
        chosen[uid]=value
    sources=[]
    if target=='stealth' and __import__('ability_transitions').active(actor,'ability/틈새포착'):
        sources.append(('ability/틈새포착',2,'active Infiltrator'))
    for uid,record in policy['edges'].items():
        count=counts[uid]
        if not count:continue
        validate_csv_source(rules,record,[*owned,*choices])
        if rules._selected_rule(uid)!=uid:
            raise ValueError('selected edge variant requires its own skill policy')
        if actor.kind!='trainer':
            raise ValueError('trainer edge cannot substitute for a Pokemon edge')
        if record['kind']=='fixed_skills':
            if count!=1:raise ValueError('repeated fixed skill edge needs a sourced ruling')
            prereq=record['prerequisite']
            if rank(rules,actor,prereq['skill'])[2]<prereq['minimum_rank']:
                raise ValueError('skill edge acquisition prerequisite is not established')
            if uid in chosen:raise ValueError('this skill edge has no selectable skill/category')
            detail=tuple(record['skills'])
            applies=target in detail
        elif record['kind']=='category':
            if uid not in chosen:raise ValueError('acquired skill edge needs explicit choices: '+uid)
            choice=chosen[uid]
            if count!=1:raise ValueError('repeated Categoric Inclination needs a sourced ruling')
            selected=[c for c,aliases in policy['categories'].items() if key(choice) in {key(x) for x in aliases}]
            if len(selected)!=1:raise ValueError('unknown skill category')
            canonical=skill_id(policy,skill,required=True)
            applies=policy['skills'][canonical]['category']==selected[0]
            detail=selected[0]
        else:
            if uid not in chosen:raise ValueError('acquired skill edge needs explicit choices: '+uid)
            choice=chosen[uid]
            if not isinstance(choice,(list,tuple)) or len(choice)!=count:
                raise ValueError('one skill pair per acquired Skill Enhancement required')
            selected=[]
            for pair in choice:
                if not isinstance(pair,(list,tuple)) or len(pair)!=2:
                    raise ValueError('Skill Enhancement needs two distinct skills')
                pair=tuple(skill_id(policy,s,required=True) for s in pair)
                if pair[0]==pair[1]:raise ValueError('Skill Enhancement needs two distinct skills')
                selected.extend(pair)
            detail=tuple(sorted(set(selected)))
            applies=target in detail
        if applies:sources.append((uid,record['value'],detail))
    # Source-owned fixed modifiers do not change rank(), effective_rank(),
    # species pools, or permanent Skill Improvement refund thresholds.
    import grant_payments as PAYMENTS
    PAYMENTS.validate(actor)
    for source_id,grant in actor.spec.get('state_grants',{}).get('sources',{}).items():
        entries=grant.get('grants',{}).get('skill_modifiers',[])
        if not entries:continue
        if type(entries) is not list:raise ValueError('skill modifier contributions must be records')
        uid=grant.get('rule_id')
        if type(uid) is not str or rules._selected_rule(uid)!=uid:
            raise ValueError('selected skill modifier source required')
        for entry in entries:
            if type(entry) is not dict or set(entry)!={'skill','delta'} or type(entry['delta']) is not int:
                raise ValueError('explicit skill and integer modifier required')
            canonical=skill_id(policy,entry['skill'],required=True)
            if canonical!=entry['skill']:raise ValueError('canonical skill modifier required')
            if canonical==target:sources.append((source_id,entry['delta'],canonical))
    import equipment_variant_contracts as EQUIPMENT_VARIANTS
    sources.extend(EQUIPMENT_VARIANTS.skill_modifiers(rules,actor,target,skill_context))
    sources.extend(glitch_modifier(rules,actor,skill_context))
    import capability_parameter_edges as PARAMETERS
    sources.extend(PARAMETERS.tracker_modifiers(rules,actor,target,skill_context))
    import body_modes as BODY_MODES
    shadow_bonus=BODY_MODES.stealth(actor,target)
    if shadow_bonus:sources.append((BODY_MODES.DEFINITIONS['shadow']['source'],shadow_bonus,'active Shadow Meld'))
    ace=__import__('type_ace').all_rolls(actor)
    if ace:sources.append(('type-ace/all-rolls',ace,'active Type Ace effect'))
    contributions=[{'id':'skill-modifier:'+str(i),'source':source,'value':value}
                   for i,(source,value,detail) in enumerate(sources)]
    composition=COMPOSITION.derive(additional,contributions,
        [{'law':'add','contributors':[row['id'] for row in contributions]}] if contributions else [])
    return {'modifier':composition['value'],'additional':additional,'sources':tuple(sources),
            'composition':composition}


def effective_rank(rules, actor, skill):
    """Rank-dependent capabilities use Virtuoso 8; ordinary dice still use rank()."""
    ordinary=rank(rules,actor,skill)[2]
    target=skill_id(rules.skill_policy,skill)
    for uid,policy in rules.skill_policy.get('rank_effects',{}).items():
        aliases={key(uid),*(key(x) for x in policy['aliases'])}
        owned=actor.spec.get('edges',[])
        if not isinstance(owned,(list,tuple)):raise ValueError('edge ownership must be a list')
        count=sum(key(e) in aliases for e in owned)
        selected=[v for k,v in actor.spec.get('edge_choices',{}).items() if key(k) in aliases]
        if not count and not selected:continue
        validate_csv_source(rules,policy,[*owned,*actor.spec.get('edge_choices',{})])
        if len(selected)!=1 or not count:raise ValueError('rank effect needs owned edge and explicit choices')
        if rules._selected_rule(uid)!=uid:raise ValueError('selected rank effect needs its own policy')
        if actor.kind!='trainer' or actor.level<policy['minimum_level']:
            raise ValueError('rank effect acquisition prerequisite is not established')
        choices=selected[0]
        if not isinstance(choices,(list,tuple)) or len(choices)!=count:
            raise ValueError('one skill per acquired rank effect required')
        skills=[skill_id(rules.skill_policy,x,required=True) for x in choices]
        if len(set(skills))!=len(skills):raise ValueError('rank effect must select different skills')
        for name in choices:
            if rank(rules,actor,name)[2]<policy['minimum_rank']:
                raise ValueError('rank effect requires an acquired Master skill')
        if target in skills:ordinary=policy['effective_rank']
    return ordinary

def procedural_edge(rules,actor,uid):
    """Validate the actual single acquisition before its specialized procedure."""
    record=rules.skill_policy['procedural_edges'][uid]
    aliases={key(x) for x in record['aliases']}
    owned=actor.spec.get('edges',[])
    if not isinstance(owned,(tuple,list)):raise ValueError('edge ownership must be a list')
    count=sum(x==uid or key(x) in aliases for x in owned)
    if not count:return None
    if count!=1 or actor.kind!='trainer':raise ValueError('single trainer edge acquisition required')
    if rules._selected_rule(uid)!=uid:raise ValueError('selected procedural edge needs its own policy')
    need=record['prerequisite']
    if rank(rules,actor,need['skill'])[2]<need['minimum_rank']:raise ValueError('procedural edge prerequisite is not established')
    return record

def assistance_bonus(rules,helper,skill,rank_value):
    record=procedural_edge(rules,helper,'edge/설명')
    if record and skill_id(rules.skill_policy,skill,required=True) in record['education_skills']:
        if rank_value<3:raise ValueError('Instruction needs at least Novice in the helping Education skill')
        return rank_value
    return M.ratio(rank_value,2)
