import json,urllib.request,time
idx=json.load(urllib.request.urlopen('http://127.0.0.1:8772/api/index'));results=[]
for row in idx['assets']:
 if not row.get('levelPreview'):continue
 start=time.time()
 try:
  data=json.load(urllib.request.urlopen(f"http://127.0.0.1:8772/asset/{row['id']}/level"));result=dict(name=row['name'],seconds=round(time.time()-start,2),bounds=data['bounds'],groups=data['groups'],report=data['report'],warnings=data['warnings']);print(row['name'],data['report']['drawInstances'],'instances',len(data['report'].get('unresolvedForms',[])),'unresolved',len(data['warnings']),'warnings',flush=True)
 except Exception as e:
  result=dict(name=row['name'],error=str(e));print(result,flush=True)
 results.append(result)
open('sac-asset-viewer/research/levels-audit.json','w').write(json.dumps(results,indent=2))
