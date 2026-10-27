"""Native Telepathy consumes common communication, observation and scoped checks."""
from copy import deepcopy
from pathlib import Path
import json
import crafting_recipes as Q,common_checks as C,skill_modifiers as S
import perception_observe as O,perception_communicate as M
import resolution_transaction as TX
from source_context import verified_source

SOURCE='capability/텔레파시'
EDGE='poke_edge/장거리-판독'
CAPABILITIES=('텔레파시','Telepath','Telepathy',SOURCE)
ALIASES={EDGE:EDGE,'장거리 판독':EDGE,'Far Reading':EDGE,'FarReading':EDGE}


def policy(rules):
    value=json.loads((Path(rules.root)/'data/telepathy-policy.json').read_text(encoding='utf-8'))
    verified_source(rules,value['source'],label='Telepathy')
    if value.get('rule_id')!=SOURCE or rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected native Telepathy source required')
    declaration=M.declaration(value['declaration'])
    if declaration['source']!=SOURCE:raise ValueError('native Telepathy declaration identity required')
    return value


def _previous_policy(rules):
    value=policy(rules);body=M._body(value['declaration'])
    if body['retry']['penalty'].get('stacking')!='cumulative':return None
    body['retry']['penalty'].pop('stacking')
    correction=value.get('source_correction',{})
    if TX.request_fingerprint(body)==correction.get('previous_declaration_sha256'):return body
    return None


def accepts_stored_policy(rules,body):
    # Only the exact pre-correction declaration is historical, never a new option.
    return body==M._body(policy(rules)['declaration']) or body==_previous_policy(rules)


def replay_intent(engine,intent,receipt,field):
    if receipt is None or receipt['intent']==TX.request_fingerprint(intent):return intent
    previous=_previous_policy(engine.r)
    if previous is None or intent[field]!=M._body(policy(engine.r)['declaration']):return intent
    legacy=dict(intent,**{field:previous})
    return legacy if receipt['intent']==TX.request_fingerprint(legacy) else intent


def owns(actor):return bool({S.key(x) for x in CAPABILITIES}&{S.key(x) for x in M._current(actor,'capabilities')})


def prepare(engine,owner,other,value,operation,thought):
    expected=policy(engine.r)['declaration']
    if M._body(expected)!=M._body(value):raise ValueError('native Telepathy retains its selected source contract')
    if operation not in ('send','read','offer'):raise ValueError('supported Telepathy operation required')
    if operation=='read':
        if thought is not None:raise ValueError('reading cannot supply invented thought content')
    else:Q._text(thought)
    if operation=='send':
        if not owns(other):raise ValueError('Telepathy projection requires another actual telepath')
        if projection_maximum(owner)<1:raise ValueError('actual Focus rank permits no projection targets')
    if operation=='offer' and other.kind!='trainer':raise ValueError('only an actual trainer can offer thoughts without Telepathy')


def projection_maximum(actor):
    import arithmetic as R
    return R.evaluate('floor(rank/2)',{'rank':S.effective_rank(actor.r,actor,'집중')})


def read_block(engine,target,operation):
    if operation!='read':return None
    for block in policy(engine.r)['read_blockers']:
        if M._owns(target,block['field'],block['names']):
            Q._selected(engine,block['source']);return block['source']
    return None


def deliver(engine,owner,other,thought,operation):
    if operation=='read':
        fact=O.current_thought(other)
        return {'source':SOURCE,'sender_id':other.entity_id,'recipient_id':owner.entity_id,
                'surface_thought':None if fact is None else fact['text'],
                'thought_revision':None if fact is None else fact['revision'],
                'status':'unknown' if fact is None else 'observed'}
    sender,recipient=(other,owner) if operation=='offer' else (owner,other)
    return {'source':SOURCE,'sender_id':sender.entity_id,'recipient_id':recipient.entity_id,'text':thought}


def attempt(engine,owner,other,operation,unwilling):
    import iron_mind as I
    if policy(engine.r)['read_notice_source']!=I.SOURCE:raise ValueError('native read-attempt consumer source changed')
    notice=I.notice(engine,owner,other,operation)
    return {'source':SOURCE,'kind':'telepathy_read_attempt' if operation=='read' else 'telepathy_projection_attempt',
            'owner_id':owner.entity_id,'target_id':other.entity_id,'at':engine.elapsed_seconds,
            'unwilling':unwilling,'supernatural_trace':unwilling,'notice':notice}


def validate_result(engine,result,*,source=SOURCE,cumulative=False):
    modifier=C.integer(result.get('retry_modifier'),'Telepathy retry modifier',maximum=0)
    penalty=policy(engine.r)['declaration']['retry']['penalty'] if source==SOURCE else {'modifier':-3,'stacking':'cumulative' if cumulative else 'single'}
    if modifier%penalty['modifier'] or penalty.get('stacking','single')=='single' and modifier not in (penalty['modifier'],0):raise ValueError('source-defined Telepathy retry modifier required')
    operation=result.get('operation')
    if operation not in ('read','send','offer'):raise ValueError('actual Telepathy operation receipt required')
    event=result.get('event')
    if event is not None:
        Q._fields(event,('source','kind','owner_id','target_id','at','unwilling','supernatural_trace','notice'))
        if event['source']!=source or event['owner_id']!=result['sender_id'] or event['target_id']!=result['recipient_id']:raise ValueError('actual Telepathy attempt endpoints required')
        if event['kind']!=('telepathy_read_attempt' if operation=='read' else 'telepathy_projection_attempt'):raise ValueError('actual Telepathy attempt kind required')
        C.integer(event['at'],'Telepathy attempt time',0,engine.elapsed_seconds)
        if type(event['unwilling']) is not bool or event['supernatural_trace'] is not event['unwilling'] or operation=='offer' and event['unwilling']:raise ValueError('actual unwilling attempt trace required')
        notice=event['notice']
        if notice is not None:
            import iron_mind as I
            I.policy(engine.r)
            Q._fields(notice,('source','recipient_id','kind','reader_id','at'))
            if operation!='read' or notice!={'source':policy(engine.r)['read_notice_source'],'recipient_id':event['target_id'],'kind':'telepathy_read_attempt','reader_id':event['owner_id'],'at':event['at']}:raise ValueError('actual sourced read attempt notice required')
    message=result.get('message')
    if result['status']=='delivered':
        if event is None:raise ValueError('Telepathy delivery lacks actual attempt')
        a,b=(result['recipient_id'],result['sender_id']) if operation in ('read','offer') else (result['sender_id'],result['recipient_id'])
        if type(message) is not dict or message.get('source')!=source or message.get('sender_id')!=a or message.get('recipient_id')!=b:raise ValueError('actual Telepathy message endpoints required')
        if operation=='read':
            Q._fields(message,('source','sender_id','recipient_id','surface_thought','thought_revision','status'))
            if message['status']=='unknown':
                if message['surface_thought'] is not None or message['thought_revision'] is not None:raise ValueError('unknown thought cannot contain invented information')
            elif message['status']=='observed':Q._text(message['surface_thought']);C.integer(message['thought_revision'],'read thought revision',1)
            else:raise ValueError('bounded observed thought status required')
        else:Q._text(message.get('text'))


def read(engine,reader,target,*,request_id,roll_options=None):
    return M.send(engine,reader,target,policy(engine.r)['declaration'],None,request_id=request_id,roll_options=roll_options,operation='read')


def project(engine,sender,recipients,thought,*,request_id,roll_options=None):
    return M.send_many(engine,sender,recipients,policy(engine.r)['declaration'],thought,
                       request_id=request_id,maximum=projection_maximum(sender),roll_options=roll_options)


def offer(engine,trainer,telepath,thought,*,request_id):
    # The ability owner receives an explicit trainer offer. Its actual Focus
    # determines range; this grants no Telepathy capability to the trainer.
    return M.send(engine,telepath,trainer,policy(engine.r)['declaration'],thought,request_id=request_id,operation='offer')


def events(engine,actor=None,*,notices_only=False):
    import world_entities as W
    if actor is not None:W.require_actors(engine,actor)
    M.validate_world(engine,W.actor_index(engine));result=[]
    for row in M._state(engine)['requests'].values():
        event=row['result'].get('event')
        if event is None or event.get('source')!=SOURCE:continue
        if notices_only:
            import iron_mind as I
            item=None if event['notice'] is None else I.information(engine.r,event['notice'])
        else:item=event
        if item is None:continue
        if actor is not None and (item['recipient_id']!=actor.entity_id if notices_only else actor.entity_id not in (event['owner_id'],event['target_id'])):continue
        result.append(deepcopy(item))
    return result
