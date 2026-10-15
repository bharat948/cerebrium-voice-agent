/* Voice Foundry UI. No build step, external runtime, or bundled secrets. */
const $ = (id) => document.getElementById(id);
const state = { key: sessionStorage.getItem('vf_key') || '', agents: [], plans: [], calls: [],
                config: null, selectedPlan: null, selectedCall: null, page: 'dashboard' };
const safe = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const prettyTime = (s) => s ? new Date(s).toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'}) : '—';
const fmt = (s) => String(s||'').replace(/_/g,' ').replace(/-/g,' ');
function toast(msg, error=false) { const el=$('toast'); el.textContent=msg; el.classList.toggle('error',error); el.hidden=false; clearTimeout(window.toastTimer); window.toastTimer=setTimeout(()=>el.hidden=true,4200); }
async function api(path, options={}) {
  const response = await fetch(path, {...options, headers:{ 'X-API-Key':state.key, ...(options.body?{'Content-Type':'application/json'}:{}), ...(options.headers||{}) }});
  let data;
  try { data = await response.json(); } catch { data = {}; }
  if(!response.ok){ const detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data); throw new Error(detail || `HTTP ${response.status}`); }
  return data;
}
async function load(){
  const [config, agents, plans, calls] = await Promise.all([
    api('/api/config'), api('/api/agents'), api('/api/plans'), api('/api/calls')]);
  state.config=config; state.agents=agents; state.plans=plans; state.calls=calls;
  render();
}
async function authenticate(key){
  state.key=key;
  await load();
  sessionStorage.setItem('vf_key',key);
  $('auth-overlay').hidden=true;$('app').hidden=false;
}
$('auth-form').addEventListener('submit', async(e)=>{
 e.preventDefault(); $('auth-error').textContent='';
 try { await authenticate($('auth-input').value.trim()); } catch(e) { $('auth-error').textContent=e.message; }
});
$('logout-btn').addEventListener('click',()=>{state.key='';sessionStorage.removeItem('vf_key');$('app').hidden=true;$('auth-overlay').hidden=false;$('auth-input').value='';});
function navigate(page){
  if(!['dashboard','compose','history','agents','settings'].includes(page))return;
  state.page=page;
  document.querySelectorAll('.page').forEach(el=>el.hidden=el.id!==`page-${page}`);
  document.querySelectorAll('.nav-item').forEach(el=>el.classList.toggle('active',el.dataset.page===page));
  $('breadcrumb').textContent=({dashboard:'Overview',compose:'Call studio',history:'Call history',agents:'Your agents',settings:'Configuration'})[page];
  if(page==='history') renderCallDetail();
  location.hash=page;
}
document.addEventListener('click',(e)=>{
 const nav=e.target.closest('[data-goto],[data-page]');
 if(nav)navigate(nav.dataset.goto || nav.dataset.page);
 const suggestion=e.target.closest('[data-suggestion]');
 if(suggestion){ $('message-input').value=suggestion.dataset.suggestion;navigate('compose');$('message-input').focus(); }
 const open=e.target.closest('[data-call-id]');
 if(open){state.selectedCall=open.dataset.callId;navigate('history');renderCallDetail();}
});
function callRow(call){
 const style=['completed'].includes(call.status)?'#c6fc83':(['failed','busy','no-answer'].includes(call.status)?'#ffb9a9':'#e4c994');
 return `<button class="list-row" data-call-id="${safe(call.id)}"><span class="row-symbol">↗</span><span class="row-main"><strong>${safe(call.phone)}</strong><small>${safe(fmt(call.direction))} · ${safe(call.mode)} · ${safe(call.voice_engine||"deepgram")}</small></span><span class="row-end"><strong style="color:${style}">${safe(fmt(call.status))}</strong><small>${safe(prettyTime(call.created_at))}</small></span></button>`;
}
function render(){
 const s=state.config;
 $('runtime-label').textContent=s.demo_mode?'Preview environment':'Live calling environment';
 $('model-label').textContent=s.voice_engine==='openai_live'?s.live_model:s.model+' + Deepgram';
 $('engine-select').value=s.voice_engine;
 $('mode-chip').textContent=s.demo_mode?'● Demo mode':'● Live mode';
 $('mode-chip').style.color=s.demo_mode?'#c8f4a4':'#f3c793';
 $('stat-total').textContent=state.calls.length;$('stat-done').textContent=state.calls.filter(c=>c.status==='completed').length;
 $('stat-agents').textContent=state.agents.length;$('stat-plans').textContent=state.plans.length;
 $('recent-calls').innerHTML=state.calls.length?state.calls.slice(0,5).map(callRow).join(''):'<div class="empty-message">No calls yet. Open the call studio to prepare your first mission.</div>';
 $('history-items').innerHTML=state.calls.length?state.calls.map(callRow).join(''):'<div class="empty-message">Your call history will appear here.</div>';
 $('agent-select').innerHTML=state.agents.map(a=>`<option value="${safe(a.id)}">${safe(a.name)} · ${safe(a.role)}</option>`).join('');
 $('agent-count').textContent=`${state.agents.length} AGENTS`;
 $('agent-list').innerHTML=state.agents.map(a=>`<div class="agent-card"><span class="row-symbol">◈</span><div><h3>${safe(a.name)}</h3><p>${safe(a.role)} · ${safe(a.language)}</p><small>${safe(a.instructions.slice(0,180))}${a.instructions.length>180?'…':''}</small></div></div>`).join('');
 $('settings-readiness').innerHTML=[['Runtime mode',s.demo_mode?'Demo / no dialing':'Live'],['Default voice engine',s.voice_engine],['Default engine readiness',s.ready_for_calls?'Configured':'Missing live configuration'],['OpenAI planning',s.openai_enabled?'Enabled':'Template-only mode'],['Reasoning model',s.model],['Allowlisted recipients',String(s.allowed_numbers)],['Maximum call duration',s.max_call_seconds+' seconds']].map(([k,v])=>`<div class="setting-row"><span>${safe(k)}</span><strong>${safe(v)}</strong></div>`).join('');
 $('dial-verb').textContent=s.demo_mode?'start preview':'place live call';
 if(state.selectedPlan)showPlan(state.selectedPlan);
}
function addBubble(type, content){
 const feed=$('chat-feed');
 const intro=feed.querySelector('.chat-intro');if(intro)intro.remove();
 const div=document.createElement('div');div.className=`bubble ${type}`;
 div.innerHTML=`<span class="bubble-label">${type==='user'?'YOU':'CALL PLANNER'}</span>${safe(content)}`;
 feed.append(div);feed.scrollTop=feed.scrollHeight;
}
$('plan-form').addEventListener('submit',async(e)=>{
 e.preventDefault(); const message=$('message-input').value.trim(); const phone=$('phone-input').value.trim();
 if(!message || !phone)return;
 $('plan-btn').disabled=true;addBubble('user',message);
 try {
   const plan=await api('/api/plans',{method:'POST',body:JSON.stringify({message,phone,agent_id:$('agent-select').value})});
   state.selectedPlan=plan;state.plans.unshift(plan);
   addBubble('assistant',`Plan ready for ${plan.phone}.\n\nGOAL: ${plan.goal}\n\nAGENDA:\n${plan.agenda.map((x,i)=>`${i+1}. ${x}`).join('\n')}\n\nReview or edit the agenda on the right. Nothing has been dialed.`);
   $('message-input').value='';showPlan(plan);$('stat-plans').textContent=state.plans.length;
   toast('Call plan created. Review before proceeding.');
 }catch(err){addBubble('assistant','Unable to prepare plan. '+err.message);toast(err.message,true);}
 finally{$('plan-btn').disabled=false;}
});
function showPlan(plan){
 $('plan-empty').hidden=true;$('plan-editor').hidden=false;$('plan-status').textContent=plan.state.toUpperCase();
 $('inspect-phone').textContent=plan.phone;$('edit-goal').value=plan.goal;
 $('edit-agenda').value=plan.agenda.join('\n');$('edit-script').value=plan.script;
 $('call-btn').disabled=plan.state!=='draft';$('save-plan-btn').disabled=plan.state!=='draft';
}
async function savePlan(){
 if(!state.selectedPlan)return null;
 const data={goal:$('edit-goal').value.trim(),agenda:$('edit-agenda').value.split('\n').map(x=>x.trim()).filter(Boolean),script:$('edit-script').value.trim()};
 const updated=await api(`/api/plans/${state.selectedPlan.id}`,{method:'PATCH',body:JSON.stringify(data)});
 state.selectedPlan=updated;state.plans=state.plans.map(p=>p.id===updated.id?updated:p);showPlan(updated);
 return updated;
}
$('save-plan-btn').addEventListener('click',async()=>{try{await savePlan();toast('Plan updated');}catch(e){toast(e.message,true);}});
$('call-btn').addEventListener('click',async()=>{
 if(!state.selectedPlan)return;
 const mode=state.config.demo_mode?'simulation (no telephone call)':'REAL telephone call';
 const phone=state.selectedPlan.phone;
 const engine=$('engine-select').value;
 if(!state.config.demo_mode&&!state.config.ready_by_engine[engine]){toast('Missing provider keys for '+engine,true);return;}
 if(!confirm(`Approve ${mode} to ${phone}?\n\nEnsure you are authorized to call this recipient.`))return;
 $('call-btn').disabled=true;
 try{
   const plan=await savePlan();
   const call=await api('/api/calls',{method:'POST',body:JSON.stringify({plan_id:plan.id,confirm:true,voice_engine:engine})});
   state.selectedCall=call.id;state.selectedPlan.state='used';
   await load();navigate('history');await renderCallDetail();
   toast(state.config.demo_mode?'Preview opened. No call was placed.':'Call submitted to Twilio.');
 }catch(e){toast(e.message,true);$('call-btn').disabled=false;}
});
async function renderCallDetail(){
 const id=state.selectedCall; if(!id)return;
 try{
 const call=await api(`/api/calls/${id}`);
 $('detail-status').textContent=call.status.toUpperCase();
 $('call-detail-body').classList.remove('inspector-empty');
 const isOpen=!['completed','failed','busy','no-answer','canceled'].includes(call.status);
 let html=`<div class="detail-top"><h3>${safe(call.phone)}</h3><p>${safe(call.direction)} · ${safe(call.mode)} · ${safe(call.voice_engine||"deepgram")} · ${safe(prettyTime(call.created_at))}</p><p style="margin-top:8px">${safe(call.plan?.goal || 'General support')}</p><button class="btn outline" id="summary-btn">Generate outcome summary</button> ${isOpen?`<button class="btn outline" id="hangup-btn">${call.mode==='demo'?'End preview':'End call'}</button>`:''}</div>`;
 html+=`<div class="event-list">${call.events.length?call.events.map(e=>`<div class="event"><span class="event-mark">${e.type==='transcript'?(e.speaker==='caller'?'◉':'⌁'):'◇'}</span><div class="event-content"><div class="event-meta"><span>${safe(e.speaker||e.type)}</span><span>${safe(prettyTime(e.created_at))}</span></div>${safe(e.content)}</div></div>`).join(''):'<p class="muted">Waiting for events…</p>'}</div>`;
 if(call.mode==='demo'&&call.status==='simulated'){
  html+=`<form id="preview-form" class="preview-form"><input id="preview-input" placeholder="Type what the recipient might say…" required maxlength="800"/><button class="btn primary" type="submit">Reply ↗</button></form>`;
 }
 $('call-detail-body').innerHTML=html;
 document.querySelectorAll('[data-call-id]').forEach(el=>el.classList.toggle('selected',el.dataset.callId===id));
 const summary=$('summary-btn');if(summary)summary.onclick=async()=>{summary.disabled=true;try{await api(`/api/calls/${id}/summary`,{method:'POST'});await renderCallDetail();toast('Outcome report added');}catch(e){toast(e.message,true);summary.disabled=false;}};
 const hangup=$('hangup-btn');if(hangup)hangup.onclick=async()=>{if(!confirm('End this call?'))return;try{await api(`/api/calls/${id}/hangup`,{method:'POST'});await load();renderCallDetail();}catch(e){toast(e.message,true);}};
 const preview=$('preview-form');if(preview)preview.onsubmit=async(e)=>{
  e.preventDefault();const value=$('preview-input').value.trim();if(!value)return;preview.querySelector('button').disabled=true;
  try{await api(`/api/calls/${id}/preview`,{method:'POST',body:JSON.stringify({text:value})});await renderCallDetail();}catch(err){toast(err.message,true);preview.querySelector('button').disabled=false;}
 };
 }catch(e){toast(e.message,true);}
}
$('refresh-btn').addEventListener('click',async()=>{try{await load();await renderCallDetail();toast('Refreshed');}catch(e){toast(e.message,true);}});
$('agent-form').addEventListener('submit',async(e)=>{
 e.preventDefault();const form=e.target;const data=Object.fromEntries(new FormData(form));
 try{await api('/api/agents',{method:'POST',body:JSON.stringify(data)});form.reset();await load();toast('Agent created');}catch(e){toast(e.message,true);}
});
// Poll only when the call history view is visible, don't re-render the call composer mid-entry.
setInterval(async()=>{
 if(state.key && state.page==='history' && state.selectedCall && document.activeElement?.id!=='preview-input'){
  try{state.calls=await api('/api/calls');$('history-items').innerHTML=state.calls.map(callRow).join('');await renderCallDetail();}catch{/* Keep previous data; user can refresh manually. */}
 }
},7000);
(async()=>{
 if(state.key){try{await authenticate(state.key);}catch{state.key='';sessionStorage.removeItem('vf_key');}}
 if(!state.key){$('auth-overlay').hidden=false;$('app').hidden=true;}
 const hash=location.hash.substring(1);if(['dashboard','compose','history','agents','settings'].includes(hash))navigate(hash);
})();
