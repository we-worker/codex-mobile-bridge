'use strict';
if(process.platform==='win32'){
  process.argv.splice(2,0,'dev');
  require('./tauri.cjs');
}else{
  const {spawnSync}=require('node:child_process');
  const result=spawnSync(require('electron'),['.',...process.argv.slice(2)],{stdio:'inherit'});
  if(result.error)throw result.error;
  process.exitCode=result.status??1;
}
