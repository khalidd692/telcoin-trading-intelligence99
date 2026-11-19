"""Reproduce the integration acceptance suite without real model calls."""
import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--sandbox-image")
    args=parser.parse_args()
    if args.sandbox_image:
        os.environ["TEL99_TEST_SANDBOX_IMAGE"]=args.sandbox_image
    private=ROOT/".tel99-automation-state/final-tests"
    private.mkdir(parents=True,exist_ok=True)
    public=ROOT/"docs/agents/autonomy-evidence"
    public.mkdir(parents=True,exist_ok=True)
    loader=unittest.TestLoader()
    suite=unittest.TestSuite([
        loader.discover(str(ROOT/"tests"),pattern="test_agent*.py"),
        loader.loadTestsFromNames(["tests.test_autonomy_runtime","tests.test_kilo_executor",
            "tests.test_kilo_process_control","tests.test_autonomy_review_regressions","tests.test_local_codex"])])
    with (private/"tests.log").open("w",encoding="utf-8") as log, contextlib.redirect_stdout(log):
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    summary={"utc":datetime.now(timezone.utc).isoformat(),
        "command":"python -B tests/run_autonomy_acceptance.py --sandbox-image "+str(args.sandbox_image),
        "tests_run":result.testsRun,"failures":[t.id() for t,_ in result.failures],
        "errors":[t.id() for t,_ in result.errors],
        "skipped":[{"test":t.id(),"reason":why} for t,why in result.skipped],
        "success":result.wasSuccessful(),"docker_image":args.sandbox_image,
        "log_sha256":hashlib.sha256((private/"tests.log").read_bytes()).hexdigest(),
        "network_model_calls":0}
    (public/"tests-summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary))
    return 0 if result.wasSuccessful() else 1

if __name__=="__main__":
    raise SystemExit(main())
