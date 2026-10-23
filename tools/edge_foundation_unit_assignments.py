"""Reviewed subunit assignments for source consumers. Order is source-record order."""
CODES=dict(x.split('=') for x in '''SP=source_policy.selection SA=source_policy.adjudication OI=object_lifecycle.identity OL=object_lifecycle.lifecycle TX=atomic_transition.commit RP=atomic_transition.replay AQ=acquisition.qualification AR=acquisition.receipt AW=acquisition.withdrawal CD=composition.derive CR=composition.reconcile PL=roll_context.plan RR=roll_context.resolve RA=resources.actions RF=resources.frequency ED=events.dispatch ET=events.trace AC=activity.clock AJ=activity.job GS=growth.stats GM=growth.milestones LG=learning.grant LS=learning.slots CH=combat.hit DD=combat.damage CP=combat.capture EA=effects.apply EL=effects.lifetime ER=effects.recovery MP=movement.permission MV=movement.path MF=movement.forced MO=maneuvers.opposed MG=maneuvers.grapple FR=crafting.recipe FP=crafting.product CG=cultivation.growth CY=cultivation.harvest TE=training.eligibility TR=training.rewards CE=creation.egg CF=creation.fossil PO=perception.observe PC=perception.communicate CM=control.mount CV=control.vehicle CX=control.remote NC=network.connection NI=network.integrity RH=repair.restore RB=repair.breach EN=environment.derive EC=environment.change ID=initiative.derive IS=initiative.schedule SL=scripting.load SX=scripting.execute'''.split())
CONSUMER={
'alluring':'RF|RR PO|LG CD',
'stealth':'PO MV|CH EN|CH ED',
'telekinetic':'MP PL|RR|MP OI|CH PL|DD|MO PL|MO MF PL|LG CD',
'telepathy':'PC PL|PC|PC PL|PC OI|PC RR|PC EL PL|ED ET|ED',
'threaded':'RA|OI MP|MF|CH|CH RR|LG CD',
'tracker':'PO RR|PO RR|PO RR|PL RR|RF AC|LG CD',
'tremorsense':'PO|PO OI|PO|PO OI',
'underdog_identity':'AQ OI|GS AQ',
'augmentation_shock':'EA EL|PL CH CD|SA EL|MP PL|EA SP|EA',
'vehicle_permission':'CV OI|CV RA|CV OI|CV CX',
'network':'NC OI|NC AQ|NC RA AC|NC AQ|NC NI|CX|NI GS|NI GS|NI NC|SA EL|NI ER NC',
'dream_machine':'CV OI|SA PC|PL RR|SA RR|GM|RA|PL RR|AJ RR|AC AJ|PL RR|SA CR',
'disarm':'MO CH RA|MO RR|MO OL',
'dirty_trick':'MO CH RA|RF|MO RR EA EL PL|MO RR EA EL|MO RR EA EL ID',
'manipulate':'MO CH RA OI|RF|MO RR EA RA EL|MO RR EA EL|MO RR ER RA EL',
'push':'MO CH RA|MO RR|MP|MF|MO MV RA',
'trip':'MO CH RA|MO RR|MO EA',
'grapple':'MG CH RA|MG RR|MG|MG EA MP CH|MG RA RR|MG MP|MG RA RR DD MF',
'breather':'RA RR|MV MP|EA EL|GS ER|ER OI MP|RA MP|RR|MV MP|EA EL CH ER|RR ER',
'pokemon_stats':'GS|GS|GS|GS|GS|GS SP',
'pokemon_learning':'LG GM|LG LS|LS|LS|LS|LG SP',
'pokemon_progression_evolution':'GM|GS GM|GM|GM LG|GM AR|AW CR|GS GM|LG LS GM|LG GM',
'training':'TE AJ|AJ TR LG|TE RF|TE RF|TR PL',
'mount':'CM OI SA|CM RA RR|CM RA MP|CM MP|CM RA MP|CM ED RR|CX',
'digestion':'FP EA AJ|EA|ED EA RA|EA|ER SP',
'cultivation':'CG OI|CG AC|CY RF|CY|CY EN|CG EN|CG EL|CY RR|CY FP|FR',
'craft_resources':'FR OI|FR|FR|FP OL|FR|FP|OI',
'dowsing':'AJ AC|RF|PL|PL EN|PL|RR FP|RR FP',
'poffin_contest':'GS|GS|GS GM|FP GS|RA RF|PL|RR GS|RR GS',
'poffin_recipe':'FR OI|FR|FP|FR FP',
'breeding':'CE AR|CE RR|CE LS|GM LG|CE SA|CE RR SA|CE RR SA|CE AC',
'fossil':'CF OI|CF AQ|CF CE|CF SA LG|CF SA',
'bait':'OI|AJ RR|RF FP|PO SA OL|CH RA|RR RA|OL ED',
'pokebot_base':'OI GM GS|DD MO OI|EA OI|OI RA|GS MP PL|EN|RH ER|OL FP|OI CD|CV RA',
'vehicle_base':'GS ID CV|EA|OL FP|RH AJ|DD|RB ED|RB EA|RB OL|RB AJ',
'vehicle_operation':'CV RA RR SA|CV RA|CV RA|RH RB RA RR',
'shock_trigger':'DD ED EA|ED EA|DD EA|ED EA',
'trainer_entitlements':'GM AR|AQ|GM AQ|AQ AR|GM AR|RP GM',
'trainer_retraining':'AW RA|AW GM|AW AQ|AW|AW SA',
'gravity_interval':'EN AQ|EN CD|EN OI|EC AJ',
'look_and_learn':'AQ AR|AQ AW|RF AQ AR',
'study_manual':'AQ AJ RA|EL RA CR|PL|CD PL',
'doctor_gifts':'AQ AR|AQ|AR',
'aura_pulse_consumer':'PC|PC',
'aura_communication_block':'PC PO CD|AW AR',
'arcane_training_consumer':'AQ DD|AQ DD CH|MO PL OI',
'ball_manual_product':'FR AQ RA EL|FP AR CH EL',
'expand_horizons_provider':'AQ RA AR RF|SP AQ',
'jailbreaker_permission':'AQ FR AJ|AQ FR',
}
ORIGINAL={
'gravity_original':'EN SP|EN PL CH|EN MP CH|EN SP|EN MP|EN MP|MF IS|EN MP',
'network_original':'NI GS|NC AQ RA AC|NC NI|NI NC EL SA|NI DD RR|NI ED|NI SA|NI CX',
}
# IDs are stable occurrence positions from the inspected search file; source anchors
# are used in the resulting plan, not these local shorthand positions.
NAMED={
5:'CH PL',19:'FR FP AQ',37:'AR RF',47:'FR PL RA EL CH DD FP',48:'CG LG FR FP RF',49:'CF CE AR LG LS FP EA DD',68:'CD EL',85:'CH RA PL',86:'CH OL',87:'CP SP RR',88:'CP SP RR',91:'CH PL',95:'CX RA MP',98:'ER ED EL',99:'ER ED',100:'ER EL ED SP',110:'ED RA CX',112:'CP SP',113:'CH RA PL',114:'CH OL',115:'CX MV',116:'CP OI',117:'CP OI',119:'FR SP',120:'CP SP',121:'CP SP',122:'FP EL RF RA CP',123:'CH SP',124:'PC',125:'CE GS GM CX EA TR',127:'DD ED CP',149:'CD AQ',164:'PO PC CD AW',165:'AR SA',187:'FR AQ',188:'FP CH CD EL',207:'AQ DD CH MO PL',209:'AQ CD',238:'CH DD RA',241:'FP RA CD',243:'CH MV ED',244:'ED CH',245:'CP CX CD',246:'FP EA ED',248:'CP EA ED',249:'OI OL CX RF',250:'DD ED',252:'FP RA CD',253:'ED CP',254:'CX PC',256:'OI CX AJ ED',258:'PO OI',261:'CP SP',262:'CP SP',263:'SA SP',264:'RA CP OI',266:'CH EA EL',267:'CH EA SP',268:'CH EA EL ED',271:'CD SP',273:'AQ CD',277:'FR AQ',279:'FR AQ',280:'FR CD',281:'FP CD',282:'ED CH',283:'CH ED RF',285:'EN CP CD',286:'EN CP CD',
}

def decode(text):return [CODES[x] for x in text.split()]

def reviewed_assignments(discovery,search):
 result={}
 for rows,table,prefix in [(discovery['consumer_dependency_reviews'],CONSUMER,'consumer'),(discovery['original_source_dependency_reviews'],ORIGINAL,'original')]:
  assert {r['id'] for r in rows}==set(table),(prefix,'source sections changed; review assignments')
  for row in rows:
   cells=table[row['id']].split('|');assert len(cells)==len(row['required_behaviors']),row['id']
   for i,cell in enumerate(cells):result[f"{prefix}/{row['id']}/{i}"]=decode(cell)
 expected={i for i,r in enumerate(search['rows']) if r['review']['classification']=='consumer_or_product_dependency'}
 assert set(NAMED)==expected,'Search occurrences changed; source mapping needs review'
 for i,row in enumerate(search['rows']):
  ref='named/'+row['file']+':L'+str(row['line'])
  if i in NAMED:result[ref]=decode(NAMED[i])
  elif row['review']['classification']=='prerequisite_dependency':result[ref]=decode('AQ AW SP')
 for row in discovery['english_alias_search']['rows']:
  if row.get('candidate_contracts'):result['alias/'+row['file']+':L'+str(row['line'])]=decode('AQ FR SP')
 return result
