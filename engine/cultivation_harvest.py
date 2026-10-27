"""One shared harvest: eligibility, scoped dice, opportunity and actual products."""
from copy import deepcopy
import common_checks as C,crafting_recipes as Q,cultivation_state as P,cultivation_growth as GROWTH
import crafting_products as PRODUCTS,crafting_resources as R,world_entities as W

BOTANY='input/ch04-trainer-classes.md:2097'


def declaration(value):
    Q._fields(value,('id','source','output','period','roll','soil','contributions','zero_consumes','native'))
    Q._text(value['id']);Q._text(value['source'])
    Q._fields(value['output'],('item_id','key'));Q._text(value['output']['item_id']);Q._text(value['output']['key'])
    period=value['period'];Q._fields(period,('clock','span','limit'))
    if period['clock'] not in ('day','seconds','sessions'):raise ValueError('explicit harvest period clock required')
    C.integer(period['span'],'harvest period span',1);C.integer(period['limit'],'harvest period limit',1)
    roll=value['roll'];Q._fields(roll,('count','sides','offset'))
    C.integer(roll['count'],'harvest dice count',0);C.integer(roll['sides'],'harvest dice sides',1);C.integer(roll['offset'],'harvest yield offset')
    Q._fields(value['soil'],('base','site','fertilizer'))
    if any(type(x) is not bool for x in value['soil'].values()) or type(value['zero_consumes']) is not bool or type(value['native']) is not bool:raise ValueError('explicit harvest contribution and consumption policies required')
    if type(value['contributions']) is not list:raise ValueError('harvest contribution declarations required')
    seen=set()
    for row in value['contributions']:
        Q._fields(row,('id','source','condition','value'));Q._text(row['id']);Q._text(row['source']);Q._condition(row['condition']);C.integer(row['value'],'harvest contribution')
        if row['id'] in seen:raise ValueError('distinct harvest contributions required')
        seen.add(row['id'])
    PRODUCTS._hash(value)
    return deepcopy(value)


def native_definition(rules,plant):
    crop=P.crop(rules,plant['berry'])
    condition={'kind':'all','conditions':[
        {'kind':'owned','fields':['feats'],'names':['최상급 열매','Top Tier Berries']},
        {'kind':'any','conditions':[{'kind':'skill','skill':s,'rank':6,'effective':True} for s in ('일반 지식','생존')]}]}
    return {'id':'native:harvest:'+plant['berry'],'source':P.SOURCE,
            'output':{'item_id':P.item_source(rules,plant['berry']),'key':plant['berry']},
            'period':{'clock':'day','span':1,'limit':1},'roll':{'count':1,'sides':crop['die'],'offset':crop['offset']},
            'soil':{'base':True,'site':True,'fertilizer':True},
            'contributions':[{'id':'botany','source':BOTANY,'condition':condition,'value':1}],
            'zero_consumes':True,'native':True}


def _period(value,at,session,day):
    period=value['period'];epoch={'day':day,'seconds':at,'sessions':session}[period['clock']]
    C.integer(epoch,'actual harvest period clock',0)
    return {'clock':period['clock'],'span':period['span'],'index':epoch//period['span']}


def _usage(plant,value,period,prior):
    used=0;baseline=plant.get('history_start_day')
    if baseline is not None:
        if value['period']['clock']!='day':raise ValueError('observed harvest baseline does not identify this period clock')
        if baseline//value['period']['span']==period['index']:used+=1
    for row in prior:
        if 'harvest_definition' in row:
            if row['harvest_definition']!=value:raise ValueError('retained harvest policy cannot change its period or yield')
            previous=row['period'];spent=row['period_consumed']
        else:
            previous={'clock':value['period']['clock'],'span':value['period']['span'],
                'index':{'day':row['day'],'seconds':row['at'],'sessions':row['session']}[value['period']['clock']]//value['period']['span']}
            spent=True
        if previous['clock']==period['clock'] and previous['index']>period['index']:raise ValueError('harvest period cannot move backward')
        if previous==period and spent:used+=1
    return used


def _legacy_context(engine,actor,plant,environment,soil):
    if type(environment) is not bool:raise ValueError('explicit actual growing environment required')
    C.integer(soil,'actual growing soil')
    protected=plant['planter_slot'] is not None
    if protected:
        selected,common=P.variant(engine.r,plant['planter_policy']);Q._selected(engine,P.PLANTER)
        import crafting_activities as A
        A._inventory(actor,'나무열매플랜터',plant['planter_slot']+1)
        clock='sessions' if selected['maturity_sessions'] is not None else 'seconds'
        if clock=='sessions' and not engine.session_frequency:raise ValueError('actual selected session maturity clock required')
        amount=selected['maturity_sessions'] or selected['maturity_seconds'];base=0;site=common['soil_quality_bonus']
    else:
        clock='seconds';amount=P.policy(engine.r,'cultivation')['maturity_seconds'];base=soil;site=int(plant['soft_soil'])
    now=engine.session_epoch if clock=='sessions' else engine.elapsed_seconds
    start=plant['planted_session'] if clock=='sessions' else plant['planted_at'];mature=now-start>=amount
    day=actor.spec.get('frequency_state',{}).get('day',0)
    bonus,applications=GROWTH.soil_bonus(plant,base+site,day,engine.elapsed_seconds,engine.session_epoch)
    return {'plant_id':plant['id'],'site_id':None,'mature':mature,'clock':clock,'remaining':max(0,start+amount-now),
            'environment_allows_growth':environment,'protected':protected,'ready':mature and (protected or environment),
            'soil_base':base,'site_bonus':site,'fertilizer_bonus':bonus,'fertilizer_applications':applications,'soil_quality':base+site+bonus}


def prepare(engine,actor,plant,value,environment,soil,fixed):
    import physical_planter as PHYSICAL
    PHYSICAL.require_access(engine,actor,plant)
    if engine.encounter_active:raise ValueError('harvest requires its outside-combat procedure')
    if P.harvest_pending(plant):return _pending_harvest(engine,actor,plant)
    if environment is not None and type(environment) is not bool:raise ValueError('actual harvest environment must be an observation')
    if soil is not None:C.integer(soil,'actual harvest soil observation')
    Q._selected(engine,value['source']);Q._selected(engine,value['output']['item_id'])
    if value['native'] and value!=native_definition(engine.r,plant):raise ValueError('native harvest declaration contradicts its retained source')
    if plant.get('harvest_policy') is not None and plant['harvest_policy']!=value:raise ValueError('actual plant retains its selected harvest policy')
    output=value['output']
    if output['item_id']==P.SOURCE:
        if output['item_id']!=P.item_source(engine.r,plant['berry']) or output['key']!=plant['berry']:raise ValueError('native apricorn output identity required')
    else:Q._item_key(engine,output['key'],output['item_id'])
    if 'growth' in plant:
        observed=GROWTH.status(engine,actor,plant['id'],environment_allows_growth=environment,soil_quality=soil)
    else:observed=_legacy_context(engine,actor,plant,environment,soil)
    if not observed['mature']:raise ValueError('actual plant has not matured on its retained clock')
    if not observed['ready']:return C.PendingDecision('GM environment currently prevents plant growth')
    if value['period']['clock']=='sessions' and not engine.session_frequency:raise ValueError('harvest requires an enabled actual session period')
    day=actor.spec.get('frequency_state',{}).get('day',0);C.integer(day,'actual harvest day',0)
    period=_period(value,engine.elapsed_seconds,engine.session_epoch,day)
    if _usage(plant,value,period,plant.get('harvest_history',[]))>=value['period']['limit']:raise ValueError('this plant already used its harvest period limit')
    if fixed is not None:
        if type(fixed) is not list or len(fixed)!=value['roll']['count']:raise ValueError('one explicit harvest observation per die required')
        for face in fixed:C.integer(face,'fixed harvest face',1,value['roll']['sides'])
    contributions=[]
    native_bonus=None
    if value['native']:
        import crafting_activities as A
        native_bonus=A._top_tier(engine,actor,required=False)>=6
    for row in value['contributions']:
        # The reviewed native adapter retains a book-line provenance reference.
        # External contributions bind an actual selected executable identity.
        if not (value['native'] and row['id']=='botany'):Q._selected(engine,row['source'])
        admitted=native_bonus if value['native'] and row['id']=='botany' else Q._observe(engine,actor,row['condition'],set())
        if admitted:contributions.append({'id':row['id'],'source':row['source'],'value':row['value'],'actor_id':actor.entity_id})
    before=C.integer(actor.spec.get('items',{}).get(output['key'],0),'actual harvest output balance',0)
    return {'context':observed,'period':period,'day':day,'contributions':contributions,'before':before}


def harvest(engine,actor,value,*,plant_id,fixed=None,event_id=None,environment_allows_growth=None,soil_quality=None,book_bonus=False):
    W.require_actors(engine,actor);Q._text(plant_id);value=declaration(value)
    import state_grants as GRANTS,roll_context as ROLLS
    def commit(e,c):
        P.validate(c)
        options={'declaration':deepcopy(value),'plant_id':plant_id,'fixed':deepcopy(fixed),
                 'environment_allows_growth':environment_allows_growth,'soil_quality':soil_quality,'book_bonus':book_bonus}
        plan=PRODUCTS.preflight(e,c,'harvest_berry',options,None,event_id)
        if 'replay' in plan:return plan['replay']
        plant=c.spec.get('plants',{}).get(plant_id)
        if not isinstance(plant,dict):raise ValueError('actual owned identified plant required')
        prepared=prepare(e,c,plant,value,environment_allows_growth,soil_quality,fixed)
        if isinstance(prepared,C.PendingDecision):return prepared
        balances=R.snapshot(c);started=e.elapsed_seconds;observed=prepared['context']
        roll=ROLLS.resolve_pool(e,c,plant,purpose='harvest',source=value['source'],fixed=fixed,**value['roll'])
        soil=sum(observed[key] for flag,key in (('base','soil_base'),('site','site_bonus'),('fertilizer','fertilizer_bonus')) if value['soil'][flag])
        feature=sum(row['value'] for row in prepared['contributions'])
        book=__import__('study_books').yield_bonus(e,c,use=book_bonus,production_id=plan['id'])
        book_provider=__import__('study_books').provider(c,'berries') if book else None
        amount=max(0,roll['total']+soil+feature)+book
        if plant.get('harvest_policy') is None:plant['harvest_policy']=deepcopy(value)
        receipt=P.record_harvest(c,plant,{'actor_id':c.entity_id,'day':prepared['day'],'at':e.elapsed_seconds,'session':e.session_epoch,
            'face':roll['faces'][0] if len(roll['faces'])==1 else None,'roll':roll,'soil_base':observed['soil_base'],'site_bonus':observed['site_bonus'],
            'mulch_bonus':observed['fertilizer_bonus'],'mulch_applications':observed['fertilizer_applications'],'fertilizer_count_at_harvest':len(plant.get('mulch_applications',[])),
            'feature_bonus':feature,'feature_source':BOTANY if value['native'] and feature else None,'contributions':prepared['contributions'],
            'protected':observed['protected'],'environment_allows_growth':observed['environment_allows_growth'],'growth_context':observed,
            'harvest_definition':deepcopy(value),'period':prepared['period'],'period_consumed':amount>0 or value['zero_consumes'],
            'production_id':plan['id'],'amount':amount,'inventory_key':value['output']['key'],'inventory_before':prepared['before'],'inventory_after':prepared['before']+amount,
            **({'study_book':book_provider} if book else {})})
        result={'activity':'harvest_berry','plant_id':plant_id,'face':receipt['face'],'faces':deepcopy(roll['faces']),'soil_bonus':soil+feature,'amount':amount,
                'count':amount,'item':value['output']['key'],'item_id':value['output']['item_id'],'recipe_source':value['source'],'protected':observed['protected'],'receipt':deepcopy(receipt)}
        PRODUCTS.materialize(e,c,result,plan)
        sources=[value['source'],value['output']['item_id'],*[x['source'] for x in prepared['contributions']]]
        R.record(e,c,operation='harvest_berry',sources=list(dict.fromkeys(sources)),started_at=started,before=balances,result=result)
        PRODUCTS.publish(e,c,plan,c.spec['resource_transformations'][-1]);P.validate(c)
        return result
    return GRANTS.transition(engine,actor,commit)


def _pending_harvest(engine,actor,plant):
    W.require_actors(engine,actor);P.validate(actor);GROWTH.validate_world(engine,W.actor_index(engine))
    if engine.encounter_active:raise ValueError('harvest requires its outside-combat procedure')
    W.require_usable_object(plant)
    W.require_usable_object(engine._physical_objects[plant['growth']['site_id']])
    return C.PendingDecision('Plant '+plant['berry']+' exists; its species maturity duration, harvest yield and period need an explicit reviewed source policy')


def native_harvest(engine,actor,*,plant_id,environment_allows_growth=True,soil_quality=0,fixed=None,event_id=None,book_bonus=False):
    P.validate(actor);plant=actor.spec.get('plants',{}).get(plant_id)
    if not isinstance(plant,dict):raise ValueError('actual owned planted instance required')
    if P.harvest_pending(plant):return _pending_harvest(engine,actor,plant)
    value=plant.get('harvest_policy')
    if value is None:
        if plant.get('growth',{}).get('definition',{}).get('native_variant','legacy') is None:raise ValueError('data-authored growth needs its declared harvest policy')
        value=native_definition(engine.r,plant)
    if fixed is not None and type(fixed) is not list:fixed=[C.integer(fixed,'fixed native harvest face',1,value['roll']['sides'])]
    return harvest(engine,actor,value,plant_id=plant_id,fixed=fixed,event_id=event_id,environment_allows_growth=environment_allows_growth,soil_quality=soil_quality,book_bonus=book_bonus)


def validate_receipt(actor,plant,row,prior):
    value=declaration(row['harvest_definition'])
    if row.get('actor_id')!=actor.entity_id or value!=plant.get('harvest_policy'):raise ValueError('harvest provider or retained declaration changed')
    if value['native'] and value!=native_definition(actor.r,plant):raise ValueError('native harvest source changed')
    for source in (value['source'],value['output']['item_id']):
        if actor.r._selected_rule(source)!=source:raise ValueError('selected harvest source changed')
    day=C.integer(row.get('day'),'actual harvest day',0);at=C.integer(row.get('at'),'actual harvest time',plant['planted_at'])
    session=C.integer(row.get('session'),'actual harvest session',plant['planted_session'])
    period=_period(value,at,session,day)
    Q._fields(row.get('period'),('clock','span','index'));C.integer(row['period']['span'],'retained harvest period span',1);C.integer(row['period']['index'],'retained harvest period index',0)
    if row.get('period')!=period or _usage(plant,value,period,prior)>=value['period']['limit']:raise ValueError('harvest period limit or clock evidence changed')
    if type(row.get('period_consumed')) is not bool:raise ValueError('explicit actual harvest opportunity consumption required')
    observed=row.get('growth_context',{})
    if type(observed) is not dict or observed.get('plant_id')!=plant['id'] or observed.get('mature') is not True or observed.get('ready') is not True:raise ValueError('actual ready growth context required')
    C.integer(observed.get('remaining'),'actual maturity remaining',0,0)
    protected=observed.get('protected')
    if type(protected) is not bool or row.get('protected')!=protected or row.get('environment_allows_growth')!=observed.get('environment_allows_growth'):raise ValueError('harvest environment evidence changed')
    if not protected and observed.get('environment_allows_growth') is not True:raise ValueError('harvest cannot ignore blocked growth')
    if 'growth' in plant:
        growth=plant['growth'];definition=growth['definition']
        import physical_planter as PHYSICAL
        expected_protected,site=PHYSICAL.receipt_site(plant,observed,at)
        if not GROWTH.mature_at(plant,at,session) or observed.get('site_id')!=growth['site_id'] or protected!=expected_protected or observed.get('clock')!=definition['maturity']['clock']:raise ValueError('harvest preceded actual declared maturity or changed sites')
    else:
        slot=plant['planter_slot']
        if slot is not None:
            selected,common=P.variant(actor.r,plant['planter_policy'])
            clock='sessions' if selected['maturity_sessions'] is not None else 'seconds'
            current=session if clock=='sessions' else at;start=plant['planted_session'] if clock=='sessions' else plant['planted_at']
            amount=selected['maturity_sessions'] or selected['maturity_seconds'];site=common['soil_quality_bonus']
        else:clock='seconds';current=at;start=plant['planted_at'];amount=P.policy(actor.r,'cultivation')['maturity_seconds'];site=int(plant['soft_soil'])
        if current-start<amount or observed.get('clock')!=clock or protected!=(slot is not None):raise ValueError('harvest preceded actual native maturity')
    base=C.integer(row.get('soil_base'),'actual observed harvest soil');C.integer(row.get('site_bonus'),'actual harvest site contribution')
    if row['site_bonus']!=site or observed.get('soil_base')!=base or observed.get('site_bonus')!=site or protected and base!=0:raise ValueError('actual soil/site contribution changed')
    applications=plant.get('mulch_applications',[])
    prefix=C.integer(row.get('fertilizer_count_at_harvest'),'actual fertilizer history prefix',0,len(applications))
    selected=dict(plant,mulch_applications=applications[:prefix])
    bonus,identities=GROWTH.soil_bonus(selected,base+site,day,at,session)
    C.integer(row.get('mulch_bonus'),'actual fertilizer contribution',0)
    if row.get('mulch_bonus')!=bonus or row.get('mulch_applications')!=identities or observed.get('fertilizer_bonus')!=bonus or observed.get('fertilizer_applications')!=identities:raise ValueError('harvest fertilizer contribution or lifetime changed')
    roll=row.get('roll',{})
    if type(roll) is not dict:raise ValueError('actual scoped harvest roll required')
    faces=roll.get('faces')
    for field in ('count','sides','offset','total'):C.integer(roll.get(field),'actual harvest roll '+field)
    if type(faces) is not list or len(faces)!=value['roll']['count']:raise ValueError('actual harvest dice observations required')
    for face in faces:C.integer(face,'actual harvest face',1,value['roll']['sides'])
    expected=dict(purpose='harvest',source=value['source'],actor_id=actor.entity_id,subject_id=plant['id'],**value['roll'],faces=faces,
                  observations=[{'path':str(i),'face':face,'rerolled':False} for i,face in enumerate(faces)],total=sum(faces)+value['roll']['offset'])
    if roll!=expected or row.get('face')!=(faces[0] if len(faces)==1 else None):raise ValueError('harvest scoped roll or arithmetic changed')
    admitted=row.get('contributions')
    if type(admitted) is not list:raise ValueError('actual sourced harvest contributions required')
    declarations={r['id']:r for r in value['contributions']};seen=set()
    for contribution in admitted:
        if type(contribution) is not dict or contribution.get('id') in seen:raise ValueError('distinct actual harvest contributions required')
        declared=declarations.get(contribution.get('id'))
        if declared is None or contribution!=dict(id=declared['id'],source=declared['source'],value=declared['value'],actor_id=actor.entity_id):raise ValueError('harvest contribution changed its source or provider')
        seen.add(contribution['id'])
    feature=sum(x['value'] for x in admitted)
    C.integer(row.get('feature_bonus'),'actual harvest feature contribution')
    if row.get('feature_bonus')!=feature or row.get('feature_source')!=(BOTANY if value['native'] and feature else None):raise ValueError('harvest feature contribution evidence changed')
    soil=sum(observed[k] for flag,k in (('base','soil_base'),('site','site_bonus'),('fertilizer','fertilizer_bonus')) if value['soil'][flag])
    amount=max(0,roll['total']+soil+feature)+__import__('study_books').harvest_record(actor,row)
    C.integer(row.get('amount'),'actual harvest output count',0)
    if observed.get('soil_quality')!=base+site+bonus:raise ValueError('actual harvest growth soil evidence changed')
    before=C.integer(row.get('inventory_before'),'harvest stock before',0);after=C.integer(row.get('inventory_after'),'harvest stock after',0)
    if row.get('amount')!=amount or after-before!=amount or row.get('inventory_key')!=value['output']['key'] or row['period_consumed']!=(amount>0 or value['zero_consumes']):raise ValueError('harvest output/quantity/opportunity evidence changed')
    Q._text(row.get('production_id'))
    return value


def validate_result(actor,record):
    result=record['result'];plant=actor.spec.get('plants',{}).get(result.get('plant_id'),{})
    receipt=result.get('receipt')
    if type(receipt) is not dict or type(receipt.get('sequence')) is not int:raise ValueError('harvest production needs its actual plant receipt')
    rows=plant.get('harvest_history',[]);n=receipt['sequence']
    if not 1<=n<=len(rows) or receipt!=rows[n-1]:raise ValueError('harvest production lost its actual shared plant result')
    if 'harvest_definition' not in receipt:
        # Retained native receipts predate data-authored harvest declarations.
        # Validate their actual plant/yield without inventing a new policy.
        if 'production_id' in receipt:raise ValueError('declared harvest cannot discard its policy evidence')
        P.validate(actor)
        amount=C.integer(result.get('amount'),'retained native harvest amount',0)
        if amount!=receipt['amount'] or result.get('face')!=receipt['face'] or result.get('protected')!=receipt['protected']:
            raise ValueError('retained native harvest result changed')
        expected=[] if not amount else [dict(field='items',key=receipt['inventory_key'],unit='count',before=receipt['inventory_before'],after=receipt['inventory_after'],delta=amount)]
        if record.get('resources')!=expected or record['started_at']!=receipt['at'] or record['completed_at']!=receipt['at']:
            raise ValueError('retained native harvest quantity or time changed')
        return True
    value=validate_receipt(actor,plant,receipt,rows[:n-1])
    if receipt['production_id']!=result.get('production_id') or result.get('amount')!=receipt['amount'] or result.get('count')!=receipt['amount'] or result.get('item')!=value['output']['key'] or result.get('item_id')!=value['output']['item_id'] or result.get('recipe_source')!=value['source']:raise ValueError('harvest production and plant output disagree')
    if record['started_at']!=record['completed_at'] or record['completed_at']!=receipt['at']:raise ValueError('harvest production has invented work time')
    amount=receipt['amount']
    C.integer(result.get('amount'),'actual harvest result amount',0);C.integer(result.get('count'),'actual harvest result count',0)
    expected=[] if not amount else [dict(field='items',key=receipt['inventory_key'],unit='count',before=receipt['inventory_before'],after=receipt['inventory_after'],delta=amount)]
    if record.get('resources')!=expected or value['source'] not in record['sources'] or value['output']['item_id'] not in record['sources']:raise ValueError('harvest production quantity/source receipt changed')
    return True
