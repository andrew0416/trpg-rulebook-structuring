"""Source-bound JSON policy values for native consumers and external rule authors.

Declarations prepare values and execute through native effect/action/grant,
growth and teaching adapters.
Neither preparation nor execution certifies the interpretation of source prose.
The application supplies authored declarations and explicit GM decisions; source
hashes establish freshness, not that an author interpreted prose correctly.
"""
from pathlib import Path
from copy import deepcopy
import json
from source_context import verified_source
import root_resolution as R
from ruleset import ExcludedRuleSelection


def _text(value):
    if type(value) is not str or not value.strip():
        raise ValueError('nonempty identity required')
    return value


def _matches(value, spec):
    expected = {'integer': int, 'boolean': bool, 'string': str}[spec['type']]
    return (type(value) is expected
            and ('choices' not in spec or value in spec['choices'])
            and ('minimum' not in spec or value >= spec['minimum'])
            and ('maximum' not in spec or value <= spec['maximum']))


def _variant(row):
    required = {'rule_id', 'source', 'values', 'inputs'}
    if type(row) is not dict or not required <= set(row) or set(row) - (required | {'version','when'}):
        raise ValueError('exact policy variant fields required')
    _text(row['rule_id'])
    if 'version' in row: _text(row['version'])
    src = row['source']
    if type(src) is not dict or set(src) != {'file', 'sha256'}:
        raise ValueError('source file and sha256 required')
    _text(src['file']); _text(src['sha256'])
    if type(row['values']) is not dict or type(row['inputs']) is not dict:
        raise ValueError('values and inputs must be objects')
    for key, spec in row['inputs'].items():
        _text(key)
        if type(spec) is not dict or not {'type', 'authority', 'question'} <= set(spec):
            raise ValueError('typed input authority and question required')
        if set(spec) - {'type', 'authority', 'question', 'choices', 'binding', 'decision_kind', 'definition_kind', 'minimum', 'maximum'}:
            raise ValueError('unsupported input declaration')
        if spec['type'] not in ('integer', 'boolean', 'string'):
            raise ValueError('unsupported input type')
        for bound in ('minimum', 'maximum'):
            if bound in spec and (spec['type'] != 'integer' or type(spec[bound]) is not int):
                raise ValueError('input bounds require exact integers on an integer input')
        if 'minimum' in spec and 'maximum' in spec and spec['minimum'] > spec['maximum']:
            raise ValueError('input minimum exceeds maximum')
        if 'definition_kind' in spec:
            if spec['type']!='string' or spec['definition_kind'] not in ('edge','feat','class','gift','poke_edge','move','ability','item'):
                raise ValueError('definition input requires a string and supported catalog kind')
        if spec['authority'] not in ('context', 'gm', 'state'):
            raise ValueError('unsupported input authority')
        _text(spec['question'])
        if 'decision_kind' in spec:
            if spec['authority']!='gm' or spec['decision_kind'] not in ('delegated_choice','source_conflict'):
                raise ValueError('decision kind belongs to an explicit GM adjudication')
        if spec.get('decision_kind')=='source_conflict':
            choices=spec.get('choices')
            if type(choices) is not list or len(choices)<2 or len({R.fingerprint(v) for v in choices})!=len(choices):
                raise ValueError('source conflict requires distinct explicit alternatives')
        if spec['authority']=='state':
            import source_policy_state as STATE
            STATE.validate(spec)
        elif 'binding' in spec:
            raise ValueError('only native state inputs may declare a binding')
        if 'choices' in spec:
            if type(spec['choices']) is not list or not spec['choices']:
                raise ValueError('nonempty choices required')
            if any(not _matches(v, spec) for v in spec['choices']):
                raise ValueError('choice type mismatch')
    def check(value):
        if type(value) is dict:
            if '$input' in value:
                if set(value) != {'$input'} or type(value['$input']) is not str or value['$input'] not in row['inputs']:
                    raise ValueError('unknown or malformed input reference')
            else:
                for child in value.values(): check(child)
        elif type(value) is list:
            for child in value: check(child)
    R.freeze(row)  # No floats, objects or executable callbacks in declarations.
    check(row['values'])
    import source_policy_predicates as P
    if 'when' in row: P.validate(row['when'],row['inputs'])
    if 'operations' in row['values']:
        import foundation_operations as OPERATIONS
        OPERATIONS.validate(row['values'],row['inputs'])


def resolve(rules, document, *, context=None, decisions=None, _state_reader=None):
    """Return selected values or explicit obligations without consuming any state.

    String inputs may declare definition_kind to require an exact, current
    catalog definition of that kind. choices constrains the provider domain;
    a replacement is never silently admitted. This proves source eligibility,
    not acquisition prerequisites or entitlement. Execution adapters recheck
    these inputs before their normal native payment/commit and replay paths.

    Integer inputs may declare inclusive minimum/maximum bounds; missing values
    remain obligations and are never replaced by a bound or default.

    Decisions are supplied by the application/GM, never inferred from a question
    substring. A source override is a separate declaration, not silent merging.

    GM inputs may declare decision_kind=delegated_choice or source_conflict.
    A source_conflict requires at least two distinct typed choices. Its host
    decision supplies value, reason and the decision_scope returned by a pending
    resolution. This scope binds the whole definition, selected version and
    effective profile; a changed interpretation requires a new explicit review.
    A scope match establishes applicability, not correctness of source prose or
    external authorization. Unclassified legacy GM inputs keep their contract.
    """
    document = R.plain(R.freeze(document))
    if type(document) is not dict or set(document) != {'schema', 'id', 'variants'}:
        raise ValueError('exact policy document fields required')
    if type(document['schema']) is not int or document['schema'] != 1:
        raise ValueError('unsupported policy schema')
    _text(document['id'])
    if type(document['variants']) is not list or not document['variants']:
        raise ValueError('nonempty variants required')
    seen = set()
    for row in document['variants']:
        _variant(row)
        identity = (row['rule_id'], row.get('version'))
        if identity in seen: raise ValueError('duplicate policy variant')
        seen.add(identity)
    winners = {}
    for row in document['variants']:
        try:
            selected = rules._selected_rule(row['rule_id'], supports_versions=True)
        except ExcludedRuleSelection:
            continue
        selected_version = rules.ruleset.unit_versions.get(selected)
        selected_identity = (selected, selected_version)
        if selected_identity not in seen:
            raise ValueError('selected replacement lacks authored policy or version')
        if selected_identity == (row['rule_id'], row.get('version')):
            winners[selected] = row
    if len(winners) != 1:
        raise ValueError('policy requires exactly one selected source variant')
    selected, row = next(iter(winners.items()))
    binding=rules.bind_source_policy(selected,row,supports_versions=True)
    row=binding['definition']
    registered = getattr(rules,'_authored_policy_sources',{}).get(selected)
    rulings = rules.rulings
    if rulings.mech.get(selected) or rulings.effects.get(selected):
        raise ValueError('selected rule override requires its own authored policy')
    context = {} if context is None else deepcopy(context)
    decisions = {} if decisions is None else deepcopy(decisions)
    if type(context) is not dict or type(decisions) is not dict:
        raise ValueError('explicit context and decisions objects required')
    profile = {'name':rules.ruleset.name, 'profile':rules.ruleset.profile,
               'choices':rules.ruleset.variant_choices, 'versions':rules.ruleset.unit_versions,
               'admission':{'sources':sorted(rules.ruleset.sources),'variants':sorted(rules.ruleset.variants),
                            'exclude_units':sorted(rules.ruleset.exclude_units),'exclude_tags':sorted(rules.ruleset.exclude_tags),
                            'replaces':rules.ruleset.replaces,'rulings_files':rules.ruleset.rulings_files}}
    profile_hash=R.fingerprint(profile);definition_hash=R.fingerprint(document)
    decision_scope={'policy_id':document['id'],'selected_id':selected,
                    'selected_version':row.get('version'),'definition_hash':definition_hash,
                    'profile_hash':profile_hash}
    specs = row['inputs']
    if set(context) - {k for k,v in specs.items() if v['authority']=='context'}:
        raise ValueError('unknown or non-context input')
    if set(decisions) - {k for k,v in specs.items() if v['authority']=='gm'}:
        raise ValueError('unknown or non-delegated decision')
    native = {} if _state_reader is None else _state_reader(specs)
    values, obligations, evidence = {}, [], []
    definition_selections = {}
    for key, spec in specs.items():
        supplied = context if spec['authority']=='context' else decisions if spec['authority']=='gm' else native
        if key not in supplied or supplied[key] is None:
            obligation={'input': key, 'authority': spec['authority'], 'question': spec['question']}
            if 'decision_kind' in spec:obligation['decision_kind']=spec['decision_kind']
            obligation['constraints']={field:deepcopy(spec[field]) for field in ('type','choices','minimum','maximum') if field in spec}
            obligations.append(obligation)
            continue
        value = supplied[key]
        if spec['authority']=='gm':
            conflict=spec.get('decision_kind')=='source_conflict'
            scoped=conflict or (type(value)is dict and 'scope' in value)
            fields={'value','reason','scope'} if scoped else {'value','reason'}
            if type(value) is not dict or set(value)!=fields:
                raise ValueError('source conflict decision requires value, reason and scope' if conflict else 'GM decision requires value and reason')
            _text(value['reason'])
            if scoped and value['scope']!=decision_scope:
                raise ValueError('GM decision scope changed; review required')
            record={'input': key, 'reason': value['reason']}
            if 'decision_kind' in spec:
                record.update(decision_kind=spec['decision_kind'],scope=deepcopy(decision_scope))
            evidence.append(record)
            value = value['value']
        if not _matches(value, spec): raise ValueError('invalid policy input: '+key)
        if 'definition_kind' in spec:
            if not value.startswith(spec['definition_kind']+'/'):
                raise ValueError('exact definition kind required: '+key)
            selection=rules.select_source_definition(value)
            if selection['selected_id']!=value:
                raise ValueError('replacement definition needs explicit provider eligibility: '+key)
            definition_selections[key]=selection
        values[key] = value
    def bind(value):
        if type(value) is dict:
            if '$input' in value: return deepcopy(values[value['$input']])
            return {k:bind(v) for k,v in value.items()}
        if type(value) is list: return [bind(v) for v in value]
        return value
    import source_policy_predicates as P
    condition = P.evaluate(row.get('when',True),specs,values)
    status = 'PolicyNotApplicable' if condition.truth is R.Truth.FALSE else 'PolicyInputsRequired' if obligations else 'PolicyValuesReady'
    return {'status':status, 'condition':R.plain(condition),
            'policy_id':document['id'], 'selected_id':selected, 'selected_version':row.get('version'),
            'values':None if status!='PolicyValuesReady' else bind(row['values']),
            'obligations':obligations, 'decision_evidence':evidence, 'input_values':deepcopy(values),
            'source':deepcopy(row['source']), 'source_policy_binding':binding,
            'authored_source':deepcopy(registered), 'profile_hash':profile_hash,
            'definition_hash':definition_hash,'decision_scope':deepcopy(decision_scope),
            'inputs_hash':R.fingerprint({'context':context,'decisions':decisions,'state':native}),
            'state_bindings':{key:deepcopy(spec['binding']) for key,spec in specs.items() if spec['authority']=='state'},
            'definition_selections':deepcopy(definition_selections),
            'effects_executed':False}


class PolicyExecutionPending(ValueError):
    """A prepared effect bundle did not complete; no staged changes committed."""


def _grant_operation(values, inputs=None):
    """Validate closed operation shapes, including typed scalar placeholders."""
    if set(values) != {'grant_operation'} or type(values['grant_operation']) is not dict:
        raise ValueError('exact grant_operation execution field required')
    op = values['grant_operation']
    kind = op.get('type')
    if kind == 'acquire':
        required = {'type','group_id','grants','points','reason'}
        optional = {'allocation','owner_id','lifetime','qualification','replacement','withdrawal_policies'}
    elif kind == 'refund':
        required = {'type','sources','request_id','reason'}
        optional = {'allocations','withdrawal'}
    else:
        raise ValueError('unsupported grant operation')
    if not required <= set(op) or set(op) - (required | optional):
        raise ValueError('exact grant operation fields required')
    def scalar(value, expected):
        if inputs is not None and type(value) is dict and set(value) == {'$input'}:
            if inputs[value['$input']]['type'] != ('integer' if expected=='signed_integer' else expected):
                raise ValueError('grant input type mismatch')
        elif expected == 'string':
            _text(value)
        elif type(value) is not int or (expected != 'signed_integer' and value < 0):
            raise ValueError('nonnegative grant points required')
    def allocation(value):
        if type(value) is not dict or not value:
            raise ValueError('explicit allocation mapping required')
        for key, amount in value.items():
            _text(key); scalar(amount, 'integer')
    scalar(op['reason'], 'string')
    if kind == 'acquire':
        scalar(op['group_id'], 'string'); scalar(op['points'], 'integer')
        if 'qualification' in op and type(op['qualification']) is not dict:raise ValueError('qualification declaration required')
        if 'withdrawal_policies' in op:
            import acquisition_withdrawal as WITHDRAWAL
            WITHDRAWAL.policy_bindings(op['withdrawal_policies'],op['grants'])
        if 'owner_id' in op: scalar(op['owner_id'], 'string')
        if 'lifetime' in op and op['lifetime'] not in ('owner_bound','your_pokemon'):
            raise ValueError('unsupported grouped grant lifetime')
        if type(op['grants']) is not list or not op['grants']:
            raise ValueError('nonempty declared grant group required')
        for row in op['grants']:
            if type(row) is not dict or row.get('field') not in ('moves','abilities','capabilities','stats','skill_modifier'):
                raise ValueError('unsupported grouped grant field')
            fields = {'source_id','field','skill','delta'} if row['field']=='skill_modifier' else {'source_id','field','stat','delta','minimum'} if row['field']=='stats' else {'source_id','field','value'} | ({'learning_route'} if row['field']=='moves' else set())
            if set(row) != fields: raise ValueError('exact group grant fields required')
            scalar(row['source_id'], 'string')
            if row['field']=='skill_modifier':
                scalar(row['skill'],'string');scalar(row['delta'],'signed_integer')
            elif row['field']=='stats':
                if row['stat'] not in ('hp','atk','def','spa','spd','spe'):raise ValueError('known stat required')
                scalar(row['delta'],'signed_integer')
                if row['minimum'] is not None:scalar(row['minimum'],'signed_integer')
            else:scalar(row['value'], 'string')
            if row['field']=='moves' and row['learning_route'] not in ('taught','granted'):
                raise ValueError('explicit move learning route required')
        if 'allocation' in op: allocation(op['allocation'])
    else:
        scalar(op['request_id'], 'string')
        if type(op['sources']) is not list or not op['sources']:
            raise ValueError('nonempty refund sources required')
        for source in op['sources']: scalar(source, 'string')
        if 'allocations' in op:
            if type(op['allocations']) is not dict or not op['allocations']:
                raise ValueError('explicit group allocations required')
            for key, shares in op['allocations'].items():
                _text(key); allocation(shares)
    return op


def _progression_operation(values,inputs=None):
    if set(values)!={'progression_operation'} or type(values['progression_operation']) is not dict:
        raise ValueError('exact progression_operation field required')
    op=values['progression_operation']
    schemas={
        'experience':{'kind','request_id','reason','amount'},
        'milestone':{'kind','request_id','reason'},
        'milestone_choice':{'kind','level','option','reason'},
        'milestone_stats':{'kind','level','stats','request_id','reason'},
        'growth_stats':{'kind','stats','request_id','reason'}}
    kind=op.get('kind')
    if type(kind) is not str or kind not in schemas:raise ValueError('unsupported progression operation')
    fields=schemas[kind]
    if set(op)!=fields:raise ValueError('exact progression operation fields required')
    def scalar(value,expected):
        if inputs is not None and type(value) is dict and set(value)=={'$input'}:
            if inputs[value['$input']]['type']!=expected:raise ValueError('progression input type mismatch')
        elif expected=='string':_text(value)
        elif type(value) is not int or value<0:raise ValueError('nonnegative progression integer required')
    for key in fields-{'kind','stats'}:
        scalar(op[key],'integer' if key in ('amount','level') else 'string')
    if 'level' in op and type(op['level']) is int:
        import trainer_milestone_rewards as REWARDS
        if op['level'] not in REWARDS.OPTIONS:raise ValueError('known special milestone level required')
    if kind=='milestone_choice' and type(op['option']) is str:
        import trainer_milestone_rewards as REWARDS
        allowed=REWARDS.OPTIONS.get(op['level'],()) if type(op['level']) is int else {option for options in REWARDS.OPTIONS.values() for option in options}
        if op['option'] not in allowed:raise ValueError('allowed milestone option required')
    if kind in ('milestone_stats','growth_stats'):
        stats=op['stats']
        allowed={'hp','atk','def','spa','spd','spe'} if kind=='growth_stats' else {'atk','spa'}
        if type(stats) is not dict or not stats or not set(stats)<=allowed or (kind=='milestone_stats' and set(stats)!=allowed):raise ValueError('explicit allocation within allowed stats required')
        for value in stats.values():scalar(value,'integer')
        if all(type(value) is int for value in stats.values()) and not sum(stats.values()):raise ValueError('positive milestone allocation required')
    return op


def _training_operation(values,inputs=None):
    """Declare native multi-target training; formulas and quotas stay native."""
    if set(values)!={'training_operation'} or type(values['training_operation']) is not dict:
        raise ValueError('exact training_operation execution field required')
    op=values['training_operation'];kind=op.get('kind')
    if kind not in ('groom','experience','regime','hour'):raise ValueError('unsupported native training kind')
    required={'kind','targets'};optional={'pushed_skills','safe'}
    if kind=='hour':required|={'safe','reason','request_id'};optional=set()
    if kind=='regime':required|={'features','minutes','reason','request_id'};optional={'from_grooming','from_training','safe'}
    if kind=='experience':optional|={'use_intimidate','from_grooming','from_training','bonus_skill','grooming_policy','beast_policy','use_reserves'}
    if not required<=set(op) or set(op)-(required|optional):raise ValueError('exact native training fields required')
    def scalar(value,expected):
        if inputs is not None and type(value) is dict and set(value)=={'$input'}:
            if inputs[value['$input']]['type']!=expected:raise ValueError('training input type mismatch')
        elif expected=='string':_text(value)
        elif expected=='integer':
            if type(value) is not int or value<30:raise ValueError('at least thirty training minutes required')
        elif type(value) is not bool:raise ValueError('explicit boolean training option required')
    targets=op['targets']
    if type(targets) is not list or not 1<=len(targets)<=6:raise ValueError('one to six declared training targets required')
    for value in targets:scalar(value,'string')
    if all(type(value) is str for value in targets) and len(set(targets))!=len(targets):
        raise ValueError('distinct training target identities required')
    for key,value in op.items():
        if key in ('kind','targets'):continue
        if key=='features':
            if type(value) is not dict or not value:raise ValueError('per-target training features required')
            for uid,names in value.items():
                _text(uid)
                if type(names) is not list or not names:raise ValueError('nonempty training feature choices required')
                for name in names:scalar(name,'string')
        elif key=='minutes':scalar(value,'integer')
        elif key=='pushed_skills':
            if type(value) is not dict or not value:raise ValueError('explicit pushed skill mapping required')
            for uid,skill in value.items():_text(uid);scalar(skill,'string')
        else:scalar(value,'string' if key in ('bonus_skill','grooming_policy','beast_policy','reason','request_id') else 'boolean')
    return op


def _training_targets(engine,identities):
    import world_entities as W
    index=W.actor_index(engine);targets=[]
    for uid in identities:
        if uid not in index:raise ValueError('actual registered training target required: '+uid)
        targets.append(index[uid])
    W.require_actors(engine,*targets)
    return targets


def execute_training(engine,actor,document,*,context=None,decisions=None,request_id=None):
    """Train declared actual world IDs together using the native group consumer.

    Both policy state subjects identify the trainer; per-Pokemon eligibility is
    checked by native training. Target strings may bind declared inputs. All
    target IDs, order and native results are retained as execution evidence.
    """
    return _execute(engine,actor,actor,document,context=context,decisions=decisions,
                    request_id=request_id,_training=True)


def _teaching_operation(values,inputs=None):
    """Closed native teaching operations; authors cannot replace native costs."""
    if set(values)!={'teaching_operation'} or type(values['teaching_operation']) is not dict:
        raise ValueError('exact teaching_operation execution field required')
    op=values['teaching_operation'];kind=op.get('kind')
    if kind=='edge':
        required={'kind','edge'};optional={'skill','stat','capability','move_id','lesson','ability','from_grooming','from_training','safe'}
    elif kind=='machine':
        required={'kind','instance_id'};optional={'replace'}
    elif kind=='feature':
        required={'kind','feature','move_id','seconds','reason'};optional={'replace'}
    else:raise ValueError('unsupported native teaching kind')
    if not required<=set(op) or set(op)-(required|optional):
        raise ValueError('exact native teaching fields required')
    for key,value in op.items():
        if key=='kind':continue
        if key=='lesson':
            if type(value)is not dict or set(value)!={'species','move_id'}:raise ValueError('explicit final species and Move lesson fields required')
            for part in value.values():
                if inputs is not None and type(part)is dict and set(part)=={'$input'}:
                    if inputs[part['$input']]['type']!='string':raise ValueError('lesson input type mismatch')
                else:_text(part)
            continue
        expected='boolean' if key in ('from_grooming','from_training','safe') else 'integer' if key=='seconds' else 'string'
        if inputs is not None and type(value) is dict and set(value)=={'$input'}:
            if inputs[value['$input']]['type']!=expected:raise ValueError('teaching input type mismatch')
        elif expected=='string':_text(value)
        elif expected=='boolean':
            if type(value) is not bool:raise ValueError('explicit boolean grooming choice required')
        elif type(value) is not int or value<1:raise ValueError('positive teaching duration required')
    return op


def execute_teaching(engine,actor,target,document,*,context=None,decisions=None,request_id=None):
    """Run existing Edge, machine or Mentor/Tutor acquisition on the actual pair.

    teaching_operation.kind is edge, machine or feature; remaining fields are
    the native consumer's named scalar options. Cost, source selection, actual
    ownership, qualifications, completed grooming, frequency and move occupancy
    are still enforced by pokemon_teaching. No arbitrary state setter is exposed.
    Request IDs use the shared policy replay ledger and survive save/restore.
    """
    return _execute(engine,actor,target,document,context=context,decisions=decisions,
                    request_id=request_id,_teaching=True)


def execute_progression(engine,actor,target,document,*,context=None,decisions=None,request_id=None):
    """Apply native growth, milestone branch choice or restricted stat allocation.

    progression_operation.kind is static: experience, milestone,
    milestone_choice, milestone_stats or growth_stats. Scalar fields allow typed inputs;
    milestone allocation requires explicit atk/spa amounts; growth_stats accepts
    a nonempty subset of the six combat stats. Actual reward qualification
    and branch availability are checked by the native consumer after binding.
    """
    return _execute(engine,actor,target,document,context=context,decisions=decisions,
                    request_id=request_id,_progression=True)


def execute_effects(engine, actor, target, document, *, context=None, decisions=None, request_id=None, _action=False):
    """Execute effects, optionally binding completion to an application request ID.

    With request_id, return durable evidence plus replayed; repeated canonical
    requests return the original execution without costs, RNG or dispatch tokens.
    Source/profile and actual participant checks still apply. Pending/invalid
    attempts are uncommitted and do not reserve a completed request identity.
    Omit request_id for the legacy per-invocation dispatcher receipt contract.
    """
    return _execute(engine, actor, target, document, context=context, decisions=decisions,
                    request_id=request_id, _action=_action)


def execute_grants(engine, actor, target, document, *, context=None, decisions=None, request_id=None):
    """Execute host-adjudicated acquisition/withdrawal on the actual target.

    The sole values field is grant_operation. Acquire operations declare type,
    group_id, grants, points, reason and optional owner_id/lifetime/allocation.
    Refund operations declare type, sources, request_id, reason and optional
    allocations. Scalar values may reference declared typed inputs; operation
    kinds, grant fields, learning routes and mapping keys are static. Acquisition
    rule_id is always the selected source, never an independently supplied ID.
    A replay returns the native historical result and adds a policy invocation
    record; grants_executed means the adapter completed, not a fresh debit.

    Eligibility is supplied by the application declaration; execution does not
    certify source interpretation or grant host authorization.
    """
    return _execute(engine, actor, target, document, context=context, decisions=decisions,
                    request_id=request_id, _grants=True)


def execute_operations(engine, actor, target, document, *, context=None, decisions=None, request_id=None,
                       tool_instance_id=None):
    """Run a data-only ordered native program through the existing transaction."""
    return _execute(engine,actor,target,document,context=context,decisions=decisions,
                    request_id=request_id,_operations=True,_tool_instance_id=tool_instance_id)


def _execute(engine, actor, target, document, **options):
    import source_context as SC
    with SC.capture_reads(engine.r) as reads:
        return _execute_captured(engine,actor,target,document,_trace_reads=reads,**options)


def _execute_captured(engine, actor, target, document, *, context=None, decisions=None, request_id=None, _action=False, _grants=False, _progression=False, _teaching=False, _training=False, _operations=False, _trace_reads=None, _tool_instance_id=None):
    """Execute an authored operation atomically using its native consumer.

    This is an application-authorized effect entry, not acquisition/usage legality
    or action-cost automation. Callers must use the appropriate action consumer
    for those obligations. Declarations cannot inject native private metadata.
    """
    import effects as FX
    import state_grants as GRANTS
    import source_policy_state as STATE
    if _operations:
        import foundation_operations as OPERATIONS,world_entities as WORLD
        WORLD.require_actors(engine,actor,target)
    if _tool_instance_id is not None:
        _text(_tool_instance_id)
        if not _operations:raise ValueError('physical tool binding requires an operation program')
    def prepare(e,a,t):
        return resolve(e.r,document,context=context,decisions=decisions,
                       _state_reader=lambda specs:STATE.read(e,a,t,specs))
    prepared = prepare(engine,actor,target)
    if _progression:
        import trainer_entitlements as ENTITLEMENTS
        ENTITLEMENTS.validate(target)
        import trainer_milestone_rewards as REWARDS
        REWARDS.validate(target)
    if request_id is not None:
        import resolution_transaction as TX
        # State-bound inputs and budgets may have changed because this request
        # already completed. Replays read history, while source/profile freshness
        # and actual participant admission still run through prepare above.
        intent = {'document':document,'context':context or {},'decisions':decisions or {},
                  'actor_id':actor.entity_id,'target_id':target.entity_id,
                  'profile_hash':prepared['profile_hash'],
                  'mode':'operations' if _operations else 'training' if _training else 'teaching' if _teaching else 'progression' if _progression else 'grants' if _grants else ('action' if _action else 'effects')}
        if _tool_instance_id is not None:intent['tool_instance_id'] = _tool_instance_id
        prior = TX.replay_result(getattr(engine,'_source_policy_requests',{}),
                                 request_id,intent,fingerprint_field='intent')
        if prior is not None:
            if _training:_training_targets(engine,prior['result']['training_target_ids'])
            return dict(prior['result'], replayed=True)
    if prepared['status'] != 'PolicyValuesReady':
        return prepared
    tool_use = None
    if _tool_instance_id is not None:
        import crafting_recipes as TOOLS
        tool_use = TOOLS.require_tool(engine,actor,_tool_instance_id)
    values = prepared['values']
    fields = {'effects','action','ap'} if _action else {'effects'}
    if _action:
        fields.update(key for key in ('recipient_debt','frequency') if key in values)
    if _operations:
        operation_plan=OPERATIONS.plan(prepared,event_id=request_id or prepared['policy_id'])
        operation=operation_plan['aspects'][0]['value']
    elif _training:
        operation = _training_operation(values)
    elif _teaching:
        operation = _teaching_operation(values)
    elif _progression:
        operation = _progression_operation(values)
    elif _grants:
        operation = _grant_operation(values)
        if 'replacement' in operation and request_id is None:raise ValueError('replacement acquisition requires durable request identity')
        if 'withdrawal_policies' in operation and request_id is None:raise ValueError('withdrawal policy acquisition requires durable request identity')
    elif set(values) != fields or type(values.get('effects')) is not list or not values['effects']:
        raise ValueError('exact execution fields and nonempty effects list required')
    action = None
    frequency_key = None
    if _action:
        import action_metadata as META
        action = META.ActionCost(tuple(values['action'])) if type(values['action']) is list else values['action']
        if not META.supported_combat_action(action):
            raise ValueError('unsupported authored combat action')
        if 'frequency' in values:
            import frequency as FREQ
            frequency_key=FREQ.declaration_key(engine,actor,target,prepared['selected_id'],action,values['frequency'])
        if 'recipient_debt' in values:
            import action_resources as RESOURCES
            RESOURCES.loss(values['recipient_debt'])
        ap = values['ap']
        if type(ap) is not dict or type(ap.get('amount')) is not int or ap['amount'] < 0 or ap.get('mode') not in ('spend','drain','bind'):
            raise ValueError('explicit nonnegative AP amount and known mode required')
        expected={'amount','mode','instance_id','ending_method'} if ap['mode']=='bind' else {'amount','mode'}
        if set(ap)!=expected:raise ValueError('exact AP declaration fields required')
        if ap['mode']=='bind':
            import bound_ap as BOUND
            BOUND.prepare_effects(engine,actor,target,values['effects'],
                                  ending_method=ap['ending_method'],source_ref=prepared['selected_id'])
        if not engine.encounter_active:
            raise ValueError('authored combat action requires an active encounter')
    def public(value):
        if type(value) is dict:
            if any(key.startswith('_') for key in value):
                raise ValueError('authored effects cannot set private runtime metadata')
            for child in value.values(): public(child)
        elif type(value) is list:
            for child in value: public(child)
    public(values)
    # Provider callbacks and arbitrary hooks may perform external I/O that the
    # native in-memory transition cannot roll back. Bind decisions beforehand.
    for rulings in (engine.r.rulings, getattr(engine,'rulings',None)):
        if rulings is not None and (rulings.provider or any(rulings.hooks.values())):
            raise ValueError('policy effects require prebound decisions without callbacks')
    def apply(staged_engine, staged_actor, staged_target):
        import event_trace as TRACE
        before = TRACE.resources(staged_engine)
        current = prepare(staged_engine,staged_actor,staged_target)
        if current != prepared:
            raise PolicyExecutionPending('policy inputs changed before execution')
        if tool_use is not None and TOOLS.require_tool(staged_engine,staged_actor,_tool_instance_id) != tool_use:
            raise ValueError('physical tool identity or ownership changed before execution')
        withdrawal_result = None
        if _grants and operation['type']=='refund' and 'withdrawal' in operation:
            import acquisition_withdrawal as W
            withdrawal_result=W.policy(operation['withdrawal'])
            if withdrawal_result['status']=='pending':raise PolicyExecutionPending('withdrawal policy unresolved')
            if withdrawal_result['status']!='allowed':raise ValueError('withdrawal cause denied')
        replacement_result = None
        resolved_grants = None
        if _grants and operation['type']=='acquire' and 'replacement' in operation:
            import acquisition_qualification as Q
            resolved_grants,replacement_result=Q.replacement(staged_engine,staged_actor,staged_target,prepared['selected_id'],operation)
            if replacement_result['status']=='pending':raise PolicyExecutionPending('replacement qualification unresolved')
            if replacement_result['status']!='qualified':raise ValueError('replacement qualification denied')
        qualification_result = None
        if _grants and operation['type']=='acquire' and 'qualification' in operation:
            import acquisition_qualification as Q
            qualification_result=Q.declaration_result(prepared['selected_id'],operation['qualification'])
            if qualification_result['provider']!=staged_actor.entity_id:
                raise ValueError('qualification provider must be the actual granting actor')
            if qualification_result['status']=='pending':raise PolicyExecutionPending('acquisition qualification unresolved')
            if qualification_result['status']!='qualified':raise ValueError('acquisition qualification denied')
        if frequency_key is not None:
            import frequency as FREQ
            if not FREQ.activation_allowed(staged_actor,frequency_key,values['frequency'],engine=staged_engine):
                raise PolicyExecutionPending('authored activation frequency exhausted')
        if _action:
            import turn as TURN
            import action_lifecycle as ACTION
            import action_points as AP
            sleep_cure=ACTION.self_cures_sleep(staged_actor,staged_target,values['effects'])
            if not TURN.spend(staged_engine,staged_actor,action,prepared['selected_id'],sleep_cure=sleep_cure):
                raise PolicyExecutionPending('ordinary action permission or budget denied')
            if values['ap']['amount'] and values['ap']['mode']!='bind':
                AP.charge(staged_actor,values['ap']['amount'],mode=values['ap']['mode'])
        if _operations:
            operation_results=OPERATIONS.execute(staged_engine,staged_actor,staged_target,operation,prepared['selected_id'],tool_use=tool_use)
            outcomes=[]
        elif _training:
            import pokemon_activities as TRAINING
            targets=_training_targets(staged_engine,operation['targets'])
            args={key:value for key,value in operation.items() if key not in ('kind','targets')}
            if operation['kind']=='hour':
                training_result=staged_engine.complete_training_hour(staged_actor,targets,**args)
            elif operation['kind']=='regime':
                features=args.pop('features')
                if set(features)!=set(operation['targets']):raise ValueError('training choices must match every actual target')
                choices=[(pokemon,features[pokemon.entity_id]) for pokemon in targets]
                training_result=staged_engine.train_pokemon(staged_actor,choices,**args)
            else:
                activity='groom' if operation['kind']=='groom' else 'experience_training'
                training_result=TRAINING.perform(staged_engine,staged_actor,activity,targets=targets,**args)
            outcomes=[]
        elif _teaching:
            import pokemon_teaching as TEACHING
            consumer={'edge':TEACHING.teach_edge,'machine':TEACHING.teach_machine,'feature':TEACHING.teach_feature}[operation['kind']]
            args={key:value for key,value in operation.items() if key!='kind'}
            teaching_result=consumer(staged_engine,staged_actor,target=staged_target,**args)
            outcomes=[]
        elif _progression:
            import downtime
            import trainer_milestone_rewards as REWARDS
            if operation['kind'] in ('experience','milestone'):
                progression_result=downtime.award_trainer_progression(staged_engine,staged_target,**operation)
            else:
                consumer=REWARDS.choose if operation['kind']=='milestone_choice' else REWARDS.allocate_growth if operation['kind']=='growth_stats' else REWARDS.allocate
                args={key:value for key,value in operation.items() if key!='kind'}
                progression_result=consumer(staged_engine,staged_target,**args)
            outcomes=[]
        elif _grants:
            import grant_payments as PAY
            args = {key:value for key,value in operation.items() if key not in ('type','qualification','replacement','withdrawal','withdrawal_policies')}
            if withdrawal_result is not None:args['refund_mode']=withdrawal_result['refund_mode']
            if resolved_grants is not None:args['grants']=resolved_grants
            if operation['type'] == 'acquire':
                grant_result = PAY.acquire(staged_engine, staged_target,
                                           rule_id=prepared['selected_id'], **args)
                if 'withdrawal_policies' in operation:
                    import acquisition_withdrawal as WITHDRAWAL
                    for key,policies in operation['withdrawal_policies'].items():
                        WITHDRAWAL.bind_policy(staged_engine,staged_target,key,policies)
            else:
                try:grant_result = PAY.refund(staged_engine, staged_target, **args)
                except PAY.RefundAllocationPending as exc:raise PolicyExecutionPending(str(exc)) from exc
            outcomes = []
        elif _action and values['ap']['mode']=='bind':
            import bound_ap as BOUND
            BOUND.activate_effects(staged_engine,staged_actor,staged_target,values['ap']['instance_id'],
                amount=values['ap']['amount'],effects=values['effects'],
                ending_method=values['ap']['ending_method'],source_ref=prepared['selected_id'])
            outcomes=[{'source_id':prepared['selected_id'],'status':'completed',
                       'instance_id':values['ap']['instance_id']}]
        else:
            batch = FX.run_effects(staged_engine, staged_actor, staged_target,
                                   values['effects'], {'hit':True}, prepared['selected_id'])
            if any(row.status not in ('completed','condition_false') for row in batch.outcomes):
                raise PolicyExecutionPending('effect bundle unresolved: '+','.join(row.status for row in batch.outcomes))
            outcomes = [{'source_id':row.source_id,'status':row.status,
                         'occurrence':row.occurrence} for row in batch.outcomes]
        if frequency_key is not None:
            FREQ.consume_activation(staged_actor,frequency_key,values['frequency'],engine=staged_engine)
        if _action and 'recipient_debt' in values:
            import action_resources as RESOURCES
            RESOURCES.schedule(staged_target,values['recipient_debt'])
        if prepare(engine,actor,target) != prepared:
            raise PolicyExecutionPending('policy inputs changed before commit')
        sequence = getattr(staged_engine,'_source_policy_sequence',0)+1
        execution_id = 'source-policy:'+str(sequence)
        record = dict(prepared, execution_id=execution_id,
                      status='PolicyOperationsCompleted' if _operations else 'PolicyTrainingCompleted' if _training else 'PolicyTeachingCompleted' if _teaching else 'PolicyProgressionCompleted' if _progression else 'PolicyGrantsCompleted' if _grants else ('PolicyActionCompleted' if _action else 'PolicyEffectsCompleted'),
                      effects_executed=not (_operations or _grants or _progression or _teaching or _training), actor_id=staged_actor.entity_id,
                      target_id=staged_target.entity_id,
                      scope={'kind':'single_execution','round':staged_engine.round_no,
                             'session_id':getattr(staged_engine,'session_id',None)},
                      outcomes=outcomes)
        if qualification_result is not None:record['qualification']=qualification_result
        if tool_use is not None:record['tool_use']=tool_use
        if _operations:record.update(operations_executed=True,operation_plan=operation_plan,operation_results=operation_results)
        if replacement_result is not None:record['replacement']=replacement_result
        if withdrawal_result is not None:record['withdrawal']=withdrawal_result
        if _grants and 'withdrawal_policies' in operation:record['withdrawal_policies']=deepcopy(operation['withdrawal_policies'])
        if _training:
            record.update(training_executed=True,training_target_ids=list(operation['targets']),training_result=training_result)
        if _teaching:
            record.update(teaching_executed=True,teaching_result=teaching_result)
        if _progression:
            record.update(progression_executed=True,progression_result=progression_result)
        if _grants:
            record.update(grants_executed=True, grant_operation=operation['type'],
                          grant_result=grant_result)
        record["trace"] = {"schema":1,"state":"completed",
            "source_reads":deepcopy(_trace_reads),
            "resource_changes":TRACE.changes(before,TRACE.resources(staged_engine)),
            "resource_scope":list(TRACE.RESOURCE_FIELDS)}
        # Store plain values, not dispatcher tokens/callbacks or live actor refs.
        # This record is evidence only; it grants no authority to replay effects.
        trace = record.pop('trace')
        record = R.plain(R.freeze(record))
        # Native observations can contain finite decimal source values. They
        # remain evidence, never executable exact-arithmetic declarations.
        record['trace'] = json.loads(json.dumps(trace,ensure_ascii=False,allow_nan=False))
        if not hasattr(staged_engine,'_source_policy_executions'):
            staged_engine._source_policy_executions = {}
        staged_engine._source_policy_executions[execution_id] = deepcopy(record)
        staged_engine._source_policy_sequence = sequence
        if request_id is not None:
            record['request_id'] = request_id
            staged_engine._source_policy_executions[execution_id] = deepcopy(record)
            if not hasattr(staged_engine,'_source_policy_requests'):
                staged_engine._source_policy_requests = {}
            staged_engine._source_policy_requests[request_id] = {
                'intent':TX.request_fingerprint(intent),'result':deepcopy(record)}
            # Request-based consumers receive durable evidence, never a new
            # dispatcher token that could authorize an additional effect.
            return dict(record, replayed=False)
        if _operations or _grants or _progression or _teaching or _training or (_action and values['ap']['mode']=='bind'): return record
        return dict(record, outcomes=[{'source_id':row.source_id,'status':row.status,
                                      'receipt':row.receipt} for row in batch.outcomes])
    # Native effects and nested operations can change terrain indirectly in any
    # execution mode. Commit the staged map through the same shared transition;
    # mapless programs retain their existing actor/world-only contract.
    return GRANTS.transition(engine,actor,apply,participants=(target,),
                             include_grid=engine.grid is not None)


def execution_record(engine, execution_id):
    """Read a detached historical record; never use it to authorize new effects."""
    _text(execution_id)
    records = getattr(engine,'_source_policy_executions',{})
    if execution_id not in records:
        raise KeyError('no completed source policy execution: '+execution_id)
    return deepcopy(records[execution_id])


def register_sources(rules, definitions):
    """Admit explicit application-authored identities without replacing native IDs.

    File hashes/locators prove the cited material exists, not its interpretation.
    Tags and rationale are authored evidence; registration never chooses a winner.
    Native ambiguous identities remain untouched and cannot gain authority here.
    """
    import csv
    from ruleset import RuleSelection
    definitions = R.plain(R.freeze(definitions))
    if type(definitions) is not list or not definitions:
        raise ValueError('nonempty source definitions required')
    root = Path(rules.root).resolve()
    known = deepcopy(getattr(rules,'_authored_policy_sources',{}))
    new_units = []
    for row in definitions:
        fields = {'id','title','source','locator','tags','rationale'}
        if type(row) is not dict or set(row) != fields:
            raise ValueError('exact authored source definition fields required')
        uid = _text(row['id']);_text(row['title']);_text(row['rationale'])
        if not uid.startswith('authored/') or not uid.removeprefix('authored/'):
            raise ValueError('authored source IDs must use authored/ namespace')
        if type(row['tags']) is not list or any(type(v) is not str or not v for v in row['tags']):
            raise ValueError('explicit source tag list required')
        source = row['source'];locator = row['locator']
        if type(source) is not dict or set(source) != {'file','sha256'}:
            raise ValueError('source file and sha256 required')
        _text(source['file']);_text(source['sha256'])
        path = (root/source['file']).resolve()
        if not path.is_relative_to(root/'input'):
            raise ValueError('authored source must be inside input')
        content = verified_source(rules, source, label='authored')
        if type(locator) is not dict:
            raise ValueError('exact source locator required')
        if set(locator)=={'lines'}:
            bounds=locator['lines']
            if type(bounds) is not list or len(bounds)!=2 or any(type(v) is not int for v in bounds) or not 1<=bounds[0]<=bounds[1]<=len(content.decode('utf-8-sig').splitlines()):
                raise ValueError('invalid source line bounds')
        elif set(locator)=={'record'} and path.suffix.lower()=='.csv':
            import io
            records=list(csv.reader(io.StringIO(content.decode('utf-8-sig'))))
            if type(locator['record']) is not int or not 1<=locator['record']<=len(records):
                raise ValueError('invalid CSV source record')
        elif set(locator)=={'pages'} and path.suffix.lower()=='.pdf':
            import io
            from pypdf import PdfReader
            bounds=locator['pages']
            if type(bounds) is not list or len(bounds)!=2 or any(type(v) is not int for v in bounds) or not 1<=bounds[0]<=bounds[1]:
                raise ValueError('invalid PDF source page bounds')
            try:
                reader=PdfReader(io.BytesIO(content))
                if reader.is_encrypted or bounds[1]>len(reader.pages):
                    raise ValueError('invalid or encrypted PDF source page bounds')
            except Exception as exc:
                raise ValueError('invalid PDF source page bounds or document') from exc
        else:
            raise ValueError('lines, CSV record or PDF pages locator required')
        if uid in known:
            if known[uid]!=row:raise ValueError('authored source identity cannot be redefined')
            continue
        if uid in rules.selection.units:
            raise ValueError('source identity already belongs to another registration')
        unit={'id':uid,'title':row['title'],'kind':'authored:policy',
              'source':{'file':path.relative_to(root/'input').as_posix(),'sha256':source['sha256'],**deepcopy(locator)},
              'tags':row['tags']}
        # Evaluate current profile including unknown lineage. Excluded sources
        # may be registered as alternatives, but resolve() will still reject them.
        decision=rules.ruleset.decision(unit)
        if decision['status']=='unresolved':
            raise ValueError('unresolved authored source: '+decision['reason'])
        known[uid]=row;new_units.append(unit)
    selection=RuleSelection(rules.ruleset,list(rules.selection.units.values())+new_units)
    selection.dependencies=deepcopy(rules.selection.dependencies)
    selection.source_audit_snapshots=deepcopy(getattr(rules.selection,'source_audit_snapshots',{}))
    rules.selection=selection
    rules._authored_policy_sources=known
    return deepcopy(definitions)


def load_package(rules, package):
    """Validate a JSON declaration bundle before publishing any catalog changes.

    Loading verifies references and operation names, not gameplay applicability.
    Actual inputs, state-dependent contracts and source freshness are checked at
    execution. Packages contain data only and never install Python callbacks.
    """
    import json
    from copy import copy
    import effects as FX
    if type(package) is str:
        def unique_pairs(pairs):
            result={}
            for key,value in pairs:
                if key in result:raise ValueError('duplicate JSON key: '+key)
                result[key]=value
            return result
        def bad_constant(value):raise ValueError('invalid JSON constant: '+value)
        package=json.loads(package,object_pairs_hook=unique_pairs,parse_constant=bad_constant)
    package=R.plain(R.freeze(package))
    if type(package) is not dict or set(package)!={'schema','sources','policies'} or type(package['schema']) is not int or package['schema']!=1:
        raise ValueError('exact source policy package schema required')
    if type(package['sources']) is not list or type(package['policies']) is not list or not package['policies']:
        raise ValueError('source list and nonempty policy list required')
    staged=copy(rules)
    staged.ruleset=deepcopy(rules.ruleset)
    if package['sources']:register_sources(staged,package['sources'])
    documents=deepcopy(getattr(rules,'_source_policy_documents',{}))
    seen=set();results=[]
    for document in package['policies']:
        # Resolve checks schema, every variant's typed declaration, selected
        # identity and source hash. Required inputs may deliberately be pending.
        prepared=resolve(staged,document)
        uid=document['id']
        if uid in seen:raise ValueError('duplicate policy in package')
        seen.add(uid)
        if uid in documents and documents[uid]!=document:
            raise ValueError('loaded policy identity cannot be redefined')
        for row in document['variants']:
            source=row['source']
            verified_source(staged, source, label='package')
            if row['rule_id'] not in staged.selection.units:
                raise ValueError('package variant has no source identity')
            registered=getattr(staged,'_authored_policy_sources',{}).get(row['rule_id'])
            if registered is not None and registered['source']!=source:
                raise ValueError('package variant differs from registered provenance')
            if staged.selection.units[row['rule_id']]['source'].get('file')!=source['file'].removeprefix('input/'):
                raise ValueError('package variant source mismatch')
            if 'training_operation' in row['values']:
                _training_operation(row['values'],row['inputs'])
            if 'teaching_operation' in row['values']:
                _teaching_operation(row['values'],row['inputs'])
            if 'progression_operation' in row['values']:
                _progression_operation(row['values'],row['inputs'])
            if 'grant_operation' in row['values']:
                _grant_operation(row['values'], row['inputs'])
            if 'effects' in row['values']:
                effects=row['values']['effects']
                if type(effects) is not list or not effects:
                    raise ValueError('declared effects must be a nonempty list')
                for effect in effects:
                    if type(effect) is not dict or type(effect.get('type')) is not str or effect['type'] not in FX.HANDLERS or effect['type'] in FX.JUDGEMENT_TYPES|FX.ENGINE_TYPES:
                        raise ValueError('unsupported package effect operation')
        documents[uid]=deepcopy(document)
        results.append({'policy_id':uid,'status':prepared['status'],'obligations':prepared['obligations'],
                        'execution_certified':False})
        if prepared['status']=='PolicyValuesReady' and 'operations' in prepared['values']:
            import foundation_operations as OPERATIONS
            results[-1]['operation_plan']=OPERATIONS.plan(prepared,event_id='load:'+uid)
    staged.selection.filter=rules.ruleset
    rules.ruleset.alias_conflicts=deepcopy(staged.ruleset.alias_conflicts)
    rules.selection=staged.selection
    if hasattr(staged,'_authored_policy_sources'):
        rules._authored_policy_sources=deepcopy(staged._authored_policy_sources)
    rules._source_policy_documents=documents
    return results


def loaded_document(rules, policy_id):
    _text(policy_id)
    documents=getattr(rules,'_source_policy_documents',{})
    if policy_id not in documents:raise KeyError('no loaded source policy: '+policy_id)
    return deepcopy(documents[policy_id])
