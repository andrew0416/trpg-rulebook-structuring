"""Source-proved cost replacement for one actual targeted Order.

The existing Order adapter still owns knowledge, choices, delivery, frequency,
effects and lifetime. This primitive changes only its action payment.
"""
from contextlib import contextmanager
import acquired_features as A
import action_lifecycle as ACTION


def current(engine,actor,source=None):
    row=getattr(engine,'_free_order_scope',None)
    if row is None or row['actor'] is not actor:return None
    unit=engine.r.selection.units[row['feature']]
    if source is not None and source not in (row['feature'],unit['title'],unit.get('eng')):return None
    return row


def pay(engine,actor,source,kind):
    row=current(engine,actor,source)
    if row is None:return kind
    if row['spent']:raise ValueError('one source-proved Free Order payment only')
    row['spent']=True
    return 'free'


def payment(engine,actor,source):
    row=current(engine,actor,source)
    if row is None:return None
    if not row['spent']:raise ValueError('actual Free Order action must precede its receipt')
    return {'kind':'free_order','source':row['source'],'parent':row['parent'],
        'feature':row['feature'],'target_id':row['target'].entity_id}


def validate(engine,actor,target,feature,proof):
    if (type(proof) is not dict or set(proof)!={'kind','source','parent','feature','target_id'}
            or proof['kind']!='free_order' or proof['source']!='feat/채찍질'
            or proof['feature']!=feature or proof['target_id']!=target.entity_id):
        raise ValueError('exact source-proved targeted Free Order payment required')
    parent=getattr(engine,'_native_action_resolutions',{}).get(proof['parent'])
    if (parent is None or parent['actor'] is not actor or parent['source']!='feat/압박'
            or parent['kind']!='feature' or parent['phase']!='producer_returned'):
        raise ValueError('Free Order requires its completed native Press producer')
    facts=[] if parent is None else [fact for trigger in parent['triggers'] if trigger['actor'] is actor
        and trigger['source']=='feat/압박' and trigger['status']=='completed' for fact in trigger['observations']]
    if not any(fact.get('press_target')==target.entity_id and fact.get('whip_order')==feature for fact in facts):
        raise ValueError('Free Order requires its actual Press and Whip occurrence')
    return True


@contextmanager
def granted(engine,actor,target,feature,*,source,parent):
    if getattr(engine,'_free_order_scope',None) is not None:raise ValueError('nested Free Order grant is not the same Order')
    row={'actor':actor,'target':target,'feature':feature,'source':source,'parent':parent,'spent':False}
    engine._free_order_scope=row
    try:
        yield
        if not row['spent']:raise ValueError('selected Order did not execute its native action payment')
    finally:engine._free_order_scope=None


def execute(engine,actor,target,choice,*,source,parent):
    import training_features as TRAINING,moment_of_action as MOMENT
    if isinstance(choice,str):feature=choice;options={}
    elif type(choice) is dict and set(choice)=={'feature','options'} and type(choice['options']) is dict:
        feature=choice['feature'];options=choice['options']
    else:raise ValueError('explicit known targeted Order and native options required')
    if not isinstance(feature,str):raise ValueError('exact selected Order identity required')
    if feature not in engine.r.selection.units:feature=engine.r.selection.resolve_name(feature,('feat/',))
    unit=engine.r.selection.units[feature]
    if not A.owned_rule_count(actor,feature):raise ValueError('actual known Order required')
    if TRAINING.identity(feature) is None and not any('지시' in tag or tag=='Orders' for tag in unit.get('tags',[])):
        raise ValueError('known targeted [Orders] Feature required')
    with granted(engine,actor,target,feature,source=source,parent=parent):
        if feature==MOMENT.FEATURE:
            return MOMENT.use(engine,actor,[target],**options)
        import directive_features as DIRECTIVE
        if feature==DIRECTIVE.FEATURE:
            if set(options)-{'adjustment'}:raise ValueError('native directive adjustment only')
            return engine.manual_feat(actor,feature,target,adjustment=options.get('adjustment'))
        return engine.manual_feat(actor,feature,target,adjustment=options or None)
