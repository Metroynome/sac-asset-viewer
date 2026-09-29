"""Assemble SAC cooked scene instances and BOG mobys. See FORMAT_NOTES.md."""
import array
import collections
import hashlib
import itertools
import json
import math
import re
import struct
from functools import lru_cache
from pathlib import Path
import cooked


def catalog(root):
    rows=[]
    for p in sorted((root/'image/Levels').glob('*/*.cooked'),key=lambda p:p.parent.name.lower()):
        folder=p.parent.name
        match=re.match(r'level(\d+)_(.*)',folder,re.I)
        name=f'Level {int(match[1])} - {match[2]}' if match else folder
        if folder.lower()=='level01_exterior':name='Level 1 - Museum / Exterior'
        source=p.relative_to(root).as_posix()
        rows.append(dict(id=hashlib.sha256(('level:'+source).encode()).hexdigest()[:20],name=name,category='Levels',group='Levels',source=source,offset=0,archive=p.relative_to(root/'image').as_posix(),size=p.stat().st_size,status='Fly-through preview',levelPreview=True,format='SAC assembled level'))
    rows.sort(key=lambda r:(not r['name'].startswith('Level '),int(re.search(r'Level (\d+)',r['name'])[1]) if r['name'].startswith('Level ') else 99,r['name']))
    return rows


def matrix(x,z,pos,scale):
    y=[z[1]*x[2]-z[2]*x[1],z[2]*x[0]-z[0]*x[2],z[0]*x[1]-z[1]*x[0]]
    return [v*scale[i] if j<3 else 0 for i,basis in enumerate((x,y,z)) for j,v in enumerate([*basis,0])]+[*pos,1]


def instances(scene):
    result=[]
    for tag,p,n in scene.records:
        if tag!='GINS':continue
        h,size=cooked.children(scene.b,p,n)['GINH'];b=scene.b
        if size!=116 or b[h+1]!=1:raise ValueError('Unsupported GINH version/size')
        x,z,pos,scale=[struct.unpack_from('<3f',b,h+i) for i in (2,14,26,38)]
        result.append(dict(name=cooked.string(b[h+62:h+94]),hash=cooked.u32(b,h+54),geometryHash=cooked.u32(b,h+94),parentHash=cooked.u32(b,h+98),parentPartHash=cooked.u32(b,h+102),flags=cooked.u32(b,h+50),lightGroup=cooked.u32(b,h+110),matrix=matrix(x,z,pos,scale),source='GINS'))
    return result


def lights(scene):
    """Saved ambient/directional lights; runtime light animation is not evaluated."""
    definitions={};placements=[];b=scene.b
    for tag,p,n in scene.records:
        if tag=='LITB':
            h,size=cooked.children(b,p,n)['LITH']
            if size!=72 or b[h]!=1:raise ValueError('Unsupported LITH version/size')
            intensity=math.sqrt(max(0,cooked.f32(b,h+10)))
            kind=b[h+1]
            definitions[cooked.u32(b,h+26)]=dict(name=cooked.string(b[h+34:h+66]),type=kind,lightGroup=cooked.u32(b,h+2),color=[v/255*min(1,intensity) if kind==0 else v/255*intensity for v in b[h+6:h+9]])
        elif tag=='LINS':
            h,size=cooked.children(b,p,n)['LINH']
            if size!=116 or b[h+1]!=1:raise ValueError('Unsupported LINH version/size')
            placements.append(h)
    result=[]
    for h in placements:
        light=definitions.get(cooked.u32(b,h+94))
        if light is None or not cooked.u32(b,h+50)&1:continue
        light=dict(light);light['parentHash']=cooked.u32(b,h+98)
        # ProcessLights stores the negative world Z basis as the light vector.
        z=struct.unpack_from('<3f',b,h+14);length=math.sqrt(sum(v*v for v in z)) or 1
        light['direction']=[-v/length for v in z]
        result.append(light)
    return result


def cstring(b,p):
    if not 0<p<len(b):return None
    s=b[p:p+100].split(b'\0')[0]
    return s.decode('ascii') if s and len(s)<100 and all(32<=v<127 for v in s) else None


@lru_cache(maxsize=4)
def type_names(module,signatures):
    """136-byte REL type registry: signature, type-info pointer, 32 model-name pointers."""
    b=Path(module).read_bytes();result={}
    for sig in signatures:
        needle=struct.pack('<I',sig);start=0
        while True:
            p=b.find(needle,start)
            if p<0:break
            start=p+4
            if p%4 or p+136>len(b):continue
            info=cooked.u32(b,p+4)
            if not 0<info<len(b)-4:continue
            name=cstring(b,cooked.u32(b,info))
            if not name:continue
            pointers=struct.unpack_from('<32I',b,p+8)
            forms=[cstring(b,v) if v else None for v in pointers]
            if any(v and not s for v,s in zip(pointers,forms)):continue
            if sig in result and result[sig]!=(name,forms):raise ValueError('Ambiguous REL type registry')
            result[sig]=(name,forms)
    return result


def gameplay(root,row,assets):
    folder=Path(row['archive']).parent.name.lower()
    if folder=='level01_exterior':folder='level01_museum'
    bog=next((r for r in assets if r['category']=='Gameplay' and Path(r['archive']).parent.name.lower()==folder),None)
    if not bog:return [],{'note':'No gameplay archive found.'}
    with (root/bog['source']).open('rb') as f:f.seek(bog['offset']);b=f.read(bog['size'])
    if b[:4]!=b'BOG ' or cooked.u32(b,4)!=58 or cooked.u32(b,8)!=len(b):raise ValueError('Unsupported BOG')
    types,nt,start,count=struct.unpack_from('<4I',b,44)
    cooked.bounds(b,types,nt*80);cooked.bounds(b,start,count*128)
    signatures=tuple(cooked.u32(b,types+i*80+48) for i in range(nt))
    module=None
    for p in sorted((root/'disc/BIN').glob('*.REL')):
        if bog['archive'].lower().encode() in p.read_bytes().lower():module=p;break
    registry=type_names(str(module),signatures) if module else {}
    out=[];no_model=0;unresolved=[];pooled=0
    for i in range(count):
        p=start+i*128;t=cooked.u32(b,p+64)
        if not cooked.u32(b,p+92):pooled+=1;continue
        if not types<=t<types+nt*80 or (t-types)%80:raise ValueError('Invalid BOG type pointer')
        sig=cooked.u32(b,t+48);form=b[p+68];num=b[t+72]
        if not num:no_model+=1;continue
        if form>=num:raise ValueError('Invalid BOG form index')
        fp=cooked.u32(b,t+4)+form*52;cooked.bounds(b,fp,52)
        name,forms=registry.get(sig,(f'{sig:08x}',[]))
        model_name=forms[form] if form<len(forms) else None
        if not model_name:
            unresolved.append(dict(index=i,type=name,form=form));continue
        m=list(struct.unpack_from('<16f',b,p))
        if not all(math.isfinite(v) for v in m):raise ValueError('Invalid BOG matrix')
        group='Terrain / scenery' if name=='VehicleSection' else layer(model_name) if name=='VehicleObstacle' else 'Mobys'
        out.append(dict(name=f'{name} #{i}',modelName=model_name,matrix=m,source='BOG',flags=cooked.u32(b,p+100),group=group))
    return out,dict(source=bog['archive'],module=module.name if module else None,records=count,pooled=pooled,logicOnly=no_model,unresolvedForms=unresolved)


def layer(name):
    n=name.lower()
    if any(t in n for t in ('skybox','skydome','sky_dome','horizon','nebula','starsphere','starscape','moon','cloud','planet')):return 'Skybox'
    if any(t in n for t in ('bush','shrub','foliage','grass','tree','fern','flower','plant','leaf','leaves')):return 'Shrubs / foliage'
    if n.startswith(('inst_','def_')):return 'Ties / props'
    return 'Terrain / scenery'


def assemble(root,row,assets,model_loader):
    scene=cooked.load(str(root/row['source']));nodes=instances(scene);report={};byhash={n['hash']:n for n in nodes};resolved={}
    def world(n,stack=()):
        key=n['hash']
        if key in stack:raise ValueError('Cyclic scene parenting')
        if key not in resolved:
            parent=byhash.get(n['parentHash']);m=n['matrix']
            if parent:m=cooked.multiply(world(parent,stack+(key,)),m)
            resolved[key]=m
        return resolved[key]
    models=[a for a in assets if a.get('modelPreview')]
    local={int(a['signature'],16):a for a in models if a['archive']==row['archive']}
    shared={int(a['signature'],16):a for a in models if a['archive'] in ('Levels/Common.san.cooked','Levels/RatchetCommon.san.cooked')}
    byname=collections.defaultdict(list)
    for a in models:byname[a['name'].lower()].append(a)
    warnings=[];draw=[];hidden=0
    for n in nodes:
        a=local.get(n['geometryHash']) or shared.get(n['geometryHash'])
        if not a:warnings.append(f"Missing geometry {n['geometryHash']:08x}: {n['name']}");continue
        n['matrix']=world(n);n['modelId']=a['id'];n['group']=layer(n['name']+' '+a['name'])
        if not n['flags']&1:n['group']='Inactive / templates';hidden+=1
        if n['parentPartHash']:warnings.append('Bone-parented instance shown at parent origin: '+n['name'])
        draw.append(n)
    mobys,report=gameplay(root,row,assets)
    for n in mobys:
        choices=byname.get(n.pop('modelName').lower(),[])
        choices=sorted(choices,key=lambda a:(a['archive']!=row['archive'],a['archive'] not in ('Levels/Common.san.cooked','Levels/RatchetCommon.san.cooked'),not a['archive'].startswith('Actors/'),a['archive']))
        if not choices:warnings.append('Missing moby geometry: '+n['name']);continue
        # Same-level definitions take priority; do not borrow geometry from another level.
        choices=[a for a in choices if a['archive']==row['archive'] or a['archive'] in ('Levels/Common.san.cooked','Levels/RatchetCommon.san.cooked') or a['archive'].startswith('Actors/')]
        if not choices:warnings.append('Moby has no local/shared definition: '+n['name']);continue
        n['modelId']=choices[0]['id'];draw.append(n)
    binary=bytearray();geometry={};materials=[];materialids={}
    for key in dict.fromkeys(n['modelId'] for n in draw):
        model=model_loader(key);parts=[]
        for mesh in model['meshes']:
            if mesh['lod']!=0:continue
            mat=model['materials'][mesh['material']];tex=mat.get('textureUrl');mk=json.dumps(mat,sort_keys=True,separators=(',',':'))
            if mk not in materialids:materialids[mk]=len(materials);materials.append(dict(mat))
            pos=mesh['positions'];normals=mesh.get('normals');indices=mesh['indices']
            if not normals:
                normals=[[0.,0.,0.] for _ in pos]
                for i in range(0,len(indices),3):
                    ids=indices[i:i+3];a,b,c=[pos[j] for j in ids];u=[b[k]-a[k] for k in range(3)];v=[c[k]-a[k] for k in range(3)];normal=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
                    for j in ids:
                        for k in range(3):normals[j][k]+=normal[k]
                normals=[[v/(math.sqrt(sum(x*x for x in n)) or 1) for v in n] for n in normals]
            alphas=mesh.get('alphas') or [1]*len(pos)
            data=array.array('f',(v for i,p in enumerate(pos) for v in (*p,*normals[i],*mesh['uvs'][i],*mesh['colors'][i],alphas[i])))
            vo=len(binary);binary.extend(data.tobytes());io=len(binary);binary.extend(array.array('I',indices).tobytes())
            parts.append(dict(vertexOffset=vo,indexOffset=io,count=len(indices),material=materialids[mk],bakedLighting=mesh.get('bakedLighting',False),sceneLighting=bool(mesh.get('normals')) and not mesh.get('bakedLighting',False)))
        geometry[key]=dict(parts=parts,bounds=model['bounds'],name=model['name'])
    low=[math.inf]*3;high=[-math.inf]*3
    for n in draw:
        if n['group'] in ('Skybox','Inactive / templates'):continue
        bounds=geometry[n['modelId']]['bounds'];m=n['matrix']
        for p in itertools.product(*zip(*bounds)):
            v=[sum(m[j*4+k]*p[j] for j in range(3))+m[12+k] for k in range(3)]
            for k in range(3):low[k]=min(low[k],v[k]);high[k]=max(high[k],v[k])
    if not all(math.isfinite(v) for v in low+high):low=[-10,-10,-10];high=[10,10,10]
    report.update(cookedInstances=len(nodes),hiddenTemplates=hidden,placedMobys=sum(n['source']=='BOG' for n in draw),drawInstances=len(draw),uniqueModels=len(geometry),binaryBytes=len(binary))
    return dict(version=2,vertexStride=48,name=row['name'],nodes=draw,geometry=geometry,materials=materials,lights=lights(scene),bounds=[low,high],groups=dict(collections.Counter(n['group'] for n in draw)),report=report,warnings=warnings),binary
