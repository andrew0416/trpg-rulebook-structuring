"""Profile applicability and explicit variant selection. Profile policy is not source authority."""
import json
from copy import deepcopy
import os
import re

GROUP_BY_PREFIX = [("supp-errata", "errata"), ("supp-polygon", "polygon"), ("supp-blessings", "blessings"), ("supp-fantasy", "fantasy"), ("hb-weather", "hb-weather"), ("hb-terastal", "hb-terastal"), ("hb-zmoves", "hb-zmoves"), ("hb-finance", "hb-finance")]
VARIANT_RE = re.compile(r"\[(?:\d{1,2}-\d{2,4}\s+)?(Playtest|플레이테스트|홈브류|썬문|소실)\]", re.I)
ENGLISH_VARIANT_RE = re.compile(r"\[(?:\d{1,2}-\d{2,4}\s+)?(Playtest|Homebrew|SuMo|SwSh)\]", re.I)
VARIANT_ID_RE = re.compile(r"-(playtest|홈브류|썬문|소실)(-\d+)?$")
ALL_GROUPS = ["core", "errata", "polygon", "blessings", "fantasy", "hb-weather", "hb-terastal", "hb-zmoves", "hb-finance", "rulings", "custom"]
ALL_VARIANTS = ["playtest", "홈브류", "썬문", "소실"]

def source_unit(record, default_file=None):
    """Preserve explicit entity provenance; defaults only cover absent metadata.

    Chapter names and custom labels are representations already emitted by this
    repository, not a claim about the authority of the underlying source.
    """
    source = record.get("source") or record.get("_source")
    if source == "core_example" and isinstance(record.get("_source"), dict):
        source = record["_source"]
    explicit = "source" in record or "_source" in record or bool(record.get("chapter"))
    if source == "custom":
        source = {"file": "data/custom/" + str(record.get("custom_file") or "runtime.json")}
    elif not isinstance(source, dict):
        source = {} if source is None else {"file": ""}
    else:
        source = dict(source)
    chapter = source.get("chapter") or record.get("chapter")
    if not source.get("file") and chapter:
        parts = str(chapter).split(" + ")
        files = [x if x.endswith((".csv", ".md")) else x + ".md" for x in parts]
        source["file"] = files[0]
        if len(files) > 1: source["additional_files"] = files[1:]
    if not explicit and default_file is not None:
        source["file"] = default_file
    mech = record.get("mech") or {}
    data = mech.get("data", mech) if isinstance(mech, dict) else {}
    data = data if isinstance(data, dict) else {}
    # Saved ruleunits have layer tags at the top and source tags in mech.data.
    # Preserve both structured fields; do not search effect prose for markers.
    tags = []
    for value in (record.get("tags"), data.get("tags")):
        values = list(value) if isinstance(value, (list, tuple, set)) else [value] if value else []
        for tag in values:
            if tag not in tags: tags.append(tag)
    if record.get("homebrew") and "homebrew" not in tags: tags.append("homebrew")
    keyword = record.get("keyword")
    if keyword is None:
        header = data.get("header", record.get("header", {}))
        keyword = header.get("keyword") if isinstance(header, dict) else None
    source_group = record.get("source_group", record.get("group", data.get("group")))
    return {"id": record.get("id"), "title": record.get("title", record.get("name", "")),
            "kind": record.get("kind"), "source": source, "tags": tags, "keyword": keyword,
            "source_group": source_group, "eng": record.get("eng", data.get("eng"))}



def classify(unit):
    return _classify_normalized(source_unit(unit))


def _classify_normalized(unit):
    """Classify a source_unit result without normalizing it again."""
    f = str(unit["source"].get("file") or "").replace("\\", "/")
    if f.startswith("input/"):f = f[len("input/"):]
    group = "unknown"
    if ".." not in f.split("/"):
        if re.fullmatch(r"ch\d{2}-[a-z0-9-]+\.md", f) or re.fullmatch(r"db/[^/]+\.csv", f):group = "core"
        elif f == "supp-polygon-original.pdf":group = "polygon"
        elif f.startswith("data/custom/"):group = "custom"
        elif re.fullmatch(r"data/gm-rulings(?:-[a-z0-9-]+)?\.json", f):group = "rulings"
        else:group = {pre + ".md": value for pre, value in GROUP_BY_PREFIX}.get(f, "unknown")
    markers = set()
    for field in [unit.get("title", "")] + list(unit.get("tags") or []):
        for match in VARIANT_RE.finditer(str(field)):
            value = match.group(1).lower()
            markers.add("playtest" if value in ("playtest", "플레이테스트") else value)
    if "homebrew" in (unit.get("tags") or []): markers.add("홈브류")
    keyword = unit.get("keyword")
    if isinstance(keyword, str):
        keyword = keyword.strip()
        if re.fullmatch(r"(?:\d{1,2}-\d{2,4}\s+)?(?:Playtest|플레이테스트)", keyword, re.I):
            markers.add("playtest")
        elif keyword == "홈브류": markers.add("홈브류")
        elif keyword in ("썬문", "썬문(SuMo)"): markers.add("썬문")
        elif keyword in ("소실", "소실(SwSh)"): markers.add("소실")
    # English-only labels do not establish a selected edition. However, an
    # explicit English label conflicting with a known structured/local marker
    # is evidence of unresolved lineage, not permission to discard that label.
    if markers:
        english_names = {"playtest": "playtest", "homebrew": "홈브류", "sumo": "썬문", "swsh": "소실"}
        english = {english_names[m.group(1).lower()] for m in ENGLISH_VARIANT_RE.finditer(str(unit.get("eng") or ""))}
        if english and english != markers: markers.update(english)
    variant = next(iter(markers)) if len(markers) == 1 else None
    if len(markers) > 1: variant = "conflicting_variant_markers:" + ",".join(sorted(markers))
    return group, variant

def base_id(uid):return VARIANT_ID_RE.sub("", uid)
def base_name(name):return re.sub(r"\s*" + VARIANT_RE.pattern + r"\s*", "", name, flags=re.I).strip()

class UnresolvedRuleSelection(ValueError):
    """A source/profile choice is missing; no game outcome has been resolved."""
    def __init__(self, identity, candidates):
        self.identity = identity
        self.candidates = tuple(sorted(set(candidates)))
        super().__init__(f"Unresolved rule selection for {identity}: {', '.join(self.candidates)}")

class RuleFilter:
    def __init__(self, profile, name="custom"):
        self.name = name
        if profile is not None and not isinstance(profile, dict):raise TypeError("Profile must be a mapping")
        self.profile = profile or {}
        import personal_type_settings as PERSONAL_TYPES
        PERSONAL_TYPES.validate(self.profile)
        for key, universe in (("sources", ALL_GROUPS), ("variants", ALL_VARIANTS)):
            value = self.profile.get(key, "*")
            if value != "*" and (not isinstance(value, list) or any(not isinstance(x, str) or x not in universe for x in value)):
                raise ValueError(f"{key} must be '*' or a list of known values")
        for key in ("exclude_units", "exclude_tags", "rulings_files"):
            value = self.profile.get(key, [])
            if not isinstance(value, list) or any(not isinstance(x, str) for x in value):raise ValueError(f"{key} must be a list of strings")
        if type(self.profile.get("variant_replaces_core", False)) is not bool:raise ValueError("variant_replaces_core must be boolean")
        for key in ("variant_choices", "unit_versions"):
            value = self.profile.get(key, {})
            if not isinstance(value, dict) or any(not isinstance(k, str) or not isinstance(v, str) or not v for k, v in value.items()):
                raise ValueError(f"{key} must map rule IDs to nonempty string choices")
        self.variant_choices = dict(self.profile.get("variant_choices", {}))
        self.replaces = self.profile.get("variant_replaces_core", False)
        if self.variant_choices and not self.replaces:raise ValueError("variant_choices requires variant_replaces_core")
        self.alias_conflicts = {}
        src = self.profile.get("sources", "*");var = self.profile.get("variants", "*")
        self.sources = set(ALL_GROUPS) if src == "*" else set(src)
        self.variants = set(ALL_VARIANTS) if var == "*" else set(var)
        self.exclude_units = set(self.profile.get("exclude_units", []))
        self.exclude_tags = set(self.profile.get("exclude_tags", []))
        self.unit_versions = dict(self.profile.get("unit_versions", {}))
        self.rulings_files = list(self.profile.get("rulings_files", []))
        self.description = self.profile.get("description", "")

    @classmethod
    def load(cls, root, name=None):
        name = "all" if name is None else name
        with open(os.path.join(root, "data/rulesets.json"), encoding="utf-8") as handle:profiles = json.load(handle)["rulesets"]
        import condition_editions as CONDITION_EDITIONS
        if name in CONDITION_EDITIONS.PROFILES:
            return cls(CONDITION_EDITIONS.profile(name,profiles.get(name)),name)
        if name not in profiles:raise KeyError(f"룰셋 프로필 없음: {name} (있는 것: {', '.join(profiles)})")
        return cls(profiles[name], name)

    def decision(self, unit):
        unit = source_unit(unit)
        if unit.get("id") in self.exclude_units:return {"status": "excluded", "reason": "exclude_units"}
        if self.exclude_tags & set(unit.get("tags") or []):return {"status": "excluded", "reason": "exclude_tags"}
        group, variant = _classify_normalized(unit)
        for file in unit["source"].get("additional_files", []):
            other_group, _ = classify(dict(unit, source={"file": file}))
            if other_group == "unknown": return {"status": "unresolved", "reason": "unknown_source"}
            if other_group not in self.sources: return {"status": "excluded", "reason": f"source:{other_group}"}
        if group == "unknown":return {"status": "unresolved", "reason": "unknown_source"}
        if group not in self.sources:return {"status": "excluded", "reason": f"source:{group}"}
        if unit.get("source_group") == "기타/홈브류" and variant is None:
            return {"status": "unresolved", "reason": "unknown_variant_lineage:기타/홈브류"}
        if variant and variant.startswith("conflicting_variant_markers:"):return {"status": "unresolved", "reason": variant}
        if variant is not None and variant not in self.variants:return {"status": "excluded", "reason": f"variant:{variant}"}
        return {"status": "allowed", "reason": ""}

    def require(self, unit):
        result = self.decision(unit)
        if result["status"] == "unresolved":
            raise UnresolvedRuleSelection(unit["id"], [result["reason"]])
        if result["status"] == "excluded":
            raise ExcludedRuleSelection(unit["id"], result["reason"])
        return unit["id"]

    def allows(self, unit):
        result = self.decision(unit)
        reason = ("unresolved:" if result["status"] == "unresolved" else "") + result["reason"]
        return result["status"] == "allowed", reason

    def split(self, units):
        units = list(units);by_id = {u["id"]: u for u in units}
        if len(by_id) != len(units):raise ValueError("Duplicate rule IDs in selection input")
        kept, excluded = [], [];self.alias_conflicts = {}
        for u in units:
            ok, why = self.allows(u)
            (kept if ok else excluded).append(u if ok else (u, why))
        alias = {};candidates = {}
        if self.replaces:
            for u in kept:
                if classify(u)[1] is None:continue
                base = base_id(u["id"])
                if base != u["id"] and base in by_id and self.allows(by_id[base])[0]:
                    other = by_id[base]
                    if base_name(u.get("title", u.get("name", ""))) != base_name(other.get("title", other.get("name", ""))):
                        continue  # Suffix similarity does not establish rule identity.
                    if u.get("kind") and other.get("kind") and u["kind"] != other["kind"]:
                        continue
                    candidates.setdefault(base, set()).add(u["id"])
            for base, choice in self.variant_choices.items():
                if base in by_id and choice not in candidates.get(base, set()):raise ValueError(f"Selected variant is not an eligible candidate: {base} -> {choice}")
            for base, options in sorted(candidates.items()):
                if base in self.variant_choices:alias[base] = self.variant_choices[base]
                elif len(options) == 1:alias[base] = next(iter(options))
                else:self.alias_conflicts[base] = sorted(options)
            if self.alias_conflicts:
                unresolved = [u for u in kept if u["id"] in self.alias_conflicts]
                kept = [u for u in kept if u["id"] not in self.alias_conflicts]
                excluded.extend((u, "unresolved_variant:" + ",".join(self.alias_conflicts[u["id"]])) for u in unresolved)
        return kept, excluded, alias

    def entity_unit(self, uid, name, homebrew=False, file="db/moves.csv"):
        return {"id": uid, "title": name, "tags": ["homebrew"] if homebrew else [], "source": {"file": file}}

    def mech_version(self, uid, data):
        key = self.unit_versions.get(uid)
        if key and not isinstance(data.get(key), dict):raise ValueError(f"Selected rule version is missing or invalid: {uid} -> {key}")
        if key:
            result = {k: v for k, v in data.items() if k != key};result.update(data[key]);result["_version"] = key
            return result
        return data

    def selection_policy(self):
        """Small admission configuration, excluding mutable split-result caches."""
        fields=('sources','variants','exclude_units','exclude_tags','replaces',
                'variant_choices','unit_versions','rulings_files')
        declared=('sources','variants','exclude_units','exclude_tags','variant_replaces_core',
                  'variant_choices','unit_versions','rulings_files','personal_type_settings')
        return {'effective':{key:getattr(self,key) for key in fields},
                'declared':{key:self.profile[key] for key in declared if key in self.profile}}

    def summary(self):
        return f"룰셋 '{self.name}': 출처 {sorted(self.sources)}, 변형 {sorted(self.variants) or '없음'}{' (변형판이 코어판 대체)' if self.replaces else ''}" + (f", 제외 단위 {len(self.exclude_units)}" if self.exclude_units else "") + (f", 단위 버전 {self.unit_versions}" if self.unit_versions else "")


class ExcludedRuleSelection(ValueError):
    """An excluded rule is not executable, including via direct query APIs."""
    def __init__(self, identity, reason):
        self.identity, self.reason = identity, reason
        super().__init__(f"Excluded rule selection for {identity}: {reason}")


class RuleSelection:
    """One ID-preserving admission index for every catalogued rule kind.

    This index guards reads; it does not itself make arbitrary raw dictionaries
    safe or establish source authority. Callers must route their reads through it.
    """
    def __init__(self, rule_filter, units):
        self.filter = rule_filter
        self._selection_policy = deepcopy(rule_filter.selection_policy())
        units = [source_unit(u) for u in units]
        if any(not isinstance(u["id"], str) or not u["id"] for u in units):
            raise ValueError("Rule selection requires nonempty string identities")
        self.units = {u["id"]: u for u in units}
        if len(self.units) != len(units): raise ValueError("Duplicate rule IDs in selection input")
        _, excluded, self.aliases = rule_filter.split(units)
        self.conflicts = {k: list(v) for k, v in rule_filter.alias_conflicts.items()}
        self.excluded = {u["id"]: reason for u, reason in excluded}
        self.dependencies = {}
        self.names = {}
        for u in units:
            if u["title"]: self.names.setdefault(u["title"], []).append(u["id"])

    def require_current_filter(self, rule_filter=None):
        """Reject stale admission rather than silently use cached aliases/exclusions.

        Rebuild a selection explicitly after changing admission policy. Comparing
        both effective fields and declarations catches in-place edits while
        preserving equivalent copied RuleFilter instances used by package loading.
        """
        if (self.filter.selection_policy()!=self._selection_policy or
                (rule_filter is not None and rule_filter.selection_policy()!=self._selection_policy)):
            raise UnresolvedRuleSelection('profile', ['selection_profile_changed_rebuild_required'])

    def resolve(self, uid):
        self.require_current_filter()
        if uid not in self.units:
            raise UnresolvedRuleSelection(uid, ["missing_source_identity"])
        if uid in self.conflicts:
            raise UnresolvedRuleSelection(uid, self.conflicts[uid])
        reason = self.excluded.get(uid)
        if reason:
            if reason.startswith("unresolved:"):
                raise UnresolvedRuleSelection(uid, [reason])
            raise ExcludedRuleSelection(uid, reason)
        for dependency in self.dependencies.get(uid, ()):
            self.resolve(dependency)
        target = self.aliases.get(uid, uid)
        # Aliases cannot turn an excluded/missing target into an allowed one.
        if target != uid:
            if uid in self.filter.unit_versions:
                raise UnresolvedRuleSelection(uid, ["version_choice_on_replaced_identity", target])
            return self.resolve(target)
        return target

    def register_derived(self, unit, dependencies):
        """Register a runtime-derived identity only after all parents are active."""
        unit = source_unit(unit)
        if unit["id"] in self.units: raise ValueError("Cannot overwrite registered identity: " + unit["id"])
        if not dependencies: raise ValueError("Derived rules require source dependencies")
        for uid in dependencies: self.resolve(uid)
        self.filter.require(unit)
        self.units[unit["id"]] = unit
        self.dependencies[unit["id"]] = tuple(dependencies)
        self.names.setdefault(unit["title"], []).append(unit["id"])
        return unit["id"]

    def resolve_name(self, name, prefixes=()):
        candidates = [uid for uid in self.names.get(name, [])
                      if not prefixes or uid.startswith(tuple(prefixes))]
        if not candidates:
            raise UnresolvedRuleSelection(name, ["missing_source_identity"])
        resolved, rejected = set(), []
        for uid in candidates:
            try: resolved.add(self.resolve(uid))
            except ExcludedRuleSelection as exc: rejected.append(exc)
        if len(resolved) > 1:
            raise UnresolvedRuleSelection(name, sorted(resolved))
        if not resolved: raise rejected[0]
        # A name-keyed effect registry may already have been overwritten by an
        # excluded same-name record. It cannot distinguish the surviving ID.
        if len(candidates) > 1:
            raise UnresolvedRuleSelection(name, sorted(candidates))
        return next(iter(resolved))

    def require_supported_version(self, uid, supports_versions=False):
        selected = self.resolve(uid)
        if selected in self.filter.unit_versions and not supports_versions:
            raise UnresolvedRuleSelection(selected, ["version_not_supported_by_reader"])
        return selected

    def validate_choices(self):
        for field in ("variant_choices", "unit_versions"):
            for uid in getattr(self.filter, field):
                if uid not in self.units:
                    raise ValueError(f"Unknown rule identity in {field}: {uid}")


def build_runtime_selection(rules):
    """Join saved source identities with runtime records without guessing by name.

    Runtime units take precedence only for the SAME identity's provenance.
    Missing source metadata remains unresolved; no kind defaults to core.
    """
    catalog = {}
    source_snapshots = {}
    path = os.path.join(rules.root, "output/ruleunits.jsonl")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if not line.strip(): continue
                unit = json.loads(line)
                if unit["id"] in catalog: raise ValueError("Duplicate catalog rule ID: " + unit["id"])
                catalog[unit["id"]] = source_unit(unit)
    # Reviewed exact source identities absent from the legacy entity export.
    # Preserve exported identities when later extraction repairs the omission.
    path = os.path.join(rules.root, "data/content-source-identities.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            supplement = json.load(handle)
            source_snapshots = supplement.get("source_snapshots", {})
            for unit in supplement["units"]:
                catalog.setdefault(unit["id"], source_unit(unit))
    for uid, unit in getattr(rules, "units", {}).items():
        normalized = source_unit(dict(unit, id=uid))
        # These two hand-authored lookup units cite the exact saved sheet label.
        # Keep the identity mapping explicit; arbitrary sheet labels stay unknown.
        if uid in ("combat/type-chart", "pokemon/natures") and normalized["source"].get("sheet") == "데이터베이스 버전.9세대 / 성격/타입 정보":
            normalized["source"]["file"] = "db/nature-type.csv"
        catalog[uid] = normalized
    for attr in ("moves", "species"):
        for uid, record in getattr(rules, attr, {}).items():
            if uid == "struggle": continue
            if record.get("source") == "weapon":
                catalog[uid] = source_unit({"id": uid, "name": record["name"], "source": {"file": "ch09-equipment.md"}, "tags": ["derived-weapon"]})
            else:
                catalog[uid] = source_unit(dict(record, id=uid))
    path = os.path.join(rules.root, "output/entities/abilities.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            for record in json.load(handle):
                # Legacy fixtures without metadata may still be classified by
                # their known exported table, but explicit metadata is preserved.
                catalog[record["id"]] = source_unit(record, "db/abilities.csv")
    for record in getattr(rules, "core_abilities", {}).values():
        if record["id"] in catalog:
            raise ValueError("Duplicate explicit core ability identity: " + record["id"])
        catalog[record["id"]] = source_unit(record)
    for unit in getattr(rules, "_custom_rule_metadata", {}).values():
        catalog[unit["id"]] = source_unit(unit)
    if "combat/struggle" in catalog:
        catalog["struggle"] = dict(catalog["combat/struggle"], id="struggle", title="struggle")
    if "pokemon/capture-rate" in catalog:
        catalog["ball"] = dict(catalog["pokemon/capture-rate"], id="ball", title="ball")
    # Only explicit runtime registrations survive a catalog rebuild. The new
    # RuleSelection still applies the current filter and each source dependency.
    previous = getattr(rules, "selection", None)
    retained = {}
    if previous is not None:
        registered = set(previous.dependencies) | set(getattr(rules, "_authored_policy_sources", {}))
        retained = {uid: deepcopy(unit) for uid, unit in previous.units.items()
                    if uid in registered and uid not in catalog}
        catalog.update(retained)
    for unit in catalog.values():
        source=unit['source'];file=source.get('file','').removeprefix('input/')
        if file in source_snapshots:
            expected=source_snapshots[file]
            if source.get('sha256',expected)!=expected:raise ValueError('conflicting registered source snapshots: '+file)
            source['sha256']=expected
        additional=source.get('additional_files',[])
        if additional:source['additional_snapshots']={file:source_snapshots[file] for file in additional if file in source_snapshots}
    import mentor
    expand_csv=mentor.bind_expand_csv_source(rules,catalog)
    selection = RuleSelection(rules.ruleset, catalog.values())
    if expand_csv:selection.dependencies[mentor.EXPAND_CSV]=(mentor.EXPAND,)
    selection.source_audit_snapshots = {row['id']:{row['official_source']['extract']:row['official_source']['sha256']}
        for row in getattr(rules,'core_abilities',{}).values()
        if str(row.get('official_source',{}).get('extract','')).startswith('source-audit/')}
    if previous is not None:
        for uid in retained:
            if uid in previous.dependencies:
                selection.dependencies[uid] = deepcopy(previous.dependencies[uid])
            if uid in getattr(previous, "source_audit_snapshots", {}):
                selection.source_audit_snapshots[uid] = deepcopy(previous.source_audit_snapshots[uid])
    if "ball" in catalog:
        selection.dependencies["ball"] = ("pokemon/capture-rate", "combat/accuracy-roll")
    for uid, record in getattr(rules, "moves", {}).items():
        if record.get("source") == "weapon":
            selection.dependencies[uid] = ("combat/struggle", "ch09-equipment/장비/무기")
    selection.validate_choices()
    return selection


from contextvars import ContextVar
from contextlib import contextmanager

_GENERATED_WEAPON_JOURNALS = ContextVar('generated_weapon_publications', default=())


@contextmanager
def generated_weapon_transaction(rules):
    """Journal only actual generated-weapon writes, including nested producers."""
    journal={}
    token=_GENERATED_WEAPON_JOURNALS.set((*_GENERATED_WEAPON_JOURNALS.get(),
                                         (rules.moves,rules.selection,journal)))
    try:
        yield
    except BaseException:
        for records in reversed(tuple(journal.values())):
            for mapping,key,present,old,contents in reversed(records):
                if not present:mapping.pop(key,None)
                else:
                    if contents is not None:old[:]=contents
                    mapping[key]=old
        raise
    finally:
        _GENERATED_WEAPON_JOURNALS.reset(token)


def capture_runtime_weapon(rules,uid,title):
    """Capture this producer's exact touched keys once per enclosing transaction."""
    selection=rules.selection
    identity=(id(rules.moves),id(selection),uid)
    for move_owner,selection_owner,journal in _GENERATED_WEAPON_JOURNALS.get():
        if move_owner is not rules.moves or selection_owner is not selection:continue
        if identity in journal:continue
        keys=[(rules.moves,uid),(rules.moves_mech,uid),(selection.units,uid),
              (selection.dependencies,uid),(selection.names,title),
              (rules._runtime_weapon_declarations,uid)]
        journal[identity]=[(mapping,key,key in mapping,mapping.get(key),
                            list(mapping[key]) if mapping is selection.names and key in mapping else None)
                           for mapping,key in keys]


def require_runtime_weapon(rules, uid):
    """Known turn.equip_weapon output inherits struggle AND weapon rules.

    This is an adapter for that explicit producer, not an unknown-ID fallback.
    Arbitrary dictionary mutation remains outside the source-trust boundary.
    """
    record = rules.moves.get(uid)
    if not record or record.get("source") != "weapon":
        return rules.selection.require_supported_version(uid)
    dependencies = ("combat/struggle", "ch09-equipment/장비/무기")
    if uid not in rules.selection.units:
        capture_runtime_weapon(rules,uid,record['name'])
        rules.selection.register_derived({"id": uid, "title": record["name"],
            "source": {"file": "ch09-equipment.md"}, "tags": ["derived-weapon"]}, dependencies)
    for dependency in dependencies:
        rules.selection.require_supported_version(dependency, supports_versions=(dependency == "combat/struggle"))
    return rules.selection.require_supported_version(uid)


def bind_rule_identity(value, uid):
    """Copy effect trees and retain the selected ID through nested dispatch."""
    if isinstance(value, list): return [bind_rule_identity(v, uid) for v in value]
    if isinstance(value, dict):
        result = {k: bind_rule_identity(v, uid) for k, v in value.items()}
        if "type" in result: result["_rule_id"] = uid
        return result
    return value
