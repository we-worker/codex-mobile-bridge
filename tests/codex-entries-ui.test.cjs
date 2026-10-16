'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function fixture(){
  const node=()=>({children:[],dataset:{},value:'',textContent:'',hidden:false,disabled:false,setAttribute(){},append(...v){this.children.push(...v);},replaceChildren(...v){this.children=[...v];}});
  const calls=[],changes=[],errors=[],root=node();let reply=()=>({entries:[]});
  const context=vm.createContext({document:{createElement:node},BridgeI18n:{t:v=>v}});
  vm.runInContext(fs.readFileSync('web/features/clients/client-navigation.js','utf8'),context);
  const C=vm.runInContext('CodexEntries',context),entry=new C({root,request:async(path,body)=>{calls.push({path,body});return reply(body);},onChange:v=>changes.push(v),notify:v=>errors.push(v)});
  return {entry,calls,changes,errors,setReply:v=>reply=v};
}
const candidate={id:'wsl:fixture',kind:'wsl-cli',label:'WSL <script>fixture</script>',enabled:false,running:true};
test('entry inventory is passive and only explicit connect registers the discovered ID',async()=>{
 const ui=fixture();ui.setReply(body=>({entries:[{id:'desktop',kind:'desktop',label:'桌面 Codex',enabled:true,running:true},{...candidate,enabled:body?.action==='configure'}]}));
 await ui.entry.refresh();assert.equal(ui.calls[0].body,undefined);assert.equal(ui.entry.options.children[0].children[0].textContent,candidate.label);
 await ui.entry.refresh(true);assert.deepEqual(JSON.parse(JSON.stringify(ui.calls[1].body)),{action:'scan'});
 await ui.entry.options.children[0].children[1].onclick();assert.deepEqual(JSON.parse(JSON.stringify(ui.calls[2].body)),{action:'configure',id:'wsl:fixture',enabled:true});
 ui.entry.select.value='wsl:fixture';ui.entry.select.onchange();assert.equal(ui.changes.at(-1),'wsl:fixture');
});
test('logout and a stale scan cannot restore an entry or change the selected target',async()=>{
 const ui=fixture();let finish;ui.setReply(()=>new Promise(resolve=>finish=resolve));const scanning=ui.entry.refresh(true);ui.entry.clear();finish({entries:[candidate]});await scanning;
 assert.equal(ui.entry.options.children.length,0);assert.equal(ui.entry.value,'');assert.equal(ui.errors.length,0);
});
test('disabled selection resets and unsupported hosts do not advertise WSL scanning',()=>{
 const ui=fixture();ui.entry.value='wsl:fixture';ui.entry.render({entries:[candidate],wslSupported:false});
 assert.equal(ui.entry.value,'');assert.equal(ui.changes.at(-1),'');assert.equal(ui.entry.scan.hidden,true);
});
