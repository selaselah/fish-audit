/* Workspace identity is resolved from the URL. The server checks every scoped request. */
const Team = {
  session: null,
  current: null,
  authMode: 'login',
  roles: {admin:'管理员', auditor:'审计人员', employee:'员工'},
  route() {
    const [raw, query] = location.hash.slice(1).split("?");
    const params = new URLSearchParams(query);
    const match = /^w\/([a-f0-9]{32})(?:\/(.*))?$/.exec(raw);
    return match ? {id:match[1], page:match[2] || 'desk',params} : {id:null,page:raw || 'desk',params};
  },
  hash(page) { return '#' + (this.current ? 'w/' + this.current.id + '/' : '') + page; },
  paperLink(label, caseId, className, params) {
    const suffix = params ? '?'+params : '';
    const path = (this.current ? '/w/'+this.current.id : '')+'/workpaper/'+caseId+suffix;
    const target = this.hash('case/'+caseId+suffix);
    const anchor = link(label,path,className);
    anchor.addEventListener('click',event=>{
      if (event.button===0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) {
        event.preventDefault(); location.hash = target;
      }
    });
    return anchor;
  },
  cases() { return (this.current ? '/api/w/' + this.current.id : '/api') + '/cases'; },
  async load() { this.session = await api('/api/session'); return this.session; },
  syncNav() {
    const signed = this.session.user;
    const guest = !signed && this.session.mode === 'saas';
    $('#nav-desk').hidden = guest;
    $('#nav-account').textContent = this.current?.name || signed?.name || '企业登录';
    $('#nav-team').hidden = this.current?.role !== 'admin';
    $('#nav-library').hidden = this.current?.role === 'employee' || (!signed && this.session.mode === 'saas');
    $('#nav-library').href = this.hash('library');
    const name = this.current?.name || '本机工作区';
    $('#workspace-name').textContent = name;
    $('#library-scope').textContent = name;
    $('#nav-team').href = this.hash('team');
    $('#nav-desk').href = this.hash('desk');
    $('#nav-rules').href = this.hash('rules');
    $('.brand').href = guest ? '#account' : this.hash('desk');
    for (const back of document.querySelectorAll('.back')) back.href = guest ? '#account' : this.hash('desk');
    $('#rules .back').textContent = guest ? '返回企业登录' : '返回工作台';
  },
  field(form, title, key, options = {}) {
    const field = el('input');
    field.name = key; field.required = true; field.type = options.type || 'text';
    field.maxLength = options.max || 80; field.autocomplete = options.auto || 'off';
    if (options.min) field.minLength = options.min;
    const label = el('label',title); label.append(field); form.append(label);
    return field;
  },
  submit(form, title, callback) {
    const error = el('p'); error.setAttribute('role','alert');
    const button = el('button',title,'primary'); button.type = 'submit';
    form.append(error, button); form.addEventListener('submit',async event => {
      event.preventDefault(); button.disabled = true; error.textContent = '';
      try { await callback(Object.fromEntries(new FormData(form))); }
      catch (problem) { error.textContent = problem.message; }
      finally { button.disabled = false; }
    });
  },
  async logout() {
    await post('/api/auth/logout',{});
    Desk.reset(); this.authMode = 'login'; this.freshInvite = null;
    this.session = null; this.current = null; state.bundle = null; state.detail = null; state.cases = [];
    for (const id of ['case-panel','case-list','team-panel']) $('#'+id).replaceChildren();
    location.hash = 'account'; await refresh();
  },
  go(id) { location.hash = 'w/' + id + '/desk'; },
  account(invite) {
    const panel = $('#account-panel'); panel.replaceChildren();
    const session = this.session;
    $('#account-title').textContent = invite ? '加入企业' : '企业工作区';
    if (session.user) {
      const user = session.user;
      const current = box('panel',el('h2',user.name),el('p',user.login,'muted'));
      current.append(action('退出登录',()=>this.logout().catch(alertText),'plain'));
      if (invite) {
        const form = el('form'); form.append(el('p','使用当前账号接受企业邀请。'));
        this.submit(form,'接受邀请',async () => {
          const data = await post('/api/workspaces/join',{invite}); await this.load(); this.go(data.selected);
        }); current.append(form);
      }
      const list = box('panel',el('h2','我的企业'));
      for (const space of session.workspaces) list.append(box('line panel-head',
        box('',el('strong',space.name),el('small',this.roles[space.role],'small')),
        link('进入工作区','#w/'+space.id+'/desk','button')));
      if (!session.workspaces.length) list.append(el('p','可创建企业或打开管理员发给你的邀请链接。'));
      const form = el('form'); this.field(form,'企业名称','name');
      this.submit(form,'创建企业',async data => {
        const result = await post('/api/workspaces',data); await this.load(); this.go(result.selected);
      });
      list.append(fold('创建新的企业工作区',form)); panel.append(box('account-grid',current,list));
      return;
    }
    const registering = this.authMode === 'register';
    const form = el('form','','panel auth-card');
    form.append(el('h2',registering ? (invite ? '注册并加入企业' : '开通企业工作区') : '登录工作区'));
    if (registering && !invite) this.field(form,'企业名称','workspace');
    if (registering) this.field(form,'姓名','name',{max:50,auto:'name'});
    this.field(form,'登录名','login',{min:3,auto:'username'});
    this.field(form,registering?'密码（至少 12 个字符）':'密码','password',{type:'password',max:128,
      min:registering?12:1,auto:registering?'new-password':'current-password'});
    this.submit(form,registering ? '注册并进入' : '登录',async data => {
      if (invite && registering) data.invite = invite;
      const info = await post('/api/auth/'+(registering?'register':'login'),data);
      this.session = info;
      if (invite && !registering) {
        const result = await post('/api/workspaces/join',{invite}); await this.load(); this.go(result.selected); return;
      }
      const next = info.selected || info.workspaces[0]?.id;
      const wanted = this.returnTo;
      this.returnTo = null;
      if (wanted && info.workspaces.some(w=>wanted.startsWith('#w/'+w.id+'/'))) location.hash = wanted;
      else if (next) this.go(next); else { location.hash = 'account'; await refresh(); }
    });
    form.append(action(registering?'已有账号，去登录':(invite?'创建账号并接受邀请':'创建企业账号'),()=>{
      this.authMode = registering?'login':'register'; this.account(invite);
    },'text-button'));
    const info = box('auth-aside',el('h2','从资料提交到审计签收'),el('p','员工提交票据，审计人员逐项核对引文。企业管理员管理成员与权限。'));
    if (session.mode === 'local') info.append(link('打开本机工作台','#desk','button'));
    panel.append(box('account-grid',form,info));
  },
  usagePanel(usage) {
    const limits = usage.limits;
    const list = el('dl','','usage-list');
    const rows = [
      ['本月新建任务',usage.monthly_cases+' / '+limits.monthly_cases],
      ['正在排队或处理',usage.active_cases+' / '+limits.active_cases],
      ['原件存储',(usage.storage_bytes/1048576).toLocaleString('zh-CN',{maximumFractionDigits:2})+' / '+limits.storage_mib+' MiB'],
      ['本月模型请求',usage.requests+' / '+limits.monthly_requests],
      ['模型已报告的输入 / 输出 token',usage.input_tokens.toLocaleString('zh-CN')+' / '+usage.output_tokens.toLocaleString('zh-CN')],
    ];
    for (const [title,value] of rows) list.append(el('dt',title),el('dd',value));
    const panel = box('panel',box('panel-head',el('h2','企业用量'),el('small',usage.period+' · 北京时间','small')),list);
    if (usage.unreported) panel.append(el('p',usage.unreported+' 次请求尚无完整 token 回执。','muted'));
    return panel;
  },
  async team(epoch) {
    const space = this.current; const url = '/api/workspaces/'+space.id;
    const data = await api(url+'/team'); if (epoch !== state.epoch) return;
    const list = box('panel',el('h2',space.name+' · 成员'));
    for (const member of data.members) {
      const group = box('panel-head line',box('',el('strong',member.name),el('small',member.login,'small')));
      const select = el('select'); select.setAttribute('aria-label',member.name+'的角色');
      for (const [value,title] of Object.entries(this.roles)) select.add(new Option(title,value,false,value===member.role));
      select.add(new Option('移出企业','remove'));
      const update = action('保存', async ()=>{
        if (select.value==='remove' && !window.confirm('确认将 '+member.name+' 移出此企业？')) return;
        update.disabled=true;
        try { await post(url+'/members/'+member.id,{role:select.value}); await this.load(); await refresh(); }
        catch(error){alertText(error);} finally {update.disabled=false;}
      }); group.append(box('flow',select,update)); list.append(group);
    }
    const form = el('form','','panel'); form.append(el('h2','邀请成员'));
    const label = el('label','邀请角色'); const select = el('select'); select.name='role';
    select.add(new Option('员工 · 提交和跟踪自己的资料','employee'));
    select.add(new Option('审计人员 · 核查企业资料并验收','auditor'));label.append(select);form.append(label);
    this.submit(form,'生成邀请链接',async values=>{
      const invite=await post(url+'/invites',values);
      this.freshInvite={workspace:space.id,id:invite.id,url:location.origin+location.pathname+'#invite/'+invite.token};await refresh();
    });
    const fresh=this.freshInvite;
    if (fresh?.workspace===space.id && data.invites.some(row=>row.id===fresh.id)) {
      const input=el('input');input.value=fresh.url;input.readOnly=true;input.setAttribute('aria-label','本次生成的邀请链接');
      const copy=action('复制链接',async()=>{try{await navigator.clipboard.writeText(input.value);copy.textContent='已复制';}
        catch{input.focus();input.select();}});
      form.append(el('p','此链接 72 小时内可使用一次，请直接交给受邀人。','muted'),input,copy);
    }
    const invites=box('panel',el('h2','待使用的邀请'));
    for(const item of data.invites) invites.append(box('line panel-head',el('span',this.roles[item.role]+' · '+time(item.expires*1000)+' 到期'),
      action('撤销',async()=>{try{await post(url+'/invites/'+item.id+'/cancel',{});await refresh();}catch(e){alertText(e);}})));
    if(!data.invites.length) invites.append(el('p','暂无待使用的邀请。','muted'));
    const names={workspace_created:'创建企业',invite_created:'生成邀请',invite_accepted:'接受邀请',invite_cancelled:'撤销邀请',member_changed:'变更成员权限'};
    const timeline=fold('查看成员操作记录',...data.events.map(row=>box('line',el('strong',row.actor+' · '+names[row.action]),
      el('small',time(row.at*1000)+' · '+(this.roles[row.target]||row.target),'small'))));
    $('#team-panel').replaceChildren(box('grid',box('',list,this.usagePanel(data.usage)),box('',form,invites)),timeline);
  }
};
