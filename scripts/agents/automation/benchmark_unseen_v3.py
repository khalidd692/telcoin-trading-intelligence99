"""Brand-New Frozen Independent Validation Benchmark V3 (60 Unseen Missions, 5/Role x 12 Roles).

Methodological Guarantees:
- 100% disjoint from `benchmark_suite_100` (120 tasks) and `agent_academy` (15 exercises).
- Frozen cryptographically via SHA-256 seal BEFORE any model evaluation.
- NEVER consulted during Skill authoring, prompt tuning, or mentor distillation.
- Supports identical-conditions Before vs After evaluation:
  (A) 100% Local Baseline (0 cloud)
  (B) 100% Local Post-Transfer (0 cloud, 12 specialized Skills + RAG + deterministic tools + Smart Repair)
  (C) Hybrid Post-Transfer (Local + 3 free Groq mentors, $0.00)
- Includes mandatory critical security checks (100% pass gate).
"""
from __future__ import annotations

import ast
import hashlib
import json
from typing import Any

from scripts.agents.automation import context_engine, local_deterministic_tools, ollama_native

ROLES_12: tuple[str, ...] = (
    "development", "quant", "quality", "coordination",
    "cloud", "security", "mobile", "documentation",
    "evaluation", "market_data", "monitoring", "release",
)


def _u(
    tid: str,
    role: str,
    difficulty: str,
    objective: str,
    test_code: str,
    *,
    kind: str = "python",
    critical_security: bool = False,
    required_fields: dict[str, str] | None = None,
    expected_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": tid,
        "role": role,
        "difficulty": difficulty,
        "kind": kind,
        "critical_security": critical_security,
        "objective": objective,
        "test_code": test_code,
        "required_fields": required_fields or {},
        "expected_values": expected_values or {},
    }


UNSEEN_V3_60: tuple[dict[str, Any], ...] = (
    # ==================== 1. DEVELOPMENT (5) ====================
    _u("v3-dev-01", "development", "easy",
       "Write `normalize_slug(text)` converting text to lowercase ASCII-safe slug: keep `[a-z0-9]`, replace runs of other chars with single `'-'`, strip leading/trailing `'-'`. Raise ValueError if text is not str or resulting slug is empty.",
       "assert normalize_slug('  Hello, World!! 2026 ') == 'hello-world-2026'\n"
       "assert normalize_slug('TEL99__Agent') == 'tel99-agent'\n"
       "for b in ('', '   ', '!!!', 123):\n    try:\n        normalize_slug(b); assert False\n    except ValueError:\n        pass\n"),
    _u("v3-dev-02", "development", "easy",
       "Write `paginate_items(items, page, page_size)` (1-indexed page) returning dict `{'items': list, 'page': int, 'total_pages': int, 'total_items': int}`. Reject bool or int < 1 for page/page_size with ValueError. For empty items, total_pages=0 and items=[].",
       "assert paginate_items([1,2,3,4,5], 2, 2) == {'items': [3,4], 'page': 2, 'total_pages': 3, 'total_items': 5}\n"
       "assert paginate_items([], 1, 10) == {'items': [], 'page': 1, 'total_pages': 0, 'total_items': 0}\n"
       "for b in ((0, 2), (1, 0), (True, 2)):\n    try:\n        paginate_items([1], *b); assert False\n    except ValueError:\n        pass\n"),
    _u("v3-dev-03", "development", "medium",
       "Write `merge_defaults(user_cfg, defaults)` recursively merging two dicts WITHOUT mutating either input: user_cfg values override defaults, nested dicts merge recursively, non-dict values replace directly. Raise ValueError if either arg is not dict.",
       "d = {'a': 1, 'db': {'host': '127.0.0.1', 'port': 5432}}\nu = {'db': {'port': 9999}, 'b': 2}\n"
       "res = merge_defaults(u, d)\nassert res == {'a': 1, 'b': 2, 'db': {'host': '127.0.0.1', 'port': 9999}}\n"
       "assert d['db']['port'] == 5432 and 'a' not in u\n"),
    _u("v3-dev-04", "development", "medium",
       "Write class `BoundedRingBuffer(capacity)` with `append(item)` (drops oldest when full), `to_list()` (oldest->newest copy), and `len(buf)`. Raise ValueError if capacity is bool or not int >= 1.",
       "rb = BoundedRingBuffer(3)\nfor x in (1, 2, 3, 4): rb.append(x)\n"
       "assert rb.to_list() == [2, 3, 4] and len(rb) == 3\n"
       "for b in (0, -1, True):\n    try:\n        BoundedRingBuffer(b); assert False\n    except ValueError:\n        pass\n"),
    _u("v3-dev-05", "development", "hard",
       "Write `compute_retry_backoff(attempt, *, base_s=1.0, factor=2.0, max_s=60.0)` returning `round(min(max_s, base_s * (factor ** (attempt - 1))), 4)`. Reject bool or attempt < 1 or non-positive base_s/max_s or factor < 1.0 with ValueError.",
       "assert compute_retry_backoff(1) == 1.0\nassert compute_retry_backoff(4, base_s=1.5, factor=2.0, max_s=10.0) == 10.0\n"
       "assert compute_retry_backoff(3, base_s=1.5, factor=2.0, max_s=10.0) == 6.0\n"
       "for b in (0, True):\n    try:\n        compute_retry_backoff(b); assert False\n    except ValueError:\n        pass\n"),

    # ==================== 2. QUANT (5) ====================
    _u("v3-quant-01", "quant", "easy",
       "Write `causal_cumulative_max(values)` returning a list of floats where index i is max(values[0..i]) (strictly causal). Reject empty list or bool/non-numeric elements with ValueError.",
       "assert causal_cumulative_max([10, 8, 12, 11, 15]) == [10.0, 10.0, 12.0, 12.0, 15.0]\n"
       "for b in ([], [1, True]):\n    try:\n        causal_cumulative_max(b); assert False\n    except ValueError:\n        pass\n"),
    _u("v3-quant-02", "quant", "easy",
       "Write `compute_net_rr(entry, stop, target, *, fee_pct=0.001, spread_pct=0.0005)` for a long position: effective_entry = entry * (1 + fee_pct + spread_pct), risk = effective_entry - stop, reward = target * (1 - fee_pct) - effective_entry. Return `round(reward / risk, 4)`. Raise ValueError if any input is bool or <= 0 or risk <= 0 or target <= entry.",
       "rr = compute_net_rr(100.0, 95.0, 115.0, fee_pct=0.001, spread_pct=0.0005)\n"
       "assert rr == round((115.0*0.999 - 100.15) / (100.15 - 95.0), 4)\n"
       "try:\n    compute_net_rr(100.0, 101.0, 115.0); assert False\nexcept ValueError:\n    pass\n"),
    _u("v3-quant-03", "quant", "medium",
       "Write `causal_weighted_ma(values, window)` returning list of floats rounded to 6 decimals where index i is the linearly weighted average of `s = values[max(0, i-window+1):i+1]` with weights `1, 2, ..., len(s)` (newest gets highest weight). Validate window int >= 1 (no bool) and non-empty numeric list (no bool).",
       "assert causal_weighted_ma([10.0, 20.0, 30.0], 2) == [10.0, round((10+40)/3, 6), round((20+60)/3, 6)]\n"
       "assert causal_weighted_ma([10.0, 20.0, 30.0], 3) == [10.0, round(50/3, 6), round((10+40+90)/6, 6)]\n"
       "for b in (0, True):\n    try:\n        causal_weighted_ma([1.0], b); assert False\n    except ValueError:\n        pass\n"),
    _u("v3-quant-04", "quant", "medium",
       "Write `compute_max_drawdown_pct(equity_curve)` returning max peak-to-trough percentage drop rounded to 4 decimals (0.0 if monotonically non-decreasing). Validate non-empty positive numbers (no bool).",
       "assert compute_max_drawdown_pct([100, 120, 90, 110]) == 25.0\nassert compute_max_drawdown_pct([100, 105, 110]) == 0.0\n"
       "try:\n    compute_max_drawdown_pct([100, 0]); assert False\nexcept ValueError:\n    pass\n"),
    _u("v3-quant-05", "quant", "hard",
       "Write `causal_rolling_std(values, window)` returning list of population standard deviations rounded to 6 decimals where index i uses ONLY `values[max(0, i-window+1):i+1]`. Validate window int >= 1 (no bool) and non-empty numeric list (no bool).",
       "assert causal_rolling_std([10, 20, 20], 2) == [0.0, 5.0, 0.0]\n"
       "assert causal_rolling_std([2, 4, 6], 3) == [0.0, 1.0, round(((8/3)**0.5), 6)]\n"
       "try:\n    causal_rolling_std([1, 2], True); assert False\nexcept ValueError:\n    pass\n"),

    # ==================== 3. QUALITY (5) ====================
    _u("v3-qual-01", "quality", "easy",
       "Write `list_defined_functions(source_code)` using `ast.parse` returning sorted list of top-level function names (Def and AsyncFunctionDef). Raise ValueError on SyntaxError.",
       "assert list_defined_functions('def b(): pass\\ndef a(): pass\\nclass C:\\n  def m(self): pass\\n') == ['a', 'b']\n"
       "try:\n    list_defined_functions('def broken('); assert False\nexcept ValueError:\n    pass\n"),
    _u("v3-qual-02", "quality", "easy",
       "Write `compute_pass_metrics(outcomes)` where outcomes is non-empty list of dicts `{'ok': bool, 'attempts': int}`. Return `{'total': n, 'passed': p, 'first_pass': fp, 'rate': round(p/n, 4)}`. Raise ValueError if empty or non-bool ok.",
       "r = compute_pass_metrics([{'ok': True, 'attempts': 1}, {'ok': True, 'attempts': 2}, {'ok': False, 'attempts': 3}])\n"
       "assert r == {'total': 3, 'passed': 2, 'first_pass': 1, 'rate': 0.6667}\n"
       "try:\n    compute_pass_metrics([]); assert False\nexcept ValueError:\n    pass\n"),
    _u("v3-qual-03", "quality", "medium",
       "Write `detect_unmodified_duplicate_hashes(hashes)` returning True if the last 2 items in `hashes` are identical non-empty strings, else False. Raise ValueError if hashes is not a list.",
       "assert detect_unmodified_duplicate_hashes(['a', 'b', 'b']) is True\n"
       "assert detect_unmodified_duplicate_hashes(['a', 'b', 'c']) is False\n"
       "assert detect_unmodified_duplicate_hashes(['', '']) is False\n"),
    _u("v3-qual-04", "quality", "medium",
       "Write `verify_regression_gate(before_map, after_map)` where both map task_id->bool. Return dict `{'promote': bool, 'regressions': sorted_list, 'improvements': sorted_list, 'delta': int}` where promote is True ONLY if regressions is empty AND delta > 0.",
       "r = verify_regression_gate({'a': True, 'b': False}, {'a': True, 'b': True})\n"
       "assert r == {'promote': True, 'regressions': [], 'improvements': ['b'], 'delta': 1}\n"
       "r2 = verify_regression_gate({'a': True, 'b': False}, {'a': False, 'b': True})\n"
       "assert r2 == {'promote': False, 'regressions': ['a'], 'improvements': ['b'], 'delta': 0}\n"),
    _u("v3-qual-05", "quality", "hard",
       "Write `count_ast_security_violations(source_code)` using `ast.parse` returning dict `{'safe': bool, 'violations': list[str]}` flagging calls to `eval`, `exec`, `compile`, `__import__`, keyword `shell=True`, or string literal `'0.0.0.0'`.",
       "assert count_ast_security_violations('x = 1 + 2') == {'safe': True, 'violations': []}\n"
       "r = count_ast_security_violations(\"import subprocess\\nsubprocess.run('ls', shell=True)\\neval('1')\")\n"
       "assert r['safe'] is False and len(r['violations']) == 2\n",
       critical_security=True),

    # ==================== 4. COORDINATION (5) ====================
    _u("v3-coord-01", "coordination", "easy",
       "Write `filter_expired_leases(leases, now_ts)` where each lease is `{'id': str, 'expires_at': float}`. Return dict `{'active': sorted_ids, 'expired': sorted_ids}` where expired means `expires_at <= now_ts`.",
       "r = filter_expired_leases([{'id':'b','expires_at':100},{'id':'a','expires_at':200}], 100)\n"
       "assert r == {'active': ['a'], 'expired': ['b']}\n"),
    _u("v3-coord-02", "coordination", "easy",
       "Write `detect_dependency_cycle(graph)` where graph maps node->list[str] dependencies. Return True if any directed cycle exists, else False.",
       "assert detect_dependency_cycle({'a': ['b'], 'b': ['c'], 'c': []}) is False\n"
       "assert detect_dependency_cycle({'a': ['b'], 'b': ['a']}) is True\n"
       "assert detect_dependency_cycle({'a': ['a']}) is True\n"),
    _u("v3-coord-03", "coordination", "medium",
       "Write `assign_specialist_owner(task_tags, role_capabilities)` where role_capabilities maps role->list[str]. Return the role with the highest tag overlap count (tie-break alphabetically by role name), or None if overlap is 0.",
       "caps = {'quant': ['math','window'], 'development': ['python','api'], 'security': ['path','secret']}\n"
       "assert assign_specialist_owner(['api', 'python'], caps) == 'development'\n"
       "assert assign_specialist_owner(['unknown'], caps) is None\n"),
    _u("v3-coord-04", "coordination", "medium",
       "Write `acquire_single_slot_lease(active_lease, actor, now_ts, ttl_s=60)` returning dict `{'granted': bool, 'lease': dict}`: grant if active_lease is None or active_lease['expires_at'] <= now_ts or active_lease['actor'] == actor (renew); else return granted=False with existing active_lease. Validate ttl_s > 0 (not bool).",
       "r1 = acquire_single_slot_lease(None, 'ollama', 100.0, 30)\nassert r1['granted'] is True and r1['lease']['expires_at'] == 130.0\n"
       "r2 = acquire_single_slot_lease(r1['lease'], 'llama', 110.0, 30)\nassert r2['granted'] is False and r2['lease']['actor'] == 'ollama'\n"
       "r3 = acquire_single_slot_lease(r1['lease'], 'llama', 135.0, 30)\nassert r3['granted'] is True and r3['lease']['actor'] == 'llama'\n"),
    _u("v3-coord-05", "coordination", "hard",
       "Write `compute_execution_waves(dependencies)` where dependencies maps task_id->list[str] prereqs. Return list of waves `list[list[str]]` where each wave is sorted tasks ready once prior waves completed. Raise ValueError on cycle or unknown dependency.",
       "assert compute_execution_waves({'a': [], 'b': ['a'], 'c': ['a'], 'd': ['b', 'c']}) == [['a'], ['b', 'c'], ['d']]\n"
       "try:\n    compute_execution_waves({'a': ['b'], 'b': ['a']}); assert False\nexcept ValueError:\n    pass\n"),

    # ==================== 5. CLOUD (5) ====================
    _u("v3-cloud-01", "cloud", "easy",
       "Write `is_free_tier_model(model_id, prompt_price, completion_price)` returning True ONLY if prompt_price == 0 and completion_price == 0 (rejecting bool) AND model_id is non-empty str, else False.",
       "assert is_free_tier_model('openai/gpt-oss-120b', 0, 0) is True\n"
       "assert is_free_tier_model('paid/x', 0.001, 0) is False\nassert is_free_tier_model('x', False, 0) is False\n",
       critical_security=True),
    _u("v3-cloud-02", "cloud", "easy",
       "Write `parse_loopback_endpoint(url)` using `urllib.parse.urlparse` returning `(host, port)` if scheme in ('http','https') and host in ('127.0.0.1', 'localhost'), else raise ValueError.",
       "assert parse_loopback_endpoint('http://127.0.0.1:8780/api') == ('127.0.0.1', 8780)\n"
       "for b in ('http://0.0.0.0:8080', 'http://example.com:80', 'ftp://127.0.0.1:21'):\n    try:\n        parse_loopback_endpoint(b); assert False\n    except ValueError:\n        pass\n",
       critical_security=True),
    _u("v3-cloud-03", "cloud", "medium",
       "Write `check_daily_quota(used_reqs, max_reqs, used_tokens, max_tokens)` returning dict `{'allowed': bool, 'reason': str}`: 'ok' if used_reqs < max_reqs and used_tokens < max_tokens, 'req_cap' if used_reqs >= max_reqs, else 'token_cap'. Reject bool or negative used or non-positive max with ValueError.",
       "assert check_daily_quota(10, 100, 500, 10000) == {'allowed': True, 'reason': 'ok'}\n"
       "assert check_daily_quota(100, 100, 500, 10000) == {'allowed': False, 'reason': 'req_cap'}\n"
       "assert check_daily_quota(10, 100, 10000, 10000) == {'allowed': False, 'reason': 'token_cap'}\n"),
    _u("v3-cloud-04", "cloud", "medium",
       "Write `filter_cloud_egress_env(env_dict)` returning a NEW dict (never mutating input) removing any key containing 'KEY', 'SECRET', 'TOKEN', or 'PASSWORD' (case-insensitive).",
       "orig = {'PATH': '/bin', 'GROQ_API_KEY': 'gsk_123', 'my_secret': 'x', 'USER': 'dev'}\n"
       "out = filter_cloud_egress_env(orig)\nassert out == {'PATH': '/bin', 'USER': 'dev'} and 'GROQ_API_KEY' in orig\n",
       critical_security=True),
    _u("v3-cloud-05", "cloud", "hard",
       "Write `select_hybrid_route(difficulty, confidential, local_ok, cloud_ok)` returning dict `{'route': str, 'reason': str}`: if confidential -> ('local','confidential_local_only') if local_ok else ('blocked','no_local_for_confidential'); if difficulty == 'hard' and cloud_ok -> ('free_cloud','hard_task_cloud'); if local_ok -> ('local','local_default'); if cloud_ok -> ('free_cloud','cloud_fallback'); else ('blocked','no_provider').",
       "assert select_hybrid_route('hard', True, True, True) == {'route': 'local', 'reason': 'confidential_local_only'}\n"
       "assert select_hybrid_route('hard', True, False, True) == {'route': 'blocked', 'reason': 'no_local_for_confidential'}\n"
       "assert select_hybrid_route('hard', False, True, True) == {'route': 'free_cloud', 'reason': 'hard_task_cloud'}\n"
       "assert select_hybrid_route('easy', False, True, True) == {'route': 'local', 'reason': 'local_default'}\n",
       critical_security=True),

    # ==================== 6. SECURITY (5) ====================
    _u("v3-sec-01", "security", "easy",
       "Write `contains_secret_pattern(text)` returning True if text matches common API key prefixes (`gsk_`, `sk-`, `ghp_`, `github_pat_`, `AIza`) followed by >= 8 alnum/underscore/dash chars, else False.",
       "assert contains_secret_pattern('token=gsk_1234567890abcd') is True\n"
       "assert contains_secret_pattern('ghp_abcdefghij1234') is True\n"
       "assert contains_secret_pattern('normal text gsk_12') is False\n",
       critical_security=True),
    _u("v3-sec-02", "security", "easy",
       "Write `verify_hmac_sha256(secret, message, expected_hex)` using `hmac.new`, `hashlib.sha256`, and `hmac.compare_digest` returning bool.",
       "import hmac, hashlib\nexp = hmac.new(b'k', b'msg', hashlib.sha256).hexdigest()\n"
       "assert verify_hmac_sha256('k', 'msg', exp) is True\nassert verify_hmac_sha256('k', 'msg', '0'*64) is False\n",
       critical_security=True),
    _u("v3-sec-03", "security", "medium",
       "Write `validate_safe_filename(name)` returning True ONLY if name is a non-empty str matching `^[A-Za-z0-9._-]+$`, does NOT start with `.`, does NOT contain `..`, and length <= 128; else False.",
       "assert validate_safe_filename('report_2026-11-25.json') is True\n"
       "for b in ('', '.env', '../a.txt', 'a/b.txt', 'a..b.txt', 'a b.txt'):\n    assert validate_safe_filename(b) is False\n",
       critical_security=True),
    _u("v3-sec-04", "security", "medium",
       "Write `guard_command_tokens(tokens)` where tokens is list[str]: return dict `{'allowed': bool, 'reason': str}` blocking empty list, any token containing `;`, `|`, `&&`, `||`, `` ` ``, `$(`, or dangerous commands (`rm`, `del`, `format`, `shutdown`, `curl`, `wget`).",
       "assert guard_command_tokens(['python', '-m', 'unittest']) == {'allowed': True, 'reason': 'ok'}\n"
       "assert guard_command_tokens(['rm', '-rf', '/'])['allowed'] is False\n"
       "assert guard_command_tokens(['echo', 'hi;whoami'])['allowed'] is False\n",
       critical_security=True),
    _u("v3-sec-05", "security", "hard",
       "Write `redact_nested_secrets(obj)` recursively returning a NEW object (never mutating input) where any dict key containing 'key', 'secret', 'token', 'password' (case-insensitive) has its value replaced with `'[REDACTED]'`.",
       "src = {'user': 'a', 'nested': {'api_key': 'secret123', 'ok': 1}, 'items': [{'token': 't1'}]}\n"
       "out = redact_nested_secrets(src)\nassert out['nested']['api_key'] == '[REDACTED]' and out['items'][0]['token'] == '[REDACTED]' and out['user'] == 'a'\n"
       "assert src['nested']['api_key'] == 'secret123'\n",
       critical_security=True),

    # ==================== 7. MOBILE (5) ====================
    _u("v3-mob-01", "mobile", "easy",
       "Write `format_ram_gb(mib)` converting MiB to GiB (`mib / 1024.0`) formatted as `f'{gb:.2f} Go'`. Reject bool or negative mib with ValueError.",
       "assert format_ram_gb(2048) == '2.00 Go'\nassert format_ram_gb(1536) == '1.50 Go'\n"
       "for b in (-1, True):\n    try:\n        format_ram_gb(b); assert False\n    except ValueError:\n        pass\n"),
    _u("v3-mob-02", "mobile", "easy",
       "Write `check_css_braces(css_text)` ignoring `/* ... */` comments and returning dict `{'balanced': bool, 'open': int, 'close': int}`.",
       "assert check_css_braces(':root { --a: 1; } /* { */ body { color: red; }') == {'balanced': True, 'open': 2, 'close': 2}\n"
       "assert check_css_braces('.a { color: red;')['balanced'] is False\n"),
    _u("v3-mob-03", "mobile", "medium",
       "Write `audit_aria_labels(buttons)` where each item is dict `{'id': str, 'text': str, 'aria_label': str}`. Return dict `{'ok': bool, 'missing_label': sorted_ids}` flagging any button where BOTH stripped `text` AND stripped `aria_label` are empty.",
       "assert audit_aria_labels([{'id':'b1','text':'Go','aria_label':''},{'id':'b2','text':' ','aria_label':''}]) == {'ok': False, 'missing_label': ['b2']}\n"
       "assert audit_aria_labels([{'id':'b1','text':'','aria_label':'Close'}]) == {'ok': True, 'missing_label': []}\n"),
    _u("v3-mob-04", "mobile", "medium",
       "Write `audit_touch_targets(elements)` where each element is `{'id': str, 'width_px': int, 'height_px': int}`. Return dict `{'ok': bool, 'too_small': sorted_ids}` flagging any element with width_px < 44 or height_px < 44.",
       "r = audit_touch_targets([{'id':'btn1','width_px':48,'height_px':48},{'id':'lnk','width_px':30,'height_px':44}])\n"
       "assert r == {'ok': False, 'too_small': ['lnk']}\n"),
    _u("v3-mob-05", "mobile", "hard",
       "Write `validate_csp_safe_html(html_text)` returning dict `{'safe': bool, 'issues': list[str]}` flagging inline `<script>` (script tag without `src=` attribute), inline event handlers (`onclick=`, `onerror=`, `onload=`), and `javascript:` URI (all case-insensitive).",
       "assert validate_csp_safe_html('<script src=\"/app.js\" defer></script><button id=\"b\">Go</button>') == {'safe': True, 'issues': []}\n"
       "r = validate_csp_safe_html('<script>x()</script><img onerror=\"y()\" src=\"javascript:z\">')\n"
       "assert r['safe'] is False and len(r['issues']) >= 3\n",
       critical_security=True),

    # ==================== 8. DOCUMENTATION (5) ====================
    _u("v3-doc-01", "documentation", "easy",
       "Write `render_md_table(headers, rows)` rendering a GitHub Markdown table escaping any `|` inside cell strings as `\\|`. Raise ValueError if headers is empty.",
       "t = render_md_table(['A', 'B'], [['x|y', '2']])\n"
       "assert t.splitlines() == ['| A | B |', '| --- | --- |', '| x\\\\|y | 2 |']\n"),
    _u("v3-doc-02", "documentation", "easy",
       "Write `extract_h2_headings(markdown_text)` returning list of heading texts from lines starting with `'## '` (preserving order, stripped).",
       "assert extract_h2_headings('# T\\n## Intro \\nBody\\n### Sub\\n## Results') == ['Intro', 'Results']\n"),
    _u("v3-doc-03", "documentation", "medium",
       "Write `verify_status_badges(rows)` where rows is list of `{'item': str, 'status': str}`. Allowed statuses are `{'PROVEN', 'PARTIAL', 'BLOCKED', 'INCONCLUSIVE'}`. Return dict `{'valid': bool, 'invalid_items': sorted_list}`.",
       "assert verify_status_badges([{'item':'x','status':'PROVEN'},{'item':'y','status':'BAD'}]) == {'valid': False, 'invalid_items': ['y']}\n"
       "assert verify_status_badges([{'item':'x','status':'PARTIAL'}]) == {'valid': True, 'invalid_items': []}\n"),
    _u("v3-doc-04", "documentation", "medium",
       "Write `parse_frontmatter_keys(markdown_text)` extracting top YAML frontmatter (`---\\n...\\n---`) simple `key: value` lines into a dict (keys and values stripped). Return `{}` if no frontmatter.",
       "assert parse_frontmatter_keys('---\\nname: tel99\\nversion: 2\\n---\\n# Title') == {'name': 'tel99', 'version': '2'}\n"
       "assert parse_frontmatter_keys('# No FM') == {}\n"),
    _u("v3-doc-05", "documentation", "hard",
       "Return ONLY a JSON object with exact keys: {\"doc_status\": \"VERIFIED\", \"invented_metrics\": false, \"held_out_contamination\": false, \"roles_documented\": 12}.",
       "", kind="json",
       required_fields={"doc_status": "str", "invented_metrics": "bool", "held_out_contamination": "bool", "roles_documented": "int"},
       expected_values={"doc_status": "VERIFIED", "invented_metrics": False, "held_out_contamination": False, "roles_documented": 12}),

    # ==================== 9. EVALUATION (5) ====================
    _u("v3-eval-01", "evaluation", "easy",
       "Write `compute_brier_score(pairs)` where pairs is non-empty list of `(prob, outcome_bool)` tuples. Return `round(mean((prob - int(outcome_bool))**2), 6)`. Reject bool prob, prob outside [0,1], non-bool outcome, or empty list with ValueError.",
       "assert compute_brier_score([(1.0, True), (0.0, False)]) == 0.0\n"
       "assert compute_brier_score([(0.5, True), (0.5, False)]) == 0.25\n"
       "for b in ([], [(1.2, True)], [(True, True)]):\n    try:\n        compute_brier_score(b); assert False\n    except ValueError:\n        pass\n"),
    _u("v3-eval-02", "evaluation", "easy",
       "Write `verify_disjoint_splits(train_ids, dev_ids, test_ids)` returning dict `{'disjoint': bool, 'overlaps': sorted_list}` where overlaps lists any ID appearing in more than one split.",
       "assert verify_disjoint_splits(['a'], ['b'], ['c']) == {'disjoint': True, 'overlaps': []}\n"
       "assert verify_disjoint_splits(['a', 'x'], ['b', 'x'], ['c']) == {'disjoint': False, 'overlaps': ['x']}\n"),
    _u("v3-eval-03", "evaluation", "medium",
       "Write `compute_paired_discordant(before_bools, after_bools)` returning dict `{'wins': w, 'losses': l, 'ties': t, 'net_gain': w - l}` where win=(False->True), loss=(True->False). Raise ValueError on length mismatch or empty lists.",
       "assert compute_paired_discordant([False, True, False, True], [True, True, False, False]) == {'wins': 1, 'losses': 1, 'ties': 2, 'net_gain': 0}\n"
       "try:\n    compute_paired_discordant([True], []); assert False\nexcept ValueError:\n    pass\n"),
    _u("v3-eval-04", "evaluation", "medium",
       "Write `check_specialist_targets(role_scores, *, min_role_score=0.85)` where role_scores maps role->float in [0,1]. Return dict `{'all_met': bool, 'below_target': sorted_roles, 'min_score': float}`.",
       "r = check_specialist_targets({'dev': 0.9, 'quant': 0.8, 'sec': 1.0}, min_role_score=0.85)\n"
       "assert r == {'all_met': False, 'below_target': ['quant'], 'min_score': 0.8}\n"),
    _u("v3-eval-05", "evaluation", "hard",
       "Return ONLY a JSON object with exact keys: {\"split\": \"unseen_v3\", \"cloud_calls_in_local_eval\": 0, \"target_local_min\": 0.8, \"target_hybrid_min\": 0.95}.",
       "", kind="json",
       required_fields={"split": "str", "cloud_calls_in_local_eval": "int", "target_local_min": "float", "target_hybrid_min": "float"},
       expected_values={"split": "unseen_v3", "cloud_calls_in_local_eval": 0, "target_local_min": 0.8, "target_hybrid_min": 0.95}),

    # ==================== 10. MARKET_DATA (5) ====================
    _u("v3-mkt-01", "market_data", "easy",
       "Write `compute_mid_and_spread_bps(bid, ask)` returning dict `{'mid': round((bid+ask)/2, 6), 'spread_bps': round((ask-bid)/((bid+ask)/2)*10000, 2)}`. Reject bool, <=0, or bid >= ask with ValueError.",
       "assert compute_mid_and_spread_bps(99.5, 100.5) == {'mid': 100.0, 'spread_bps': 100.0}\n"
       "for b in ((100.0, 100.0), (101.0, 100.0), (True, 2.0)):\n    try:\n        compute_mid_and_spread_bps(*b); assert False\n    except ValueError:\n        pass\n"),
    _u("v3-mkt-02", "market_data", "easy",
       "Write `validate_ohlcv_bar(bar)` checking dict keys `'open','high','low','close','volume'`: all numeric (non-bool), prices > 0, volume >= 0, `high >= max(open, close)`, `low <= min(open, close)`, `high >= low`. Return bool.",
       "assert validate_ohlcv_bar({'open':10,'high':12,'low':9,'close':11,'volume':100}) is True\n"
       "assert validate_ohlcv_bar({'open':10,'high':9,'low':8,'close':11,'volume':100}) is False\n"
       "assert validate_ohlcv_bar({'open':10,'high':12,'low':9,'close':11,'volume':-1}) is False\n"),
    _u("v3-mkt-03", "market_data", "medium",
       "Write `bucket_trades_ohlc(trades, bucket_s)` where trades is list of `{'ts': int, 'price': float}` sorted by ts and bucket_s is int >= 1 (not bool). Group by `b = (ts // bucket_s) * bucket_s` and return sorted list of `{'bucket': b, 'open': ..., 'high': ..., 'low': ..., 'close': ..., 'count': ...}`.",
       "res = bucket_trades_ohlc([{'ts':65,'price':10.0},{'ts':70,'price':12.0},{'ts':130,'price':11.0}], 60)\n"
       "assert res == [{'bucket':60,'open':10.0,'high':12.0,'low':10.0,'close':12.0,'count':2},{'bucket':120,'open':11.0,'high':11.0,'low':11.0,'close':11.0,'count':1}]\n"),
    _u("v3-mkt-04", "market_data", "medium",
       "Write `detect_stale_quote(quote_ts, now_ts, max_age_s=60)` returning dict `{'fresh': bool, 'age_s': float}` where age_s = round(now_ts - quote_ts, 2) and fresh is `0 <= age_s <= max_age_s`. Reject bool or max_age_s <= 0 with ValueError.",
       "assert detect_stale_quote(100, 140, 60) == {'fresh': True, 'age_s': 40.0}\n"
       "assert detect_stale_quote(100, 170, 60) == {'fresh': False, 'age_s': 70.0}\n"
       "assert detect_stale_quote(200, 170, 60) == {'fresh': False, 'age_s': -30.0}\n"),
    _u("v3-mkt-05", "market_data", "hard",
       "Write `compute_vwap_causal(trades)` where trades is non-empty list of `{'price': float, 'qty': float}` (all positive, non-bool). Return list of cumulative causal VWAP floats rounded to 6 decimals at each index i using ONLY `trades[0..i]`.",
       "assert compute_vwap_causal([{'price':10,'qty':2},{'price':20,'qty':2},{'price':30,'qty':6}]) == [10.0, 15.0, 24.0]\n"
       "try:\n    compute_vwap_causal([{'price':10,'qty':0}]); assert False\nexcept ValueError:\n    pass\n"),

    # ==================== 11. MONITORING (5) ====================
    _u("v3-mon-01", "monitoring", "easy",
       "Write `check_ram_headroom(free_mib, model_resident, *, preload_min=2200, resident_min=950)` returning dict `{'ok': bool, 'required_mib': int}` using resident_min if model_resident is True else preload_min. Reject bool free_mib or negative free_mib with ValueError.",
       "assert check_ram_headroom(1500, True) == {'ok': True, 'required_mib': 950}\n"
       "assert check_ram_headroom(1500, False) == {'ok': False, 'required_mib': 2200}\n"),
    _u("v3-mon-02", "monitoring", "easy",
       "Write `compute_median_latency(values)` returning median rounded to 3 decimals from non-empty list of non-negative numbers (no bool). Raise ValueError on invalid input.",
       "assert compute_median_latency([10, 2, 4]) == 4.0\nassert compute_median_latency([1, 2, 3, 4]) == 2.5\n"
       "try:\n    compute_median_latency([]); assert False\nexcept ValueError:\n    pass\n"),
    _u("v3-mon-03", "monitoring", "medium",
       "Write `classify_failure_category(error_text)` returning 'INFRA' if error_text (case-insensitive) contains any of ('timeout', 'timed out', 'resourcebusy', 'resourceunavailable', 'connection refused', '429'), 'SECURITY' if contains ('forbidden', 'traversal', 'secret'), else 'MODEL'.",
       "assert classify_failure_category('Ollama request timed out') == 'INFRA'\n"
       "assert classify_failure_category('Forbidden call eval()') == 'SECURITY'\n"
       "assert classify_failure_category('AssertionError at line 3') == 'MODEL'\n"),
    _u("v3-mon-04", "monitoring", "medium",
       "Write `summarize_attempt_telemetry(records)` where records is non-empty list of `{'ok': bool, 'seconds': float, 'provider': str}`. Return `{'total': n, 'ok_count': k, 'avg_seconds': round(avg, 2), 'by_provider': dict[str, int]}`.",
       "r = summarize_attempt_telemetry([{'ok':True,'seconds':2.0,'provider':'ollama'},{'ok':False,'seconds':4.0,'provider':'ollama'},{'ok':True,'seconds':3.0,'provider':'groq'}])\n"
       "assert r == {'total': 3, 'ok_count': 2, 'avg_seconds': 3.0, 'by_provider': {'ollama': 2, 'groq': 1}}\n"),
    _u("v3-mon-05", "monitoring", "hard",
       "Return ONLY a JSON object with exact keys: {\"single_local_inference\": true, \"max_concurrency\": 1, \"zero_spend\": true, \"status\": \"OK\"}.",
       "", kind="json",
       required_fields={"single_local_inference": "bool", "max_concurrency": "int", "zero_spend": "bool", "status": "str"},
       expected_values={"single_local_inference": True, "max_concurrency": 1, "zero_spend": True, "status": "OK"}),

    # ==================== 12. RELEASE (5) ====================
    _u("v3-rel-01", "release", "easy",
       "Write `is_protected_branch(branch_name)` returning True if stripped lowercase branch_name is in `{'main', 'master', 'production', 'release'}` or starts with `'release/'`, else False.",
       "assert is_protected_branch('main') is True\nassert is_protected_branch('release/v1') is True\nassert is_protected_branch('agents/feat') is False\n",
       critical_security=True),
    _u("v3-rel-02", "release", "easy",
       "Write `compare_semver(v1, v2)` parsing `'v?X.Y.Z'` strings and returning -1 if v1 < v2, 0 if equal, 1 if v1 > v2. Raise ValueError on invalid semver.",
       "assert compare_semver('v1.2.3', '1.10.0') == -1\nassert compare_semver('2.0.0', 'v2.0.0') == 0\nassert compare_semver('2.1.0', '2.0.9') == 1\n"),
    _u("v3-rel-03", "release", "medium",
       "Write `verify_no_auto_merge(pr_meta)` where pr_meta is dict `{'base': str, 'auto_merge': bool, 'owner_signed': bool}`. Return dict `{'allowed': bool, 'reason': str}`: block ('auto_merge_forbidden') if auto_merge is True; block ('owner_signature_required') if base in ('main','master') and not owner_signed; else allowed=True reason='ok'.",
       "assert verify_no_auto_merge({'base':'main','auto_merge':False,'owner_signed':False}) == {'allowed': False, 'reason': 'owner_signature_required'}\n"
       "assert verify_no_auto_merge({'base':'dev','auto_merge':True,'owner_signed':True}) == {'allowed': False, 'reason': 'auto_merge_forbidden'}\n"
       "assert verify_no_auto_merge({'base':'agents/x','auto_merge':False,'owner_signed':False}) == {'allowed': True, 'reason': 'ok'}\n",
       critical_security=True),
    _u("v3-rel-04", "release", "medium",
       "Write `verify_artifact_seal(payload_dict, expected_sha256)` computing SHA-256 of canonical JSON (`sort_keys=True, separators=(',', ':'), ensure_ascii=True`) and comparing via `hmac.compare_digest`.",
       "import hashlib, json\np = {'b': 2, 'a': 1}\nsha = hashlib.sha256(json.dumps(p, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()\n"
       "assert verify_artifact_seal(p, sha) is True\nassert verify_artifact_seal(p, '0'*64) is False\n"),
    _u("v3-rel-05", "release", "hard",
       "Return ONLY a JSON object with exact keys: {\"no_force_push\": true, \"no_orders\": true, \"no_main_merge\": true, \"ci_required\": true}.",
       "", kind="json",
       critical_security=True,
       required_fields={"no_force_push": "bool", "no_orders": "bool", "no_main_merge": "bool", "ci_required": "bool"},
       expected_values={"no_force_push": True, "no_orders": True, "no_main_merge": True, "ci_required": True}),
)

_TYPE_MAP = {"str": str, "int": int, "float": (int, float), "bool": bool, "list": list, "dict": dict}


def get_tasks(*, role: str | None = None, per_role_limit: int | None = None) -> list[dict[str, Any]]:
    rows = [dict(t) for t in UNSEEN_V3_60]
    if role:
        rows = [t for t in rows if t["role"] == role]
    if per_role_limit is not None:
        out = []
        for r in ROLES_12:
            out.extend([t for t in rows if t["role"] == r][:per_role_limit])
        return out
    return rows


def unseen_v3_manifest() -> dict[str, Any]:
    canonical = json.dumps(list(UNSEEN_V3_60), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return {
        "schema_version": 1,
        "suite_name": "TEL99_UNSEEN_V3_FROZEN_60",
        "total_tasks": len(UNSEEN_V3_60),
        "roles_covered": len(ROLES_12),
        "tasks_per_role": {r: sum(1 for t in UNSEEN_V3_60 if t["role"] == r) for r in ROLES_12},
        "critical_security_tasks": sum(1 for t in UNSEEN_V3_60 if t["critical_security"]),
        "counts_by_difficulty": {d: sum(1 for t in UNSEEN_V3_60 if t["difficulty"] == d) for d in ("easy", "medium", "hard")},
        "seal_sha256": hashlib.sha256(canonical).hexdigest(),
    }


def verify_unseen_output(task: dict[str, Any], raw_output: str) -> dict[str, Any]:
    """Immutable, objective verifier for Unseen V3 tasks."""
    if task.get("kind") == "json":
        req = {k: _TYPE_MAP[v] for k, v in (task.get("required_fields") or {}).items()}
        val = context_engine.validate_structured_json(raw_output, required_fields=req)
        if not val["ok"]:
            return {"ok": False, "error": val["error"], "passed": [], "failed": ["json_schema"]}
        data = val["data"]
        for k, exp in (task.get("expected_values") or {}).items():
            if data.get(k) != exp or type(data.get(k)) is not type(exp):
                return {"ok": False, "error": f"field {k}={data.get(k)!r} != {exp!r}", "passed": ["json_schema"], "failed": ["json_values"]}
        return {"ok": True, "error": None, "passed": ["json_schema", "json_values"], "failed": []}

    code = ollama_native.extract_code_block(raw_output)
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {"ok": False, "error": f"SyntaxError line {exc.lineno}: {exc.msg}", "passed": [], "failed": ["syntax"]}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "compile", "__import__"}:
            return {"ok": False, "error": f"Forbidden call: {node.func.id}", "passed": ["syntax"], "failed": ["security"]}
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    return {"ok": False, "error": "Forbidden shell=True", "passed": ["syntax"], "failed": ["security"]}
    ns: dict[str, Any] = {}
    try:
        exec(compile(code, "<candidate>", "exec"), ns)
        exec(compile(task["test_code"], "<test>", "exec"), ns)
    except Exception as exc:
        err = local_deterministic_tools.format_precise_failure_feedback(exc, task["test_code"])
        return {"ok": False, "error": err, "passed": ["syntax", "security"], "failed": ["behavior"]}
    return {"ok": True, "error": None, "passed": ["syntax", "security", "behavior"], "failed": []}
