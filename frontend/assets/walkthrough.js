import {captureContext, describeContext, returnUrl} from './walkthrough-context.js';
import {notebook} from './walkthrough-store.js';
import {pickPoint,pointLabel,pointPage,samePointPage,showDraftPoint} from './walkthrough-point.js';

const style = document.createElement('link');
style.rel='stylesheet'; style.href='/assets/walkthrough.css'; document.head.append(style);
const dialog = document.createElement('dialog');
dialog.id='walk-dialog'; dialog.setAttribute('aria-labelledby','walk-title');
const rail=document.createElement('aside');
rail.id='walk-rail'; rail.setAttribute('popover','manual'); rail.setAttribute('aria-labelledby','walk-title');
const wide=matchMedia('(min-width:1280px)');
const content=document.createElement('div');
content.innerHTML = `<header class="walk-head"><h2 id="walk-title">产品走查</h2><button type="button" id="walk-dock" hidden>并排走查</button><button type="button" id="walk-close" aria-label="关闭走查"><i class="ui-glyph ic-x-lg" aria-hidden="true"></i></button></header>
  <nav class="walk-views" aria-label="走查视图"><button type="button" id="walk-compose" aria-pressed="true">写意见</button><button type="button" id="walk-saved" aria-pressed="false">已记录 <span></span></button></nav>
  <form id="walk-form"><div class="walk-location"><div><small id="walk-origin">记录位置</small><p id="walk-location"></p></div><div class="walk-pick-actions"><button type="button" id="walk-pick">点选控件</button><button type="button" id="walk-point" hidden>标记原图</button></div></div>
    <label for="walk-text">修改意见</label><textarea id="walk-text" required maxlength="2000" rows="4" placeholder="你希望这里怎么改？"></textarea>
    <div class="walk-actions"><small class="walk-scope"></small><button type="submit" id="walk-save">保存意见</button></div></form>
  <section id="walk-history" aria-label="已记录的意见" hidden><ol></ol><div class="walk-export" hidden><button type="button" id="walk-copy">复制给 Codex</button><button type="button" id="walk-download">下载 Markdown</button></div></section>
  <p id="walk-status" role="status"></p><button type="button" id="walk-retry" hidden>重试连接</button>`;
dialog.append(content); document.body.append(dialog);
const q = sel => content.querySelector(sel);
const launcher = document.getElementById('walk-launch');
const text = q('#walk-text');
const saveButton=q('#walk-save'), shortcut=document.createElement('kbd');
const mac=/Mac/i.test(navigator.userAgentData?.platform || navigator.platform);
shortcut.textContent=mac?'⌘ ↵':'Ctrl ↵';shortcut.setAttribute('aria-hidden','true');
saveButton.append(shortcut);
saveButton.title=mac?'保存意见（⌘ + Enter）':'保存意见（Ctrl + Enter）';
saveButton.setAttribute('aria-keyshortcuts','Control+Enter Meta+Enter');
const uuid = () => crypto.randomUUID().replaceAll('-','');
let owner, book, context, baseline, draftKey, ident, attempted, records, pick, busy=false, docked=false, generation=0, successTimer;
const drafts = new Map();
let selectedElement;
function markSelection(element) {
  selectedElement?.classList.remove('walk-selected');
  selectedElement=element;
  selectedElement?.classList.add('walk-selected');
}

function status(message) { q('#walk-status').textContent=message; }
function draft() {
  if (!draftKey) return;
  const item = {text:text.value,context,id:ident,attempted};
  const pinned=(context?.target || context?.page_point) && JSON.stringify(context)!==JSON.stringify(baseline);
  if (text.value || pinned) drafts.set(draftKey,item);
  else drafts.delete(draftKey);
  try {
    if (drafts.has(draftKey)) sessionStorage.setItem(draftKey,JSON.stringify(item));
    else sessionStorage.removeItem(draftKey);
  } catch { /* The current tab still retains its draft. */ }
}
function switchView(history) {
  if (history && pick?.page) endPick(null,false);
  if (history) {markSelection(null);showDraftPoint(pointPage(owner),null);}
  q('#walk-form').hidden=history;
  q('#walk-history').hidden=!history;
  q('#walk-compose').setAttribute('aria-pressed',String(!history));
  q('#walk-saved').setAttribute('aria-pressed',String(history));
  if (!history && (dialog.open || docked)) updatePoint();
  status('');
}
function showLocation() {
  const place=q('#walk-location'), full=describeContext(context);
  const signing=context.raw_ref?.startsWith('contract-signing-form/') || context.anchor?.startsWith('form-H') || context.raw_ref?.startsWith('measurement-number/') || context.anchor?.startsWith('number-H');
  const compact=(docked || signing || context.anchor?.startsWith('party-reading-')) && context.screen==='case' && context.rev && (context.target || context.page_point);
  q('#walk-origin').textContent=compact?'底稿 '+context.case_id.slice(0,8)+' · R'+context.rev:'记录位置';
  place.textContent=compact?[context.target || context.doc,context.doc && '第 '+context.page+' 页',context.line && '第 '+context.line+' 行',
    context.page_point && pointLabel(context.page_point)].filter(Boolean).join(' · '):full;
  place.title=full;
  updatePoint();
}
function updatePoint() {
  const view=pointPage(owner), button=q('#walk-point');
  button.hidden=!view; button.disabled=!book || busy;
  if (pick?.page && pick.page!==view) endPick(null,Boolean(owner?.open));
  if ((docked || dialog.open) && !q('#walk-form').hidden) showDraftPoint(view,context);
}
const reader=document.getElementById('page-content');
if (reader) new MutationObserver(changes=>{
  if (!book || !(dialog.open || docked || pick?.page)) return;
  if (changes.some(change=>change.target===reader || change.attributeName==='data-page-sha256')) updatePoint();
}).observe(reader,{childList:true,subtree:true,attributes:true,attributeFilter:['data-page-sha256']});
function draftAddress(position) {
  const address={...position};
  if (address.dialog==='page-dialog' && address.doc) delete address.target;
  return 'fish-walk-draft:'+book.key+':'+JSON.stringify(address);
}
function storedDraft(key) {
  const cached=drafts.get(key);
  if (cached) return cached;
  try {return JSON.parse(sessionStorage.getItem(key));} catch {return null;}
}
function forgetDraft(key) {
  drafts.delete(key);
  try {sessionStorage.removeItem(key);} catch { /* The in-memory draft is already cleared. */ }
}
function prepareDraft(position) {
  baseline=position; context=position; ident=uuid(); attempted='';
  draftKey=draftAddress(position);
  const last=storedDraft(draftKey);
  if (last?.context && !text.value) {
    context=last.context; text.value=last.text; ident=last.id; attempted=last.attempted;
  }
  showLocation();
  if (text.value) draft();
}
function renderedPosition() {
  const next=captureContext(owner);
  // A route change can precede the arrival of its workpaper. Keep the recorded place until it renders.
  if (location.pathname==='/app' && Team.route().page.startsWith('case/') && next.screen!=='case') return null;
  return next;
}
function followLocation() {
  if (!docked || !book || busy || pick || text.value || context!==baseline) return;
  const next=renderedPosition();
  if (next && JSON.stringify(next)!==JSON.stringify(baseline)) prepareDraft(next);
}
function updateDockButton() {
  q('#walk-dock').hidden=docked || !wide.matches || typeof rail.showPopover!=='function';
}
function mountRail() {
  owner=launcher.closest('dialog[open]');
  const host=owner || document.body;
  // A native modal makes its siblings inert. Keep the recorder in the active dialog's focus scope.
  if (rail.parentElement!==host) host.append(rail);
  if (!rail.matches(':popover-open')) rail.showPopover();
}
function leaveRail() {
  if (rail.matches(':popover-open')) rail.hidePopover();
  dialog.append(content); rail.remove(); docked=false;
  document.body.classList.remove('walk-docked'); updateDockButton(); showLocation(); resetButton();
}
function closeRecorder() {
  showDraftPoint(pointPage(owner),null);
  if (docked) {
    draft(); if (pick) endPick(null,false);
    leaveRail(); markSelection(null); launcher.focus({preventScroll:true});
  } else if (dialog.open) dialog.close();
}
q('#walk-dock').onclick=()=>{
  if (!book || !wide.matches || busy) return;
  docked=true; dialog.close(); rail.append(content);
  document.body.classList.add('walk-docked'); mountRail(); updateDockButton(); showLocation(); resetButton();
  (q('#walk-form').hidden?q('#walk-saved'):text).focus({preventScroll:true});
};
launcher.addEventListener('walkthrough-owner-change',()=>{
  if (docked) {mountRail(); followLocation(); updatePoint();}
  else if (pick?.page && !owner?.open) endPick(null,false);
});
wide.addEventListener('change',()=>{
  if (docked && !wide.matches) {
    if (pick) endPick(null,false);
    leaveRail(); dialog.showModal(); (q('#walk-form').hidden?q('#walk-saved'):text).focus();
  }
  updateDockButton();
});
updateDockButton();
function dateLabel(value) {
  return new Date(value).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Shanghai'});
}
function linkTo(note) { return returnUrl(note.context,book.workspace); }
async function readHistory() {
  const token=generation;
  const rows=await book.list();
  if (token!==generation || !(docked || dialog.open)) return;
  // Notes are append-only. A list requested before a save can arrive after its acknowledgement.
  const notes=new Map([...records,...rows].map(note=>[note.id,note]));
  records=[...notes.values()].sort((a,b)=>b.created.localeCompare(a.created) || b.id.localeCompare(a.id));
  renderHistory();
}
function renderHistory() {
  q('#walk-copy-text')?.remove();
  const list=q('#walk-history ol');
  list.replaceChildren();
  for (const item of records) {
    const li=document.createElement('li'), meta=document.createElement('div'), place=document.createElement('a');
    const time=document.createElement('time'), note=document.createElement('p');
    place.href=linkTo(item); place.textContent=describeContext(item.context);
    place.title='回到记录时的页面'; time.dateTime=item.created; time.textContent=dateLabel(item.created);
    place.addEventListener('click',event=>{
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const url=linkTo(item);
      closeRecorder();
      if (url===location.pathname+location.search+location.hash) {
        event.preventDefault();
        if (item.context.screen==='case') { state.openedCitation=null; refresh(); }
        dispatchEvent(new Event('walkthrough-return'));
      }
    });
    meta.append(place,time); note.textContent=item.text; li.append(meta,note); list.append(li);
  }
  if (!records.length) {
    const empty=document.createElement('li'); empty.className='walk-empty'; empty.textContent='还没有保存的意见。'; list.append(empty);
  }
  q('#walk-saved span').textContent=String(records.length);
  q('.walk-export').hidden=!records.length;
}
function markdown() {
  const quote = s => s.split(/\r?\n/).map(l=>'> '+l).join('\n');
  return '# Fish Audit 产品走查\n\n'+records.map((n,i)=>
    '## '+(i+1)+' · '+dateLabel(n.created)+'（北京时间）\n\n'+quote(describeContext(n.context))+
    '\n\n[回到页面]('+new URL(linkTo(n),location.origin).href+')\n\n'+quote(n.text)
  ).join('\n\n')+'\n';
}
function resetButton() {
  clearTimeout(successTimer); launcher.querySelector('span').textContent=docked?'回到走查':'提意见';
}
function endPick(el, reopen=true, pagePoint=null) {
  if (!pick) return;
  const old=pick; pick=null;
  old.controller.abort(); old.mark?.classList.remove('walk-mark');
  if (old.page) {q('#walk-point').textContent='标记原图';saveButton.disabled=!book || busy;}
  launcher.removeAttribute('data-picking'); resetButton(); q('#walk-pick').textContent='点选控件'; status('');
  if (el || pagePoint) {
    const position=renderedPosition();
    if (position && (!pagePoint || (old.page===pointPage(owner) && samePointPage(old.page,{...position,page_point:pagePoint})))) {
      const address=draftAddress(position);
      // When repinning across pages, preserve any independent draft already at the destination.
      if (address!==draftKey && !storedDraft(address)) {
        forgetDraft(draftKey); draftKey=address; baseline=position;
      }
      context=captureContext(owner,el,pagePoint); markSelection(el); showLocation(); draft();
    } else status('底稿正在打开，请稍后再点选。');
  }
  if (reopen) { if (!docked) dialog.showModal(); updatePoint(); text.focus(); }
}
q('#walk-point').onclick=()=>{
  if (pick) {endPick(null);return;}
  const view=pointPage(owner);
  if (!view || !book || busy) return;
  markSelection(null);
  const controller=new AbortController();
  pick={controller,page:view};
  q('#walk-point').textContent='取消标记'; saveButton.disabled=true;
  if (!docked) dialog.close();
  launcher.dataset.picking='true'; launcher.querySelector('span').textContent='取消点选';
  pickPoint(view,samePointPage(view,context)?context.page_point:null,controller.signal,p=>endPick(null,true,p));
};
function choosePosition() {
  if (pick) {endPick(null);return;}
  markSelection(null);
  document.querySelectorAll('.walk-mark').forEach(el=>el.classList.remove('walk-mark'));
  if (!docked) dialog.close();
  const controller=new AbortController();
  pick={controller,mark:null};
  launcher.dataset.picking='true'; launcher.querySelector('span').textContent='取消点选';
  if (docked) {q('#walk-pick').textContent='取消点选'; status('点选页面中的控件，按 Esc 取消。');}
  const options={capture:true,signal:controller.signal};
  const select=target=>{
    if (!(target instanceof Element) || target.closest('#walk-launch,#walk-dialog,#walk-rail')) return null;
    return target.closest('button,a,input,select,textarea,label,summary,[role=tab],[role=switch],h1,h2,h3,h4,[data-warranty-order],[data-warranty-note],[data-board-note],[data-board-row],[data-party-reading],#board-unavailable,.quality-order,.warranty-certificate,[data-finding]') || target;
  };
  document.addEventListener('pointerover',e=>{
    const el=select(e.target);
    pick.mark?.classList.remove('walk-mark'); pick.mark=el; el?.classList.add('walk-mark');
  },options);
  const stop=e=>{e.preventDefault();e.stopImmediatePropagation();};
  for (const name of ['pointerdown','mousedown','pointerup','mouseup','contextmenu']) document.addEventListener(name,stop,options);
  document.addEventListener('click',e=>{stop(e);endPick(select(e.target));},options);
  document.addEventListener('keydown',e=>{
    if (e.isComposing || e.keyCode===229) return;
    if (e.key==='Escape') {stop(e);endPick(null);}
    else if (e.key==='Enter' || e.key===' ') {stop(e);endPick(select(e.target));}
  },options);
}
q('#walk-pick').onclick=choosePosition;
q('#walk-close').onclick=closeRecorder;
q('#walk-compose').onclick=()=>{switchView(false);text.focus();};
q('#walk-saved').onclick=async()=>{
  const token=generation;
  switchView(true);
  if (!book) return;
  try { await readHistory(); }
  catch (err) {if (token===generation) status('清单未载入，请再次点「已记录」。'+err.message);}
};
text.addEventListener('input',draft);
text.addEventListener('focus',followLocation);
text.addEventListener('beforeinput',followLocation);
text.addEventListener('keydown',event=>{
  if (event.key==='Enter' && (event.ctrlKey || event.metaKey) && !event.shiftKey && !event.altKey &&
      !event.isComposing && event.keyCode!==229 && !event.repeat && !saveButton.disabled) {
    event.preventDefault();q('#walk-form').requestSubmit(saveButton);
  }
});
dialog.addEventListener('close',()=>{ if (!docked && !pick && !dialog.open) {markSelection(null); showDraftPoint(pointPage(owner),null); draft(); launcher.focus({preventScroll:true});} });
content.addEventListener('keydown',e=>{
  if (e.key==='Escape') {
    e.stopPropagation();
    if (!e.isComposing && e.keyCode!==229) {e.preventDefault(); closeRecorder();}
  }
});
q('#walk-form').addEventListener('submit',async event=>{
  event.preventDefault();
  if (pick?.page) return;
  if (busy || !book || !text.value.trim()) { if (!text.value.trim()) {status('请填写修改意见');text.focus();} return; }
  const token=generation, body=text.value.trim(), key=JSON.stringify([body,context]);
  if (attempted && attempted!==key) ident=uuid();
  attempted=key; draft(); busy=true; saveButton.disabled=true; text.readOnly=true; q('#walk-pick').disabled=true; updatePoint(); status('正在保存…');
  try {
    const saved=await book.save({id:ident,text:body,context});
    if (generation!==token) return;
    records=[saved,...records.filter(n=>n.id!==saved.id)]; renderHistory();
    text.value=''; context=baseline; forgetDraft(draftKey);
    draftKey=null;
    if (docked) {
      markSelection(null); prepareDraft(renderedPosition() || baseline); status('意见已保存。');
      if (!q('#walk-form').hidden && (content.contains(document.activeElement) || document.activeElement===document.body)) text.focus({preventScroll:true});
    } else {
      dialog.close(); launcher.querySelector('span').textContent='已记录'; successTimer=setTimeout(resetButton,1700);
    }
  } catch (err) { if (generation===token) status('保存失败，意见已保留。'+err.message); }
  finally {if (generation===token) {busy=false;saveButton.disabled=false;text.readOnly=false;q('#walk-pick').disabled=false;updatePoint();}}
});
q('#walk-copy').onclick=async()=>{
  const token=generation,content=markdown();
  try {await navigator.clipboard.writeText(content);status('已复制，可以粘贴到 Codex。');}
  catch {
    if (token!==generation || !(docked || dialog.open)) return;
    const area=q('#walk-copy-text') || document.createElement('textarea');
    area.id='walk-copy-text'; area.readOnly=true; area.setAttribute('aria-label','可复制的 Markdown 清单');
    q('#walk-history').append(area); area.value=content; area.focus(); area.select();
    let copied=false;
    try {copied=document.execCommand('copy');} catch { /* Leave the selected text available. */ }
    if (copied) {
      area.remove(); q('#walk-copy').focus(); status('已复制，可以粘贴到 Codex。');
    } else status('已选中清单，可手动复制或下载 Markdown。');
  }
};
q('#walk-download').onclick=()=>{
  const url=URL.createObjectURL(new Blob([markdown()],{type:'text/markdown;charset=utf-8'}));
  const a=document.createElement('a'); a.href=url; a.download='Fish-Audit-走查意见.md'; a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1500);
};
function clearRecorder() {
  if (pick) endPick(null,false);
  closeRecorder(); draft(); draftKey=null; book=null; generation++; records=[]; text.value='';
  baseline=null; context=null; markSelection(null); q('#walk-location').textContent=''; q('#walk-location').title='';
  q('#walk-origin').textContent='记录位置'; q('.walk-scope').textContent=''; status(''); renderHistory();
}
addEventListener('hashchange',()=>{
  if (pick) endPick(null,false);
  if (docked && (location.pathname==='/' || book?.workspace===Team.route().id &&
      (book.key==='local' || book.author===(Team.session?.user?.id || 'guest')))) return;
  clearRecorder();
});
addEventListener('audit-account-change',clearRecorder);
addEventListener('storage',event=>{
  if (event.key==='fish-audit-account-change' && event.storageArea===localStorage) clearRecorder();
});
export async function openRecorder(sourceDialog) {
  if (pick) {endPick(null);return;}
  if (docked) {(q('#walk-form').hidden?q('#walk-saved'):text).focus();return;}
  if (dialog.open) return;
  resetButton();
  generation++;
  owner=sourceDialog; book=null; busy=false; draftKey=null; records=[];
  baseline=captureContext(owner); context=baseline; ident=uuid(); attempted='';
  text.value=''; text.readOnly=false; showLocation(); renderHistory(); switchView(false);
  q('#walk-dock').disabled=true; saveButton.disabled=true; q('#walk-pick').disabled=true; q('#walk-saved').disabled=true;
  q('.walk-scope').textContent='';
  dialog.showModal(); text.focus();
  await connect();
}
q('#walk-retry').onclick=connect;
async function connect() {
  const token=generation;
  q('#walk-retry').hidden=true; status('正在打开清单…');
  try {
    const store=await notebook();
    if (token!==generation || !dialog.open) return;
    book=store;
    prepareDraft(baseline);
    q('.walk-scope').textContent=book.label;
    q('#walk-dock').disabled=false;saveButton.disabled=false;q('#walk-pick').disabled=false;q('#walk-saved').disabled=false;
    status('');
    await readHistory();
  } catch (err) {
    if (token===generation && (docked || dialog.open)) {
      q('#walk-retry').hidden=Boolean(book);
      status((book?'清单未载入，可再次点「已记录」。':'暂时无法连接，已输入的意见仍在这里。')+err.message);
    }
  }
}
