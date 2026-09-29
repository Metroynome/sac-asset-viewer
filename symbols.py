"""Named SAC REL linkage symbols and ELF symbol tables (module-relative REL values)."""
import struct
from models import bounds, u32


def string(b,p):
    bounds(b,p,1);end=b.find(b'\0',p,min(p+4096,len(b)))
    if end<0:raise ValueError('Unterminated symbol name')
    return b[p:end].decode('ascii')


def decode(b):
    if b[:4]==b'SNR2':
        table,count=u32(b,12),u32(b,16);bounds(b,table,count*12);rows=[]
        for i in range(count):
            name,value,a,c,kind,done=struct.unpack_from('<IIBBBB',b,table+i*12)
            if not name:continue
            text=string(b,name)
            if not text and kind==0:continue
            if kind not in (1,2,3,4):raise ValueError('Unknown REL linkage')
            rows.append(dict(name=text,value=value,address=f'0x{value:08x}',linkage=kind,index=i))
        return dict(format='SNR2',addressBasis='Module-relative values; linkage 1 entries are imports, not function addresses.',symbols=rows)
    if b[:6]!=b'\x7fELF\x01\x01':raise ValueError('Not a supported code binary')
    shoff=u32(b,32);size,count=struct.unpack_from('<HH',b,46);bounds(b,shoff,size*count)
    sections=[struct.unpack_from('<10I',b,shoff+i*size) for i in range(count)];rows=[]
    for s in sections:
        if s[1] not in (2,11):continue
        if s[9]<16 or s[6]>=len(sections):raise ValueError('Invalid ELF symbol table')
        st=sections[s[6]];text=b[st[4]:st[4]+st[5]];bounds(b,s[4],s[5])
        for p in range(s[4],s[4]+s[5],s[9]):
            name,value,n,info,other,index=struct.unpack_from('<IIIBBH',b,p)
            if name:rows.append(dict(name=string(text,name),value=value,address=f'0x{value:08x}',size=n,type=info&15,section=index))
    return dict(format='ELF32',addressBasis='ELF virtual addresses for defined symbols.',symbols=rows)
