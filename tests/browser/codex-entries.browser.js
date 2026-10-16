/* Load the actual client-navigation/accounts modules; invoke explicitly.
 * All requests below are synthetic. No gateway or real client is contacted. */
window.checkCodexEntries = async function checkCodexEntries() {
  const assert=(value,message)=>{if(!value)throw Error(message);};
  const root=document.getElementById('entries'),calls=[],changes=[];
  const candidate={id:'wsl:synthetic',kind:'wsl-cli',label:'WSL · Ubuntu · fixture · /home/fixture/.codex',enabled:false,running:true};
  let enabled=false;
  const widget=new CodexEntries({root,notify:message=>{throw Error(message);},onChange:value=>changes.push(value),request:async(path,body)=>{
    calls.push({path,body});if(body?.action==='configure')enabled=body.enabled;
    return {wslSupported:true,entries:[{id:'desktop',label:'桌面 Codex',kind:'desktop',enabled:true,running:true},{...candidate,enabled}]};
  }});
  await widget.refresh();assert(calls.length===1&&!calls[0].body,'inventory must remain passive');
  await widget.refresh(true);assert(calls[1].body.action==='scan','scan must be explicit');
  await widget.options.querySelector('button').onclick();assert(calls[2].body.id==='wsl:synthetic'&&calls[2].body.enabled===true,'connect registered ID');
  widget.select.value='wsl:synthetic';widget.select.onchange();assert(changes.at(-1)==='wsl:synthetic','select WSL');
  const value={accounts:[{id:'synthetic-account',name:'Saved API fixture',kind:'api',baseUrl:'https://fixture.invalid/v1',model:'group/fixture'}],
    current:{status:'ready',kind:'external',name:'Magpie'},switch:{phase:'idle'},
    management:{mode:'auto',external:true,reason:'此入口由 Magpie 或外部工具管理；请在原工具中切换接入'},
    canSwitch:false,blockers:[],desktopUpdate:{state:'unsupported'}};
  const panel=new AccountsPanel({root:document.getElementById('accounts'),read:async()=>value,request:async()=>{throw Error('must not modify externally managed config');}});
  await panel.refresh();
  const choose=[...document.querySelectorAll('#accounts button')].find(b=>b.textContent==='切换到此接入');
  assert(choose?.disabled,'Magpie switch must be disabled');
  assert(root.getBoundingClientRect().width<=innerWidth,'entry widget must fit narrow viewport');
  assert(root.scrollWidth<=root.clientWidth,'no entry horizontal overflow');
  return {passed:7,registeredTarget:widget.value,externalSwitchDisabled:choose.disabled,requests:calls.length};
};
