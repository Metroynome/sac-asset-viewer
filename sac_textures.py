"""SAC cooked PS2 base textures and simple BMP/TGA previews."""
import struct
from cooked import children
from models import bounds, u32


def texture(scene, record):
    b=scene.b;ch=children(b,record['offset'],record['size']);p,_=ch['TPS2']
    w,h=record['width'],record['height']
    if not 0<w<=4096 or not 0<h<=4096:raise ValueError('Invalid texture dimensions')
    base=scene.block+scene.buffers[2][0];off=u32(b,p+32);paloff=u32(b,p+96);psm=b[p+117]
    count=w*h;rgba=bytearray()
    if psm in (19,20):
        n=count if psm==19 else (count+1)//2;bounds(b,base+off,n)
        palcount=256 if psm==19 else 16;bounds(b,base+paloff,palcount*4)
        data=b[base+off:base+off+n];palette=b[base+paloff:base+paloff+palcount*4]
        for i in range(count):
            v=data[i] if psm==19 else (data[i//2]>>(4*(i%2)))&15
            if psm==19:v=(v&~24)|((v&8)<<1)|((v&16)>>1)
            r,g,bl,a=palette[v*4:v*4+4];rgba.extend((r,g,bl,min(255,a*2)))
    elif psm==0:
        bounds(b,base+off,count*4)
        for r,g,bl,a in struct.iter_unpack('<4B',b[base+off:base+off+count*4]):rgba.extend((r,g,bl,min(255,a*2)))
    else:raise ValueError(f'Unsupported PS2 texture PSM {psm}')
    return w,h,rgba
