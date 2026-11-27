import {captureContext, describeContext, returnUrl} from './walkthrough-context.js';
import {notebook} from './walkthrough-store.js';

const style = document.createElement('link');
style.rel='stylesheet'; style.href='/assets/walkthrough.css'; document.head.append(style);
const dialog = document.createElement('dialog');
dialog.id='walk-dialog'; dialog.setAttribute('aria-labelledby','walk-title');
dialog.innerHTML = `<header class="walk-head"><h2 id="walk-title">产品走查</h2><button type="button" id="walk-close" aria-label="关闭走查"><i class="ui-glyph ic-x-lg" aria-hidden="true"></i></button></header>
  <nav class="walk-views" aria-label="走查视图"><button type="button" id="walk-compose" aria-pressed="true">写意见</button><button type="button" id="walk-saved" aria-pressed="false">已记录 <span></span></button></nav>
  <form id="walk-form"><div class="walk-location"><div><small>当前位置</small><p id="walk-location"></p></div><button type="button" id="walk-pick">点选控件</button></div>
    <label for="walk-text">修改意见</label><textarea id="walk-text" required maxlength="2000" rows="4" placeholder="你希望这里怎么改？"></textarea>
    <div class="walk-actions"><small class="walk-scope"></small><button type="submit" id="walk-save">保存意见</button></div></form>
  <section id="walk-history" aria-label="已记录的意见" hidden><ol></ol><div class="walk-export" hidden><button type="button" id="walk-copy">复制给 Codex</button><button type="button" id="walk-download">下载 Markdown</button></div></section>
  <p id="walk-status" role="status"></p><button type="button" id="walk-retry" hidden>重试连接</button>`;
document.body.append(dialog);
const q = sel => dialog.querySelector(sel);
const launcher = document.getElementById('walk-launch');
const text = q('#walk-text');
const uuid = () => crypto.randomUUID().replaceAll('-','');
let owner, book, context, baseline, draftKey, ident, attempted, records, pick, busy=false, generation=0, successTimer;
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
  if (text.value || context?.target) drafts.set(draftKey,item); else drafts.delete(draftKey);
  try {
    if (drafts.has(draftKey)) sessionStorage.setItem(draftKey,JSON.stringify(item));
    else sessionStorage.removeItem(draftKey);
  } catch { /* The current tab still retains its draft. */ }
}
function switchView(history) {
  if (history) markSelection(null);
  q('#walk-form').hidden=history;
  q('#walk-history').hidden=!history;
  q('#walk-compose').setAttribute('aria-pressed',String(!history));
  q('#walk-saved').setAttribute('aria-pressed',String(history));
  status('');
}
function showLocation() { q('#walk-location').textContent=describeContext(context); }
function dateLabel(value) {
  return new Date(value).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Shanghai'});
}
function linkTo(note) { return returnUrl(note.context,book.workspace); }
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
      dialog.close();
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
  clearTimeout(successTimer); launcher.querySelector('span').textContent='提意见';
}
function endPick(el, reopen=true) {
  if (!pick) return;
  const old=pick; pick=null;
  old.controller.abort(); old.mark?.classList.remove('walk-mark');
  launcher.removeAttribute('data-picking'); resetButton();
  if (el) { context=captureContext(owner,el); markSelection(el); showLocation(); draft(); }
  if (reopen) { dialog.showModal(); text.focus(); }
}
function choosePosition() {
  markSelection(null);
  document.querySelectorAll('.walk-mark').forEach(el=>el.classList.remove('walk-mark'));
  dialog.close();
  const controller=new AbortController();
  pick={controller,mark:null};
  launcher.dataset.picking='true'; launcher.querySelector('span').textContent='取消点选';
  const options={capture:true,signal:controller.signal};
  const select=target=>{
    if (!(target instanceof Element) || target.closest('#walk-launch,#walk-dialog')) return null;
    return target.closest('button,a,input,select,textarea,label,summary,[role=tab],[role=switch],h1,h2,h3,h4,[data-warranty-order],[data-warranty-note],[data-board-note],[data-board-row],#board-unavailable,.warranty-certificate,[data-finding]') || target;
  };
  document.addEventListener('pointerover',e=>{
    const el=select(e.target);
    pick.mark?.classList.remove('walk-mark'); pick.mark=el; el?.classList.add('walk-mark');
  },options);
  const stop=e=>{e.preventDefault();e.stopImmediatePropagation();};
  for (const name of ['pointerdown','mousedown','pointerup','mouseup','contextmenu']) document.addEventListener(name,stop,options);
  document.addEventListener('click',e=>{stop(e);endPick(select(e.target));},options);
  document.addEventListener('keydown',e=>{
    if (e.key==='Escape') {stop(e);endPick(null);}
    else if (e.key==='Enter' || e.key===' ') {stop(e);endPick(select(e.target));}
  },options);
}
q('#walk-pick').onclick=choosePosition;
q('#walk-close').onclick=()=>dialog.close();
q('#walk-compose').onclick=()=>{switchView(false);text.focus();};
q('#walk-saved').onclick=async()=>{
  const token=generation;
  switchView(true);
  if (!book) return;
  try { const rows=await book.list(); if (token===generation) {records=rows;renderHistory();} }
  catch (err) {if (token===generation) status('清单未载入，请再次点「已记录」。'+err.message);}
};
text.addEventListener('input',draft);
dialog.addEventListener('close',()=>{ if (!pick && !dialog.open) {markSelection(null); draft(); launcher.focus({preventScroll:true});} });
dialog.addEventListener('keydown',e=>{if (e.key==='Escape') e.stopPropagation();});
q('#walk-form').addEventListener('submit',async event=>{
  event.preventDefault();
  if (busy || !book || !text.value.trim()) { if (!text.value.trim()) {status('请填写修改意见');text.focus();} return; }
  const token=generation, body=text.value.trim(), key=JSON.stringify([body,context]);
  if (attempted && attempted!==key) ident=uuid();
  attempted=key; draft(); busy=true; q('#walk-save').disabled=true; status('正在保存…');
  try {
    const saved=await book.save({id:ident,text:body,context});
    if (generation!==token) return;
    records=[saved,...records.filter(n=>n.id!==saved.id)]; renderHistory();
    text.value=''; context=baseline; draft(); draftKey=null;
    dialog.close(); launcher.querySelector('span').textContent='已记录'; successTimer=setTimeout(resetButton,1700);
  } catch (err) { if (generation===token) status('保存失败，意见已保留。'+err.message); }
  finally {if (generation===token) {busy=false;q('#walk-save').disabled=false;}}
});
q('#walk-copy').onclick=async()=>{
  const token=generation,content=markdown();
  try {await navigator.clipboard.writeText(content);status('已复制，可以粘贴到 Codex。');}
  catch {
    if (token!==generation || !dialog.open) return;
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
addEventListener('hashchange',()=>{
  if (pick) endPick(null,false);
  if (dialog.open) dialog.close();
  draft(); draftKey=null; book=null; generation++;
});
export async function openRecorder(sourceDialog) {
  if (pick) {endPick(null);return;}
  if (dialog.open) return;
  resetButton();
  generation++;
  owner=sourceDialog; book=null; busy=false; draftKey=null; records=[];
  baseline=captureContext(owner); context=baseline; ident=uuid(); attempted='';
  text.value=''; showLocation(); renderHistory(); switchView(false);
  q('#walk-save').disabled=true; q('#walk-pick').disabled=true; q('#walk-saved').disabled=true;
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
    book=store; draftKey='fish-walk-draft:'+book.key+':'+JSON.stringify(baseline);
    let last=drafts.get(draftKey);
    try {last=last || JSON.parse(sessionStorage.getItem(draftKey));} catch { /* Storage can be disabled. */ }
    if (last?.context && !text.value) {context=last.context; text.value=last.text;ident=last.id;attempted=last.attempted;showLocation();}
    q('.walk-scope').textContent=book.label;
    q('#walk-save').disabled=false;q('#walk-pick').disabled=false;q('#walk-saved').disabled=false;
    status('');
    const rows=await store.list();
    if (token===generation && dialog.open) {records=rows;renderHistory();}
  } catch (err) {
    if (token===generation && dialog.open) {
      q('#walk-retry').hidden=Boolean(book);
      status((book?'清单未载入，可再次点「已记录」。':'暂时无法连接，已输入的意见仍在这里。')+err.message);
    }
  }
}
