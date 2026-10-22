/* Voice Foundry UI. No build step, external runtime, or bundled secrets. */
const $ = (id) => document.getElementById(id);
const state = { key: sessionStorage.getItem('vf_key') || '', agents: [], plans: [], calls: [],
                config: null, selectedPlan: null, selectedCall: null, page: 'dashboard', contacts: [], missions: [], authenticated: false };
const safe = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const prettyTime = (s) => s ? new Date(s).toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'}) : '—';
const fmt = (s) => String(s||'').replace(/_/g,' ').replace(/-/g,' ');
function toast(msg, error=false) { const el=$('toast'); el.textContent=msg; el.classList.toggle('error',error); el.hidden=false; clearTimeout(window.toastTimer); window.toastTimer=setTimeout(()=>el.hidden=true,4200); }
async function api(path, options={}) {
  const response = await fetch(path, {...options, headers:{ 'X-API-Key':state.key, ...(options.body && !(options.body instanceof FormData)?{'Content-Type':'application/json'}:{}), ...(options.headers||{}) }});
  let data;
  try { data = await response.json(); } catch { data = {}; }
  if(!response.ok){ const detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data); throw new Error(detail || `HTTP ${response.status}`); }
  return data;
}
async function load(){
  const [config, agents, plans, calls, contacts, missions] = await Promise.all([
    api('/api/config'), api('/api/agents'), api('/api/plans'), api('/api/calls'), api('/api/v3/contacts'), api('/api/v3/missions')]);
  state.config=config; state.agents=agents; state.plans=plans; state.calls=calls; state.contacts=contacts; state.missions=missions;
  render();
}
async function authenticate(key){
  state.key=key;
  await load(); state.authenticated=true;
  sessionStorage.setItem('vf_key',key);
  $('auth-overlay').hidden=true;$('app').hidden=false;
}
$('auth-form').addEventListener('submit', async(e)=>{
 e.preventDefault(); $('auth-error').textContent='';
 try { await authenticate($('auth-input').value.trim()); } catch(e) { $('auth-error').textContent=e.message; }
});
$('logout-btn').addEventListener('click',async()=>{await fetch('/auth/logout',{method:'POST'}); state.authenticated=false;state.key='';sessionStorage.removeItem('vf_key');$('app').hidden=true;$('auth-overlay').hidden=false;$('auth-input').value='';});
function navigate(page){
  if(!['dashboard','compose','history','agents','contacts','missions','voice-lab','knowledge','operations','calendar','integrations','settings'].includes(page))return;
  state.page=page;
  document.querySelectorAll('.page').forEach(el=>el.hidden=el.id!==`page-${page}`);
  document.querySelectorAll('.nav-item').forEach(el=>el.classList.toggle('active',el.dataset.page===page));
  $('breadcrumb').textContent=({dashboard:'Overview',compose:'Call studio',history:'Call history',agents:'Agent Studio',contacts:'Contacts',missions:'Missions','voice-lab':'Voice Lab',knowledge:'Knowledge',operations:'Operations',calendar:'Calendar',integrations:'Integrations',settings:'Configuration'})[page];
  if(page==='history') renderCallDetail();
  if(page==='integrations') renderIntegrations();
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
 $('mission-agent').innerHTML=state.agents.map(a=>`<option value="${safe(a.id)}">${safe(a.name)}</option>`).join('');
 if($('voice-agent')&&!$('voice-agent').children.length){
   $('voice-agent').innerHTML=state.agents.map(a=>`<option value="${safe(a.id)}">${safe(a.name)} · ${safe(a.role)}</option>`).join('');
   renderSelectedVoiceAgent();
 }
 $('agent-select').innerHTML=state.agents.map(a=>`<option value="${safe(a.id)}">${safe(a.name)} · ${safe(a.role)}</option>`).join('');
 $('contact-count').textContent=`${state.contacts.length} CONTACTS`;
 $('contact-list').innerHTML=state.contacts.length ? state.contacts.map(c=>`<div class="agent-card"><span class="row-symbol">♧</span><div><h3>${safe(c.name)}</h3><p>${safe(c.phone)} · ${safe(c.language)}</p><small>${c.outbound_consent?'Outbound consent recorded':'Outbound not authorized'} · ${c.email_consent?'Email consent recorded':'No email consent'} · ${c.memory_opt_in?'Memory enabled':'Memory disabled'}</small><p><button class="btn outline" data-contact-consent="${safe(c.id)}">Consent settings</button> <button class="btn outline" data-contact-memory="${safe(c.id)}">Memories</button> <button class="btn outline" data-memory-policy="${safe(c.id)}">${c.memory_opt_in?'Disable memory':'Enable memory'}</button> <button class="btn outline" data-contact-deactivate="${safe(c.id)}">Deactivate</button></p></div></div>`).join('') : '<div class="empty-message">Add your first contact.</div>';
 $('contact-select').innerHTML='<option value="">Enter a number below</option>'+state.contacts.map(c=>`<option value="${safe(c.id)}">${safe(c.name)} · ${safe(c.phone)}</option>`).join('');
 $('mission-contact').innerHTML='<option value="">Select recipient</option>'+state.contacts.filter(c=>c.email&&c.email_consent).map(c=>`<option value="${safe(c.id)}">${safe(c.name)} · ${safe(c.email)}</option>`).join('');
 $('mission-list').innerHTML=state.missions.length?state.missions.map(m=>`<div class="agent-card"><span class="row-symbol">◉</span><div><h3>${safe(m.objective.slice(0,90))}</h3><p>${safe(m.state)} · ${safe(prettyTime(m.created_at))}</p><small>${safe(m.error||m.result?.slice(0,120)||'Awaiting worker')}</small><p><button class="btn outline" data-mission-view="${safe(m.id)}">Timeline</button> ${['queued','blocked','awaiting_consent'].includes(m.state)?`<button class="btn outline" data-mission-action="pause" data-mission-id="${safe(m.id)}">Pause</button>`:''} ${m.state==='paused'?`<button class="btn outline" data-mission-action="resume" data-mission-id="${safe(m.id)}">Resume</button>`:''} ${['queued','blocked','awaiting_consent','paused'].includes(m.state)?`<button class="btn outline" data-mission-action="revise" data-mission-id="${safe(m.id)}">Revise</button>`:''} ${['queued','blocked','awaiting_consent','paused','running'].includes(m.state)?`<button class="btn outline" data-mission-action="cancel" data-mission-id="${safe(m.id)}">Cancel</button>`:''}</p></div></div>`).join(''):'<div class="empty-message">No research missions yet.</div>';
 $('agent-count').textContent=`${state.agents.length} AGENTS`;
 $('agent-list').innerHTML=state.agents.map(a=>`<div class="agent-card"><span class="row-symbol">◈</span><div><h3>${safe(a.name)}</h3><p>${safe(a.role)} · ${safe(a.language)}</p><small>${safe(a.instructions.slice(0,180))}${a.instructions.length>180?'…':''}</small><p><button class="btn outline" data-edit-agent="${safe(a.id)}">Edit agent ↗</button> <button class="btn outline" data-agent-releases="${safe(a.id)}">Release history</button></p></div></div>`).join('');
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
 if(!message || (!phone && !$('contact-select').value))return;
 $('plan-btn').disabled=true;addBubble('user',message);
 try {
   const plan=await api('/api/plans',{method:'POST',body:JSON.stringify({message,phone,contact_id:$('contact-select').value||null,agent_id:$('agent-select').value})});
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
$('contact-select').addEventListener('change',()=>{
 const c=state.contacts.find(x=>x.id===$('contact-select').value);
 if(c)$('phone-input').value=c.phone;
});
$('contact-form').addEventListener('submit',async(e)=>{
 e.preventDefault(); const form=e.target, data=Object.fromEntries(new FormData(form));
 data.outbound_consent=Boolean(form.elements.outbound_consent.checked);
 data.email_consent=Boolean(form.elements.email_consent.checked);
 try{await api('/api/v3/contacts',{method:'POST',body:JSON.stringify(data)});form.reset();await load();toast('Contact saved');}catch(err){toast(err.message,true);}
});
$('import-csv-btn').addEventListener('click',async()=>{
 const file=$('contacts-csv').files[0];if(!file){toast('Choose a CSV file',true);return;}
 const form=new FormData();form.append('file',file);
 try{const r=await api('/api/v3/contacts/import',{method:'POST',body:form,headers:{}});await load();toast(`${r.imported} contacts imported`);}catch(e){toast(e.message,true);}
});
let studioAgentId=null,studioDraftId=null;
document.addEventListener('click',async(e)=>{
 const openStudio=e.target.closest('[data-open-studio-agent]');
 if(openStudio){
   const agentId=openStudio.dataset.openStudioAgent;
   navigate('agents');
   setTimeout(()=>{const btn=document.querySelector(`[data-edit-agent="${CSS.escape(agentId)}"]`);if(btn)btn.click();},60);
   return;
 }
 const btn=e.target.closest('[data-edit-agent]');if(!btn)return;
 studioAgentId=btn.dataset.editAgent;studioDraftId=null;$('studio-publish').disabled=true;
 try{
   const p=await api(`/api/v3/agents/${studioAgentId}/prompt`);
   const c=p.configuration;
   $('studio-agent-label').textContent=c.name;
   $('studio-personality').value=c.personality;
   $('studio-voice').value=c.voice;
   $('studio-language').value=c.language;
   $('studio-access').value=c.access;
   const b=c.behavior_policy||{};
   $('studio-pace').value=b.pace||'adaptive';$('studio-initiative').value=b.initiative||'guided';
   $('studio-expression').value=b.expression||'balanced';$('studio-pause').value=b.pause_tolerance||'patient';
   $('studio-interrupt').value=b.interruption_sensitivity||'normal';

   // Populate integration access checkboxes
   const activeIntegrations = c.integrations || [];
   try {
     const allIntegrations = await api('/api/v3/integrations');
     const activeList = allIntegrations.filter(i => i.status === 'active');
     $('studio-integrations-checkboxes').innerHTML = activeList.length ? activeList.map(i => `
       <label>
         <input type="checkbox" name="studio_integration" value="${safe(i.id)}" ${activeIntegrations.includes(i.id)?'checked':''}>
         <span>${safe(i.name)} ${i.connected ? '<small class="tag-badge">Connected</small>' : '<small class="tag-badge muted">Offline</small>'}</span>
       </label>
     `).join('') : '<span class="muted tiny">No active integrations found. Connect services in the Integrations hub.</span>';
   } catch {
     $('studio-integrations-checkboxes').innerHTML = '<span class="muted tiny">Could not load integrations list.</span>';
   }

   $('studio-editor').hidden=false;
   $('prompt-preview').hidden=true;
   $('studio-editor').scrollIntoView({behavior:'smooth',block:'nearest'});
 }catch(err){toast(err.message,true);}
});
$('studio-preview').addEventListener('click',async()=>{
 if(!studioAgentId)return;
 const p=await api(`/api/v3/agents/${studioAgentId}/prompt`);
 $('prompt-preview').textContent=p.compiled_prompt;$('prompt-preview').hidden=false;
});
$('studio-form').addEventListener('submit',async(e)=>{
 e.preventDefault();if(!studioAgentId)return;
 const selectedIntegrations = Array.from(document.querySelectorAll('input[name="studio_integration"]:checked')).map(cb=>cb.value);
 const changes={personality:$('studio-personality').value.trim(),voice:$('studio-voice').value.trim(),language:$('studio-language').value.trim(),access:$('studio-access').value,
 integrations:selectedIntegrations,
 behavior_policy:{pace:$('studio-pace').value,initiative:$('studio-initiative').value,expression:$('studio-expression').value,pause_tolerance:$('studio-pause').value,interruption_sensitivity:$('studio-interrupt').value}};
 try{
  const draft=await api(`/api/v3/agents/${studioAgentId}/drafts`,{method:'POST',body:JSON.stringify({changes})});
  studioDraftId=draft.id;$('studio-publish').disabled=false;
  toast(`Draft v${draft.version} saved. Review before publishing.`);
 }catch(err){toast(err.message,true);}
});
$('studio-review-save').addEventListener('click',async()=>{
 if(!studioAgentId)return;
 try{await api(`/api/v3/agents/${studioAgentId}/feedback`,{method:'POST',body:JSON.stringify({agent_id:studioAgentId,rating:Number($('studio-rating').value),note:$('studio-review-note').value})});
   $('studio-review-note').value='';toast('Human review saved');}
 catch(err){toast(err.message,true);}
});
$('studio-improve').addEventListener('click',async()=>{
 if(!studioAgentId)return;
 try{
  const theme=prompt('Proposal category: conciseness, turn_taking, or uncertainty','conciseness');
  if(!theme)return;
  const proposed=await api(`/api/v4/agents/${studioAgentId}/evolution/propose`,{method:'POST',body:JSON.stringify({theme})});
  if(!confirm(`Create a REVIEW DRAFT (not published)?\n\nEvidence: ${proposed.evidence.feedback_count} human reviews, average ${proposed.evidence.average_rating} / 5.\nProposed: ${JSON.stringify(proposed.changes)}`))return;
  const decision=await api(`/api/v4/evolution/${proposed.id}/decision`,{method:'POST',body:JSON.stringify({approve:true})});
  studioDraftId=decision.draft.id;$('studio-publish').disabled=false;
  toast('Improvement draft created, test before publishing');
 }catch(err){toast(err.message,true);}
});
$('studio-publish').addEventListener('click',async()=>{
 if(!studioDraftId || !studioAgentId)return;
 if(!confirm('Publish this agent version for NEW calls?'))return;
 try{await api(`/api/v3/agents/${studioAgentId}/releases/${studioDraftId}/publish`,{method:'POST'});studioDraftId=null;$('studio-publish').disabled=true;await load();toast('Agent configuration published');}
 catch(err){toast(err.message,true);}
});
$('template-add-btn').addEventListener('click',async()=>{
 const template=$('template-select').value;if(!template){toast('Select a template',true);return;}
 try{const r=await api('/api/v3/agents/from-template',{method:'POST',body:JSON.stringify({template})});await api(`/api/v3/agents/${r.agent.id}/releases/${r.draft.id}/publish`,{method:'POST'});await load();toast('Template agent published');}catch(e){toast(e.message,true);}
});
$('mission-form').addEventListener('submit',async(e)=>{
 e.preventDefault();const payload={agent_id:$('mission-agent').value,contact_id:$('mission-contact').value,objective:$('mission-objective').value.trim()};
 if(!confirm('Queue research and automatically email the authorized contact when complete?'))return;
 try{await api('/api/v3/missions',{method:'POST',body:JSON.stringify(payload)});$('mission-objective').value='';await load();toast('Mission queued');}catch(err){toast(err.message,true);}
});
$('missions-refresh').addEventListener('click',async()=>{await load();toast('Mission list refreshed');});
$('agent-form').addEventListener('submit',async(e)=>{
 e.preventDefault();const form=e.target;const data=Object.fromEntries(new FormData(form));
 try{await api('/api/agents',{method:'POST',body:JSON.stringify(data)});form.reset();await load();toast('Agent created');}catch(e){toast(e.message,true);}
});
// Poll only when the call history view is visible, don't re-render the call composer mid-entry.
setInterval(async()=>{
 if(state.authenticated && state.page==='history' && state.selectedCall && document.activeElement?.id!=='preview-input'){
  try{state.calls=await api('/api/calls');$('history-items').innerHTML=state.calls.map(callRow).join('');await renderCallDetail();}catch{/* Keep previous data; user can refresh manually. */}
 }
},7000);
(async()=>{
 let authMode='api_key';
 try{ const identity=await (await fetch('/auth/me')).json();authMode=identity.mode;
   if(authMode==='google'){
     $('google-login').hidden=false;$('auth-form').hidden=true;
     if(identity.authenticated)await authenticate('');
   }
 }catch{}
 if(authMode!=='google' && state.key){try{await authenticate(state.key);}catch{state.key='';sessionStorage.removeItem('vf_key');}}
 if(!state.authenticated){$('auth-overlay').hidden=false;$('app').hidden=true;}
 const hash=location.hash.substring(1);if(['dashboard','compose','history','agents','contacts','missions','voice-lab','knowledge','operations','calendar','settings'].includes(hash))navigate(hash);
})();

// Feature-workstream owner controls. All state changes are server-authorized.
document.addEventListener('click',async (e)=>{
 const consent=e.target.closest('[data-contact-consent]');
 const memoryPolicy=e.target.closest('[data-memory-policy]');
 const deactivate=e.target.closest('[data-contact-deactivate]');
 const memory=e.target.closest('[data-contact-memory]');
 const release=e.target.closest('[data-agent-releases]');
 const missionAction=e.target.closest('[data-mission-action]');
 const missionView=e.target.closest('[data-mission-view]');
 try {
  if(memoryPolicy){
    const c=state.contacts.find(x=>x.id===memoryPolicy.dataset.memoryPolicy);if(!c)return;
    const enabled=!Boolean(c.memory_opt_in);
    if(!confirm(`${enabled?'Enable':'Disable'} long-term memory for ${c.name}? Disabling stops retrieval and new memory collection, but does not erase history.`))return;
    await api(`/api/v4/contacts/${c.id}/memory-policy`,{method:'PATCH',body:JSON.stringify({enabled})});
    await load();toast('Contact memory preference updated');return;
  }
  if(consent){
   const c=state.contacts.find(x=>x.id===consent.dataset.contactConsent);if(!c)return;
   const approveOutbound=confirm(`Record CURRENT outbound-call consent for ${c.name}?
OK = consented, Cancel = not consented.`);
   const approveEmail=confirm(`Record CURRENT research-email consent for ${c.name}?
OK = consented, Cancel = not consented.`);
   await api(`/api/v3/contacts/${c.id}`,{method:'PATCH',body:JSON.stringify({outbound_consent:approveOutbound,email_consent:approveEmail})});
   await load();toast('Contact consent updated');return;
  }
  if(deactivate){
   const c=state.contacts.find(x=>x.id===deactivate.dataset.contactDeactivate);if(!c)return;
   if(!confirm(`Deactivate ${c.name}? This revokes calling/email consent and access grants.`))return;
   await api(`/api/v3/contacts/${c.id}`,{method:'DELETE'});await load();toast('Contact deactivated');return;
  }
  if(memory){
   const cid=memory.dataset.contactMemory;
   const agent=state.agents.find(a=>a.id===prompt('Enter the agent ID to inspect memory for:',state.agents[0]?.id||''));
   if(!agent)return;
   const rows=await api(`/api/v3/memories?agent_id=${encodeURIComponent(agent.id)}&contact_id=${encodeURIComponent(cid)}`);
   if(!rows.length){alert('No stored memories for this agent and contact.');return;}
   const selected=prompt(`Agent: ${agent.name}
Saved memories:
${rows.map((m,i)=>`${i+1}. ${m.content}`).join('\n')}

Enter a memory number to inspect, or Cancel.`);
   if(!selected)return;
   const m=rows[Number(selected)-1];if(!m)return;
   const action=prompt('Type CORRECT to replace, DELETE to forget, or CANCEL.','CANCEL');
   if(action?.toUpperCase()==='DELETE'){
     if(confirm('Delete this memory from active retrieval?'))await api(`/api/v3/memories/${m.id}?contact_id=${encodeURIComponent(cid)}`,{method:'DELETE'});
   } else if(action?.toUpperCase()==='CORRECT'){
     const content=prompt('Enter the corrected memory:',m.content);if(content?.trim())await api(`/api/v3/memories/${m.id}/correct`,{method:'POST',body:JSON.stringify({contact_id:cid,content,consent:false})});
   }
   toast('Memory action processed');return;
  }
  if(release){
   const aid=release.dataset.agentReleases;
   const list=await api(`/api/v3/agents/${aid}/releases`);
   const published=list.filter(x=>x.status!=='draft');
   if(!published.length){alert('No published versions yet.');return;}
   const selection=prompt(`Select a release VERSION to restore as a new draft:
${published.map(x=>`v${x.version} — ${x.status}`).join('\n')}

Cancel to do nothing.`);
   const selected=published.find(x=>x.version===Number(selection));if(!selected)return;
   if(!confirm(`Create a restore draft from v${selected.version}? This will NOT publish it.`))return;
   const restored=await api(`/api/v3/agents/${aid}/releases/${selected.id}/restore`,{method:'POST'});
   studioAgentId=aid;studioDraftId=restored.draft.id;
   $('studio-publish').disabled=false;
   toast(`Restore draft v${restored.draft.version} created. Review before publishing.`);return;
  }
  if(missionAction){
   const mid=missionAction.dataset.missionId,action=missionAction.dataset.missionAction;
   if(action==='revise'){
     const m=state.missions.find(x=>x.id===mid);const objective=prompt('Revise mission objective',m?.objective||'');
     if(!objective?.trim())return;
     await api(`/api/v3/missions/${mid}`,{method:'PATCH',body:JSON.stringify({objective})});
   } else {
     if(action==='cancel'&&!confirm('Cancel this mission? Finished emails cannot be recalled.'))return;
     await api(`/api/v3/missions/${mid}/${action}`,{method:'POST'});
   }
   await load();toast(`Mission ${action} completed`);return;
  }
  if(missionView){
    const m=await api(`/api/v3/missions/${missionView.dataset.missionView}`);
    alert(`${m.objective}
Status: ${m.state}

${m.events.map(x=>`${prettyTime(x.created_at)} ${x.event_type}: ${x.detail}`).join('\n')}`);
    return;
  }
 }catch(err){toast(err.message,true);}
});

let architectProposal=null;
$('architect-form').addEventListener('submit',async (e)=>{
 e.preventDefault();$('architect-propose').disabled=true;
 try {
  const value=$('architect-brief').value.trim();
  const result=await api('/api/v3/architect/propose',{method:'POST',body:JSON.stringify({brief:value})});
  architectProposal=result.proposal;
  $('architect-preview').textContent=JSON.stringify(result.proposal,null,2);
  $('architect-preview').hidden=false;
  $('architect-create').hidden=false;
  toast('Proposal ready. Review before creating an unpublished draft.');
 }catch(err){toast(err.message,true);}finally{$('architect-propose').disabled=false;}
});
$('architect-create').addEventListener('click',async()=>{
 if(!architectProposal)return;
 if(!confirm('Create this agent as an UNPUBLISHED draft? No phone call will be placed.'))return;
 try {
  const r=await api('/api/v3/architect/create',{method:'POST',body:JSON.stringify({proposal:architectProposal})});
  architectProposal=null;$('architect-create').hidden=true;
  studioAgentId=r.agent.id;studioDraftId=r.draft.id;
  await load();
  const edit=document.querySelector(`[data-edit-agent="${CSS.escape(studioAgentId)}"]`);
  if(edit)edit.click();
  studioDraftId=r.draft.id;$('studio-publish').disabled=false;
  toast(`Created agent draft v${r.draft.version}. Publish only after review.`);
 }catch(err){toast(err.message,true);}
});

// v3 platform extensions: all mutations are owner-authenticated; UI never trusts
// caller-provided content as HTML. Use safe() for every rendered field.
async function loadAdvanced(){
  if(!state.authenticated)return;
  try{
    const [dashboard,approvals,alerts,docs,calendar,google]=await Promise.all([
       api('/api/v3/dashboard'),api('/api/v3/approvals'),api('/api/v3/notifications'),
       api('/api/v3/knowledge'),api('/api/v3/calendar'),api('/api/v3/integrations/google/status')]);
    $('ops-approvals-count').textContent=dashboard.pending_approvals;
    $('ops-alerts-count').textContent=dashboard.unread_notifications;
    $('ops-cost').textContent='$'+dashboard.costs.total_estimated_or_actual_usd.toFixed(2);
    $('ops-approvals').innerHTML=approvals.length?approvals.map(a=>`<article class="advanced-row"><strong>${safe(a.action)}</strong><small>${safe(prettyTime(a.requested_at))} · ${safe(a.state)}</small><p class="tiny">${safe(a.payload).slice(0,300)}</p>${a.state==='pending'?`<button class="btn outline" data-approval="${safe(a.id)}" data-decision="true">Approve</button> <button class="btn outline" data-approval="${safe(a.id)}" data-decision="false">Reject</button>`:''}</article>`).join(''):'<p class="muted">No pending approvals.</p>';
    $('ops-alerts').innerHTML=alerts.length?alerts.slice(0,25).map(a=>`<article class="advanced-row"><strong>${safe(a.title)}</strong><small>${safe(a.priority)} · ${safe(prettyTime(a.created_at))}</small><p>${safe(a.detail)}</p>${a.state==='unread'?`<button class="btn outline" data-alert="${safe(a.id)}">Mark read</button>`:''}</article>`).join(''):'<p class="muted">No notifications.</p>';
    $('knowledge-list').innerHTML=docs.length?docs.map(d=>`<article class="advanced-row"><strong>${safe(d.title)}</strong><small>${safe(d.visibility)} · ${safe(d.trust_tier)} · ${safe(prettyTime(d.updated_at))}</small></article>`).join(''):'<p class="muted">No indexed sources.</p>';
    $('calendar-list').innerHTML=calendar.length?calendar.map(e=>`<article class="advanced-row"><strong>${safe(e.title)}</strong><small>${safe(prettyTime(e.starts_at))} · ${safe(e.state)}</small></article>`).join(''):'<p class="muted">No local appointments.</p>';
    $('google-integration-status').textContent=google.connected?'Google services connected.':'Google services not connected.';
    const sel=state.agents.map(a=>`<option value="${safe(a.id)}">${safe(a.name)} · ${safe(a.role)}</option>`).join('');
    const prevVoiceAgent=$('voice-agent')?.value;
    $('voice-agent').innerHTML=sel;$('knowledge-agent').innerHTML=sel;
    if(prevVoiceAgent && state.agents.some(a=>a.id===prevVoiceAgent)){
      $('voice-agent').value=prevVoiceAgent;
    }
    renderSelectedVoiceAgent();
    $('ops-call').innerHTML='<option value="">Choose active call</option>'+state.calls.filter(c=>['queued','initiated','ringing','in-progress'].includes(c.status)).map(c=>`<option value="${safe(c.id)}">${safe(c.phone)} · ${safe(c.status)}</option>`).join('');
  }catch(error){toast('Operations refresh: '+error.message,true);}
}
for(const id of ['ops-refresh','knowledge-refresh','calendar-refresh']) $(id).addEventListener('click',loadAdvanced);
document.addEventListener('click',async e=>{
  const a=e.target.closest('[data-approval]'),n=e.target.closest('[data-alert]'),c=e.target.closest('[data-control]');
  try{
    if(a){const approve=a.dataset.decision==='true';if(!confirm(`Confirm ${approve?'approval':'rejection'} of this action?`))return;
      await api(`/api/v3/approvals/${a.dataset.approval}/decision`,{method:'POST',body:JSON.stringify({approve})});await loadAdvanced();toast('Decision recorded');}
    if(n){await api(`/api/v3/notifications/${n.dataset.alert}/read`,{method:'POST'});await loadAdvanced();}
    if(c){const callId=$('ops-call').value;if(!callId)throw new Error('Choose an active call');
      const command=c.dataset.control,instruction=command==='instruct'?$('ops-instruction').value.trim():null;
      if(command==='stop'&&!confirm('Stop the live voice runtime?'))return;
      await api(`/api/v3/calls/${callId}/control`,{method:'POST',body:JSON.stringify({command,instruction})});toast(`Call control ${command} accepted`);}
  }catch(err){toast(err.message,true);}
});
$('knowledge-form').addEventListener('submit',async e=>{
  e.preventDefault();const input=$('knowledge-file');if(!input.files.length)return;
  const data=new FormData();data.append('file',input.files[0]);data.append('agent_id',$('knowledge-agent').value);
  data.append('visibility',$('knowledge-scope').value);data.append('trust_tier',$('knowledge-tier').value);
  try{const r=await api('/api/v3/knowledge/upload',{method:'POST',body:data});toast(`Ingested ${r.chunks} chunks`);await loadAdvanced();}
  catch(err){toast(err.message,true);}
});
$('knowledge-search').addEventListener('click',async()=>{
  const query=$('knowledge-query').value.trim();if(!query)return;
  try{const hits=await api(`/api/v3/knowledge/search?agent_id=${encodeURIComponent($('knowledge-agent').value)}&query=${encodeURIComponent(query)}`);
    $('knowledge-results').innerHTML=hits.length?hits.map(h=>`<article class="advanced-row"><strong>${safe(h.title)}</strong><small>${safe(h.trust_tier)} · score ${h.score}</small><p>${safe(h.content.slice(0,700))}</p></article>`).join(''):'<p class="muted">No matching excerpts.</p>';
  }catch(err){toast(err.message,true);}
});
$('google-import').addEventListener('click',async()=>{
  if(!confirm('Import your Google Contacts? New contacts will have calling and email consent DISABLED.'))return;
  try{const result=await api('/api/v3/integrations/google/import-contacts',{method:'POST'});toast(`Imported ${result.imported} contacts; skipped ${result.skipped}`);await load();}
  catch(err){toast(err.message,true);}
});
// Refresh advanced panels only when entering the relevant screen.
const oldNavigate=navigate;
navigate=function(page){oldNavigate(page);if(['operations','knowledge','voice-lab','calendar'].includes(page))loadAdvanced();};

let previewSocket=null,previewMic=null,previewAudio=null,previewProcessor=null,previewStream=null,nextPlay=0;
const pcmULaw=(value)=>{
  // G.711 µ-law encoder, input float in [-1,1].
  let pcm=Math.max(-32768,Math.min(32767,Math.round(value*32767)));
  let sign=pcm<0?0x80:0;if(sign)pcm=-pcm;
  pcm=Math.min(32635,pcm+132);
  let exponent=7;for(let mask=0x4000;exponent>0&&!(pcm&mask);mask>>=1)exponent--;
  const mantissa=(pcm>>(exponent+3))&15;
  return (~(sign|(exponent<<4)|mantissa))&255;
};
const ulawFloat=(u)=>{u=(~u)&255;let t=(((u&15)<<3)+132)<<((u>>4)&7);return ((u&0x80)?(132-t):(t-132))/32768;};
function playPCMU(encoded){if(!previewAudio)return;
  const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));if(!bytes.length)return;
  const buffer=previewAudio.createBuffer(1,bytes.length,8000),out=buffer.getChannelData(0);
  for(let i=0;i<bytes.length;i++)out[i]=ulawFloat(bytes[i]);
  const src=previewAudio.createBufferSource();src.buffer=buffer;src.connect(previewAudio.destination);
  nextPlay=Math.max(previewAudio.currentTime+0.04,nextPlay);src.start(nextPlay);nextPlay+=buffer.duration;
}
function renderSelectedVoiceAgent(){
  const card=$('voice-agent-card');
  if(!card)return;
  const currentId=$('voice-agent')?.value;
  const agent=state.agents.find(a=>a.id===currentId)||state.agents[0];
  if(!agent){
    card.innerHTML='<div class="muted small">No configured agent found. Add one in Agent Studio.</div>';
    return;
  }
  const initial=safe((agent.name||'A').slice(0,1).toUpperCase());
  const instr=safe(agent.instructions||'');
  card.innerHTML=`
    <div class="agent-card-header">
      <div class="agent-card-avatar">${initial}</div>
      <div class="agent-card-title">
        <h4>${safe(agent.name)}</h4>
        <span class="agent-role-pill">${safe(agent.role||'Voice Agent')}</span>
      </div>
    </div>
    <div class="agent-card-badges">
      <span class="agent-meta-chip"><span>🌐</span> Language: <strong>${safe(agent.language||'English')}</strong></span>
      <span class="agent-meta-chip"><span>⚡</span> Engine: <strong>GPT-Live (8 kHz PCMU)</strong></span>
      <span class="agent-meta-chip"><span>🛡️</span> Sandbox: <strong>Zero call charges</strong></span>
    </div>
    <div class="agent-instructions-preview">
      <span class="preview-label">Core Persona &amp; Instructions</span>
      <p title="${instr}">${instr||'No working instructions provided.'}</p>
    </div>
    <div class="agent-card-footer">
      <button class="agent-studio-link" type="button" data-open-studio-agent="${safe(agent.id)}">Customize in Agent Studio ↗</button>
    </div>`;
}

let voiceTranscriptState={
  currentSpeaker:null,
  currentBubbleTextEl:null,
  currentPulseEl:null,
  lastDeltaTime:0,
  turnCount:0
};

function resetVoiceTranscriptState(){
  if(voiceTranscriptState.currentPulseEl){
    voiceTranscriptState.currentPulseEl.remove();
    voiceTranscriptState.currentPulseEl=null;
  }
  voiceTranscriptState.currentSpeaker=null;
  voiceTranscriptState.currentBubbleTextEl=null;
  voiceTranscriptState.lastDeltaTime=0;
}

function clearVoiceTranscript(){
  resetVoiceTranscriptState();
  voiceTranscriptState.turnCount=0;
  const turnCountEl=$('voice-turn-count');
  if(turnCountEl) turnCountEl.textContent='0 TURNS';
  const feed=$('voice-captions');
  if(feed){
    feed.innerHTML=`
      <div class="empty-transcript" id="voice-empty-state">
        <div class="tiny-orb">🎙️</div>
        <h3>No preview in progress</h3>
        <p class="muted small">Select an agent and click &ldquo;Start talking&rdquo;. Real-time audio stream from you and the agent will render here conversationally.</p>
      </div>`;
  }
}

async function stopVoice(){
  try{previewSocket?.send(JSON.stringify({type:'stop'}));previewSocket?.close();}catch{}
  previewProcessor?.disconnect();previewStream?.getTracks().forEach(t=>t.stop());await previewAudio?.close();
  previewSocket=previewProcessor=previewStream=previewAudio=null;
  $('voice-start').disabled=false;$('voice-stop').disabled=true;$('voice-status').textContent='DISCONNECTED';
  if($('voice-agent')) $('voice-agent').disabled=false;
  resetVoiceTranscriptState();
}
$('voice-start').addEventListener('click',async()=>{
  $('voice-start').disabled=true;
  if($('voice-agent')) $('voice-agent').disabled=true;
  try{
    const {token}=await api('/api/v3/voice/preview-token',{method:'POST',body:JSON.stringify({agent_id:$('voice-agent').value})});
    const url=`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/api/v3/voice/preview?token=${encodeURIComponent(token)}`;
    previewSocket=new WebSocket(url);$('voice-status').textContent='CONNECTING';
    previewSocket.onmessage=async e=>{
      const msg=JSON.parse(e.data);
      if(msg.type==='ready'){
        try{
          previewAudio=new AudioContext();await previewAudio.resume();previewStream=await navigator.mediaDevices.getUserMedia({audio:true});
          const source=previewAudio.createMediaStreamSource(previewStream),processor=previewAudio.createScriptProcessor(2048,1,1);
          previewProcessor=processor;const muted=previewAudio.createGain();muted.gain.value=0;
          let buffer=[],readPos=0;
          processor.onaudioprocess=e=>{
            const input=e.inputBuffer.getChannelData(0),step=previewAudio.sampleRate/8000;
            while(readPos<input.length){
              const idx=Math.floor(readPos);buffer.push(pcmULaw(input[idx]||0));readPos+=step;
              if(buffer.length>=320){
                if(previewSocket?.readyState===1){
                  const bytes=String.fromCharCode(...buffer.splice(0,320));
                  previewSocket.send(JSON.stringify({type:'audio',audio:btoa(bytes)}));
                }else buffer=[];
              }
            }
            readPos-=input.length;
          };
          source.connect(processor);processor.connect(muted);muted.connect(previewAudio.destination);
          $('voice-status').textContent='LIVE';$('voice-stop').disabled=false;
        }catch(err){toast('Microphone: '+err.message,true);await stopVoice();}
      }else if(msg.type==='audio'){
        playPCMU(msg.audio);
      }else if(msg.type==='caption'){
        const delta=msg.delta;
        if(!delta) return;
        const speaker=msg.speaker;
        const now=Date.now();
        const feed=$('voice-captions');
        
        const empty=$('voice-empty-state');
        if(empty) empty.remove();
        
        const shouldCreateNew=!voiceTranscriptState.currentBubbleTextEl ||
          voiceTranscriptState.currentSpeaker!==speaker ||
          (now-voiceTranscriptState.lastDeltaTime)>2500;
          
        if(shouldCreateNew){
          if(voiceTranscriptState.currentPulseEl){
            voiceTranscriptState.currentPulseEl.remove();
            voiceTranscriptState.currentPulseEl=null;
          }
          
          voiceTranscriptState.turnCount++;
          const turnCountEl=$('voice-turn-count');
          if(turnCountEl) turnCountEl.textContent=`${voiceTranscriptState.turnCount} TURN${voiceTranscriptState.turnCount===1?'':'S'}`;
          
          const currentAgentId=$('voice-agent')?.value;
          const currentAgent=state.agents.find(a=>a.id===currentAgentId);
          const agentName=currentAgent?.name||'Agent';
          const displayName=speaker==='assistant'?agentName:'You';
          const avatarLetter=speaker==='assistant'?safe(agentName.slice(0,1).toUpperCase()):'YOU';
          const timeStr=new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
          
          const turnDiv=document.createElement('div');
          turnDiv.className=`voice-chat-turn ${speaker}`;
          turnDiv.innerHTML=`<div class="voice-chat-meta"><span class="voice-chat-avatar">${avatarLetter}</span><strong class="voice-chat-name">${safe(displayName)}</strong><span class="voice-chat-time">${timeStr}</span></div><div class="voice-chat-bubble"><span class="voice-chat-text"></span><span class="streaming-pulse" aria-hidden="true"></span></div>`;
          
          feed.append(turnDiv);
          voiceTranscriptState.currentSpeaker=speaker;
          voiceTranscriptState.currentBubbleTextEl=turnDiv.querySelector('.voice-chat-text');
          voiceTranscriptState.currentPulseEl=turnDiv.querySelector('.streaming-pulse');
        }
        
        const textEl=voiceTranscriptState.currentBubbleTextEl;
        const currentText=textEl.textContent;
        const cleanDelta=currentText.length===0 ? delta.trimStart() : delta;
        if(!cleanDelta) return;
        
        const needsSpace=currentText.length>0 &&
          !/\s$/.test(currentText) &&
          !/^\s/.test(cleanDelta) &&
          !/^[.,!?;:'")\]]/.test(cleanDelta);
          
        textEl.textContent+=(needsSpace?' ':'')+cleanDelta;
        voiceTranscriptState.lastDeltaTime=now;
        feed.scrollTop=feed.scrollHeight;
      }else if(msg.type==='error'){
        toast(msg.detail,true);
      }else if(msg.type==='info'){
        const feed=$('voice-captions');
        const empty=$('voice-empty-state');
        if(empty) empty.remove();
        const notice=document.createElement('div');
        notice.className='voice-system-notice';
        notice.textContent=msg.detail;
        feed.append(notice);
        feed.scrollTop=feed.scrollHeight;
        $('voice-stop').disabled=false;
      }
    };
    previewSocket.onerror=()=>toast('WebSocket voice preview failed',true);
    previewSocket.onclose=()=>{
      if(previewSocket)$('voice-status').textContent='ENDED';
      $('voice-start').disabled=false;
      if($('voice-agent')) $('voice-agent').disabled=false;
      resetVoiceTranscriptState();
    };
  }catch(err){
    toast(err.message,true);
    if($('voice-agent')) $('voice-agent').disabled=false;
    await stopVoice();
  }
});
$('voice-stop').addEventListener('click',stopVoice);
$('voice-agent')?.addEventListener('change',renderSelectedVoiceAgent);
$('voice-clear-btn')?.addEventListener('click',clearVoiceTranscript);

$('contact-select').addEventListener('change',()=>{const contact=state.contacts.find(c=>c.id===$('contact-select').value);if(contact)$('phone-input').value=contact.phone;});


/* Integrations Hub Implementation */
async function renderIntegrations() {
  const grid = $('integrations-grid');
  if(!grid) return;
  grid.innerHTML = '<div class="muted small">Loading integrations...</div>';
  try {
    const list = await api('/api/v3/integrations');
    grid.innerHTML = list.map(item => {
      const isConnected = item.connected;
      const isCatalog = item.status === 'catalog';
      const statusClass = isConnected ? 'connected' : (isCatalog ? 'catalog' : 'disconnected');
      const statusLabel = isConnected ? '● Connected' : (isCatalog ? 'Coming Soon' : '○ Not connected');
      const icon = item.id === 'google' ? 'G' : (item.id === 'linear' ? 'L' : (item.id === 'outlook' ? 'O' : (item.id === 'teams' ? 'T' : (item.id === 'notion' ? 'N' : 'J'))));

      const toolsHtml = item.tools && item.tools.length ? `
        <div class="integration-tools-wrap">
          <span class="integration-tools-label">Available Agent Tools (${item.tools.length})</span>
          <div class="integration-tools">
            ${item.tools.map(t => `<span class="tool-tag ${t.is_write?'write':''}" title="${safe(t.description)}">${safe(t.name)}</span>`).join('')}
          </div>
        </div>
      ` : (isCatalog ? '<p class="muted tiny">Native connector template ready for activation.</p>' : '<p class="muted tiny">No tools registered.</p>');

      const buttonHtml = isConnected ? `
        <button class="btn outline small" data-disconnect-integration="${safe(item.id)}" type="button">Disconnect</button>
      ` : (isCatalog ? `
        <button class="btn outline small" disabled style="opacity:0.4" type="button">Catalog</button>
      ` : `
        <button class="btn primary small" data-connect-integration="${safe(item.id)}" data-integration-name="${safe(item.name)}" data-auth-type="${safe(item.auth_type)}" type="button">Connect ↗</button>
      `);

      return `
        <div class="integration-card" data-provider-card="${safe(item.id)}">
          <div class="integration-card-head">
            <div class="integration-brand">
              <div class="integration-icon">${icon}</div>
              <div class="integration-meta">
                <h3 class="integration-name">${safe(item.name)}</h3>
                <span class="integration-cat">${safe(item.category)} · ${safe(item.auth_type)}</span>
              </div>
            </div>
            <span class="status-chip ${statusClass}">${statusLabel}</span>
          </div>
          <p class="integration-desc">${safe(item.description)}</p>
          ${toolsHtml}
          <div class="integration-card-actions">
            <span class="permitted-count"><strong>${item.permitted_agents_count || 0}</strong> agents assigned</span>
            ${buttonHtml}
          </div>
        </div>
      `;
    }).join('');
  } catch(err) {
    grid.innerHTML = `<div class="error-msg">Failed to load integrations: ${safe(err.message)}</div>`;
  }
}

// Integration connect/disconnect events
document.addEventListener('click', async (e) => {
  const connBtn = e.target.closest('[data-connect-integration]');
  if(connBtn) {
    const providerId = connBtn.dataset.connectIntegration;
    const providerName = connBtn.dataset.integrationName;
    const authType = connBtn.dataset.authType;
    $('connect-provider-id').value = providerId;
    $('connect-modal-title').textContent = `Connect ${providerName}`;
    const fields = $('connect-fields');
    if(authType === 'api_key') {
      fields.innerHTML = `
        <label>API Key / Personal Access Token
          <input id="connect-api-key" type="password" required placeholder="Paste your API key" autocomplete="off" />
        </label>
        <label>Default Team Identifier (optional)
          <input id="connect-team" placeholder="e.g. ENG" value="ENG" />
        </label>
      `;
      $('connect-modal-hint').textContent = 'Your API token is encrypted with Fernet at rest and is never exposed to browser context.';
    } else {
      const authQuery = state.key ? `?api_key=${encodeURIComponent(state.key)}` : '';
      fields.innerHTML = `
        <p class="muted small">Google Workspace uses OAuth 2.0 to access Gmail and Google Calendar. You can authorize with Google directly using your configured Google credentials, or provide an access token below for test/offline mode.</p>
        <div style="margin: 14px 0;">
          <a class="btn primary small" style="display:inline-flex;align-items:center;gap:6px;" href="/auth/google/connect${authQuery}">
            <span>Sign in & Authorize with Google</span> <span>↗</span>
          </a>
        </div>
        <div class="muted tiny" style="margin-bottom:10px;">— OR ENTER TOKEN FOR PREVIEW / TESTING —</div>
        <label>Access Token (or test token)
          <input id="connect-api-key" type="text" value="demo-oauth-token" required />
        </label>
      `;
      $('connect-modal-hint').textContent = 'Live OAuth sessions store refresh tokens encrypted with Fernet at rest.';
    }
    $('integration-connect-modal').hidden = false;
    return;
  }

  const disBtn = e.target.closest('[data-disconnect-integration]');
  if(disBtn) {
    const providerId = disBtn.dataset.disconnectIntegration;
    if(!confirm(`Disconnect ${providerId} and revoke stored credentials?`)) return;
    try {
      await api(`/api/v3/integrations/${providerId}/disconnect`, { method: 'POST' });
      toast(`Disconnected ${providerId}`);
      await renderIntegrations();
    } catch(err) {
      toast(err.message, true);
    }
    return;
  }

  if(e.target.id === 'connect-modal-close' || e.target.id === 'connect-modal-cancel' || e.target.id === 'integration-connect-modal') {
    $('integration-connect-modal').hidden = true;
    return;
  }

  if(e.target.id === 'integrations-refresh') {
    renderIntegrations();
    return;
  }
});

const connectForm = $('integration-connect-form');
if(connectForm) {
  connectForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const providerId = $('connect-provider-id').value;
    const key = $('connect-api-key').value.trim();
    const teamEl = $('connect-team');
    const team = teamEl ? teamEl.value.trim() : undefined;
    try {
      const payload = { api_key: key, access_token: key, default_team: team };
      await api(`/api/v3/integrations/${providerId}/connect`, {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      $('integration-connect-modal').hidden = true;
      toast(`Successfully connected ${providerId}!`);
      await renderIntegrations();
    } catch(err) {
      toast(err.message, true);
    }
  });
}
