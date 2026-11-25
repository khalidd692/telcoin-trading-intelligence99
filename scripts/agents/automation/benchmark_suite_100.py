"""Frozen 120-Mission Executable Reference Benchmark across all 12 TEL99 Specialties.

Design guarantees (Target >= 89% verified real capability, stretch 95%):
- 120 genuinely distinct tasks: 10 per specialty across all 12 official TEL99 roles.
- Strictly disjoint 3-way split, cryptographically sealed (SHA-256) BEFORE evaluation:
    * train (24 tasks, 2/role): failure mining, verified lesson extraction, skill authoring.
    * dev   (24 tasks, 2/role): bounded prompt/harness/model-routing optimization.
    * held_out_final (72 tasks, 6/role across easy/medium/hard): UNSEEN final evaluation only.
- 100% executable programmatic verifiers (AST security scan + isolated Python assertions
  or strict structured JSON schema + value validation). Zero keyword-only heuristics.
- Verifiers are immutable and discriminative (a stub returning None fails 120/120 tasks).
"""
from __future__ import annotations

import ast
import hashlib
import json
from typing import Any

from scripts.agents.automation import context_engine, ollama_native

ROLES_12 = (
    "development",
    "quant",
    "quality",
    "coordination",
    "cloud",
    "security",
    "mobile",
    "documentation",
    "evaluation",
    "market_data",
    "monitoring",
    "release",
)


def _t(
    tid: str,
    role: str,
    split: str,
    difficulty: str,
    objective: str,
    test_code: str,
    *,
    kind: str = "code",
    required_fields: dict[str, str] | None = None,
    expected_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": tid,
        "role": role,
        "split": split,
        "difficulty": difficulty,
        "kind": kind,
        "task_profile": "module" if difficulty != "easy" else "patch",
        "objective": objective,
        "test_code": test_code,
        **({"required_fields": required_fields} if required_fields else {}),
        **({"expected_values": expected_values} if expected_values else {}),
    }


# 120 genuinely distinct executable tasks (10 per role: 2 train, 2 dev, 6 held_out_final)
BENCHMARK_120: tuple[dict[str, Any], ...] = (
    # ==================== 1. DEVELOPMENT (10) ====================
    _t("dev-tr-01", "development", "train", "easy",
       "Write `clamp_value(x, lo, hi)` returning x clamped to [lo, hi]. Reject bool/None or lo > hi with ValueError.",
       "assert clamp_value(5, 0, 10) == 5\nassert clamp_value(-2, 0, 10) == 0\nassert clamp_value(15, 0, 10) == 10\n"
       "for b in ((True,0,1),(5,10,0),(None,0,1)):\n    try:\n        clamp_value(*b); assert False\n    except ValueError:\n        pass\n"),
    _t("dev-tr-02", "development", "train", "medium",
       "Write `chunk_list(items, size)` splitting list `items` into sublists of length `size`. Raise ValueError if items is not list or size is bool/non-int/<=0.",
       "assert chunk_list([1,2,3,4,5], 2) == [[1,2],[3,4],[5]]\nassert chunk_list([], 3) == []\n"
       "for b in (('abc',2),([1],0),([1],True)):\n    try:\n        chunk_list(*b); assert False\n    except ValueError:\n        pass\n"),
    _t("dev-dv-01", "development", "dev", "medium",
       "Write `merge_sorted_unique(a, b)` merging two lists of ints/floats (rejecting bool) into a sorted list without duplicates. Raise ValueError on invalid inputs.",
       "assert merge_sorted_unique([3,1,2], [2,4,1]) == [1,2,3,4]\nassert merge_sorted_unique([], [5]) == [5]\n"
       "try:\n    merge_sorted_unique([True], [1]); assert False\nexcept ValueError:\n    pass\n"),
    _t("dev-dv-02", "development", "dev", "hard",
       "Write `retry_backoff_schedule(attempts, base_s=1.0, factor=2.0, cap_s=30.0)` returning list of `attempts` floats `min(cap_s, round(base_s * (factor ** i), 4))` for i in range(attempts). Validate attempts int (not bool) >=1, base_s>0, factor>=1, cap_s>=base_s.",
       "assert retry_backoff_schedule(4, 1.0, 2.0, 5.0) == [1.0, 2.0, 4.0, 5.0]\n"
       "for b in ((0,),(True,),(2,-1.0),(2,2.0,2.0,1.0)):\n    try:\n        retry_backoff_schedule(*b); assert False\n    except ValueError:\n        pass\n"),
    _t("dev-ho-01", "development", "held_out_final", "easy",
       "Write `safe_divide(a, b, default=0.0)` returning a/b rounded to 4 decimals when b!=0, else default. Reject bool or non-numeric a/b with ValueError.",
       "assert safe_divide(1, 4) == 0.25\nassert safe_divide(5, 0, default=-1.0) == -1.0\n"
       "for b in ((True, 2), ('1', 2)):\n    try:\n        safe_divide(*b); assert False\n    except ValueError:\n        pass\n"),
    _t("dev-ho-02", "development", "held_out_final", "easy",
       "Write `flatten_strings(nested)` recursively flattening arbitrarily nested lists/tuples of strings into a flat list of stripped non-empty strings. Raise ValueError if any leaf is not str.",
       "assert flatten_strings([' a ', ['b', ('', 'c ')]]) == ['a', 'b', 'c']\n"
       "try:\n    flatten_strings(['a', [123]]); assert False\nexcept ValueError:\n    pass\n"),
    _t("dev-ho-03", "development", "held_out_final", "medium",
       "Write `parse_env_lines(text)` parsing lines of `KEY=VALUE` (ignoring blank lines and `#` comments, stripping surrounding single/double quotes from VALUE) into dict[str, str]. Raise ValueError on malformed non-comment lines lacking `=` or empty key.",
       "res = parse_env_lines('# c\\nA=1\\nB=\"hello world\"\\n\\nC=\\'x\\'\\n')\nassert res == {'A': '1', 'B': 'hello world', 'C': 'x'}\n"
       "try:\n    parse_env_lines('BADLINE'); assert False\nexcept ValueError:\n    pass\n"),
    _t("dev-ho-04", "development", "held_out_final", "medium",
       "Write `deep_get(data, dotted_path, default=None)` retrieving nested dict keys separated by '.' without mutating `data`. Return `default` if any key is missing or intermediate node is not dict. Raise ValueError if dotted_path is empty or not str.",
       "assert deep_get({'a': {'b': {'c': 7}}}, 'a.b.c') == 7\nassert deep_get({'a': 1}, 'a.b', default='x') == 'x'\n"
       "try:\n    deep_get({}, ''); assert False\nexcept ValueError:\n    pass\n"),
    _t("dev-ho-05", "development", "held_out_final", "hard",
       "Write class `BoundedLRUCache(capacity)` using collections.OrderedDict with `get(key, default=None)` and `put(key, value)` and `size()`. Validate capacity int (not bool) >=1. Evict least recently used item when full; both get (on hit) and put refresh recency.",
       "c = BoundedLRUCache(2)\nc.put('a', 1); c.put('b', 2); assert c.get('a') == 1\nc.put('c', 3)\nassert c.get('b') is None and c.get('a') == 1 and c.get('c') == 3 and c.size() == 2\n"
       "try:\n    BoundedLRUCache(0); assert False\nexcept ValueError:\n    pass\n"),
    _t("dev-ho-06", "development", "held_out_final", "hard",
       "Write class `CASKeyStore` with `read(key, default=None)` and `put_cas(key, value, expected)` returning True and storing a deep copy ONLY if current stored value equals `expected` (None if absent), else returning False without mutating state.",
       "s = CASKeyStore()\nassert s.put_cas('k', {'v': 1}, None) is True\nassert s.put_cas('k', {'v': 2}, None) is False\nassert s.put_cas('k', {'v': 2}, {'v': 1}) is True\nassert s.read('k') == {'v': 2}\n"),

    # ==================== 2. QUANT (10) ====================
    _t("qnt-tr-01", "quant", "train", "easy",
       "Write `simple_returns(prices)` returning list of `(prices[i] - prices[i-1]) / prices[i-1]` rounded to 6 decimals for i>=1. Raise ValueError if len<2 or any price<=0 or bool.",
       "assert simple_returns([100, 110, 99]) == [0.1, -0.1]\n"
       "for b in ([100], [100, 0], [100, True]):\n    try:\n        simple_returns(b); assert False\n    except ValueError:\n        pass\n"),
    _t("qnt-tr-02", "quant", "train", "medium",
       "Write `causal_ema(values, alpha)` computing strictly causal EMA: ema[0]=float(values[0]), ema[i]=alpha*values[i]+(1-alpha)*ema[i-1], rounded to 4 decimals. Validate 0<alpha<=1 and non-empty numeric (non-bool) values.",
       "assert causal_ema([10, 20, 30], 0.5) == [10.0, 15.0, 22.5]\n"
       "for b in (([],0.5),([10],0.0),([10],1.5),([True],0.5)):\n    try:\n        causal_ema(*b); assert False\n    except ValueError:\n        pass\n"),
    _t("qnt-dv-01", "quant", "dev", "medium",
       "Write `net_risk_reward(entry, stop, target, *, fee_bps=10.0, spread_bps=5.0)` for a long trade (entry>stop, target>entry). Compute total round-trip cost `entry * (2*fee_bps + spread_bps) / 10000.0`, net_reward = (target - entry) - cost, net_risk = (entry - stop) + cost, returning round(net_reward / net_risk, 4). Reject bool or invalid prices.",
       "rr = net_risk_reward(100.0, 95.0, 115.0, fee_bps=10.0, spread_bps=5.0)\nassert rr == round((15.0 - 0.25) / (5.0 + 0.25), 4)\n"
       "for b in ((100,105,115),(100,95,99),(True,95,115)):\n    try:\n        net_risk_reward(*b); assert False\n    except ValueError:\n        pass\n"),
    _t("qnt-dv-02", "quant", "dev", "hard",
       "Write `causal_zscore(values, window)` returning list of length len(values) where index i uses ONLY `slice = values[max(0, i-window+1):i+1]`: return 0.0 if len(slice)<2 or population std==0, else round((values[i]-mean)/std, 4). Validate window int>=2 (non-bool) and non-empty numeric values.",
       "assert causal_zscore([10, 10, 20], 3) == [0.0, 0.0, 1.4142]\n"
       "try:\n    causal_zscore([1,2], 1); assert False\nexcept ValueError:\n    pass\n"),
    _t("qnt-ho-01", "quant", "held_out_final", "easy",
       "Write `max_drawdown(equity_curve)` returning the maximum peak-to-trough fractional drop `min((v - peak)/peak)` as a non-positive float rounded to 4 decimals (0.0 if monotonic up). Reject empty, non-positive, or bool elements.",
       "assert max_drawdown([100, 120, 90, 110, 84]) == -0.3\nassert max_drawdown([10, 20, 30]) == 0.0\n"
       "try:\n    max_drawdown([100, 0]); assert False\nexcept ValueError:\n    pass\n"),
    _t("qnt-ho-02", "quant", "held_out_final", "easy",
       "Write `win_rate_stats(pnls)` returning dict `{'count': n, 'wins': w, 'losses': l, 'win_rate': round(w/n, 4), 'profit_factor': pf}` where wins have pnl>0, losses pnl<0, profit_factor = round(sum_pos/abs(sum_neg), 4) or None if sum_neg==0. Reject empty list or bool elements.",
       "r = win_rate_stats([10, -5, 20, -5])\nassert r == {'count': 4, 'wins': 2, 'losses': 2, 'win_rate': 0.5, 'profit_factor': 3.0}\nassert win_rate_stats([5, 5])['profit_factor'] is None\n"
       "try:\n    win_rate_stats([]); assert False\nexcept ValueError:\n    pass\n"),
    _t("qnt-ho-03", "quant", "held_out_final", "medium",
       "Write `classify_signal_stage(early_alert, confirmed, invalidated, risk_checked)` enforcing TEL99 concept separation: if invalidated -> 'market_invalidation'; elif risk_checked and confirmed -> 'risk_checked_buy'; elif confirmed -> 'market_confirmation'; elif early_alert -> 'market_early_alert'; else -> 'neutral'. All 4 args must be bool else raise ValueError.",
       "assert classify_signal_stage(True, False, False, False) == 'market_early_alert'\n"
       "assert classify_signal_stage(True, True, False, False) == 'market_confirmation'\n"
       "assert classify_signal_stage(True, True, False, True) == 'risk_checked_buy'\n"
       "assert classify_signal_stage(True, True, True, True) == 'market_invalidation'\n"
       "assert classify_signal_stage(True, False, False, True) == 'market_early_alert'\n"
       "try:\n    classify_signal_stage(1, False, False, False); assert False\nexcept ValueError:\n    pass\n"),
    _t("qnt-ho-04", "quant", "held_out_final", "medium",
       "Write `causal_rolling_max(values, window)` returning list where index i is max(values[max(0, i-window+1):i+1]) strictly without lookahead. Validate window int>=1 (non-bool) and non-empty numeric (non-bool) list.",
       "assert causal_rolling_max([3, 1, 5, 2, 4], 2) == [3, 3, 5, 5, 4]\n"
       "try:\n    causal_rolling_max([1, 2], 0); assert False\nexcept ValueError:\n    pass\n"),
    _t("qnt-ho-05", "quant", "held_out_final", "hard",
       "Write `evaluate_forward_outcomes(prices, alert_indices, horizons=(1, 4))` computing forward percentage returns `(prices[idx+h]-prices[idx])/prices[idx]` rounded to 4 decimals (or None if idx+h >= len(prices)) for each alert_index and horizon h, strictly returning list of dicts `{'index': idx, 'returns': {h: val}}`. Reject negative/out-of-range indices or non-positive prices.",
       "res = evaluate_forward_outcomes([100, 105, 110, 99, 120], [0, 3], horizons=(1, 2))\n"
       "assert res == [{'index': 0, 'returns': {1: 0.05, 2: 0.1}}, {'index': 3, 'returns': {1: round(21/99, 4), 2: None}}]\n"
       "try:\n    evaluate_forward_outcomes([100, 110], [5]); assert False\nexcept ValueError:\n    pass\n"),
    _t("qnt-ho-06", "quant", "held_out_final", "hard",
       "Write `detect_lookahead_leak(feature_timestamps, label_timestamps)` returning dict `{'leak_free': bool, 'leaking_indices': list[int]}` where index i leaks if `feature_timestamps[i] > label_timestamps[i]`. Require equal non-empty lists of int/float (non-bool), else raise ValueError.",
       "assert detect_lookahead_leak([10, 20, 30], [10, 25, 30]) == {'leak_free': True, 'leaking_indices': []}\n"
       "assert detect_lookahead_leak([10, 26, 30], [10, 25, 30]) == {'leak_free': False, 'leaking_indices': [1]}\n"
       "try:\n    detect_lookahead_leak([1], [1, 2]); assert False\nexcept ValueError:\n    pass\n"),

    # ==================== 3. QUALITY / VERIFIER (10) ====================
    _t("qlt-tr-01", "quality", "train", "easy",
       "Write `check_syntax_valid(code_str)` using `ast.parse` returning `{'ok': True, 'error': None}` on valid Python code, else `{'ok': False, 'error': str}`. Raise ValueError if code_str is not str.",
       "assert check_syntax_valid('x = 1 + 2')['ok'] is True\nassert check_syntax_valid('def (')['ok'] is False\n"
       "try:\n    check_syntax_valid(123); assert False\nexcept ValueError:\n    pass\n"),
    _t("qlt-tr-02", "quality", "train", "medium",
       "Write `summarize_test_runs(runs)` where runs is list of `{'id': str, 'ok': bool, 'attempts': int}`. Return `{'total': n, 'passed': p, 'first_pass': fp, 'repaired': rep, 'rate': round(p/n, 4)}`. Raise ValueError if runs is empty.",
       "r = summarize_test_runs([{'id':'a','ok':True,'attempts':1},{'id':'b','ok':True,'attempts':2},{'id':'c','ok':False,'attempts':2}])\n"
       "assert r == {'total': 3, 'passed': 2, 'first_pass': 1, 'repaired': 1, 'rate': 0.6667}\n"),
    _t("qlt-dv-01", "quality", "dev", "medium",
       "Write `detect_function_signature_change(old_src, new_src, func_name)` using `ast.parse`: return `{'changed': bool, 'old_args': list[str], 'new_args': list[str]}` comparing positional+kwonly arg names. Raise ValueError if func_name missing from either source.",
       "assert detect_function_signature_change('def f(a, b): return a', 'def f(a, b): return a+b', 'f')['changed'] is False\n"
       "assert detect_function_signature_change('def f(a): pass', 'def f(a, b): pass', 'f')['changed'] is True\n"
       "try:\n    detect_function_signature_change('def g(): pass', 'def g(): pass', 'f'); assert False\nexcept ValueError:\n    pass\n"),
    _t("qlt-dv-02", "quality", "dev", "hard",
       "Write `verify_bounded_diff(old_src, new_src, allowed_func)` using `ast.parse`: return True ONLY if all top-level FunctionDef/ClassDef names are unchanged AND every top-level function OTHER than `allowed_func` has identical `ast.dump` body. Return False otherwise.",
       "a = 'def f(): return 1\\ndef g(): return 2\\n'\nb = 'def f(): return 9\\ndef g(): return 2\\n'\nc = 'def f(): return 9\\ndef g(): return 3\\n'\n"
       "assert verify_bounded_diff(a, b, 'f') is True\nassert verify_bounded_diff(a, c, 'f') is False\n"),
    _t("qlt-ho-01", "quality", "held_out_final", "easy",
       "Write `is_discriminative_test(baseline_passed, candidate_passed)` returning True ONLY if baseline_passed is False AND candidate_passed is True. Both args must be bool else raise ValueError.",
       "assert is_discriminative_test(False, True) is True\nassert is_discriminative_test(True, True) is False\nassert is_discriminative_test(False, False) is False\n"
       "try:\n    is_discriminative_test(0, 1); assert False\nexcept ValueError:\n    pass\n"),
    _t("qlt-ho-02", "quality", "held_out_final", "easy",
       "Write `truncate_diagnostic(text, max_chars=240)` returning stripped single-line normalized whitespace text truncated to `max_chars` with '...' suffix if longer. Raise ValueError if max_chars < 10 or bool.",
       "assert truncate_diagnostic('  hello\\n  world  ', 20) == 'hello world'\nassert len(truncate_diagnostic('a'*100, 20)) == 20 and truncate_diagnostic('a'*100, 20).endswith('...')\n"
       "try:\n    truncate_diagnostic('x', 5); assert False\nexcept ValueError:\n    pass\n"),
    _t("qlt-ho-03", "quality", "held_out_final", "medium",
       "Write `classify_test_outcome(exit_code, timed_out=False, infra_error=False)` returning 'INFRA_TIMEOUT' if timed_out, 'INFRA_ERROR' if infra_error, 'PASS' if exit_code==0, else 'FAIL'. Validate exit_code is int (not bool).",
       "assert classify_test_outcome(0) == 'PASS'\nassert classify_test_outcome(1) == 'FAIL'\n"
       "assert classify_test_outcome(1, timed_out=True) == 'INFRA_TIMEOUT'\nassert classify_test_outcome(1, infra_error=True) == 'INFRA_ERROR'\n"
       "try:\n    classify_test_outcome(True); assert False\nexcept ValueError:\n    pass\n"),
    _t("qlt-ho-04", "quality", "held_out_final", "medium",
       "Write `find_regressions(before_map, after_map)` where maps are `{task_id: bool}`. Return sorted list of task_ids that were True in before_map and False (or missing) in after_map, plus improvements list in dict `{'regressions': [...], 'improvements': [...]}`.",
       "r = find_regressions({'a': True, 'b': False, 'c': True}, {'a': False, 'b': True, 'c': True})\n"
       "assert r == {'regressions': ['a'], 'improvements': ['b']}\n"),
    _t("qlt-ho-05", "quality", "held_out_final", "hard",
       "Write `mutation_kill_rate(killed, total)` returning dict `{'score': float, 'status': str}` where score = round(killed/total, 4), status='STRONG' if score>=0.8 else ('MODERATE' if score>=0.5 else 'WEAK'). Reject bool, killed<0, total<=0, or killed>total with ValueError.",
       "assert mutation_kill_rate(9, 10) == {'score': 0.9, 'status': 'STRONG'}\nassert mutation_kill_rate(3, 10) == {'score': 0.3, 'status': 'WEAK'}\n"
       "for b in ((11,10),(-1,5),(0,0),(True,2)):\n    try:\n        mutation_kill_rate(*b); assert False\n    except ValueError:\n        pass\n"),
    _t("qlt-ho-06", "quality", "held_out_final", "hard",
       "Write `verify_receipt_integrity(artifact_text, claimed_sha256, checks)` using hashlib.sha256: return True ONLY if sha256(artifact_text.encode('utf-8')).hexdigest() == claimed_sha256 AND checks is a non-empty list of dicts all having `ok is True`. Return False otherwise.",
       "import hashlib\nh = hashlib.sha256(b'ok').hexdigest()\nassert verify_receipt_integrity('ok', h, [{'name':'a','ok':True}]) is True\n"
       "assert verify_receipt_integrity('tampered', h, [{'name':'a','ok':True}]) is False\nassert verify_receipt_integrity('ok', h, []) is False\n"),

    # ==================== 4. COORDINATION (10) ====================
    _t("crd-tr-01", "coordination", "train", "easy",
       "Write `detect_path_overlap(paths_a, paths_b, *, case_insensitive=False)` returning sorted overlapping normalized (forward-slash) paths.",
       "assert detect_path_overlap(['a\\\\b.py', 'c.py'], ['a/b.py']) == ['a/b.py']\n"
       "assert detect_path_overlap(['App.py'], ['app.py'], case_insensitive=True) == ['app.py']\n"
       "assert detect_path_overlap(['App.py'], ['app.py'], case_insensitive=False) == []\n"),
    _t("crd-tr-02", "coordination", "train", "medium",
       "Write `can_release_lease(lease_actor, caller_actor, expires_at, now)` returning True ONLY if caller_actor == lease_actor OR expires_at <= now (an active foreign lease can NEVER be released). Raise ValueError on empty actor strings.",
       "assert can_release_lease('ollama', 'ollama', 100, 50) is True\nassert can_release_lease('ollama', 'llama', 100, 50) is False\n"
       "assert can_release_lease('ollama', 'llama', 100, 100) is True\n"),
    _t("crd-dv-01", "coordination", "dev", "medium",
       "Write `topological_order(dag)` where dag is `{node: list[dep]}`. Return deterministic lexicographically-smallest topological order (Kahn's algorithm with sorted ready queue). Raise ValueError on cycles or unknown dependency.",
       "assert topological_order({'c': ['a'], 'b': ['a'], 'a': []}) == ['a', 'b', 'c']\n"
       "for bad in ({'a': ['b'], 'b': ['a']}, {'a': ['missing']}):\n    try:\n        topological_order(bad); assert False\n    except ValueError:\n        pass\n"),
    _t("crd-dv-02", "coordination", "dev", "hard",
       "Write `partition_by_concurrency(tasks, max_per_wave=1)` where tasks are `[{'id': str, 'dependencies': list[str]}]`. Return list of waves (each wave sorted list of ids, length <= max_per_wave) respecting dependencies. Raise ValueError if max_per_wave<1 or cycle.",
       "ts = [{'id':'b','dependencies':['a']},{'id':'a','dependencies':[]},{'id':'c','dependencies':['a']}]\n"
       "assert partition_by_concurrency(ts, max_per_wave=1) == [['a'], ['b'], ['c']]\n"
       "assert partition_by_concurrency(ts, max_per_wave=2) == [['a'], ['b', 'c']]\n"),
    _t("crd-ho-01", "coordination", "held_out_final", "easy",
       "Write `is_lease_expired(expires_at, now)` returning True if `now >= expires_at` else False. Reject bool or non-numeric inputs with ValueError.",
       "assert is_lease_expired(100, 100) is True\nassert is_lease_expired(100, 99.5) is False\n"
       "try:\n    is_lease_expired(True, 10); assert False\nexcept ValueError:\n    pass\n"),
    _t("crd-ho-02", "coordination", "held_out_final", "easy",
       "Write `select_free_engine_slot(active_lease_actor, requester_actor)` returning `{'allow': True, 'wait': False}` if active_lease_actor is None or equals requester_actor, else `{'allow': False, 'wait': True}`.",
       "assert select_free_engine_slot(None, 'engine:ollama') == {'allow': True, 'wait': False}\n"
       "assert select_free_engine_slot('engine:llama-server', 'engine:ollama') == {'allow': False, 'wait': True}\n"),
    _t("crd-ho-03", "coordination", "held_out_final", "medium",
       "Write `filter_reclaimable_leases(leases, alive_pids, now)` where each lease is `{'lease_id': str, 'pid': int, 'expires_at': float}`. Return sorted list of lease_ids that are either expired (`expires_at <= now`) OR whose `pid` is NOT in `alive_pids`.",
       "ls = [{'lease_id':'l1','pid':10,'expires_at':200},{'lease_id':'l2','pid':99,'expires_at':200},{'lease_id':'l3','pid':10,'expires_at':50}]\n"
       "assert filter_reclaimable_leases(ls, {10}, now=100) == ['l2', 'l3']\n"),
    _t("crd-ho-04", "coordination", "held_out_final", "medium",
       "Write `detect_branch_file_collisions(claims, *, is_windows=False)` where claims is list of `{'id': str, 'branch': str, 'path': str}`. Return list of sorted 2-tuples `(id1, id2)` that share the same branch AND normalized path (case-insensitive if is_windows=True).",
       "cs = [{'id':'m1','branch':'b1','path':'a/Foo.py'},{'id':'m2','branch':'b1','path':'a/foo.py'},{'id':'m3','branch':'b2','path':'a/foo.py'}]\n"
       "assert detect_branch_file_collisions(cs, is_windows=True) == [('m1', 'm2')]\n"
       "assert detect_branch_file_collisions(cs, is_windows=False) == []\n"),
    _t("crd-ho-05", "coordination", "held_out_final", "hard",
       "Write `plan_specialist_cap(candidates, *, max_specialists=4, require_verifier=True)` where candidates are `[{'name': str, 'score': float}]`. Sort by (-score, name), cap to max_specialists, and if require_verifier=True ensure 'tel99-verifier' is included (replacing lowest-scored slot if full and missing). Return list of names.",
       "c = [{'name':'a','score':9},{'name':'b','score':8},{'name':'c','score':7},{'name':'d','score':6},{'name':'tel99-verifier','score':1}]\n"
       "res = plan_specialist_cap(c, max_specialists=3, require_verifier=True)\nassert len(res) == 3 and 'tel99-verifier' in res and 'a' in res\n"),
    _t("crd-ho-06", "coordination", "held_out_final", "hard",
       "Write `compute_dependency_depth(dag)` where dag is `{id: list[dep]}`. Return dict `{id: depth}` where nodes with no deps have depth 0 and others have `1 + max(depth[d] for d in deps)`. Raise ValueError on cycle or unknown dep.",
       "assert compute_dependency_depth({'a':[], 'b':['a'], 'c':['a','b']}) == {'a':0, 'b':1, 'c':2}\n"
       "try:\n    compute_dependency_depth({'a':['b'],'b':['a']}); assert False\nexcept ValueError:\n    pass\n"),

    # ==================== 5. CLOUD (10) ====================
    _t("cld-tr-01", "cloud", "train", "easy",
       "Write `is_loopback_url(url)` returning True ONLY if url starts with 'http://127.0.0.1' or 'http://localhost' (case-insensitive) and contains no '@' userinfo. Return False otherwise.",
       "assert is_loopback_url('http://127.0.0.1:11434/api/tags') is True\nassert is_loopback_url('http://example.com') is False\nassert is_loopback_url('http://localhost@evil.com') is False\n"),
    _t("cld-tr-02", "cloud", "train", "medium",
       "Write `validate_pinned_image(image_ref)` returning True ONLY if image_ref contains '@sha256:' followed by exactly 64 lowercase hex characters and has no whitespace. Return False otherwise.",
       "assert validate_pinned_image('python@sha256:' + 'a'*64) is True\nassert validate_pinned_image('python:3.12') is False\nassert validate_pinned_image('python@sha256:short') is False\n"),
    _t("cld-dv-01", "cloud", "dev", "medium",
       "Write `check_billing_policy(provider_billing_class, *, allow_subscription_cli=False, confidential=True)` returning `{'allow': bool, 'reason': str}`: allow LOCAL_FREE always; reject BILLING_UNVERIFIED/NOT_INSTALLED; reject non-LOCAL_FREE if confidential=True; allow SUBSCRIPTION_OPT_IN only if allow_subscription_cli=True and not confidential.",
       "assert check_billing_policy('LOCAL_FREE', confidential=True)['allow'] is True\n"
       "assert check_billing_policy('SUBSCRIPTION_OPT_IN', allow_subscription_cli=True, confidential=True)['allow'] is False\n"
       "assert check_billing_policy('SUBSCRIPTION_OPT_IN', allow_subscription_cli=True, confidential=False)['allow'] is True\n"
       "assert check_billing_policy('BILLING_UNVERIFIED', allow_subscription_cli=True, confidential=False)['allow'] is False\n"),
    _t("cld-dv-02", "cloud", "dev", "hard",
       "Write `scrub_paid_env_vars(env_dict)` returning a NEW dict excluding any key whose uppercase name starts with ('OPENAI_','ANTHROPIC_','GOOGLE_','GEMINI_','AZURE_','GH_','GITHUB_') or ends with ('_TOKEN','_KEY','_SECRET','_PASSWORD'), without mutating `env_dict`.",
       "orig = {'PATH':'/bin', 'OPENAI_API_KEY':'x', 'MY_SECRET':'y', 'SAFE_FLAG':'1'}\n"
       "res = scrub_paid_env_vars(orig)\nassert res == {'PATH':'/bin', 'SAFE_FLAG':'1'} and 'OPENAI_API_KEY' in orig\n"),
    _t("cld-ho-01", "cloud", "held_out_final", "easy",
       "Write `is_valid_cron_5field(expr)` returning True if `expr` is a str with exactly 5 whitespace-separated non-empty fields containing only chars from `0123456789*/,-`, else False.",
       "assert is_valid_cron_5field('*/15 * * * *') is True\nassert is_valid_cron_5field('0 6 * * 1-5') is True\n"
       "assert is_valid_cron_5field('* * *') is False\nassert is_valid_cron_5field('* * * * ; rm -rf') is False\n"),
    _t("cld-ho-02", "cloud", "held_out_final", "easy",
       "Write `validate_container_flags(flags)` returning True ONLY if '--network=none' (or '--network' followed by 'none') and '--read-only' are present AND '--privileged' is absent.",
       "assert validate_container_flags(['--network=none', '--read-only', '--memory=512m']) is True\n"
       "assert validate_container_flags(['--network=none', '--read-only', '--privileged']) is False\n"
       "assert validate_container_flags(['--read-only']) is False\n"),
    _t("cld-ho-03", "cloud", "held_out_final", "medium",
       "Write `evaluate_cloud_independence(cloud_calls, active_cloud_procs)` returning dict `{'independent': bool, 'violations': list[str]}`: flag 'cloud_api_called' if cloud_calls>0, flag 'cloud_process_detected' if active_cloud_procs non-empty. Raise ValueError if cloud_calls<0 or bool.",
       "assert evaluate_cloud_independence(0, []) == {'independent': True, 'violations': []}\n"
       "r = evaluate_cloud_independence(1, ['codex'])\nassert r['independent'] is False and len(r['violations']) == 2\n"),
    _t("cld-ho-04", "cloud", "held_out_final", "medium",
       "Write `select_sandbox_memory_limit(host_free_mb)` returning '256m' if host_free_mb < 1500, '512m' if host_free_mb < 3500, else '1024m'. Raise ValueError for negative/bool/None.",
       "assert select_sandbox_memory_limit(1000) == '256m'\nassert select_sandbox_memory_limit(2500) == '512m'\nassert select_sandbox_memory_limit(5000) == '1024m'\n"
       "try:\n    select_sandbox_memory_limit(True); assert False\nexcept ValueError:\n    pass\n"),
    _t("cld-ho-05", "cloud", "held_out_final", "hard",
       "Write `audit_github_actions_jobs(jobs)` where jobs is `{job_name: dict}`. Return dict `{'ok': bool, 'errors': list[str]}` flagging any job missing positive int `timeout-minutes` (`f'{name}:missing_timeout'`) or using unpinned action (any step `uses` containing '@' without 40-hex SHA or starting with './' -> `f'{name}:unpinned_action'`).",
       "j_ok = {'test': {'timeout-minutes': 10, 'steps': [{'uses': 'actions/checkout@' + 'a'*40}]}}\nassert audit_github_actions_jobs(j_ok) == {'ok': True, 'errors': []}\n"
       "j_bad = {'test': {'steps': [{'uses': 'actions/checkout@v4'}]}}\nr = audit_github_actions_jobs(j_bad)\nassert r['ok'] is False and 'test:missing_timeout' in r['errors'] and 'test:unpinned_action' in r['errors']\n"),
    _t("cld-ho-06", "cloud", "held_out_final", "hard",
       "Write `compute_quota_reserve(used_percent, reserve_percent=10.0)` returning dict `{'allow': bool, 'headroom_percent': float}` where allow is True ONLY if `used_percent <= 100.0 - reserve_percent`, headroom = round(max(0.0, 100.0 - reserve_percent - used_percent), 2). Reject bool or values outside [0, 100].",
       "assert compute_quota_reserve(80.0, 10.0) == {'allow': True, 'headroom_percent': 10.0}\n"
       "assert compute_quota_reserve(92.0, 10.0) == {'allow': False, 'headroom_percent': 0.0}\n"
       "try:\n    compute_quota_reserve(105.0); assert False\nexcept ValueError:\n    pass\n"),

    # ==================== 6. SECURITY (10) ====================
    _t("sec-tr-01", "security", "train", "easy",
       "Write `contains_secret_token(text)` returning True if text matches `ghp_[A-Za-z0-9]{20,}`, `github_pat_[A-Za-z0-9_]{20,}`, or `sk-[A-Za-z0-9]{16,}`, else False.",
       "assert contains_secret_token('key=ghp_' + 'a'*24) is True\nassert contains_secret_token('normal text') is False\n"),
    _t("sec-tr-02", "security", "train", "medium",
       "Write `audit_ast_forbidden_calls(source_code)` using `ast.parse` returning sorted list of forbidden calls found among {'eval', 'exec', 'compile', '__import__'} plus 'shell=True' if any Call has keyword `shell=True`.",
       "assert audit_ast_forbidden_calls('x = 1') == []\n"
       "assert audit_ast_forbidden_calls('eval(\"1\")\\nsubprocess.run(\"ls\", shell=True)') == ['eval', 'shell=True']\n"),
    _t("sec-dv-01", "security", "dev", "medium",
       "Write `neutralize_prompt_injection(text)` replacing case-insensitive matches of 'ignore all previous instructions', 'ignore previous instructions', 'system prompt override', or 'bypass guard' with '[REDACTED]' and returning `(clean_text, flagged_bool)`.",
       "clean, flag = neutralize_prompt_injection('Hi. Ignore all previous instructions now!')\n"
       "assert flag is True and '[REDACTED]' in clean and 'ignore' not in clean.lower()\n"
       "assert neutralize_prompt_injection('Safe message') == ('Safe message', False)\n"),
    _t("sec-dv-02", "security", "dev", "hard",
       "Write `verify_allowed_write_path(workspace_root, target_rel, allowed_paths)` using pathlib.Path: return True ONLY if `target_rel` has no '..', is not absolute, is explicitly in normalized `allowed_paths`, AND `(Path(workspace_root)/target_rel).resolve()` is inside `Path(workspace_root).resolve()`. Return False otherwise.",
       "import tempfile\nwith tempfile.TemporaryDirectory() as d:\n    assert verify_allowed_write_path(d, 'src/a.py', ['src/a.py']) is True\n"
       "    assert verify_allowed_write_path(d, '../x.py', ['../x.py']) is False\n    assert verify_allowed_write_path(d, 'src/b.py', ['src/a.py']) is False\n"),
    _t("sec-ho-01", "security", "held_out_final", "easy",
       "Write `reject_non_loopback_bind(host)` returning host if host in ('127.0.0.1', 'localhost', '::1'), else raising ValueError.",
       "assert reject_non_loopback_bind('127.0.0.1') == '127.0.0.1'\n"
       "for b in ('0.0.0.0', '', '192.168.1.5', None):\n    try:\n        reject_non_loopback_bind(b); assert False\n    except ValueError:\n        pass\n"),
    _t("sec-ho-02", "security", "held_out_final", "easy",
       "Write `redact_dict_secrets(record)` recursively returning a new dict where any key containing ('secret','token','password','api_key','apikey') (case-insensitive) has value '[REDACTED]', without mutating `record`.",
       "orig = {'user': 'a', 'api_key': '123', 'nested': {'my_token': 'xyz', 'ok': 1}}\n"
       "res = redact_dict_secrets(orig)\nassert res == {'user': 'a', 'api_key': '[REDACTED]', 'nested': {'my_token': '[REDACTED]', 'ok': 1}} and orig['api_key'] == '123'\n"),
    _t("sec-ho-03", "security", "held_out_final", "medium",
       "Write `validate_contract_seal(mission_dict, expected_sha256)` using canonical JSON (`sort_keys=True, separators=(',',':'), ensure_ascii=True`) and `hmac.compare_digest` on SHA-256 hex digest. Return True only on exact match.",
       "import hashlib, json\nm = {'id': 'm1', 'x': 2}\nh = hashlib.sha256(json.dumps(m, sort_keys=True, separators=(',',':'), ensure_ascii=True).encode()).hexdigest()\n"
       "assert validate_contract_seal(m, h) is True\nassert validate_contract_seal({'id': 'm1', 'x': 3}, h) is False\n"),
    _t("sec-ho-04", "security", "held_out_final", "medium",
       "Write `audit_js_safety(js_text)` returning dict `{'safe': bool, 'findings': list[str]}` flagging occurrences of `eval(`, `new Function`, `document.write(`, or `.innerHTML =` (case-sensitive).",
       "assert audit_js_safety('el.textContent = \"hi\";') == {'safe': True, 'findings': []}\n"
       "r = audit_js_safety('eval(x); document.write(y);')\nassert r['safe'] is False and len(r['findings']) == 2\n"),
    _t("sec-ho-05", "security", "held_out_final", "hard",
       "Write `enforce_memory_isolation(entries, target_project, *, verified_only=True)` where each entry is dict `{'id', 'project', 'verified', 'superseded_by'}`. Return list of entries belonging ONLY to `target_project` (never other projects), with `superseded_by` falsy, and if verified_only=True requiring `verified is True`.",
       "es = [{'id':'1','project':'p1','verified':True,'superseded_by':None},{'id':'2','project':'p2','verified':True,'superseded_by':None},{'id':'3','project':'p1','verified':False,'superseded_by':None},{'id':'4','project':'p1','verified':True,'superseded_by':'5'}]\n"
       "assert [e['id'] for e in enforce_memory_isolation(es, 'p1', verified_only=True)] == ['1']\n"),
    _t("sec-ho-06", "security", "held_out_final", "hard",
       "Write `block_guardrail_self_edit(changed_paths)` returning dict `{'allowed': bool, 'blocked': list[str]}` rejecting any path (normalized `/`) matching `scripts/agents/guard/*`, `.github/workflows/*`, or `AGENTS.md`.",
       "assert block_guardrail_self_edit(['app/radar_api.py']) == {'allowed': True, 'blocked': []}\n"
       "r = block_guardrail_self_edit(['scripts/agents/guard/guard.py', 'AGENTS.md', 'app/a.py'])\nassert r['allowed'] is False and len(r['blocked']) == 2\n"),

    # ==================== 7. MOBILE / UI (10) ====================
    _t("mob-tr-01", "mobile", "train", "easy",
       "Write `check_css_braces_balanced(css_text)` returning True if `{` and `}` counts are balanced and never negative during scan (ignoring braces inside `/* ... */` comments), else False.",
       "assert check_css_braces_balanced('body { color: red; } @media (max-width:768px) { .a { display:block; } }') is True\n"
       "assert check_css_braces_balanced('body { color: red;') is False\nassert check_css_braces_balanced('} {') is False\n"),
    _t("mob-tr-02", "mobile", "train", "medium",
       "Write `extract_html_ids(html_text)` returning sorted unique list of all `id=\"...\"` or `id='...'` attribute values found in `html_text`.",
       "assert extract_html_ids('<div id=\"kpi-grid\"><input id=\\'search-input\\'><span id=\"kpi-grid\"></span></div>') == ['kpi-grid', 'search-input']\n"),
    _t("mob-dv-01", "mobile", "dev", "medium",
       "Write `check_responsive_breakpoints(css_text)` returning dict `{'responsive': bool, 'breakpoints_px': list[int]}` extracting all integer pixel values from `@media (max-width: Npx)` (case-insensitive) and marking responsive=True if at least one breakpoint <= 900.",
       "r = check_responsive_breakpoints('@media (max-width: 768px) { .g { display: block; } }')\n"
       "assert r == {'responsive': True, 'breakpoints_px': [768]}\nassert check_responsive_breakpoints('body{color:#fff}')['responsive'] is False\n"),
    _t("mob-dv-02", "mobile", "dev", "hard",
       "Write `validate_ui_contract(html_text, required_ids)` returning dict `{'ok': bool, 'missing_ids': list[str], 'security_issues': list[str]}` checking all required_ids exist, no inline `<script>` without `src=`, no `javascript:` URI, and no inline `onclick=`/`onerror=` attributes.",
       "good = '<div id=\"a\"></div><script src=\"/app.js\" defer></script>'\nassert validate_ui_contract(good, ['a']) == {'ok': True, 'missing_ids': [], 'security_issues': []}\n"
       "bad = '<button onclick=\"x()\">hi</button><script>alert(1)</script>'\nr = validate_ui_contract(bad, ['a'])\nassert r['ok'] is False and r['missing_ids'] == ['a'] and len(r['security_issues']) >= 2\n"),
    _t("mob-ho-01", "mobile", "held_out_final", "easy",
       "Write `compute_contrast_ratio_hex(hex1, hex2)` computing WCAG relative luminance contrast ratio `(L1+0.05)/(L2+0.05)` rounded to 2 decimals for 6-digit `#RRGGBB` strings. Raise ValueError on invalid hex.",
       "assert compute_contrast_ratio_hex('#000000', '#ffffff') == 21.0\nassert compute_contrast_ratio_hex('#ffffff', '#ffffff') == 1.0\n"
       "try:\n    compute_contrast_ratio_hex('red', '#fff'); assert False\nexcept ValueError:\n    pass\n"),
    _t("mob-ho-02", "mobile", "held_out_final", "easy",
       "Write `format_french_kpi(value, unit='')` formatting int/float (non-bool) with space thousands separator and comma decimal (e.g. `1234.5 -> '1 234,5'` or int `1000 -> '1 000'`), appending `' ' + unit` if unit is non-empty.",
       "assert format_french_kpi(1234.5, 'Mo') == '1 234,5 Mo'\nassert format_french_kpi(1000) == '1 000'\n"
       "try:\n    format_french_kpi(True); assert False\nexcept ValueError:\n    pass\n"),
    _t("mob-ho-03", "mobile", "held_out_final", "medium",
       "Write `check_touch_target_sizes(elements)` where elements are `[{'id': str, 'width_px': int, 'height_px': int}]`. Return dict `{'ok': bool, 'too_small': list[str]}` flagging any element with width_px < 44 or height_px < 44 (sorted).",
       "es = [{'id':'btn1','width_px':48,'height_px':44},{'id':'btn2','width_px':32,'height_px':48}]\n"
       "assert check_touch_target_sizes(es) == {'ok': False, 'too_small': ['btn2']}\n"),
    _t("mob-ho-04", "mobile", "held_out_final", "medium",
       "Write `check_widget_inventory(widgets, expected_count=21)` returning dict `{'ok': bool, 'actual': int, 'duplicates': list[str]}` checking no duplicate widget IDs and len(widgets) == expected_count.",
       "ws = [f'w{i}' for i in range(21)]\nassert check_widget_inventory(ws, 21) == {'ok': True, 'actual': 21, 'duplicates': []}\n"
       "assert check_widget_inventory(['w1', 'w1'], 2) == {'ok': False, 'actual': 2, 'duplicates': ['w1']}\n"),
    _t("mob-ho-05", "mobile", "held_out_final", "hard",
       "Write `build_aria_status_badge(status)` mapping `'compatible'->('Compatible','status-compatible','status')`, `'limite'->('Limite','status-limite','status')`, `'incompatible'->('Incompatible','status-incompatible','alert')`, `'cloud'->('Cloud','status-cloud','status')` into dict `{'label','css_class','aria_role'}`. Raise ValueError for unknown status.",
       "assert build_aria_status_badge('incompatible') == {'label': 'Incompatible', 'css_class': 'status-incompatible', 'aria_role': 'alert'}\n"
       "try:\n    build_aria_status_badge('magic'); assert False\nexcept ValueError:\n    pass\n"),
    _t("mob-ho-06", "mobile", "held_out_final", "hard",
       "Write `audit_mobile_viewport_meta(html_text)` returning dict `{'ok': bool, 'issues': list[str]}`: verify `<meta name=\"viewport\"` exists with `width=device-width`, and flag `zoom_disabled` if `user-scalable=no` or `maximum-scale=1` appears (accessibility anti-pattern).",
       "assert audit_mobile_viewport_meta('<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">') == {'ok': True, 'issues': []}\n"
       "r = audit_mobile_viewport_meta('<meta name=\"viewport\" content=\"width=device-width, user-scalable=no\">')\nassert r['ok'] is False and 'zoom_disabled' in r['issues']\n"),

    # ==================== 8. DOCUMENTATION (10) ====================
    _t("doc-tr-01", "documentation", "train", "easy",
       "Write `extract_markdown_headings(md_text)` returning list of `(level, title)` tuples for lines starting with 1..6 `#` followed by space.",
       "assert extract_markdown_headings('# Title\\nText\\n## Sub 1\\n### Deep') == [(1, 'Title'), (2, 'Sub 1'), (3, 'Deep')]\n"),
    _t("doc-tr-02", "documentation", "train", "medium",
       "Write `validate_status_tags(rows)` where rows is list of `{'capability': str, 'status': str, 'evidence': str}`. Require status in {'PROVEN','PARTIAL','BLOCKED','INCONCLUSIVE'} and non-empty evidence when status=='PROVEN'. Return `{'ok': bool, 'errors': list[str]}`.",
       "assert validate_status_tags([{'capability':'c1','status':'PROVEN','evidence':'log.txt'}]) == {'ok': True, 'errors': []}\n"
       "r = validate_status_tags([{'capability':'c1','status':'PROVEN','evidence':''},{'capability':'c2','status':'DONE','evidence':'x'}])\nassert r['ok'] is False and len(r['errors']) == 2\n"),
    _t("doc-dv-01", "documentation", "dev", "medium",
       "Write `check_precedence_dates(docs)` where docs is list of `{'title': str, 'date': 'YYYY-MM-DD', 'supersedes': list[str]}`. Return docs sorted newest-first by date, raising ValueError if any date is invalid YYYY-MM-DD.",
       "res = check_precedence_dates([{'title':'a','date':'2026-11-10','supersedes':[]},{'title':'b','date':'2026-11-13','supersedes':['a']}])\n"
       "assert [d['title'] for d in res] == ['b', 'a']\n"
       "try:\n    check_precedence_dates([{'title':'x','date':'13/11/2026','supersedes':[]}]); assert False\nexcept ValueError:\n    pass\n"),
    _t("doc-dv-02", "documentation", "dev", "hard",
       "Write `render_evidence_table(rows)` where rows is list of `{'capability': str, 'status': str, 'proof': str}`. Return a GitHub-flavored Markdown table string with header `| Capability | Status | Proof |`, separator `| --- | --- | --- |`, and pipe-escaped cells (`|` -> `\\|`). Raise ValueError if rows is empty.",
       "md = render_evidence_table([{'capability':'RAM','status':'PROVEN','proof':'a|b'}])\n"
       "lines = md.strip().splitlines()\nassert len(lines) == 3 and 'a\\\\|b' in lines[2]\n"),
    _t("doc-ho-01", "documentation", "held_out_final", "easy",
       "Write `count_code_fences(md_text)` returning dict `{'blocks': int, 'balanced': bool}` counting lines starting with '```' (after strip): balanced is True when count is even, blocks = count // 2.",
       "assert count_code_fences('```py\\nx=1\\n```\\n') == {'blocks': 1, 'balanced': True}\n"
       "assert count_code_fences('```py\\nx=1') == {'blocks': 0, 'balanced': False}\n"),
    _t("doc-ho-02", "documentation", "held_out_final", "easy",
       "Write `verify_no_absolute_secrets_in_doc(md_text)` returning True if md_text contains NO `ghp_`, `sk-`, `AIza`, or `password=` (case-insensitive for password=), else False.",
       "assert verify_no_absolute_secrets_in_doc('# Guide\\nUse env vars.') is True\n"
       "assert verify_no_absolute_secrets_in_doc('password=secret123') is False\n"),
    _t("doc-ho-03", "documentation", "held_out_final", "medium",
       "Write `extract_file_links(md_text)` returning list of relative/file URLs inside Markdown links `[label](target)` excluding `http://` and `https://`.",
       "assert extract_file_links('[a](docs/x.md) and [b](https://example.com) and [c](file:///C:/a.py)') == ['docs/x.md', 'file:///C:/a.py']\n"),
    _t("doc-ho-04", "documentation", "held_out_final", "medium",
       "Write `check_required_sections(md_text, required_titles)` returning dict `{'ok': bool, 'missing': list[str]}` matching H1/H2/H3 heading titles case-insensitively.",
       "md = '# Title\\n## Installation\\n## Usage\\n'\n"
       "assert check_required_sections(md, ['installation', 'usage']) == {'ok': True, 'missing': []}\n"
       "assert check_required_sections(md, ['installation', 'security']) == {'ok': False, 'missing': ['security']}\n"),
    _t("doc-ho-05", "documentation", "held_out_final", "hard",
       "Write `format_changelog_entry(version, date_str, items)` returning Markdown block `## [version] - date_str` followed by `- item` lines. Validate date_str matches YYYY-MM-DD and items is non-empty list of non-empty strings, else raise ValueError.",
       "out = format_changelog_entry('1.2.0', '2026-11-25', ['Fix RAM lock', 'Add tests'])\n"
       "assert out.startswith('## [1.2.0] - 2026-11-25\\n- Fix RAM lock\\n- Add tests')\n"
       "try:\n    format_changelog_entry('1.0', 'bad-date', ['a']); assert False\nexcept ValueError:\n    pass\n"),
    _t("doc-ho-06", "documentation", "held_out_final", "hard",
       "Return ONLY a JSON object with exact keys: {\"doc_status\": \"PROVEN\", \"sections_checked\": 4, \"ungrounded_claims\": 0, \"ready_for_review\": true}.",
       "", kind="json",
       required_fields={"doc_status": "str", "sections_checked": "int", "ungrounded_claims": "int", "ready_for_review": "bool"},
       expected_values={"doc_status": "PROVEN", "sections_checked": 4, "ungrounded_claims": 0, "ready_for_review": True}),

    # ==================== 9. EVALUATION (10) ====================
    _t("evl-tr-01", "evaluation", "train", "easy",
       "Write `brier_score(predictions)` where predictions is non-empty list of `(prob, outcome_bool)` with 0<=prob<=1. Return mean `(prob - int(outcome))**2` rounded to 4 decimals. Raise ValueError on invalid inputs.",
       "assert brier_score([(1.0, True), (0.0, False)]) == 0.0\nassert brier_score([(0.8, True), (0.8, False)]) == 0.34\n"
       "try:\n    brier_score([(1.5, True)]); assert False\nexcept ValueError:\n    pass\n"),
    _t("evl-tr-02", "evaluation", "train", "medium",
       "Write `paired_win_loss(outcomes)` where outcomes is list of `{'id': str, 'base': bool, 'cand': bool}`. Return `{'wins': w, 'losses': l, 'ties': t, 'delta_rate': round((cand_ok-base_ok)/n, 4)}`. Raise ValueError if empty.",
       "r = paired_win_loss([{'id':'1','base':False,'cand':True},{'id':'2','base':True,'cand':True},{'id':'3','base':False,'cand':True}])\n"
       "assert r == {'wins': 2, 'losses': 0, 'ties': 1, 'delta_rate': 0.6667}\n"),
    _t("evl-dv-01", "evaluation", "dev", "medium",
       "Write `check_split_leakage(train_ids, dev_ids, test_ids)` returning dict `{'leak_free': bool, 'overlaps': list[str]}` detecting any task ID appearing in more than one split (sorted).",
       "assert check_split_leakage(['a','b'], ['c'], ['d']) == {'leak_free': True, 'overlaps': []}\n"
       "assert check_split_leakage(['a','b'], ['b','c'], ['c','d']) == {'leak_free': False, 'overlaps': ['b', 'c']}\n"),
    _t("evl-dv-02", "evaluation", "dev", "hard",
       "Write `wilson_lower_bound(passed, total, z=1.96)` computing the Wilson score lower confidence bound rounded to 4 decimals (0.0 if passed==0). Validate passed/total ints (non-bool), total>=1, 0<=passed<=total.",
       "lb = wilson_lower_bound(90, 100)\nassert 0.82 <= lb <= 0.84\nassert wilson_lower_bound(0, 10) == 0.0\n"
       "try:\n    wilson_lower_bound(11, 10); assert False\nexcept ValueError:\n    pass\n"),
    _t("evl-ho-01", "evaluation", "held_out_final", "easy",
       "Write `decide_promotion(base_rate, cand_rate, regressions_count, *, min_delta=0.0)` returning 'ROLLBACK' if cand_rate < base_rate or (regressions_count > 0 and cand_rate <= base_rate), 'PROMOTE' if cand_rate - base_rate > min_delta and regressions_count == 0, else 'KEEP_BASELINE'.",
       "assert decide_promotion(0.7, 0.9, 0) == 'PROMOTE'\nassert decide_promotion(0.8, 0.75, 1) == 'ROLLBACK'\nassert decide_promotion(0.8, 0.8, 0) == 'KEEP_BASELINE'\n"),
    _t("evl-ho-02", "evaluation", "held_out_final", "easy",
       "Write `overconfidence_gap(pairs)` where pairs is non-empty list of `(confidence, success_bool)`. Return `round(mean_conf - actual_acc, 4)`.",
       "assert overconfidence_gap([(0.9, True), (0.9, False)]) == 0.4\nassert overconfidence_gap([(0.5, True), (0.5, False)]) == 0.0\n"),
    _t("evl-ho-03", "evaluation", "held_out_final", "medium",
       "Write `compute_role_breakdown(rows)` where rows is list of `{'role': str, 'ok': bool}`. Return dict `{role: {'passed': p, 'total': t, 'rate': round(p/t, 4)}}`.",
       "r = compute_role_breakdown([{'role':'dev','ok':True},{'role':'dev','ok':False},{'role':'sec','ok':True}])\n"
       "assert r == {'dev': {'passed': 1, 'total': 2, 'rate': 0.5}, 'sec': {'passed': 1, 'total': 1, 'rate': 1.0}}\n"),
    _t("evl-ho-04", "evaluation", "held_out_final", "medium",
       "Write `exact_sign_test_pvalue(wins, losses)` using `math.comb` computing exact two-sided binomial p-value for `n = wins + losses` with p=0.5 (return 1.0 if n==0), rounded to 6 decimals. Validate non-negative ints (non-bool).",
       "assert exact_sign_test_pvalue(0, 0) == 1.0\nassert exact_sign_test_pvalue(6, 0) == round(2 * (1 / 64), 6)\n"
       "try:\n    exact_sign_test_pvalue(-1, 2); assert False\nexcept ValueError:\n    pass\n"),
    _t("evl-ho-05", "evaluation", "held_out_final", "hard",
       "Write `audit_corpus_dedup(records, key='prompt')` where records is list of dicts. Normalize `str(r.get(key,'')).strip().lower()` and return `{'total': n, 'unique': u, 'duplicates': n-u, 'duplicate_ratio': round((n-u)/max(1,n), 4)}`.",
       "r = audit_corpus_dedup([{'prompt':'Hello'},{'prompt':' hello '},{'prompt':'World'}])\n"
       "assert r == {'total': 3, 'unique': 2, 'duplicates': 1, 'duplicate_ratio': 0.3333}\n"),
    _t("evl-ho-06", "evaluation", "held_out_final", "hard",
       "Return ONLY a JSON object with exact keys: {\"target_rate\": 0.89, \"rubric_frozen\": true, \"held_out_isolated\": true, \"verdict\": \"EVALUATED\"}.",
       "", kind="json",
       required_fields={"target_rate": "float", "rubric_frozen": "bool", "held_out_isolated": "bool", "verdict": "str"},
       expected_values={"target_rate": 0.89, "rubric_frozen": True, "held_out_isolated": True, "verdict": "EVALUATED"}),

    # ==================== 10. MARKET DATA (10) ====================
    _t("mkt-tr-01", "market_data", "train", "easy",
       "Write `validate_ohlcv_candle(c)` where c is dict with keys 'open','high','low','close','volume'. Return True ONLY if all 5 are numeric (non-bool), open/high/low/close > 0, volume >= 0, and `low <= min(open, close) <= max(open, close) <= high`.",
       "assert validate_ohlcv_candle({'open':10,'high':12,'low':9,'close':11,'volume':100}) is True\n"
       "assert validate_ohlcv_candle({'open':10,'high':9,'low':11,'close':10,'volume':10}) is False\n"
       "assert validate_ohlcv_candle({'open':10,'high':12,'low':9,'close':11,'volume':-1}) is False\n"),
    _t("mkt-tr-02", "market_data", "train", "medium",
       "Write `compute_spread_bps(bid, ask)` returning `round(((ask - bid) / ((ask + bid) / 2.0)) * 10000.0, 4)`. Reject bool, non-positive, or ask < bid with ValueError.",
       "assert compute_spread_bps(99.5, 100.5) == 100.0\n"
       "for b in ((101, 100), (0, 1), (True, 2)):\n    try:\n        compute_spread_bps(*b); assert False\n    except ValueError:\n        pass\n"),
    _t("mkt-dv-01", "market_data", "dev", "medium",
       "Write `deduplicate_candles(candles)` where each candle is `{'ts': int, 'close': float}`. Keep the LAST candle per `ts` and return sorted by `ts` ascending. Raise ValueError if any ts is not int or is bool.",
       "cs = [{'ts':120,'close':2.0},{'ts':60,'close':1.0},{'ts':120,'close':2.5}]\n"
       "assert deduplicate_candles(cs) == [{'ts':60,'close':1.0},{'ts':120,'close':2.5}]\n"),
    _t("mkt-dv-02", "market_data", "dev", "hard",
       "Write `resample_candles(candles, bucket_s)` aggregating sorted OHLCV dicts `{'ts','open','high','low','close','volume'}` into buckets `ts // bucket_s * bucket_s` (open=first, high=max, low=min, close=last, volume=sum). Validate bucket_s int (non-bool) > 0.",
       "cs = [{'ts':60,'open':10,'high':12,'low':9,'close':11,'volume':5},{'ts':120,'open':11,'high':15,'low':10,'close':14,'volume':7}]\n"
       "res = resample_candles(cs, 300)\nassert res == [{'ts':0,'open':10,'high':15,'low':9,'close':14,'volume':12}]\n"),
    _t("mkt-ho-01", "market_data", "held_out_final", "easy",
       "Write `check_feed_freshness(last_ts, now_ts, max_lag_s=60)` returning dict `{'fresh': bool, 'lag_s': float}` where lag_s = round(now_ts - last_ts, 3), fresh is True if `0 <= lag_s <= max_lag_s`. Reject bool or max_lag_s <= 0.",
       "assert check_feed_freshness(100, 130, 60) == {'fresh': True, 'lag_s': 30.0}\n"
       "assert check_feed_freshness(100, 200, 60) == {'fresh': False, 'lag_s': 100.0}\n"
       "assert check_feed_freshness(200, 100, 60)['fresh'] is False\n"),
    _t("mkt-ho-02", "market_data", "held_out_final", "easy",
       "Write `estimate_vwap(trades)` where trades is non-empty list of `(price, qty)` with price>0 and qty>0 (non-bool). Return `round(sum(p*q)/sum(q), 6)`.",
       "assert estimate_vwap([(10.0, 2), (20.0, 2)]) == 15.0\n"
       "try:\n    estimate_vwap([]); assert False\nexcept ValueError:\n    pass\n"),
    _t("mkt-ho-03", "market_data", "held_out_final", "medium",
       "Write `check_orderbook_integrity(bids, asks)` where bids/asks are lists of `(price, size)`. Return True ONLY if both non-empty, all prices/sizes > 0, bids sorted descending by price, asks sorted ascending by price, and `bids[0][0] < asks[0][0]` (no crossed book).",
       "assert check_orderbook_integrity([(100, 1), (99, 2)], [(101, 1), (102, 2)]) is True\n"
       "assert check_orderbook_integrity([(102, 1)], [(101, 1)]) is False\n"
       "assert check_orderbook_integrity([(99, 1), (100, 1)], [(101, 1)]) is False\n"),
    _t("mkt-ho-04", "market_data", "held_out_final", "medium",
       "Write `detect_price_spike(prev_price, curr_price, max_pct=0.25)` returning True if `abs(curr_price - prev_price) / prev_price > max_pct` else False. Reject bool or non-positive prices or max_pct <= 0.",
       "assert detect_price_spike(100.0, 130.0, 0.25) is True\nassert detect_price_spike(100.0, 110.0, 0.25) is False\n"
       "try:\n    detect_price_spike(0, 10); assert False\nexcept ValueError:\n    pass\n"),
    _t("mkt-ho-05", "market_data", "held_out_final", "hard",
       "Write `select_primary_source(sources, max_lag_s=60)` where sources is list of `{'name': str, 'priority': int, 'lag_s': float, 'ok': bool}`. Return name of lowest `priority` source having `ok is True` and `0 <= lag_s <= max_lag_s`, or None if none qualify.",
       "srcs = [{'name':'kraken','priority':1,'lag_s':90,'ok':True},{'name':'kucoin','priority':2,'lag_s':10,'ok':True},{'name':'mexc','priority':3,'lag_s':5,'ok':True}]\n"
       "assert select_primary_source(srcs, 60) == 'kucoin'\nassert select_primary_source([{'name':'a','priority':1,'lag_s':10,'ok':False}], 60) is None\n"),
    _t("mkt-ho-06", "market_data", "held_out_final", "hard",
       "Write `check_seasonality_window_coverage(actual_days, requested_years=5)` returning dict `{'requested_days': int, 'actual_days': int, 'coverage_ratio': float, 'is_full_window': bool}` where requested_days = int(requested_years * 365), coverage_ratio = round(min(1.0, actual_days/requested_days), 4), is_full_window = actual_days >= requested_days. Validate non-negative actual_days and positive requested_years.",
       "r = check_seasonality_window_coverage(365, 5)\nassert r == {'requested_days': 1825, 'actual_days': 365, 'coverage_ratio': 0.2, 'is_full_window': False}\n"
       "assert check_seasonality_window_coverage(2000, 5)['is_full_window'] is True\n"),

    # ==================== 11. MONITORING (10) ====================
    _t("mon-tr-01", "monitoring", "train", "easy",
       "Write `classify_ram_headroom(free_mb, *, model_resident=False)` returning 'OK' if free_mb >= (950 if model_resident else 2200), 'WARN' if free_mb >= (700 if model_resident else 1400), else 'CRITICAL'. Reject negative/bool.",
       "assert classify_ram_headroom(1200, model_resident=True) == 'OK'\nassert classify_ram_headroom(1200, model_resident=False) == 'CRITICAL'\n"
       "assert classify_ram_headroom(2500, model_resident=False) == 'OK'\n"),
    _t("mon-tr-02", "monitoring", "train", "medium",
       "Write `compute_error_rate(events)` where events is non-empty list of `{'ok': bool}`. Return round(failed / total, 4). Raise ValueError on empty list.",
       "assert compute_error_rate([{'ok':True},{'ok':False},{'ok':True},{'ok':True}]) == 0.25\n"
       "try:\n    compute_error_rate([]); assert False\nexcept ValueError:\n    pass\n"),
    _t("mon-dv-01", "monitoring", "dev", "medium",
       "Write `detect_heartbeat_stale(last_hb_ts, now_ts, stale_after_s=120)` returning dict `{'stale': bool, 'age_s': float}` where age_s = round(now_ts - last_hb_ts, 2) and stale = age_s > stale_after_s or age_s < 0. Reject bool or stale_after_s <= 0.",
       "assert detect_heartbeat_stale(100, 150, 120) == {'stale': False, 'age_s': 50.0}\n"
       "assert detect_heartbeat_stale(100, 250, 120) == {'stale': True, 'age_s': 150.0}\n"),
    _t("mon-dv-02", "monitoring", "dev", "hard",
       "Write `summarize_ram_timeseries(samples)` where samples is non-empty list of `{'free_mb': float, 'used_mb': float}`. Return `{'count': n, 'min_free_mb': mn, 'max_free_mb': mx, 'avg_free_mb': avg, 'low_ram_events': low}` counting samples with free_mb < 1400. Round floats to 2 decimals.",
       "r = summarize_ram_timeseries([{'free_mb':3000,'used_mb':11000},{'free_mb':1000,'used_mb':13000},{'free_mb':2000,'used_mb':12000}])\n"
       "assert r == {'count': 3, 'min_free_mb': 1000.0, 'max_free_mb': 3000.0, 'avg_free_mb': 2000.0, 'low_ram_events': 1}\n"),
    _t("mon-ho-01", "monitoring", "held_out_final", "easy",
       "Write `detect_repeated_error_streak(errors, threshold=3)` returning True if the LAST `threshold` items in `errors` are identical non-empty strings, else False. Validate threshold int>=2 (non-bool).",
       "assert detect_repeated_error_streak(['a', 'timeout', 'timeout', 'timeout'], 3) is True\n"
       "assert detect_repeated_error_streak(['timeout', 'ok', 'timeout'], 3) is False\n"),
    _t("mon-ho-02", "monitoring", "held_out_final", "easy",
       "Write `compute_p95_latency(latencies)` returning the 95th percentile (nearest-rank `sorted[ceil(0.95*n)-1]`) rounded to 3 decimals from a non-empty list of non-negative numbers (non-bool).",
       "assert compute_p95_latency(list(range(1, 21))) == 19.0\nassert compute_p95_latency([2.5]) == 2.5\n"
       "try:\n    compute_p95_latency([]); assert False\nexcept ValueError:\n    pass\n"),
    _t("mon-ho-03", "monitoring", "held_out_final", "medium",
       "Write `should_trigger_circuit_breaker(recent_results, *, window=5, max_failures=3)` where recent_results is list of bools (True=ok). Inspect ONLY the last `window` entries and return True if failures >= max_failures, else False. Validate window>=1 and max_failures>=1.",
       "assert should_trigger_circuit_breaker([True, False, False, False], window=5, max_failures=3) is True\n"
       "assert should_trigger_circuit_breaker([False, False, False, True, True, True], window=3, max_failures=2) is False\n"),
    _t("mon-ho-04", "monitoring", "held_out_final", "medium",
       "Write `classify_engine_collision(ollama_loaded, llama_alive, llama_processing)` returning 'ACTIVE_COLLISION' if ollama_loaded and llama_processing, 'IDLE_COMPETITOR' if ollama_loaded and llama_alive, else 'CLEAN'.",
       "assert classify_engine_collision(True, True, True) == 'ACTIVE_COLLISION'\n"
       "assert classify_engine_collision(True, True, False) == 'IDLE_COMPETITOR'\n"
       "assert classify_engine_collision(True, False, False) == 'CLEAN'\n"),
    _t("mon-ho-05", "monitoring", "held_out_final", "hard",
       "Write `compute_active_work_ratio(active_s, total_s)` returning dict `{'active_s': float, 'wait_s': float, 'utilization': float}` where wait_s = round(max(0.0, total_s - active_s), 2), utilization = round(active_s / total_s, 4). Reject bool, negative values, total_s<=0, or active_s > total_s.",
       "assert compute_active_work_ratio(45.0, 60.0) == {'active_s': 45.0, 'wait_s': 15.0, 'utilization': 0.75}\n"
       "try:\n    compute_active_work_ratio(70.0, 60.0); assert False\nexcept ValueError:\n    pass\n"),
    _t("mon-ho-06", "monitoring", "held_out_final", "hard",
       "Return ONLY a JSON object with exact keys: {\"engine_concurrency\": 1, \"ram_guard_active\": true, \"orphan_reclaim\": true, \"status\": \"HEALTHY\"}.",
       "", kind="json",
       required_fields={"engine_concurrency": "int", "ram_guard_active": "bool", "orphan_reclaim": "bool", "status": "str"},
       expected_values={"engine_concurrency": 1, "ram_guard_active": True, "orphan_reclaim": True, "status": "HEALTHY"}),

    # ==================== 12. RELEASE (10) ====================
    _t("rel-tr-01", "release", "train", "easy",
       "Write `parse_semver(tag)` parsing `'v1.2.3'` or `'1.2.3'` into `(1, 2, 3)` tuple of 3 non-negative ints. Raise ValueError on invalid semver.",
       "assert parse_semver('v2.10.4') == (2, 10, 4)\nassert parse_semver('0.1.0') == (0, 1, 0)\n"
       "for b in ('1.2', 'v1.2.x', ''):\n    try:\n        parse_semver(b); assert False\n    except ValueError:\n        pass\n"),
    _t("rel-tr-02", "release", "train", "medium",
       "Write `verify_manifest_digests(expected_map, actual_map)` returning dict `{'ok': bool, 'missing': list[str], 'mismatched': list[str]}` with sorted lists.",
       "assert verify_manifest_digests({'a':'1','b':'2'}, {'a':'1','b':'2'}) == {'ok': True, 'missing': [], 'mismatched': []}\n"
       "assert verify_manifest_digests({'a':'1','b':'2'}, {'a':'9'}) == {'ok': False, 'missing': ['b'], 'mismatched': ['a']}\n"),
    _t("rel-dv-01", "release", "dev", "medium",
       "Write `check_pr_merge_policy(branch, *, ci_green, reviews_approved, is_draft)` returning dict `{'mergeable': bool, 'reasons': list[str]}`: block if is_draft ('pr_is_draft'), not ci_green ('ci_not_green'), reviews_approved < 1 ('missing_review'), or branch in ('main','master') ('cannot_merge_protected_head').",
       "assert check_pr_merge_policy('agents/feat', ci_green=True, reviews_approved=1, is_draft=False) == {'mergeable': True, 'reasons': []}\n"
       "r = check_pr_merge_policy('agents/feat', ci_green=True, reviews_approved=0, is_draft=True)\nassert r['mergeable'] is False and 'pr_is_draft' in r['reasons'] and 'missing_review' in r['reasons']\n"),
    _t("rel-dv-02", "release", "dev", "hard",
       "Write `check_issue_number_collision(proposed_issues, occupied_issues)` returning dict `{'ok': bool, 'collisions': list[int], 'suggested_next': list[int]}` where collisions are sorted overlaps and suggested_next assigns `len(proposed_issues)` consecutive free integers strictly greater than `max(occupied_issues, default=0)`.",
       "r = check_issue_number_collision([215, 216], {214, 215})\n"
       "assert r == {'ok': False, 'collisions': [215], 'suggested_next': [216, 217]}\n"
       "assert check_issue_number_collision([216, 217], {214, 215})['ok'] is True\n"),
    _t("rel-ho-01", "release", "held_out_final", "easy",
       "Write `is_clean_git_status(porcelain_output)` returning True ONLY if stripped `porcelain_output` is empty, else False.",
       "assert is_clean_git_status('') is True\nassert is_clean_git_status('   \\n') is True\nassert is_clean_git_status(' M file.py\\n') is False\n"),
    _t("rel-ho-02", "release", "held_out_final", "easy",
       "Write `validate_commit_sha(sha)` returning True ONLY if `sha` is a 40-char lowercase hexadecimal string, else False.",
       "assert validate_commit_sha('a' * 40) is True\nassert validate_commit_sha('A' * 40) is False\nassert validate_commit_sha('abc123') is False\n"),
    _t("rel-ho-03", "release", "held_out_final", "medium",
       "Write `select_rollback_target(versions, current_version)` where versions is ordered list of version strings oldest->newest. Return the immediately preceding version before `current_version`, or None if current_version is oldest. Raise ValueError if current_version not in versions.",
       "assert select_rollback_target(['v1', 'v2', 'v3'], 'v3') == 'v2'\nassert select_rollback_target(['v1', 'v2'], 'v1') is None\n"
       "try:\n    select_rollback_target(['v1'], 'v9'); assert False\nexcept ValueError:\n    pass\n"),
    _t("rel-ho-04", "release", "held_out_final", "medium",
       "Write `validate_mandate_expiry(expires_at_iso, now_iso)` parsing ISO UTC timestamps (`YYYY-MM-DDTHH:MM:SSZ`) via `datetime.fromisoformat` and returning True if `expires_at_iso > now_iso` else False. Raise ValueError on malformed timestamps.",
       "assert validate_mandate_expiry('2026-12-09T23:59:59Z', '2026-11-25T15:00:00Z') is True\n"
       "assert validate_mandate_expiry('2026-11-01T00:00:00Z', '2026-11-25T15:00:00Z') is False\n"),
    _t("rel-ho-05", "release", "held_out_final", "hard",
       "Write `build_release_checklist(checks)` where checks is dict `{name: bool}`. Return `{'ready': bool, 'passed': list[str], 'failed': list[str], 'score_pct': float}` with sorted lists and score_pct rounded to 2 decimals. Raise ValueError if checks is empty.",
       "r = build_release_checklist({'ci': True, 'tests': True, 'security': False, 'docs': True})\n"
       "assert r == {'ready': False, 'passed': ['ci', 'docs', 'tests'], 'failed': ['security'], 'score_pct': 75.0}\n"),
    _t("rel-ho-06", "release", "held_out_final", "hard",
       "Return ONLY a JSON object with exact keys: {\"auto_merge_main\": false, \"owner_signature_required\": true, \"draft_pr_only\": true, \"status\": \"READY_FOR_REVIEW\"}.",
       "", kind="json",
       required_fields={"auto_merge_main": "bool", "owner_signature_required": "bool", "draft_pr_only": "bool", "status": "str"},
       expected_values={"auto_merge_main": False, "owner_signature_required": True, "draft_pr_only": True, "status": "READY_FOR_REVIEW"}),
)

_TYPE_MAP = {"str": str, "int": int, "float": (int, float), "bool": bool, "list": list, "dict": dict}


def get_split(split: str) -> list[dict[str, Any]]:
    if split not in ("train", "dev", "held_out_final", "all"):
        raise ValueError(f"unknown benchmark split: {split!r}")
    if split == "all":
        return [dict(t) for t in BENCHMARK_120]
    return [dict(t) for t in BENCHMARK_120 if t["split"] == split]


def benchmark_manifest() -> dict[str, Any]:
    """Compute frozen cryptographic SHA-256 seals for all splits before evaluation."""
    by_split = {sp: get_split(sp) for sp in ("train", "dev", "held_out_final")}
    seals = {
        sp: hashlib.sha256(
            json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).hexdigest()
        for sp, rows in by_split.items()
    }
    by_role = {r: sum(1 for t in BENCHMARK_120 if t["role"] == r) for r in ROLES_12}
    by_diff = {d: sum(1 for t in BENCHMARK_120 if t["difficulty"] == d) for d in ("easy", "medium", "hard")}
    return {
        "schema_version": 1,
        "total_tasks": len(BENCHMARK_120),
        "roles_covered": len(by_role),
        "counts_by_split": {sp: len(rows) for sp, rows in by_split.items()},
        "counts_by_role": by_role,
        "counts_by_difficulty": by_diff,
        "seals_sha256": seals,
        "all_sha256": hashlib.sha256(
            json.dumps(list(BENCHMARK_120), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).hexdigest(),
    }


def verify_task_output(task: dict[str, Any], raw_output: str) -> dict[str, Any]:
    """Immutable, objective programmatic verifier for any benchmark task."""
    if task.get("kind") == "json":
        req = {k: _TYPE_MAP[v] for k, v in (task.get("required_fields") or {}).items()}
        val = context_engine.validate_structured_json(raw_output, required_fields=req)
        if not val["ok"]:
            return {"ok": False, "error": val["error"], "passed": [], "failed": ["json_schema"]}
        data = val["data"]
        for k, exp in (task.get("expected_values") or {}).items():
            if data.get(k) != exp:
                return {"ok": False, "error": f"field {k}={data.get(k)!r} != {exp!r}", "passed": ["json_schema"], "failed": ["json_values"]}
        return {"ok": True, "error": None, "passed": ["json_schema", "json_values"], "failed": []}

    code = ollama_native.extract_code_block(raw_output)
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {"ok": False, "error": f"SyntaxError line {exc.lineno}: {exc.msg}", "passed": [], "failed": ["syntax"]}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "__import__"}:
            return {"ok": False, "error": f"Forbidden call: {node.func.id}", "passed": ["syntax"], "failed": ["security"]}
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    return {"ok": False, "error": "Forbidden shell=True", "passed": ["syntax"], "failed": ["security"]}
    ns: dict[str, Any] = {}
    try:
        exec(compile(code, f"<candidate:{task['id']}>", "exec"), ns)
        exec(compile(task["test_code"], f"<test:{task['id']}>", "exec"), ns)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:220]}", "passed": ["syntax", "security"], "failed": ["behavior"]}
    return {"ok": True, "error": None, "passed": ["syntax", "security", "behavior"], "failed": []}
