"""C09-004: observed merchant ball stock feeds the existing purchase owner."""
from copy import deepcopy
import common_checks as C
import campaign_rewards as REWARDS
import state_grants as GRANTS

SOURCE='ch09-equipment/트레이너의-필수품/몬스터볼-표'
REFERENCE={'file':'input/ch09-equipment.md','sha256':'b5aeb6b82af4b05fe0b369368f8b0181ed3b1d22079e8a86a1c4248e6cbf92d2'}
KIND='ball_shop'
PRICES={'item/몬스터볼-2':250,'item/슈퍼볼':400,'item/하이퍼볼':800}
PRICES.update({'item/'+name:800 for name in ('사파리볼','레벨볼','루어볼','문볼','프렌드볼',
    '러브러브볼','헤비볼','스피드볼','컴퍼티션볼','프리미어볼','리피트볼','타이머볼',
    '네스트볼','네트볼','다이브볼','럭셔리볼','힐볼','퀵볼','다크볼','프레셔스볼','파크볼')})
BALLS=(*PRICES,'item/마스터볼')


def source(rules):
    selected=rules.select_source_definition(SOURCE,source=REFERENCE)
    bounds=selected['source'].get('lines',())
    if selected['selected_id']!=SOURCE or len(bounds)!=2 or not bounds[0]<=29<=bounds[1]:
        raise ValueError('selected ball price and availability source needs its own policy')
    return selected


def ball(engine,key):
    name,price=REWARDS.item(engine,key)
    header=engine.r.item_effects(key)[1]
    uid=header.get('id')
    if uid not in BALLS:return name,None,price
    if header.get('use')!='ball':raise ValueError('selected capture ball definition changed')
    if uid=='item/마스터볼':raise ValueError('Master Ball is not sold; its value is not a shop price')
    return name,uid,PRICES[uid]


def observe(engine,actor,*,event_id,merchant,stock,reason,unit_prices=None):
    REWARDS.base(engine,actor,reward_source=False)
    REWARDS.text(event_id,'actual shop observation identity')
    REWARDS.text(merchant,'actual merchant');REWARDS.text(reason,'GM observed stock and adopted prices')
    if event_id in REWARDS.events(engine):raise ValueError('shop observation event already used')
    selection=source(engine.r)
    if not isinstance(stock,dict) or not stock:raise ValueError('explicit observed ball quantities required')
    if unit_prices is not None and (not isinstance(unit_prices,dict) or set(unit_prices)!=set(stock)):
        raise ValueError('observed prices must identify every observed ball')
    counts={};prices={};identities={}
    for key,count in stock.items():
        C.integer(count,'observed whole ball stock',0)
        name,uid,catalogue=ball(engine,key)
        if uid is None:raise ValueError('actual selected capture ball required')
        if name in counts:raise ValueError('same canonical ball repeated')
        price=catalogue if unit_prices is None else unit_prices[key]
        C.integer(price,'observed point unit price',0)
        counts[name]=count;prices[name]=price;identities[name]=uid
    row={'kind':KIND,'source':SOURCE,'selection':selection,'observer':actor.spec['id'],
         'merchant':merchant,'stock':counts,'unit_prices':prices,'item_ids':identities,
         'reason':reason,'status':'observed'}
    REWARDS.put(engine,event_id,row)
    return deepcopy(row)


def prepare(engine,merchant,items,observation_id,unit_prices,price_currency):
    selection=source(engine.r)
    if not isinstance(items,dict) or not items:raise ValueError('actual purchased inventory required')
    requested=[]
    for key,count in items.items():
        C.integer(count,'purchased count',1)
        requested.append((key,count,*ball(engine,key)))
    latest=[key for key,value in REWARDS.events(engine).items()
            if value.get('kind')==KIND and value.get('merchant')==merchant]
    if observation_id is None:
        if not latest:return C.PendingDecision('GM must observe this merchant ball stock and prices')
        observation_id=latest[-1]
    REWARDS.text(observation_id,'actual ball shop observation identity')
    row=REWARDS.events(engine).get(observation_id)
    if row is None:return C.PendingDecision('GM must observe this merchant ball stock and prices')
    if row.get('kind')!=KIND or row.get('source')!=SOURCE or row.get('merchant')!=merchant:
        raise ValueError('actual ball observation for this merchant required')
    if not latest or latest[-1]!=observation_id:raise ValueError('latest actual merchant stock observation required')
    if row.get('selection')!=selection or row.get('status')!='observed':
        raise ValueError('observed ball source selection changed')
    if price_currency=='dollar' and unit_prices is None:
        raise ValueError('explicit GM agreed dollar unit prices required')
    counts={};prices={}
    for key,count,name,uid,catalogue in requested:
        if uid is None:
            prices[key]=catalogue
            continue
        if name in counts:raise ValueError('same canonical ball repeated')
        if name not in row['stock']:
            return C.PendingDecision('GM must observe availability and quantity of the requested ball')
        if row['item_ids'].get(name)!=uid:raise ValueError('observed ball identity changed')
        available=C.integer(row['stock'][name],'actual remaining merchant stock',0)
        if available<count:raise ValueError('insufficient observed merchant ball stock')
        counts[name]=count;prices[key]=C.integer(row['unit_prices'][name],'observed point unit price',0)
    if not counts:raise ValueError('ball stock selection requires an actual purchased ball')
    return {'counts':counts,'unit_prices':prices if unit_prices is None else unit_prices,
            'observation_id':observation_id}


def purchase(engine,actor,*,ball_shop_id,**options):
    items=options['items']
    has_ball=isinstance(items,dict) and any(engine.r.item_effects(key)[1].get('id') in BALLS for key in items)
    if not has_ball and ball_shop_id is None:return REWARDS._purchase(engine,actor,**options)
    REWARDS.fresh(engine,actor,options['event_id'])
    REWARDS.text(options['merchant'],'actual merchant');REWARDS.text(options['reason'],'actual purchase/price agreement')
    def plan(e):return prepare(e,options['merchant'],options['items'],ball_shop_id,
                              options.get('unit_prices'),options.get('price_currency','point'))
    prepared=plan(engine)
    if isinstance(prepared,C.PendingDecision):return prepared
    def apply(e,payer):
        if plan(e)!=prepared:raise ValueError('observed merchant stock changed before purchase')
        purchase_options=dict(options,unit_prices=prepared['unit_prices'])
        receipt=REWARDS._purchase(e,payer,**purchase_options)
        observation_id=prepared['observation_id']
        observation=REWARDS.events(e)[observation_id]
        before={name:observation['stock'][name] for name in prepared['counts']}
        for name,count in prepared['counts'].items():observation['stock'][name]-=count
        receipt['ball_shop']={'source':SOURCE,'observation_id':observation_id,
            'stock_before':before,'stock_after':{name:observation['stock'][name] for name in before},
            'observed_unit_prices':{name:observation['unit_prices'][name] for name in before},
            'price_basis':'observed' if options.get('unit_prices') is None else 'GM_agreed'}
        REWARDS.events(e)[options['event_id']]['ball_shop']=deepcopy(receipt['ball_shop'])
        return deepcopy(receipt)
    return GRANTS.transition(engine,actor,apply)
