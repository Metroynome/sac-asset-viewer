"""APE ANIM key streams recovered from LEVEL1.REL's named stream readers."""
import math
import struct
from models import bounds, u32, f32

TICK=struct.unpack('<f',struct.pack('<I',0x3d08882f))[0]
SEMANTICS={0x13db7:'rotation',0x13634:'translation',0x4b1112a:'scale'}
STRIDES={0:8,1:16,2:20,3:8,4:48,5:52,6:14,7:8,8:4}


def decode(b, offset, size, skeleton=None):
    end=offset+size;p=offset+8
    if b[offset:offset+4]!=b'ANIM' or b[p]!=1:raise ValueError('Unsupported APE ANIM')
    count=u32(b,p+1);p+=5;allocation=[]
    if count>10000:raise ValueError('Invalid track count')
    for _ in range(count):
        typ,n=struct.unpack_from('<II',b,p);p+=8
        extra=u32(b,p) if typ==6 else 0
        if typ==6:p+=4
        if typ not in STRIDES or n>100000:raise ValueError('Invalid track allocation')
        allocation.append((typ,n,extra))
    key,duration,second_count=struct.unpack_from('<IfI',b,p);p+=12
    if second_count!=count or not math.isfinite(duration) or not 0<=duration<10000:raise ValueError('Invalid animation header')
    headers=[struct.unpack_from('<5I',b,p+i*20) for i in range(count)];p+=count*20
    bones={x['hash']:i for i,x in enumerate(skeleton or [])};tracks=[];ignored=[]
    for header,alloc in zip(headers,allocation):
        typ,obj,part,semantic,n=header
        if (typ,n)!=alloc[:2]:raise ValueError('Animation allocation mismatch')
        stride=STRIDES[typ];bounds(b,p,n*stride)
        frames=[];channel=SEMANTICS.get(semantic)
        for i in range(n):
            q=p+i*stride;frame={}
            if typ==3:
                tick,x,y,z=struct.unpack_from('<4H',b,q)
                xyz=[v*2/65535-1 for v in (x,y,z)]
                frame=dict(time=tick*TICK,rotation=xyz+[math.sqrt(max(0,1-sum(v*v for v in xyz)))])
            elif typ==7:
                tick,x,y,z=struct.unpack_from('<4H',b,q);frame=dict(time=tick*TICK,translation=[v/4096-8 for v in (x,y,z)])
            elif typ==8:
                tick,x,y,z=b[q:q+4];frame=dict(time=tick*TICK,scale=[v/64 for v in (x,y,z)])
            elif typ in (1,2,6):
                time=f32(b,q) if typ!=6 else struct.unpack_from('<H',b,q)[0]*TICK
                values=list(struct.unpack_from('<'+('4f' if typ==2 else '3f'),b,q+(2 if typ==6 else 4)))
                if channel:frame=dict(time=time,**{channel:values})
            if frame and channel in frame:
                if not all(math.isfinite(v) for v in [frame['time'],*frame[channel]]):raise ValueError('Nonfinite animation value')
                if frames and frame['time']<frames[-1]['time']:raise ValueError('Nonmonotonic animation track')
                frames.append(frame)
        p+=n*stride+alloc[2]*8
        if part in bones and frames:tracks.append(dict(bone=bones[part],frames=frames))
        elif skeleton is None and frames:tracks.append(dict(boneHash=part,frames=frames))
        else:ignored.append(dict(type=typ,objectHash=obj,boneHash=part,semanticHash=semantic,keys=n))
    if p>end or any(b[p:end]):raise ValueError(f'Animation size mismatch: {p-offset}/{size}')
    return dict(name=f'Clip {key}',id=key,duration=duration,tracks=tracks,ignoredTracks=ignored)


def bank(scene, library, skeleton):
    clips=[decode(scene.b,a['offset'],a['size'],skeleton) for a in scene.animations if a['libraryHash']==library]
    return dict(format='SAC APE ANIM',clips=clips,maxBone=max((t['bone'] for c in clips for t in c['tracks']),default=-1))
