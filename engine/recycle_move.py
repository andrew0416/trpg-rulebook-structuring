"""Recycle an admitted native immediate-item effect, never its spent stock."""
from functools import wraps
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import csv
import hashlib
import io
import json
import consumption_execution as PAYMENTS
import world_entities as W

SOURCE='move/리사이클'
RAW={'type':'item_restore','item':'consumed consumable this encounter','reuse_once':True}
CSV_SHA='ab83f872e5eca67a41db7d126b842f0165437e0fa70bb77ddad832a0b7396c93'
ROW_SHA='e6040bad3ad9f9fdde3337483f395a923a33f281b16c14a2b11665f904558fd9'
PDF_SHA='e5e0371031601c3ad0a04056771c17599a2d8826e5a5102ccd37f9b368108907'


def source(rules):
    from source_context import verified_source
    content=verified_source(rules,{'file':'input/db/moves.csv','sha256':CSV_SHA},label='Recycle CSV')
    row=list(csv.reader(io.StringIO(content.decode('utf-8-sig'))))[552]
    digest=hashlib.sha256(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    pdf=Path(rules.root)/'output/source-audit/2026-10-10/ptu-core-1.05.pdf'
    if digest!=ROW_SHA or hashlib.sha256(pdf.read_bytes()).hexdigest()!=PDF_SHA or rules._selected_rule(SOURCE)!=SOURCE:
        raise ValueError('Recycle exact selected source changed')


def native_move(function):
    @wraps(function)
    def run(engine,actor,target,move_id,*args,**options):
        identity=options.pop('recycle_receipt_id',None)
        if identity is None:return function(engine,actor,target,move_id,*args,**options)
        if move_id!=SOURCE or type(identity)is not str or not identity:
            raise ValueError('actual Recycle consumption receipt selection required')
        W.require_actors(engine,actor,target)
        previous=getattr(engine,'_recycle_choice',None)
        choice={'actor_id':actor.entity_id,'receipt_id':identity}
        if previous is not None and previous!=choice:raise ValueError('nested Recycle selection changed')
        engine._recycle_choice=choice
        try:return function(engine,actor,target,move_id,*args,**options)
        finally:
            if previous is None:del engine._recycle_choice
            else:engine._recycle_choice=previous
    return run


def continuation_choice(engine,args):
    selected_payment(engine,args['attacker'])
    return deepcopy(engine._recycle_choice)


@contextmanager
def resume_choice(engine,args,choice):
    if choice is None:
        yield
        return
    if (args['move_id']!=SOURCE or type(choice)is not dict or
            set(choice)!={'actor_id','receipt_id'} or choice['actor_id']!=args['attacker'].entity_id):
        raise ValueError('Recycle continuation lost its actual consumption selection')
    previous=getattr(engine,'_recycle_choice',None)
    if previous is not None and previous!=choice:raise ValueError('Recycle continuation changed selection')
    engine._recycle_choice=deepcopy(choice)
    try:
        selected_payment(engine,args['attacker'])
        yield
    finally:
        if previous is None:del engine._recycle_choice
        else:engine._recycle_choice=previous


def selected_payment(engine,actor):
    choice=getattr(engine,'_recycle_choice',None)
    if not choice or choice['actor_id']!=actor.entity_id:
        raise ValueError('actual Recycle consumption receipt selection required')
    matches=[(payer,row) for payer in W.actors(engine) for identity,row in PAYMENTS.validate(payer).items()
             if identity==choice['receipt_id']]
    if len(matches)!=1:raise ValueError('Recycle needs one actual original consumption receipt')
    payer,row=matches[0]
    if row.get('encounter')!={'active':True,'epoch':engine._party_encounter_epoch}:
        raise ValueError('Recycle item was not actually consumed earlier in this encounter')
    if row['outcome']!='applied' or row.get('native_immediate_result',{}).get('held')!=0:
        raise ValueError('Recycle needs the actual completed item effect, not payment alone')
    import restorative_items as REST
    item=row['item_stock']['item_id']
    if row['item_stock']['count']!=1 or item not in REST.HELD_CONSUMABLES:
        raise ValueError('Recycle of this item family needs its original native effect adapter')
    stock=row['item_stock']
    if stock['kind']=='held_instance':
        obj=getattr(engine,'_physical_objects',{}).get(stock['instance_id'])
        if not obj or 'consumed' not in obj or obj.get('item_rule_id')!=item:
            raise ValueError('Recycle requires the same actually consumed physical item')
    return payer,row


def preflight(engine,actor,target,effect,source_id):
    if source_id!=SOURCE or {k:v for k,v in effect.items() if not k.startswith('_')}!=RAW:
        raise ValueError('Recycle requires its exact sourced one-effect reuse payload')
    source(engine.r)
    W.require_actors(engine,actor,target)
    if actor is not target:raise ValueError('Recycle has the actual user as its sole effect target')
    if not engine.encounter_active or engine.round_start_seconds is None:
        raise ValueError('Recycle requires an actual open encounter')
    payer,row=selected_payment(engine,actor)
    item=row['item_stock']['item_id']
    import restorative_items as REST,food_effects as FOOD,effects as FX
    REST.selected(engine,item)
    if item in REST.X_ITEMS and actor.kind!='pokemon':raise ValueError('recycled X item requires an actual Pokemon recipient')
    pending=REST.preflight(engine,actor,item)
    if pending is not None:raise ValueError('recycled item needs its original unresolved timing policy')
    if item in FOOD.HERBS:FOOD.herbal_preflight(engine,actor,item)
    effects,header=engine.r.item_effects(item)
    if item=='item/만능가루':effects=[{'type':'cure_status','status':'persistent all','target':'target'}]
    FX.preflight_effects(engine,actor,actor,effects,item,consumer='items.use_item')
    return payer,row,effects,header


def apply(engine,actor,target,effect,context):
    payer,row,effects,header=preflight(engine,actor,target,effect,context.get('source_id'))
    token=context.get('effect_receipt')
    occurrence=context.get('effect_occurrence')
    completion=context.get('move_completion')
    import effect_contracts as CONTRACTS
    CONTRACTS.validate_receipt(engine,token,SOURCE,occurrence,actor,target,effect)
    native=getattr(engine,'_move_completions',{}).get(completion)
    if native is None or native['actor'] is not actor or native['move_id']!=SOURCE:
        raise ValueError('Recycle requires its actual native Move completion')
    if any(event['dispatch_receipt'] is token for event in row.get('reuses',[])):
        raise ValueError('this native Recycle occurrence already reused its effect once')
    import items as ITEMS,restorative_items as REST
    result=(1,0) if header['id'] in REST.X_ITEMS and REST.special_apply(engine,actor,header['id']) else ITEMS.apply_immediate_effects(
        engine,actor,actor,header['id'].split('/',1)[1],effects,header)
    if result[1]:raise ValueError('Recycle original item effect did not complete')
    row.setdefault('reuses',[]).append({'actor_id':actor.entity_id,'dispatch_receipt':token,
        'occurrence':occurrence,'completion_id':completion,'result':list(result),'at':engine.elapsed_seconds})
    engine.log('    리사이클: 소비된 원본 효과 1회 재사용; 도구는 소모 상태 유지',SOURCE)
    return {'payment_id':row['receipt_id'],'item_id':header['id'],'result':list(result)}


def validate_world(engine,index):
    seen=set()
    for payer in index.values():
        for row in PAYMENTS.validate(payer).values():
            for event in row.get('reuses',[]):
                token=event.get('dispatch_receipt')
                try:
                    receipt=getattr(engine,'_effect_dispatch_receipts',{}).get(token)
                    completion=getattr(engine,'_move_completions',{}).get(event.get('completion_id'))
                    duplicate=token in seen
                except TypeError:raise ValueError('Recycle requires native dispatcher and Move identities')
                actor=index.get(event.get('actor_id'))
                if duplicate or receipt is None or completion is None or actor is None:
                    raise ValueError('Recycle reuse requires one actual native occurrence')
                if receipt['source_id']!=SOURCE or receipt['actor'] is not actor or receipt['target'] is not actor or receipt['occurrence']!=event.get('occurrence') or completion['actor'] is not actor or completion['move_id']!=SOURCE:
                    raise ValueError('Recycle reuse provenance changed')
                if row['outcome']!='applied' or row.get('encounter',{}).get('active') is not True:
                    raise ValueError('Recycle original consumption lost its actual completed outcome')
                seen.add(token)
    return True
