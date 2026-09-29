"""Secret Agent Clank asset library: cooked models, textures, animation and REL symbols."""
import argparse
import collections
import functools
import hashlib
import http.server
import json
import re
import struct
import urllib.parse
from pathlib import Path
import cooked
import sac_animation
import sac_textures
import symbols
from formats import png, gim

HERE=Path(__file__).resolve().parent
VERSION=1


def identity(source,offset,size):return hashlib.sha256(f'{source}:{offset}:{size}'.encode()).hexdigest()[:20]
def safe_name(s):return re.sub(r'[^A-Za-z0-9_.-]+','_',s)[:120]
def group(path):
    p=Path(path)
    if p.parts[0]=='Actors':return 'Characters · '+p.parts[1]
    if p.parts[0]=='Levels':return 'Shared · '+p.stem if len(p.parts)==2 else p.parts[1]
    return p.parts[0]


def build(root,out):
    out.mkdir(parents=True,exist_ok=True);assets=[];errors=[];models_by_library=collections.defaultdict(list);banks=[]
    def add(source,offset,size,name,category,archive,**extra):
        row=dict(id=identity(source,offset,size),source=source,offset=offset,size=size,name=name,category=category,archive=archive,group=group(archive),status='Raw download',**extra)
        assets.append(row);return row
    def notice(row,exc):
        row.update(status='Preview unavailable',error=str(exc));errors.append(dict(id=row['id'],name=row['name'],archive=row['archive'],error=str(exc)))
    def preview(row,w,h,rgba):
        path=Path('textures')/(row['id']+'.png');dest=out/path;dest.parent.mkdir(exist_ok=True)
        dest.write_bytes(png(w,h,rgba));row.update(width=w,height=h,preview=path.as_posix(),status='PNG preview')
    for path in sorted((root/'image').rglob('*.cooked')):
        scene=cooked.Scene(path.read_bytes());archive=path.relative_to(root/'image').as_posix();source=path.relative_to(root).as_posix()
        for tex in scene.textures:
            row=add(source,tex['offset'],tex['size'],tex['name'],'Textures',archive,format='SAC cooked texture',signature=tex['signature'])
            try:preview(row,*sac_textures.texture(scene,tex))
            except (ValueError,IndexError,struct.error) as exc:notice(row,exc)
        for geo in scene.geometries:
            row=add(source,geo['offset'],geo['size'],geo['name'],'Models',archive,format='SAC APE cooked',signature=geo['signature'],libraryHash=geo['libraryHash'],assetKind='Skinned moby' if geo['skinned'] else 'Prop / level geometry')
            try:
                model=scene.model(geo['offset']);skel=model['skeleton'] or []
                row.update(modelPreview=True,status='3D preview',vertexCount=model['vertexCount'],triangleCount=model['triangleCount'],boneCount=len(skel))
                if skel:models_by_library[geo['libraryHash']].append(row)
            except (ValueError,IndexError,struct.error,OverflowError) as exc:notice(row,exc)
        libraries=collections.defaultdict(list)
        for a in scene.animations:libraries[a['libraryHash']].append(a)
        for lib,records in libraries.items():
            start=records[0]['offset'];end=records[-1]['offset']+records[-1]['size']
            name=next((g['name'] for g in scene.geometries if g['libraryHash']==lib),f'Library {lib:08x}')
            row=add(source,start,end-start,name+' animations','Animation',archive,format='SAC APE ANIM',libraryHash=lib,clipCount=len(records))
            try:
                clips=[sac_animation.decode(scene.b,a['offset'],a['size']) for a in records]
                row.update(status='Animation bank',clipIds=[c['id'] for c in clips]);banks.append(row)
            except (ValueError,IndexError,struct.error) as exc:notice(row,exc)
        print(archive,f'{len(scene.geometries)} models, {len(scene.textures)} textures, {len(scene.animations)} clips',flush=True)
    for bank in banks:
        matches=models_by_library.get(bank['libraryHash'],[])
        if not matches:bank['error']='No skinned geometry with this animation-library hash.';continue
        same=[m for m in matches if m['archive']==bank['archive']]
        preferred=same or [m for m in matches if m['archive'].startswith('Actors/')] or matches
        bank.update(modelId=preferred[0]['id'],animationPreview=True,status='Animation preview')
        for m in matches:
            m.setdefault('animations',[]).append(dict(id=bank['id'],name=bank['group']+' · '+bank['name'],clipCount=bank['clipCount']))
    manifest=json.loads((root/'manifest.json').read_text())
    for record in manifest['archives']:
        path=root/'unpacked'/record['path']/'payload.bin';data=path.read_bytes();source=path.relative_to(root).as_posix()
        for hit in re.finditer(rb'[A-Za-z]:\\',data):
            h=hit.start()-4
            if h<0 or h%16 or h+192>len(data):continue
            name=data[h+4:h+100].split(b'\0')[0];typ,size=struct.unpack_from('<II',data,h+100)
            if not size or typ>100 or h+192+size>len(data) or any(c<32 or c>126 for c in name):continue
            source_name=name.decode();name=source_name.rsplit('\\',1)[-1];ext=Path(name).suffix.lower()
            category={'.col':'Collision','.pcol':'Collision','.bog':'Gameplay','.nav':'Navigation','.gim':'Textures'}.get(ext,'WAD assets')
            row=add(source,h+192,size,name,category,record['path'],sourceName=source_name,assetType=typ,signature=f'{cooked.u32(data,h):08x}')
            if category=='Textures':
                try:preview(row,*gim(data[h+192:h+192+size]))
                except (ValueError,IndexError,struct.error) as exc:notice(row,exc)
    for path in sorted((root/'disc').rglob('*')):
        if not path.is_file():continue
        with path.open('rb') as f:magic=f.read(4)
        if magic in (b'SNR2',b'\x7fELF'):
            row=add(path.relative_to(root).as_posix(),0,path.stat().st_size,path.name,'Code',path.relative_to(root/'disc').as_posix())
            try:
                info=symbols.decode(path.read_bytes());dest=out/'symbols'/(row['id']+'.json');dest.parent.mkdir(exist_ok=True);dest.write_text(json.dumps(info),encoding='utf-8')
                row.update(format=info['format'],symbolCount=len(info['symbols']),addressBasis=info['addressBasis'],status='Symbols + raw download',symbolFile=dest.relative_to(out).as_posix())
            except (ValueError,IndexError,struct.error,UnicodeDecodeError) as exc:notice(row,exc)
        elif path.suffix.upper() in ('.FSB','.BIK'):
            add(path.relative_to(root).as_posix(),0,path.stat().st_size,path.name,'Sound banks' if path.suffix.upper()=='.FSB' else 'Video',path.relative_to(root/'disc').as_posix())
    for path in sorted((root/'image').rglob('*')):
        if not path.is_file() or path.suffix.lower() in ('.cooked','.wad'):continue
        ext=path.suffix.lower();category='GUI images' if ext in ('.bmp','.tga','.png','.gim') else 'Scripts' if ext=='.xmb' else 'Other'
        row=add(path.relative_to(root).as_posix(),0,path.stat().st_size,path.name,category,path.relative_to(root/'image').as_posix())
        if ext=='.gim':
            try:preview(row,*gim(path.read_bytes()))
            except (ValueError,IndexError,struct.error) as exc:notice(row,exc)
        elif ext=='.png':
            target=out/'textures'/(row['id']+'.png');target.write_bytes(path.read_bytes());row.update(preview=target.relative_to(out).as_posix(),status='PNG preview')
    index=dict(version=VERSION,root=str(root),manifestSha256=hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest(),assets=assets,counts=dict(collections.Counter(a['category'] for a in assets)),errors=errors)
    (out/'index.json').write_text(json.dumps(index,ensure_ascii=False),encoding='utf-8')
    print('Indexed',len(assets),'assets;',index['counts'],'notices',len(errors),flush=True)
    return index


def serve(root,out,index,port):
    by_id={x['id']:x for x in index['assets']};textures=collections.defaultdict(list)
    for row in index['assets']:
        if row.get('preview') and row.get('signature'):textures[row['signature']].append(row)
    @functools.lru_cache(maxsize=8)
    def model_json(key):
        row=by_id[key];scene=cooked.load(str(root/row['source']));model=scene.model(row['offset']);model['animations']=row.get('animations',[]);model['assetId']=key
        model['warnings']=['Base texture layer and simple lighting. Game shader effects and animation events are not simulated.']
        for mat in model['materials']:
            choices=textures.get(mat['textureSignature'],[]);same=[x for x in choices if x['archive']==row['archive']]
            common=[x for x in choices if x['archive'] in ('Levels/Common.san.cooked','Levels/RatchetCommon.san.cooked')]
            choices=same or common or choices[:1]
            if choices:mat['textureUrl']='/asset/'+choices[0]['id']+'/png'
        return json.dumps(model,allow_nan=False,separators=(',',':')).encode()
    def animation_json(row,model_id=None):
        model=by_id[model_id or row['modelId']]
        if model.get('libraryHash')!=row['libraryHash']:raise ValueError('Animation library does not match model')
        scene=cooked.load(str(root/model['source']));geo=next(g for g in scene.geometries if g['offset']==model['offset']);ch=cooked.children(scene.b,geo['offset'],geo['size']);p,n=ch['SKEL'];skel=scene.skeleton(p-8,n+8)
        return sac_animation.bank(cooked.load(str(root/row['source'])),row['libraryHash'],skel)
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,data,kind,status=200,filename=None):
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.send_header('X-Content-Type-Options','nosniff')
            if filename:self.send_header('Content-Disposition',f'attachment; filename="{safe_name(filename)}"')
            self.end_headers()
            try:self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):pass
        def do_GET(self):
            url=urllib.parse.urlsplit(self.path);path=url.path
            try:
                if path=='/':return self.send((HERE/'web/index.html').read_bytes(),'text/html; charset=utf-8')
                if path=='/web/model-viewer.js':return self.send((HERE/'web/model-viewer.js').read_bytes(),'text/javascript; charset=utf-8')
                if path=='/api/index':return self.send(json.dumps(index,ensure_ascii=False).encode(),'application/json')
                match=re.fullmatch(r'/asset/([a-f0-9]{20})/(raw|png|info|model|animation|symbols)',path)
                if not match or match[1] not in by_id:return self.send(b'Not found','text/plain',404)
                row=by_id[match[1]];action=match[2]
                if action=='model':return self.send(model_json(row['id']),'application/json')
                if action=='animation':return self.send(json.dumps(animation_json(row,urllib.parse.parse_qs(url.query).get('model',[None])[0]),allow_nan=False).encode(),'application/json')
                if action=='png':return self.send((out/row['preview']).read_bytes(),'image/png')
                if action=='symbols':return self.send((out/row['symbolFile']).read_bytes(),'application/json',filename=row['name']+'.symbols.json' if 'download' in url.query else None)
                source=(root/row['source']).resolve();source.relative_to(root)
                with source.open('rb') as f:f.seek(row['offset']);raw=f.read(row['size'])
                if len(raw)!=row['size']:raise ValueError('Source changed; rebuild the index')
                if action=='raw':return self.send(raw,'application/octet-stream',filename=row['name'])
                detail=dict(row,hexPreview='\n'.join(f'{i:04x}  '+raw[i:i+16].hex(' ') for i in range(0,min(256,len(raw)),16)))
                if row['category']=='Animation' and row.get('modelId'):detail['clips']=[dict(name=c['name'],duration=c['duration'],tracks=len(c['tracks'])) for c in animation_json(row)['clips']]
                return self.send(json.dumps(detail,ensure_ascii=False).encode(),'application/json')
            except (ValueError,KeyError,OSError,struct.error,IndexError,OverflowError) as exc:self.send(str(exc).encode(),'text/plain',422)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'Browse http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,default=HERE.parent/'test/sac/extracted');ap.add_argument('--out',type=Path,default=HERE/'output');ap.add_argument('--port',type=int,default=8766);ap.add_argument('--rebuild',action='store_true');ap.add_argument('--build-only',action='store_true')
    args=ap.parse_args();root=args.root.resolve();out=args.out.resolve()
    if not (root/'manifest.json').is_file():ap.error('Missing SAC extraction manifest; use --root to select it')
    index=json.loads((out/'index.json').read_text(encoding='utf-8')) if (out/'index.json').is_file() else {}
    fingerprint=hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest()
    if args.rebuild or index.get('version')!=VERSION or index.get('root')!=str(root) or index.get('manifestSha256')!=fingerprint:index=build(root,out)
    if not args.build_only:serve(root,out,index,args.port)


if __name__=='__main__':main()
