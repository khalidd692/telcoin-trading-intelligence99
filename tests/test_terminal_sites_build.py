"""The published Worker must identify the exact product commit it packages."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class SitesBuildProvenance(unittest.TestCase):
    def manifest(self, directory, commit):
        names=['index.html','app.js','core.js','scenarios.js','smartview.js','radar.js','smartwidgets.js','terminal.css','data.json','vendor/lightweight-charts-5.0.8.js']
        paths=['site/terminal/'+name for name in names]+['deploy/sites/worker.mjs','deploy/sites/build.py']
        def digest(name):
            content=Path(name).read_bytes()
            return hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest()
        manifest=Path(directory,'manifest.json')
        manifest.write_text(json.dumps({'commit':commit,'files':{name:digest(name) for name in paths}}))
        return manifest

    def test_unverified_explicit_commit_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, TEL99_PRODUCT_COMMIT='a' * 40)
            env.pop('TEL99_PRODUCT_BLOBS_PATH', None)
            run = subprocess.run([sys.executable, 'deploy/sites/build.py', directory], env=env,
                                 text=True, capture_output=True)
            self.assertNotEqual(run.returncode, 0, 'Un SHA fourni sans manifeste ne prouve pas le contenu')

    def test_explicit_product_commit_is_embedded_in_version(self):
        commit = 'a' * 40
        with tempfile.TemporaryDirectory() as directory:
            manifest=self.manifest(directory,commit)
            env = dict(os.environ, TEL99_PRODUCT_COMMIT=commit,TEL99_PRODUCT_BLOBS_PATH=str(manifest))
            run = subprocess.run([sys.executable, 'deploy/sites/build.py', directory], env=env,
                                 text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            source = Path(directory, 'index.js').read_text()
            assets = json.loads(source.removeprefix('const ASSETS=').split(';\n', 1)[0])
            self.assertEqual(json.loads(assets['/version.json']['body'])['product_commit'], commit)
            self.assertIn('/smartwidgets.js', assets)

    def test_product_blob_mismatch_is_rejected(self):
        commit='a'*40
        with tempfile.TemporaryDirectory() as directory:
            manifest=self.manifest(directory,commit)
            payload=json.loads(manifest.read_text())
            payload['files']['site/terminal/app.js']='0'*40
            manifest.write_text(json.dumps(payload))
            env=dict(os.environ,TEL99_PRODUCT_COMMIT=commit,TEL99_PRODUCT_BLOBS_PATH=str(manifest))
            run=subprocess.run([sys.executable,'deploy/sites/build.py',directory],env=env,text=True,capture_output=True)
            self.assertNotEqual(run.returncode,0)
            self.assertIn('site/terminal/app.js',run.stderr)

    def test_fallback_cannot_change_research_or_order_protections(self):
        commit='a'*40
        with tempfile.TemporaryDirectory() as directory:
            manifest=self.manifest(directory,commit)
            fallback=Path(directory,'fallback.json')
            payload=json.loads(Path('site/terminal/data.json').read_text())
            payload['safety']['real_orders']=True
            fallback.write_text(json.dumps(payload))
            env=dict(os.environ,TEL99_PRODUCT_COMMIT=commit,TEL99_PRODUCT_BLOBS_PATH=str(manifest),TEL99_FALLBACK_DATA=str(fallback))
            run=subprocess.run([sys.executable,'deploy/sites/build.py',directory],env=env,text=True,capture_output=True)
            self.assertNotEqual(run.returncode,0)
            self.assertIn('safety',run.stderr)

    def test_invalid_explicit_commit_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, TEL99_PRODUCT_COMMIT='not-a-sha')
            run = subprocess.run([sys.executable, 'deploy/sites/build.py', directory], env=env,
                                 text=True, capture_output=True)
            self.assertNotEqual(run.returncode, 0)


if __name__ == '__main__':
    unittest.main()
