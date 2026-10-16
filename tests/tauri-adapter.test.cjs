'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../desktop/tauri-bridge.js'),'utf8');
test('Tauri exposes every existing desktop method and passes payloads without HTTP',async()=>{
  const preload=fs.readFileSync(path.join(__dirname,'../desktop/preload.cjs'),'utf8');
  const expected=[...preload.matchAll(/^  (\w+):/gm)].map(m=>m[1]).sort();
  const calls=[],window={__TAURI__:{core:{invoke:async(command,args)=>{calls.push({command,args});return {ok:true};}}}};
  vm.runInNewContext(source,{window});
  assert.deepEqual(Object.keys(window.bridgeDesktop).sort(),expected);
  await window.bridgeDesktop.accounts({action:'list',entry:'wsl:fixture'});
  assert.equal(calls[0].command,'bridge');
  assert.equal(calls[0].args.action,'accounts');
  assert.equal(calls[0].args.payload.entry,'wsl:fixture');
  assert.equal(Object.isFrozen(window.bridgeDesktop),true);
  assert.equal(Object.getOwnPropertyDescriptor(window,'bridgeDesktop').writable,false);
});
test('Tauri errors preserve user-facing messages without resending a write',async()=>{
  let attempts=0;
  const window={__TAURI__:{core:{invoke:async()=>{attempts++;throw '操作结果未知';}}}};
  vm.runInNewContext(source,{window});
  await assert.rejects(window.bridgeDesktop.start(),error=>error.message==='操作结果未知');
  assert.equal(attempts,1);
});
