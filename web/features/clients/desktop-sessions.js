'use strict';
// Desktop providers use the same conversation, composer and workspace presentation as Codex.
class DesktopSessionsView {
  constructor({root,select,request,notify,onSelect,csrf,onUnauthorized}) {
    Object.assign(this,{root,select,request,notify,onSelect,csrf,onUnauthorized});this.provider='codex';this.generation=0;this.detailRevision=0;this.modelSelectionRevision=0;this.drafts=new Map();this.provisionalDrafts=new Map();this.accountDrafts=new Map();this.skillSelections=new Map();this.composerDrafts=typeof ComposerDrafts==='function'?new ComposerDrafts():null;this.draftGateway='';this.draftScope=null;this.draftTouched=false;this.restoringDraft=false;this.pending=new Map();this.rows=[];this.messageNodes=new Map();this.providerViews=new Map();this.detailCache=new Map();this.activity=new SessionActivity({key:'bridge-desktop-session-activity'});try{this.collapsedGroups=new Set(JSON.parse(localStorage.getItem('bridge-desktop-session-groups')||'[]'));}catch{this.collapsedGroups=new Set();}
    this.readTasks=new Map();this.readEpoch=0;this.providerReadEpochs=new Map();this.listPrefetchAt=new Map();this.detailCacheSizes=new Map();this.detailCacheBytes=0;this.modelDialog=null;
    this.listCacheIdentity='';this.listCacheHost='';this.modelCatalogs=new Map();
    this.container=this.node('section','desktop-sessions');root.append(this.container);this.container.hidden=true;
    this.list=this.node('aside','ds-list');this.main=this.node('main','ds-main');this.container.append(this.list,this.main);
    this.search=this.node('input','search');this.search.placeholder=BridgeI18n.t('搜索');this.label(this.search,'搜索聊天或项目');this.search.oninput=()=>this.renderList();
    const filters=this.node('div','list-filters');const display=this.node('label','list-mode');display.append(this.translated('span','显示方式'));this.listMode=this.node('select');this.label(this.listMode,'聊天列表显示方式');for(const [id,title] of [['recent','最近交互'],['project','按项目']])this.listMode.add(new Option(BridgeI18n.t(title),id));this.listMode.onchange=()=>this.renderList();display.append(this.listMode);
    this.surface=this.node('select','ds-surface');this.label(this.surface,'会话类型');this.surface.add(new Option(BridgeI18n.t('全部会话'),'all'));this.surface.value='all';this.surfaceSelection='all';this.surface.hidden=true;this.surface.onchange=()=>{this.surfaceSelection=this.surface.value;this.renderList();};const archive=this.node('label','archive');this.archived=this.node('input');this.archived.type='checkbox';this.archived.onchange=()=>this.renderList();archive.append(this.archived,this.translated('span','已归档'));filters.append(this.surface,display,archive);
    this.listStatus=this.node('p','muted ds-list-status');this.listStatus.setAttribute('role','status');this.connectionRetry=this.button('重试连接',async()=>{const provider=this.provider;if(this.retryingClient||!this.retryClient)return;this.retryingClient=provider;this.renderConnectionStatus();try{await this.retryClient(provider);}finally{this.retryingClient=null;this.renderConnectionStatus();}});this.connectionRetry.hidden=true;
    this.connectionInitialize=this.button('初始化连接',async()=>{const provider=this.provider;if(this.initializingClient||!this.initializeClient)return;this.initializingClient=provider;this.renderConnectionStatus();try{await this.initializeClient(provider);}finally{this.initializingClient=null;this.renderConnectionStatus();}});this.connectionInitialize.hidden=true;
    this.connectionReconnect=this.button('重新连接 Desktop',async()=>{const provider=this.provider;if(this.reconnectingClient||!this.reconnectClient)return;this.reconnectingClient=provider;this.renderConnectionStatus();try{await this.reconnectClient(provider);}finally{this.reconnectingClient=null;this.renderConnectionStatus();}});this.connectionReconnect.hidden=true;
    this.connectionNotice=this.node('p','muted');this.connectionNotice.hidden=true;this.connectionRefresh=this.button('刷新状态',async()=>{if(this.refreshingClient||!this.refreshClients)return;this.refreshingClient=true;this.renderConnectionStatus();try{await this.refreshClients();}finally{this.refreshingClient=false;this.renderConnectionStatus();}});this.connectionRefresh.hidden=true;this.rowsRoot=this.node('div','sessions');const toolbar=this.node('div','chat-list-toolbar');toolbar.append(this.search,filters);this.list.append(toolbar,this.listStatus,this.connectionNotice,this.connectionRetry,this.connectionReconnect,this.connectionInitialize,this.connectionRefresh,this.rowsRoot);if(typeof bindChatListToolbar==='function')bindChatListToolbar(toolbar);
    this.welcome=this.node('div','welcome ds-welcome');const logo=this.node('img','mark large');logo.src='/icon.png';logo.alt='';logo.width=72;logo.height=72;this.welcome.append(logo,this.translated('h1','从一条聊天继续'),this.translated('p','选择电脑上的聊天，查看进度或发送消息。','muted'));
    this.conversation=this.node('section','ds-conversation chat');this.conversation.hidden=true;this.main.append(this.welcome,this.conversation);
    this.back=this.iconButton('返回聊天列表','m15 5-7 7 7 7',()=>this.backToList());this.back.classList.add('ds-back');
    this.clientIcon=this.node('span','client-icon');const info=this.node('div','chat-info');this.title=this.node('span','ds-title');this.titleButton=this.button('',()=>this.chatDetails());this.titleButton.className='chat-title-button';this.label(this.titleButton,'查看聊天详情');this.titleButton.append(this.title);info.append(this.titleButton);
    this.status=this.node('span','status');this.status.setAttribute('role','status');const settings=this.iconButton('设置','M5 12h.01M12 12h.01M19 12h.01',()=>{document.getElementById('appearance-dialog')?.showModal();window.loadNotificationDefaults?.();});settings.className='ds-settings appearance-button';settings.setAttribute('data-open-appearance','');
    const head=this.node('header','ds-head chat-head');head.append(this.back,this.clientIcon,info,this.status,settings);
    this.messages=this.node('div','ds-messages timeline');this.messages.tabIndex=-1;this.requests=this.node('div','ds-requests');this.notice=this.node('p','notice');this.notice.hidden=true;this.resumeButton=this.button('继续会话',()=>this.mutate('resume',{}));this.resumeButton.hidden=true;
    this.form=this.node('form','ds-composer composer');this.tools=this.node('div','composer-tools');this.modelButton=this.button('',()=>this.models());this.modelButton.className='tool-button ds-model';this.modelName=this.translated('span','模型','ds-model-name');this.modelEffort=this.node('span','ds-model-effort');this.modelButton.append(this.modelName,this.modelEffort);
    this.skillsButton=this.button('Skill',()=>this.skills());this.skillsButton.className='tool-button';this.skillsButton.hidden=true;this.permissionsButton=this.button('权限',()=>this.permissions());this.permissionsButton.className='tool-button';this.permissionsButton.hidden=true;
    this.composerToggle=this.iconButton('收起输入区','m6 9 6 6 6-6',()=>this.collapseComposer(!this.composerBody.hidden));this.composerToggle.className='composer-toggle';this.composerToggle.setAttribute('aria-expanded','true');this.contextButton=this.button('',()=>this.contextDetails());this.contextButton.className='tool-button context-usage ds-context';this.contextRing=this.node('span','context-usage-ring');this.contextRing.setAttribute('aria-hidden','true');this.contextButton.append(this.contextRing);this.tools.append(this.modelButton,this.skillsButton,this.permissionsButton,this.contextButton,this.composerToggle);
    this.composerBody=this.node('div','ds-composer-body');this.skillPills=this.node('div','skill-pills');this.attachmentList=this.node('div','attachment-list');this.attachmentList.hidden=true;this.attachmentInput=this.node('input');this.attachmentInput.type='file';this.attachmentInput.multiple=true;this.attachmentInput.accept='image/png,image/jpeg,image/gif,image/webp';this.attachmentInput.hidden=true;this.attachButton=this.iconButton('添加文件或图片','m8 12 6-6a3.5 3.5 0 0 1 5 5l-8 8a5 5 0 0 1-7-7l8-8m-6 10 7-7',()=>{});this.attachButton.className='attach-button';this.error=this.node('div','error');this.error.setAttribute('role','alert');this.input=this.node('textarea');this.input.rows=1;this.input.maxLength=100000;this.input.placeholder=BridgeI18n.t('继续这条聊天…');this.label(this.input,'消息内容');this.input.oninput=()=>{this.draftTouched=true;this.saveDraft();this.resizeInput();this.updateComposer();};this.input.addEventListener('keyup',()=>this.saveDraft());this.input.addEventListener('click',()=>this.saveDraft());
    this.mode=this.node('select');this.label(this.mode,'发送方式');for(const [id,title] of [['send','发送新消息'],['queue','完成后发送'],['steer','补充当前任务']])this.mode.add(new Option(BridgeI18n.t(title),id));this.mode.onchange=()=>this.saveDraft();
    this.send=this.button('发送 ↑',()=>{});this.send.className='primary';this.send.type='submit';this.stop=this.button('■ 停止',()=>this.mutate('stop',{}));this.stop.className='stop';this.stop.hidden=true;
    const actions=this.node('div','ds-actions compose-bottom'),sendActions=this.node('div','compose-actions');sendActions.append(this.stop,this.send);actions.append(this.attachButton,this.attachmentInput,this.mode,sendActions);this.composerBody.append(this.skillPills,this.attachmentList,this.error,this.input,actions);this.form.append(this.tools,this.composerBody);this.form.onsubmit=e=>{e.preventDefault();return this.submit();};
    this.attachments=new ChatAttachments({root:this.attachmentList,button:this.attachButton,input:this.attachmentInput,paste:this.input,drop:this.form,onChange:()=>this.updateComposer(),upload:(key,id,file)=>this.uploadAttachment(key,id,file),preview:(key,id)=>this.attachmentUrl(key,id,'preview'),thumbnail:async(key,id,file)=>{const image=await this.attachments.thumbnailBlob(file);return this.uploadBinary(this.attachmentUrl(key,id,'thumb')+'&width='+image.width+'&height='+image.height,image.data,image.mime);}});
    const addAttachments=this.attachments.add.bind(this.attachments);this.attachments.add=files=>{if(!this.attachments.key||this.attachments.locked)return;if(this.overRequestLimit([...this.attachments.rows,...files])){this.attachments.error=this.requestLimitMessage();this.attachments.render();return;}if(this.provider!=='claude'||this.state?.backend!=='cli'){if(files.some(file=>!file.type?.startsWith('image/'))){this.attachments.error='此应用的消息附件仅支持图片；其他文件请使用文件传输。';this.attachments.render();return;}}addAttachments(files);};
    this.conversation.append(head,this.notice,this.messages,this.requests,this.form);this.workbench=new Workbench({chat:this.conversation,request,csrf,notify,onUnauthorized});select.onchange=()=>this.choose(select.value);
    document.addEventListener('bridge-language',()=>this.relabel());const resume=()=>{clearTimeout(this.timer);if(document.hidden)this.listSync.reset();else{this.prefetchLists();if(this.provider!=='codex')this.refresh();}};document.addEventListener('visibilitychange',resume);window.addEventListener('focus',resume);window.addEventListener('pagehide',()=>this.saveDraft());
    this.appearanceObserver=new MutationObserver(()=>{this.renderMessages(this.lastMessages||[]);this.workbench.setThumbnails(document.documentElement.dataset.showFileThumbnails==='true');});this.appearanceObserver.observe(document.documentElement,{attributes:true,attributeFilter:['data-show-reasoning','data-show-process','data-show-file-thumbnails']});
    const listRegion=this.node('div','session-list-region');this.listHint=this.button('',()=>{});this.listHint.className='list-sync';this.listHint.hidden=true;this.listHint.setAttribute('aria-live','polite');listRegion.append(this.rowsRoot,this.listHint);this.list.append(listRegion);
    this.listSync=new ListSync({root:this.rowsRoot,status:this.listHint,refresh:()=>this.refreshList(),visible:()=>!this.root.hidden&&!this.container.hidden&&this.list.getBoundingClientRect().width>0,ready:()=>document.activeElement!==this.search,automatic:false});
    this.rowsRoot.addEventListener('scroll',()=>this.saveListSnapshot(this.provider),{passive:true});
    this.updateComposer();
  }
  node(tag,cls='',text){const n=document.createElement(tag);n.className=cls;if(text!==undefined)n.textContent=text;return n;}
  translated(tag,text,cls=''){const node=this.node(tag,cls,BridgeI18n.t(text));node.dataset.i18n=text;return node;}
  label(node,text){node.dataset.i18nAriaLabel=text;node.setAttribute('aria-label',BridgeI18n.t(text));}
  button(text,fn){const n=this.translated('button',text,'plain');n.type='button';n.onclick=async()=>{try{return await fn();}catch(e){this.notify(BridgeI18n.t(e.message));}};return n;}
  iconButton(text,path,fn){const button=this.button('',fn);button.className='icon-button';this.label(button,text);button.title=BridgeI18n.t(text);const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('class','header-icon');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');const shape=document.createElementNS(svg.namespaceURI,'path');shape.setAttribute('d',path);svg.append(shape);button.append(svg);return button;}
  path(action,sid=this.sid,provider=this.provider){const path='/api/desktop-sessions/'+provider+'/'+action+(sid?'?sessionId='+encodeURIComponent(sid):'');return window.BridgeRelayURL?.(path)||path;}
  listSnapshotKey(provider){return this.listCacheIdentity&&this.listCacheHost&&['claude','deepseek'].includes(provider)?'desktop-list-v1:'+this.listCacheIdentity+':'+encodeURIComponent(this.listCacheHost)+':'+provider:'';}
  bindListCache(identity,host){
    if(this.listCacheIdentity!==identity||this.listCacheHost!==host)this.providerViews.clear();
    this.listCacheIdentity=identity;this.listCacheHost=host;
    if(identity)for(const storage of [localStorage,sessionStorage])for(let i=storage.length-1;i>=0;i--){const key=storage.key(i);if(key?.startsWith('desktop-list-v1:')&&!key.startsWith('desktop-list-v1:'+identity+':'))storage.removeItem(key);}
    for(const provider of ['claude','deepseek']){
      const key=this.listSnapshotKey(provider);if(!key)continue;
      let saved;try{const snapshot=localStorage.getItem(key)||sessionStorage.getItem(key);if(snapshot?.length>512*1024)continue;saved=JSON.parse(snapshot||'null');}catch{continue;}
      if(saved&&Array.isArray(saved.rows)&&saved.rows.length<=200)this.providerViews.set(provider,{...saved,cachedAt:0,snapshotReady:true});
    }
  }
  previewCachedList(provider){
    if(!this.providerViews.get(provider)?.snapshotReady)return false;
    this.choose(provider,{previewOnly:true}).catch(error=>this.notify(error.message));
    return true;
  }
  confirmCachedList(){
    if(!this.previewOnly)return;
    this.previewOnly=false;this.listStamp='';this.renderList();this.refresh().catch(error=>this.notify(error.message));
  }
  saveListSnapshot(provider){
    const key=this.listSnapshotKey(provider),view=this.providerViews.get(provider);if(!key||!view?.snapshotReady)return;
    const current=provider===this.provider?{query:this.search.value,archived:this.archived.checked,listMode:this.listMode.value,surface:this.surfaceSelection,scroll:this.rowsRoot.scrollTop}:view;
    const rows=(view.rows||[]).slice(0,200).map(row=>({id:row.id,title:row.title,cwd:row.cwd,backend:row.backend,updatedAt:row.updatedAt,archived:row.archived}));
    try{const snapshot=JSON.stringify({rows,query:current.query||'',archived:current.archived===true,listMode:current.listMode||'recent',surface:current.surface||'all',scroll:current.scroll||0});if(snapshot.length<=512*1024){localStorage.setItem(key,snapshot);sessionStorage.removeItem(key);}}catch{}
  }
  sharedRead(provider,action,sid=null){
    const epoch=this.readEpoch,version=this.providerReadEpochs.get(provider)||0,key=JSON.stringify([provider,action,sid,epoch,version]);
    if(this.readTasks.has(key))return this.readTasks.get(key);
    const task={current:()=>epoch===this.readEpoch&&version===(this.providerReadEpochs.get(provider)||0)};
    task.promise=(async()=>{const value=await this.request(this.path(action,sid,provider));if(task.current()){
      if(action==='list'){
        const complete=value.connected!==false&&value.complete!==false&&!value.unavailableHosts?.length;
        this.providerViews.set(provider,{...this.providerViews.get(provider),rows:value.sessions||[],cachedAt:Date.now(),snapshotReady:complete});
        if(complete)this.saveListSnapshot(provider);
      }
      else if(action==='detail'&&value.session)this.cacheDetail(JSON.stringify([provider,sid]),value);
    }return value;})();this.readTasks.set(key,task);
    const done=()=>{if(this.readTasks.get(key)===task)this.readTasks.delete(key);};task.promise.then(done,done);return task;
  }
  forgetDetail(key){this.detailCache.delete(key);this.detailCacheBytes-=this.detailCacheSizes.get(key)||0;this.detailCacheSizes.delete(key);}
  cacheDetail(key,value){
    const bytes=JSON.stringify(value).length*2,limit=8*1024*1024;this.forgetDetail(key);if(bytes>limit)return;
    this.detailCache.set(key,value);this.detailCacheSizes.set(key,bytes);this.detailCacheBytes+=bytes;
    while(this.detailCache.size>12||this.detailCacheBytes>limit)this.forgetDetail(this.detailCache.keys().next().value);
  }
  invalidateReads(provider){
    this.providerReadEpochs.set(provider,(this.providerReadEpochs.get(provider)||0)+1);for(const key of this.readTasks.keys())if(JSON.parse(key)[0]===provider)this.readTasks.delete(key);
    this.listPrefetchAt.delete(provider);const saved=this.providerViews.get(provider);if(saved)saved.cachedAt=0;
    if(provider===this.provider){this.freshDetail=false;this.detailRevision++;this.loading=null;this.listSync.reset();}
  }
  prefetchLists(){
    if(document.hidden||this.root.hidden)return;
    const now=Date.now();for(const client of this.clientStates||[]){
      if(!['claude','deepseek'].includes(client.id)||client.id===this.provider||!client.enabled||!this.sourceReadable(client)||client.operationUncertain)continue;
      if(now-Math.max(this.providerViews.get(client.id)?.cachedAt||0,this.listPrefetchAt.get(client.id)||0)<30000)continue;
      this.listPrefetchAt.set(client.id,now);this.sharedRead(client.id,'list').promise.catch(()=>{});
    }
  }
  setClientStates(clients,retry,initialize,refresh,reconnect){
    for(const client of clients){const old=this.clientStates?.find(row=>row.id===client.id);if(old&&(old.enabled!==false&&client.enabled===false||this.sourceReadable(old)&&!this.sourceReadable(client)))this.invalidateReads(client.id);}
    const before=this.clientStates?.find(client=>client.id===this.provider);this.clientStates=clients;this.retryClient=retry;this.initializeClient=initialize;this.refreshClients=refresh;this.reconnectClient=reconnect;
    const selected=clients.find(client=>client.id===this.provider),cliReadable=this.provider==='claude'&&this.state?.backend==='cli'&&selected?.enabled!==false&&this.sourceReadable(selected);
    if(this.state&&!this.canMutate()&&!cliReadable)this.staleDetail();else this.updateComposer();
    const current=clients.find(client=>client.id===this.provider),wasWaiting=before&&ClientLifecycle.connection(before).waiting;
    this.prefetchLists();
    if(!this.renderConnectionStatus()&&before&&(wasWaiting||(!this.sourceReadable(before)&&this.sourceReadable(current)))){this.listStatus.textContent=this.rows.length?'':BridgeI18n.t('正在读取聊天…');return this.refresh();}
  }
  sourceReadable(client){return !!client&&(client.connected===true||client.id==='claude'&&client.cliAvailable===true);}
  renderConnectionStatus(){
    const client=this.clientStates?.find(client=>client.id===this.provider),state=client&&ClientLifecycle.connection(client);
    const failure=client?.operationFailure,uncertain=!!(client?.operationUncertain||failure?.uncertain),blocked=!!state&&!client.connected&&(state.waiting||state.action||state.retryable||state.canReconnect||!!failure);
    this.listStatus.setAttribute('aria-busy',String(!!state?.waiting));this.listStatus.classList.toggle('client-connection-waiting',!!state?.waiting);
    this.connectionRetry.hidden=!blocked||!state.retryable||uncertain;this.connectionRetry.disabled=!!this.retryingClient;
    this.connectionInitialize.hidden=!blocked||!state.canInitialize||uncertain;this.connectionInitialize.disabled=!!this.initializingClient;
    this.connectionReconnect.hidden=!blocked||!state.canReconnect||uncertain;this.connectionReconnect.disabled=!!this.reconnectingClient;this.connectionReconnect.textContent=BridgeI18n.t('重新连接 Desktop');
    this.connectionInitialize.textContent=BridgeI18n.t(state?.canReconnect?'重新初始化连接':'初始化连接');
    this.connectionNotice.hidden=!failure;this.connectionNotice.textContent=failure?BridgeI18n.t(ClientLifecycle.failureMessage(failure)):'';this.connectionRefresh.hidden=!uncertain;this.connectionRefresh.disabled=!!this.refreshingClient;
    if(blocked)this.listStatus.textContent=BridgeI18n.t(state.label)+(state.reason&&state.reason!==state.label?' · '+BridgeI18n.t(state.reason):'');
    return blocked&&!(client?.enabled!==false&&client?.cliAvailable===true&&this.provider==='claude');
  }
  get isChatOpen(){return this.provider!=='codex'&&!!this.sid&&!this.conversation.hidden;}
  bindDraftGateway(identity){if(this.draftGateway&&this.draftGateway!==identity){this.provisionalDrafts.clear();this.drafts.clear();for(let i=sessionStorage.length-1;i>=0;i--){const key=sessionStorage.key(i);if(key?.startsWith('desktop-draft:'))sessionStorage.removeItem(key);}}this.draftGateway=identity||'';}
  saveDraft(){
    if(!this.sid||this.restoringDraft)return null;
    const key=this.provider+':'+this.sid,fields={text:this.input.value,selectionStart:this.input.selectionStart,selectionEnd:this.input.selectionEnd,sendMode:this.mode.value,skills:[...this.selectedSkills().keys()]};
    if(!this.draftScope||!this.composerDrafts){if(this.draftGateway&&this.composerDrafts){if(this.draftTouched)this.provisionalDrafts.set(key,{gateway:this.draftGateway,account:'',...fields});}else this.drafts.set(key,fields.text);return null;}
    const saved=this.composerDrafts.save(this.draftScope,fields);
    if(saved){this.provisionalDrafts.delete(key);this.drafts.delete(key);sessionStorage.removeItem('desktop-draft:'+key);}
    else{this.provisionalDrafts.set(key,{gateway:this.draftGateway,account:this.draftScope.account,...fields});this.drafts.set(key,fields.text);}
    return saved;
  }
  bindDraftScope(value){
    const account=value?.draftAccountIdentity||value?.session?.draftAccountIdentity||'';
    if(!account&&this.draftScope){this.saveDraft();this.drafts.delete(this.provider+':'+this.sid);this.draftScope=null;this.draftTouched=false;this.input.value='';this.selectedSkills().clear();this.updateComposer();return;}
    if(!this.draftGateway||!account||!this.sid||!this.composerDrafts)return;
    const scope={gateway:this.draftGateway,provider:this.provider,account,host:'local',session:this.sid};
    if(this.composerDrafts.key(scope)===this.composerDrafts.key(this.draftScope))return;
    const switching=!!this.draftScope;if(switching){this.saveDraft();this.drafts.delete(this.provider+':'+this.sid);for(const key of this.pending.keys())if(key.startsWith(this.provider+':'+this.sid+':send:')&&key.endsWith(':'+this.draftGateway+':'))this.pending.delete(key);}this.draftScope=scope;
    const key=this.provider+':'+this.sid,pending=this.provisionalDrafts.get(key);
    if(pending&&(pending.gateway!==this.draftGateway||pending.account&&pending.account!==account)){this.provisionalDrafts.delete(key);this.drafts.delete(key);sessionStorage.removeItem('desktop-draft:'+key);}
    const provisional=this.provisionalDrafts.get(key),promoted=provisional&&this.composerDrafts.save(scope,provisional);
    if(promoted){this.provisionalDrafts.delete(key);this.drafts.delete(key);sessionStorage.removeItem('desktop-draft:'+key);}
    const stored=this.composerDrafts.load(scope),legacy=(stored||provisional)?null:this.composerDrafts.migrate(scope,sessionStorage,{text:'desktop-draft:'+this.provider+':'+this.sid});
    const draft=promoted||provisional||stored||legacy;
    if(draft&&(switching||!this.draftTouched)){
      this.restoringDraft=true;this.input.value=draft.text;this.input.setSelectionRange(draft.selectionStart,draft.selectionEnd);this.mode.value=draft.sendMode;
      const selected=this.selectedSkills();selected.clear();for(const id of draft.skills)selected.set(id,{id,name:id});
      this.restoringDraft=false;this.renderSkillPills();this.resizeInput();this.updateComposer();
    }else if(switching||!this.draftTouched){this.input.value='';this.mode.value='send';this.selectedSkills().clear();this.updateComposer();}
    if(this.draftTouched&&!switching)this.saveDraft();this.draftTouched=false;
  }
  showSelection(open){this.conversation.hidden=!open;this.welcome.hidden=open;this.container.classList.toggle('ds-open',open);this.root.classList.toggle('chat-open',open);document.body.classList.toggle('chat-detail',open);}
  rememberView(){
    if(this.provider==='codex')return;this.saveDraft();this.workbench.rememberScroll();this.providerViews.set(this.provider,{...this.providerViews.get(this.provider),rows:this.rows,sid:this.sid,query:this.search.value,archived:this.archived.checked,listMode:this.listMode.value,surface:this.surfaceSelection,scroll:this.rowsRoot.scrollTop});this.saveListSnapshot(this.provider);
  }
  async choose(provider,{previewOnly=false}={}){
    if(provider===this.provider)return;
    this.modelDialog?.close();this.rememberView();this.listSync.reset();clearTimeout(this.timer);this.generation++;this.detailRevision++;this.provider=provider;this.previewOnly=previewOnly;this.select.value=provider;this.workbench.provider=provider;this.workbench.current=null;this.workbench.panel.hidden=true;this.workbench.tabs.replaceChildren();this.conversation.classList.remove('workbench-active','wb-split');this.sid=null;this.state=null;this.freshDetail=false;const saved=this.providerViews.get(provider);this.rows=saved?.rows||[];this.listStamp='';this.search.value=saved?.query||'';this.archived.checked=saved?.archived||false;if(saved?.listMode)this.listMode.value=saved.listMode;this.surfaceSelection=saved?.surface||'all';this.showSelection(false);
    this.container.hidden=provider==='codex';this.root.classList.toggle('desktop-mode',provider!=='codex');this.clientIcon.replaceChildren();if(provider!=='codex'){const img=this.node('img');img.src='/client-icons/'+provider+'.png';img.alt='';this.clientIcon.append(img);}this.clientIcon.className='client-icon client-'+provider;this.listStatus.textContent=this.rows.length?'':BridgeI18n.t('正在读取聊天…');this.renderList();this.rowsRoot.scrollTop=saved?.scroll||0;this.saveListSnapshot(provider);this.updateComposer();if(saved?.sid&&!previewOnly)this.prepareChat(saved.sid);if(!previewOnly)this.onSelect(provider);
    this.renderConnectionStatus();if(provider!=='codex'&&!previewOnly)await this.refresh();
  }
  backToList(){if(!this.isChatOpen)return false;this.modelDialog?.close();this.saveDraft();this.workbench.cancelLocate();this.workbench.rememberScroll();this.workbench.stopThumbnails();this.sid=null;this.state=null;this.freshDetail=false;this.detailRevision++;this.showSelection(false);this.renderList();this.updateComposer();this.rememberView();this.onListEnter?.();return true;}
  async accountChanged(provider,previous={},next={}){
    if(provider===this.provider)this.modelDialog?.close();this.invalidateReads(provider);
    const identity=value=>JSON.stringify([provider,[...(value.activeIds||[value.activeId].filter(Boolean))].sort()]);
    if(provider===this.provider)this.saveDraft();
    const drafts=new Map([...this.drafts].filter(([key])=>key.startsWith(provider+':')));this.accountDrafts.set(identity(previous),drafts);
    if(provider===this.provider){clearTimeout(this.timer);this.generation++;this.detailRevision++;this.sid=null;this.state=null;this.draftScope=null;this.draftTouched=false;this.freshDetail=false;this.input.value='';}
    const jsonKey=key=>{try{return JSON.parse(key)[0]===provider;}catch{return false;}};
    this.providerViews.delete(provider);for(const key of this.drafts.keys())if(key.startsWith(provider+':'))this.drafts.delete(key);for(const key of this.provisionalDrafts.keys())if(key.startsWith(provider+':'))this.provisionalDrafts.delete(key);for(let i=sessionStorage.length-1;i>=0;i--){const key=sessionStorage.key(i);if(key?.startsWith('desktop-draft:'+provider+':'))sessionStorage.removeItem(key);}
    const snapshotKey=this.listSnapshotKey(provider);if(snapshotKey){localStorage.removeItem(snapshotKey);sessionStorage.removeItem(snapshotKey);}
    if(!this.draftGateway||!this.composerDrafts)for(const [key,text] of this.accountDrafts.get(identity(next))||[])this.drafts.set(key,text);
    for(const key of this.detailCache.keys())if(jsonKey(key))this.forgetDetail(key);for(const key of this.skillSelections.keys())if(jsonKey(key))this.skillSelections.delete(key);
    for(const key of this.pending.keys())if(key.startsWith(provider+':'))this.pending.delete(key);
    for(const key of Object.keys(this.activity.rows))if(key.startsWith(provider+'|'))delete this.activity.rows[key];this.activity.save();
    this.workbench.reset(provider);this.attachments.forget(jsonKey);
    if(provider!==this.provider)return;
    this.rows=[];this.listStamp='';this.lastMessages=[];this.requestStamp='';this.messageNodes.clear();this.messages.replaceChildren();this.requests.replaceChildren();this.showSelection(false);this.renderList();this.updateComposer();await this.refresh();
  }
  clear(){this.modelDialog?.close();this.listSync.reset();this.readEpoch++;this.readTasks.clear();this.providerReadEpochs.clear();this.listPrefetchAt.clear();this.detailCacheSizes.clear();this.detailCacheBytes=0;this.clientStates=[];this.workbench.reset();clearTimeout(this.timer);this.generation++;this.detailRevision++;this.provider='codex';this.previewOnly=false;this.select.value='codex';this.select.hidden=true;this.container.hidden=true;this.root.classList.remove('desktop-mode');this.sid=null;this.state=null;this.showSelection(false);this.drafts.clear();this.provisionalDrafts.clear();for(let i=sessionStorage.length-1;i>=0;i--){const key=sessionStorage.key(i);if(key?.startsWith('desktop-draft:'))sessionStorage.removeItem(key);}this.accountDrafts.clear();this.skillSelections.clear();this.providerViews.clear();this.listCacheIdentity='';this.listCacheHost='';this.draftGateway='';this.draftScope=null;this.detailCache.clear();this.activity.clear();this.freshDetail=false;this.rows=[];this.listStamp='';this.rowsRoot.replaceChildren();this.lastMessages=[];this.requestStamp='';this.pending.clear();this.attachments.reset();this.messages.replaceChildren();this.requests.replaceChildren();this.messageNodes.clear();}
  async refresh(){
    clearTimeout(this.timer);const generation=this.generation,provider=this.provider;if(this.previewOnly||provider==='codex'||document.hidden||this.root.hidden)return;
    if(this.renderConnectionStatus()){this.updateActivity(this.rows,false);this.renderIndicators();this.freshDetail=false;this.updateComposer();return;}
    if(this.loading?.generation===generation)return this.loading.promise;const loading={generation};this.loading=loading;
    if(this.sid)this.detail(generation).catch(error=>{if(generation===this.generation){this.error.textContent=BridgeI18n.t(error.message);this.status.textContent=BridgeI18n.t('连接失败');}});
    loading.promise=this.refreshList().catch(()=>{}).finally(()=>{if(this.loading===loading){this.loading=null;if(generation===this.generation)this.timer=setTimeout(()=>this.refresh(),this.sid||ClientLifecycle.connection(this.clientStates?.find(client=>client.id===provider)).waiting?2000:5000);}});
    return loading.promise;
  }
  refreshList(){
    const generation=this.generation,provider=this.provider;if(this.previewOnly||provider==='codex'||document.hidden||this.root.hidden||this.renderConnectionStatus())return Promise.resolve(false);
    const task=this.sharedRead(provider,'list');if(this.listRead?.task===task&&this.listRead.generation===generation)return this.listRead.promise;
    const reading={task,generation};this.listRead=reading;
    reading.promise=(async()=>{
      try{const value=await task.promise;if(!task.current()||generation!==this.generation)return false;this.rows=value.sessions||[];this.updateActivity(this.rows,value.connected!==false);this.listStatus.textContent=value.connected===false?BridgeI18n.t('尚未连接'):this.rows.length?'':BridgeI18n.t('电脑上还没有聊天');this.renderConnectionStatus();this.renderList();this.rememberView();this.onListReady?.(provider,value);if(value.connected===false)throw Error(BridgeI18n.t('尚未连接'));this.listSync.acknowledgeSuccess();return true;}
      catch(error){if(!task.current()||generation!==this.generation)return false;this.updateActivity(this.rows,false);this.renderIndicators();if(!this.renderConnectionStatus()){this.listStatus.textContent=this.rows.length?'':BridgeI18n.t(error.message);if(!this.listSync.busy)this.listSync.reportFailure(error);}if(this.sid&&!this.state)this.error.textContent=BridgeI18n.t(error.message);throw error;}
      finally{if(this.listRead===reading)this.listRead=null;}
    })();return reading.promise;
  }
  visibleActivity(){return this.isChatOpen&&!document.hidden&&!this.workbench.isFileVisible?this.provider+'|'+this.sid:null;}
  updateActivity(rows,connected=true){this.activity.update(rows.map(row=>({id:row.id,host:this.provider,connected,status:row.status,turnId:row.turnId,turnStatus:row.turnStatus})),this.visibleActivity());}
  renderIndicators(){
    const rows=new Map(this.rows.map(row=>[row.id,row]));for(const button of this.rowsRoot.querySelectorAll('.session')){button.querySelector('.session-indicator')?.remove();const row=this.freshDetail&&button.dataset.id===this.sid?this.state:rows.get(button.dataset.id),indicator=row?.requests?.length?(this.activity.rows[this.provider+'|'+button.dataset.id]?.offline?{kind:'unknown',label:'运行状态暂不可用'}:{kind:'awaiting',label:'等待回应'}):this.activity.indicator(this.provider+'|'+button.dataset.id);if(indicator){const dot=this.node('span','session-indicator '+indicator.kind);dot.title=BridgeI18n.t(indicator.label);dot.setAttribute('aria-label',BridgeI18n.t(indicator.label));button.querySelector('strong')?.prepend(dot);}}
  }
  renderList(){
    const types=new Set(this.provider==='claude'?(this.rows||[]).map(row=>row.backend).filter(kind=>['code','cowork','cli'].includes(kind)):[]),showTypes=types.size>1,selected=showTypes&&types.has(this.surfaceSelection)?this.surfaceSelection:'all';this.surfaceSelection=selected;const optionStamp=JSON.stringify([BridgeI18n.language(),...['code','cowork','cli'].filter(kind=>types.has(kind))]);if(optionStamp!==this.surfaceOptionsStamp){this.surface.replaceChildren(new Option(BridgeI18n.t('全部会话'),'all'),...['code','cowork','cli'].filter(kind=>types.has(kind)).map(kind=>new Option(kind==='cli'?'CLI':kind==='cowork'?'Cowork':'Code',kind)));this.surfaceOptionsStamp=optionStamp;}if(this.surface.value!==selected)this.surface.value=selected;this.surface.hidden=!showTypes;
    const query=this.search.value.trim().toLowerCase();const stamp=JSON.stringify([this.provider,this.sid,query,this.archived.checked,this.listMode.value,selected,showTypes,this.rows,BridgeI18n.language()]);if(stamp===this.listStamp){this.renderIndicators();return;}this.listStamp=stamp;const scroll=this.rowsRoot.scrollTop,top=this.rowsRoot.getBoundingClientRect().top,anchor=scroll>0?[...this.rowsRoot.querySelectorAll('.session')].find(node=>node.getBoundingClientRect().bottom>top):null,offset=anchor?anchor.getBoundingClientRect().top-top:0;this.rowsRoot.replaceChildren();
    const timestamp=value=>{const raw=Number(value||0);return raw<1e12?raw*1000:raw;};
    const rows=(this.rows||[]).filter(row=>(selected==='all'||row.backend===selected)&&(this.archived.checked||!row.archived)&&((row.title||'')+' '+(row.cwd||'')).toLowerCase().includes(query)).sort((a,b)=>timestamp(b.updatedAt)-timestamp(a.updatedAt));
    const groups=new Map();for(const row of rows){const key=this.listMode.value==='project'?row.cwd||BridgeI18n.t('电脑上的聊天'):'';if(!groups.has(key))groups.set(key,[]);groups.get(key).push(row);}
    for(const [name,items] of groups){let target=this.rowsRoot;if(name){const group=this.node('details','project-group ds-session-group'),key=JSON.stringify([this.provider,this.listMode.value,name]);group.open=!this.collapsedGroups.has(key);group.ontoggle=()=>{if(!group.isConnected)return;if(group.open)this.collapsedGroups.delete(key);else this.collapsedGroups.add(key);try{localStorage.setItem('bridge-desktop-session-groups',JSON.stringify([...this.collapsedGroups]));}catch{}};group.append(this.node('summary','',name));this.rowsRoot.append(group);target=group;}
      for(const row of items){const button=this.button('',()=>this.open(row.id));button.disabled=this.previewOnly===true;button.className='session ds-session-row'+(row.id===this.sid?' selected':'');button.dataset.id=row.id;button.dataset.provider=this.provider;const meta=this.node('small'),location=this.node('span','',row.cwd||''),time=this.node('time');if(row.updatedAt){const date=new Date(timestamp(row.updatedAt));if(Number.isFinite(date.getTime()))time.textContent=date.toLocaleDateString(BridgeI18n.locale(),{month:'numeric',day:'numeric'});}meta.append(location,time);button.append(this.node('strong','',row.title||BridgeI18n.t('新会话')));{const kind=this.node('span','ds-session-type',this.provider==='claude'?({code:'Code',cowork:'Cowork',cli:'CLI'}[row.backend]||BridgeI18n.t('其他来源')):'APP');kind.setAttribute('aria-label',BridgeI18n.t('会话类型')+': '+kind.textContent);button.append(kind);}button.append(meta);target.append(button);}
    }
    if(!rows.length&&this.rows.length)this.rowsRoot.append(this.translated('p','没有匹配的聊天','muted ds-list-empty'));this.rowsRoot.scrollTop=scroll;if(anchor){const next=[...this.rowsRoot.querySelectorAll('.session')].find(node=>node.dataset.id===anchor.dataset.id);if(next)this.rowsRoot.scrollTop+=next.getBoundingClientRect().top-this.rowsRoot.getBoundingClientRect().top-offset;}this.renderIndicators();this.saveListSnapshot(this.provider);
  }
  prepareChat(sid){
    this.modelDialog?.close();this.saveDraft();this.sid=sid;this.draftScope=null;this.draftTouched=false;this.mode.value='send';this.state=null;this.freshDetail=false;this.detailRevision++;this.modelSelectionRevision++;const row=this.rows.find(r=>r.id===sid);this.title.textContent=row?.title||BridgeI18n.t('正在读取聊天…');this.status.textContent=BridgeI18n.t('正在连接…');this.input.value=this.draftGateway&&this.composerDrafts?'':this.drafts.get(this.provider+':'+sid)||'';this.requestStamp='';this.error.textContent='';this.notice.hidden=true;this.messages.replaceChildren(this.translated('p','正在读取聊天…','muted'));this.messageNodes.clear();this.lastMessages=[];this.requests.replaceChildren();this.showSelection(true);this.attachments.open(JSON.stringify([this.provider,sid]));this.workbench.open(sid,'local');const cached=this.detailCache.get(JSON.stringify([this.provider,sid]));if(cached){this.applyDetail(cached,true);this.messages.scrollTop=this.workbench.current.scroll||0;}this.activity.read(this.provider+'|'+sid);this.updateComposer();this.renderList();this.resizeInput();this.rememberView();
  }
  async open(sid){
    if(this.previewOnly)return;
    const generation=this.generation;this.prepareChat(sid);
    try{await this.detail(generation);}catch(error){if(generation===this.generation&&sid===this.sid){this.error.textContent=BridgeI18n.t(error.message);this.status.textContent=BridgeI18n.t('连接失败');this.updateComposer();}}
  }
  async detail(generation){
    const sid=this.sid,provider=this.provider,revision=this.detailRevision,task=this.sharedRead(provider,'detail',sid),current=()=>task.current()&&generation===this.generation&&provider===this.provider&&sid===this.sid&&revision===this.detailRevision;let value;
    try{value=await task.promise;}catch(error){if(current()){this.staleDetail();throw error;}return;}if(!current())return;this.applyDetail(value);
  }
  canMutate(){const client=this.clientStates?.find(row=>row.id===this.provider);if(!this.state||!this.freshDetail||client?.enabled===false)return false;if(this.provider==='claude'&&this.state.backend==='cli')return ['ready','active','awaiting'].includes(this.state.connectionState);return !client||client.connected===true;}
  canResume(){const client=this.clientStates?.find(row=>row.id===this.provider);return this.provider==='claude'&&this.state?.backend==='cli'&&this.freshDetail&&client?.enabled!==false&&this.state.capabilities?.resume===true;}
  staleDetail(){this.freshDetail=false;this.renderRequests([]);this.requestStamp='';this.updateComposer();}
  applyDetail(value,cached=false){
    if(!value.session){this.staleDetail();this.status.textContent=BridgeI18n.t('尚未连接');return;}
    this.freshDetail=!cached&&value.connected!==false;if(!cached)this.bindDraftScope(value);this.state={...value.session,modelCatalogIdentity:value.modelCatalogIdentity||value.session.modelCatalogIdentity||'',capabilities:value.capabilities||value.session.capabilities||{},maxRequestBytes:value.maxRequestBytes||value.session.maxRequestBytes||0};this.title.textContent=this.state.title;this.status.textContent=BridgeI18n.t(cached?'正在连接…':!this.canMutate()?(this.state.backend==='cli'?'历史记录':'尚未连接'):this.state.requests?.length?'等待回应':this.state.status==='active'?'运行中':'已连接');this.updateComposer();this.sessionFiles=value.files||[];this.renderMessages(value.messages||[]);
    const requests=this.canMutate()?this.state.requests||[]:[],stamp=JSON.stringify([requests,BridgeI18n.language()]);if(stamp!==this.requestStamp){this.renderRequests(requests);this.requestStamp=stamp;}
    this.detailNotice=value.notice||'';this.renderNotice();if(!cached)this.updateActivity([this.state]);this.renderIndicators();
  }
  renderNotice(){const resumable=this.canResume();this.notice.textContent=BridgeI18n.t(this.detailNotice||(resumable?'可先阅读聊天历史；继续时将恢复原 Claude Code 会话。':''));this.notice.hidden=!this.detailNotice&&!resumable;if(resumable)this.notice.append(this.resumeButton);}
  updateComposer(){
    const state=this.state,caps=state?.capabilities||{},active=state?.status==='active',ready=this.canMutate();this.modelName.textContent=state?.model||BridgeI18n.t('模型');delete this.modelName.dataset.i18n;this.modelEffort.textContent=state?.effort?'· '+state.effort:'';this.modelEffort.hidden=!state?.effort;this.modelButton.title=[state?.model||BridgeI18n.t('模型'),state?.effort].filter(Boolean).join(' · ');this.modelButton.disabled=!ready||!!this.busy||caps.models===false;
    const permission=state?.permissionLabel||({'default':'默认权限','acceptEdits':'允许文件编辑','plan':'计划模式','bypassPermissions':'完全访问'}[state?.permissionMode])||state?.permissionMode||'权限';this.permissionsButton.textContent=BridgeI18n.t(permission);this.permissionsButton.dataset.i18n=permission;this.renderContext();
    this.resumeButton.textContent=BridgeI18n.t('继续会话');this.resumeButton.hidden=!this.canResume();this.resumeButton.disabled=!!this.busy||!this.canResume();
    const canAttach=caps.attachments===true;this.attachmentInput.accept=this.provider==='claude'&&state?.backend==='cli'?'':'image/png,image/jpeg,image/gif,image/webp';this.attachButton.hidden=!canAttach;this.form.classList.toggle('ds-has-attachments',canAttach);if(this.attachments){const locked=!ready||!!this.busy||!canAttach;if(this.attachments.locked!==locked)this.attachments.setLocked(locked);this.attachmentList.hidden=!canAttach||(!this.attachments.rows.length&&!this.attachments.error);}
    this.attachButton.title=BridgeI18n.t('添加文件或图片')+(state?.maxRequestBytes?' · '+BridgeI18n.t('消息和图片编码后合计最多 10 MiB'):'');this.skillsButton.hidden=caps.skills!==true;this.skillsButton.disabled=!state||!!this.busy;this.renderSkillPills();
    this.send.disabled=!ready||!!this.busy||caps.send===false||(canAttach&&(!this.attachments.ready()||this.overRequestLimit(this.attachments.rows)))||[...this.selectedSkills().values()].some(s=>s.invalid);this.stop.disabled=!ready||!active||!!this.busy;this.stop.hidden=!active||caps.stop===false;this.permissionsButton.hidden=caps.permissions!==true;this.permissionsButton.disabled=!ready||!!this.busy;this.mode.disabled=!ready||!!this.busy;
    this.mode.options[1].disabled=caps.queue===false;if(this.mode.options[1].disabled&&this.mode.value==='queue')this.mode.value='send';const steer=this.mode.options[2];steer.disabled=!active||caps.steer===false;if(steer.disabled&&this.mode.value==='steer')this.mode.value='send';
  }
  renderContext(){
    const usage=this.state?.contextUsage,used=usage?.usedTokens,limit=usage?.contextWindow;
    const known=Number.isFinite(used)&&used>=0&&Number.isFinite(limit)&&limit>0,percent=known?Math.round(used/limit*100):null;
    this.contextButton.hidden=!this.state;this.contextRing.style.setProperty('--context-percent',known?Math.min(100,percent)+'%':'0%');this.contextRing.classList.toggle('unknown',!known);
    this.contextButton.title=BridgeI18n.t('上下文使用量')+' · '+(known?percent+'%':BridgeI18n.t('暂未提供'));this.contextButton.setAttribute('aria-label',this.contextButton.title);
  }
  contextDetails(){
    if(!this.state)return;const dialog=this.dialog('上下文使用量'),usage=this.state.contextUsage;
    const number=value=>Number.isFinite(value)&&value>=0?value.toLocaleString(BridgeI18n.locale()):BridgeI18n.t('暂未提供');
    if(!usage)dialog.append(this.translated('p',this.state.contextUsageStatus==='unsupported'?'当前客户端或会话模式未提供上下文用量接口。':this.state.contextUsageStatus==='unavailable'?'当前会话尚未提供上下文用量；有可用数据时会自动更新。':'当前客户端尚未提供此会话的上下文用量。','muted'));
    else {for(const [label,key] of [[usage.measurement==='lastPrompt'?'最近一次模型输入':'已用 Token','usedTokens'],['上下文容量','contextWindow']])dialog.append(this.node('p','',BridgeI18n.t(label)+' · '+number(usage[key])));
      if(usage.contextWindow>0&&Number.isFinite(usage.usedTokens))dialog.append(this.node('p','',BridgeI18n.t('使用占比')+' · '+(usage.usedTokens/usage.contextWindow*100).toFixed(1)+'%'));
      if(usage.model)dialog.append(this.node('p','',BridgeI18n.t('模型')+' · '+usage.model));
      if(usage.compacted)dialog.append(this.translated('p','最近一次压缩后统计。','muted'));
      if(usage.measurement==='lastPrompt')dialog.append(this.translated('p','统计最近一次请求的输入与缓存 Token；不包含尚未发送的内容。','muted'));
      if(usage.estimated)dialog.append(this.translated('p','包含客户端对尚未发送内容的估算。','muted'));
      if(!this.freshDetail)dialog.append(this.translated('p','当前为缓存数据，连接恢复后更新。','muted'));
    }dialog.showModal();
  }
  resizeInput(){if(this.composerBody.hidden)return;this.input.style.height='auto';this.input.style.height=Math.min(160,Math.max(48,this.input.scrollHeight||48))+'px';}
  collapseComposer(value){this.composerBody.hidden=value;this.form.classList.toggle('is-collapsed',value);this.composerToggle.setAttribute('aria-expanded',String(!value));this.label(this.composerToggle,value?'展开输入区':'收起输入区');this.composerToggle.title=BridgeI18n.t(value?'展开输入区':'收起输入区');if(!value)this.resizeInput();}
  renderMessages(messages){
    this.lastMessages=messages;const atBottom=this.messages.scrollHeight-this.messages.scrollTop-this.messages.clientHeight<100,top=this.messages.scrollTop,nodes=[],next=new Map();
    for(const [index,message] of messages.entries()){
      const key=String(message.id??index),stamp=JSON.stringify([message,BridgeI18n.language(),this.sessionFiles]);const prior=this.messageNodes.get(key);let node=prior?.stamp===stamp?prior.node:null;
      if(!node){const activity=['activity','reasoning'].includes(message.role);node=this.node(activity?'details':'article',activity?'activity timeline-row':'message timeline-row '+message.role);if(activity){node.open=!!prior?.node.open;node.append(this.node('summary','',BridgeI18n.t(message.title||(message.role==='reasoning'?'思考摘要':'执行过程'))));node.append(this.node('pre','activity-body',message.text||''));}
        else{const who=message.role==='user'?BridgeI18n.t('你'):message.role==='error'?BridgeI18n.t('执行错误'):[this.provider==='claude'?'Claude':'DeepSeek',message.model&&[message.model,message.effort].filter(Boolean).join(' ')].filter(Boolean).join(' · ');node.append(this.node('span','who',who));const body=this.node('div','message-body');renderMarkdown(body,message.text||'',this.sessionFiles||[],file=>this.workbench.url(this.workbench.current,'download',file.path));node.append(body);const actions=this.node('div','message-actions');const copy=this.button('复制',()=>window.BridgeClipboard.copy(async()=>message.text||'',copy));copy.classList.add('message-copy');actions.append(copy,this.button('引用',()=>{this.input.value+=(this.input.value?'\n\n':'')+(message.text||'').split('\n').map(line=>'> '+line).join('\n')+'\n\n';this.collapseComposer(false);this.input.oninput();this.input.focus();}));node.append(actions);}
      }
      node.hidden=message.role==='reasoning'?document.documentElement.dataset.showReasoning==='false':message.role==='activity'&&document.documentElement.dataset.showProcess==='false';next.set(key,{stamp,node});nodes.push(node);
    }
    this.messageNodes=next;this.messages.replaceChildren(...nodes);if(!nodes.length&&this.state)this.messages.append(this.translated('p','这条聊天还没有消息','muted ds-history-empty'));if(atBottom)this.messages.scrollTop=this.messages.scrollHeight;else this.messages.scrollTop=top;
  }
  renderRequests(requests){const saved=new Map([...this.requests.children].map(form=>[form.dataset.requestKey,new Map((form.answerInputs||[]).map(({key,area,custom})=>[key,{values:[...area.querySelectorAll('input:checked')].map(n=>n.value),custom:custom.value}]))]));this.requests.replaceChildren();for(const request of requests){const sid=this.sid,generation=this.generation,form=this.node('form','approval');form.dataset.requestKey=JSON.stringify([this.provider,sid,request.id]);const answers=saved.get(form.dataset.requestKey);form.append(this.node('strong','',BridgeI18n.t(request.tool||'等待确认')));const inputs=[];
    if(request.needsInput){for(const [i,q] of (request.input?.questions||[]).entries()){const key=String(q.id||q.question||i);const label=this.node('fieldset','ds-question');label.append(this.node('legend','',q.question||q.header||BridgeI18n.t('问题')));const area=this.node('div');for(const option of q.options||[]){const line=this.node('label','ds-answer-option');const check=this.node('input');check.type=q.multiSelect?'checkbox':'radio';check.name='q'+i;check.value=option.label;check.checked=answers?.get(key)?.values.includes(option.label)||false;line.append(check,document.createTextNode(option.label+(option.description?' — '+option.description:'')));area.append(line);}const custom=this.node('input');custom.value=answers?.get(key)?.custom||'';custom.placeholder=BridgeI18n.t('补充回答');this.label(custom,'补充回答');label.append(area,custom);form.append(label);inputs.push({key,area,custom});}}
    else form.append(this.node('pre','',JSON.stringify(request.input||{},null,2)));
    form.answerInputs=inputs;const accept=this.button(request.needsInput?'提交回答':'允许本次',()=>{});accept.type='submit';form.append(accept);
    // Harness question events have no denial vocabulary; never invent a response.
    if(!request.needsInput||this.provider==='claude')form.append(this.button('拒绝',()=>{if(this.freshDetail&&sid===this.sid&&generation===this.generation)return this.mutate('respond',{requestId:request.id,decision:'decline'});}));
    form.onsubmit=event=>{event.preventDefault();if(!this.freshDetail||sid!==this.sid||generation!==this.generation)return;const answers={};for(const {key,area,custom} of inputs){const values=[...area.querySelectorAll('input:checked')].map(n=>n.value);if(custom.value.trim())values.push(custom.value.trim());if(!values.length){this.notify(BridgeI18n.t('请回答每一项问题'));return;}answers[key]={answers:values};}accept.disabled=true;this.mutate('respond',{requestId:request.id,decision:'accept',answers}).finally(()=>accept.disabled=false);};this.requests.append(form);
  }}
  requestId(){if(typeof uuid==='function')return uuid();if(typeof crypto.randomUUID==='function')return crypto.randomUUID();const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;const h=[...bytes].map(x=>x.toString(16).padStart(2,'0')).join('');return h.slice(0,8)+'-'+h.slice(8,12)+'-'+h.slice(12,16)+'-'+h.slice(16,20)+'-'+h.slice(20);}
  pendingKey(action,body,sessionId,provider=this.provider,account=''){return provider+':'+sessionId+':'+action+':'+JSON.stringify(body)+(action==='send'?':'+this.draftGateway+':'+account:'');}
  async mutate(action,body,sessionId=action==='create'?null:this.sid,requestId=null,draftAccount=''){
    if(this.busy||sessionId&&(!(action==='resume'?this.canResume():this.canMutate())||sessionId!==this.sid))return null;const provider=this.provider,generation=this.generation,key=this.pendingKey(action,body,sessionId,provider,draftAccount);this.invalidateReads(provider);const epoch=this.readEpoch,providerEpoch=this.providerReadEpochs.get(provider),currentWrite=()=>epoch===this.readEpoch&&providerEpoch===this.providerReadEpochs.get(provider);this.busy=true;this.error.textContent='';this.updateComposer();
    try{let id=requestId||this.pending.get(key);if(!id)id=this.requestId();if(action==='send'||!requestId)this.pending.set(key,id);const result=await this.request(this.path(action,null,provider),{...body,id,sessionId});if(action==='resume'&&result.status==='blocked')this.pending.delete(key);if(!['accepted','queued','ready'].includes(result.status))throw Error(result.message||'结果待核对，请检查桌面原会话');this.pending.delete(key);if(action==='access'&&result.mode&&provider===this.provider&&sessionId===this.sid&&generation===this.generation&&currentWrite()&&this.state){this.state.permissionMode=result.mode;const option=result.options?.find(row=>(row.value??row.id)===result.mode);this.state.permissionLabel=option?.label||option?.name||null;}return result;}
    catch(error){if(generation===this.generation&&sessionId===this.sid)this.error.textContent=BridgeI18n.t(error.message);this.notify(BridgeI18n.t(error.message));return null;}
    finally{const current=currentWrite();if(current)this.invalidateReads(provider);this.busy=false;this.updateComposer();if(current&&provider===this.provider)this.refresh();}
  }
  attachmentUrl(key,id,action){const [provider,sid]=JSON.parse(key);return this.path('uploads/'+encodeURIComponent(id)+'/'+action,sid,provider);}
  async uploadBinary(url,data,type){const response=await fetch(url,{method:'POST',credentials:'same-origin',headers:{'Content-Type':type||'application/octet-stream','X-CSRF-Token':this.csrf()},body:data});const result=await response.json();if(!response.ok){if(response.status===401)this.onUnauthorized();throw Error(result.error||BridgeI18n.t('附件上传失败，请重试'));}return result;}
  uploadAttachment(key,id,file){const [provider,sid]=JSON.parse(key);return this.uploadBinary(this.path('uploads',sid,provider)+'&id='+encodeURIComponent(id)+'&name='+encodeURIComponent(file.name),file,'application/octet-stream');}
  requestLimitMessage(){return 'Claude 单次消息与图片编码后不能超过 10 MiB，请减少附件';}
  overRequestLimit(rows){const limit=this.state?.maxRequestBytes;if(!limit)return false;return rows.reduce((total,row)=>total+Math.ceil(row.size/3)*4,0)+new TextEncoder().encode(JSON.stringify(this.input.value)).length>limit;}
  selectedSkills(){const key=JSON.stringify([this.provider,this.sid]);if(!this.skillSelections.has(key))this.skillSelections.set(key,new Map());return this.skillSelections.get(key);}
  renderSkillPills(){
    const selected=this.selectedSkills();this.skillPills.replaceChildren();this.skillsButton.textContent=selected.size?'Skill ('+selected.size+')':'Skill';delete this.skillsButton.dataset.i18n;
    for(const [id,skill] of selected){const pill=this.button((skill.name||id)+' ×',()=>{selected.delete(id);this.updateComposer();this.saveDraft();});pill.className='skill-pill'+(skill.invalid?' invalid':'');pill.disabled=!!this.busy;this.skillPills.append(pill);}this.skillPills.hidden=this.state?.capabilities?.skills!==true||!selected.size;
  }
  async skills(){
    if(!this.sid||this.state?.capabilities?.skills!==true)return;const sid=this.sid,generation=this.generation,selected=this.selectedSkills(),dialog=this.dialog('Skill'),loading=this.translated('p','正在读取已安装 Skill…','muted');dialog.append(loading);dialog.showModal();
    try{const catalog=await this.request(this.path('catalog'));if(sid!==this.sid||generation!==this.generation||!dialog.open)return dialog.close();loading.remove();const rows=catalog.skills||[],offered=new Set(rows.filter(s=>s.selectable!==false&&catalog.capabilities?.skills!==false).map(s=>s.id));for(const [id,skill] of selected)skill.invalid=!offered.has(id);this.updateComposer();
      const search=this.node('input','search'),list=this.node('div','skill-list');search.placeholder=BridgeI18n.t('搜索 Skill');this.label(search,'搜索 Skill');const render=()=>{list.replaceChildren();const query=search.value.trim().toLocaleLowerCase();for(const skill of rows.filter(s=>[s.name,s.description].join(' ').toLocaleLowerCase().includes(query))){const label=this.node('label','skill-option'),check=this.node('input'),info=this.node('span');check.type='checkbox';check.checked=selected.has(skill.id);check.disabled=!offered.has(skill.id);check.onchange=()=>{if(generation!==this.generation||sid!==this.sid)return dialog.close();if(check.checked&&this.state?.backend==='cli')selected.clear();else if(check.checked&&selected.size>=8){check.checked=false;this.notify(BridgeI18n.t('最多选择 8 个 Skill'));return;}if(check.checked)selected.set(skill.id,{id:skill.id,name:skill.name||skill.id});else selected.delete(skill.id);this.updateComposer();this.saveDraft();if(this.state?.backend==='cli')render();};info.append(this.node('strong','',skill.name||skill.id),this.node('small','',skill.description||''));if(skill.kind==='plugin')info.append(this.node('small','',BridgeI18n.t('插件')+' · '+BridgeI18n.t(skill.status||'只读')));label.append(check,info);list.append(label);}if(!list.children.length)list.append(this.translated('p','没有匹配的 Skill','muted'));};search.oninput=render;render();dialog.append(search,list);if(catalog.pluginError)dialog.append(this.node('p','error',BridgeI18n.t(catalog.pluginError)));
    }catch(error){if(dialog.open){loading.textContent=BridgeI18n.t(error.message);loading.className='error';}}
  }
  async submit(){
    const raw=this.input.value,text=raw.trim(),ids=this.state?.capabilities?.attachments===true?this.attachments.ids():[],selected=this.selectedSkills();
    if((!text&&!ids.length)||!this.sid||!this.state||!this.freshDetail||this.busy||this.state.capabilities.send===false||ids.length&&!this.attachments.ready())return;
    if(this.overRequestLimit(ids.length?this.attachments.rows:[])){this.error.textContent=BridgeI18n.t(this.requestLimitMessage());return;}
    if([...selected.values()].some(s=>s.invalid)){this.error.textContent=BridgeI18n.t('已选 Skill 已失效，请刷新列表后重新选择');return;}
    const sid=this.sid,provider=this.provider,key=JSON.stringify([provider,sid]),scope=this.draftScope;
    const body={text,mode:this.mode.value},skills=this.state.capabilities.skills===true?[...selected.keys()].sort():[];
    if(ids.length)body.attachments=ids;if(skills.length)body.plugins=skills;
    const transientKey=this.pendingKey('send',body,sid,provider),scopedKey=this.pendingKey('send',body,sid,provider,scope?.account||''),fallbackId=this.pending.get(scopedKey)||this.pending.get(transientKey);
    const revision=this.saveDraft()?.revision,provisional=this.provisionalDrafts.get(provider+':'+sid),pending=scope&&this.composerDrafts?this.composerDrafts.begin(scope,body,fallbackId||this.requestId()):null;
    if(pending?.blocked){this.error.textContent=BridgeI18n.t('上次发送结果尚未确认，请检查聊天记录或先处理未确认记录。');return;}
    const result=await this.mutate('send',body,sid,pending?.id||fallbackId,scope?.account||'');
    if(scope&&(pending||this.pending.has(scopedKey)||result))this.pending.delete(transientKey);
    if(result){
      const sameRevision=pending?this.composerDrafts.load(scope)?.revision===revision:this.input.value===raw;
      const confirmed=pending?this.composerDrafts.confirm(scope,pending.id,revision):true;
      if(confirmed&&provisional&&JSON.stringify(this.provisionalDrafts.get(provider+':'+sid))===JSON.stringify(provisional)){this.provisionalDrafts.delete(provider+':'+sid);this.drafts.delete(provider+':'+sid);sessionStorage.removeItem('desktop-draft:'+provider+':'+sid);}
      if(confirmed)this.attachments.clear(key,ids);
      if(confirmed&&sameRevision){for(const id of skills)selected.delete(id);
        if(!pending)this.drafts.delete(provider+':'+sid);
        if(sid===this.sid&&provider===this.provider&&(!this.composerDrafts||this.composerDrafts.key(scope)===this.composerDrafts.key(this.draftScope))){
          this.restoringDraft=true;this.input.value='';this.restoringDraft=false;this.resizeInput();
        }
      }
      this.updateComposer();
    }
  }
  dialog(title){const dialog=this.node('dialog','picker ds-picker'),head=this.node('div','picker-head');head.append(this.translated('h2',title));const close=this.button('×',()=>dialog.close());close.className='icon-button';this.label(close,'关闭');head.append(close);dialog.append(head);dialog.addEventListener('close',()=>dialog.remove());document.body.append(dialog);return dialog;}
  async models(){
    const sid=this.sid,provider=this.provider,generation=this.generation,revision=this.modelSelectionRevision;if(!sid||!this.state||!this.canMutate()||this.state.capabilities.models===false)return;
    this.modelDialog?.close();const dialog=this.dialog('模型设置'),head=dialog.querySelector('.picker-head'),close=head.querySelector('.icon-button'),actions=this.node('div','picker-head-actions'),refresh=this.button('刷新',()=>load(true));
    this.modelDialog=dialog;dialog.addEventListener('close',()=>{if(this.modelDialog===dialog)this.modelDialog=null;});dialog.classList.add('ds-model-dialog');refresh.className='tool-button ds-model-refresh';this.label(refresh,'从上游刷新可用模型');refresh.title=BridgeI18n.t('从上游刷新可用模型');const icon=document.createElementNS('http://www.w3.org/2000/svg','svg'),path=document.createElementNS('http://www.w3.org/2000/svg','path');icon.setAttribute('viewBox','0 0 24 24');icon.setAttribute('aria-hidden','true');path.setAttribute('d','M20 12a8 8 0 1 1-2.34-5.66L20 8M20 3v5h-5');icon.append(path);refresh.prepend(icon);close.remove();actions.append(refresh,close);head.append(actions);
    const form=this.node('form','ds-model-form'),modelField=this.node('div','model-field'),modelTitle=this.translated('div','模型','model-section-title'),model=this.node('select'),modelOptions=this.node('div','model-options'),effortField=this.node('div','model-field'),effortTitle=this.translated('div','思考强度','model-section-title'),effort=this.node('select'),effortOptions=this.node('div','effort-options'),notice=this.node('p','muted'),updated=this.node('small',undefined,'muted'),error=this.node('p','error'),footer=this.node('div','ds-model-actions'),cancel=this.button('取消',()=>dialog.close()),save=this.button('应用到此聊天',()=>{});
    model.hidden=true;effort.hidden=true;model.tabIndex=-1;effort.tabIndex=-1;model.setAttribute('aria-hidden','true');effort.setAttribute('aria-hidden','true');modelOptions.setAttribute('role','radiogroup');effortOptions.setAttribute('role','radiogroup');modelOptions.setAttribute('aria-label',BridgeI18n.t('模型'));effortOptions.setAttribute('aria-label',BridgeI18n.t('思考强度'));save.type='submit';save.className='primary';cancel.type='button';save.disabled=true;modelField.append(modelTitle,model,modelOptions);effortField.append(effortTitle,effort,effortOptions);footer.append(cancel,save);form.append(modelField,effortField,notice,updated,error,footer);dialog.append(form);dialog.showModal();
    const identity=this.state.modelCatalogIdentity||'',cacheKey=identity?JSON.stringify([this.listCacheIdentity,this.listCacheHost||'local',provider,this.state.backend||'',identity]):'',cached=cacheKey?this.modelCatalogs.get(cacheKey):null;
    let rows=[],capabilities={},current=this.state.model||'',currentEffort=this.state.effort||'',request=0,saving=false,loadingCatalog=false,needsReload=false,selectedModel='',selectedEffort='';
    const active=()=>dialog.open&&sid===this.sid&&provider===this.provider&&generation===this.generation&&revision===this.modelSelectionRevision&&(this.state?.modelCatalogIdentity||'')===identity;
    const effortNames={auto:'自动（模型默认）',none:'无',minimal:'最低',low:'低',medium:'中',high:'高',xhigh:'极高',max:'Max',ultra:'Ultra'};
    const choices=(host,values,selected,kind,disabled=false)=>{host.replaceChildren();for(const value of values){const choice=this.node('label',kind+'-choice'),input=this.node('input'),name=this.node('span',kind==='model'?'model-choice-name':'',kind==='model'?value.name||value.id:BridgeI18n.t(value.name&&value.name!==value.id?value.name:effortNames[value.id]||value.id)),id=value.id;input.type='radio';input.name='ds-'+kind+'-choice';input.value=id;input.checked=id===selected;input.disabled=disabled;input.onchange=()=>{if(!input.checked||input.disabled||!active())return;if(kind==='model'){selectedModel=id;selectedEffort='';render();}else{selectedEffort=id;renderEffort();}};choice.append(input,name);if(kind==='model'){choice.title=id;const check=this.node('span','model-choice-check','✓');check.setAttribute('aria-hidden','true');choice.append(check);}host.append(choice);}};
    const renderEffort=()=>{const row=rows.find(item=>item.id===selectedModel),options=capabilities.effort===false?[]:(row?.efforts||[]).map(item=>typeof item==='string'?{id:item,name:item}:item).filter(item=>item.id);effortField.hidden=!options.length;effort.replaceChildren(...options.map(item=>new Option(item.name||item.id,item.id)));if(!options.some(item=>item.id===selectedEffort))selectedEffort=options.some(item=>item.id===(selectedModel===current?currentEffort:row?.defaultEffort))?(selectedModel===current?currentEffort:row.defaultEffort):options[0]?.id||'';effort.value=selectedEffort;effortOptions.style.setProperty('--effort-columns',options.length<=4?Math.max(1,options.length):options.length<=6?3:4);choices(effortOptions,options,selectedEffort,'effort',saving||loadingCatalog);save.disabled=saving||loadingCatalog||needsReload||!selectedModel||capabilities.models===false||!!options.length&&!selectedEffort;};
    const render=()=>{model.value=selectedModel;choices(modelOptions,rows,selectedModel,'model',saving||loadingCatalog);renderEffort();};
    const showCatalog=(catalog,preserve=false,fromCache=false)=>{const offered=Array.isArray(catalog.models)?catalog.models.filter(row=>row&&typeof row.id==='string'&&row.id):[];rows=offered;capabilities=catalog.capabilities||{};current=offered.some(row=>row.id===this.state.model)||fromCache?this.state.model||'':catalog.currentModel||this.state.model||'';currentEffort=this.state.effort||catalog.currentEffort||'';const draft=preserve&&offered.some(row=>row.id===selectedModel);selectedModel=draft?selectedModel:offered.some(row=>row.id===current)?current:'';selectedEffort=draft?selectedEffort:'';model.replaceChildren(...rows.map(row=>new Option(row.name||row.id,row.id)));needsReload=false;render();const stamp=catalog.cache?.updatedAt;updated.textContent=Number.isFinite(stamp)&&stamp>0?BridgeI18n.t('更新于：')+new Date(stamp*1000).toLocaleString(BridgeI18n.locale()):'';notice.textContent=BridgeI18n.t(catalog.notice||(!rows.length?'暂未提供可用模型':current&&!selectedModel?'当前聊天模型不在可用列表中，请选择模型后应用。':''));};
    if(cached?.models?.length)showCatalog(cached,false,true);
    const load=async preserve=>{if(saving||!active())return;const ticket=++request;loadingCatalog=true;refresh.disabled=true;error.textContent='';if(rows.length)render();if(!rows.length)modelOptions.textContent=BridgeI18n.t('正在读取模型…');try{const catalog=await this.request(this.path('catalog',sid,provider)+'&section=models'+(preserve?'&refresh=true':''));if(ticket!==request||!active()){if(!active())dialog.close();return;}if(identity&&catalog.cache?.identity!==identity)throw Error(BridgeI18n.t('账号已切换，请重新打开模型设置'));showCatalog(catalog,preserve);if(cacheKey&&catalog.cache?.identity===identity)this.modelCatalogs.set(cacheKey,catalog);}catch(failure){if(ticket===request){if(active())error.textContent=BridgeI18n.t(failure.message);else dialog.close();}}finally{if(ticket===request&&active()){loadingCatalog=false;refresh.disabled=false;render();}}};
    form.onsubmit=async event=>{event.preventDefault();if(!active()||saving||loadingCatalog||save.disabled)return;request++;saving=true;const body={model:selectedModel};if(!effortField.hidden&&selectedEffort)body.effort=selectedEffort;refresh.disabled=true;cancel.disabled=true;close.disabled=true;render();error.textContent='';try{const result=await this.mutate('settings',body,sid);if(result&&active())dialog.close();else if(active()&&!result){needsReload=true;error.textContent=this.error.textContent||BridgeI18n.t('结果待核对，请检查桌面原会话');}}finally{saving=false;if(active()){refresh.disabled=false;cancel.disabled=false;close.disabled=false;render();}}};
    await load(false);
  }
  async permissions(){
    if(!this.sid||!this.state?.capabilities?.permissions)return;const sid=this.sid,generation=this.generation,value=await this.request(this.path('access'));if(sid!==this.sid||generation!==this.generation)return;const dialog=this.dialog('权限');for(const option of value.options||[]){const mode=option.value??option.id,button=this.button('',async()=>{if(sid!==this.sid||generation!==this.generation)return dialog.close();if(await this.mutate('access',{mode,...mode==='bypassPermissions'?{confirmed:true}:{}}))dialog.close();});permissionOption(button,mode,option.label||option.name||mode,option.description||'',mode===value.mode);dialog.append(button);}dialog.showModal();
  }
  chatDetails(){if(!this.state)return;const dialog=this.dialog('聊天详情');dialog.append(this.node('p','',this.state.title),this.node('p','muted',[this.provider==='claude'?(this.state.backend==='cowork'?'Claude · Cowork':'Claude · Code'):'DeepSeek Harness',this.state.model,this.state.effort].filter(Boolean).join(' · ')),this.node('p','muted',this.state.cwd||''),this.button('聊天通知设置',()=>{dialog.close();return this.notifications();}));dialog.showModal();}
  async notifications(){
    const sid=this.sid,provider=this.provider,generation=this.generation;if(!sid||!this.state)return;
    const dialog=this.dialog('聊天通知设置'),loading=this.translated('p','正在读取…','muted'),current=()=>sid===this.sid&&provider===this.provider&&generation===this.generation&&dialog.open;
    dialog.append(loading);dialog.showModal();
    try{
      const value=await this.request(this.path('notifications',sid,provider));if(!current())return dialog.close();loading.remove();
      const form=this.node('form'),fields={};
      for(const [key,title] of [['requests','请求处理通知'],['completion','运行完毕通知']]){
        const label=this.node('label'),select=this.node('select');this.label(select,title);label.append(this.translated('span',title),select);
        for(const [id,text] of [['inherit','跟随全局设置'],['on','开启'],['off','未开启']]){const option=this.translated('option',text);option.value=id;select.add(option);}select.value=value[key]||'inherit';fields[key]=select;form.append(label);
      }
      const error=this.node('p','error');error.setAttribute('role','alert');const save=this.button('保存配置',()=>{});save.type='submit';save.className='primary';
      form.append(this.translated('p',value.available?'通知通道已开启':'尚未配置通知通道，请在第三方通知中配置。','muted'),error,save);
      form.onsubmit=async event=>{event.preventDefault();if(!current())return dialog.close();if(save.disabled)return;save.disabled=true;error.textContent='';try{await this.request(this.path('notifications',sid,provider),{requests:fields.requests.value,completion:fields.completion.value});if(current()){dialog.close();this.notify(BridgeI18n.t('聊天提醒设置已保存'));}}catch(failure){if(current())error.textContent=BridgeI18n.t(failure.message);}finally{save.disabled=false;}};
      dialog.append(form);
    }catch(error){if(current()){loading.textContent=BridgeI18n.t(error.message);loading.className='error';}}
  }
  async create(){
    if(this.previewOnly)return;
    const generation=this.generation,provider=this.provider,dialog=this.dialog('新建聊天'),loading=this.translated('p','正在读取…','muted');dialog.append(this.node('p','muted',(provider==='claude'?'Claude':'DeepSeek Harness')+' · '+BridgeI18n.t('当前客户端')),loading);dialog.showModal();
    try{const value=await this.request(this.path('projects',null));if(generation!==this.generation||!dialog.open)return dialog.close();loading.remove();const projects=value.projects||[],form=this.node('form'),surface=this.node('select'),project=this.node('select'),title=this.node('input'),message=this.node('textarea'),error=this.node('p','error');this.label(project,'项目');this.label(surface,'会话类型');title.maxLength=120;title.required=true;title.value=BridgeI18n.t('新会话');this.label(title,'聊天名称');message.rows=3;message.maxLength=100000;message.required=provider==='claude'||value.createRequiresMessage===true;this.label(message,'首条消息');
      for(const kind of ['code','cowork','cli'])if(projects.some(row=>row.surface===kind))surface.add(new Option(kind==='code'?'Code':kind==='cowork'?'Cowork':'Claude Code CLI',kind));surface.value=[...surface.options].some(row=>row.value===this.state?.backend)?this.state.backend:surface.options[0]?.value||'';
      const create=this.button(message.required?'创建并发送':'创建并打开',()=>{});create.type='submit';create.className='primary';let titleField;const sync=()=>{project.replaceChildren();for(const row of projects.filter(row=>provider!=='claude'||row.surface===surface.value))project.add(new Option(row.name+' · '+row.cwd,row.key));const cli=provider==='claude'&&surface.value==='cli';title.required=!cli;titleField.hidden=cli;create.disabled=!project.options.length;};surface.onchange=sync;
      const field=(label,input)=>{const node=this.translated('label',label);node.append(input);form.append(node);return node;};if(provider==='claude')field('会话类型',surface);field('项目',project);titleField=field('聊天名称',title);if(message.required)field('首条消息',message);sync();
      form.append(this.node('p','muted',BridgeI18n.t(projects.length?'沿用所选项目与客户端配置':'请先在客户端创建一个项目会话')),error,create);form.onsubmit=async event=>{event.preventDefault();if(generation!==this.generation)return dialog.close();const cli=provider==='claude'&&surface.value==='cli';if(!cli&&!title.value.trim()||message.required&&!message.value.trim()){error.textContent=BridgeI18n.t(cli?'请输入首条消息':message.required?'请填写聊天名称和首条消息':'请输入聊天名称');return;}create.disabled=true;const body={projectKey:project.value};if(!cli)body.title=title.value.trim();if(message.required)body.firstMessage=message.value.trim();const result=await this.mutate('create',body,null);if(result?.result?.id&&generation===this.generation){dialog.close();await this.open(result.result.id);}else{error.textContent=BridgeI18n.t('结果待核对，请检查原会话列表');create.disabled=false;}};dialog.append(form);
    }catch(error){if(dialog.open){loading.textContent=BridgeI18n.t(error.message);loading.className='error';}}
  }
  relabel(){this.renderConnectionStatus();this.listStamp='';this.requestStamp='';this.search.placeholder=BridgeI18n.t('搜索');this.input.placeholder=BridgeI18n.t('继续这条聊天…');[...this.mode.options].forEach((option,i)=>option.textContent=BridgeI18n.t(['发送新消息','完成后发送','补充当前任务'][i]));this.listMode.options[0].textContent=BridgeI18n.t('最近交互');this.listMode.options[1].textContent=BridgeI18n.t('按项目');this.renderList();this.attachments.render();this.updateComposer();this.renderMessages(this.lastMessages||[]);this.collapseComposer(this.composerBody.hidden);this.workbench.relabel();if(this.sid)this.renderNotice();if(this.sid)this.renderRequests(this.freshDetail?this.state?.requests||[]:[]);}
}
if(typeof module!=='undefined')module.exports={DesktopSessionsView};
