// Read-only CDP checks on issued workpapers. Browser-only mutations exercise sparse archives and polling.
import assert from 'node:assert/strict';
import {accessibility,browserInput,inspect,size} from './review-screen.mjs';

const trace = '.execution-trace', source = trace+' .execution-source button';
const picker = '#execution-trace-page', prev = '.execution-navigation button:first-child', next = '.execution-navigation button:last-child';
const events = '.execution-events', logs = events+' details', summary = logs+' summary';
const raw = '.execution-details > details:first-child', prompt = '.execution-details > details:last-child';
const q = selector => 'document.querySelector('+JSON.stringify(selector)+')';

export async function checkExecutionTrace(ctx,id,rev,previous) {
  const {root,call,evaluate,wait} = ctx;
  const {key,tap} = browserInput(ctx);
  const api = root+'/api/cases/'+id;
  const versions = await Promise.all([rev,previous].map(async r=>{
    const res = await fetch(api+'/reports/'+r); assert.equal(res.status,200);
    const bundle = await res.json(); assert.equal(bundle.rev,r); assert.equal(bundle.report.case_id,id);
    assert.ok(bundle.report.calls.pages.length >= 2 && bundle.report.calls.expert);
    return bundle;
  }));
  async function load(version) {
    await call('Page.navigate',{url:root+'/workpaper/'+id+'?rev='+version});
    await wait('state.bundle?.rev === '+version+' && '+q('#tabs [data-tab=activity]')+'?.isConnected','load R'+version);
    await evaluate(q('#tabs [data-tab=activity]')+'.click()');
    await wait(q(trace)+'?.dataset.rev === '+JSON.stringify(String(version)),'normal activity tab R'+version);
  }
  const click = selector => evaluate(q(selector)+'.click()');
  const focus = selector => evaluate(q(selector)+'.focus()');
  async function pick(index) {
    await evaluate('(()=>{const select='+q(picker)+';select.selectedIndex='+index+';select.dispatchEvent(new Event("change"));})()');
  }
  async function checkStep(row,kind,calls) {
    assert.equal(await evaluate(q(trace)+'.dataset.step'),kind);
    assert.equal(await evaluate(q('.execution-details')+'.querySelector("pre") === null'),true);
    const meta = await evaluate('[...'+q('.execution-facts')+'.children].map(n=>[n.firstChild.textContent,n.lastChild.textContent,n.querySelector("time")?.dateTime])');
    assert.deepEqual(meta.slice(0,2).map(r=>r[1]),[row.model ?? '未记录',String(row.attempts ?? '未记录')]);
    assert.deepEqual(meta.slice(2,4).map(r=>r[2]),[row.started,row.completed]);
    await focus(raw+' summary'); await key('Enter');
    await wait(q(raw+' pre')+'?.textContent','raw JSON');
    assert.deepEqual(JSON.parse(await evaluate(q(raw+' pre')+'.textContent')),row);
    await click(raw+' summary');
    await focus(prompt+' summary'); await key('Enter');
    await wait(q(prompt+' pre')+'?.textContent','selected prompt');
    assert.equal(await evaluate(q(prompt+' pre')+'.textContent'),calls.instructions[row.prompt_sha256]);
    await click(prompt+' summary');
  }
  async function checkPage(page,r,width) {
    if (width < 600) await tap(q(source));
    else { await focus(source); await key('Enter'); }
    const link = '#page-dialog .source-tools > a';
    await wait(q('#page-dialog')+'.open && '+q('#page-dialog .page-image')+'?.naturalWidth > 0','open page '+page.doc+' R'+r);
    assert.equal(await evaluate(q(link)+'.href'),api+'/documents/'+page.doc+'/pages/'+page.page+'?rev='+r);
    assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+r);
    await key('Escape');
    await wait('!'+q('#page-dialog')+'.open && document.activeElement === '+q(source),'return to issued page control');
  }
  async function checkLogs() {
    const expected = await evaluate('[...state.detail.events].reverse()');
    assert.ok(expected.length > 3);
    assert.deepEqual(await evaluate('[...'+q(events)+' .querySelectorAll(":scope > ol > li")].map(e=>[e.dataset.seq,e.lastChild.textContent])'),
      expected.slice(0,3).map(e=>[String(e.seq),e.message]));
    assert.equal(await evaluate(q(logs)+'.open'),false);
    assert.equal(await evaluate(q(logs)+' .querySelectorAll("li").length'),0);
    await focus(summary); await key('Enter');
    await wait(q(logs)+' .querySelectorAll("li").length === '+expected.length,'all task events');
    assert.deepEqual(await evaluate('[...'+q(logs)+'.querySelectorAll("li")].map(li=>[li.dataset.seq,li.querySelector("time").dateTime,li.querySelector("small").textContent,li.lastChild.textContent])'),
      expected.map(e=>[String(e.seq),e.time,'#'+e.seq+' · '+e.stage,e.message]));
    assert.equal(await evaluate('(()=>{const summary=document.activeElement, details=summary.parentElement, first=details.querySelector("li"), selected='+q(picker)+';'+
      'const events=state.detail.events; try { state.detail.events=[...events,{...events.at(-1),seq:events.at(-1).seq+1,message:"本地轮询回归"}]; renderCase();'+
      'return details.querySelectorAll("li")[1]===first && details.open && summary===document.activeElement && selected==='+q(picker)+' && details.querySelector("li").lastChild.textContent==="本地轮询回归" && summary.textContent==="查看全部 "+(events.length+1)+" 条";'+
      '} finally {state.detail.events=events;renderCase();}})()'),true);
    await key('Enter');
    await wait('!'+q(logs)+'.open','collapse events');
  }

  async function walk(calls) {
    const route = calls.pages.flatMap((page,i)=>[[i,'initial'],...(page.check ? [[i,'check']] : [])]);
    if (calls.expert) route.push([calls.pages.length,'expert']);
    await pick(0);
    for (const control of [next,prev]) {
      const order = control===next ? route : [...route].reverse();
      await focus(control);
      for (const step of order) {
        assert.deepEqual(await evaluate('['+q(picker)+'.selectedIndex,'+q(trace)+'.dataset.step]'),step);
        await key('Enter');
      }
      assert.equal(await evaluate('document.activeElement === '+q(control)),true);
    }
    await focus(picker);
    await key('End'); await wait(q(trace)+'.dataset.step === "expert"','keyboard picker to expert');
    await key('Home'); await wait(q(trace)+'.dataset.step === "initial"','keyboard picker to first page');
  }

  const [latest,frozen] = versions;
  for (const width of [320,360,390,768,1024,1440]) {
    await size(ctx,width);
    await call('Emulation.setTouchEmulationEnabled',{enabled:width<600});
    await load(rev);
    const {pages,expert} = latest.report.calls;
    assert.equal(await evaluate(q(picker)+'.options.length'),pages.length+1);
    assert.equal(await evaluate(q(trace)+'.querySelectorAll("pre").length'),0);
    const layout=await evaluate('({viewport:innerWidth,body:document.documentElement.scrollWidth,controls:[...'+q(trace)+'.querySelectorAll("select,button,summary")].map(n=>{const r=n.getBoundingClientRect();return [n.tagName,n.textContent.slice(0,14),r.left,r.right,r.height]})})');
    assert.ok(layout.body<=width+1 && layout.controls.every(([,,left,right,height])=>right>left && left>=0 && right<=width+1 && height>=43.99),'controls at '+width+' '+JSON.stringify(layout));
    assert.equal(await evaluate(q(prev)+'.getAttribute("aria-disabled")'),'true');
    if (width<600) await tap(q(next)); else { await focus(next); await key('Enter'); }
    await wait(q(trace)+'.dataset.step==="check"','step forward at '+width);
    await click(prev);
    assert.equal(await evaluate(q(trace)+'.dataset.step'),'initial');
    if (![390,1440].includes(width)) continue;
    if (width===1440) {
      await pick(1);
      await click('.execution-steps button:nth-child(2)');
      await focus('.execution-steps button:nth-child(2)');
    }
    await inspect(ctx,width,trace,'execution-trace');
    await walk(latest.report.calls);
    await checkLogs();
    const requests = 'performance.getEntriesByType("resource").filter(e=>new URL(e.name).pathname.startsWith("/api/")).length';
    const before = await evaluate(requests);
    await checkStep(pages[0],'initial',latest.report.calls);
    await focus(next); await key('Enter');
    assert.equal(await evaluate('document.activeElement === '+q(next)),true);
    await checkStep(pages[0].check,'check',latest.report.calls);
    await click(next);
    assert.equal(await evaluate(q(picker)+'.selectedIndex'),1);
    await checkStep(pages[1],'initial',latest.report.calls);
    assert.equal(await evaluate(requests),before);
    await checkPage(pages[1],rev,width);
    for (let i=2;i<pages.length;i++) {
      await pick(i);
      await checkPage(pages[i],rev,width);
    }
    await pick(pages.length);
    await checkStep(expert,'expert',latest.report.calls);
    assert.equal(await evaluate(q(source)+'===null && '+q(next)+'.getAttribute("aria-disabled")==="true"'),true);
    await focus(prev); await key('Enter');
    assert.equal(await evaluate(q(trace)+'.dataset.step'),'check');
    await pick(0);
    await checkPage(pages[0],rev,width);
    assert.ok(await evaluate(q('.rule-replay')+' && !'+q('[data-trace-rerun]')+'.hidden && [...document.querySelectorAll("#case-panel summary")].some(n=>n.textContent==="执行程序与版本摘要")'));
    // Change versions through the live workpaper picker and exercise the old DOM reference.
    await evaluate('window.detachedTraceSource='+q(source)+';const v=document.querySelector("#version");v.value='+JSON.stringify(String(previous))+';v.dispatchEvent(new Event("change"));void 0');
    await wait(q(trace)+'?.dataset.rev==='+JSON.stringify(String(previous)),'switch to frozen R'+previous);
    await evaluate('window.detachedTraceSource.click();delete window.detachedTraceSource');
    assert.equal(await evaluate(q('#page-dialog')+'.open'),false);
    const old = frozen.report.calls;
    await walk(old);
    for (let i=0;i<old.pages.length;i++) {
      await pick(i);
      await checkStep(old.pages[i],'initial',old);
      await checkPage(old.pages[i],previous,width);
      await click(next);
      await checkStep(old.pages[i].check,'check',old);
    }
    await pick(old.pages.length); await checkStep(old.expert,'expert',old);
    assert.equal(await evaluate(q('[data-trace-rerun]')+'.hidden'),true);
    await checkLogs();
  }
  const permalink = '.execution-count a';
  const stepUrl = (r,ref) => root+'/workpaper/'+id+'?'+new URLSearchParams({rev:r,view:'execution',call:ref});
  const active = 'document.activeElement === '+q(picker);
  for (const [version,bundle] of [[previous,frozen],[rev,latest]]) {
    for (const [ref,kind] of [['d01/p1/check','check'],['expert','expert'],['d99/p7/check','unavailable']]) {
      await call('Page.navigate',{url:stepUrl(version,ref)});
      await wait('state.bundle?.rev === '+version+' && '+active+' && '+q(trace)+'?.dataset.step==='+JSON.stringify(kind),'open fixed '+ref+' R'+version);
      if (kind==='unavailable') {
        assert.equal(await evaluate(q(picker)+'.selectedIndex'),-1);
        assert.equal(await evaluate(q(permalink)+' === null && '+q('.execution-step-row')+'.hidden && !'+q('.execution-unavailable')+'.hidden'),true);
        await click(next);
        assert.equal(await evaluate(q(permalink)+'.href'),stepUrl(version,'d01/p1/initial'));
      } else {
        assert.equal(await evaluate(q(permalink)+'.href'),stepUrl(version,ref));
        const row = kind==='expert' ? bundle.report.calls.expert : bundle.report.calls.pages[0].check;
        await checkStep(row,kind,bundle.report.calls);
        await click(next);
        const unchanged = await evaluate('(()=>{const p='+q(picker)+',step='+q(trace)+'.dataset.step;renderCase();return p==='+q(picker)+' && step==='+q(trace)+'.dataset.step;})()');
        assert.equal(unchanged,true);
      }
    }
  }
  await call('Page.navigate',{url:root+'/workpaper/'+id+'?rev='+rev+'&view=replay'});
  await wait('document.activeElement==='+q('.rule-replay button')+' && state.bundle?.rev==='+rev,'replay route focus');
  await pick(1); await click('.execution-steps button:last-child');
  const shared=await evaluate(q(permalink)+'.href');
  assert.equal(shared,stepUrl(rev,'d02/p1/check'));
  assert.equal(await evaluate('(()=>{const a='+q(permalink)+';let intercepted;a.addEventListener("click",e=>{intercepted=e.defaultPrevented;e.preventDefault();},{once:true});'+
    'a.dispatchEvent(new MouseEvent("click",{bubbles:true,cancelable:true,ctrlKey:true}));return intercepted;})()'),false);
  await focus(permalink); await key('Enter');
  await wait('Team.route().params.get("call")==="d02/p1/check" && '+active+' && '+q(trace)+'.dataset.step==="check"','activate share link');
  await evaluate('history.back()');
  await wait('Team.route().params.get("view")==="replay" && document.activeElement==='+q('.rule-replay button'),'return to rule replay');
  await load(previous);
  await focus(summary); await key('Enter');
  await click(raw+' summary'); await click(prompt+' summary');
  await wait(q(raw+' pre')+' && '+q(prompt+' pre')+' && '+q(logs)+'.open','expanded technical and log views');
  await click(raw+' details summary');
  await wait(q(raw+' details pre')+'?.textContent','complete original trace archive');
  assert.deepEqual(JSON.parse(await evaluate(q(raw+' details pre')+'.textContent')),frozen.report.calls);
  await accessibility(ctx,'expanded technical records and task log');
  await focus(raw+' summary'); await key('Tab');
  assert.equal(await evaluate('document.activeElement === '+q(raw+' pre')),true);
  await focus(summary);
  const polling = await evaluate(`(()=>{
    const bundle=state.bundle, detail=state.detail, focus=document.activeElement;
    const stable=()=>focus===document.activeElement && focus.parentElement.open && focus.isConnected;
    try {
      state.detail=structuredClone(detail);state.detail.status='running';state.detail.stage='extract';
      state.bundle=null;state.tab='report';renderCase();const running=stable();
      state.detail.documents[0].name+='（分页中）';renderCase();const pagination=stable();
      state.detail=detail;state.bundle=bundle;renderCase();
      return [running,pagination,stable(),state.tab,document.querySelector('.execution-events').dataset.case];
    } finally {state.detail=detail;state.bundle=bundle;state.tab='activity';renderCase();}
  })()`);
  assert.deepEqual(polling,[true,true,true,'activity',id]);
  // Simulate sparse or misbound older records in the document, without changing a stored report.
  const legacy = await evaluate(`(async()=>{
    const own=state.bundle, original=state.detail, slot=document.createElement('div');
    document.body.append(slot);
    try {
      const copy=structuredClone(own), calls=copy.report.calls, first=calls.pages[0];
      delete first.check; delete first.attempts; delete first.model; delete first.started; delete first.completed;
      first.prompt_sha256='unavailable'; calls.pages=[first]; delete calls.expert;
      state.bundle=copy;
      function render(){const node=ExecutionTrace.inspector(copy);slot.replaceChildren(node);return node;}
      first.check={doc:'other-doc'};const conflict=render();conflict.querySelector('.execution-steps button:last-child').click();
      const crossedCheck=!!conflict.querySelector('.execution-source button,.execution-count a');
      delete first.check;
      const sparse=render(), meta=[...sparse.querySelectorAll('dd')].slice(0,4).map(n=>n.textContent);
      const detail=sparse.querySelector('.execution-details > details:last-child'); detail.open=true;
      await new Promise(resolve=>detail.addEventListener('toggle',resolve,{once:true}));
      const missingPrompt=detail.textContent.includes('本版未留存此步指令');
      const nav=sparse.querySelector('.execution-navigation button:last-child').getAttribute('aria-disabled');
      const button=sparse.querySelector('.execution-source button'), saved=location.href;
      history.replaceState(null,'',Team.hash('case/'+original.id+'?rev='+(own.rev+1)));
      try {button.click();} finally {history.replaceState(null,'',saved);}
      const wrongRev=document.querySelector('#page-dialog').open;
      const wrong='00000000000000000000000000000000';
      history.replaceState(null,'',Team.hash('case/'+wrong+'?rev='+own.rev));
      try {button.click();} finally {history.replaceState(null,'',saved);}
      const wrongCase=document.querySelector('#page-dialog').open;
      let ambiguous,sharedDuplicate,workspace,scopedUrl;
      try {
        const url=Team.hash('case/'+original.id+'?rev='+own.rev+'&view=execution&call='+first.doc+'%2Fp'+first.page+'%2Finitial');
        history.replaceState(null,'',url);calls.pages=[first,structuredClone(first)];
        const duplicate=render();ambiguous=duplicate.dataset.step==='unavailable' && duplicate.querySelector('.execution-unavailable').textContent.includes('无法唯一定位');
        duplicate.querySelector('.execution-navigation button:last-child').click();
        sharedDuplicate=!!duplicate.querySelector('.execution-count a');calls.pages=[first];
        history.replaceState(null,'','#w/'+wrong+'/'+url.slice(1));const otherScope=render();
        workspace=otherScope.dataset.step==='unavailable' && !otherScope.querySelector('.execution-count a');
        const team=Team.current;
        try {Team.current={id:wrong};scopedUrl=render().querySelector('.execution-count a')?.getAttribute('href');}
        finally {Team.current=team;}
      } finally {history.replaceState(null,'',saved);calls.pages=[first];}
      const hash=first.page_sha256;
      first.page_sha256='0'.repeat(64);
      const mismatch=!!render().querySelector('.execution-source button');
      first.page_sha256=hash;
      const graph=copy.report.graph, edges=graph.edges;
      graph.edges=edges.filter(e=>!(e.type==='contains' && e.from===first.doc));
      const detached=!!render().querySelector('.execution-source button');
      graph.edges=edges;
      const ref=first.doc+'/p'+first.page, parent=edges.find(e=>e.type==='contains' && e.to===ref);
      const documentNode=graph.nodes.find(n=>n.id===first.doc);
      const otherDoc=graph.documents.find(d=>d.id!==first.doc && d.sha256!==documentNode.sha256);
      const altered={
        swappedDocumentHash:{nodes:graph.nodes.map(n=>n===documentNode ? {...n,sha256:otherDoc.sha256} : n)},
        duplicateDocument:{nodes:[...graph.nodes,{...documentNode}]},
        missingDocument:{nodes:graph.nodes.filter(n=>n!==documentNode)},
        wrongNodeType:{nodes:graph.nodes.map(n=>n===documentNode ? {...n,type:'page'} : n)},
        extraParent:{edges:[...edges,{...parent,from:otherDoc.id}]},
        duplicateEdge:{edges:[...edges,{...parent}]},
        extraEvidence:{edges:edges.map(e=>e===parent ? {...e,evidence:[ref,otherDoc.id]} : e)}
      };
      const offeredJumps=[], unreadable=[];
      for (const [name,changes] of Object.entries(altered)) {
        copy.report.graph={...graph,...changes};
        const node=render();
        if (node.querySelector('.execution-source button')) offeredJumps.push(name);
        const raw=node.querySelector('.execution-details > details:first-child');
        raw.open=true;
        await new Promise(resolve=>raw.addEventListener('toggle',resolve,{once:true}));
        if (node.dataset.step!=='initial' || raw.querySelector('pre')?.textContent!==JSON.stringify(first,null,2))
          unreadable.push(name);
      }
      copy.report.graph=graph; copy.report.case_id=wrong;
      const other=!!render().querySelector('.execution-source button');
      return {meta,missingPrompt,nav,wrongRev,wrongCase,mismatch,detached,offeredJumps,unreadable,other,crossedCheck,ambiguous,sharedDuplicate,workspace,scopedUrl};
    } finally {state.bundle=own;state.detail=original;slot.remove();}
  })()`);
  assert.deepEqual(legacy,{meta:Array(4).fill('未记录'),missingPrompt:true,nav:'true',wrongRev:false,
    wrongCase:false,mismatch:false,detached:false,offeredJumps:[],unreadable:[],other:false,crossedCheck:false,ambiguous:true,sharedDuplicate:false,workspace:true,
    scopedUrl:'/w/'+'0'.repeat(32)+'/workpaper/'+id+'?'+new URLSearchParams({rev:previous,view:'execution',call:'d01/p1/initial'})});
  console.log('Execution trace R'+rev+'/R'+previous+' passed six widths, frozen originals, exact JSON/prompts, current-task logs, scoped call links and replay return.');
}
