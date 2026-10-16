'use strict';
// Exercise the built Tauri/WebView2 application using only isolated fixture data.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),net=require('node:net'),os=require('node:os');
const {spawn,spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..'),delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function port(){const server=net.createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));const value=server.address().port;await new Promise(r=>server.close(r));return value;}
async function until(fn,label,timeout=45000){let error;const end=Date.now()+timeout;while(Date.now()<end){try{const value=await fn();if(value)return value;}catch(e){error=e;}await delay(250);}throw Error(label+' timed out'+(error?': '+error.message:''));}
async function connect(url){
  const socket=new WebSocket(url),pending=new Map();let next=0;const exceptions=[];
  socket.addEventListener('message',event=>{const value=JSON.parse(event.data);if(value.method==='Runtime.exceptionThrown')exceptions.push(value.params.exceptionDetails.text);const request=pending.get(value.id);if(!request)return;pending.delete(value.id);clearTimeout(request.timer);value.error?request.reject(Error(value.error.message)):request.resolve(value.result);});
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  function call(method,params={}){return new Promise((resolve,reject)=>{const id=++next,timer=setTimeout(()=>{pending.delete(id);reject(Error(method+' timed out'));},180000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});}
  return {call,exceptions,close:()=>socket.close(),async evaluate(expression){const result=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description||'Renderer evaluation failed');return result.result.value;}};
}

async function main(){
  assert.equal(process.platform,'win32','The native smoke test requires Windows/WebView2');
  const executable=path.resolve(process.argv[2]||'src-tauri/target/release/codex-mobile-bridge-tauri.exe');
  assert.ok(fs.existsSync(executable),'Build the Tauri application first');
  fs.mkdirSync(path.join(root,'.tmp'),{recursive:true});
  const fixture=fs.mkdtempSync(path.join(root,'.tmp','tauri-smoke-')),appDir=path.join(fixture,'app'),data=path.join(fixture,'data'),home=path.join(fixture,'codex-home');
  fs.mkdirSync(appDir);fs.mkdirSync(data);fs.mkdirSync(home);
  const staged=path.join(appDir,path.basename(executable));
  fs.copyFileSync(executable,staged);
  for(const name of fs.readdirSync(path.dirname(executable)).filter(name=>name.endsWith('.dll')))fs.copyFileSync(path.join(path.dirname(executable),name),path.join(appDir,name));
  fs.cpSync(path.join(root,'dist/gateway'),path.join(appDir,'gateway'),{recursive:true});
  const debugPort=await port(),gatewayPort=await port(),origin=`http://127.0.0.1:${gatewayPort}/`;
  const addresses=Object.values(os.networkInterfaces()).flat().filter(row=>row?.family==='IPv4'&&!row.internal);
  const lan=addresses.find(row=>/^192\.168\.|^10\./.test(row.address))||addresses[0];
  assert.ok(lan,'A real LAN address is required by the unchanged mobile pairing policy');
  const qrOrigin=`http://${lan.address}:${gatewayPort}/`;
  fs.writeFileSync(path.join(data,'desktop.json'),JSON.stringify({port:gatewayPort,lan:true,lanAddresses:[lan.address],localAccess:true,autoStart:false,codexHome:home,ipcPath:'\\\\.\\pipe\\cmb-tauri-fixture-'+path.basename(fixture),connections:[]}));
  const env={...process.env,CMB_DATA_DIR:data,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${debugPort}`};
  delete env.CMB_UPDATE_TRANSACTION;delete env.CMB_UPDATE_DATA_DIR;
  const child=spawn(staged,[],{env,cwd:appDir,windowsHide:true,stdio:'ignore'});let cdp;
  const checks=[];
  try{
    const page=await until(async()=>{if(child.exitCode!==null||child.signalCode!==null)throw Error('Native application exited: '+(child.exitCode??child.signalCode));const pages=await(await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();return pages.find(p=>p.type==='page'&&p.url.includes('/desktop/index.html'));},'Tauri local page');
    cdp=await connect(page.webSocketDebuggerUrl);await cdp.call('Runtime.enable');
    await until(()=>cdp.evaluate('typeof window.bridgeDesktop?.snapshot === "function"'),'native bridge');
    const initial=await cdp.evaluate('window.bridgeDesktop.snapshot()');
    assert.equal(initial.desktopHost,'tauri');assert.equal(path.resolve(initial.dataDir),path.resolve(data));
    assert.equal(initial.runtime.running,false);assert.equal(initial.preferences.codexHome,home);
    assert.equal(initial.update.state,'unsupported');checks.push('native WebView2, packaged Python host, isolated data and separate update channel');
    await cdp.evaluate('window.bridgeDesktop.setLanguage("en")');assert.equal(await cdp.evaluate('window.bridgeDesktop.language()'),'en');
    await cdp.evaluate('window.bridgeDesktop.setLanguage("zh-CN")');checks.push('persistent language and native title');
    const rejected=await cdp.evaluate('(async()=>{let rejected=0;for(const [action,payload] of [["exec",{}],["set-data-dir","C:/"],["open","file:///C:/Windows/System32/cmd.exe"],["copy","https://attacker.invalid/"]]){try{await window.__TAURI__.core.invoke("bridge",{action,payload});}catch{rejected++;}}return rejected;})()');
    assert.equal(rejected,4);checks.push('arbitrary process, internal commands and unapproved paths/URLs rejected');
    const saved=await cdp.evaluate('(async()=>{const s=await bridgeDesktop.snapshot();return bridgeDesktop.save({preferences:s.preferences,auth:s.auth,origins:s.origins,notifications:s.notifications});})()');
    assert.equal(saved.desktopHost,'tauri');assert.ok(!saved.validationError);checks.push('save through the persistent private owner');
    const invalid=await cdp.evaluate('(async()=>{const s=await bridgeDesktop.snapshot();return bridgeDesktop.save({preferences:{...s.preferences,port:0},auth:s.auth,origins:s.origins,notifications:s.notifications});})()');
    assert.ok(invalid.validationError?.message,'Field validation must survive the native bridge');
    assert.equal((await cdp.evaluate('bridgeDesktop.snapshot()')).preferences.port,gatewayPort);
    await cdp.evaluate('window.bridgeDesktop.start()');
    await until(async()=>{const response=await fetch(origin+'api/health');return response.ok&& (await response.json()).service==='codex-mobile-bridge';},'isolated gateway start');
    const pixels=await cdp.evaluate(`(async()=>{const grant=await bridgeDesktop.pairing({action:'create',url:${JSON.stringify(qrOrigin)}});if(grant.url)throw Error('Raw bearer URL exposed');const image=new Image();image.src=grant.image;await image.decode();const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);window.__smokeGrant=grant.id;return {width:canvas.width,height:canvas.height,pixels:Array.from(ctx.getImageData(0,0,canvas.width,canvas.height).data)};})()`);
    const decoded=require('jsqr')(new Uint8ClampedArray(pixels.pixels),pixels.width,pixels.height);
    assert.ok(decoded,'A real scanner must decode the native QR');const scanned=new URL(decoded.data);assert.equal(scanned.origin,new URL(qrOrigin).origin);assert.ok(scanned.hash.startsWith('#pair='));
    await cdp.evaluate('bridgeDesktop.pairing({action:"revoke",id:window.__smokeGrant})');checks.push('local QR renders, decodes and revokes a real isolated pairing grant');
    const log=await cdp.evaluate('window.bridgeDesktop.logs()');assert.ok(Array.isArray(log.sections));
    await cdp.evaluate('window.bridgeDesktop.stop()');await until(async()=>!(await cdp.evaluate('bridgeDesktop.snapshot()')).runtime.running,'explicit gateway stop');
    await cdp.evaluate('window.bridgeDesktop.start()');await until(async()=>(await fetch(origin+'api/health')).ok,'gateway restart');
    await delay(500);assert.deepEqual(cdp.exceptions,[],'The real desktop page must run without uncaught errors');
    const screenshot=await cdp.call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(root,'.tmp/tauri-smoke.png'),Buffer.from(screenshot.data,'base64'));
    cdp.close();cdp=null;child.kill();await until(()=>child.exitCode!==null||child.signalCode!==null,'controller exit',10000);
    assert.equal((await fetch(origin+'api/health')).ok,true);checks.push('explicit stop/restart and gateway survives controller exit');
    const result={ok:true,checks,fixture,executable};fs.writeFileSync(path.join(root,'.tmp/tauri-smoke-result.json'),JSON.stringify(result,null,2));
    for(const check of checks)console.log('PASS:',check);
  }catch(error){
    console.error('Native smoke:',error.message);
    throw error;
  }finally{
    cdp?.close();if(child.exitCode===null&&child.signalCode===null)child.kill();
    // This invokes the existing fresh identity checks for our own fixture only.
    if(fs.existsSync(path.join(data,'gateway-control.json'))){
      const stopped=spawnSync(path.join(appDir,'gateway/codex-mobile-gateway.exe'),['stop','--data-dir',data],{encoding:'utf8',timeout:30000,windowsHide:true});
      if(stopped.error||stopped.status!==0)throw Error('Isolated gateway cleanup failed: '+(stopped.error?.message||stopped.stderr||stopped.stdout));
    }
  }
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
