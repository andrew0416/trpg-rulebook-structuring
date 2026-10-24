"""Source-bound native policy bridge over the scoped partial-order kernel.

This is a finite, reviewed set of native policies, not a source-admission
certificate for the whole Engine. Callers first validate actual ownership,
consent and situation; arbitrary caller dictionaries cannot register policies.
No file-name ordering, text similarity or extraction confidence is precedence.
"""
from pathlib import Path
import json
import root_resolution as R

class PolicyPending(ValueError):
    def __init__(self, code, obligations=()):
        self.code=code
        self.obligations=tuple(obligations)
        super().__init__(code+(': '+str(self.obligations) if self.obligations else ''))

PRECEDENCE_SOURCE='ch06-gameplay/시스템-기본-사항'

SOURCE={
 'item-use':'ch09-equipment/모험-도구/약/아이템-사용',
 'medic':'edge/메딕-훈련', 'stunt':'edge/고난이도-스킬',
 'dowsing':'item/다우징-로드'}

def _fact(facts,name,expected=True):
    value=facts[name]
    if value is None:return R.Predicate(R.Truth.UNKNOWN,'missing_native_fact:'+name,((name,),))
    if type(value) is not bool:raise TypeError('explicit boolean or unknown required: '+name)
    return R.Predicate(R.Truth.TRUE if value is expected else R.Truth.FALSE,reads=((name,),))

def medicine_source_choices(rules,choice=None):
    """Prepare the bounded KR Swift / EN Shift recipient-debt choice."""
    document=json.loads((Path(rules.root)/'data/native-rule-policy.json').read_text(encoding='utf-8'))['medicine_source_choice']
    result=rules.resolve_source_policy(document,decisions={} if choice is None else {'source_text':choice})
    if result['status']=='PolicyValuesReady':
        definition=result['values']['definitions'][result['values']['variant']]
        if result['values']['variant']=='english_shift':
            from source_context import verified_source
            verified_source(rules,definition['source'],source_root='source-audit',label='English medicine')
    return result


def evaluate(rules,policy,facts,*,medicine_source_choice=None):
    """Pure policy preparation: reads source/profile and returns frozen decisions.

    Closed candidate sets are ONLY the named bounded native policy. An unknown
    fact/conflict cannot become a gameplay yes; consumers must not commit costs.
    """
    # The selected general law authorizes the scoped edges below; changing that
    # law cannot silently keep the old ordering even when leaf sources match.
    def selected(uid):
        from source_selection import SourceChangedError
        try:return rules._selected_rule(uid)
        except SourceChangedError as exc:raise PolicyPending('stale_policy_source',(uid,)) from exc
    if selected(PRECEDENCE_SOURCE)!=PRECEDENCE_SOURCE:
        raise PolicyPending('unreviewed_common_precedence_source',(PRECEDENCE_SOURCE,))
    precedence_rulings=getattr(rules,'rulings',None)
    if precedence_rulings is not None and (
            getattr(precedence_rulings,'mech',{}).get(PRECEDENCE_SOURCE) or
            getattr(precedence_rulings,'effects',{}).get(PRECEDENCE_SOURCE)):
        raise PolicyPending('unreviewed_common_precedence_override',(PRECEDENCE_SOURCE,))
    fields={'medicine':{'self_use','restorative','medic'},'skill_stunt':{'dowsing'}}
    if policy not in fields:raise PolicyPending('unregistered_native_policy')
    if medicine_source_choice is not None and policy!='medicine':raise ValueError('medicine source choice requires medicine policy')
    if not isinstance(facts,dict) or set(facts)!=fields[policy]:raise ValueError('exact native policy facts required')
    # Validate even facts whose short-circuit branch would be false.
    for name in fields[policy]:_fact(facts,name)
    if not hasattr(rules,'selection'):raise PolicyPending('missing_selected_rule_index')
    metadata=json.loads((Path(rules.root)/'data/native-rule-policy.json').read_text(encoding='utf-8'))
    if metadata.get('schema')!=1:raise PolicyPending('unsupported_native_policy_schema')
    medicine_variant='korean_swift';medicine_resolution=None
    if medicine_source_choice is not None:
        medicine_resolution=medicine_source_choices(rules,medicine_source_choice)
        if medicine_resolution['status']!='PolicyValuesReady':raise PolicyPending('explicit_medicine_source_choice_required')
        medicine_variant=medicine_resolution['values']['variant']
    def verify(anchor,source,values):
        ref=metadata['anchors'][anchor]
        if rules.selection.units[source]['source'].get('file')!=ref['file'].removeprefix('input/'):
            raise PolicyPending('policy_source_mismatch',(source,))
        declaration={'rule_id':source,'source':{key:ref[key] for key in ('file','sha256')},
                     'locator':ref.get('definition_locator',{'lines':ref['lines']}),
                     'evidence':ref,'values':values}
        try: binding=rules.bind_source_policy(source,declaration)
        except (ValueError,OSError) as exc:
            raise PolicyPending('stale_policy_source',(source,)) from exc
        return binding
    precedence=verify('precedence',PRECEDENCE_SOURCE,{'ordering':'specific_over_general'})
    clauses=[];edges=[];used={'precedence':precedence}
    def clause(uid,aspect,value,anchor,scope=R.TRUE):
        admitted=R.TRUE
        if scope.truth is not R.Truth.FALSE:
            source=SOURCE[anchor]
            if selected(source)!=source:raise PolicyPending('unreviewed_policy_source_variant',(source,))
            rulings=getattr(rules,'rulings',None)
            if rulings is not None and (getattr(rulings,'mech',{}).get(source) or getattr(rulings,'effects',{}).get(source)):
                raise PolicyPending('unreviewed_policy_gm_override',(source,))
            binding=verify(anchor,source,{'aspect':aspect,'value':value})
            used[uid]=binding
            aspect=binding['definition']['values']['aspect']
            value=binding['definition']['values']['value']
        clauses.append(R.Clause(uid,aspect,value,selected=admitted,scope=scope,source_refs=(SOURCE[anchor],)))
    def override(general,specific,aspect,anchor):
        edges.append(R.Override(general,specific,aspect,R.TRUE,SOURCE[anchor]))
    if policy=='medicine':
        clause('item.standard','action','standard','item-use')
        self_rest=R.conjunction(_fact(facts,'self_use'),_fact(facts,'restorative'))
        clause('restorative.self.full','action','full','item-use',self_rest)
        override('item.standard','restorative.self.full','action','item-use')
        definition=metadata['medicine_source_choice']['variants'][0]['values']['definitions'][medicine_variant]
        clause('item.recipient.debt','debt',definition['debt'],'item-use')
        clause('restorative.self.no_debt','debt',None,'item-use',self_rest)
        medic_other=R.conjunction(_fact(facts,'medic'),_fact(facts,'self_use',False))
        clause('medic.other.no_debt','debt',None,'medic',medic_other)
        override('item.recipient.debt','restorative.self.no_debt','debt','item-use')
        override('item.recipient.debt','medic.other.no_debt','debt','medic')
    else:
        clause('stunt.normal','pool',{'dice':-1,'modifier':6},'stunt')
        clause('stunt.dowsing','pool',{'dice':1,'modifier':0},'dowsing',_fact(facts,'dowsing'))
        override('stunt.normal','stunt.dowsing','pool','dowsing')
    aspects=tuple(sorted({c.aspect for c in clauses}))
    profile={'name':rules.ruleset.name,'profile':rules.ruleset.profile,
             'choices':rules.ruleset.variant_choices,'versions':rules.ruleset.unit_versions}
    request=R.ResolutionRequest('native-policy:'+policy,'native-policy',R.fingerprint(profile),
        R.fingerprint({'metadata':metadata,'sources':used,'medicine_source':medicine_resolution}),R.fingerprint(facts),tuple(clauses),tuple(edges),
        tuple(R.CompositionLaw(a,'exclusive','native-policy:'+policy+':'+a) for a in aspects),R.TRUE)
    answer=R.resolve(request)
    if answer.tag!='ModelReady':raise PolicyPending('unresolved_native_policy',R.plain(answer.obligations))
    return {'status':'ScopedPolicyReady','policy':policy,
            'values':{a.aspect:R.plain(a.value) for a in answer.aspects},
            'aspects':R.plain(answer.aspects),'source_refs':sorted({s for c in clauses for s in c.source_refs}),
            'model_receipt':R.plain(answer.receipt),'precedence_source':PRECEDENCE_SOURCE,
            'whole_engine_certified':False,
            **({'source_variant':medicine_variant,'source_policy':medicine_resolution} if policy=='medicine' else {})}
