// Run on the isolated synthetic gateway fixture. Checks the rendered list while a swipe is in progress.
async function runClientSwipeLayoutTests(){
  const checks=[],nav=clientNavigation;
  const check=(condition,message)=>{if(!condition)throw Error(message);checks.push(message);};
  const gutterStyle=document.createElement('style');
  gutterStyle.textContent='#sidebar .sessions,.ds-list .sessions{scrollbar-gutter:stable}';
  document.head.append(gutterStyle);
  const waitForRows=async()=>{
    for(let i=0;i<100;i++){
      const rows=nav.swipeRows();
      if(rows?.querySelector('.session')&&rows.offsetWidth&&rows.scrollHeight>rows.clientHeight)return;
      await new Promise(resolve=>setTimeout(resolve,20));
    }
    throw Error('Timed out waiting for synthetic sessions');
  };
  try{for(const provider of ['codex','claude','deepseek']){
    await nav.choose(provider);
    await waitForRows();
    const source=nav.swipeRows();
    const original=source.querySelector('.session');
    check(!!original,provider+' has a rendered session');
    check(source.offsetWidth-source.clientWidth>0,provider+' has a reserved scrollbar gutter');
    const badgeSelector=provider==='codex'?'.session-source':'.ds-session-type';
    const measure=row=>{
      const title=row.querySelector('strong').getBoundingClientRect();
      const badge=row.querySelector(badgeSelector)?.getBoundingClientRect();
      return {display:getComputedStyle(row).display,height:row.getBoundingClientRect().height,width:row.getBoundingClientRect().width,
        badgeOffset:badge&&badge.top-title.top,badgeRight:badge?.right,rowRight:row.getBoundingClientRect().right};
    };
    const originalScroll=source.scrollTop;
    source.scrollTop=120;
    const before=measure(original),scroll=source.scrollTop;
    const list=provider==='codex'?document.getElementById('sidebar'):nav.view.list;
    nav.dragListSwipe({provider,list},provider==='codex'?-110:110);
    try{
      const preview=nav.swipePreview,copy=preview.current.querySelector('.session');
      const heading=nav.heading,headingParent=heading.parentElement,badgeIcon=nav.badge.querySelector('.client-icon'),navigation=nav.navigation,navigationParent=navigation.parentElement;
      nav.listGesture={provider,list};nav.paint();
      check(nav.swipePreview===preview&&nav.listGesture?.provider===provider,provider+' status paint preserves the active swipe');
      check(heading.parentElement===headingParent&&navigation.parentElement===navigationParent&&nav.badge.querySelector('.client-icon')===badgeIcon,provider+' status paint keeps the header and footer in place');
      check(!!preview&&preview.root.inert&&preview.root.getAttribute('aria-hidden')==='true',provider+' preview is inert');
      check(preview.current.querySelector('.client-swipe-rows').scrollTop===scroll,provider+' preview preserves the scroll position');
      check(preview.root.querySelectorAll('[id]').length===0,provider+' preview has no duplicate IDs');
      check(preview.root.querySelectorAll('[href], [autofocus]').length===0,provider+' preview has no active targets');
      const during=measure(copy);
      check(during.display===before.display,provider+' row keeps its layout while dragging');
      check(Math.abs(during.width-before.width)<1,provider+' row width stays stable while dragging');
      check(Math.abs(during.height-before.height)<1,provider+' row height stays stable while dragging');
      if(before.badgeOffset!==undefined){
        check(Math.abs(during.badgeOffset-before.badgeOffset)<1,provider+' type badge stays beside the title');
        check(Math.abs((during.rowRight-during.badgeRight)-(before.rowRight-before.badgeRight))<1,provider+' type badge stays right aligned');
      }
    }finally{nav.cancelListSwipe();}
    check(!document.querySelector('.client-swipe-preview')&&source.scrollTop===scroll,provider+' canceled preview restores the live list');
    source.scrollTop=originalScroll;
  }}finally{nav.cancelListSwipe();gutterStyle.remove();}
  return checks;
}
