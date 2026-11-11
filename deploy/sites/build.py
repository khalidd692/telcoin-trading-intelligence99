"""Build the existing terminal as one Sites Worker with fixed read-only proxies."""
import json,sys,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[2]
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
assets={}
for name in ['index.html','app.js','core.js','scenarios.js','terminal.css','data.json','vendor/lightweight-charts-5.0.8.js']:
 p=root/'site/terminal'/name
 kind={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json'}[p.suffix]
 assets['/'+name]={'body':p.read_text(),'type':kind}
sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assets['/version.json']={'body':json.dumps({'product_commit':sha,'mode':'read-only'}),'type':'application/json'}
(out/'index.js').write_text('const ASSETS='+json.dumps(assets,ensure_ascii=False)+';\n'+(root/'deploy/sites/worker.mjs').read_text())
print(json.dumps({'product_commit':sha,'worker_bytes':(out/'index.js').stat().st_size}))
