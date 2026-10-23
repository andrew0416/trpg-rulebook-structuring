"""Actual stock payment originals and links to native outcomes.

No effect, growth or inventory balance is duplicated here. Result addresses are
owned by the domain that commits them; payment alone never proves application.
"""
from copy import deepcopy
import common_checks as C

KEY='stock_consumption_receipts'


def validate(actor):
    rows=actor.spec.get(KEY,{})
    if type(rows) is not dict:raise ValueError('native stock receipt mapping required')
    for n,(identity,row) in enumerate(rows.items(),1):
        if type(row) is not dict or identity!=actor.entity_id+':stock:'+str(n) or row.get('receipt_id')!=identity:
            raise ValueError('actual stock receipt identity required')
        stock=row.get('item_stock')
        if row.get('user_id')!=actor.entity_id or type(stock) is not dict or type(stock.get('item_id')) is not str:
            raise ValueError('stock receipt belongs to another payer')
        C.integer(row.get('at'),'stock payment time',0)
        C.integer(stock.get('count'),'paid stock count',1)
        if row.get('outcome') not in ('paid','applied','no_effect','loaded') or type(row.get('results')) is not list:
            raise ValueError('explicit stock application outcome required')
    return rows


def issue(engine, actor, paid):
    rows=validate(actor)
    identity=actor.entity_id+':stock:'+str(len(rows)+1)
    actor.spec.setdefault(KEY,{})[identity]={'receipt_id':identity,'user_id':actor.entity_id,
        'at':engine.elapsed_seconds,'item_stock':paid,'outcome':'paid','target_id':None,'results':[]}
    return paid


def finish(actor, paid, *, target_id, outcome, results=()):
    rows=validate(actor)
    matches=[r for r in rows.values() if r['item_stock'] is paid]
    if len(matches)!=1:
        raise ValueError('actual original stock payment required')
    row=matches[0]
    if outcome not in ('applied','no_effect','loaded') or type(target_id) is not str or not target_id:
        raise ValueError('actual application target and outcome required')
    if not isinstance(results,(list,tuple)) or any(type(r) is not dict or not r.get('kind') or not r.get('id') for r in results):
        raise ValueError('identified native result addresses required')
    proposed={'target_id':target_id,'outcome':outcome,'results':deepcopy(list(results))}
    if row['outcome']!='paid':
        if any(row[k]!=v for k,v in proposed.items()):raise ValueError('stock payment already has another outcome')
        return row
    row.update(proposed)
    return row
