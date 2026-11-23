"""End-to-end offline publisher fixture: real CAS, bounded Docker evidence, GitHub REST responses."""
import difflib
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.agents.automation import local_code_pr, local_codegen, local_team
from scripts.agents.automation.autonomy_runtime import Runtime, fingerprint
from tests.test_github_local_code_campaign import LocalFixture, FIRST, OWNER, comment, block

BASE = local_code_pr.BASE_SHA
REPO = local_code_pr.REPO
MID = "tel99-pilot-code-a"


def digest(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class FakeAPI:
    def __init__(self, *, proof, blob, issue, error_after_pr=False):
        self.proof = proof
        self.blob = blob
        self.issue = issue
        self.created = []
        self.refs = {local_code_pr.BASE_REF: BASE}
        self.commit = "c" * 40
        self.prs = []
        self.error_after_pr = error_after_pr

    def __call__(self, endpoint, *, method="GET", payload=None):
        prefix = f"repos/{REPO}/"
        assert endpoint.startswith(prefix), endpoint
        path = endpoint[len(prefix):]
        if method == "GET":
            if path.startswith("issues/comments/"):
                return self.proof
            if path.startswith("git/matching-refs/heads/"):
                name = path.removeprefix("git/matching-refs/heads/")
                return ([{"ref": f"refs/heads/{name}",
                          "object": {"type": "commit", "sha": self.refs[name]}}]
                        if name in self.refs else [])
            if path == f"git/commits/{BASE}":
                return {"sha": BASE, "tree": {"sha": "a" * 40}}
            if path.startswith("compare/"):
                return {"status": "ahead", "ahead_by": 1, "behind_by": 0,
                        "total_commits": 1, "commits": [{"sha": self.commit}],
                        "files": [{"filename": self.mission_path,
                                   "status": "modified", "sha": self.blob}]}
            if path.startswith("pulls?"):
                return self.prs.copy()
            raise AssertionError(f"unapproved GET {path}")
        self.created.append((path, payload))
        if path == "git/blobs":
            result = payload["content"].encode("utf-8")
            assert hashlib.sha1(f"blob {len(result)}\0".encode()+result,
                                usedforsecurity=False).hexdigest() == self.blob
            return {"sha": self.blob}
        if path == "git/trees":
            assert len(payload["tree"]) == 1
            assert payload["tree"][0]["path"] == self.mission_path
            return {"sha": "b" * 40}
        if path == "git/commits":
            assert payload["parents"] == [BASE]
            return {"sha": self.commit}
        if path == "git/refs":
            self.refs[payload["ref"].removeprefix("refs/heads/")] = payload["sha"]
            return {"ref": payload["ref"], "object": {"sha": payload["sha"]}}
        if path == "pulls":
            branch = payload["head"]
            pr = {"number": 805, "user": OWNER.copy(), "state": "open", "draft": True,
                  "merged_at": None, "title": payload["title"], "body": payload["body"],
                  "html_url": f"https://github.com/{REPO}/pull/805",
                  "base": {"ref": local_code_pr.BASE_REF, "sha": BASE,
                           "repo": {"full_name": REPO}},
                  "head": {"ref": branch, "sha": self.commit,
                           "repo": {"full_name": REPO}}}
            self.prs.append(pr)
            if self.error_after_pr:
                self.error_after_pr = False
                raise OSError("GitHub created PR but response lost")
            return pr
        raise AssertionError(f"unapproved POST {path}")


def fixture(root):
    ticket = LocalFixture()
    m = ticket.missions[0]
    source = "def kv_env():\n    return ('', '')\n"
    artifact = "def kv_env():\n    return ('ready', 'token')\n"
    candidate = local_codegen.replace_function(source, m["function"], artifact)
    diff = "".join(difflib.unified_diff(
        local_codegen._physical_lines(source),
        local_codegen._physical_lines(candidate),
        fromfile=f"a/{m['path']}", tofile=f"b/{m['path']}",
    ))
    analyst_note = "Keep the env tuple shape. Trim whitespace in the endpoint."
    analysis = {"role": "tel99-analyst", "model": "gemma4:e4b-tel99-8k",
                "kind": "read-only-advice", "analysis": analyst_note,
                "sha256": digest(analyst_note)}
    result = {"artifact": artifact, "sha256": digest(artifact),
              "provider": local_codegen.PROVIDER, "model": m["model"],
              "specialist_id": "tel99-dev",
              "agent_trace": local_team.trace(analysis, developer_model=m["model"], artifact=artifact)}
    verification = {
        "verifier": local_codegen.VERIFIER, "ok": True,
        "artifact_sha256": digest(artifact), "base_sha": BASE,
        "path": m["path"], "function": m["function"], "model": m["model"],
        "test_sha256": digest(m["test"]), "sandbox_image": m["sandbox_image"],
        "base_file_sha256": digest(source), "candidate_sha256": digest(candidate),
        "diff_sha256": digest(diff),
        "verification_role": {"role": "tel99-verifier",
                              "analyst_sha256": analysis["sha256"],
                              "method": "independent Docker baseline-red / candidate-green"},
        "checks": [{"name": "bounded-model-receipt", "ok": True},
                   {"name": "approved-function-diff", "ok": True},
                   {"name": "baseline-fails", "ok": True, "exit_code": 1},
                   {"name": "candidate-passes", "ok": True, "exit_code": 0}],
    }
    state = {"id": m["id"], "project": "tel99", "status": "ACCEPTED",
             "execution_status": "COMPLETED", "contract_sha256": fingerprint(m),
             "result": result, "verification": verification, "verdict": {"validated": True}}
    runtime = Runtime(root)
    store = runtime.store
    store.put(f"kilo-local/{m['id']}", state)
    store.put("github-local-code/config", {"repo": REPO, "issue": 240,
                                          "profile": "github-local-code", "campaign": True})
    store.put(f"kilo-github/approvals/{m['id']}", {
        "mission": m, "contract_sha256": fingerprint(m), "issue": FIRST,
        "base": local_code_pr.BASE_REF, "base_sha": BASE,
    })
    evidence_url = f"https://github.com/{REPO}/issues/{FIRST}#issuecomment-9001"
    event = {"event": local_code_pr.EVENT, "phase": "EVIDENCE", "issue": FIRST,
             "mission_id": m["id"], "scope": "approved-python-function",
             "status": "ACCEPTED", "contract_sha256": fingerprint(m),
             "artifact_sha256": digest(artifact),
             "verification_sha256": fingerprint(verification)}
    store.put(f"kilo-github/outbox/{m['id']}/EVIDENCE", {
        "event": event, "url": evidence_url,
    })
    proof = comment(9001, FIRST, block(local_code_pr.EVENT, event), "2026-11-23T18:05:00Z")
    proof["html_url"] = evidence_url
    folder = root / "verified-code" / m["id"]
    candidate_path = folder / m["path"]
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_text(candidate, encoding="utf-8")
    (folder / "change.diff").write_text(diff, encoding="utf-8")
    fake = FakeAPI(proof=proof, blob=hashlib.sha1(
        f"blob {len(candidate.encode())}\0".encode() + candidate.encode(),
        usedforsecurity=False).hexdigest(), issue=FIRST)
    fake.mission_path = m["path"]
    return store, state, evidence_url, fake, source


class CodePublisherTests(unittest.TestCase):
    def test_verified_code_publishes_one_draft_and_reconciles_without_duplication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store, state, url, fake, source = fixture(root)
            with patch.object(local_codegen, "_source", return_value=source):
                first = local_code_pr.publish_verified_code_pr(
                    REPO, FIRST, local_code_pr.BASE_REF, BASE,
                    state, url, api=fake, store=store, root=root,
                )
                second = local_code_pr.publish_verified_code_pr(
                    REPO, FIRST, local_code_pr.BASE_REF, BASE,
                    state, url, api=fake, store=store, root=root,
                )
            self.assertEqual(first, f"https://github.com/{REPO}/pull/805")
            self.assertEqual(first, second)
            self.assertEqual(len([name for name, payload in fake.created
                                  if name == "pulls"]), 1)
            self.assertEqual(len([name for name, payload in fake.created
                                  if name == "git/refs"]), 1)

    def test_lost_post_response_is_reconciled_by_get_not_reposted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store, state, url, fake, source = fixture(root)
            fake.error_after_pr = True
            with patch.object(local_codegen, "_source", return_value=source):
                result = local_code_pr.publish_verified_code_pr(
                    REPO, FIRST, local_code_pr.BASE_REF, BASE,
                    state, url, api=fake, store=store, root=root,
                )
            self.assertEqual(result, f"https://github.com/{REPO}/pull/805")
            self.assertEqual(len([name for name, _ in fake.created if name == "pulls"]), 1)

    def test_tampered_docker_or_receipt_fails_before_gh_network(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store, state, url, fake, source = fixture(root)
            state["verification"]["checks"][-1]["ok"] = False
            store.put(f"kilo-local/{state['id']}", state)
            with patch.object(local_codegen, "_source", return_value=source):
                result = local_code_pr.publish_verified_code_pr(
                    REPO, FIRST, local_code_pr.BASE_REF, BASE,
                    state, url, api=fake, store=store, root=root,
                )
            self.assertIsNone(result)
            self.assertFalse(fake.created)

if __name__ == "__main__":
    unittest.main()
