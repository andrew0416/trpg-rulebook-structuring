"""Whole-corpus audit ledger. This is NOT a certification of semantic correctness.
python -X utf8 -B -I tools/audit_rulebook_all.py [root]
Frozen primary-source snapshot: data/source-audit-manifest.json.
No original input, RuleUnit, or runtime engine file is rewritten.
"""
import collections
import hashlib
import html
import json
import re
import sys
import unicodedata
from pathlib import Path


def norm(text):
    text=html.unescape(str(text or ""))
    text=re.sub(r"</?table>|\[img\]|\*\*|`|\||_", "",text)
    text=re.sub(r"(?m)^[ \t]*(?:#{1,6}[ \t]*|[-*●•][ \t]+|\d+\.[ \t]+)","",text)
    return re.sub(r"\s|\ufeff|\u200b","",unicodedata.normalize("NFKC",text))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def walk_effects(value,path="effects"):
    if isinstance(value,list):
        for i,v in enumerate(value): yield from walk_effects(v,f"{path}[{i}]")
    elif isinstance(value,dict):
        if isinstance(value.get("type"),str):yield path,value
        for k,v in value.items():
            if isinstance(v,(list,dict)):yield from walk_effects(v,path+"."+k)


def main(root):
    sys.path.insert(0,str(root/"engine"))
    import effects as FX
    import effects_ext as EXT
    import items as ITEMS
    manifest=json.loads((root/"data/source-audit-manifest.json").read_text(encoding="utf-8"))
    evidence=root/manifest["snapshot_directory"]
    for path,expected in manifest["snapshot_hashes"].items():
        if sha(evidence/path)!=expected:raise ValueError("Evidence hash changed: "+path)
    out=root/"output/whole-rulebook-audit";out.mkdir(exist_ok=True)
    units=[json.loads(line) for line in (root/"output/ruleunits.jsonl").read_text(encoding="utf-8").splitlines()]
    sys.path.insert(0,str(root/"tools"))
    from audit_current_sources import current_checks
    sheets,field_checks=current_checks(root,evidence)
    byid={x["id"]:x for x in field_checks}
    files={p.name:p.read_text(encoding="utf-8") for p in (root/"input").glob("*.md")}
    docs=[]
    for d in manifest["documents"]:
        remote=(evidence/(d["name"]+".txt")).read_text(encoding="utf-8-sig")
        local="\n".join(files[f] for f in d["input_files"])
        rn,ln=norm(remote),norm(local)
        local_misses=[];remote_misses=[];nc=nr=0
        for file in d["input_files"]:
            for i,line in enumerate(files[file].splitlines(),1):
                if norm(line):
                    nc+=1
                    if norm(line) not in rn:local_misses.append(dict(file=file,line=i,text=line))
        for i,line in enumerate(remote.splitlines(),1):
            if norm(line):
                nr+=1
                if norm(line) not in ln:remote_misses.append(dict(line=i,text=line))
        docs.append(dict(name=d["name"],url=d["url"],files=d["input_files"],
            local_nonempty_lines=nc,remote_nonempty_lines=nr,local_unmatched=local_misses,remote_unmatched=remote_misses,
            image_placeholders=local.count("[img]"),status="normalized_line_text_match" if not local_misses and not remote_misses else "format_or_content_difference_review",
            limitation="Line-presence check ignores formatting/whitespace, does not prove order, duplicate counts, images or layout."))

    execution=json.loads((root/"output/execution-accuracy-audit-core.json").read_text(encoding="utf-8"))
    findings={
        "L01":dict(stage="acquisition",status="confirmed",title="gviz CSV drops mixed-type text cells",evidence="sheet-comparison.json + database.xlsx + sheets/*.csv",impact="Missing sentinel/header values and substantive labels/costs. Not every missing cell changes execution."),
        "L02":dict(stage="acquisition",status="confirmed",title="damage-table CSV merges first source rows into header",evidence="sheet-comparison.json: damage-table.csv",impact="Original table coordinates are lost; runtime consequence is not yet established."),
        "L03":dict(stage="structuring",status="confirmed",title="Mighty Change homebrew effect2 bonus omitted",units=["ability/마이티체인지-홈브류"],source="특성 데이터!G685",omitted="마이티폼일 때 사용자는 격투타입 기술에 자속 보정을 받습니다.",evidence="C685 omits bonus present in G685; parse_abilities reads but does not retain effect2; entity, RuleUnit and runtime lack bonus."),
        "L04":dict(stage="structuring",status="confirmed",title="Injury true-maximum exception omitted from executable rule",units=["combat/injuries","combat/tick-of-hit-points"],source="input/ch07-combat.md:700",execution_cases=["H04","H07","H08","H11"]),
        "L05":dict(stage="structuring_execution",status="confirmed",title="Restorative/X-item global procedure not applied",units=["item/상처약","item/플러스파워"],source="input/ch09-equipment.md:132-138",execution_cases=["A03","A05","A07","X02","X03"]),
        "L06":dict(stage="execution",status="confirmed",title="Fainted no_actions present in data but not enforced",units=["condition/기절","combat/hit-points"],source="input/ch07-combat.md:211,633",execution_cases=["K01","K02"]),
        "L07":dict(stage="execution",status="confirmed",title="Stage bounds and encounter_end reset not enforced across paths",units=["combat/combat-stages","combat/evasion"],source="input/ch07-combat.md:217-237",execution_cases=["S-acc-upper","S-acc-lower","S-eva-upper","S-eva-lower","S-end"]),
        "L08":dict(stage="execution",status="confirmed_derived_contract",title="Held-item ownership and effect lifetime diverge",units=["item/분홍진주"],execution_cases=["I05","I06","I07","I08","I09"]),
        "L09":dict(stage="provenance",status="confirmed",title="Exported source locations include placeholders and zero rows",impact="Traceability defect, not proof of fabricated text."),
        "L10":dict(stage="coverage_reporting",status="confirmed",title="Effect support membership counts GM prompts and registry entries",evidence="tools/effect_support.py",impact="Type recognition cannot establish semantic correctness or complete automation."),
    }
    if not any(x["differences"] for x in sheets):
        for fid in ["L01","L02"]:
            findings[fid]["status"]="repaired_original_cells_preserved"
            findings[fid]["current_evidence"]="current-source-cells.json; XLSX cached values, formula calculation unverified"
    mighty=next(x for x in field_checks if x["id"]=="ability/마이티체인지-홈브류")
    if not mighty["differences"]:
        findings["L03"]["status"]="source_text_restored_execution_clause_requires_test"
        findings["L03"]["current_evidence"]="Both source effect columns preserved; full ability lifecycle still unverified"
    findings["L10"]["status"]="report_wording_corrected_semantics_still_unverified"
    latest_cases={x['id']:x['status'] for x in execution['results']}
    for record in findings.values():
        case_ids=record.get('execution_cases',[])
        if case_ids and all(latest_cases.get(cid)=='pass' for cid in case_ids):
            record['execution_status']='previous_failure_now_passes_selected_cases'
            record['status']='historical_failure_with_current_sample_fix' if record['stage']=='execution' else 'source_or_contract_review_still_required'
            record['limitation']='Current samples pass; no full-rule semantic certification.'
    known={}
    for fid,record in findings.items():
        for uid in record.get("units",[]):known.setdefault(uid,[]).append(fid)
    counters={key:collections.Counter() for key in ["kind","coverage_claim","source_locator","semantic_status","route_occurrences"]}
    ledger=[]
    from source_locations import validate_record
    csv_location_cache={}
    for u in units:
        src=u["source"];file=src.get("file","");span=src.get("lines",[]);body=u.get("text",{}).get("body","")
        mech=u.get("mech") or {};data=mech.get("data") or {};paths=[]
        if file in files:
            lines=files[file].splitlines()
            if len(span)==2 and 1<=span[0]<=span[1]<=len(lines):
                locator="valid_local_md_span"
                cited="\n".join(lines[span[0]-1:span[1]])
                text_state="within_cited_span" if norm(body) and norm(body) in norm(cited) else "elsewhere_in_file" if norm(body) and norm(body) in norm(files[file]) else "transformed_or_unmatched"
            else:locator="invalid_local_md_span";text_state="not_checked"
        elif file.startswith("db/"):
            if file=="db/":locator="missing_csv_filename"
            elif not (root/"input"/file).is_file():locator="composite_or_missing_file"
            elif src.get("record_span"):
                locator="valid_csv_record_span" if not validate_record(root,src,cache=csv_location_cache) else "invalid_csv_record_span"
            elif span==[0,0]:locator="csv_record_number_missing"
            else:locator="csv_location_needs_record_semantics"
            text_state="selected_source_fields_checked" if u["id"] in byid else "not_checked"
        elif (root/file).is_file():locator="local_generated_data_source";text_state="not_checked"
        else:locator="non_resolvable_source_label";text_state="not_checked"
        routes=[];opaque=[]
        for path,e in walk_effects(data.get("effects",[])):
            typ=e["type"]
            if typ in EXT.PROMPT_TYPES:route="gm_prompt_or_special_handler"
            elif typ in EXT.REGISTRY_TYPES:route="registry_requires_consumer_verification"
            elif typ in FX.HANDLERS:route="handler_exists_unverified"
            elif typ in FX.PASSIVE_TYPES|FX.JUDGEMENT_TYPES|FX.ENGINE_TYPES:route="engine_path_unverified"
            elif typ in ITEMS.PASSIVE_ITEM_TYPES|ITEMS.CONSUMABLE_TYPES:route="item_path_unverified"
            else:route="unclassified_context_required"
            routes.append(dict(path=path,type=typ,route=route))
            counters["route_occurrences"][route]+=1
            if isinstance(e.get("if"),str) and e["if"] not in FX.KNOWN_IF:opaque.append(dict(path=path,condition=e["if"]))
        semantic="known_finding_requires_full_review" if u["id"] in known else "not_semantically_verified"
        entry=dict(id=u["id"],title=u.get("title"),kind=u["kind"],source=src,source_locator=locator,
            stored_text_state=text_state,coverage_claim=mech.get("coverage"),confidence_claim=mech.get("confidence"),
            source_field_check=byid.get(u["id"]),effect_routes=routes,conditions_requiring_path_review=opaque,
            semantic_status=semantic,findings=known.get(u["id"],[]),execution_correctness="not_certified")
        ledger.append(entry)
        for key,value in [("kind",u["kind"]),("coverage_claim",mech.get("coverage") or "none"),("source_locator",locator),("semantic_status",semantic)]:counters[key][value]+=1
    location_errors=sum(count for key,count in counters["source_locator"].items() if key not in ("valid_local_md_span","valid_csv_record_span","local_generated_data_source"))
    if not location_errors:
        findings["L09"]["status"]="source_locations_repaired_not_semantic_certification"
        findings["L09"]["current_evidence"]="CSV logical records/columns and composite source references preserved; source-location tests pass."
    missing=[dict(file=x["file"],**d) for x in sheets for d in x["differences"] if d["kind"]=="missing_in_csv"]
    def category(d):
        if d["remote"] in ("--","-","X","x"):return "sentinel"
        if re.search(r"[가-힣A-Za-z]",d["remote"]):return "text_value_or_header"
        return "other_value"
    missing_counts=collections.Counter(category(d) for d in missing)
    summary=dict(scope=f"All {len(units)} exported units inventoried; selected field/source fidelity checks do not complete semantic or execution verification.",
        total_units=len(units),counts={k:dict(v) for k,v in counters.items()},documents=len(docs),local_md_files=sum(len(x["files"]) for x in docs),
        source_csv_files=len(sheets),image_placeholders=sum(x["image_placeholders"] for x in docs),
        csv_missing_cells=len(missing),csv_missing_categories=dict(missing_counts),
        csv_cell_differences=sum(len(x["differences"]) for x in sheets),
        source_field_mismatches=sum(bool(x["differences"]) for x in field_checks),
        source_field_entities=len(field_checks),source_field_comparisons=sum(len(x.get("checked_fields",[])) for x in field_checks),
        source_internal_column_disagreement_units=[x["id"] for x in field_checks if x.get("source_column_disagreements")],
        execution_audit=execution["counts"],findings=findings,full_semantic_audit_complete=False,
        evidence_manifest_sha256=sha(root/"data/source-audit-manifest.json"),ruleunits_sha256=sha(root/"output/ruleunits.jsonl"))
    for name,obj in [("current-source-cells.json",sheets),("summary.json",summary),("document-comparison.json",docs),("source-field-checks.json",field_checks),("missing-source-cells.json",missing)]:
        (out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (out/"rule-audit-ledger.jsonl").write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in ledger),encoding="utf-8")
    print(json.dumps({k:summary[k] for k in ["total_units","documents","local_md_files","source_csv_files","csv_missing_cells","csv_missing_categories","image_placeholders","full_semantic_audit_complete"]},ensure_ascii=False))
    print(json.dumps(summary["counts"],ensure_ascii=False))
    return 1 # Confirmed findings remain unresolved; do not turn this audit green.


if __name__=="__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]))
