"""Plan verification coverage under an estimated budget. Read one JSON contract on stdin."""
import json
import sys


def identifiers(values):
    if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
        raise ValueError("Expected a list of nonempty identifiers.")
    result = frozenset(values)
    if len(result) != len(values):
        raise ValueError("Identifiers must be unique.")
    return result


def plan_checks(contract):
    fields = {"budget", "obligations", "mandatory", "checks"}
    if not isinstance(contract, dict) or contract.keys() != fields:
        raise ValueError("Expected budget, obligations, mandatory and checks.")
    budget = contract["budget"]
    if type(budget) is not int or budget < 0:
        raise ValueError("Budget must be a nonnegative integer.")
    target = identifiers(contract["obligations"])
    mandatory = identifiers(contract["mandatory"])
    rows = contract["checks"]
    if not 1 <= len(target) <= 12 or not isinstance(rows, list) or len(rows) > 64:
        raise ValueError("Expected 1 to 12 obligations and at most 64 checks.")

    catalog = {}
    for row in rows:
        if not isinstance(row, dict) or row.keys() != {"id", "cost", "covers"}:
            raise ValueError("Each check needs id, cost and covers.")
        name, cost = row["id"], row["cost"]
        covers = identifiers(row["covers"])
        if not isinstance(name, str) or not name.strip() or name in catalog:
            raise ValueError("Check identifiers must be unique and nonempty.")
        if type(cost) is not int or cost < 1 or not covers <= target:
            raise ValueError("Each check needs a positive integer cost and known obligations.")
        catalog[name] = cost, covers
    if not mandatory <= catalog.keys():
        raise ValueError("Missing mandatory check in catalog.")

    available = frozenset().union(*(covers for _, covers in catalog.values()))
    if target - available:
        return {"status": "blocked", "checks": [], "uncovered": sorted(target - available)}

    # For each covered set retain the cheapest plan, then the shortest, then stable IDs.
    covered = frozenset().union(*(catalog[name][1] for name in mandatory))
    required_cost = sum(catalog[name][0] for name in mandatory)
    best = {covered: (required_cost, 0, ())}
    for name in sorted(catalog.keys() - mandatory):
        cost, covers = catalog[name]
        for previous, (spent, count, chosen) in list(best.items()):
            combined = previous | covers
            if combined == previous:
                continue
            candidate = (spent + cost, count + 1, (*chosen, name))
            if combined not in best or candidate < best[combined]:
                best[combined] = candidate
    minimum, _, optional = best[target]
    if minimum > budget:
        return {"status": "blocked", "checks": [], "minimum_cost": minimum}
    reference_cost = sum(cost for name, (cost, covers) in catalog.items() if covers or name in mandatory)
    return {"status": "planned", "checks": sorted(mandatory.union(optional)),
            "cost": minimum, "all_relevant_cost": reference_cost}


def main():
    try:
        payload = sys.stdin.buffer.read(65537)
        if len(payload) > 65536:
            raise ValueError("Contract exceeds 64 KiB.")
        result = plan_checks(json.loads(payload))
    except (ValueError, RecursionError) as error:
        print(json.dumps({"status": "invalid", "reason": str(error)}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
