"""Lossless species template facts, separate from observed individuals."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from pathlib import Path
import csv, hashlib, json


def sex_distribution(raw):
    """Normalize explicit complete fractions/percentages; preserve doubtful text."""
    raw = list(raw)
    if raw == ["무성", "무성"]:return {"status":"genderless", "raw":raw}
    if all(x.strip() in ("", "-") for x in raw):return {"status":"unknown", "raw":raw}
    try:
        values = [Decimal(value) for value in raw]
        if any(not value.is_finite() or value < 0 for value in values):raise InvalidOperation
        total = sum(values)
        if total == 1:scale=Decimal(1)
        elif total == 100:scale=Decimal(100)
        else:raise InvalidOperation
        return {"status":"known", "male":float(values[0]/scale), "female":float(values[1]/scale),
                "source_notation":"fraction" if scale == 1 else "percent", "raw":raw}
    except (InvalidOperation, ValueError):
        return {"status":"unresolved_source_value", "raw":raw,
                "reason":"Incomplete, malformed, or non-unit sex distribution; no guessed correction."}

def project(rules, species):
    source=species.get("_source", {})
    result={"individual_values_inferred":False, "sex_distribution":{"status":"unknown", "raw":[]},
            "catalog_measurements":None, "diet":None, "habitat":None, "hatch_guidance":None,
            "special_form_notes":None, "breeding":None, "move_learning_routes":None,
            "species_skills":None, "sources":[]}
    if source.get("file") == "db/pokemon.csv":
        path=Path(rules.root)/"input"/source["file"]
        raw=path.read_bytes()
        manifest=json.loads((Path(rules.root)/"input/db/source-xlsx.json").read_text(encoding="utf-8"))
        digest=hashlib.sha256(raw).hexdigest()
        if digest != manifest["files"]["pokemon.csv"]["sha256"]:
            raise ValueError("species table disagrees with its saved-input fingerprint")
        with path.open(encoding="utf-8-sig",newline="") as file:rows=list(csv.reader(file))
        first,last=source["record_span"]
        if first!=last or rows[first-1][0] != species["name"]:
            raise ValueError("species metadata source row does not identify the selected species")
        result["sex_distribution"]=sex_distribution(rows[first-1][34:36])
        result["sources"].append({"file":"input/db/pokemon.csv", "row":first, "columns":[35,36], "sha256":digest})
    # A custom species must opt into its own facts; matching a stock display
    # name is not authority to silently import the stock species' metadata.
    learnset=rules.learnsets.get(species["name"]) if source.get("file") == "db/pokemon.csv" else None
    if learnset:
        result.update(catalog_measurements={key:learnset.get(key) for key in ("height_m","weight_kg","size","weight_class")},
                      diet=learnset.get("diet"), habitat=learnset.get("habitat"),
                      hatch_guidance=learnset.get("hatch"), special_form_notes=learnset.get("note"))
        result["sources"].append(deepcopy(learnset.get("_source")))
        result["breeding"]={"egg_groups":deepcopy(species.get("egg_groups")),
            "sex_distribution":deepcopy(result["sex_distribution"]),
            "hatch_guidance":deepcopy(learnset.get("hatch")),
            "individual_compatibility_inferred":False}
        links=rules.learnset_links.get(species["name"],{})
        result["move_learning_routes"]={
            route:{"source_field":field,"listed":deepcopy(learnset.get(field,[])),
                   "resolved":deepcopy([row for row in links.get("moves",[]) if row.get("source")==field]),
                   "acquired_by_individual":False}
            for route,field in (("level_up","level_up"),("egg","egg"),("tm_hm","tm"),("tutor","tutor"))}
        result["move_learning_routes"]["unresolved_references"]=deepcopy(links.get("unresolved",[]))
        result["species_skills"]=deepcopy(rules.species_skills.get(species["name"]))
    return result
