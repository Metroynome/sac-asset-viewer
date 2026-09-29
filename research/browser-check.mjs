import fs from 'node:fs/promises';
const pages=await (await fetch('http://127.0.0.1:9225/json/list')).json();
const target=pages.find(p=>p.type==='page');
const ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
let id=0;const pending=new Map();
ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const [resolve,reject]=pending.get(m.id)||[];pending.delete(m.id);if(resolve)m.error?reject(m.error):resolve(m.result);}};
const send=(method,params={})=>new Promise((r,j)=>{pending.set(++id,[r,j]);ws.send(JSON.stringify({id,method,params}));});
await send('Runtime.enable');await send('Page.enable');
if(process.argv[2]==='navigate')await send('Page.navigate',{url:process.argv[3]});
else if(process.argv[2]==='screenshot'){
 const {data}=await send('Page.captureScreenshot',{format:'png'});await fs.writeFile(process.argv[3],Buffer.from(data,'base64'));
}else{
 const r=await send('Runtime.evaluate',{expression:process.argv[3],awaitPromise:true,returnByValue:true});console.log(JSON.stringify(r));
}
ws.close();
