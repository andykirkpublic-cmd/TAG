'use strict';
const root = document.querySelector('#app');
let me, csrf='', data, tab='overview', timer, busy=false, deviceState, connected=false, holdTimer, held=false;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const time = value => value ? new Date(value*1000).toLocaleString('en-GB',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}) : '—';
const brand = '<span class="brand">TAG<span class="brand-dot">.</span></span>';
function toast(message){const el=document.querySelector('#toast');el.textContent=message;el.classList.add('show');clearTimeout(el.timeout);el.timeout=setTimeout(()=>el.classList.remove('show'),6000);}
async function api(path, body){
  const res=await fetch('/api'+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store',signal:AbortSignal.timeout(10000)});
  let result;try{result=await res.json();}catch{throw new Error('The server could not complete that request. Please try again.');}
  if(!res.ok){const err=new Error(result.error||'Request failed.');err.status=res.status;throw err;}return result;
}
function formData(form){return Object.fromEntries(new FormData(form));}
function button(text, extra=''){return `<button ${extra}>${text}</button>`;}
function login(){
  clearInterval(timer);
  root.innerHTML=`<main class="entry"><section class="entry-story">${brand}<div><span class="eyebrow">A little connection. A lot of reassurance.</span><h1>Close to home.<br>Present at school.</h1><p>The messages that matter, without a smartphone.</p></div><small>School & family communication · Software pilot</small></section><section class="entry-form"><div class="form-wrap"><span class="eyebrow">WELCOME TO TAG</span><h2>Good to see you.</h2><p class="muted">Sign in with the account provided by your school.</p><form id="login"><label>Email address<input name="email" type="email" autocomplete="username" required></label><label>Password<input name="password" type="password" autocomplete="current-password" required maxlength="256"></label><button class="primary wide">Sign in <span>→</span></button></form><p class="small muted">Need access or a password reset? Contact your school’s TAG administrator.</p><a class="device-link" href="/device">Open the virtual TAG device ↗</a></div></section></main>`;
  document.querySelector('#login').onsubmit=async e=>{e.preventDefault();await action(e.target,async()=>{await api('/login',formData(e.target));await boot();});};
}
async function action(form, fn){
  const buttons=[...form.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
  try{await fn();}catch(err){toast(err.message);}finally{buttons.forEach(b=>b.disabled=false);}
}
function passwordScreen(){
  root.innerHTML=`<main class="narrow">${brand}<h1>Make it yours.</h1><p>Choose a private password before opening your account.</p><form id="password"><label>Temporary or current password<input type="password" name="current" autocomplete="current-password" required></label><label>New password · at least 12 characters<input type="password" name="password" autocomplete="new-password" minlength="12" maxlength="256" required></label><button class="primary">Save password</button></form></main>`;
  document.querySelector('#password').onsubmit=e=>{e.preventDefault();action(e.target,async()=>{await api('/password',formData(e.target));await boot();});};
}
function shell(){
  const staff=me.user.role==='staff';
  root.innerHTML=`<div class="layout"><aside>${brand}<div class="school-name">${esc(me.school)}<span>${staff?'School console':'Family space'}</span></div><nav><button data-tab="overview">◉ <span>Overview</span></button><button data-tab="messages">↗ <span>Messages</span></button>${staff?'<button data-tab="setup">⊞ <span>People & devices</span></button>':''}</nav><div class="sidebar-bottom"><a href="/device" target="_blank" rel="noopener">Virtual TAG ↗</a><div class="pilot-label">SOFTWARE PILOT</div><p>Simple connection.<br>Room to be a child.</p></div></aside><div class="workspace"><header><span id="connection" class="connection">Connecting…</span><div class="account"><span>${esc(me.user.name)}</span><button id="account-password" class="quiet">Password</button><button id="logout" class="quiet">Sign out</button></div></header><main id="content"></main><footer>TAG · Messages go straight through. Replies stay simple.</footer></div></div>`;
  document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;renderPage();});
  document.querySelector('#logout').onclick=async()=>{try{await api('/logout',{});login();}catch(e){toast(e.message);}};
  document.querySelector('#account-password').onclick=()=>{clearInterval(timer);passwordScreen();};
}
function connection(ok){const el=document.querySelector('#connection');if(el){el.textContent=ok?'Connected · updates every 5 seconds':'Offline · displayed information may be out of date';el.classList.toggle('offline',!ok);}}
async function refresh(initial=false){
  if(busy)return;busy=true;
  try{data=await api('/dashboard');connection(true);if(initial)renderPage();else renderLive();}
  catch(e){connection(false);if(e.status===401){login();}else if(initial)toast(e.message);}
  finally{busy=false;}
}
function renderPage(){
  document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));
  const staff=me.user.role==='staff', first=me.user.name.split(' ')[0];
  document.querySelector('#content').innerHTML=`<div class="page-title"><div><span class="eyebrow">${staff?'YOUR SCHOOL, CONNECTED':'A LITTLE PEACE OF MIND'}</span><h1>${tab==='overview'?`Hello, ${esc(first)}.`:tab==='messages'?'A few words. A clear reply.':'People & devices.'}</h1><p>${tab==='overview'?'See what’s happening, and send what matters.':tab==='messages'?'A notice to acknowledge. A question with a real choice.':'Give each family a secure connection to their child.'}</p></div><span class="date">${new Date().toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long'})}</span></div><section id="alerts" aria-label="Help requests" aria-live="polite"></section>${tab==='setup'?'<div id="setup"></div>':`<div id="stats" class="stats"></div><div class="main-grid"><section><div class="section-heading"><h2>${staff?'Children':'Your children'}</h2><span class="muted small">Device & message activity</span></div><div id="children"></div></section><section class="card compose"><span class="eyebrow">SEND A MESSAGE</span><h2>A small check-in.</h2><form id="compose"><label>To<select name="child_id" required>${data.children.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></label><fieldset><legend>Message type</legend><div class="type-options"><label><input type="radio" name="kind" value="NOTICE" checked><span><strong>Notice</strong><small>Acknowledge only</small></span></label><label><input type="radio" name="kind" value="QUESTION"><span><strong>Question</strong><small>Yes or no</small></span></label></div></fieldset><label>Message<textarea name="body" maxlength="240" rows="4" placeholder="Grandad is picking you up at the usual time." required></textarea></label><div class="compose-meta"><span id="char-count">0 / 240</span><span>Expires after 24 hours</span></div><button class="primary wide" ${data.children.length?'':'disabled'}>Send to TAG <span>↗</span></button></form><p class="small muted">Delivered directly. A response appears when your child presses a button.</p></section></div><section class="card history"><div class="section-heading"><h2>Message history</h2><span class="small muted">Most recent 50 per child</span></div><div id="history"></div></section>`}`;
  if(tab==='setup'){setup();}else{
    const form=document.querySelector('#compose');form.dataset.key=crypto.randomUUID();
    form.body.oninput=()=>document.querySelector('#char-count').textContent=`${form.body.value.length} / 240`;
    form.onsubmit=e=>{e.preventDefault();action(form,async()=>{await api('/messages',{...formData(form),request_key:form.dataset.key});form.body.value='';form.dataset.key=crypto.randomUUID();document.querySelector('#char-count').textContent='0 / 240';toast('Message queued for TAG.');await refresh();});};
  }
  renderLive();
}
function status(m){if(m.response)return {label:m.response==='ACK'?'Acknowledged':`Answered ${m.response.toLowerCase()}`,cls:'success'};if(m.expires<=data.server_time)return {label:'Expired',cls:'muted'};return m.delivered?{label:'Delivered · awaiting reply',cls:'pending'}:{label:'Queued · awaiting device',cls:'muted'};}
function renderLive(){
  if(!data)return;
  const open=data.alerts.filter(a=>!a.resolved);
  document.querySelector('#alerts').innerHTML=open.map(a=>`<article class="alert"><div><span class="eyebrow">HELP REQUEST</span><h2>${esc(a.child_name)} needs help.</h2><p>${time(a.created)} · Shared with school and linked parents.</p></div><div class="alert-actions">${a.seen?'<span>You’ve seen this</span>':`<button data-seen="${a.id}">Mark as seen</button>`}${me.user.role==='staff'?`<button data-resolve="${a.id}">Resolve after checking</button>`:''}</div></article>`).join('');
  document.querySelectorAll('[data-seen]').forEach(b=>b.onclick=()=>action(b.parentElement,async()=>{await api(`/alerts/${b.dataset.seen}/seen`,{});await refresh();}));
  document.querySelectorAll('[data-resolve]').forEach(b=>b.onclick=()=>{if(confirm('Have you checked that the child’s request has been handled?'))action(b.parentElement,async()=>{await api(`/alerts/${b.dataset.resolve}/resolve`,{});await refresh();});});
  if(tab==='setup')return;
  const messages=data.children.flatMap(c=>c.messages.map(m=>({...m,child:c.name}))).sort((a,b)=>b.created-a.created);
  const connectedCount=data.children.filter(c=>c.device?.last_seen>data.server_time-30).length;
  document.querySelector('#stats').innerHTML=`<div><span>Children connected</span><strong>${connectedCount}<small> / ${data.children.length}</small></strong></div><div><span>Awaiting a reply</span><strong>${messages.filter(m=>!m.response&&m.expires>data.server_time).length}</strong></div><div><span>Open help requests</span><strong>${open.length}<small>${open.length?' needs attention':' all clear'}</small></strong></div>`;
  document.querySelector('#children').innerHTML=data.children.length?data.children.map(c=>{
    const online=c.device?.last_seen>data.server_time-30;
    return `<article class="card child-card"><div class="avatar">${esc(c.name.charAt(0))}</div><div class="child-details"><h3>${esc(c.name)}</h3><p>${esc(c.class_name)}</p></div><div class="device-status ${online?'online':''}"><span>${online?'TAG connected':c.device?.last_seen?'TAG offline':'Not connected yet'}</span><small>${c.device?.last_seen?`Last seen ${time(c.device.last_seen)}`:'Ask school staff to pair a device'}</small></div></article>`;
  }).join(''):'<div class="empty card"><h3>A connection starts here.</h3><p>No children linked yet. '+(me.user.role==='staff'?'Open People & devices to add your first family.':'Ask your school to link your account.')+'</p></div>';
  document.querySelector('#history').innerHTML=messages.length?`<div class="table-wrap"><table><thead><tr><th>Child / sent</th><th>Message</th><th>Status</th></tr></thead><tbody>${messages.map(m=>{const s=status(m);return `<tr><td><strong>${esc(m.child)}</strong><small>${time(m.created)}</small></td><td><span class="message-type">${esc(m.kind)}</span><p>${esc(m.body)}</p><small>From ${esc(m.sender)}</small></td><td><span class="badge ${s.cls}">${s.label}</span>${m.responded?`<small>${time(m.responded)}</small>`:''}</td></tr>`;}).join('')}</tbody></table></div>`:'<div class="empty"><p>No messages yet. Send your first notice or question.</p></div>';
}
async function setup(){
  try{
    const {parents}=await api('/admin/parents');
    if(tab!=='setup')return;
    const options=parents.map(p=>`<option value="${p.id}">${esc(p.name)} · ${esc(p.email)}</option>`).join('');
    const childOptions=data.children.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('');
    document.querySelector('#setup').innerHTML=`<div class="setup-grid"><section class="card"><span class="eyebrow">01 · FAMILY ACCESS</span><h2>Create a parent account</h2><form id="add-parent"><label>Parent name<input name="name" required maxlength="120"></label><label>Email<input type="email" name="email" required maxlength="254"></label><button class="primary">Create account</button></form><div id="credentials" role="status"></div></section><section class="card"><span class="eyebrow">02 · CHILD PROFILE</span><h2>Add a child</h2><form id="add-child"><label>Child’s display name<input name="name" required maxlength="120"></label><label>Class / form<input name="class_name" required maxlength="120"></label><label>Parent<select name="parent_id" required>${options}</select></label><button class="primary" ${parents.length?'':'disabled'}>Add child</button></form></section><section class="card"><span class="eyebrow">03 · ANOTHER GUARDIAN</span><h2>Link a parent</h2><form id="add-guardian"><label>Child<select name="child_id" required>${childOptions}</select></label><label>Parent<select name="parent_id" required>${options}</select></label><button class="primary" ${parents.length&&data.children.length?'':'disabled'}>Link account</button></form></section></div><section class="card history"><h2>Pair a virtual TAG</h2><p>Generate a one-use code, then enter it at <a href="/device" target="_blank" rel="noopener">the virtual device</a>. Pairing replaces any previous device for that child.</p><div id="pair-result" role="status"></div>${data.children.map(c=>`<div class="pair-row"><strong>${esc(c.name)}</strong><div><button data-pair="${c.id}">Generate pairing code</button> <button class="quiet" data-revoke="${c.id}">Revoke device</button></div></div>`).join('')||'<p class="muted">Add a child to get started.</p>'}</section>`;
    document.querySelector('#add-parent').onsubmit=e=>{e.preventDefault();action(e.target,async()=>{const result=await api('/admin/parents',formData(e.target));e.target.reset();await setup();document.querySelector('#credentials').innerHTML=`<div class="credential-box"><strong>Temporary password</strong><code>${esc(result.temporary_password)}</code><p>Copy this now and share privately with the parent. It is shown once. They must change it at first sign-in.</p></div>`;});};
    document.querySelector('#add-child').onsubmit=e=>{e.preventDefault();action(e.target,async()=>{await api('/admin/children',formData(e.target));await refresh();await setup();toast('Child added. You can pair their TAG below.');});};
    document.querySelector('#add-guardian').onsubmit=e=>{e.preventDefault();action(e.target,async()=>{await api('/admin/guardians',formData(e.target));toast('Parent linked.');});};
    document.querySelectorAll('[data-pair]').forEach(b=>b.onclick=()=>action(b.parentElement,async()=>{const result=await api('/admin/pair',{child_id:b.dataset.pair});document.querySelector('#pair-result').innerHTML=`<div class="credential-box">Pairing code for ${esc(data.children.find(c=>c.id===b.dataset.pair).name)}<code>${result.code}</code><p>Valid for 10 minutes. Use once at /device.</p></div>`;}));
    document.querySelectorAll('[data-revoke]').forEach(b=>b.onclick=()=>{if(confirm('Disconnect this child’s device?'))action(b.parentElement,async()=>{await api('/admin/revoke-device',{child_id:b.dataset.revoke});toast('Device disconnected.');});});
  }catch(e){toast(e.message);}
}
function deviceShell(){
  root.innerHTML=`<main class="device-page"><div class="device-page-head">${brand}<span>VIRTUAL DEVICE · PILOT</span><a href="/">Back to account ↗</a></div><div class="device-intro"><span class="eyebrow">THEIR OWN LITTLE CONNECTION</span><h1>Just what matters.</h1><p>Two buttons. No scrolling. No distractions.</p></div><div class="tag-hardware"><div class="hardware-top"><span>TAG</span><span id="device-online">CONNECTING</span></div><div id="screen" class="eink" aria-live="polite"></div><div class="physical-buttons"><button id="left" aria-label="Left TAG button" disabled>●</button><button id="right" aria-label="Right TAG button" disabled>●</button></div><div class="hardware-bottom">A LITTLE CLOSER</div></div><div id="device-feedback" class="device-feedback" role="status"></div><p class="device-instructions">Hold the left button for 3 seconds to ask for help.<br>School and parents can see your request in TAG.</p><p class="small muted device-note">Pilot alerts appear while their TAG dashboards are open.<br>This is not an emergency-service connection.</p><div id="pair-form"></div></main>`;
  const left=document.querySelector('#left'),right=document.querySelector('#right');
  const start=()=>{if(!connected)return;held=false;left.classList.add('holding');holdTimer=setTimeout(async()=>{held=true;holdTimer=null;left.classList.remove('holding');await deviceAction('/device/help',{},'Help request sent to TAG.');},3000);};
  const cancel=()=>{clearTimeout(holdTimer);holdTimer=null;left.classList.remove('holding');};
  left.onpointerdown=e=>{if(e.button!==0)return;left.setPointerCapture(e.pointerId);start();};left.onpointerup=cancel;left.onpointercancel=()=>{held=true;cancel();};left.onlostpointercapture=cancel;
  left.onkeydown=e=>{if((e.key===' '||e.key==='Enter')&&!e.repeat){e.preventDefault();start();}};
  left.onkeyup=e=>{if(e.key===' '||e.key==='Enter'){e.preventDefault();cancel();if(!held)reply('left');}};
  left.onblur=()=>{held=true;cancel();};
  left.onclick=()=>{if(!held)reply('left');};right.onclick=()=>reply('right');
}
function deviceConnection(ok){
  connected=ok;document.querySelector('#device-online').textContent=ok?'CONNECTED':'OFFLINE';
  document.querySelector('#left').disabled=!ok;
  document.querySelector('#right').disabled=!ok||deviceState?.message?.kind!=='QUESTION';
}
async function deviceRefresh(){
  if(busy||holdTimer)return;busy=true;
  try{
    deviceState=await api('/device/state');deviceConnection(true);
    document.querySelector('#pair-form').innerHTML='';
    const m=deviceState.message;
    const html=`<div class="screen-name">${esc(deviceState.name)}’s TAG</div>${m?`<span class="screen-kind">${m.kind==='NOTICE'?'A MESSAGE FOR YOU':'A QUESTION FOR YOU'}</span><div class="screen-message">${esc(m.body)}</div><div class="screen-labels"><strong>${m.kind==='NOTICE'?'GOT IT':'YES'}</strong><strong>${m.kind==='QUESTION'?'NO':'—'}</strong></div>`:`<div class="screen-idle"><span>✓</span><h2>You’re all caught up.</h2><p>Go and be you.</p></div><div class="screen-labels"><strong>HOLD FOR HELP</strong><strong>—</strong></div>`}${deviceState.alert?'<div class="help-sent">Help requested · waiting for school to resolve</div>':''}`;
    const screen=document.querySelector('#screen');if(screen.innerHTML!==html)screen.innerHTML=html;
    document.querySelector('#left').setAttribute('aria-label',m?.kind==='QUESTION'?'Yes. Hold three seconds to request help.':m?'Got it. Hold three seconds to request help.':'Hold three seconds to request help.');
    document.querySelector('#right').setAttribute('aria-label',m?.kind==='QUESTION'?'No':'No action');
    if(m)await api('/device/delivered',{id:m.id});
  }catch(e){
    deviceConnection(false);
    if(e.status===401){
      document.querySelector('#screen').innerHTML='<div class="screen-idle"><h2>Let’s connect.</h2><p>Ask school staff for a pairing code.</p></div>';
      if(!document.querySelector('#pair')){document.querySelector('#pair-form').innerHTML='<form id="pair" class="card"><label>8-digit pairing code<input name="code" inputmode="numeric" pattern="[0-9]{8}" maxlength="8" required autocomplete="off"></label><button class="primary">Connect this TAG</button></form>';document.querySelector('#pair').onsubmit=e=>{e.preventDefault();action(e.target,async()=>{await api('/device/pair',formData(e.target));await deviceRefresh();});};}
    }else document.querySelector('#device-feedback').textContent='Connection lost. Replies and help requests cannot be sent until reconnected.';
  }finally{busy=false;}
}
async function deviceAction(path, body, success){
  if(!connected)return;
  while(busy)await new Promise(resolve=>setTimeout(resolve,50));
  if(!connected)return;
  busy=true;deviceConnection(false);
  try{await api(path,body);document.querySelector('#device-feedback').textContent=success;}
  catch(e){document.querySelector('#device-feedback').textContent=`Not confirmed: ${e.message} Reconnect and check before trying again.`;}
  finally{busy=false;await deviceRefresh();}
}
async function reply(side){const m=deviceState?.message;if(!m)return;if(side==='right'&&m.kind==='NOTICE')return;await deviceAction('/device/respond',{id:m.id,response:m.kind==='NOTICE'?'ACK':side==='left'?'YES':'NO'},'Your response has been sent.');}
async function boot(){
  clearInterval(timer);
  if(location.pathname==='/device'){deviceShell();await deviceRefresh();timer=setInterval(deviceRefresh,3000);return;}
  try{me=await api('/me');csrf=me.csrf;if(me.user.must_change){passwordScreen();return;}shell();await refresh(true);timer=setInterval(()=>refresh(),5000);}
  catch(e){if(e.status===401)login();else{root.innerHTML='<main class="narrow"><h1>TAG cannot connect.</h1><p>Please refresh to try again.</p></main>';toast(e.message);}}
}
boot();
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
