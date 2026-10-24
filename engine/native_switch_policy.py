"""The explicit Korean Orders / English 1.05 Stratagems Baton source conflict."""
from copy import deepcopy
import root_resolution as ROOT
import source_policy as POLICY

BATON='move/배턴터치'
KEY='baton_source_choice'
KOREAN={'file':'input/db/moves.csv','sha256':'ab83f872e5eca67a41db7d126b842f0165437e0fa70bb77ddad832a0b7396c93'}
ENGLISH={'file':'source-audit/core-1.05-baton-pass.txt','sha256':'58e750d4753308533ba009817288abd14167f7ec467d5ba7c9e6b1fcc6f76757'}
ORIGINS={'korean':{'record':443,'physical_line':477},
    'english':{'file':'english-sources/core-1.05.txt','sha256':'a0e5f0bf0eaf9d79cf2a268b3647c077b7175cc3172e35d620a476dad73992b1','LF_line':11662},
    'english_index':{'file':'english-sources/indices-reference-1.05.txt','sha256':'87c5b4a18b4fc427e168cf2cbdcdc34523f0a00045f8ed166d8cd934561852b4','LF_line':2049}}
VARIANTS={'korean_orders':'orders','english_1_05_stratagems':'stratagems'}
QNA={'file':'input/hb-finance.md','sha256':'3c813528b5bd62cca98c69c16e75b4e9ddc4fb910a11fd37421ab79ddffeb416'}
QNA_LINE_SHA='8f8291bb5b0c3714be263b9001e4e20e5d6817df94afdc932784d013c94a504f'


def document():
    return {'schema':1,'id':'native/baton-transfer-scope','variants':[{
        'rule_id':BATON,'source':deepcopy(KOREAN),
        'values':{'variant':{'$input':'source_text'}},
        'inputs':{'source_text':{'type':'string','authority':'gm','decision_kind':'source_conflict',
            'choices':list(VARIANTS),'question':'Korean Baton Pass passes all Orders; English 1.05 passes Stratagems only. Which source contract applies?'}}}]}


def sources(engine):
    from source_context import verified_source
    verified_source(engine.r,KOREAN,label='Korean Baton Pass')
    verified_source(engine.r,ENGLISH,label='English 1.05 Baton Pass excerpt',source_root='source-audit')
    return {'korean':deepcopy(KOREAN),'english_excerpt':deepcopy(ENGLISH),'original_locators':deepcopy(ORIGINS)}


def choices(engine):
    sources(engine)
    return POLICY.resolve(engine.r,document())


def choose(engine,pokemon,variant,*,reason,decision_scope):
    """Record an explicit scoped source decision; this never executes a Move."""
    import world_entities as W
    W.require_actors(engine,pokemon)
    if pokemon.kind!='pokemon':raise ValueError('actual Baton/Tag In outgoing Pokemon required')
    decision={'value':variant,'reason':reason,'scope':deepcopy(decision_scope)}
    receipt=POLICY.resolve(engine.r,document(),decisions={'source_text':decision})
    if receipt['status']!='PolicyValuesReady':raise ValueError('complete explicit Baton source choice required')
    choice={'decision':deepcopy(decision),'receipt':deepcopy(receipt)}
    result={'variant':variant,'scope':VARIANTS[variant],'authority':'explicit_source_conflict',
            'sources':sources(engine),'binding':receipt['source_policy_binding'],'choice':deepcopy(choice)}
    pokemon.spec[KEY]=choice
    return result


def contract(engine,pokemon):
    refs=sources(engine);choice=pokemon.spec.get(KEY)
    if choice is None:
        prepared=POLICY.resolve(engine.r,document())
        return {'variant':'korean_orders','scope':'orders','authority':'selected_korean_default',
            'sources':refs,'binding':prepared['source_policy_binding'],'choice':None}
    receipt=POLICY.resolve(engine.r,document(),decisions={'source_text':choice['decision']})
    if receipt!=choice['receipt']:raise ValueError('Baton source choice changed; explicit source review required')
    variant=receipt['values']['variant']
    return {'variant':variant,'scope':VARIANTS[variant],'authority':'explicit_source_conflict',
            'sources':refs,'binding':receipt['source_policy_binding'],'choice':deepcopy(choice)}


def validate(engine,record):
    """Historical choices retain their producer profile; never silently reselect."""
    import source_selection as SELECTION
    if (type(record)is not dict or set(record)!={'variant','scope','authority','sources','binding','choice'}
            or record['variant'] not in VARIANTS or record['scope']!=VARIANTS[record['variant']]
            or record['sources']!=sources(engine)):
        raise ValueError('Baton source contract or retained source hashes changed')
    SELECTION.policy_values(record['binding'],document()['variants'])
    choice=record['choice']
    if choice is None:
        if record['variant']!='korean_orders' or record['authority']!='selected_korean_default':
            raise ValueError('only the selected Korean entry is the native default')
        return record
    decision=choice['decision'];receipt=choice['receipt']
    if (record['authority']!='explicit_source_conflict' or receipt['status']!='PolicyValuesReady'
            or receipt['values']!={'variant':record['variant']} or decision['value']!=record['variant']
            or receipt['source_policy_binding']!=record['binding'] or receipt['selected_id']!=BATON
            or receipt['definition_hash']!=ROOT.fingerprint(document()) or receipt['decision_scope']!=decision['scope']
            or receipt['inputs_hash']!=ROOT.fingerprint({'context':{},'decisions':{'source_text':decision},'state':{}})
            or receipt['decision_evidence']!=[{'input':'source_text','reason':decision['reason'],
                'decision_kind':'source_conflict','scope':decision['scope']}]
            or not isinstance(decision['reason'],str) or not decision['reason'].strip()):
        raise ValueError('Baton source conflict decision lost its scoped actual receipt')
    return record


def _qna_definition():
    return {'rule_id':'hb-finance','source':deepcopy(QNA),
            'values':{'fainted_tag_in_passes_stages':False}}


def _qna_source(engine):
    from source_context import verified_source
    from hashlib import sha256
    text=verified_source(engine.r,QNA,label='selected Tag In Q&A').decode('utf-8').split('\n')[35].rstrip('\r')
    if sha256(text.encode('utf-8')).hexdigest()!=QNA_LINE_SHA:
        raise ValueError('Tag In fainted-recipient Q&A line changed')


def fainted_tag_rule(engine,*,fainted):
    from ruleset import ExcludedRuleSelection
    if type(fainted)is not bool:raise ValueError('actual recall faint observation required')
    try:selected=engine.r._selected_rule('hb-finance')
    except ExcludedRuleSelection:return None
    if selected!='hb-finance':raise ValueError('Q&A replacement requires its own Tag In source contract')
    _qna_source(engine)
    return {'binding':engine.r.bind_source_policy('hb-finance',_qna_definition()),
            'line':36,'line_sha256':QNA_LINE_SHA,'fainted_at_recall':fainted}


def validate_fainted_tag_rule(engine,record):
    if record is None:return
    import source_selection as SELECTION
    _qna_source(engine)
    if (type(record)is not dict or set(record)!={'binding','line','line_sha256','fainted_at_recall'}
            or record['line']!=36 or record['line_sha256']!=QNA_LINE_SHA or type(record['fainted_at_recall'])is not bool
            or SELECTION.policy_values(record['binding'],_qna_definition())!={'fainted_tag_in_passes_stages':False}):
        raise ValueError('Tag In Q&A must retain its actual selected source and faint observation')
