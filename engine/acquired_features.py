"""Acquired class/feature instance projection, not category-6 acquisition approval.

ch03:603/607/609 and ch04:12-15. Existing classes/feats are references to
acquired sources; branch choices determine distinct class-slot instances.
"""
import acquisition_qualification as Q
import json
import re
from functools import lru_cache

BRANCH_CLASSES={
    "class/스타일-전문가":("아름다움","근사함","귀여움","슬기로움","강인함"),
    "class/스탯-에이스":("atk","def","spa","spd","spe","공격","방어","특수공격","특수방어","스피드"),
    "class/타입-에이스":None,
    "class/연구원":None,
}
STAT_ALIASES=dict(zip(("공격","방어","특수공격","특수방어","스피드"),("atk","def","spa","spd","spe")))
RUNE_CLASS='supp-fantasy/룬마스터'
BERSERKER_CLASS='supp-fantasy/버서커'
ARCANIST_CLASS='supp-fantasy/아케니스트'
MARKSMAN_CLASS='supp-fantasy/명사수'
FORTRESS_CLASS='supp-fantasy/포트리스'
SKIRMISHER_CLASS='supp-fantasy/척후'


@lru_cache(maxsize=16)
def _prefix_ids(keys,prefix,rune_class,berserker_class,arcanist_class=ARCANIST_CLASS,marksman_class=MARKSMAN_CLASS,fortress_class=FORTRESS_CLASS,skirmisher_class=SKIRMISHER_CLASS):
    """Index immutable IDs, preserving the local supplemental class routing."""
    return tuple(uid for uid in keys if (prefix=='class/' if uid in (rune_class,berserker_class,arcanist_class,marksman_class,fortress_class,skirmisher_class) else uid.startswith(prefix)))


def _names(actor,prefix):
    units=actor.r.selection.units
    # Re-snapshot keys on every call: additions, removals and order changes are
    # immediately visible. Exact builtins make this path free of user callbacks;
    # custom mappings/strings retain the original iteration and error behavior.
    if type(units) is dict and type(prefix) is str and all(type(value)is str for value in (RUNE_CLASS,BERSERKER_CLASS,ARCANIST_CLASS,MARKSMAN_CLASS,FORTRESS_CLASS,SKIRMISHER_CLASS)):
        keys=tuple(units)
        if set(map(type,keys)) <= {str}:
            result={}
            for uid in _prefix_ids(keys,prefix,RUNE_CLASS,BERSERKER_CLASS,ARCANIST_CLASS,MARKSMAN_CLASS,FORTRESS_CLASS,SKIRMISHER_CLASS):
                unit=units[uid]
                if type(unit) is not dict:break
                title,eng=unit.get("title"),unit.get("eng")
                if not (title is None or type(title) is str):break
                if not (eng is None or type(eng) is str):break
                for name in (uid,title,eng):
                    if name:result.setdefault(name,[]).append(uid)
            else:
                return result
    result={}
    for uid,unit in units.items():
        if uid in (RUNE_CLASS,BERSERKER_CLASS,ARCANIST_CLASS,MARKSMAN_CLASS,FORTRESS_CLASS,SKIRMISHER_CLASS):
            if prefix!='class/':continue
        elif not uid.startswith(prefix):continue
        for name in (uid,unit.get("title"),unit.get("eng")):
            if name:result.setdefault(name,[]).append(uid)
    return result


def _resolve(actor,value,prefix,names=None):
    if not isinstance(value,str):raise ValueError("acquired feature identity must be text")
    names=_names(actor,prefix) if names is None else names
    matches=names.get(value,[])
    if len(matches)!=1:raise ValueError("unambiguous acquired feature source required: "+value)
    uid=matches[0]
    supported=uid in ('feat/훈련-상황','feat/작열','feat/패싱-왈츠')
    if actor.r._selected_rule(uid,supports_versions=supported)!=uid:raise ValueError("selected feature variant needs its own instance policy")
    if uid=='feat/훈련-상황':__import__('athlete').regime_source(actor.r)
    if uid=='feat/작열':__import__('pokemon_move_edges').incandescence_source(actor.r)
    if uid=='feat/패싱-왈츠':__import__('dancer').waltz_source(actor.r)
    return uid


def _branch_values(actor,uid):
    choices=actor.spec.get("feature_choices",{})
    if not isinstance(choices,dict):raise ValueError("acquired feature choices must be a mapping")
    if uid=="class/연구원":
        import researcher_features as R
        fields=R.research_fields(actor)
        # Each explicit two-field acquisition is one class slot. The legacy
        # two-field record is exactly one acquisition, never a second copy.
        raw=choices.get(uid)
        return tuple(tuple(R.field_id(v) for v in pair) for pair in raw) if raw is not None else (tuple(fields),)
    values=choices.get(uid)
    if not isinstance(values,(list,tuple)) or not values:raise ValueError("actual distinct class branch choices required: "+uid)
    if uid=="class/스탯-에이스":values=[STAT_ALIASES.get(value,value) for value in values]
    allowed=BRANCH_CLASSES[uid]
    if uid=="class/타입-에이스":allowed=tuple(value for value in actor.r.mech("combat/type-chart")["attack_vs_defense"] if value not in ("None","에러"))
    Q.require(uid,"native","owned",[Q.check("branch_domain","selection",
        all(isinstance(v,str) and bool(v) and (allowed is None or v in allowed) for v in values),
        "class branch choice outside its source domain: "+uid)])
    Q.require(uid,"native","owned",[Q.check("distinct_branches","repeat",
        len(set(values))==len(values),"repeated acquired class branch: "+uid)])
    return tuple(values)


def class_instances(actor):
    if actor.kind!="trainer":return ()
    import native_acquisition_adapters as NATIVE
    synthetic=NATIVE.class_instances(actor)
    synthetic_aliases={value for definition in NATIVE.DEFINITIONS.values() if definition.get('class_slot') for value in definition['owned_aliases']}
    names=_names(actor,"class/");selected=[]
    for field in ("classes","feats"):
        values=actor.spec.get(field,[])
        if not isinstance(values,(list,tuple)):raise ValueError("acquired classes/features must be lists")
        local=set()
        for value in values:
            if value in synthetic_aliases:continue
            if field=="feats" and value not in names:continue
            uid=_resolve(actor,value,"class/",names)
            if uid in local:raise ValueError("duplicate class reference needs one explicit acquired branch list")
            local.add(uid)
            if uid not in selected:selected.append(uid)
    result=[]
    for uid in selected:
        branches=_branch_values(actor,uid) if uid in BRANCH_CLASSES else (None,)
        for branch in branches:
            result.append({"source_id":uid,"branch":branch,"instance_key":uid+":"+json.dumps(branch,ensure_ascii=False,sort_keys=True)})
    result.extend(synthetic)
    Q.require("class/instances","native","owned",[Q.check("capacity","capacity",len(result)<=4,"acquired class instances exceed four slots")])
    return tuple(result)


def validate_class_slots(actor):
    class_instances(actor)
    if actor.kind=="trainer":feature_instances(actor)
    import trainer_retraining as RETRAINING
    RETRAINING.validate_actor(actor)
    import trainer_feature_acquisition as TRAINER_FEATURES
    TRAINER_FEATURES.validate_actor(actor)
    __import__('skirmisher').validate_actor(actor)
    return True


def selection_only_projection(actor,feature_id=None):
    """Current selection view derived only from committed acquisition receipts."""
    import trainer_feature_acquisition as TRAINER_FEATURES
    return TRAINER_FEATURES.projection(actor,feature_id)


def selected_at_acquisition(actor,feature_id,feature_instance_id):
    """Return immutable selected values without consulting a later live sheet."""
    import trainer_feature_acquisition as TRAINER_FEATURES
    return TRAINER_FEATURES.selected_values(actor,feature_id,feature_instance_id)


def feature_rank(actor,source_id):
    uid=_resolve(actor,source_id,"feat/")
    names=_names(actor,"feat/")
    acquired=[]
    for value in actor.spec.get("feats",[]):
        if value in names:acquired.append(_resolve(actor,value,"feat/",names))
    if uid not in acquired:raise ValueError("actual acquired ranked feature required")
    tags=actor.r.selection.units[uid].get("tags",[])
    maxima=[int(match[1] or match[2]) for tag in tags if (match:=re.fullmatch(r"(?:랭크\s*(\d+)|(\d+)\s*랭크)",tag))]
    if uid==__import__('arcanist').SIGNATURE:maxima=[2]
    ranks=actor.spec.get("feat_ranks",{})
    if not isinstance(ranks,dict):raise ValueError("acquired feature ranks must be a mapping")
    rank=ranks.get(uid,1)
    if type(rank) is not int:raise ValueError("acquired feature rank exceeds source maximum")
    Q.require(uid,"native","owned",[Q.rank_limit("rank",rank,1,maxima[0] if maxima else 1,"acquired feature rank exceeds source maximum")])
    return rank


def feature_instances(actor,*,class_source=None,exclude=()):
    """Count each acquired rank/branch without treating choices as new grants."""
    names=_names(actor,"feat/");result=[];seen=set()
    class_title=None
    if class_source is not None:
        class_source=_resolve(actor,class_source,"class/")
        class_title=actor.r.selection.units[class_source]["title"]
    for raw in actor.spec.get("feats",[]):
        if raw not in names:continue
        uid=_resolve(actor,raw,"feat/",names)
        if uid in seen:raise ValueError("duplicate feature reference requires explicit rank/branch state")
        seen.add(uid)
        if uid in exclude:continue
        unit=actor.r.selection.units[uid]
        if class_title is not None and not any(part.split("(",1)[0].strip()==class_title for part in unit.get("source",{}).get("path",[])):
            import trainer_feature_acquisition as FEATURES
            definition=FEATURES.STATIC_FEATURES.get(uid,{})
            if definition.get('class_template')!=class_source:continue
            FEATURES._static_source(actor.r,uid)
        choices=(None,)
        if "분기" in unit.get("tags",[]):
            choices=actor.spec.get("feature_choices",{}).get(uid)
            if not isinstance(choices,(list,tuple)) or not choices:raise ValueError("actual acquired feature branches required: "+uid)
            keys=[json.dumps(value,ensure_ascii=False,sort_keys=True) for value in choices]
            if len(set(keys))!=len(keys):raise ValueError("repeated acquired feature branch")
            # A global validation call must enforce the same parent branch
            # relationship as a class-filtered count. Inferring this from the
            # exact catalog ancestry does not create a new acquired class.
            ancestry={part.split("(",1)[0].strip() for part in unit.get("source",{}).get("path",[])}
            parents=[parent for parent in BRANCH_CLASSES
                     if actor.r.selection.units[parent]["title"] in ancestry]
            if len(parents)!=1:
                raise ValueError("branch feature needs its explicit parent-class policy")
            parent=parents[0]
            instances=class_instances(actor)
            owned_branches=[row["branch"] for row in instances if row["source_id"]==parent]
            if parent=="class/스탯-에이스":choices=[STAT_ALIASES.get(value,value) for value in choices]
            if parent=="class/연구원":
                raise ValueError("research field branch feature needs an explicit source policy")
            if len(choices)>len(owned_branches) or any(value not in owned_branches for value in choices):
                raise ValueError("feature branch has no matching acquired class branch")
            if len(set(choices))!=len(choices):
                raise ValueError("repeated acquired feature branch aliases")
        rank=feature_rank(actor,uid)
        for choice in choices:
            for number in range(1,rank+1):
                result.append({"source_id":uid,"rank":number,"branch":choice})
    return tuple(result)


def count_for_class(actor,source_id,*,exclude=()):
    uid=_resolve(actor,source_id,"class/")
    return sum(row["source_id"]==uid for row in class_instances(actor))+len(feature_instances(actor,class_source=uid,exclude=exclude))


def owned_rule_count(actor,source_id):
    """Read acquired trainer instances, not a new acquisition approval.

    Exact selected catalog identity is required. Classes count branches;
    Features count actual ranks/branches; repeated Edge references count as
    recorded acquisitions, without asserting that repetition was legal.
    """
    if type(source_id) is not str:
        raise ValueError('exact trainer Edge/Feature/Class source required')
    supplemental = source_id not in (RUNE_CLASS,BERSERKER_CLASS,ARCANIST_CLASS,MARKSMAN_CLASS,FORTRESS_CLASS,SKIRMISHER_CLASS) and not source_id.startswith(('edge/','feat/','class/'))
    if supplemental and actor.r.selection.units.get(source_id,{}).get('kind')!='entity:feat':
        raise ValueError('exact trainer Edge/Feature/Class source required')
    supported=source_id in ('feat/훈련-상황','feat/작열','feat/패싱-왈츠')
    if actor.r._selected_rule(source_id,supports_versions=supported)!=source_id:
        raise ValueError('selected acquisition source needs its own ownership query')
    if source_id=='feat/훈련-상황':__import__('athlete').regime_source(actor.r)
    if source_id=='feat/작열':__import__('pokemon_move_edges').incandescence_source(actor.r)
    if source_id=='feat/패싱-왈츠':__import__('dancer').waltz_source(actor.r)
    if actor.kind!='trainer':return 0
    if supplemental:
        entries=actor.spec.get('feats',[])
        if not isinstance(entries,(list,tuple)) or any(not isinstance(value,str) for value in entries):raise ValueError('acquired Features must be a text list')
        prefix=source_id.rsplit('/',1)[0]+'/'
        names=_names(actor,prefix)
        return sum(_resolve(actor,value,prefix,names)==source_id for value in entries if value in names)
    if source_id.startswith('class/') or source_id in (RUNE_CLASS,BERSERKER_CLASS,ARCANIST_CLASS,MARKSMAN_CLASS,FORTRESS_CLASS,SKIRMISHER_CLASS):
        return sum(row['source_id']==source_id for row in class_instances(actor))
    if source_id.startswith('feat/'):
        return sum(row['source_id']==source_id for row in feature_instances(actor))
    entries=actor.spec.get('edges',[])
    if not isinstance(entries,(list,tuple)):raise ValueError('acquired Edges must be a list')
    names=_names(actor,'edge/')
    import capture_techniques as CAPTURE
    granted = sum(row['rule_id'] == source_id for _, row in CAPTURE.skill_edges(actor))
    return sum(_resolve(actor,value,'edge/',names)==source_id for value in entries) + granted

