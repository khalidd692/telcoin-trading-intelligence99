"""Real-process acceptance for Windows watcher STOP and durable crash boundaries.

No GitHub or model network is contacted. Crash helpers terminate their own
process with os._exit after a confirmed durable checkpoint.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'scripts/agents/automation/autonomy_runtime.py'

BOOTSTRAP = r'''
import hashlib, json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from scripts.agents.automation.autonomy_runtime import Runtime, seal
root = Path(sys.argv[2])
action = sys.argv[3]
m = dict(id='process-test-a', project='synthetic', owner='kilo', priority='P0',
    dependencies=[], specialist='tel99-analyst', synthetic_data=True,
    objective='Return OK', expected_sha256=hashlib.sha256(b'OK').hexdigest())
result = dict(artifact='OK', sha256=hashlib.sha256(b'OK').hexdigest(),
    specialist_id='tel99-analyst', provider_evidence=dict(cost_usd='0',
    http_status=200, catalog_sha256='a'*64, response_sha256='b'*64))
def forbidden(m):
    (root/'UNEXPECTED_WORKER_CALL').touch()
    raise RuntimeError('No worker replay allowed')
if action in ('RUNNING', 'WORKER_EXITED'):
    r = Runtime(root)
    assert r.claim(m)
    if action == 'RUNNING': r.save(m, action)
    else: r.save(m, action, result=result)
    os._exit(77)
if action == 'resume':
    r = Runtime(root, executor=forbidden)
    r.run_queue([m], seal([m]))
    print(json.dumps(r.state(m)), flush=True)
if action == 'race':
    import time
    root.mkdir(parents=True, exist_ok=True)
    (root/('ready-'+str(os.getpid()))).write_text('ready')
    deadline = time.monotonic()+10
    while not (root/'race-start').exists():
        if time.monotonic()>deadline: raise RuntimeError('barrier timeout')
        time.sleep(.02)
    def counted(m):
        with (root/'worker-executions.jsonl').open('ab', buffering=0) as log:
            log.write((str(os.getpid())+'\n').encode())
        time.sleep(1)
        return result
    r = Runtime(root, executor=counted)
    r.run_queue([m], seal([m]))
    print(json.dumps(r.state(m)), flush=True)
if action == 'active':
    class SleepingWorker(Runtime):
        def worker_command(self, m):
            code = "import os,sys,time;from pathlib import Path;Path(sys.argv[1]).write_text(str(os.getpid()));time.sleep(60)"
            return [sys.executable, '-I', '-B', '-c', code, str(root/'worker.pid')]
    r = SleepingWorker(root)
    r.run_queue([m], seal([m]))
'''


class ProcessControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def helper(self, action):
        return subprocess.Popen([sys.executable, '-B', '-c', BOOTSTRAP,
            str(ROOT), str(self.root), action], cwd=ROOT,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def finish(self, p, timeout=15):
        try:
            out, err = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill(); out, err = p.communicate()
            self.fail('process failed to stop within bound: ' + err[-1000:])
        return p.returncode, out, err

    def until_file(self, path, p):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if path.exists() and path.stat().st_size > 0:
                return
            if p.poll() is not None:
                self.fail('child exited before readiness: ' + str(p.communicate()))
            time.sleep(.05)
        p.kill();p.communicate()
        self.fail('child readiness timeout')

    def stop_cli(self):
        done = subprocess.run([sys.executable, '-B', str(RUNTIME), 'stop',
            '--state', str(self.root)], cwd=ROOT, capture_output=True,
            text=True, timeout=15)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_two_real_workers_execute_one_mission_exactly_once(self):
        workers = [self.helper('race'), self.helper('race')]
        deadline = time.monotonic()+12
        while len(list(self.root.glob('ready-*'))) < 2 and time.monotonic()<deadline:
            for process in workers:
                self.assertIsNone(process.poll())
            time.sleep(.02)
        self.assertEqual(len(list(self.root.glob('ready-*'))), 2)
        (self.root/'race-start').touch()
        results = [self.finish(process) for process in workers]
        for code, _, err in results:
            self.assertEqual(code, 0, err)
        executions = (self.root/'worker-executions.jsonl').read_text().splitlines()
        self.assertEqual(len(executions), 1)
        row = json.loads((self.root/'ledger/kilo-local/process-test-a.json').read_text())
        self.assertEqual(row['status'], 'ACCEPTED')
        self.assertFalse((self.root/'UNEXPECTED_WORKER_CALL').exists())

    def test_watcher_stop_interrupts_poll_interval(self):
        registry = self.root/'registry.json'
        registry.write_text(json.dumps({'missions': [], 'approvals': {}}))
        sha = hashlib.sha256(registry.read_bytes()).hexdigest()
        p = subprocess.Popen([sys.executable, '-B', str(RUNTIME), 'run',
            '--state', str(self.root), '--registry', str(registry),
            '--registry-sha256', sha, '--seconds', '60'], cwd=ROOT,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # An empty file lock is legitimate; readiness follows successful creation.
        deadline = time.monotonic() + 12
        while not (self.root/'runtime.lock').exists() and time.monotonic() < deadline:
            self.assertIsNone(p.poll()); time.sleep(.05)
        self.assertTrue((self.root/'runtime.lock').exists())
        started = time.monotonic()
        self.stop_cli()
        code, out, err = self.finish(p, 5)
        self.assertEqual(code, 0, err)
        self.assertLess(time.monotonic()-started, 5)
        self.assertIn('STOPPED', out)

    def test_actual_crash_running_never_replays(self):
        p = self.helper('RUNNING')
        code, _, err = self.finish(p)
        self.assertEqual(code, 77, err)
        code, out, err = self.finish(self.helper('resume'))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out.splitlines()[-1])['status'], 'AWAITING_HUMAN')
        self.assertFalse((self.root/'UNEXPECTED_WORKER_CALL').exists())

    def test_actual_crash_after_receipt_verifies_without_worker(self):
        p = self.helper('WORKER_EXITED')
        code, _, err = self.finish(p)
        self.assertEqual(code, 77, err)
        code, out, err = self.finish(self.helper('resume'))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out.splitlines()[-1])['status'], 'ACCEPTED')
        self.assertFalse((self.root/'UNEXPECTED_WORKER_CALL').exists())

    def test_stop_terminates_actual_active_worker(self):
        p = self.helper('active')
        self.until_file(self.root/'worker.pid', p)
        pid = int((self.root/'worker.pid').read_text())
        self.stop_cli()
        code, _, err = self.finish(p, 8)
        self.assertEqual(code, 0, err)
        if os.name == 'nt':
            import ctypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.OpenProcess.restype = ctypes.c_void_p
            kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            handle = kernel.OpenProcess(0x100000, False, pid)
            if handle:
                try:
                    self.assertEqual(kernel.WaitForSingleObject(handle, 1000), 0)
                finally:
                    kernel.CloseHandle(handle)
        else:
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)
        row = json.loads((self.root/'ledger/kilo-local/process-test-a.json').read_text())
        self.assertEqual(row['status'], 'BLOCKED')
        self.assertFalse((self.root/'UNEXPECTED_WORKER_CALL').exists())


if __name__ == '__main__':
    unittest.main()
