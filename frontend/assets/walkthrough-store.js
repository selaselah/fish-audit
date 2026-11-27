async function json(url, options) {
  const reply = await fetch(url, options);
  const data = await reply.json();
  if (!reply.ok) throw new Error(data.error || '走查记录未载入');
  return data;
}

// The public SaaS page has no business workspace. Keep its notes in this browser.
function browserNotebook(author) {
  const prefix = 'fish-walk-public:'+author+':';
  return {
    key:prefix, workspace:null, author, label:'本浏览器 · 公开页',
    async list() {
      const items = Object.keys(localStorage).filter(k=>k.startsWith(prefix)).map(k=>JSON.parse(localStorage.getItem(k)));
      return items.sort((a,b)=>b.created.localeCompare(a.created) || b.id.localeCompare(a.id));
    },
    async save(data) {
      if (!['home','account','rules'].includes(data.context.screen)) throw new Error('请进入所属企业工作区记录这条意见');
      const key = prefix+data.id;
      const previous = localStorage.getItem(key);
      if (previous) {
        const item = JSON.parse(previous);
        if (item.text!==data.text || JSON.stringify(item.context)!==JSON.stringify(data.context)) throw new Error('已有不同内容，请重新打开走查');
        return item;
      }
      const item = {...data, created:new Date().toISOString()};
      localStorage.setItem(key, JSON.stringify(item));
      return item;
    },
  };
}

export async function notebook() {
  const session = await json('/api/session');
  const wid = location.pathname === '/app' ? Team.route().id : null;
  const member = session.workspaces.find(w=>w.id===wid);
  if (wid && !member) throw new Error('请先登录并进入所属企业再记录意见');
  if (!wid && session.mode==='saas') return browserNotebook(session.user?.id || 'guest');
  const url = (wid ? '/api/w/'+wid : '/api') + '/walkthrough';
  return {
    workspace:wid, author:session.user?.id, key:wid ? wid+'/'+session.user.id : 'local', label:wid ? '本企业 · 仅自己可见' : '本机走查清单',
    async list() { return (await json(url)).notes; },
    async save(note) {
      const headers = {'Content-Type':'application/json'};
      if (wid) headers['X-CSRF-Token']=session.csrf;
      return (await json(url,{method:'POST',headers,body:JSON.stringify(note)})).note;
    },
  };
}
