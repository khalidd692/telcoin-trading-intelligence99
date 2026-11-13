"""Build the existing terminal as one Sites Worker with fixed read-only proxies."""
import hashlib,json,math,os,re,sys,subprocess,time
from pathlib import Path
root=Path(__file__).resolve().parents[2]
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
names=['index.html','app.js','core.js','scenarios.js','smartview.js','radar.js','smartwidgets.js','terminal.css','data.json','vendor/lightweight-charts-5.0.8.js']
paths=['site/terminal/'+name for name in names]+['deploy/sites/worker.mjs','deploy/sites/build.py']
def git_blob(name):
 content=(root/name).read_bytes()
 return hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest()
sha=os.environ.get('TEL99_PRODUCT_COMMIT')
if sha is None:
 sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
 for name in paths:
  try: committed=subprocess.check_output(['git','rev-parse',sha+':'+name],cwd=root,text=True,stderr=subprocess.DEVNULL).strip()
  except subprocess.CalledProcessError as exc: raise ValueError('Product file missing from commit: '+name) from exc
  if committed!=git_blob(name):raise ValueError('Product file differs from commit: '+name)
else:
 manifest_path=os.environ.get('TEL99_PRODUCT_BLOBS_PATH')
 if not manifest_path:
  raise ValueError('An explicit commit requires a verified Git blob manifest')
 manifest=json.loads(Path(manifest_path).read_text())
 if manifest.get('commit')!=sha or not isinstance(manifest.get('files'),dict):
  raise ValueError('Product blob manifest does not match the requested commit')
 # The caller must obtain this manifest from a trusted tree for the given
 # commit. This check validates file bytes, not the manifest's provenance.
 for name in paths:
  if manifest['files'].get(name)!=git_blob(name):
   raise ValueError('Product file differs from manifest: '+name)
if not re.fullmatch(r'[0-9a-f]{40}',sha):
 raise ValueError('TEL99 product commit must be a full lowercase SHA-1')
fallback=os.environ.get('TEL99_FALLBACK_DATA')
if fallback:
 baseline=json.loads((root/'site/terminal/data.json').read_text())
 candidate=json.loads(Path(fallback).read_text())
 for key in ['schema_version','market','source','research_source_sha256','lab','safety']:
  if candidate.get(key)!=baseline.get(key):raise ValueError('Fallback differs in '+key)
 at=candidate.get('as_of')
 if isinstance(at,bool) or not isinstance(at,(int,float)) or not math.isfinite(at) or at<baseline['as_of'] or at>time.time()+60:
  raise ValueError('Invalid fallback capture time')
 if candidate.get('safety',{}).get('real_orders') is not False or candidate.get('safety',{}).get('paper_orders') is not False:
  raise ValueError('Fallback must remain read-only')
assets={}
for name in names:
 p=Path(fallback) if name=='data.json' and fallback else root/'site/terminal'/name
 kind={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json'}[p.suffix]
 assets['/'+name]={'body':p.read_text(),'type':kind}
assets['/version.json']={'body':json.dumps({'product_commit':sha,'mode':'read-only'}),'type':'application/json'}
(out/'index.js').write_text('const ASSETS='+json.dumps(assets,ensure_ascii=False)+';\n'+(root/'deploy/sites/worker.mjs').read_text())
print(json.dumps({'product_commit':sha,'worker_bytes':(out/'index.js').stat().st_size}))
