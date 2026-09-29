import array,json,math,urllib.request
base='http://127.0.0.1:8766'
def get(url):return urllib.request.urlopen(base+url).read()
index=json.loads(get('/api/index'));rows=[r for r in index['assets'] if r.get('levelPreview')];results=[]
assert len(rows)==30
for r in rows:
 s=json.loads(get('/asset/'+r['id']+'/level'));b=get('/asset/'+r['id']+'/level-bin')
 assert s['version']==2 and s['vertexStride']==48 and len(b)==s['report']['binaryBytes']
 assert len(s['lights'])==2 and all(l['parentHash']==0 for l in s['lights'])
 materialkeys=[json.dumps(m,sort_keys=True) for m in s['materials']];assert len(set(materialkeys))==len(materialkeys)
 parts=colors=0
 for g in s['geometry'].values():
  for p in g['parts']:
   vo,io,n=p['vertexOffset'],p['indexOffset'],p['count'];assert (io-vo)%48==0 and io+n*4<=len(b)
   v=array.array('f');v.frombytes(b[vo:io]);inds=array.array('I');inds.frombytes(b[io:io+n*4])
   assert all(math.isfinite(x) for x in v)
   assert all(0<=x<=1 for x in v[11::12])
   assert not inds or max(inds)<len(v)//12
   assert not(p['bakedLighting'] and p['sceneLighting'])
   parts+=1;colors+=bool(p['bakedLighting'])
 results.append(dict(name=r['name'],parts=parts,bakedParts=colors,bytes=len(b),lights=len(s['lights'])))
 print(r['name'],'PASS',parts,'parts,',colors,'baked',flush=True)
open('sac-asset-viewer/research/rendering-audit.json','w').write(json.dumps(results,indent=2))
print('PASS: all 30 production-server manifests and binary buffers validated')
