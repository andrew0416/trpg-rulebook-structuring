"""Atomic trainer Feature acquisition with immutable source-specific evidence.

The receipt schema is intentionally value-agnostic.  A source adapter proves
and canonicalizes selected values before this module commits ownership.  The
Personal Tutor adapter below is the first consumer and records move-specific
evidence without making the receipt store itself a move ledger.

Removal and reacquisition are outside this contract.  Callers must select the
explicit unresolved lifecycle policy; no ownership row is silently recycled.
No-choice registrations use existing owned sources and their retraining archive.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import csv
import json


LEDGER_KEY = "trainer_feature_acquisition_receipts"
PROJECTION_KEY = "trainer_feature_selection_projection"
SCHEMA = 1
PERSONAL_TUTOR = "feat/개인-지도"
PERSONAL_TUTOR_ADAPTER = "trainer-feature/personal-tutor-moves/v1"
MARTIAL_ARTIST = "class/무술가"
MARTIAL_PREREQUISITE = "edge/기본-무술"
MARTIAL_ARTIST_ADAPTER = "trainer-feature/martial-artist-ability/v1"
STATIC_FEATURES = {
    __import__('type_sync').FEATURE: {'clause_id': __import__('type_sync').BOOK,
        'span': [524, 531], 'catalog_span': [524, 531], 'definition': __import__('type_sync').DEFINITION,
        'minimum_level': 0, 'skill': None,
        'source': {'file': 'input/supp-fantasy.md', 'sha256': __import__('type_sync').BOOK_SHA}},
    __import__('psionic_sight').FEATURE: {'clause_id': __import__('psionic_sight').BOOK,
        'span': [903, 907], 'catalog_span': [903, 907], 'definition': __import__('psionic_sight').DEFINITION,
        'minimum_level': 0, 'skill': None,
        'source': {'file': 'input/ch03-skills-edges-feats.md', 'sha256': __import__('psionic_sight').BOOK_SHA}},
    __import__('type_expertise').FEATURE: {'clause_id': 'C03-142', 'span': [863, 867],
        'catalog_span': [863, 867], 'definition': __import__('type_expertise').DEFINITION,
        'ranked': True, 'max_rank': 2, 'minimum_level': 9, 'skill': None,
        'source': {'file': 'input/ch03-skills-edges-feats.md', 'sha256': __import__('type_expertise').BOOK_SHA256}},
    **{u:{'clause_id':d['clause_id'],'span':d['span'],'catalog_span':d['catalog_span'],'class_template':'class/저글러','definition':d,'minimum_level':0,'skill':None,'source':d.get('source',{'file':'input/ch04-trainer-classes.md','sha256':__import__('juggler').SOURCE_SHA256})} for u,d in __import__('juggler').DEFINITIONS.items()},
    **{u:{'clause_id':d['clause_id'],'span':d['span'],'catalog_span':d['catalog_span'],'class_template':__import__('ace_trainer').CLASS,'definition':d,'minimum_level':0,'skill':None,'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('ace_trainer').SOURCE_SHA256}} for u,d in __import__('ace_trainer').DEFINITIONS.items()},
    **{u:{'clause_id':'input/ch03-skills-edges-feats.md:'+str(s[0])+'-'+str(s[1]),'span':list(s),'minimum_level':0,'skill':None,'source':{'file':'input/ch03-skills-edges-feats.md','sha256':'b94e43349794836391501f9aac10009d20746bf946ea0c4b5ff3adf85e982d23'}} for u,s in __import__('ace_trainer').TRAINING.items() if u!='feat/영감성-훈련'},
    **{u:{'clause_id':d['clause_id'],'span':d['span'],'catalog_span':d['catalog_span'],'class_template':'class/공간도약자','definition':d,'minimum_level':0,'skill':None,'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('warper').SOURCE_SHA256}} for u,d in __import__('warper').DEFINITIONS.items()},
    **{u:{'clause_id':d['clause_id'],'span':d['span'],'catalog_span':d['catalog_span'],'class_template':'class/텔레파시능력자','definition':d,'minimum_level':0,'skill':None,'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('telepath').SOURCE_SHA256}} for u,d in __import__('telepath').DEFINITIONS.items()},
    **{u:{'clause_id':d['clause_id'],'span':d['span'],'catalog_span':d['catalog_span'],'class_template':'class/염동력자','definition':d,'minimum_level':0,'skill':None,'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('telekinetic').SOURCE_SHA256}} for u,d in __import__('telekinetic').DEFINITIONS.items()},
    **{u:{'clause_id':d['clause_id'],'span':d['span'],'catalog_span':d['catalog_span'],'class_template':'class/현자','definition':d,'minimum_level':0,'skill':None,'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('sage').SOURCE_SHA256}} for u,d in __import__('sage').DEFINITIONS.items()},
    **{u:{'clause_id':d['clause_id'],'span':d['span'],'catalog_span':d['catalog_span'],'class_template':'class/오라클','definition':d,'minimum_level':0,'skill':None,'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('oracle').SOURCE_SHA256}} for u,d in __import__('oracle').DEFINITIONS.items()},
    **{u:{'clause_id':d['clause_id'],'span':d['span'],'catalog_span':d['catalog_span'],'class_template':'class/닌자','definition':d,'minimum_level':0,'skill':None,'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('ninja').SOURCE_SHA256}} for u,d in __import__('ninja').DEFINITIONS.items()},
    **{u:{'clause_id':d['clause_id'],'span':d['span'],'catalog_span':d['catalog_span'],'class_template':'class/오컬트마니아','definition':d,'ranked':d['ranked'],'max_rank':3,'minimum_level':0,'skill':None,'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('hex_maniac').SOURCE_SHA256}} for u,d in __import__('hex_maniac').DEFINITIONS.items()},
    **{u:{'clause_id':d['clause_id'],'span':d['span'],'catalog_span':d['catalog_span'],'class_template':'class/교감자','definition':d,'minimum_level':0,'skill':None,'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('channeler').SOURCE_SHA256}} for u,d in __import__('channeler').DEFINITIONS.items()},
    **{u:{'clause_id':d['clause_id'],'span':d['span'],'catalog_span':d['catalog_span'],'class_template':'class/파동술사','definition':d,'ranked':d['ranked'],'max_rank':2,'minimum_level':0,'skill':None,'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('aura_guardian').SOURCE_SHA256}} for u,d in __import__('aura_guardian').DEFINITIONS.items()},
    **{u:{"clause_id":d["clause_id"],"span":d["span"],"catalog_span":d["catalog_span"],"class_template":"class/텀블러","definition":d,"minimum_level":0,"skill":None,"source":{"file":"input/ch04-trainer-classes.md","sha256":__import__("tumbler").SOURCE_SHA256}} for u,d in __import__("tumbler").DEFINITIONS.items()},
    **{u:{"clause_id":d["clause_id"],"span":d["span"],"catalog_span":d["catalog_span"],"class_template":"class/망나니","definition":d,"minimum_level":0,"skill":None,"source":{"file":"input/ch04-trainer-classes.md","sha256":__import__("roughneck").SOURCE_SHA256}} for u,d in __import__("roughneck").DEFINITIONS.items()},
    **{u:{'clause_id':d['clause_id'],'span':d['span'],'catalog_span':d['catalog_span'],'class_template':'class/무술가','definition':d,'ranked':d.get('ranked',False),'max_rank':d.get('max_rank',2),'move_choices':d.get('move_choices',False),'minimum_level':0,'skill':None,'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('martial_artist')._data['source_sha256']}} for u,d in __import__('martial_artist').DEFINITIONS.items()},
    **{u:{"clause_id":d["clause_id"],"span":d["span"],"catalog_span":d["catalog_span"],"class_template":"class/선동가","definition":d,"minimum_level":0,"skill":None,"source":{"file":"input/ch04-trainer-classes.md","sha256":__import__("provocateur").SOURCE_SHA256}} for u,d in __import__("provocateur").DEFINITIONS.items()},
    **{u:{"clause_id":d["clause_id"],"span":d["span"],"catalog_span":d["catalog_span"],"class_template":"class/음악가","definition":d,"minimum_level":0,"skill":None,"branch":u=="feat/음악-재능","source":{"file":"input/ch04-trainer-classes.md","sha256":__import__("musician").SOURCE_SHA256}} for u,d in __import__("musician").DEFINITIONS.items()},
    **{uid:{'clause_id':('C04-104' if uid==__import__('rogue').DIRTY else 'input/ch04-trainer-classes.md:'+str(d['span'][0])+'-'+str(d['span'][1])),
        'span':list(d['span']),'catalog_span':list(d.get('catalog_span',d['span'])),
        'class_template':'class/로그','definition':d,'minimum_level':0,'skill':None,'branch':uid==__import__('rogue').UNDERHAND,
        'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('rogue').SOURCE_SHA256}}
        for uid,d in __import__('rogue').DEFINITIONS.items()},
    **{u:{'clause_id':('C04-055' if u=='class/타입-에이스' else 'input/ch04-trainer-classes.md:'+str(d['span'][0])+'-'+str(d['span'][1])),
        'span':d['span'],'catalog_span':d['catalog_span'],'class_template':'class/타입-에이스','definition':d,
        'minimum_level':0,'skill':None,'branch':d.get('branch') is True,
        'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('type_ace')._data['source_sha256']}}
        for u,d in __import__('type_ace').DEFINITIONS.items()},
    **{u:{'clause_id':d['clause_id'],'span':list(d['span']),'catalog_span':list(d['catalog_span']),'class_template':'class/기록자','definition':d,
        'minimum_level':0,'skill':None,'ranked':u=='feat/자료보관-훈련',
        'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('chronicler')._data['source_sha256']}}
        for u,d in __import__('chronicler').DEFINITIONS.items()},
    **{u:{'clause_id':d['clause_id'],'span':list(d['span']),'catalog_span':list(d['catalog_span']),'class_template':'class/패셔니스타','definition':d,
        'minimum_level':0,'skill':None,
        'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('fashionista')._data['source_sha256']}}
        for u,d in __import__('fashionista').DEFINITIONS.items()},
    **{u:{'clause_id':d['clause_id'],'span':list(d['span']),'catalog_span':list(d['catalog_span']),'class_template':'class/헌터','definition':d,
        'minimum_level':0,'skill':None,'branch':d.get('branch') is True,
        'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('hunter')._data['source_sha256']}}
        for u,d in __import__('hunter').DEFINITIONS.items()},
    **{u:{'clause_id':d['clause_id'],'span':list(d['span']),'catalog_span':list(d['catalog_span']),'class_template':'class/운동선수','definition':d,
        'minimum_level':0,'skill':None,
        'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('athlete')._data['source_sha256']}}
        for u,d in __import__('athlete').DEFINITIONS.items()},
    **{uid:{'clause_id':('C04-049' if uid=='class/스타일-전문가' else 'input/ch04-trainer-classes.md:'+str(span[0])+'-'+str(span[1])),
        'span':list(span),'catalog_span':list(__import__('style_expert').CATALOG_SPANS.get(uid,span)),
        'class_template':'class/스타일-전문가','definition':__import__('style_expert').DEFINITIONS[uid],
        'minimum_level':0,'skill':None,'branch':uid in ('class/스타일-전문가','feat/스타일-플로리시','feat/스타일-엔트레인먼트'),
        'ranked':uid in __import__('style_expert').RANKED.values(),
        'source':{'file':'input/ch04-trainer-classes.md','sha256':'a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'}}
        for uid,span in __import__('style_expert').FEATURES.items()},
    **{uid:{'clause_id':('C04-047' if uid=='class/스탯-에이스' else 'C04-048' if uid=='feat/스탯-전형' else 'input/ch04-trainer-classes.md:'+str(span[0])+'-'+str(span[1])),
        'span':list(span),'catalog_span':([1086,1086] if uid=='class/스탯-에이스' else list(span)),
        'class_template':'class/스탯-에이스','definition':__import__('stat_ace').DEFINITIONS[uid],
        'minimum_level':0,'skill':None,'branch':True,'source':{'file':'input/ch04-trainer-classes.md',
        'sha256':'a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'}}
        for uid,span in __import__('stat_ace').FEATURES.items()},
    **{uid:{'clause_id':({'class/감독관':'C04-040','feat/빠른-치유':'C04-041','feat/밀고나가':'C04-042','feat/치명적인-장기말':'C04-043'}.get(uid,'input/ch04-trainer-classes.md:'+str(span[0])+'-'+str(span[1]))),
        'span':list(span),'catalog_span':([948,948] if uid=='class/감독관' else list(span)),
        'class_template':__import__('taskmaster').CLASS,'definition':__import__('taskmaster').DEFINITIONS[uid],
        'minimum_level':0,'skill':None,'source':{'file':'input/ch04-trainer-classes.md',
        'sha256':'a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'}}
        for uid,span in __import__('taskmaster').FEATURES.items()},
    **{uid:{'clause_id':row['clause_id'],'span':list(row['span']),'catalog_span':list(row['catalog_span']),
        'class_template':'class/요리사','definition':row,'minimum_level':0,'skill':None,
        'source':{'file':'input/ch04-trainer-classes.md','sha256':'a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'}}
        for uid,row in __import__('chef_cooking').STATIC_DEFINITIONS.items()},
    **{uid:{'clause_id':row['clause_id'],'span':list(row['span']),'catalog_span':list(row['catalog_span']),
        'class_template':'class/생존가','definition':row,'minimum_level':0,'skill':None,'ranked':row.get('ranks')==2,
        'source':{'file':'input/ch04-trainer-classes.md','sha256':'a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'}}
        for uid,row in __import__('survivalist_class').STATIC_DEFINITIONS.items()},
    **{uid:{'clause_id':row['clause_id'],'span':list(row['span']),'catalog_span':list(row['catalog_span']),
        'class_template':'class/댄서','definition':row,'minimum_level':0,'skill':None,'branch':uid=='class/댄서',
        'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('dancer').SOURCE_SHA256}}
        for uid,row in __import__('dancer').STATIC_DEFINITIONS.items()},
    **{uid:{'clause_id':'input/ch04-trainer-classes.md:'+str(span[0])+'-'+str(span[1]),
        'span':list(span),'minimum_level':0,'skill':None,'source':{'file':'input/ch04-trainer-classes.md',
        'sha256':'a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'}}
        for uid,span in __import__('conquerors_march').FEATURES.items()},
    **{uid:{'clause_id':('C04-039' if uid=='feat/인마일체' else 'input/ch04-trainer-classes.md:902-904'),
        'span':list(span),'catalog_span':([888,888] if uid=='class/라이더' else list(span)),
        'minimum_level':0,'skill':None,'source':{'file':'input/ch04-trainer-classes.md',
        'sha256':'a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'}}
        for uid,span in __import__('control_mount').FEATURES.items()},
    'feat/복원력': {'clause_id':'input/ch04-trainer-classes.md:812-816','span':[812,816],
        'minimum_level':0,'skill':None,'source':{'file':'input/ch04-trainer-classes.md',
        'sha256':'a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'}},
    **{uid:{'clause_id':('C04-033' if uid=='class/듀얼리스트' else 'input/ch04-trainer-classes.md:'+str(span[0])+'-'+str(span[1])),
        'span':list(span),'catalog_span':([720,720] if uid=='class/듀얼리스트' else list(span)),
        'minimum_level':0,'skill':None,'source':{'file':'input/ch04-trainer-classes.md',
        'sha256':'a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'}}
        for uid,span in __import__('duelist').FEATURES.items()},
    "feat/응원-문구": {"clause_id": "input/ch04-trainer-classes.md:705-712", "span": [705, 712], "minimum_level": 0, "skill": None,
        "source": {"file": "input/ch04-trainer-classes.md", "sha256": "a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4"}},
    "feat/끝까지-싸우자": {"clause_id": "input/ch04-trainer-classes.md:714-718", "span": [714, 718], "minimum_level": 0, "skill": None,
        "source": {"file": "input/ch04-trainer-classes.md", "sha256": "a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4"}},
    "feat/신나게-방해": {"clause_id": "input/ch04-trainer-classes.md:684-688", "span": [684, 688], "minimum_level": 0, "skill": None,
        "source": {"file": "input/ch04-trainer-classes.md", "sha256": "a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4"}},
    "feat/응원-단체": {"clause_id": "input/ch04-trainer-classes.md:678-682", "span": [678, 682], "minimum_level": 0, "skill": None,
        "source": {"file": "input/ch04-trainer-classes.md", "sha256": "a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4"}},
    "feat/영감을-주는-지원": {"clause_id": "input/ch04-trainer-classes.md:690-696", "span": [690, 696], "minimum_level": 0, "skill": None,
        "source": {"file": "input/ch04-trainer-classes.md", "sha256": "a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4"}},
    "feat/영감성-훈련": {"clause_id": "input/ch03-skills-edges-feats.md:714-718", "span": [714, 718], "minimum_level": 0, "skill": None},
    "class/치어리더": {"clause_id": "input/ch04-trainer-classes.md:675", "span": [675, 675], "catalog_span": [662, 662], "minimum_level": 0, "skill": None,
        "source": {"file": "input/ch04-trainer-classes.md", "sha256": "a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4"}},
    "feat/행동의-순간": {"clause_id": "input/ch04-trainer-classes.md:698-703", "span": [698, 703], "minimum_level": 0, "skill": None,
        "source": {"file": "input/ch04-trainer-classes.md", "sha256": "a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4"}},
    "feat/포획-추진력": {"clause_id": "input/ch04-trainer-classes.md:388-396", "span": [388, 396], "minimum_level": 0, "skill": None,
        "source": {"file": "input/ch04-trainer-classes.md", "sha256": "a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4"}},
    **{uid: {'clause_id': {'class/지휘관': 'C04-015', 'feat/리더십': 'C04-016',
                         'feat/전투-지휘': 'C04-017', 'feat/복합-지시': 'C04-018'}.get(
                         uid, 'input/ch04-trainer-classes.md:' + str(span[0]) + '-' + str(span[1])),
             'span': list(span), 'catalog_span': [411, 411] if uid == 'class/지휘관' else list(span),
             'class_template': 'class/지휘관', 'minimum_level': 0, 'skill': None,
             'branch': uid == 'class/지휘관', 'definition': __import__('commander').DEFINITIONS[uid],
             'source': {'file': 'input/ch04-trainer-classes.md', 'sha256': __import__('commander').SOURCE_SHA}}
       for uid, span in __import__('commander').FEATURES.items()},
    **{uid: {'clause_id': 'input/ch03-skills-edges-feats.md:' + str(row['span'][0]) + '-' + str(row['span'][1]),
             'span': list(row['span']), 'minimum_level': 0, 'skill': None,
             'source': {'file': 'input/ch03-skills-edges-feats.md', 'sha256': __import__('commander').GENERAL_SHA}}
       for uid, row in __import__('commander').BUNDLES.items()},
    "feat/포켓몬-넌-내-꺼야": {"clause_id": "C04-013", "span": [398, 403], "catalog_span": [398,407], "minimum_level": 0, "skill": None,
        "source": {"file": "input/ch04-trainer-classes.md", "sha256": "a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4"}},
    **{uid:{'clause_id':{'class/멘토':'C04-028','feat/지침':'C04-029','feat/평생학습':'C04-030'}.get(uid,'input/ch04-trainer-classes.md:'+str(span[0])+'-'+str(span[1])),
        'span':list(span),'catalog_span':[603,603] if uid=='class/멘토' else [650,657] if uid=='feat/평생학습' else list(span),
        'class_template':'class/멘토','minimum_level':0,'skill':None,
        'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('mentor').SOURCE_SHA256}}
       for uid,span in __import__('mentor').FEATURES.items()},
    "feat/압박": {"clause_id": "input/ch03-skills-edges-feats.md:643-647", "span": [643, 647], "minimum_level": 0, "skill": ["협박", 4]},
    "feat/계승자": {"clause_id": "C03-128", "span": [668, 672], "minimum_level": 10, "skill": ["명령", 4]},
    "feat/전력포즈": {"clause_id": "input/ch03-skills-edges-feats.md:674-677", "span": [674, 677], "minimum_level": 10, "skill": None},
    "feat/전설의-트레이너": {"clause_id": "C03-129", "span": [679, 684], "minimum_level": 20, "skill": None},
}
STATIC_FEATURES.update(__import__('versatility').DEFINITIONS)
STATIC_FEATURES.update({u:dict(d,minimum_level=0,skill=None) for u,d in __import__('coordinator').STATIC_DEFINITIONS.items()})
STATIC_FEATURES[__import__('walk_it_off').FEATURE]=dict(__import__('walk_it_off').DEFINITION)
STATIC_FEATURES.update({uid:{'clause_id':'C03-130' if uid==__import__('focused_command').VOICE else 'C03-131',
    'span':list(span),'catalog_span':[720,724] if uid==__import__('focused_command').VOICE else [726,735],
    'minimum_level':0,'skill':None,
    'source':{'file':'input/ch03-skills-edges-feats.md','sha256':__import__('commander').GENERAL_SHA}}
    for uid,span in __import__('focused_command').FEATURES.items()})
STATIC_FEATURES.update({u:{'clause_id':d['clause_id'],'span':d['span'],'catalog_span':d['catalog_span'],
 'class_template':__import__('trickster').CLASS,'definition':d,'minimum_level':0,'skill':None,
 'ranked':d['ranked'],'max_rank':2,'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('trickster').SOURCE_SHA256}}
 for u,d in __import__('trickster').DEFINITIONS.items()})
STATIC_FEATURES.update(__import__('hobbyist').STATIC_DEFINITIONS)
STATIC_FEATURES.update(__import__('rune_master').DEFINITIONS)
STATIC_FEATURES.update(__import__('arcanist').DEFINITIONS)
STATIC_FEATURES.update(__import__('berserker').DEFINITIONS)
for _uid,_span in __import__('hobbyist').GENERAL_FEATURES.items():
    if _uid not in STATIC_FEATURES and _uid not in (PERSONAL_TUTOR,'feat/종의-학자'):
        STATIC_FEATURES[_uid]={'clause_id':_uid,'span':list(_span),'minimum_level':0,'skill':None,'hobbyist_general':True,
            'source':{'file':'input/ch03-skills-edges-feats.md','sha256':__import__('hobbyist').GENERAL}}
STATIC_FEATURES['feat/지구력']={'clause_id':'input/ch04-trainer-classes.md:796-800','span':[796,800],
    'minimum_level':0,'skill':None,'source':{'file':'input/ch04-trainer-classes.md','sha256':__import__('hobbyist').BOOK}}
STATIC_SOURCE = {"file": "input/ch03-skills-edges-feats.md",
                 "sha256": "b94e43349794836391501f9aac10009d20746bf946ea0c4b5ff3adf85e982d23"}


def grant_qualified_core_edge(engine, actor, edge, choice, source_id, parent_source):
    """Printed Core Edge qualification, then existing native owner registration.

    This is an acquisition bridge, not an implementation of absent future
    effects. Source variants without a reviewed acquisition contract still hold.
    """
    import hobbyist as H, skill_modifiers as S, acquisition_qualification as Q
    import source_context as C, state_grants as G, acquisition_withdrawal as W
    if edge not in H.CORE_EDGE_SKILLS or engine.r._selected_rule(edge) != edge:
        raise ValueError('selected Edge needs its source-specific acquisition owner')
    C.verified_source(engine.r, STATIC_SOURCE, label='Core Edge acquisition')
    unit = engine.r.selection.units[edge]
    if unit['source']['file'] != 'ch03-skills-edges-feats.md':
        raise ValueError('exact Core Edge source required')
    skills = {s:S.rank(engine.r,actor,s)[2] for s in S.EDUCATION_SKILLS | set(engine.r.skill_policy['skills'])}
    parents = {}
    ordinary = H.CORE_EDGE_SKILLS[edge]
    checks = [Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
        Q.check('skills','prerequisite',not ordinary or any(S.rank(engine.r,actor,s)[2]>=n for s,n in ordinary),'ordinary printed Edge skill prerequisite required')]
    repeated = edge == 'edge/원소-교감'
    checks.append(Q.check('repeat','repeat',repeated or H.owned(actor,edge)==0,'ordinary Edge repeat restriction remains required'))
    if edge == 'edge/몬스터볼-수리':
        parents={p:H.owned(actor,p) for p in ('edge/몬스터볼','edge/규토리-볼')}
        checks.append(Q.check('parent','prerequisite',any(parents.values()),'Basic Balls or Apricorn Balls required'))
    if edge == 'edge/기본-사이오닉':
        checks.append(Q.check('psychic','prerequisite','에스퍼' in __import__('elemental_connection').choices(engine,actor),'actual Psychic Elemental Connection required'))
    if edge == 'edge/원소-교감':
        old=__import__('elemental_connection').choices(engine,actor)
        basic=set(engine.r.mech('combat/type-chart')['attack_vs_defense'])-{'에러','None'}
        checks.extend([Q.check('branch','selection',choice in basic and choice not in old,'one new canonical elemental branch required'),
            Q.check('exclusion','prerequisite',H.owned(actor,'edge/신비한-감각')==0,'Elemental Connection excludes Mystic Senses')])
    elif edge == 'edge/신비한-감각':
        checks.append(Q.check('exclusion','prerequisite',H.owned(actor,'edge/원소-교감')==0,'Mystic Senses excludes Elemental Connection'))
    if edge == 'edge/선택한-무기':
        import turn
        parents={p:1 for p in actor.spec.get('feats',[]) if '무기' in engine.r.selection.units.get(p,{}).get('tags',[]) or 'Weapon' in engine.r.selection.units.get(p,{}).get('tags',[])}
        checks.extend([Q.check('weapon','prerequisite',bool(parents),'actual acquired Weapon-tag Feature required'),
            Q.check('choice','selection',choice in turn.WEAPON_KIND,'one sourced ordinary weapon type required')])
    if edge not in ('edge/원소-교감','edge/선택한-무기') and choice is not None:
        raise ValueError('this Core Edge has no acquisition choice')
    qualification=Q.require(edge,actor.entity_id,'grant',checks)
    record={'edge':edge,'source':dict(STATIC_SOURCE,span=unit['source']['lines']),
        'choice':deepcopy(choice),'skills':skills,'parents':parents,'qualification':qualification,'parent_source':parent_source}
    record['integrity']=_digest('trainer-feature/core-edge-grant/v1',record)
    actor.spec.setdefault('edges',[]).append(edge)
    if edge=='edge/원소-교감':actor.spec.setdefault('edge_choices',{}).setdefault(edge,[]).append(choice)
    if edge=='edge/선택한-무기':actor.spec.setdefault('edge_choices',{})[edge]=choice
    G._source(actor,source_id,'feature',owner_id=actor.entity_id,rule_id=edge,lifetime='while_owned',tutor_points=0,core_edge_acquisition=record)
    W.dependencies(engine,actor,source_id,[parent_source])
    __import__('items').register_feats(engine,actor)
    __import__('class_move_grants').register_all(engine,actor)
    return deepcopy(record)
def _validate_core_edge_grants(actor):
    import hobbyist as H, source_context as C
    state=actor.spec.get('state_grants',{})
    rows=[(sid,row,True) for sid,row in state.get('sources',{}).items()]
    rows.extend((row['source_id'],row['record'],False) for row in state.get('ended_sources',[]))
    for sid,row,active in rows:
        if 'core_edge_acquisition' not in row:continue
        record=row['core_edge_acquisition'];edge=record.get('edge')
        if set(record)!={'edge','source','choice','skills','parents','qualification','parent_source','integrity'} or record.get('integrity')!=_digest('trainer-feature/core-edge-grant/v1',{k:v for k,v in record.items() if k!='integrity'}):raise ValueError('native Core Edge acquisition integrity changed')
        C.verified_source(actor.r,STATIC_SOURCE,label='Core Edge acquisition')
        unit=actor.r.selection.units.get(edge,{})
        if edge not in H.CORE_EDGE_SKILLS or actor.r._selected_rule(edge)!=edge or record['source']!=dict(STATIC_SOURCE,span=unit.get('source',{}).get('lines')):raise ValueError('actual selected Core Edge source required')
        if row.get('owner_id')!=actor.entity_id or row.get('rule_id')!=edge or row.get('lifetime')!='while_owned' or record['qualification'].get('status')!='qualified':raise ValueError('qualified Core Edge actual ownership source required')
        if active and (H.owned(actor,edge)<1 or record['parent_source'] not in state.get('sources',{})):raise ValueError('Core Edge grant must retain its actual acquired provider source')


BEAST_HEIR_SOURCE = "C2CSV/input/db/edges.csv:R21:main"
LIFECYCLE_UNRESOLVED = {
    "removal": "external_policy_required",
    "reacquisition": "external_policy_required",
}
LIFECYCLE_WHILE_OWNED = {
    "removal": "revoke_with_owned_source",
    "reacquisition": "new_acquisition_receipt_required",
}


PERSONAL_TUTOR_SOURCES = {
    "C03-127": {
        "file": "input/ch03-skills-edges-feats.md",
        "sha256": "b94e43349794836391501f9aac10009d20746bf946ea0c4b5ff3adf85e982d23",
        "version": 1,
        "span": [661, 666],
    },
    "C2CSV/input/db/feats.csv:R8:main": {
        "file": "input/db/feats.csv",
        "sha256": "4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd",
        "version": 1,
        "record": 8,
        "cells": [
            "개인 지도",
            "-",
            "초보 일반 지식, 특수(효과 참조)",
            "연장 행동(가르침)",
            "이 재주를 취득할때, 당신이 알고있는 기술 3개를 선택합니다. 해당 기술을 마스터합니다. \n"
            "연장 행동으로 당신의 포켓몬에게 마스터한 기술을 기술호환성을 무시하고 가르칩니다. "
            "개인지도를 통해 학습된 기술은 2개의 기술 슬롯과 영양제 슬롯 하나를 차지하며, 그 결과로 "
            "기본적으로 최대 5개의 기술만 배울 수 있으며, 포켓몬은 한 번에 하나의 개인지도 기술만 가질 수 있습니다.",
        ],
    },
}


MARTIAL_ARTIST_SOURCE = {
    "clause_id": "C04-098",
    "file": "input/ch04-trainer-classes.md",
    "sha256": "a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4",
    "version": 1,
    "span": [2394, 2402],
    "excerpt_sha256": "2f481f1d92929baab079707d33c55a06ad4240882f722574fb197aaeaa39bf00",
}
MARTIAL_ABILITY_SOURCE_SHA256 = "87efebd17b0a5fe09c9db060a16a8844cf41be53d65eb35716cf62f80a177fae"
MARTIAL_ABILITY_BINDINGS = {
    "ability/근성": {"printed": "근성", "title": "근성", "eng": "Guts", "keyword": None, "record": 32},
    "ability/정신력": {"printed": "정신력", "title": "정신력", "eng": "Inner Focus", "keyword": None, "record": None},
    "ability/철주먹": {"printed": "철주먹", "title": "철주먹", "eng": "Iron Fist", "keyword": None, "record": 385},
    "ability/유연": {"printed": "유연", "title": "유연", "eng": "Limber", "keyword": None, "record": 318},
    "ability/이판사판": {"printed": "이판사판", "title": "이판사판", "eng": "Reckless", "keyword": None, "record": None},
    "ability/테크니션": {"printed": "테크니션", "title": "테크니션", "eng": "Technician", "keyword": None, "record": 413},
}


def _text(value, label):
    if type(value) is not str or not value.strip():
        raise ValueError(label + " must be nonempty text")
    return value


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(label, value):
    payload = label + "\n" + _canonical_json(value)
    return "sha256:" + sha256(payload.encode("utf-8")).hexdigest()


def _static_source(rules, feature_id):
    if feature_id in __import__('berserker').FEATURES:return __import__('berserker').static_source(rules,feature_id)
    if feature_id in __import__('arcanist').FEATURES:return __import__('arcanist').static_source(rules,feature_id)
    if feature_id in __import__('rune_master').FEATURES:return __import__('rune_master').static_source(rules,feature_id)
    if feature_id in __import__('coordinator').FEATURES:return __import__('coordinator').static_source(rules,feature_id)
    import source_context as SOURCES
    definition = STATIC_FEATURES.get(feature_id)
    if definition is None:
        raise ValueError("reviewed selectionless Feature definition required")
    authority = definition.get("source", STATIC_SOURCE)
    SOURCES.verified_source(rules, authority, label="selectionless Feature")
    supported=feature_id in ('feat/훈련-상황','feat/작열','feat/패싱-왈츠')
    if rules._selected_rule(feature_id,supports_versions=supported) != feature_id:
        raise ValueError("selected static Feature requires its own acquisition contract")
    source = rules.selection.units[feature_id].get("source", {})
    if (source.get("file") != authority["file"].removeprefix("input/") or
            source.get("lines") != definition.get("catalog_span", definition["span"]) or source.get("sha256") != authority["sha256"]):
        raise ValueError("selectionless Feature catalog source differs from the reviewed clause")
    if feature_id == __import__('ace_trainer').TOP:
        rules.ruleset.require({'id': definition['clause_id'], 'source': authority})
    result=dict(authority, clause_id=definition["clause_id"], span=definition["span"])
    if feature_id=='feat/훈련-상황':
        selected=__import__('athlete').regime_source(rules)
        if feature_id in rules.ruleset.unit_versions:result['behavior_source']=selected
    if feature_id=='feat/작열':
        selected=__import__('pokemon_move_edges').incandescence_source(rules)
        if feature_id in rules.ruleset.unit_versions:result['behavior_source']=selected
    if feature_id=='feat/패싱-왈츠':
        selected=__import__('dancer').waltz_source(rules)
        if feature_id in rules.ruleset.unit_versions:result['behavior_source']=selected
    if definition.get('branch'):
        result['interpretation']={'authority':'PTU 1.05 English, user-selected precedence',
            'file':'output/source-audit/2026-10-10/ptu-core-1.05.pdf','pages':[112,113],
            'sha256':'e5e0371031601c3ad0a04056771c17599a2d8826e5a5102ccd37f9b368108907'}
        if definition.get('class_template')=='class/스타일-전문가':result['interpretation']['pages']=[115,116,117]
        if definition.get('class_template')=='class/타입-에이스':result['interpretation']['pages']=list(range(119,129))
        if definition.get('class_template') in ('class/댄서','class/음악가','class/로그'):result.pop('interpretation')   # printed Ability choices; no English precedence
        if definition.get('class_template') == 'class/지휘관':result['interpretation']['pages'] = [80, 81]
    return result


def _static_qualification(actor, feature_id, snapshot, prerequisite_source):
    if feature_id in __import__('berserker').FEATURES:return __import__('berserker').qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id in __import__('arcanist').FEATURES:return __import__('arcanist').qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id in __import__('rune_master').FEATURES:return __import__('rune_master').qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id == __import__('type_sync').FEATURE:
        return __import__('type_sync').qualification(actor,snapshot,prerequisite_source)
    import acquisition_qualification as Q
    if feature_id == __import__('psionic_sight').FEATURE:
        return __import__('psionic_sight').qualification(actor, snapshot, prerequisite_source)
    if type(prerequisite_source)is dict and 'hobbyist_parent' in prerequisite_source:
        return __import__('hobbyist').child_qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id in __import__('hobbyist').FEATURES:
        return __import__('hobbyist').qualification(actor,feature_id,snapshot,prerequisite_source)
    if STATIC_FEATURES[feature_id].get('hobbyist_general'):
        return __import__('hobbyist').general_qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id=='feat/지구력':
        return Q.require(feature_id,'native','acquire',[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),Q.check('parent','prerequisite',snapshot=={'enduring_soul':True} and prerequisite_source is None,'actual Enduring Soul prerequisite required')])
    if feature_id in __import__('versatility').FEATURES:
        return __import__('versatility').qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id == __import__('type_expertise').FEATURE:
        return __import__('type_expertise').qualification(actor, snapshot, prerequisite_source)
    if feature_id in __import__('focused_command').FEATURES:
        return __import__('focused_command').qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id==__import__('walk_it_off').FEATURE:return __import__('walk_it_off').qualification(actor,snapshot,prerequisite_source)
    if feature_id in __import__('trickster').FEATURES:return __import__('trickster').qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id in __import__('juggler').DEFINITIONS:return __import__('juggler').qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id in __import__('mentor').FEATURES:
        return __import__('mentor').qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id in __import__('coordinator').FEATURES:return __import__('coordinator').qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id in {*__import__('commander').FEATURES, *__import__('commander').BUNDLES}:
        return __import__('commander').qualification(actor, feature_id, snapshot, prerequisite_source)
    import ace_trainer as ACE
    if feature_id in ACE.FEATURES or (feature_id in ACE.TRAINING and set(snapshot)=={'skills','parents','gift','selection'}):
        return ACE.qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id in __import__('telekinetic').FEATURES:return __import__('telekinetic').qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id in __import__('warper').FEATURES:return __import__('warper').qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id in __import__('telepath').FEATURES:return __import__('telepath').qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id in __import__('sage').FEATURES:return __import__('sage').qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id in __import__('oracle').FEATURES:return __import__('oracle').qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id in __import__('ninja').FEATURES:return __import__('ninja').qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id in __import__('hex_maniac').FEATURES:return __import__('hex_maniac').qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id in __import__('channeler').FEATURES:return __import__('channeler').qualification(actor,feature_id,snapshot,prerequisite_source)
    definition = STATIC_FEATURES[feature_id]
    if feature_id in __import__('aura_guardian').FEATURES:return __import__('aura_guardian').qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id in __import__("tumbler").FEATURES:return __import__("tumbler").qualification(actor,feature_id,snapshot,prerequisite_source)
    import roughneck as ROUGHNECK
    if feature_id in ROUGHNECK.FEATURES:return ROUGHNECK.qualification(actor,feature_id,snapshot,prerequisite_source)
    import martial_artist as MARTIAL
    if feature_id in MARTIAL.FEATURES:return MARTIAL.qualification(actor,feature_id,snapshot,prerequisite_source)
    import provocateur as PROVOCATEUR
    if feature_id in PROVOCATEUR.FEATURES:return PROVOCATEUR.qualification(actor,feature_id,snapshot,prerequisite_source)
    import musician as MUSICIAN
    if feature_id in MUSICIAN.FEATURES:return MUSICIAN.qualification(actor,feature_id,snapshot,prerequisite_source)
    import rogue as ROGUE
    if feature_id in ROGUE.FEATURES:return ROGUE.qualification(actor,feature_id,snapshot,prerequisite_source)
    import type_ace as TYPE_ACE
    if feature_id in TYPE_ACE.FEATURES:return TYPE_ACE.qualification(actor,feature_id,snapshot,prerequisite_source)
    import chronicler as CHRONICLER
    if feature_id in CHRONICLER.FEATURES:return CHRONICLER.qualification(actor,feature_id,snapshot,prerequisite_source)
    import fashionista as FASHIONISTA
    if feature_id in FASHIONISTA.FEATURES:return FASHIONISTA.qualification(actor,feature_id,snapshot,prerequisite_source)
    import hunter as HUNTER
    if feature_id in HUNTER.FEATURES:return HUNTER.qualification(actor,feature_id,snapshot,prerequisite_source)
    import athlete as ATHLETE
    if feature_id in ATHLETE.FEATURES:return ATHLETE.qualification(actor,feature_id,snapshot,prerequisite_source)
    import style_expert as STYLE
    if feature_id in STYLE.FEATURES:return STYLE.qualification(actor,feature_id,snapshot,prerequisite_source)
    import stat_ace as STAT
    if feature_id in STAT.FEATURES:return STAT.qualification(actor,feature_id,snapshot,prerequisite_source)
    import taskmaster as TASK
    if feature_id in TASK.FEATURES:return TASK.qualification(actor,feature_id,snapshot,prerequisite_source)
    import chef_cooking as CHEF
    if feature_id in CHEF.FEATURES:return CHEF.qualification(actor,feature_id,snapshot,prerequisite_source)
    import survivalist_class as SURVIVAL
    if feature_id in SURVIVAL.FEATURES:return SURVIVAL.qualification(actor,feature_id,snapshot,prerequisite_source)
    import dancer as DANCER
    if feature_id in DANCER.FEATURES:return DANCER.qualification(actor,feature_id,snapshot,prerequisite_source)
    import conquerors_march as MARCH
    if feature_id in MARCH.FEATURES:return MARCH.qualification(actor,feature_id,snapshot,prerequisite_source)
    import control_mount as MOUNT
    if feature_id in MOUNT.FEATURES:return MOUNT.qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id == 'feat/복원력':
        import enduring_resilience as RESILIENCE
        return RESILIENCE.qualification(actor,snapshot,prerequisite_source)
    if feature_id == "feat/끝까지-싸우자":
        import keep_fighting as KEEP
        return KEEP.qualification(actor, snapshot, prerequisite_source)
    import duelist as DUELIST
    if feature_id in DUELIST.FEATURES:
        return DUELIST.qualification(actor,feature_id,snapshot,prerequisite_source)
    if feature_id in ("feat/영감성-훈련", "class/치어리더", "feat/행동의-순간"):
        import moment_of_action as MOMENT
        return MOMENT.qualification(actor, feature_id, snapshot, prerequisite_source)
    if feature_id in ("feat/응원-단체", "feat/영감을-주는-지원", "feat/신나게-방해", "feat/응원-문구"):
        import cheerleader as CHEER
        return CHEER.qualification(actor, feature_id, snapshot, prerequisite_source)
    if feature_id == "feat/포획-추진력":
        if 'selection' in snapshot:return __import__('capture_specialist').feature_qualification(actor,feature_id,snapshot,prerequisite_source)
        import captured_momentum as MOMENTUM
        return MOMENTUM.qualification(actor, snapshot, prerequisite_source)
    if feature_id == 'feat/포켓몬-넌-내-꺼야':return __import__('capture_specialist').feature_qualification(actor,feature_id,snapshot,prerequisite_source)
    if type(snapshot) is not dict or set(snapshot) != {"level", "skill", "rank", "beast_count"}:
        raise ValueError("exact acquisition-time static Feature observations required")
    if type(snapshot["level"]) is not int or type(snapshot["rank"]) is not int or type(snapshot["beast_count"]) is not int:
        raise ValueError("whole acquisition-time level, skill rank and owned count required")
    skill = definition["skill"]
    if prerequisite_source is not None:
        if feature_id != "feat/계승자" or prerequisite_source != BEAST_HEIR_SOURCE:
            raise ValueError("only the exact CSV Beast Master substitutes the Heir prerequisite")
        import pokemon_activities as ACTIVITIES
        if ACTIVITIES._beast_csv_source(actor.r)["source"] != prerequisite_source:
            raise ValueError("actual Beast Master CSV prerequisite source required")
        skill = ["협박", 4]
    expected_skill = skill[0] if skill else None
    if snapshot["skill"] != expected_skill or snapshot["beast_count"] != (1 if prerequisite_source else 0):
        raise ValueError("static Feature prerequisite observation has another source or skill")
    checks = [Q.check("trainer", "prerequisite", actor.kind == "trainer", "actual trainer required"),
              Q.check("level", "prerequisite", snapshot["level"] >= definition["minimum_level"],
                      "static Feature requires trainer level " + str(definition["minimum_level"]))]
    if skill:
        checks.append(Q.check("skill", "prerequisite", snapshot["rank"] >= skill[1], "static Feature requires Adept " + skill[0]))
    elif snapshot["rank"] != 0:
        raise ValueError("this static Feature has no skill prerequisite")
    return Q.require(feature_id, "native", "acquire", checks)


def _static_records(actor):
    state = actor.spec.get("state_grants", {})
    rows = [(sid, row, True) for sid, row in state.get("sources", {}).items()]
    rows.extend((entry["source_id"], entry["record"], False) for entry in state.get("ended_sources", []))
    return [(sid, row, active) for sid, row, active in rows if "static_acquisition" in row]


_ANY_STATIC_FEATURE = object()


def static_acquisitions(actor, feature=_ANY_STATIC_FEATURE, *, features=None, active=False):
    """Query committed receipts without changing their order or source identity."""
    return [(sid, row['static_acquisition']) for sid, row, live in _static_records(actor)
            if (features is None or row['static_acquisition']['feature_id'] in features)
            and (feature is _ANY_STATIC_FEATURE or row['static_acquisition']['feature_id'] == feature)
            and (not active or live)]


def static_family_acquisitions(actor, features, feature=None, *, active=False):
    return static_acquisitions(actor, _ANY_STATIC_FEATURE if feature is None else feature,
                               features=features, active=active)


def _validate_static_acquisitions(actor):
    __import__('type_sync').validate_feature_actor(actor)
    __import__('psionic_sight').validate_actor(actor)
    __import__('hobbyist').validate_actor(actor)
    _validate_core_edge_grants(actor)
    __import__('versatility').validate_actor(actor)
    __import__('type_expertise').validate_actor(actor)
    requests = set()
    for sid, row, active in _static_records(actor):
        record = row["static_acquisition"]
        fields = {"actor_id", "feature_id", "source", "request_id", "prerequisite_source", "snapshot", "qualification", "integrity"}
        if type(record) is not dict or set(record) != fields:
            raise ValueError("exact selectionless Feature acquisition evidence required")
        feature_id = record["feature_id"]
        if feature_id in __import__('berserker').FEATURES:__import__('berserker').validate_acquisition(actor,record,sid,active)
        if feature_id in __import__('rune_master').FEATURES:__import__('rune_master').validate_acquisition(actor,record,sid,active)
        if feature_id in __import__('arcanist').FEATURES:__import__('arcanist').validate_acquisition(actor,record,sid,active)
        if feature_id == __import__('psionic_sight').FEATURE:__import__('psionic_sight').validate_acquisition(actor,record,sid,active)
        if feature_id==__import__('walk_it_off').FEATURE:__import__('walk_it_off').validate_acquisition(actor,record,sid,active)
        if feature_id in __import__('juggler').DEFINITIONS:__import__('juggler').validate_acquisition(actor,record,sid,active)
        expected = _static_source(actor.r, feature_id)
        payload = {key: value for key, value in record.items() if key != "integrity"}
        if record["integrity"] != _digest("trainer-feature/static-acquisition/v1", payload):
            raise ValueError("static Feature acquisition integrity mismatch")
        _text(record["request_id"], "static Feature acquisition request")
        if record["request_id"] in requests:
            raise ValueError("static Feature acquisition request was reused")
        requests.add(record["request_id"])
        branch=record['snapshot'].get('branch') if STATIC_FEATURES[feature_id].get('branch') else None
        ranked=STATIC_FEATURES[feature_id].get('ranked')
        rank=record['snapshot'].get('rank_number') if ranked else None
        expected_sid='feature:'+actor.entity_id+':'+feature_id+(':'+branch if branch else '')+(':rank:'+str(rank) if ranked else '')
        if (record["actor_id"] != actor.entity_id or sid != expected_sid or row.get("kind") != "feature" or
                row.get("rule_id") != feature_id or row.get("owner_id") != actor.entity_id or
                row.get("lifetime") != "while_owned" or record["source"] != expected):
            raise ValueError("static Feature acquisition source or owner changed")
        if active and actor.spec.get("feats", []).count(feature_id) != 1:
            raise ValueError("static acquisition requires its one actual owned Feature")
        if active and STATIC_FEATURES[feature_id].get('move_choices'):
            choices=actor.spec.get('feature_choices',{}).get(feature_id,[])
            if len(choices)<rank or choices[rank-1]!=record['snapshot']['moves']:raise ValueError('actual acquired move choice projection changed')
        if active and branch and actor.spec.get('feature_choices',{}).get(feature_id,[]).count(branch)!=1:
            raise ValueError('actual acquired branch projection changed')
        if record["qualification"] != _static_qualification(actor, feature_id, record["snapshot"], record["prerequisite_source"]):
            raise ValueError("static Feature historical qualification changed")
        if feature_id in __import__('aura_guardian').FEATURES:__import__('aura_guardian').validate_acquisition(actor,record,sid,active)
        if feature_id in __import__('hex_maniac').FEATURES:__import__('hex_maniac').validate_acquisition(actor,record,sid,active)
        if feature_id in __import__('ninja').FEATURES:__import__('ninja').validate_acquisition(actor,record,sid,active)
        if feature_id in __import__('oracle').FEATURES:__import__('oracle').validate_acquisition(actor,record,sid,active)
        if feature_id in __import__('sage').FEATURES:__import__('sage').validate_acquisition(actor,record,sid,active)
        if feature_id in __import__('telekinetic').FEATURES:__import__('telekinetic').validate_acquisition(actor,record,sid,active)
        if feature_id in __import__('warper').FEATURES:__import__('warper').validate_acquisition(actor,record,sid,active)
        if feature_id in __import__('telepath').FEATURES:__import__('telepath').validate_acquisition(actor,record,sid,active)
        if feature_id in {*__import__('ace_trainer').FEATURES,*__import__('ace_trainer').TRAINING} and set(record['snapshot'])=={'skills','parents','gift','selection'}:
            __import__('ace_trainer').validate_acquisition(actor,record,sid,active)
        import control_mount as MOUNT
        if active and feature_id in {*MOUNT.FEATURES,*__import__('conquerors_march').FEATURES}:
            operation=actor.spec.get('state_grants',{}).get('stat_sources',{}).get('spe',{}).get('sources',{}).get(sid,{})
            if operation.get('acquisition_stat_tag')!={'delta':1,'minimum':None}:
                raise ValueError('actual source-owned Rider Speed stat tag required')
    for feature,definition in STATIC_FEATURES.items():
        if not definition.get('ranked'):continue
        rows=[row['static_acquisition'] for _,row,live in _static_records(actor) if live and row['static_acquisition']['feature_id']==feature]
        if not rows:
            if any(row['static_acquisition']['feature_id']==feature for _,row,_ in _static_records(actor)) and feature in actor.spec.get('feat_ranks',{}):
                raise ValueError('retired Ranked acquisition retains a rank projection')
            continue
        ranks=sorted(row['snapshot']['rank_number'] for row in rows)
        if ranks!=list(range(1,max(ranks)+1)) or actor.spec.get('feat_ranks',{}).get(feature)!=max(ranks):
            raise ValueError('actual active Ranked acquisition and rank projection differ')


def acquire_static(engine, actor, feature_id, *, acquisition_request_id, prerequisite_source=None, branch=None, rank=None, selection=None, source_id=None):
    """Acquire a reviewed Feature; source variants select their exact book or CSV clause."""
    import native_acquisition_adapters as NATIVE
    native = feature_id in NATIVE.DEFINITIONS
    if feature_id in (__import__('warper').FARCAST, __import__('ace_trainer').TOP):
        book_source = STATIC_FEATURES[feature_id]['clause_id']
        csv_source = NATIVE.DEFINITIONS[feature_id]['clause_id']
        if source_id not in (None, book_source, csv_source):
            raise ValueError('select the exact book or CSV acquisition source')
        history = [row['static_acquisition'] for _, row, _ in _static_records(actor)
                   if row['static_acquisition']['request_id'] == acquisition_request_id]
        history.extend(row[NATIVE.KEY] for _, row, _ in NATIVE._rows(actor)
                       if row[NATIVE.KEY]['request_id'] == acquisition_request_id)
        if history:
            if (len(history) != 1 or history[0]['feature_id'] != feature_id or
                    source_id is not None and source_id != history[0]['source']['clause_id']):
                raise ValueError('acquisition request replay changed intent or source')
            source_id = history[0]['source']['clause_id']
        # Old named requests retain their source, including withdrawn CSV receipts.
        native = source_id == csv_source
    elif source_id is not None:
        raise ValueError('explicit acquisition source choice is only defined for Farcast and Top Percentage')
    other_records = _static_records(actor) if native else NATIVE._rows(actor)
    other_key = 'static_acquisition' if native else NATIVE.KEY
    if any(row[other_key]['request_id'] == acquisition_request_id for _, row, _ in other_records):
        raise ValueError('acquisition request belongs to another source adapter')
    if native:
        if prerequisite_source is not None or branch is not None or rank is not None:
            raise ValueError('this source uses its exact native acquisition selection')
        return NATIVE.acquire(engine, actor, feature_id,
            acquisition_request_id=acquisition_request_id, selection=selection)
    import acquired_features as ACQUIRED,skill_modifiers as SKILLS,state_grants as GRANTS,world_entities as WORLD
    WORLD.require_actors(engine, actor)
    source = _static_source(engine.r, feature_id)
    if STATIC_FEATURES[feature_id].get('move_choices'):
        if type(branch) is not list or len(branch)!=2:raise ValueError('select exactly two acquired Moves')
        branch=[engine.r.move_id(value) for value in branch]
    _text(acquisition_request_id, "static Feature acquisition request")
    validate_actor(actor)
    for _, row, active in _static_records(actor):
        record = row["static_acquisition"]
        if record["request_id"] == acquisition_request_id:
            actual_selection=record["snapshot"].get("selection")
            if feature_id==__import__('commander').COMPLEX:
                actual_selection={'prerequisite_source':record['snapshot']['prerequisite_source']}
                if record['snapshot']['mastermind_declaration'] is not None:
                    actual_selection['mastermind_declaration']=record['snapshot']['mastermind_declaration']
            if actual_selection!=selection:raise ValueError("static acquisition replay cannot change optional selection")
            expected_branch=branch if STATIC_FEATURES[feature_id].get('branch') or STATIC_FEATURES[feature_id].get('move_choices') else None
            actual_branch=record['snapshot'].get('moves') if STATIC_FEATURES[feature_id].get('move_choices') else record['snapshot'].get('branch') if STATIC_FEATURES[feature_id].get('branch') else None
            if record["feature_id"] != feature_id or record["prerequisite_source"] != prerequisite_source or actual_branch!=expected_branch or (rank is not None and record['snapshot'].get('rank_number')!=rank):
                raise ValueError("static Feature acquisition replay cannot change its intent")
            return dict(deepcopy(record), status="acquired" if active else "withdrawn")
    if selection is not None and feature_id not in __import__('berserker').FEATURES and feature_id not in __import__('arcanist').FEATURES and feature_id not in __import__('rune_master').FEATURES and feature_id not in {'feat/특색있는-맛','feat/경단'} and feature_id!=__import__('type_sync').FEATURE and feature_id!=__import__('psionic_sight').FEATURE and feature_id not in __import__('hobbyist').FEATURES and feature_id!=__import__('commander').COMPLEX and feature_id!=__import__("provocateur").PUSH and feature_id not in {*__import__('style_expert').FEATURES,__import__('type_expertise').FEATURE,*__import__('versatility').FEATURES,*__import__('trickster').FEATURES,*__import__('type_ace').CSV_VARIANTS,*__import__('juggler').DEFINITIONS,*__import__('mentor').FEATURES,*__import__('coordinator').FEATURES,*__import__('ace_trainer').FEATURES,*__import__('ace_trainer').TRAINING,*__import__('aura_guardian').FEATURES,*__import__('hex_maniac').FEATURES,__import__('sage').HANDS,__import__('telekinetic').POWER,__import__('telepath').AWARE,__import__('walk_it_off').FEATURE,'feat/포획-추진력','feat/포켓몬-넌-내-꺼야'}:raise ValueError("this Feature has no optional acquisition selection")
    branched=STATIC_FEATURES[feature_id].get('branch',False)
    ranked=STATIC_FEATURES[feature_id].get('ranked',False)
    if rank is not None and not ranked:raise ValueError('this Feature is not Ranked')
    if ranked:
        maximum=STATIC_FEATURES[feature_id].get('max_rank',2)
        if type(rank) is not int or not 1<=rank<=maximum:raise ValueError('explicit acquired rank in the printed domain required')
        current=actor.spec.get('feat_ranks',{}).get(feature_id,0)
        if rank!=current+1:raise ValueError('acquire the next actual rank')
    if not branched and branch is not None and not STATIC_FEATURES[feature_id].get('move_choices'):raise ValueError('this Feature has no acquired branch')
    if (not branched and not ranked and ACQUIRED.owned_rule_count(actor, feature_id)) or (branched and branch in actor.spec.get('feature_choices',{}).get(feature_id,[])):
        raise ValueError("static Feature is already acquired; current ownership cannot invent historical qualification")
    if not isinstance(actor.spec.get("feats", []), list):
        raise ValueError("trainer Feature ownership must be a mutable list")
    skill = STATIC_FEATURES[feature_id]["skill"]
    beast_count = 0
    if prerequisite_source is not None:
        if feature_id != "feat/계승자" or prerequisite_source != BEAST_HEIR_SOURCE:
            raise ValueError("only the exact CSV Beast Master substitutes the Heir prerequisite")
        beast_count = ACQUIRED.owned_rule_count(actor, "edge/비스트-마스터")
        if beast_count != 1:
            raise ValueError("actual acquired Beast Master required for its CSV prerequisite substitution")
        skill = ["협박", 4]
    snapshot = {"level": actor.spec.get("level"), "skill": skill[0] if skill else None,
                "rank": SKILLS.rank(engine.r, actor, skill[0])[2] if skill else 0, "beast_count": beast_count}
    if feature_id in __import__('roughneck').FEATURES:
        snapshot=__import__('roughneck').acquisition_snapshot(engine,actor,feature_id)
    elif feature_id in __import__('martial_artist').FEATURES:
        snapshot=__import__('martial_artist').acquisition_snapshot(engine,actor,feature_id,rank,branch)
    elif feature_id in __import__('musician').FEATURES:
        snapshot=__import__('musician').acquisition_snapshot(engine,actor,feature_id,branch)
    elif feature_id in __import__('type_ace').FEATURES:
        snapshot=__import__('type_ace').acquisition_snapshot(engine,actor,feature_id,branch,selection)
    elif feature_id in __import__('chronicler').FEATURES:
        snapshot=__import__('chronicler').acquisition_snapshot(engine,actor,feature_id,rank)
    elif feature_id in __import__('fashionista').FEATURES:
        snapshot=__import__('fashionista').acquisition_snapshot(engine,actor,feature_id,rank)
    elif feature_id in __import__('hunter').FEATURES:
        snapshot=__import__('hunter').acquisition_snapshot(engine,actor,feature_id,branch,rank)
    elif feature_id in __import__('athlete').FEATURES:
        snapshot=__import__('athlete').acquisition_snapshot(engine,actor,feature_id,rank)
    elif feature_id in __import__('style_expert').FEATURES:
        snapshot=__import__('style_expert').acquisition_snapshot(engine,actor,feature_id,branch,rank,selection)
    elif feature_id in __import__('rogue').FEATURES:
        snapshot=__import__('rogue').acquisition_snapshot(engine,actor,feature_id,branch)
    elif feature_id in __import__('dancer').FEATURES:
        snapshot=__import__('dancer').acquisition_snapshot(engine,actor,feature_id,branch)
    elif feature_id in {*__import__('commander').FEATURES, *__import__('commander').BUNDLES}:
        snapshot = __import__('commander').acquisition_snapshot(engine, actor, feature_id, branch, selection)
    elif branched:
        import stat_ace as STAT
        snapshot=STAT.acquisition_snapshot(engine,actor,feature_id,branch)
    import taskmaster as TASK
    if feature_id in TASK.FEATURES:snapshot=TASK.acquisition_snapshot(actor,feature_id)
    import chef_cooking as CHEF
    if feature_id in CHEF.FEATURES:snapshot=CHEF.acquisition_snapshot(engine,actor,feature_id,selection)
    import survivalist_class as SURVIVAL
    if feature_id in SURVIVAL.FEATURES:snapshot=SURVIVAL.acquisition_snapshot(engine,actor,feature_id,rank)
    import control_mount as MOUNT
    if feature_id in MOUNT.FEATURES:snapshot=MOUNT.acquisition_snapshot(actor,feature_id)
    import conquerors_march as MARCH
    if feature_id in MARCH.FEATURES:snapshot=MARCH.acquisition_snapshot(actor,feature_id)
    if feature_id == 'feat/복원력':
        import enduring_resilience as RESILIENCE
        snapshot=RESILIENCE.acquisition_snapshot(actor)
    if feature_id == "feat/끝까지-싸우자":
        import keep_fighting as KEEP
        snapshot = KEEP.acquisition_snapshot(actor)
    import duelist as DUELIST
    if feature_id in DUELIST.FEATURES:
        snapshot=DUELIST.acquisition_snapshot(actor,feature_id)
    if feature_id in ("feat/영감성-훈련", "class/치어리더", "feat/행동의-순간"):
        import moment_of_action as MOMENT
        snapshot = MOMENT.acquisition_snapshot(actor, feature_id)
    if feature_id == "feat/포획-추진력":
        import captured_momentum as MOMENTUM
        snapshot = __import__('capture_specialist').feature_snapshot(actor,feature_id,selection) if selection is not None else MOMENTUM.acquisition_snapshot(actor)
    if feature_id == 'feat/포켓몬-넌-내-꺼야':snapshot=__import__('capture_specialist').feature_snapshot(actor,feature_id,selection)
    if feature_id in ("feat/응원-단체", "feat/영감을-주는-지원", "feat/신나게-방해", "feat/응원-문구"):
        import cheerleader as CHEER
        snapshot = CHEER.acquisition_snapshot(actor, feature_id)
    if feature_id in __import__("provocateur").FEATURES:
        snapshot=__import__("provocateur").acquisition_snapshot(engine,actor,feature_id,selection)
    if feature_id in __import__("tumbler").FEATURES:snapshot=__import__("tumbler").acquisition_snapshot(engine,actor,feature_id)
    if feature_id in __import__('aura_guardian').FEATURES:snapshot=__import__('aura_guardian').acquisition_snapshot(engine,actor,feature_id,rank,selection)
    if feature_id in __import__('channeler').FEATURES:snapshot=__import__('channeler').acquisition_snapshot(engine,actor,feature_id)
    if feature_id in __import__('hex_maniac').FEATURES:snapshot=__import__('hex_maniac').acquisition_snapshot(engine,actor,feature_id,rank,selection)
    if feature_id in __import__('ninja').FEATURES:snapshot=__import__('ninja').acquisition_snapshot(engine,actor,feature_id,rank,selection)
    if feature_id in __import__('oracle').FEATURES:snapshot=__import__('oracle').acquisition_snapshot(engine,actor,feature_id,rank,selection)
    if feature_id in __import__('sage').FEATURES:snapshot=__import__('sage').acquisition_snapshot(engine,actor,feature_id,rank,selection)
    if feature_id in __import__('telekinetic').FEATURES:snapshot=__import__('telekinetic').acquisition_snapshot(engine,actor,feature_id,rank,selection)
    if feature_id in __import__('warper').FEATURES:snapshot=__import__('warper').acquisition_snapshot(engine,actor,feature_id,rank,selection)
    elif feature_id in __import__('telepath').FEATURES:snapshot=__import__('telepath').acquisition_snapshot(engine,actor,feature_id,rank,selection)
    if feature_id in {*__import__('ace_trainer').FEATURES,*__import__('ace_trainer').TRAINING}:
        snapshot=__import__('ace_trainer').acquisition_snapshot(engine,actor,feature_id,rank,selection)
    if feature_id in __import__('mentor').FEATURES:
        snapshot=__import__('mentor').acquisition_snapshot(engine,actor,feature_id,selection)
    if feature_id in __import__('coordinator').FEATURES:snapshot=__import__('coordinator').acquisition_snapshot(engine,actor,feature_id,rank,selection)
    if feature_id in __import__('trickster').FEATURES:snapshot=__import__('trickster').acquisition_snapshot(engine,actor,feature_id,rank,selection)
    if feature_id in __import__('juggler').DEFINITIONS:snapshot=__import__('juggler').acquisition_snapshot(engine,actor,feature_id,rank,selection)
    if feature_id == __import__('type_expertise').FEATURE:
        snapshot = __import__('type_expertise').acquisition_snapshot(engine, actor, rank, selection)
    if feature_id==__import__('walk_it_off').FEATURE:snapshot=__import__('walk_it_off').acquisition_snapshot(engine,actor,selection)
    if feature_id in __import__('focused_command').FEATURES:
        snapshot=__import__('focused_command').acquisition_snapshot(engine,actor,feature_id)
    if feature_id in __import__('versatility').FEATURES:
        snapshot=__import__('versatility').acquisition_snapshot(engine,actor,feature_id,selection)
    if feature_id == __import__('psionic_sight').FEATURE:
        snapshot = __import__('psionic_sight').acquisition_snapshot(engine, actor, selection)
    if feature_id == __import__('type_sync').FEATURE:
        snapshot = __import__('type_sync').acquisition_snapshot(engine,actor,selection)
    if feature_id in __import__('hobbyist').FEATURES:
        snapshot=__import__('hobbyist').acquisition_snapshot(engine,actor,feature_id,rank,selection)
    elif STATIC_FEATURES[feature_id].get('hobbyist_general'):
        snapshot=__import__('hobbyist').general_snapshot(engine,actor,feature_id,selection)
    elif feature_id=='feat/지구력':
        snapshot={'enduring_soul':bool(__import__('acquired_features').owned_rule_count(actor,'class/불굴의-투지'))}
    if feature_id in __import__('rune_master').FEATURES:
        snapshot = __import__('rune_master').acquisition_snapshot(engine,actor,feature_id,rank,selection)
    if feature_id in __import__('arcanist').FEATURES:
        snapshot = __import__('arcanist').acquisition_snapshot(engine,actor,feature_id,rank,selection)
    if feature_id in __import__('berserker').FEATURES:
        snapshot = __import__('berserker').acquisition_snapshot(engine,actor,feature_id,rank,selection)
    qualification = _static_qualification(actor, feature_id, snapshot, prerequisite_source)
    record = {"actor_id": actor.entity_id, "feature_id": feature_id, "source": source, "request_id": acquisition_request_id,
              "prerequisite_source": prerequisite_source, "snapshot": snapshot, "qualification": qualification}
    record["integrity"] = _digest("trainer-feature/static-acquisition/v1", record)
    def apply(staged, trainer):
        import trainer_retraining as RETRAINING
        if feature_id not in trainer.spec.setdefault('feats',[]):trainer.spec['feats'].append(feature_id)
        if feature_id==__import__('berserker').POWER:
            __import__('berserker').prepare_acquire(staged,trainer,snapshot['selection'])
        if ranked:
            trainer.spec.setdefault('feat_ranks',{})[feature_id]=rank
            if feature_id==__import__('hex_maniac').STUDIES:
                trainer.spec.setdefault('feature_choices',{}).setdefault(feature_id,[]).append(list(snapshot['selection']['moves']))
            if STATIC_FEATURES[feature_id].get('move_choices'):
                trainer.spec.setdefault('feature_choices',{}).setdefault(feature_id,[]).append(list(snapshot['moves']))
        if branched:
            trainer.spec.setdefault('feature_choices',{}).setdefault(feature_id,[]).append(branch)
            source_id='feature:'+trainer.entity_id+':'+feature_id+':'+branch
            GRANTS._source(trainer,source_id,'feature',rule_id=feature_id,owner_id=trainer.entity_id,lifetime='while_owned',tutor_points=0)
        elif ranked:
            source_id='feature:'+trainer.entity_id+':'+feature_id+':rank:'+str(rank)
            GRANTS._source(trainer,source_id,'feature',rule_id=feature_id,owner_id=trainer.entity_id,lifetime='while_owned',tutor_points=0)
        else:source_id = RETRAINING.owned_source(staged, trainer, feature_id)
        GRANTS._source(trainer, source_id, "feature", static_acquisition=record)
        if feature_id in __import__('rune_master').FEATURES:__import__('rune_master').after_acquire(staged,trainer,feature_id,source_id)
        if feature_id in __import__('arcanist').FEATURES:__import__('arcanist').after_acquire(staged,trainer,feature_id,source_id)
        if feature_id in __import__('berserker').FEATURES:__import__('berserker').after_acquire(staged,trainer,feature_id,source_id)
        if feature_id == __import__('psionic_sight').FEATURE:__import__('psionic_sight').after_acquire(staged,trainer,source_id)
        if feature_id in __import__('hobbyist').FEATURES:
            __import__('hobbyist').after_acquire(staged,trainer,feature_id,source_id)
        elif STATIC_FEATURES[feature_id].get('hobbyist_general'):
            __import__('hobbyist').after_child(staged,trainer,feature_id,source_id,{})
        if feature_id in __import__('versatility').FEATURES:
            __import__('versatility').after_acquire(staged,trainer,feature_id,source_id)
        if feature_id==__import__('walk_it_off').FEATURE:GRANTS.stat(trainer,'hp',1,source_id,operation_id='acquisition_stat_tag')
        if feature_id in {*__import__('commander').FEATURES, *__import__('commander').BUNDLES}:
            __import__('commander').after_acquire(staged, trainer, feature_id, source_id, branch)
        if feature_id in __import__('rogue').FEATURES:
            __import__('rogue').after_acquire(staged,trainer,feature_id,source_id,branch)
        if feature_id in {*MOUNT.FEATURES,*MARCH.FEATURES}:
            GRANTS.stat(trainer,'spe',1,source_id,operation_id='acquisition_stat_tag')
        if feature_id in __import__('hunter').FEATURES:
            __import__('hunter').after_acquire(staged,trainer,feature_id,source_id,branch)
        if feature_id in __import__('athlete').FEATURES:
            GRANTS.stat(trainer,__import__('athlete').STAT_TAG,1,source_id,operation_id='acquisition_stat_tag')
        if feature_id in ("feat/포획-추진력",'feat/포켓몬-넌-내-꺼야'):
            import items
            items.register_feats(staged, trainer)
        if feature_id in __import__('martial_artist').FEATURES:
            if feature_id==__import__('martial_artist').TRAINING:__import__('class_move_grants').register_all(staged,trainer)
            __import__('static_feature_state_grants').register_all(staged,trainer)
        if feature_id in __import__("provocateur").FEATURES:
            __import__("provocateur").after_acquire(staged,trainer,feature_id,source_id)
        if feature_id in __import__("tumbler").FEATURES:__import__("tumbler").after_acquire(staged,trainer,feature_id,source_id)
        if feature_id in __import__('aura_guardian').FEATURES:__import__('aura_guardian').after_acquire(staged,trainer,feature_id,source_id)
        if feature_id in __import__('hex_maniac').FEATURES:__import__('hex_maniac').after_acquire(staged,trainer,feature_id,source_id)
        if feature_id in __import__('ninja').FEATURES:__import__('ninja').after_acquire(staged,trainer,feature_id,source_id)
        if feature_id in __import__('oracle').FEATURES:__import__('oracle').after_acquire(staged,trainer,feature_id,source_id)
        if feature_id in __import__('sage').FEATURES:__import__('sage').after_acquire(staged,trainer,feature_id,source_id)
        if feature_id in __import__('telekinetic').FEATURES:__import__('telekinetic').after_acquire(staged,trainer,feature_id,source_id)
        if feature_id in __import__('warper').FEATURES:__import__('warper').after_acquire(staged,trainer,feature_id,source_id)
        if feature_id in __import__('telepath').FEATURES:__import__('telepath').after_acquire(staged,trainer,feature_id,source_id)
        if feature_id in __import__('ace_trainer').FEATURES:__import__('ace_trainer').after_acquire(staged,trainer,feature_id,source_id)
        if feature_id in __import__('juggler').DEFINITIONS:__import__('juggler').after_acquire(staged,trainer,feature_id,source_id)
        if feature_id == __import__('type_expertise').FEATURE:
            __import__('type_expertise').after_acquire(staged, trainer, source_id)
        if feature_id in __import__('mentor').FEATURES:__import__('mentor').on_acquired(staged,trainer,feature_id,record)
        validate_actor(trainer)
        ACQUIRED.class_instances(trainer);ACQUIRED.feature_instances(trainer)
        if branched:
            import static_trainer_modifiers as STATIC
            STATIC.register_all(staged,trainer)
        if feature_id in __import__('chronicler').FEATURES:
            __import__('chronicler').after_acquire(staged,trainer)
        if feature_id in __import__('fashionista').FEATURES:
            __import__('fashionista').after_acquire(staged,trainer)
        if feature_id in __import__('dancer').FEATURES:
            __import__('dancer').after_acquire(staged,trainer,feature_id,branch)
        if feature_id in __import__('roughneck').FEATURES:
            __import__('roughneck').after_acquire(staged,trainer,feature_id,source_id)
        if feature_id in __import__('musician').FEATURES:
            __import__('musician').after_acquire(staged,trainer,feature_id,source_id,branch)
        import class_passive_combat as PASSIVE
        if feature_id in PASSIVE.POKEMON_STATIC:
            for pokemon in PASSIVE._owned_pokemon(staged,trainer):
                PASSIVE.register_all(staged,pokemon)
        return dict(deepcopy(record), status="acquired")
    return GRANTS.transition(engine, actor, apply)


def _source(rules, clause_id):
    _text(clause_id, "source clause identity")
    if clause_id not in PERSONAL_TUTOR_SOURCES:
        raise ValueError("Personal Tutor requires one reviewed exact source clause")
    if rules._selected_rule(PERSONAL_TUTOR) != PERSONAL_TUTOR:
        raise ValueError("selected Personal Tutor variant requires its own acquisition adapter")
    if clause_id in rules.ruleset.unit_versions:
        raise ValueError("selected Personal Tutor source version requires its own reviewed adapter")
    expected = PERSONAL_TUTOR_SOURCES[clause_id]
    path = Path(rules.root) / expected["file"]
    if sha256(path.read_bytes()).hexdigest() != expected["sha256"]:
        raise ValueError("Personal Tutor source changed; review required")
    if "record" in expected:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        if len(rows) < expected["record"] or rows[expected["record"] - 1] != expected["cells"]:
            raise ValueError("Personal Tutor CSV record differs from reviewed source")
        rules.ruleset.require({
            "id": clause_id,
            "source": {"file": expected["file"].removeprefix("input/"),
                       "record_span": [expected["record"], expected["record"]]},
        })
    else:
        unit = rules.selection.units.get(PERSONAL_TUTOR)
        source = unit.get("source", {}) if isinstance(unit, dict) else {}
        if (source.get("file") != expected["file"].removeprefix("input/") or
                source.get("lines") != expected["span"] or
                source.get("sha256") != expected["sha256"]):
            raise ValueError("Personal Tutor catalog source differs from reviewed clause")
    return {
        "clause_id": clause_id,
        "file": expected["file"],
        "sha256": expected["sha256"],
        "version": expected["version"],
    }


def _martial_source(rules, clause_id):
    expected = MARTIAL_ARTIST_SOURCE
    if clause_id != expected["clause_id"]:
        raise ValueError("Martial Artist requires its reviewed exact source clause")
    if rules._selected_rule(MARTIAL_ARTIST) != MARTIAL_ARTIST:
        raise ValueError("selected Martial Artist variant requires its own acquisition adapter")
    if MARTIAL_ARTIST in rules.ruleset.unit_versions:
        raise ValueError("selected Martial Artist source version requires its own reviewed adapter")
    path = Path(rules.root) / expected["file"]
    if sha256(path.read_bytes()).hexdigest() != expected["sha256"]:
        raise ValueError("Martial Artist source changed; review required")
    lines = path.read_text(encoding="utf-8").splitlines()
    excerpt = "\n".join(lines[expected["span"][0] - 1:expected["span"][1]])
    if sha256(excerpt.encode("utf-8")).hexdigest() != expected["excerpt_sha256"]:
        raise ValueError("Martial Artist choice clause changed; review required")
    rules.ruleset.require({
        "id": clause_id,
        "source": {"file": expected["file"].removeprefix("input/"), "lines": expected["span"]},
    })
    return {
        "clause_id": clause_id,
        "file": expected["file"],
        "sha256": expected["sha256"],
        "version": expected["version"],
    }


def _validate_martial_ability_catalog(rules):
    path = Path(rules.root) / "input/db/abilities.csv"
    if sha256(path.read_bytes()).hexdigest() != MARTIAL_ABILITY_SOURCE_SHA256:
        raise ValueError("Martial Artist Ability catalog changed; review required")
    for uid, expected in MARTIAL_ABILITY_BINDINGS.items():
        if rules._selected_rule(uid) != uid:
            raise ValueError("reviewed Martial Artist Ability is not selected: " + uid)
        unit = rules.selection.units.get(uid)
        source = unit.get("source", {}) if isinstance(unit, dict) else {}
        if expected["record"] is None:
            exact_source = (source.get("file") == MARTIAL_ARTIST_SOURCE["file"].removeprefix("input/") and
                            source.get("lines") == MARTIAL_ARTIST_SOURCE["span"] and
                            source.get("sha256") == MARTIAL_ARTIST_SOURCE["sha256"])
        else:
            exact_source = (source.get("file") == "db/abilities.csv" and
                            source.get("record_span") == [expected["record"], expected["record"]] and
                            source.get("sha256") == MARTIAL_ABILITY_SOURCE_SHA256)
        if (not isinstance(unit, dict) or unit.get("title") != expected["title"] or
                unit.get("eng") != expected["eng"] or unit.get("keyword") != (rules.core_abilities[uid].get('keyword') if expected['record'] is None else expected['keyword']) or
                not exact_source or expected["title"] not in rules.ability_effects or
                expected["title"] in getattr(rules, "excluded_abilities", {})):
            raise ValueError("Martial Artist Ability provenance changed: " + uid)
    return tuple(MARTIAL_ABILITY_BINDINGS)


def _canonical_martial_ability(rules, selected_value):
    if type(selected_value) is not str or not selected_value.strip():
        raise ValueError("Martial Artist selected Ability must be nonempty text")
    _validate_martial_ability_catalog(rules)
    matches = []
    for uid, row in MARTIAL_ABILITY_BINDINGS.items():
        if selected_value in (uid, row["printed"], row["title"], row["eng"]):
            matches.append(uid)
    if len(matches) != 1:
        raise ValueError("Martial Artist must select exactly one Ability from its printed domain")
    return matches[0]


def _lifecycle(value):
    if type(value) is not dict or value != LIFECYCLE_UNRESOLVED:
        raise ValueError("explicit unresolved removal/reacquisition policy required")
    return deepcopy(value)


def _martial_lifecycle(value):
    if type(value) is not dict or value != LIFECYCLE_WHILE_OWNED:
        raise ValueError("Martial Artist requires its exact while-owned removal/reacquisition policy")
    return deepcopy(value)


def _canonical_moves(rules, selected_values):
    if not isinstance(selected_values, (list, tuple)):
        raise ValueError("Personal Tutor selection must be a sequence")
    if len(selected_values) != 3:
        raise ValueError("Personal Tutor requires exactly three selected moves")
    result = []
    for value in selected_values:
        if type(value) is not str or not value.strip():
            raise ValueError("selected move identity must be nonempty text")
        mid = rules.move_id(value)
        if mid is None:
            raise ValueError("unknown selected Personal Tutor move: " + value)
        result.append(mid)
    if len(set(result)) != len(result):
        raise ValueError("Personal Tutor requires three distinct selected moves")
    return result


def _personal_tutor_qualification(actor, provider, waivers):
    if provider is not actor:
        raise ValueError("Personal Tutor acquisition provider must be the acquiring trainer")
    if waivers not in ((), []):
        raise ValueError("Personal Tutor prerequisite waiver has no reviewed native authority")
    import skill_modifiers as SKILLS
    rank_name, dice, rank = SKILLS.rank(actor.r, actor, "일반 지식")
    hobbyist=__import__('hobbyist').provider(actor,PERSONAL_TUTOR)
    waived=hobbyist is not None and hobbyist[1]['kind']=='dilettante'
    checks = [
        {"id": "trainer", "kind": "prerequisite", "state": "passed" if actor.kind == "trainer" else "denied",
         "observed": actor.kind, "reason": "Personal Tutor requires an actual trainer"},
          {"id": "general_education", "kind": "prerequisite", "state": "waived" if waived else "passed" if rank >= 3 else "denied",
         "observed": {"rank_name": rank_name, "dice": dice, "rank": rank},
         "reason": "Personal Tutor requires Novice General Education"},
    ]
    denied = next((row for row in checks if row["state"] not in ('passed','waived')), None)
    if denied is not None:
        raise ValueError(denied["reason"])
    return {"schema": 1, "status": "qualified", "checks": checks, "waivers": [{'hobbyist_provider':deepcopy(hobbyist[1])}] if waived else []}


def _permanent_move_proofs(actor, selected):
    import move_state as MOVES
    known = MOVES.known(actor.r, actor.spec)
    missing = [mid for mid in selected if mid not in known]
    if missing:
        raise ValueError("Personal Tutor selection was not permanently known at acquisition: " + missing[0])
    baseline = [{"value": mid, "authority": "actor.spec.moves", "baseline_index": known.index(mid)}
                for mid in selected]
    snapshot = {"canonical_values": known,
                "integrity": _digest("trainer-feature/permanent-known-snapshot/v1", known)}
    return [{**row, "snapshot_integrity": snapshot["integrity"]} for row in baseline], snapshot


def _martial_qualification(actor, provider, waivers):
    if provider is not actor:
        raise ValueError("Martial Artist acquisition provider must be the acquiring trainer")
    if waivers not in ((), []):
        raise ValueError("Martial Artist prerequisite waiver has no reviewed native authority")
    import skill_modifiers as SKILLS
    rank_name, dice, rank = SKILLS.rank(actor.r, actor, "전투")
    edges = actor.spec.get("edges", [])
    if not isinstance(edges, (list, tuple)):
        raise ValueError("trainer Edge ownership must be a sequence")
    basic = sum(value in (MARTIAL_PREREQUISITE, "기본 무술", "Basic Martial Arts") for value in edges)
    checks = [
        {"id": "trainer", "kind": "prerequisite", "state": "passed" if actor.kind == "trainer" else "denied",
         "observed": actor.kind, "reason": "Martial Artist requires an actual trainer"},
        {"id": "basic_martial_arts", "kind": "prerequisite", "state": "passed" if basic == 1 else "denied",
         "observed": {"owned_count": basic}, "reason": "Martial Artist requires exactly one acquired Basic Martial Arts Edge"},
        {"id": "combat", "kind": "prerequisite", "state": "passed" if rank >= 3 else "denied",
         "observed": {"rank_name": rank_name, "dice": dice, "rank": rank},
         "reason": "Martial Artist requires Novice Combat"},
    ]
    denied = next((row for row in checks if row["state"] != "passed"), None)
    if denied is not None:
        raise ValueError(denied["reason"])
    return {"schema": 1, "status": "qualified", "checks": checks, "waivers": []}


def _martial_ability_proof(rules, selected):
    domain = list(_validate_martial_ability_catalog(rules))
    return _martial_ability_evidence(selected, domain)


def _martial_ability_evidence(selected, domain):
    """Assemble immutable evidence after the caller validates the exact catalog."""
    expected = MARTIAL_ABILITY_BINDINGS[selected]
    snapshot = {
        "canonical_values": domain,
        "integrity": _digest("trainer-feature/martial-artist-ability-domain/v1", domain),
    }
    ability_source = ({
        "file": MARTIAL_ARTIST_SOURCE["file"],
        "lines": MARTIAL_ARTIST_SOURCE["span"],
        "sha256": MARTIAL_ARTIST_SOURCE["sha256"],
    } if expected["record"] is None else {
        "file": "input/db/abilities.csv",
        "record_span": [expected["record"], expected["record"]],
        "sha256": MARTIAL_ABILITY_SOURCE_SHA256,
    })
    proof = {
        "value": selected,
        "authority": "C04-098:selected_ability_domain",
        "printed": expected["printed"],
        "ability_title": expected["title"],
        "ability_source": ability_source,
        "snapshot_integrity": snapshot["integrity"],
    }
    return [proof], snapshot


def _intent(*, actor_id, feature_id, feature_instance_id, source, request_id,
            provider_id, adapter_id, selection_kind, selected_values, required_count, lifecycle_policy):
    return {
        "actor_id": actor_id,
        "feature_id": feature_id,
        "feature_instance_id": feature_instance_id,
        "source": deepcopy(source),
        "acquisition_request_id": request_id,
        "provider_id": provider_id,
        "adapter_id": adapter_id,
        "selection_kind": selection_kind,
        "selected_values": list(selected_values),
        "required_count": required_count,
        "lifecycle_policy": deepcopy(lifecycle_policy),
    }


def _projection_from_rows(rows):
    result = {}
    for row in rows:
        feature = result.setdefault(row["feature_id"], {})
        if row["feature_instance_id"] in feature:
            raise ValueError("duplicate selection-only Feature instance receipt")
        feature[row["feature_instance_id"]] = {
            "acquisition_request_id": row["acquisition_request_id"],
            "selection_kind": row["selection"]["kind"],
            "values": deepcopy(row["selection"]["values"]),
        }
    return result


def _seal(receipt):
    row = deepcopy(receipt)
    row["integrity_id"] = _digest("trainer-feature/acquisition-receipt/v1", row)
    return row


def _receipt_payload(receipt):
    payload = deepcopy(receipt)
    integrity = payload.pop("integrity_id", None)
    if integrity != _digest("trainer-feature/acquisition-receipt/v1", payload):
        raise ValueError("trainer Feature acquisition receipt integrity mismatch")
    return payload


def _validate_personal_tutor_receipt(actor, payload):
    if payload["adapter_id"] != PERSONAL_TUTOR_ADAPTER or payload["feature_id"] != PERSONAL_TUTOR:
        raise ValueError("Personal Tutor receipt requires its exact validator adapter and Feature")
    if actor.kind != "trainer":
        raise ValueError("Personal Tutor receipt belongs to an actual trainer")
    source = _source(actor.r, payload["source"].get("clause_id") if isinstance(payload["source"], dict) else None)
    if payload["source"] != source:
        raise ValueError("Personal Tutor receipt source provenance mismatch")
    provider = payload["provider"]
    if provider != {"actor_id": actor.entity_id, "mode": "self_acquisition"}:
        raise ValueError("Personal Tutor receipt provider provenance mismatch")
    qualification = payload["qualification"]
    hobbyist_waivers=qualification.get('waivers',[]) if isinstance(qualification,dict) else []
    if hobbyist_waivers:
        if type(hobbyist_waivers)is not list or len(hobbyist_waivers)!=1 or set(hobbyist_waivers[0])!={'hobbyist_provider'}:raise ValueError('exact acquired Dilettante Personal Tutor provider required')
        proof=hobbyist_waivers[0]['hobbyist_provider']
        __import__('hobbyist').validate_provider(actor,proof,False)
        if proof['child']!=PERSONAL_TUTOR or proof['kind']!='dilettante':raise ValueError('Personal Tutor skill waiver requires its actual chosen Dilettante receipt')
    if (type(qualification) is not dict or set(qualification) != {"schema", "status", "checks", "waivers"} or
            qualification["schema"] != 1 or qualification["status"] != "qualified" or
              type(qualification["checks"]) is not list or
            len(qualification["checks"]) != 2):
        raise ValueError("Personal Tutor qualification or waiver provenance mismatch")
    trainer, education = qualification["checks"]
    check_fields = {"id", "kind", "state", "observed", "reason"}
    if (type(trainer) is not dict or set(trainer) != check_fields or
            (trainer["id"], trainer["kind"], trainer["state"], trainer["observed"]) !=
            ("trainer", "prerequisite", "passed", "trainer")):
        raise ValueError("Personal Tutor trainer prerequisite provenance mismatch")
    observed = education.get("observed") if isinstance(education, dict) else None
    if (type(education) is not dict or set(education) != check_fields or
            (education["id"], education["kind"], education["state"]) !=
              ("general_education", "prerequisite", "waived" if hobbyist_waivers else "passed") or
            type(observed) is not dict or set(observed) != {"rank_name", "dice", "rank"} or
              type(observed["rank"]) is not int or observed["rank"] < (1 if hobbyist_waivers else 3)):
        raise ValueError("Personal Tutor General Education prerequisite provenance mismatch")
    selection = payload["selection"]
    values = selection["values"]
    if selection["kind"] != "canonical_move_id" or selection["required_count"] != 3 or any(
            actor.r.move_id(value) != value for value in values):
        raise ValueError("Personal Tutor requires three canonical move identities")
    proofs = selection["proofs"]
    if any(set(row) != {"value", "authority", "baseline_index", "snapshot_integrity"} or
           row["authority"] != "actor.spec.moves" or type(row["baseline_index"]) is not int or row["baseline_index"] < 0
           for row in proofs):
        raise ValueError("invalid acquisition-time permanent-known proof")
    snapshot = selection["acquisition_snapshot"]
    if (type(snapshot) is not dict or set(snapshot) != {"canonical_values", "integrity"} or
            type(snapshot["canonical_values"]) is not list or
            snapshot["integrity"] != _digest("trainer-feature/permanent-known-snapshot/v1", snapshot["canonical_values"]) or
            any(row["snapshot_integrity"] != snapshot["integrity"] for row in proofs) or
            any(row["baseline_index"] >= len(snapshot["canonical_values"]) or
                snapshot["canonical_values"][row["baseline_index"]] != row["value"] for row in proofs)):
        raise ValueError("permanent-known acquisition snapshot integrity mismatch")
    return source


def _validate_martial_artist_receipt(actor, payload):
    if payload["adapter_id"] != MARTIAL_ARTIST_ADAPTER or payload["feature_id"] != MARTIAL_ARTIST:
        raise ValueError("Martial Artist receipt requires its exact validator adapter and Class")
    if actor.kind != "trainer":
        raise ValueError("Martial Artist receipt belongs to an actual trainer")
    source = _martial_source(actor.r, payload["source"].get("clause_id") if isinstance(payload["source"], dict) else None)
    if payload["source"] != source:
        raise ValueError("Martial Artist receipt source provenance mismatch")
    if payload["provider"] != {"actor_id": actor.entity_id, "mode": "self_acquisition"}:
        raise ValueError("Martial Artist receipt provider provenance mismatch")
    qualification = payload["qualification"]
    if (type(qualification) is not dict or set(qualification) != {"schema", "status", "checks", "waivers"} or
            qualification["schema"] != 1 or qualification["status"] != "qualified" or
            qualification["waivers"] != [] or type(qualification["checks"]) is not list or
            len(qualification["checks"]) != 3):
        raise ValueError("Martial Artist qualification or waiver provenance mismatch")
    trainer, basic, combat = qualification["checks"]
    check_fields = {"id", "kind", "state", "observed", "reason"}
    if (type(trainer) is not dict or set(trainer) != check_fields or
            (trainer["id"], trainer["kind"], trainer["state"], trainer["observed"]) !=
            ("trainer", "prerequisite", "passed", "trainer")):
        raise ValueError("Martial Artist trainer prerequisite provenance mismatch")
    if (type(basic) is not dict or set(basic) != check_fields or
            (basic["id"], basic["kind"], basic["state"], basic["observed"]) !=
            ("basic_martial_arts", "prerequisite", "passed", {"owned_count": 1})):
        raise ValueError("Martial Artist Basic Martial Arts prerequisite provenance mismatch")
    observed = combat.get("observed") if isinstance(combat, dict) else None
    if (type(combat) is not dict or set(combat) != check_fields or
            (combat["id"], combat["kind"], combat["state"]) != ("combat", "prerequisite", "passed") or
            type(observed) is not dict or set(observed) != {"rank_name", "dice", "rank"} or
            type(observed["rank"]) is not int or observed["rank"] < 3):
        raise ValueError("Martial Artist Combat prerequisite provenance mismatch")
    selection = payload["selection"]
    values = selection["values"]
    if (selection["kind"] != "canonical_ability_id" or selection["required_count"] != 1 or
            len(values) != 1 or values[0] not in _validate_martial_ability_catalog(actor.r)):
        raise ValueError("Martial Artist requires one exact canonical Ability identity")
    proofs, expected_snapshot = _martial_ability_evidence(values[0], list(MARTIAL_ABILITY_BINDINGS))
    snapshot = selection["acquisition_snapshot"]
    if snapshot != expected_snapshot:
        raise ValueError("Martial Artist Ability domain snapshot integrity mismatch")
    proof = selection["proofs"][0]
    if proof != proofs[0]:
        raise ValueError("Martial Artist selected Ability proof differs from exact source")
    _martial_lifecycle(payload["lifecycle_policy"])
    return source


def _validate_receipt(actor, request_id, receipt):
    fields = {"schema", "basis", "receipt_id", "actor_id", "feature_id", "feature_instance_id",
              "source", "acquisition_request_id", "provider", "adapter_id", "qualification", "selection",
              "lifecycle_policy", "request_integrity", "committed", "integrity_id"}
    if type(receipt) is not dict or set(receipt) != fields:
        raise ValueError("exact trainer Feature acquisition receipt fields required")
    payload = _receipt_payload(receipt)
    if (payload["schema"] != SCHEMA or payload["basis"] != "trainer_feature_selection" or
            payload["committed"] is not True):
        raise ValueError("committed trainer Feature selection receipt required")
    for value, label in ((request_id, "request identity"), (payload["receipt_id"], "receipt identity"),
                         (payload["actor_id"], "actor identity"), (payload["feature_id"], "feature identity"),
                         (payload["feature_instance_id"], "feature instance identity"),
                         (payload["acquisition_request_id"], "acquisition request identity")):
        _text(value, label)
    if request_id != payload["acquisition_request_id"] or payload["actor_id"] != actor.entity_id:
        raise ValueError("trainer Feature receipt identity disagrees with its owner or request key")
    if payload["receipt_id"] != "trainer-feature-selection/" + request_id:
        raise ValueError("trainer Feature receipt identity is not derived from its request")
    _text(payload["adapter_id"], "selection validator adapter identity")
    source = payload["source"]
    if (type(source) is not dict or set(source) != {"clause_id", "file", "sha256", "version"} or
            any(type(source[key]) is not str or not source[key] for key in ("clause_id", "file", "sha256")) or
            type(source["version"]) is not int or source["version"] < 1):
        raise ValueError("exact source clause, file, hash and version required")
    provider = payload["provider"]
    if (type(provider) is not dict or set(provider) != {"actor_id", "mode"} or
            type(provider["actor_id"]) is not str or not provider["actor_id"] or
            type(provider["mode"]) is not str or not provider["mode"]):
        raise ValueError("trainer Feature receipt provider provenance mismatch")
    qualification = payload["qualification"]
    if (type(qualification) is not dict or set(qualification) != {"schema", "status", "checks", "waivers"} or
            qualification["schema"] != 1 or qualification["status"] != "qualified" or
            type(qualification["checks"]) is not list or not qualification["checks"] or
            type(qualification["waivers"]) is not list or
            any(type(row) is not dict for row in qualification["checks"] + qualification["waivers"])):
        raise ValueError("trainer Feature receipt qualification or waiver provenance mismatch")
    selection = payload["selection"]
    if type(selection) is not dict or set(selection) != {"kind", "required_count", "values", "proofs", "acquisition_snapshot"}:
        raise ValueError("exact selection-only Feature evidence required")
    _text(selection["kind"], "selection kind")
    values = selection["values"]
    if (type(selection["required_count"]) is not int or selection["required_count"] < 1 or
            type(values) is not list or len(values) != selection["required_count"] or
            any(type(value) is not str or not value for value in values) or len(set(values)) != len(values)):
        raise ValueError("canonical distinct selected values must match the required count")
    proofs = selection["proofs"]
    if (type(proofs) is not list or len(proofs) != len(values) or
            any(type(row) is not dict for row in proofs) or [row.get("value") for row in proofs] != values):
        raise ValueError("each selected value requires acquisition-time evidence")
    if type(selection["acquisition_snapshot"]) is not dict:
        raise ValueError("selection adapter acquisition snapshot required")
    import signature_moves as SIGNATURE
    import mentor_csv as MENTOR_CSV
    import class_passive_combat as CLASS_PASSIVE
    import capture_techniques as CAPTURE
    adapters = {
        PERSONAL_TUTOR_ADAPTER: _validate_personal_tutor_receipt,
        MARTIAL_ARTIST_ADAPTER: _validate_martial_artist_receipt,
        SIGNATURE.ADAPTER: SIGNATURE.validate_receipt,
        MENTOR_CSV.ADAPTER: MENTOR_CSV.validate_receipt,
        CLASS_PASSIVE.SPECIES_SAVANT_ADAPTER: CLASS_PASSIVE.validate_species_savant_receipt,
        CAPTURE.ADAPTER: CAPTURE.validate_receipt,
    }
    validator = adapters.get(payload["adapter_id"])
    if validator is None:
        raise ValueError("unknown selection-only Feature validator adapter")
    source = validator(actor, payload)
    lifecycle = (_martial_lifecycle if payload["adapter_id"] in (MARTIAL_ARTIST_ADAPTER, CLASS_PASSIVE.SPECIES_SAVANT_ADAPTER, CAPTURE.ADAPTER) else _lifecycle)(
        payload["lifecycle_policy"]
    )
    intent = _intent(actor_id=payload["actor_id"], feature_id=payload["feature_id"],
        feature_instance_id=payload["feature_instance_id"], source=source, request_id=request_id,
        provider_id=provider["actor_id"], adapter_id=payload["adapter_id"],
        selection_kind=selection["kind"], selected_values=values,
        required_count=selection["required_count"], lifecycle_policy=lifecycle)
    if payload["adapter_id"] == SIGNATURE.ADAPTER:
        intent["stat_choice"] = selection["acquisition_snapshot"]["stat"]
    if payload["adapter_id"] == CAPTURE.ADAPTER:
        intent["capture_choices"] = [proof["choice"] for proof in selection["proofs"]]
    if payload["request_integrity"] != _digest("trainer-feature/acquisition-request/v1", intent):
        raise ValueError("trainer Feature acquisition request integrity mismatch")
    return receipt


def _active_rows(actor):
    import trainer_retraining as RETRAINING
    retired = RETRAINING.retired_receipts(actor)
    return [row for row in actor.spec.get(LEDGER_KEY, {}).values() if row['receipt_id'] not in retired]


def validate_actor(actor):
    import native_acquisition_adapters as NATIVE
    NATIVE.validate_actor(actor)
    _validate_static_acquisitions(actor)
    ledger = actor.spec.get(LEDGER_KEY, {})
    projection = actor.spec.get(PROJECTION_KEY, {})
    if type(ledger) is not dict or type(projection) is not dict:
        raise ValueError("trainer Feature acquisition ledger and projection must be mappings")
    instances = set()
    rows = []
    import trainer_retraining as RETRAINING
    retired = RETRAINING.retired_receipts(actor)
    for request_id, receipt in ledger.items():
        _validate_receipt(actor, request_id, receipt)
        key = (receipt["feature_id"], receipt["feature_instance_id"])
        if key in instances:
            raise ValueError("trainer Feature instance cannot be acquired or reselected twice")
        instances.add(key)
        fields = ("classes", "feats") if receipt["feature_id"].startswith("class/") else ("feats",)
        count = sum(actor.spec.get(field, []).count(receipt["feature_id"]) for field in fields)
        expected_count = 0 if receipt['receipt_id'] in retired else 1
        if receipt["adapter_id"] == "trainer-feature/capture-techniques/v1":
            expected_count = int(any(row["feature_id"] == receipt["feature_id"] and row["receipt_id"] not in retired for row in ledger.values()))
        if count != expected_count:
            raise ValueError("selection receipt requires one exact owned trainer Feature or Class")
        if receipt['receipt_id'] not in retired:
            rows.append(receipt)
    if projection != _projection_from_rows(rows):
        raise ValueError("trainer Feature selection projection must derive exactly from committed receipts")
    import capture_techniques as CAPTURE
    CAPTURE.validate_actor(actor)
    return True


def receipts(actor):
    validate_actor(actor)
    ledger = actor.spec.get(LEDGER_KEY, {})
    import trainer_retraining as RETRAINING
    retired = RETRAINING.retired_receipts(actor)
    return [dict(deepcopy(ledger[key]), state='withdrawn') if ledger[key]['receipt_id'] in retired
            else deepcopy(ledger[key]) for key in sorted(ledger)] + __import__('native_acquisition_adapters').receipts(actor)


def projection(actor, feature_id=None):
    validate_actor(actor)
    value = deepcopy(actor.spec.get(PROJECTION_KEY, {}))
    if feature_id is None:
        return value
    _text(feature_id, "feature identity")
    return value.get(feature_id, {})


def selected_values(actor, feature_id, feature_instance_id):
    rows = projection(actor, feature_id)
    row = rows.get(feature_instance_id)
    if row is None:
        raise ValueError("committed selection-only Feature instance required")
    return tuple(row["values"])


def martial_ability_source(actor):
    return "feature:" + actor.entity_id + ":" + MARTIAL_ARTIST


def martial_ability(actor, feature_instance_id="class/무술가:1"):
    """Return the exact acquired style only while its native Ability source exists."""
    selected = selected_values(actor, MARTIAL_ARTIST, feature_instance_id)
    if len(selected) != 1 or selected[0] not in _validate_martial_ability_catalog(actor.r):
        raise ValueError("committed Martial Artist Ability selection required")
    uid = selected[0]
    expected = MARTIAL_ABILITY_BINDINGS[uid]
    source = actor.spec.get("state_grants", {}).get("sources", {}).get(martial_ability_source(actor))
    if (not isinstance(source, dict) or source.get("kind") != "feature" or
            source.get("owner_id") != actor.entity_id or source.get("lifetime") != "while_owned" or
            source.get("rule_id") != MARTIAL_ARTIST or source.get("tutor_points") != 0 or
            source.get("grants", {}).get("abilities") != [expected["title"]]):
        raise ValueError("Martial Artist selected Ability requires its exact while-owned native source")
    import ability_transitions as ABILITIES
    if uid not in ABILITIES.known(actor):
        raise ValueError("Martial Artist selected Ability is not present in native Ability state")
    return uid


def acquire_martial_artist(engine, actor, *, acquisition_request_id, selected_ability,
                           source_clause_id="C04-098", feature_instance_id="class/무술가:1",
                           provider=None, waivers=(), lifecycle_policy=None):
    """Acquire Martial Artist and its one exact selected Ability in one commit."""
    import world_entities as WORLD
    import state_grants as STATE
    provider = actor if provider is None else provider
    WORLD.require_actors(engine, actor, provider)
    _text(acquisition_request_id, "acquisition request identity")
    _text(feature_instance_id, "feature instance identity")
    lifecycle = _martial_lifecycle(lifecycle_policy)
    source = _martial_source(engine.r, source_clause_id)
    selected = _canonical_martial_ability(engine.r, selected_ability)
    if provider is not actor:
        raise ValueError("Martial Artist acquisition provider must be the acquiring trainer")
    if waivers not in ((), []):
        raise ValueError("Martial Artist prerequisite waiver has no reviewed native authority")
    intent = _intent(actor_id=actor.entity_id, feature_id=MARTIAL_ARTIST,
        feature_instance_id=feature_instance_id, source=source, request_id=acquisition_request_id,
        provider_id=provider.entity_id, adapter_id=MARTIAL_ARTIST_ADAPTER,
        selection_kind="canonical_ability_id", selected_values=[selected],
        required_count=1, lifecycle_policy=lifecycle)
    request_integrity = _digest("trainer-feature/acquisition-request/v1", intent)
    validate_actor(actor)
    existing = actor.spec.get(LEDGER_KEY, {}).get(acquisition_request_id)
    if existing is not None:
        if existing["request_integrity"] != request_integrity:
            raise ValueError("acquisition request identity was replayed with a different payload")
        martial_ability(actor, feature_instance_id)
        return deepcopy(existing)
    if actor.spec.get(LEDGER_KEY) and any(
            row["feature_id"] == MARTIAL_ARTIST for row in actor.spec[LEDGER_KEY].values()):
        raise ValueError("Martial Artist selection is immutable; reacquisition needs a new reviewed source policy")
    classes = actor.spec.get("classes", [])
    feats = actor.spec.get("feats", [])
    if not isinstance(classes, list) or not isinstance(feats, list):
        raise ValueError("trainer Class and Feature ownership must be mutable lists")
    aliases = {MARTIAL_ARTIST, "무술가", "Martial Artist"}
    if any(value in aliases for value in [*classes, *feats]):
        raise ValueError("existing unreceipted Martial Artist cannot be claimed retroactively")
    qualification = _martial_qualification(actor, provider, waivers)
    proofs, snapshot = _martial_ability_proof(engine.r, selected)
    receipt = _seal({
        "schema": SCHEMA,
        "basis": "trainer_feature_selection",
        "receipt_id": "trainer-feature-selection/" + acquisition_request_id,
        "actor_id": actor.entity_id,
        "feature_id": MARTIAL_ARTIST,
        "feature_instance_id": feature_instance_id,
        "source": source,
        "acquisition_request_id": acquisition_request_id,
        "provider": {"actor_id": provider.entity_id, "mode": "self_acquisition"},
        "adapter_id": MARTIAL_ARTIST_ADAPTER,
        "qualification": qualification,
        "selection": {"kind": "canonical_ability_id", "required_count": 1,
                      "values": [selected], "proofs": proofs, "acquisition_snapshot": snapshot},
        "lifecycle_policy": lifecycle,
        "request_integrity": request_integrity,
        "committed": True,
    })
    ability_title = MARTIAL_ABILITY_BINDINGS[selected]["title"]

    def apply(staged_engine, staged_actor):
        ledger = staged_actor.spec.setdefault(LEDGER_KEY, {})
        if acquisition_request_id in ledger:
            raise ValueError("acquisition request identity already committed")
        if any(row.get("feature_id") == MARTIAL_ARTIST for row in ledger.values()):
            raise ValueError("Martial Artist selection cannot be replaced")
        staged_actor.spec.setdefault("classes", []).append(MARTIAL_ARTIST)
        ledger[acquisition_request_id] = deepcopy(receipt)
        staged_actor.spec[PROJECTION_KEY] = _projection_from_rows(_active_rows(staged_actor))
        STATE.grant(staged_actor, "abilities", ability_title, martial_ability_source(staged_actor),
                    "feature", owner_id=staged_actor.entity_id, lifetime="while_owned",
                    rule_id=MARTIAL_ARTIST, tutor_points=0)
        staged_engine.register_abilities_one(staged_actor, ability_title)
        __import__('static_feature_state_grants').register_all(staged_engine,staged_actor)
        validate_actor(staged_actor)
        if martial_ability(staged_actor, feature_instance_id) != selected:
            raise ValueError("Martial Artist selected Ability did not materialize")
        return deepcopy(receipt)

    return STATE.transition(engine, actor, apply)


def acquire_personal_tutor(engine, actor, *, acquisition_request_id, selected_values,
                            source_clause_id, feature_instance_id="feat/개인-지도:1",
                            provider=None, waivers=(), lifecycle_policy=None):
    """Acquire Personal Tutor and its three locked moves in one native commit."""
    import world_entities as WORLD
    import state_grants as STATE
    provider = actor if provider is None else provider
    WORLD.require_actors(engine, actor, provider)
    _text(acquisition_request_id, "acquisition request identity")
    _text(feature_instance_id, "feature instance identity")
    lifecycle = _lifecycle(lifecycle_policy)
    source = _source(engine.r, source_clause_id)
    selected = _canonical_moves(engine.r, selected_values)
    if provider is not actor:
        raise ValueError("Personal Tutor acquisition provider must be the acquiring trainer")
    if waivers not in ((), []):
        raise ValueError("Personal Tutor prerequisite waiver has no reviewed native authority")
    intent = _intent(actor_id=actor.entity_id, feature_id=PERSONAL_TUTOR,
        feature_instance_id=feature_instance_id, source=source, request_id=acquisition_request_id,
        provider_id=provider.entity_id, adapter_id=PERSONAL_TUTOR_ADAPTER,
        selection_kind="canonical_move_id", selected_values=selected,
        required_count=3, lifecycle_policy=lifecycle)
    request_integrity = _digest("trainer-feature/acquisition-request/v1", intent)
    validate_actor(actor)
    existing = actor.spec.get(LEDGER_KEY, {}).get(acquisition_request_id)
    if existing is not None:
        if existing["request_integrity"] != request_integrity:
            raise ValueError("acquisition request identity was replayed with a different payload")
        return deepcopy(existing)
    if actor.spec.get(LEDGER_KEY):
        if any(row["feature_id"] == PERSONAL_TUTOR for row in actor.spec[LEDGER_KEY].values()):
            raise ValueError("Personal Tutor selection is immutable; reselection or reacquisition needs an explicit source policy")
    names = actor.spec.get("feats", [])
    if not isinstance(names, list):
        raise ValueError("trainer Feature ownership must be a mutable list")
    if PERSONAL_TUTOR in names or any(name in ("개인 지도", "Tutoring") for name in names):
        raise ValueError("existing unreceipted Personal Tutor cannot be claimed retroactively")
    qualification = _personal_tutor_qualification(actor, provider, waivers)
    proofs, snapshot = _permanent_move_proofs(actor, selected)
    receipt = _seal({
        "schema": SCHEMA,
        "basis": "trainer_feature_selection",
        "receipt_id": "trainer-feature-selection/" + acquisition_request_id,
        "actor_id": actor.entity_id,
        "feature_id": PERSONAL_TUTOR,
        "feature_instance_id": feature_instance_id,
        "source": source,
        "acquisition_request_id": acquisition_request_id,
        "provider": {"actor_id": provider.entity_id, "mode": "self_acquisition"},
        "adapter_id": PERSONAL_TUTOR_ADAPTER,
        "qualification": qualification,
        "selection": {"kind": "canonical_move_id", "required_count": 3,
                      "values": selected, "proofs": proofs, "acquisition_snapshot": snapshot},
        "lifecycle_policy": lifecycle,
        "request_integrity": request_integrity,
        "committed": True,
    })

    def apply(_staged_engine, staged_actor):
        ledger = staged_actor.spec.setdefault(LEDGER_KEY, {})
        if acquisition_request_id in ledger:
            raise ValueError("acquisition request identity already committed")
        if any(row.get("feature_id") == PERSONAL_TUTOR for row in ledger.values()):
            raise ValueError("Personal Tutor selection cannot be replaced")
        staged_actor.spec.setdefault("feats", []).append(PERSONAL_TUTOR)
        ledger[acquisition_request_id] = deepcopy(receipt)
        staged_actor.spec[PROJECTION_KEY] = _projection_from_rows(_active_rows(staged_actor))
        validate_actor(staged_actor)
        return deepcopy(receipt)

    return STATE.transition(engine, actor, apply)
