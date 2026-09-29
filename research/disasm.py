"""Local research helper; PS2 binutils is not a viewer dependency."""
import json, os, re, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
b=(ROOT/'test/sac/extracted/disc/BIN/LEVEL1.REL').read_bytes()
symbols=json.loads(Path(__file__).with_name('museum-symbols.json').read_text())
names={s['value']:s['name'] for s in symbols if s['linkage']!=1}
env=dict(os.environ);env['PATH']='C:/msys64/mingw64/bin;C:/msys64/usr/bin;'+env['PATH']
start=int(sys.argv[1],16);end=int(sys.argv[2],16)
out=subprocess.check_output(['C:/ps2dev/ee/bin/mips64r5900el-ps2-elf-objdump.exe','-D','-b','binary','-m','mips:5900','-EL',f'--start-address={start}',f'--stop-address={end}',str(ROOT/'test/sac/extracted/disc/BIN/LEVEL1.REL')],env=env).decode()
regs={}
for line in out.splitlines():
 m=re.match(r'\s*([a-f0-9]+):\s+([a-f0-9]{8})\s',line)
 if m:
  addr=int(m[1],16);w=int(m[2],16);op=w>>26;rt=(w>>16)&31;rs=(w>>21)&31;imm=w&65535
  if addr in names:print('\n'+names[addr]+':')
  if op==15:regs[rt]=imm<<16
  elif op==9 and rs in regs:
   p=(regs[rs]+(imm if imm<32768 else imm-65536))&0xffffffff;regs[rt]=p
   if p<len(b):
    text=b[p:p+96].split(b'\0')[0]
    if len(text)>2 and all(32<=c<127 for c in text):line+='  # '+text.decode()
  elif op in (2,3):line+='  # '+names.get((w&0x3ffffff)*4,'')
 print(line)
