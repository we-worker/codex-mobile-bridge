'use strict';
const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const pdf = require('../web/features/workspace/pdf-preview.js');

class Element {
  constructor(tag) {
    this.tagName=tag; this.children=[]; this.dataset={}; this.attributes={}; this.listeners={};
    this.style={setProperty:(name,value)=>{this.style[name]=value;}};
    this.className=''; this.classList={add:name=>this.className+=' '+name,remove:name=>this.className=this.className.replace(' '+name,'')};
    this.value=''; this.clientWidth=600; this.clientHeight=800; this.scrollTop=0; this.scrollLeft=0;
  }
  get textContent() { return this.value+this.children.map(child=>child.textContent).join(''); }
  set textContent(value) { this.value=value; this.children=[]; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.value=''; this.children=children; }
  setAttribute(name,value) { this.attributes[name]=value; }
  getContext() { return {canvas:this}; }
  getBoundingClientRect() { return {top:0,left:0}; }
  addEventListener(name,handler) { (this.listeners[name] ||= []).push(handler); }
  removeEventListener(name,handler) { this.listeners[name]=(this.listeners[name] || []).filter(value=>value!==handler); }
  dispatch(name,event={}) { for (const handler of this.listeners[name] || []) handler(event); }
  click() { this.onclick?.(); }
}
const element = tag => new Element(tag);
const childWithClass = (node, name) => node.children.find(child => child.className.split(' ').includes(name));
const tick = async () => { await new Promise(resolve=>setTimeout(resolve,0)); await new Promise(setImmediate); await new Promise(setImmediate); };
const setup = (coarse=false) => {
  global.document={createElement:element};
  global.BridgeI18n={t:text=>text};
  global.window={BridgeRelayBase:'',devicePixelRatio:1,matchMedia:()=>({matches:coarse})};
  let resized;
  global.ResizeObserver=class {
    constructor(callback){resized=callback;}
    observe(){}
    disconnect(){}
  };
  return {resize:()=>resized()};
};
const cleanup = () => {
  delete global.document; delete global.BridgeI18n; delete global.window; delete global.ResizeObserver;
};
const fixture = (count=30, pending=false, textChunks=[]) => {
  const events=[], renders=[], loading={destroy(){events.push('destroy');}};
  const dimensions=number => number % 3 === 1 ? [612,792] : number % 3 === 2 ? [792,400] : [420,1000];
  const doc={numPages:count, async getPage(number) {
    events.push('get '+number);
    const [width,height]=dimensions(number);
    return {
      getViewport:({scale})=>({width:width*scale,height:height*scale,scale}),
      cleanup(){events.push('cleanup '+number);},
      render({canvasContext}={}){
        if (!pending) { events.push('render '+number); return {promise:Promise.resolve(),cancel(){events.push('cancel '+number);}}; }
        if (pending === 'deferred') {
          let resolve, reject;
          const task={number,canvas:canvasContext?.canvas,settled:false,promise:new Promise((done,fail)=>{resolve=done;reject=fail;}),
            finish(){this.settled=true;resolve();},
            cancel(){this.settled=true;events.push('cancel '+number);reject({name:'RenderingCancelledException'});}};
          events.push('render '+number); renders.push(task); return task;
        }
        let reject;
        const task={promise:new Promise((_,fail)=>{reject=fail;}),cancel(){events.push('cancel '+number);reject({name:'RenderingCancelledException'});}};
        events.push('render '+number); return task;
      },
      getTextContent(){throw Error('getTextContent must not be used');},
      streamTextContent(){
        events.push('stream '+number);
        let index=0;
        return {getReader(){return {
          async read(){
            const value=textChunks[index++];
            if (value instanceof Error) throw value;
            return value ? {value,done:false} : {done:true};
          },
          async cancel(){events.push('text cancel '+number);},
          releaseLock(){events.push('text release '+number);}
        };}};
      }
    };
  }};
  loading.promise=Promise.resolve(doc);
  let options;
  const loadLibrary=async()=>({GlobalWorkerOptions:{},getDocument:value=>{options=value;return loading;}});
  return {events,renders,loadLibrary,options:()=>options};
};

test('zoom keeps completed pixels visible until the newest deferred render replaces them', async () => {
  setup();
  try {
    const fake=fixture(1,'deferred'), reader=pdf.create({url:'/api/workspace/download?path=file.pdf',
      info:{size:1000,clickDownloadMiB:1},loadLibrary:fake.loadLibrary});
    await reader.load(); await tick();
    const sheet=reader.element.children[2].children[0].children[0];
    fake.renders[0].finish(); await tick();
    const old=sheet.children[0];
    reader.element.children[0].children[5].click(); await tick();
    assert.equal(sheet.children[0],old,'committed pixels remain while next canvas is pending');
    assert.equal(Math.round(parseFloat(old.style.width)),710,'old pixels stretch to the new page width');
    reader.element.children[0].children[5].click(); await tick();
    assert.equal(sheet.children[0],old,'rapid zoom retains the same committed pixels');
    assert.ok(fake.events.includes('cancel 1'),'obsolete render was cancelled');
    assert.equal(fake.renders.length,3,'only the latest zoom starts after cancellation');
    fake.renders[2].finish(); await tick();
    assert.notEqual(sheet.children[0],old,'new pixels replace old pixels after completion');
    assert.equal(parseFloat(sheet.children[0].style.width),852);
    assert.equal(old.width,0,'old buffer is released after replacement');
    reader.dispose();
  } finally { cleanup(); }
});

test('returning to the original zoom reuses pixels and restores selectable text', async () => {
  setup();
  try {
    const fake=fixture(1,'deferred',[{items:[{str:'text'}],styles:{},lang:'en'}]);
    let textRenders=0;
    const loadLibrary=async()=>({...await fake.loadLibrary(),TextLayer:class {
      async render(){textRenders++;} cancel(){}
    }});
    const reader=pdf.create({url:'/api/workspace/download?path=file.pdf',
      info:{size:1000,clickDownloadMiB:1},loadLibrary});
    await reader.load(); await tick();
    fake.renders[0].finish(); await tick();
    const sheet=reader.element.children[2].children[0].children[0], old=sheet.children[0];
    assert.equal(textRenders,1);
    reader.element.children[0].children[5].click(); await tick();
    reader.element.children[0].children[3].click(); await tick();
    assert.equal(sheet.children[0],old);
    assert.equal(fake.renders.length,2,'the matching old raster needs no third render');
    assert.equal(textRenders,2,'text is restored after the cancelled intermediate zoom');
    assert.equal(sheet.children[1].className,'wb-pdf-text textLayer');
    reader.dispose();
  } finally { cleanup(); }
});

test('a short scroll back reuses a bounded neighboring page canvas', async () => {
  setup();
  try {
    const fake=fixture(8), reader=pdf.create({url:'/api/workspace/download?path=file.pdf',
      info:{size:1000,clickDownloadMiB:1},loadLibrary:fake.loadLibrary});
    await reader.load(); await tick();
    const stage=reader.element.children[2], sheets=stage.children[0].children;
    const first=sheets[0].children[0], renders=()=>fake.events.filter(value=>value==='render 1').length;
    assert.equal(renders(),1);
    stage.scrollTop=parseFloat(sheets[0].style.height)+16;
    stage.dispatch('scroll'); await tick();
    assert.equal(sheets[0].children[0],first,'nearby completed page remains cached');
    stage.scrollTop=0; stage.dispatch('scroll'); await tick();
    assert.equal(sheets[0].children[0],first);
    assert.equal(renders(),1,'returning to the page does not re-render its pixels');
    stage.scrollTop=10000; stage.dispatch('scroll'); await tick();
    assert.equal(first.width,0,'distant page buffer is released');
    reader.dispose();
  } finally { cleanup(); }
});

test('text-layer selection changes do not re-render completed canvas pixels', async () => {
  setup();
  try {
    const fake=fixture(4,false,[{items:[{str:'x'}],styles:{},lang:'en'}]);
    const loadLibrary=async()=>({...await fake.loadLibrary(),TextLayer:class {
      async render(){} cancel(){}
    }});
    const reader=pdf.create({url:'/api/workspace/download?path=file.pdf',
      info:{size:1000,clickDownloadMiB:1},loadLibrary});
    const stage=reader.element.children[2]; stage.clientHeight=3000;
    await reader.load(); await tick();
    const before=fake.events.filter(value=>value.startsWith('render ')).length;
    stage.scrollTop=100; stage.dispatch('scroll'); await tick();
    assert.equal(fake.events.filter(value=>value.startsWith('render ')).length,before);
    assert.ok(fake.events.includes('stream 4'),'newly selected text layer loads separately');
    reader.dispose();
  } finally { cleanup(); }
});

test('a pending replacement adds at most one 4 MP canvas to a 12 MP committed budget', async () => {
  setup();
  try {
    window.devicePixelRatio=2;
    const fake=fixture(3,'deferred'), reader=pdf.create({url:'/api/workspace/download?path=file.pdf',
      info:{size:1000,clickDownloadMiB:1},loadLibrary:fake.loadLibrary});
    const stage=reader.element.children[2]; stage.clientWidth=1200; stage.clientHeight=3000;
    await reader.load(); await tick();
    for (let index=0; index<3; index++) { fake.renders[index].finish(); await tick(); }
    const sheets=stage.children[0].children;
    const committed=()=>sheets.reduce((sum,sheet)=>sum+(sheet.children[0]?.width || 0)
      *(sheet.children[0]?.height || 0),0);
    assert.ok(committed()<=12*1024*1024);
    reader.element.children[0].children[5].click(); await tick();
    const pending=fake.renders.at(-1).canvas;
    assert.ok(pending.width*pending.height<=4*1024*1024);
    assert.ok(committed()+pending.width*pending.height<=16*1024*1024);
    reader.dispose(); await tick();
    assert.equal(pending.width,0);
    assert.equal(committed(),0);
  } finally { cleanup(); }
});

test('showing a fourth page reduces prior raster budgets before adding it', async () => {
  const observer=setup();
  try {
    window.devicePixelRatio=2;
    const fake=fixture(4,'deferred'), reader=pdf.create({url:'/api/workspace/download?path=file.pdf',
      info:{size:1000,clickDownloadMiB:1},loadLibrary:fake.loadLibrary});
    const stage=reader.element.children[2]; stage.clientWidth=1200; stage.clientHeight=3000;
    await reader.load(); await tick();
    for (let index=0; index<3; index++) { fake.renders[index].finish(); await tick(); }
    const sheets=stage.children[0].children;
    const committed=()=>sheets.reduce((sum,sheet)=>sum+(sheet.children[0]?.width || 0)
      *(sheet.children[0]?.height || 0),0);
    stage.clientHeight=6000; observer.resize(); await tick();
    for (let index=3; index<fake.renders.length && index<7; index++) {
      const task=fake.renders[index];
      assert.ok(committed()+task.canvas.width*task.canvas.height<=16*1024*1024);
      task.finish(); await tick();
    }
    assert.equal(sheets.filter(sheet=>sheet.children.length).length,4);
    assert.ok(committed()<=12*1024*1024);
    reader.dispose();
  } finally { cleanup(); }
});

test('interleaved zoom and neighboring-page return keep every committed frame within 12 MP', async () => {
  setup();
  try {
    window.devicePixelRatio=2;
    const fake=fixture(6,'deferred'), reader=pdf.create({url:'/api/workspace/download?path=file.pdf',
      info:{size:1000,clickDownloadMiB:1},loadLibrary:fake.loadLibrary});
    const stage=reader.element.children[2]; stage.clientWidth=1200; stage.clientHeight=3000;
    const sheets=()=>stage.children[0].children;
    const committed=()=>sheets().reduce((sum,sheet)=>sum+(sheet.children[0]?.width || 0)
      *(sheet.children[0]?.height || 0),0);
    const drain=async()=>{
      for (let count=0; count<20; count++) {
        await tick();
        const active=fake.renders.filter(task=>!task.settled);
        assert.ok(active.length<=1,'replacement canvases are serialized');
        assert.ok(committed()<=12*1024*1024,'every committed frame stays within budget');
        if (!active.length) return;
        assert.ok(committed()+active[0].canvas.width*active[0].canvas.height<=16*1024*1024);
        active[0].finish();
      }
      assert.fail('render queue did not settle');
    };
    await reader.load(); await drain();
    stage.scrollTop=parseFloat(sheets()[0].style.height)+16;
    stage.dispatch('scroll'); await drain();
    reader.element.children[0].children[5].click(); await tick();
    reader.element.children[0].children[5].click(); await drain();
    stage.scrollTop=0; stage.dispatch('scroll'); await drain();
    reader.element.children[0].children[3].click(); await drain();
    reader.element.children[0].children[3].click(); await drain();
    assert.ok(fake.events.some(event=>event==='cancel 2' || event==='cancel 3'));
    reader.dispose();
  } finally { cleanup(); }
});

test('PDF preview enforces preview and click-download limits before loading', async () => {
  setup();
  try {
    assert.equal(pdf.allowed({size:1024*1024,clickDownloadMiB:1}),true);
    assert.equal(pdf.allowed({size:1024*1024+1,clickDownloadMiB:1}),false);
    assert.equal(pdf.allowed({size:20*1024*1024,clickDownloadMiB:100}),true);
    assert.equal(pdf.allowed({size:20*1024*1024+1,clickDownloadMiB:100}),false);
    assert.equal(pdf.allowed({size:null,clickDownloadMiB:20}),false);
    const reader=pdf.create({url:'/api/workspace/download',info:{size:21*1024*1024,clickDownloadMiB:100}});
    await reader.load();
    assert.match(reader.element.textContent,/PDF 超过在线预览/);
    reader.dispose(); reader.dispose();
  } finally { cleanup(); }
});

test('continuous reader lazily renders a bounded mixed-size neighborhood and releases distant resources', async () => {
  setup();
  try {
    const fake=fixture(), reader=pdf.create({url:'/api/workspace/download?path=file.pdf',
      info:{size:1000,clickDownloadMiB:1},loadLibrary:fake.loadLibrary});
    await reader.load(); await tick();
    const stage=reader.element.children[2], pages=stage.children[0];
    assert.equal(pages.children.length,30);
    assert.equal(fake.options().url,'/api/workspace/download?path=file.pdf&preview=1');
    assert.equal(fake.options().disableAutoFetch,true);
    assert.ok(fake.events.filter(value=>value.startsWith('get ')).length<=4);
    assert.ok(pages.children.filter(sheet=>sheet.children.length).length<=5);
    assert.ok(pages.children.some(sheet=>parseFloat(sheet.style.height)!==parseFloat(pages.children[0].style.height)));
    stage.scrollTop=20*parseFloat(pages.children[0].style.height);
    stage.dispatch('scroll'); await tick();
    assert.ok(fake.events.some(value=>value==='get 20' || value==='get 21' || value==='get 22'));
    assert.ok(fake.events.includes('cleanup 1'));
    const active=pages.children.filter(sheet=>sheet.children.length);
    assert.ok(active.length<=3);
    for (const sheet of active) {
      const canvas=sheet.children[0];
      assert.ok(canvas.width*canvas.height<=4*1024*1024);
    }
    reader.dispose();
    assert.ok(fake.events.includes('destroy'));
    assert.equal(pages.children.length,0);
  } finally { cleanup(); }
});

test('resize preserves current reading position and pinch rerenders only after gesture end', async () => {
  const observer=setup(true);
  try {
    const fake=fixture(), reader=pdf.create({url:'/api/workspace/download?path=file.pdf',
      info:{size:1000,clickDownloadMiB:1},loadLibrary:fake.loadLibrary});
    await reader.load(); await tick();
    const toolbar=reader.element.children[0], stage=reader.element.children[2], pages=stage.children[0];
    assert.match(reader.element.className,/wb-pdf-touch/);
    stage.scrollTop=5*parseFloat(pages.children[0].style.height);
    stage.dispatch('scroll'); await tick();
    const before=toolbar.children[1].textContent, beforeTop=stage.scrollTop;
    stage.clientWidth=900; observer.resize();
    assert.equal(parseFloat(pages.children[0].style.width),568, 'observer callback defers layout writes');
    await tick();
    assert.equal(toolbar.children[1].textContent,before);
    assert.ok(stage.scrollTop>beforeTop);
    let prevented=false;
    const points=(a,b)=>[{clientX:a,clientY:300},{clientX:b,clientY:300}];
    stage.dispatch('touchstart',{touches:points(200,300)});
    const renders=fake.events.filter(value=>value.startsWith('render ')).length;
    stage.dispatch('touchmove',{touches:points(150,350),preventDefault(){prevented=true;}});
    assert.equal(prevented,true);
    assert.equal(fake.events.filter(value=>value.startsWith('render ')).length,renders);
    stage.dispatch('touchend',{touches:[]}); await tick();
    assert.equal(toolbar.children[4].textContent,'200%');
    assert.ok(fake.events.filter(value=>value.startsWith('render ')).length>renders);
    assert.ok(pages.children.filter(sheet=>sheet.children.length).reduce(
      (sum,sheet)=>sum+sheet.children[0].width*sheet.children[0].height,0)<=12*1024*1024);
    reader.dispose();
  } finally { cleanup(); }
});

test('closing cancels a deferred ResizeObserver layout', async () => {
  const observer=setup();
  const frames=new Map(); let frame=0;
  global.requestAnimationFrame=callback=>{frames.set(++frame,callback);return frame;};
  global.cancelAnimationFrame=id=>frames.delete(id);
  try {
    const fake=fixture(), reader=pdf.create({url:'/api/workspace/download?path=file.pdf',
      info:{size:1000,clickDownloadMiB:1},loadLibrary:fake.loadLibrary});
    await reader.load();
    const stage=reader.element.children[2], first=stage.children[0].children[0];
    const width=first.style.width;
    stage.clientWidth=900; observer.resize();
    assert.equal(first.style.width,width);
    assert.equal(frames.size,2, 'paint and resize are separately deferred');
    reader.dispose();
    assert.equal(frames.size,0);
  } finally {
    delete global.requestAnimationFrame; delete global.cancelAnimationFrame; cleanup();
  }
});

test('text layer reads chunks without ReadableStream async iteration', async () => {
  setup();
  try {
    const chunks=[
      {items:[{str:'one'}],styles:{first:{fontFamily:'sans-serif'}},lang:'zh'},
      {items:[{str:'two'}],styles:{second:{fontFamily:'serif'}},lang:'en'}
    ];
    const fake=fixture(1,false,chunks);
    let content, rendered=0;
    const loadLibrary=async()=>({...await fake.loadLibrary(),TextLayer:class {
      constructor({textContentSource}){content=textContentSource;}
      async render(){rendered++;}
      cancel(){}
    }});
    const reader=pdf.create({url:'/api/workspace/download?path=file.pdf',
      info:{size:1000,clickDownloadMiB:1},loadLibrary});
    await reader.load(); await tick();
    assert.equal(rendered,1);
    assert.deepEqual(content.items,chunks.flatMap(chunk=>chunk.items));
    assert.deepEqual(Object.keys(content.styles),['first','second']);
    assert.equal(content.lang,'zh');
    assert.ok(fake.events.includes('stream 1'));
    assert.ok(fake.events.includes('text release 1'));
    reader.dispose();
  } finally { cleanup(); }
});

test('text extraction failure retains the rendered PDF canvas', async () => {
  setup();
  try {
    const fake=fixture(1,false,[Error('text stream failed')]);
    const reader=pdf.create({url:'/api/workspace/download?path=file.pdf',
      info:{size:1000,clickDownloadMiB:1},loadLibrary:fake.loadLibrary});
    await reader.load(); await tick();
    const sheet=reader.element.children[2].children[0].children[0];
    assert.equal(sheet.children[0].tagName,'canvas');
    assert.ok(sheet.children[0].width>0);
    assert.ok(fake.events.includes('text cancel 1'));
    assert.ok(fake.events.includes('text release 1'));
    assert.doesNotMatch(reader.element.children[1].className,/error/);
    reader.dispose();
  } finally { cleanup(); }
});

test('text layer rendering failure also retains the canvas', async () => {
  setup();
  try {
    const fake=fixture(1,false,[{items:[{str:'one'}],styles:{},lang:'en'}]);
    let cancelled=0;
    const loadLibrary=async()=>({...await fake.loadLibrary(),TextLayer:class {
      async render(){throw Error('text layout failed');}
      cancel(){cancelled++;}
    }});
    const reader=pdf.create({url:'/api/workspace/download?path=file.pdf',
      info:{size:1000,clickDownloadMiB:1},loadLibrary});
    await reader.load(); await tick();
    const sheet=reader.element.children[2].children[0].children[0];
    assert.equal(sheet.children.length,1);
    assert.equal(sheet.children[0].tagName,'canvas');
    assert.ok(sheet.children[0].width>0);
    assert.equal(cancelled,1);
    reader.dispose();
  } finally { cleanup(); }
});

test('pending offscreen rendering is cancelled and closing destroys document', async () => {
  setup();
  try {
    const fake=fixture(8,true), reader=pdf.create({url:'/api/workspace/download?path=file.pdf',
      info:{size:1000,clickDownloadMiB:1},loadLibrary:fake.loadLibrary});
    await reader.load(); await tick();
    const stage=reader.element.children[2];
    assert.ok(fake.events.some(value=>value.startsWith('render ')));
    stage.scrollTop=10000; stage.dispatch('scroll'); await tick();
    assert.ok(fake.events.some(value=>value.startsWith('cancel ')));
    assert.ok(fake.events.some(value=>value.startsWith('cleanup ')));
    reader.dispose(); await tick();
    assert.ok(fake.events.includes('destroy'));
  } finally { cleanup(); }
});

test('tall touch viewport displays every visible short page within a 12 MP canvas budget', async () => {
  setup(true);
  try {
    const fake=fixture(), reader=pdf.create({url:'/api/workspace/download?path=file.pdf',
      info:{size:1000,clickDownloadMiB:1},loadLibrary:fake.loadLibrary});
    const stage=reader.element.children[2];
    stage.clientHeight=3000;
    await reader.load(); await tick();
    const sheets=stage.children[0].children;
    const visible=sheets.filter(sheet=>sheet.children.length);
    assert.ok(visible.length>=4, 'landscape and portrait pages visible together');
    assert.ok(visible.reduce((pixels,sheet)=>pixels+sheet.children[0].width*sheet.children[0].height,0)
      <=12*1024*1024);
    stage.scrollTop=20*parseFloat(sheets[0].style.height);
    stage.dispatch('scroll'); await tick();
    assert.ok(fake.events.includes('cleanup 1'));
    assert.ok(sheets.filter(sheet=>sheet.children.length).reduce(
      (pixels,sheet)=>pixels+sheet.children[0].width*sheet.children[0].height,0)<=12*1024*1024);
    reader.dispose();
  } finally { cleanup(); }
});

test('mixed natural page widths each fit the panel at 100 percent and pan after zoom', async () => {
  setup(true);
  try {
    const fake=fixture(3), reader=pdf.create({url:'/api/workspace/download?path=file.pdf',
      info:{size:1000,clickDownloadMiB:1},loadLibrary:fake.loadLibrary});
    const stage=reader.element.children[2]; stage.clientHeight=2400;
    await reader.load(); await tick();
    const sheets=stage.children[0].children;
    assert.deepEqual(sheets.map(sheet=>Math.round(parseFloat(sheet.style.width))),[568,568,568]);
    assert.deepEqual(sheets.map(sheet=>Math.round(parseFloat(sheet.children[0].style.width))),[568,568,568]);
    const scales=sheets.map(sheet=>Number(sheet.style['--total-scale-factor']));
    assert.ok(scales[0]!==scales[1] && scales[1]!==scales[2]);
    const points=(a,b)=>[{clientX:a,clientY:300},{clientX:b,clientY:300}];
    stage.dispatch('touchstart',{touches:points(200,300)});
    stage.dispatch('touchmove',{touches:points(150,350),preventDefault(){}});
    stage.dispatch('touchend',{touches:[]}); await tick();
    assert.deepEqual(sheets.map(sheet=>Math.round(parseFloat(sheet.style.width))),[1136,1136,1136]);
    assert.ok(parseFloat(sheets[0].style.width)>stage.clientWidth);
    reader.dispose();
  } finally { cleanup(); }
});

test('hidden resize keeps anchor; off-center pinch keeps the touched PDF point under the fingers', async () => {
  const observer=setup(true);
  try {
    const fake=fixture(), reader=pdf.create({url:'/api/workspace/download?path=file.pdf',
      info:{size:1000,clickDownloadMiB:1},loadLibrary:fake.loadLibrary});
    await reader.load(); await tick();
    const stage=reader.element.children[2], sheets=stage.children[0].children;
    stage.scrollTop=5*parseFloat(sheets[0].style.height);
    stage.dispatch('scroll'); await tick();
    const beforeTop=stage.scrollTop, beforeWidth=parseFloat(sheets[0].style.width);
    stage.clientWidth=0; stage.clientHeight=0; observer.resize(); await tick();
    assert.equal(stage.scrollTop,beforeTop);
    assert.equal(parseFloat(sheets[0].style.width),beforeWidth);
    stage.clientWidth=600; stage.clientHeight=800; observer.resize(); await tick();
    stage.scrollTop=0; stage.dispatch('scroll'); await tick();
    const firstWidth=parseFloat(sheets[0].style.width);
    const wrapperWidth=Math.max(...sheets.map(sheet=>parseFloat(sheet.style.width)));
    const focalX=250, left=16+(wrapperWidth-firstWidth)/2;
    const fraction=(stage.scrollLeft+focalX-left)/firstWidth;
    const points=(a,b)=>[{clientX:a,clientY:300},{clientX:b,clientY:300}];
    stage.dispatch('touchstart',{touches:points(200,300)});
    stage.dispatch('touchmove',{touches:points(150,350),preventDefault(){}});
    stage.dispatch('touchend',{touches:[]}); await tick();
    const afterWidth=parseFloat(sheets[0].style.width);
    const afterWrapper=Math.max(...sheets.map(sheet=>parseFloat(sheet.style.width)));
    const expected=16+(afterWrapper-afterWidth)/2+fraction*afterWidth-focalX;
    assert.ok(Math.abs(stage.scrollLeft-expected)<2);
    reader.dispose();
  } finally { cleanup(); }
});

test('workbench uses download info and disposes PDF when the tab closes', async () => {
  const calls=[], events=[];
  const context={window:{}, AbortController, BridgeI18n:{t:text=>text},
    BridgePdfPreview:{create:options=>{events.push(['create',options]);return {element:element('reader'),load:()=>events.push(['load']),dispose:()=>events.push(['dispose'])};}},
    document:{createElement:element}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(root,'web/features/workspace/workbench.js'),'utf8'),context);
  const Workbench=vm.runInContext('Workbench',context);
  const workbench=Object.create(Workbench.prototype), session={key:'fixture',files:[],active:'chat'};
  Object.assign(workbench,{current:session,sessions:new Map([[session.key,session]]),
    node:(tag,cls='',text)=>{const node=element(tag);node.className=cls;if(text!==undefined)node.textContent=text;return node;},
    button:(text,action)=>{const node=element('button');node.textContent=text;node.onclick=action;return node;},
    raw:node=>node,select:()=>{},paint:()=>{},url:(_session,operation)=>'/api/workspace/'+operation+'?path=file.pdf',
    request:async url=>{calls.push(url);return {name:'file.pdf',size:5,clickDownloadMiB:20};}});
  await workbench.preview(session,{name:'file.pdf',path:'file.pdf'});
  assert.deepEqual(calls,['/api/workspace/download?path=file.pdf&info=1']);
  assert.deepEqual(events.map(event=>event[0]),['create','load']);
  const head=childWithClass(session.files[0].body,'wb-preview-head');
  const actions=childWithClass(head,'wb-preview-actions');
  assert.equal(childWithClass(actions,'wb-download').href,'/api/workspace/download?path=file.pdf');
  await workbench.close('file:file.pdf');
  assert.deepEqual(events.map(event=>event[0]),['create','load','dispose']);
});

test('HTML preview switches to the original source and disposes its script frame', async () => {
  const lifecycle=[], original='<button>中文</button>\r\n<script>go()</script>';
  const context={window:{},AbortController,BridgeI18n:{t:text=>text},
    BridgeHtmlPreview:{create:({text})=>{assert.equal(text,original);lifecycle.push('create');return {element:element('frame'),dispose:()=>lifecycle.push('dispose')};}},
    BridgeSourceView:{create:({text})=>{const view=element('source');view.textContent=text;return view;}},
    document:{createElement:element}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(root,'web/features/workspace/workbench.js'),'utf8'),context);
  const Workbench=vm.runInContext('Workbench',context), workbench=Object.create(Workbench.prototype);
  const session={key:'fixture',files:[],active:'chat'};
  Object.assign(workbench,{current:session,sessions:new Map([[session.key,session]]),
    node:(tag,cls='',text)=>{const node=element(tag);node.className=cls;if(text!==undefined)node.textContent=text;return node;},
    button:(text,action)=>{const node=element('button');node.textContent=text;node.onclick=action;return node;},
    raw:node=>node,select:()=>{},paint:()=>{},url:()=>'/api/workspace',
    request:async()=>({kind:'text',name:'page.html',size:original.length,text:original})});
  await workbench.preview(session,{name:'page.html',path:'page.html'});
  const body=session.files[0].body;
  const modes=childWithClass(body,'wb-preview-modes'), content=childWithClass(body,'wb-preview-content');
  assert.equal(content.children[0].tagName,'frame');
  modes.children[1].onclick();
  assert.equal(content.children[0].textContent,original);
  assert.deepEqual(lifecycle,['create','dispose']);
  modes.children[0].onclick();
  await workbench.close('file:page.html');
  assert.deepEqual(lifecycle,['create','dispose','create','dispose']);
});
