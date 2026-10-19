'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {webcrypto,createHmac}=require('node:crypto');
const config={cwd:'/gateway-b',request:'request.json',response:'response.json',token:'fixture',generation:'generation-b',inspectionMarker:'current-attempt',reconnect:true,connectorRevision:5};
const source=fs.readFileSync('bridge/clients/claude/connector.js','utf8').replace('__BRIDGE_CONFIG__',JSON.stringify(config));
function fixture(old,ownerCwd='/gateway-a'){
 let stopped=0,writes=0,starts=0,errors=[];
 const payload=JSON.stringify({generation:config.generation,type:'idle',seq:0});
 const envelope=JSON.stringify({payload,signature:createHmac('sha256',config.token).update(payload).digest('hex')});
 const api={
  async getAll(){return [{sessionId:'legacy-session',cwd:ownerCwd,title:'Codex Bridge Connector'}];},
  async readFileAtCwd(){return {contents:envelope};},
  async writeSessionFile(){writes++;return {hash:'fixture'};},
  async start(){starts++;return {sessionId:'new-session'};}
 };
 const window={'claude.web':{LocalSessions:api},__claudeMobileBridge:{
  status:()=>old,stop(){stopped++;},...(old?.owns?{owns:old.owns}:{}),
  ...(old?.handoff?{handoff:old.handoff}:{})}};
 const context={window,crypto:webcrypto,TextEncoder,Uint8Array,Date,setTimeout,clearTimeout,console:{info(){},error(message){errors.push(message);}}};
 return {window,run:()=>vm.runInNewContext(source,context),counts:()=>({stopped,writes,starts}),errors};
}
for(const [name,status] of [
 ['live foreign legacy owner',{transport:'file',stopped:false,busy:false,sessionId:'legacy-session',lastWrite:Date.now()}],
 ['stale foreign legacy owner',{transport:'file',stopped:false,busy:false,sessionId:'legacy-session',lastWrite:1}],
 ['live foreign current owner',{transport:'file',stopped:false,busy:false,owns:()=>false,lastWrite:Date.now()}],
 ['unknown legacy owner',{transport:'file',stopped:false,busy:false,sessionId:'missing',lastWrite:Date.now()}]
])test(name+' remains intact and reports a one-time migration boundary',async()=>{
 const ui=fixture(status);
 await assert.rejects(ui.run(),/旧版 Claude 桥接无法核验在途请求/);
 assert.deepEqual(ui.counts(),{stopped:0,writes:0,starts:0});
 assert.match(ui.window.__codingRemoteInjectionError,/当前任务结束后重新加载或退出重开 Claude Desktop/);
 assert.match(ui.errors.at(-1),/BRIDGE_OWNER_LEGACY.*\[current-attempt\]/);
});
test('same-workspace legacy with complete execution status may be replaced without exposing its token',async()=>{
 const ui=fixture({transport:'file',stopped:false,suspended:false,busy:false,writing:false,sessionId:'legacy-session',lastWrite:Date.now()},config.cwd);
 const running=ui.run();
 for(let i=0;i<50&&!ui.window.__claudeMobileBridge?.owns;i++)await new Promise(resolve=>setTimeout(resolve,10));
 assert.equal(ui.counts().stopped,1);assert.equal(ui.window.__claudeMobileBridge.owns(config.cwd),true);
 assert.equal(ui.window.__claudeMobileBridge.owns('/gateway-a'),false);
 assert.ok(!JSON.stringify(ui.window.__claudeMobileBridge.status()).includes(config.token));
 ui.window.__claudeMobileBridge.stop();await running;
});
test('pending request or response write blocks even same-owner replacement',async()=>{
 for(const field of ['busy','writing']){
  const ui=fixture({transport:'file',stopped:false,sessionId:'legacy-session',[field]:true},config.cwd);
  await assert.rejects(ui.run(),/请求进行中/);
  assert.equal(ui.counts().stopped,0);
 }
});
test('legacy stopped flag alone does not prove a signed release',async()=>{
 const ui=fixture({transport:'file',stopped:true,busy:false,sessionId:'legacy-session'});
 await assert.rejects(ui.run(),/旧版 Claude 桥接无法核验在途请求/);
 assert.equal(ui.counts().stopped,0);
});
test('revision-5 timeout leaves an unknown mutation behind identical signed stop and closed receipt',async()=>{
 const oldToken='synthetic-old-token';
 const signed=value=>{const payload=JSON.stringify(value);return JSON.stringify({payload,
  signature:createHmac('sha256',oldToken).update(payload).digest('hex')});};
 const request=signed({generation:'old-generation',seq:334,type:'stop'});
 const response=signed({generation:'old-generation',seq:333,done:true,connected:false,connectorRevision:5});
 assert.equal(JSON.parse(response).signature.length,64);
 assert.equal(JSON.parse(request).signature.length,64);
 for(const hiddenMutation of [false,true]){
  // Distilled from the installed revision-5 closure: bounded(operation) can
  // time out and clear busy while the underlying Desktop promise continues.
  let busy=false,finish,completed=0;
  if(hiddenMutation){
   busy=true;
   const operation=new Promise(resolve=>{finish=()=>{completed++;resolve();};});
   const result=await Promise.race([operation.then(()=>true),new Promise(resolve=>setTimeout(()=>resolve(false),0))]);
   assert.equal(result,false);
   busy=false; // revision-5 bounded(...).finally, not operation.finally
  }
  // A later signed idle generation resets the single response slot. Its
  // completed seq 333 and signed stop seq 334 conceal the older operation.
  const ui=fixture({transport:'file',stopped:false,busy,sessionId:'legacy-session',lastWrite:Date.now()},config.cwd);
  await assert.rejects(ui.run(),/无法核验在途请求/);
  assert.deepEqual(ui.counts(),{stopped:0,writes:0,starts:0});
  assert.match(ui.errors.at(-1),/BRIDGE_OWNER_LEGACY.*\[current-attempt\]/);
  assert.equal(completed,0);
  finish?.();await Promise.resolve();
  assert.equal(completed,hiddenMutation?1:0);
 }
});
test('a handoff method with a different protocol revision is not trusted',async()=>{
 let calls=0;
 const ui=fixture({transport:'file',sessionId:'legacy-session',connectorRevision:4,
                   handoff(){calls++;return true;}});
 await assert.rejects(ui.run(),/旧版 Claude 桥接无法核验在途请求/);
 assert.equal(calls,0);
 assert.equal(ui.counts().stopped,0);
});
