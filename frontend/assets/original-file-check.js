// Check the fetched bytes against the digest of the selected, issued revision.
function originalFileCheck(url,expected) {
  const row=document.createElement('div'),button=document.createElement('button'),result=document.createElement('output');
  row.className='agreement-check';button.textContent='核对当前文件';
  button.type='button';
  button.addEventListener('click',async()=>{
    if (button.getAttribute('aria-disabled')==='true') return;
    if (!globalThis.crypto?.subtle) {result.textContent='此浏览器无法计算 SHA-256';return;}
    button.setAttribute('aria-disabled','true');row.dataset.state='checking';result.textContent='正在核对…';
    try {
      const reply=await fetch(url,{cache:'no-store',mode:'same-origin',credentials:'same-origin'});
      if (!reply.ok) throw new Error('Original unavailable');
      const hashed=await crypto.subtle.digest('SHA-256',await reply.arrayBuffer());
      const actual=Array.from(new Uint8Array(hashed),byte=>byte.toString(16).padStart(2,'0')).join('');
      const matches=actual===expected;
      row.dataset.state=matches?'match':'mismatch';
      result.textContent=matches?'文件与本版留存摘要一致':'文件与本版留存摘要不符';
    } catch {
      row.dataset.state='unavailable';result.textContent='原件读取失败，可以重试';
    } finally {button.removeAttribute('aria-disabled');}
  });
  row.append(button,result);return row;
}
