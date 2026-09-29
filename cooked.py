"""SAC APE cooked IFF reader. See FORMAT_NOTES.md for loader evidence."""
import math
import struct
from functools import lru_cache
from pathlib import Path
from models import bounds, u32, f32


def chunks(b, start=8, end=None):
    end = len(b) if end is None else end
    while start < end:
        bounds(b, start, 8)
        size = u32(b, start+4)+4
        if size < 8 or start+size > end:
            raise ValueError('Invalid IFF chunk bounds')
        yield b[start:start+4].decode('ascii'), start, size
        start += size


def children(b, p, size):
    return {tag: (off+8, n-8) for tag, off, n in chunks(b, p+8, p+size)}


def string(b):
    return b.split(b'\0', 1)[0].decode('ascii', 'replace')


def floats(words):
    return struct.unpack('<'+'f'*len(words), struct.pack('<'+'I'*len(words), *[w & 0xffffffff for w in words]))


def packets(b, start, size):
    """VIF UNPACK streams, including STROW/STMOD fixed-point reconstruction."""
    bounds(b, start, size)
    p, end, group, row, mode = start, start+size, [], [0]*4, 0
    while p < end:
        word = u32(b, p); p += 4
        cmd, n, imm = (word>>24)&127, (word>>16)&255, word&65535
        if cmd & 0x60 == 0x60:
            n = n or 256
            components, bits = ((cmd>>2)&3)+1, (32,16,8,5)[cmd&3]
            length = n*2 if bits==5 else n*components*bits//8
            if p+length > end: raise ValueError('Truncated VIF UNPACK')
            if bits==5:
                values=[((v&31)*8,((v>>5)&31)*8,((v>>10)&31)*8,(v>>15)*128) for (v,) in struct.iter_unpack('<H',b[p:p+length])]
            else:
                fmt = {32:'I',16:'H' if imm&0x4000 else 'h',8:'B' if imm&0x4000 else 'b'}[bits]
                values = list(struct.iter_unpack('<'+fmt*components, b[p:p+length]))
            group.append(dict(address=imm&1023, bits=bits, components=components, values=values, row=row[:], mode=mode))
            p += (length+3)&~3
        elif cmd in (0x14,0x15,0x17):
            if group: yield group
            group = []
        elif cmd == 0x30:
            row = list(struct.unpack_from('<4I', b, p)); p += 16
        elif cmd == 5: mode = imm
        elif cmd in (0x20,0x31,0x4a,0x50,0x51):
            p += 4 if cmd==0x20 else 16 if cmd==0x31 else (n or 256)*8 if cmd==0x4a else imm*16
        elif cmd not in (0,1,2,3,4,6,7,0x10,0x11,0x13):
            raise ValueError(f'Unsupported VIF command {cmd:02x}')
        if p>end: raise ValueError('VIF command exceeds display list')
    if group: yield group


def multiply(a, b):
    return [sum(a[k*4+r]*b[c*4+k] for k in range(4)) for c in range(4) for r in range(4)]


def inverse(a):
    rows=[[a[c*4+r] for c in range(4)]+[float(r==c) for c in range(4)] for r in range(4)]
    for c in range(4):
        pivot=max(range(c,4),key=lambda r:abs(rows[r][c]))
        rows[c],rows[pivot]=rows[pivot],rows[c]
        d=rows[c][c]
        if abs(d)<1e-12: raise ValueError('Singular bone matrix')
        rows[c]=[x/d for x in rows[c]]
        for r in range(4):
            if r!=c:
                d=rows[r][c];rows[r]=[x-d*y for x,y in zip(rows[r],rows[c])]
    return [rows[r][c+4] for c in range(4) for r in range(4)]


def decompose(m):
    scale=[math.sqrt(sum(m[c*4+r]**2 for r in range(3))) for c in range(3)]
    a=[[m[c*4+r]/(scale[c] or 1) for c in range(3)] for r in range(3)]
    tr=sum(a[i][i] for i in range(3))
    if tr>0:
        s=math.sqrt(tr+1)*2
        q=[(a[2][1]-a[1][2])/s,(a[0][2]-a[2][0])/s,(a[1][0]-a[0][1])/s,s/4]
    else:
        i=max(range(3),key=lambda i:a[i][i]);j=(i+1)%3;k=(i+2)%3
        s=math.sqrt(max(0,1+a[i][i]-a[j][j]-a[k][k]))*2
        q=[0.0]*4;q[i]=s/4;q[j]=(a[j][i]+a[i][j])/s;q[k]=(a[k][i]+a[i][k])/s;q[3]=(a[k][j]-a[j][k])/s
    return dict(rotation=q,scale=scale,translation=m[12:15])


class Scene:
    def __init__(self, b):
        if b[:4]!=b'FORM' or u32(b,4)+4!=len(b): raise ValueError('Not a cooked FORM')
        self.b=b; self.records=list(chunks(b));self.meshes={};self.materials={};self.textures=[];self.geometries=[];self.animations=[]
        self.buffers={};library=None
        for tag,p,n in self.records:
            if tag=='COOK':
                for q in range(p+12,p+n,12):
                    kind,offset,size=struct.unpack_from('<III',b,q);self.buffers[kind]=(offset,size)
            elif tag=='TBLK':self.block=p+8
            elif tag=='TEXR':
                ch=children(b,p,n);h,_=ch['TXRH'];self.textures.append(dict(offset=p,size=n,signature=f'{u32(b,h+1):08x}',name=string(b[h+12:h+43]),width=struct.unpack_from('<H',b,h+5)[0],height=struct.unpack_from('<H',b,h+7)[0]))
            elif tag=='MATL':
                ch=children(b,p,n);h,_=ch['MTLH'];self.materials[u32(b,h+21)]=dict(name=string(b[h+25:h+56]),textureSignature=f'{u32(b,h+1):08x}')
            elif tag=='MESH':
                ch=children(b,p,n);h,_=ch['MSHH'];self.meshes[u32(b,h+17)]=(p,n)
            elif tag=='GEOB':
                ch=children(b,p,n);h,_=ch['GEOH'];self.geometries.append(dict(offset=p,size=n,name=string(b[h+37:h+68]),signature=f'{u32(b,h+25):08x}',geometryHash=u32(b,h+25),libraryHash=u32(b,h+29),skinned='SKEL' in ch))
            elif tag=='ALIB':library=u32(b,p+9)
            elif tag=='ALIE':library=None
            elif tag=='ANIM':self.animations.append(dict(offset=p,size=n,libraryHash=library))
        for off,size in self.buffers.values():bounds(b,self.block+off,size)

    def skeleton(self, p, n):
        b=self.b;ch=children(b,p,n);h,_=ch['SKHD'];count=struct.unpack_from('<H',b,h+1)[0];q,size=ch['BONS']
        if size!=count*76:raise ValueError('Unexpected BONS stride')
        result=[];world=[];ids={}
        for i in range(count):
            t=q+i*76;key,parent=struct.unpack_from('<II',b,t);forward,up,pos=[list(struct.unpack_from('<3f',b,t+j)) for j in (8,20,32)]
            right=[up[1]*forward[2]-up[2]*forward[1],up[2]*forward[0]-up[0]*forward[2],up[0]*forward[1]-up[1]*forward[0]]
            matrix=[*forward,0,*right,0,*up,0,*pos,1]
            parent_index=ids.get(parent,-1)
            local=multiply(inverse(world[parent_index]),matrix) if parent_index>=0 else matrix
            result.append(dict(name=string(b[t+44:t+76]),hash=key,parent=parent_index,inverseBind=inverse(matrix),**decompose(local)))
            ids[key]=i;world.append(matrix)
        return result

    def model(self, offset):
        b=self.b;geo=next(x for x in self.geometries if x['offset']==offset);p,n=geo['offset'],geo['size'];ch=children(b,p,n)
        skel=self.skeleton(ch['SKEL'][0]-8,ch['SKEL'][1]+8) if 'SKEL' in ch else None
        meshes=[];materials=[];material_ids={};lods=[]
        for lod,(_,q,sz) in enumerate(x for x in chunks(b,p+8,p+n) if x[0]=='GLOD'):
            mesh_key=u32(b,q+9)
            if mesh_key not in self.meshes:raise ValueError(f'Missing mesh {mesh_key:08x}')
            mp,mn=self.meshes[mesh_key];start=len(meshes)
            for tag,sp,sn in chunks(b,mp+8,mp+mn):
                if tag!='SMSH':continue
                sub=children(b,sp,sn);h,hs=sub['MHDR']
                if b[h]!=3:raise ValueError('Unsupported submesh header')
                material=u32(b,h+6)
                if material not in material_ids:
                    material_ids[material]=len(materials);materials.append(self.materials.get(material,dict(name=f'{material:08x}',textureSignature=None)))
                mat=material_ids[material];vis=b[h+18];off,size=struct.unpack_from('<II',b,h+19)
                palette=list(struct.unpack_from('<64H',b,sub['MPAL'][0])) if 'MPAL' in sub else []
                if size:
                    for packet in packets(b,self.block+self.buffers[1][0]+off,size):
                        decoded=self.packet(packet,palette,skel)
                        if decoded:meshes.append(dict(**decoded,material=mat,lod=lod,part=vis))
                elif 'MVTX' in sub:
                    decoded=self.raw_mesh(sub,h,hs,palette,skel)
                    if decoded:meshes.append(dict(**decoded,material=mat,lod=lod,part=vis))
            lods.append(dict(level=lod,meshStart=start,meshCount=len(meshes)-start))
        verts=[v for m in meshes if m['lod']==0 for v in m['positions']]
        if not verts:raise ValueError('No drawable mesh vertices')
        if not all(math.isfinite(x) and abs(x)<1e7 for v in verts for x in v):raise ValueError('Invalid coordinates')
        return dict(format='SAC APE cooked',name=geo['name'],materials=materials,meshes=meshes,lods=lods,defaultLod=0,skeleton=skel,skeletonScale=1,upAxis='y',bounds=[list(map(min,zip(*verts))),list(map(max,zip(*verts)))],vertexCount=sum(len(m['positions']) for m in meshes),triangleCount=sum(len(m['indices'])//3 for m in meshes))

    def packet(self, packet, palette, skel):
        streams={x['address']:x for x in packet}
        if 0 not in streams or len(streams[0]['values'])!=2:return None
        header=streams[0]['values'];position=streams.get(4)
        if not position or position['components']!=3:raise ValueError('Unknown packet positions')
        values=position['values']
        if position['bits']==32:positions=[list(floats(v)) for v in values]
        elif position['mode']==1:
            bias=floats([header[1][3]])[0]
            positions=[[x+bias for x in floats([v[i]+position['row'][i] for i in range(3)])] for v in values]
        else:raise ValueError('Unknown quantized positions')
        uv=streams.get(2);normal=streams.get(3)
        if not uv or len(uv['values'])!=len(values) or (normal and len(normal['values'])!=len(values)):raise ValueError('Packet attribute count mismatch')
        uvs=[[v[0]/4096,v[1]/4096] for v in uv['values']]
        skin=bool(palette and skel and uv['components']==3)
        adc=[v[-1]&0x8000 for v in normal['values']] if skin else [v[3]&0x8000 for v in uv['values']] if uv['components']==4 else [not(v[1]&1) for v in uv['values']]
        indices=[]
        for i in range(2,len(values)):
            if not adc[i]:indices.extend([i-2,i-1,i] if i%2==0 else [i-1,i-2,i])
        result=dict(positions=positions,uvs=uvs,colors=[[1,1,1] for _ in values],indices=indices)
        if skin:
            weights=[]
            for a,c in zip(uv['values'],normal['values']):
                w=(a[2]&0xff00)/32768;i=(a[2]&255)//4;j=(c[3]&255)//4
                if i>=len(palette) or j>=len(palette) or palette[i]>=len(skel) or palette[j]>=len(skel):raise ValueError('Bone palette index out of range')
                row=[0.0]*len(palette);row[i]+=w;row[j]+=1-w;weights.append(row)
            # Unused palette entries are 0xffff; zero-weight slots map harmlessly to root.
            result.update(joints=[v if v<len(skel) else 0 for v in palette],weights=weights)
        return result

    def raw_mesh(self, sub, h, hs, palette, skel):
        b=self.b;count=struct.unpack_from('<H',b,h+1)[0];decl=[]
        for p in range(h+27,h+hs-9,10):decl.append(struct.unpack_from('<6BI',b,p))
        vertex,vsize=sub['MVTX'];attrs={}
        for usage,index,typ,components,fract,stride,offset in decl:
            if usage not in (0,1,2,5,9):continue
            fmt={0:'f',2:'B',3:'h',4:'B'}.get(typ)
            if fmt is None:raise ValueError(f'Unsupported vertex declaration {typ}')
            rows=[]
            for i in range(count):
                p=vertex+i*stride+offset;length=struct.calcsize(fmt)*components
                if p+length>vertex+vsize:raise ValueError('Raw vertex exceeds buffer')
                v=list(struct.unpack_from('<'+fmt*components,b,p));rows.append(v)
            attrs[usage]=rows
        if 0 not in attrs:raise ValueError('No raw positions')
        ip,isz=sub['MIDX'];ids=list(struct.unpack_from('<'+'H'*(isz//2),b,ip));tri=[]
        for i in range(2,len(ids)):
            t=ids[i-2:i+1]
            if len(set(t))==3:tri.extend(t if i%2==0 else t[::-1])
        if any(i>=count for i in tri):raise ValueError('Raw mesh index out of bounds')
        result=dict(positions=attrs[0],uvs=attrs.get(5,[[0,0]]*count),colors=[[1,1,1]]*count,indices=tri)
        if skel and 1 in attrs and 2 in attrs:
            weights=[]
            for joints,ws in zip(attrs[2],attrs[1]):
                row=[0.0]*len(palette)
                for j,w in zip(joints,ws):
                    if w:
                        if j>=len(palette) or palette[j]>=len(skel):raise ValueError('Invalid raw skin palette')
                        row[j]+=w/255
                total=sum(row)
                weights.append([w/(total or 1) for w in row])
            result.update(joints=[v if v<len(skel) else 0 for v in palette],weights=weights)
        return result


@lru_cache(maxsize=3)
def load(path):
    return Scene(Path(path).read_bytes())
