import json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cooked
base=Path(__file__).resolve().parents[1]
index=json.loads((base/'output/index.json').read_text())
count=normals=0
for row in index['assets']:
 if not row.get('modelPreview'):continue
 model=cooked.load(str(Path(index['root'])/row['source'])).model(row['offset'])
 for mesh in model['meshes']:
  ns=mesh.get('normals')
  if ns is not None:
   assert len(ns)==len(mesh['positions']),row['name']
   for n in ns:
    assert len(n)==3 and all(math.isfinite(v) for v in n),row['name']
    length=math.sqrt(sum(v*v for v in n))
    assert length<1e-6 or 0.98<length<1.02,(row['name'],length)
   normals+=len(ns)
 count+=1
print(f'PASS: {count} models; {normals} authored normals, finite and unit length within 2%.')
