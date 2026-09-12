'use strict';
const $ = (s) => document.querySelector(s);
const state = {user:null, config:{}, profile:null, resumes:[], jobs:[], runs:[], usage:{}, route:'overview', filter:'ELIGIBLE', search:''};
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const initials = (name) => name.split(/\s+/).slice(0,2).map(x=>x[0]).join('').toUpperCase();
const list = (v) => String(v||'').split(',').map(x=>x.trim()).filter(Boolean);
const money = (n) => n ? '₹'+(n/100000).toLocaleString('en-IN',{maximumFractionDigits:1})+'L / year' : 'Salary not disclosed';
const when = (v) => v ? new Date(v*1000).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}) : '—';
let toastTimer, polling = false;
function toast(text,error=false){const el=$('#toast');el.textContent=text;el.hidden=false;el.className=error?'error':'';clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.hidden=true,6500);}
async function api(path, options={}) {
  const headers = {...(options.headers||{})};
  if(state.user?.csrf) headers['X-CSRF-Token']=state.user.csrf;
  if(options.body && !(options.body instanceof FormData)){headers['Content-Type']='application/json';options.body=JSON.stringify(options.body);}
  const res=await fetch('/api'+path,{...options,headers,credentials:'same-origin'});
  const data=await res.json();
  if(!res.ok){const detail=Array.isArray(data.detail)?data.detail.map(x=>`${x.loc.slice(1).join('.')}: ${x.msg}`).join('; '):data.detail;throw new Error(detail||'Something went wrong. Please try again.');}
  return data;
}
async function refresh(renderPage=true){
  const [profile,resumes,jobs,runs,usage]=await Promise.all([api('/profile'),api('/resumes'),api('/jobs'),api('/runs'),api('/usage')]);
  Object.assign(state,{profile:profile.data,resumes,jobs,runs,usage});
  $('#nav-count').textContent=jobs.filter(j=>j.match.status==='ELIGIBLE'&&!j.application_status).length;
  if(renderPage)render();
}
function authenticated(){
  $('#landing').hidden=true;$('#workspace').hidden=false;
  $('#user-name').textContent=state.user.name;$('#user-initials').textContent=initials(state.user.name);$('#top-avatar').textContent=initials(state.user.name).slice(0,1);
  $('#mode-pill').textContent=state.user.demo?'Demo · no real submissions':state.config.delivery==='provider'?'Connected delivery':'Manual application mode';
  document.querySelectorAll('dialog[open]').forEach(d=>d.close());
  if(!location.hash)location.hash='overview';
}
function badge(status){const green=['ELIGIBLE','CONFIRMED','COMPLETE','SIMULATED','PAID'].includes(status);const red=['REJECTED','FAILED','CANCELLED'].includes(status);const labels={ELIGIBLE:'Good match',REJECTED:'Not a fit',NEEDS_REVIEW:'Needs review',NEEDS_ACTION:'Your action needed',SIMULATED:'Simulated',WAITING_QUOTA:'Allowance used',SUBMITTING:'Submitting'};return `<span class="badge ${green?'green':red?'red':'orange'}">${esc(labels[status]||status.toLowerCase().replaceAll('_',' '))}</span>`;}
function heading(title,subtitle,action=''){return `<div class="page-heading"><div><h1>${title}</h1><p>${subtitle}</p></div>${action}</div>`;}
function empty(title,text,button=''){return `<div class="empty"><div class="empty-icon">⌕</div><h3>${title}</h3><p>${text}</p>${button}</div>`;}
function jobCard(j){return `<article class="job-card"><div class="job-top"><div class="company-logo">${esc(initials(j.company))}</div><div><h3>${esc(j.title)}</h3><p>${esc(j.company)}</p></div>${badge(j.match.status)}</div><div class="job-details"><span>⌖ ${esc(j.work_mode==='remote'?'Remote':j.location||'Location unknown')}</span><span>◷ ${j.minimum_experience===null?'Experience unknown':esc(j.minimum_experience)+'+ years'}</span><span>${esc(money(j.salary_max_inr))}</span></div><div class="tags">${(j.match.matched_skills||[]).map(s=>`<b>${esc(s)}</b>`).join('')}</div><div class="job-bottom"><p>${esc(j.application_status?'Already in your tracker · '+j.application_status.toLowerCase():j.match.reason)}</p><a href="${esc(j.url)}" target="_blank" rel="noopener noreferrer" aria-label="View ${esc(j.title)} at ${esc(j.company)}">View ↗</a></div></article>`;}
function overview(){
  const eligible=state.jobs.filter(j=>j.match.status==='ELIGIBLE'&&!j.application_status);
  const attempts=state.runs.flatMap(r=>r.attempts), complete=attempts.filter(a=>['CONFIRMED','SIMULATED'].includes(a.status)).length;
  const first=state.user.name.split(' ')[0];
  const action='<button class="button primary" data-action="start">'+(state.user.demo?'Start demo run':state.config.delivery==='manual'?'Prepare applications':'Start applications')+' <span>↗</span></button>';
  return heading(`A new chapter, ${esc(first)} <span style="color:#9ca886">✦</span>`, 'A little less searching. A little closer to your next role.', action)+
  `<section class="hero-card"><div><div class="eyebrow">YOUR NEXT MOVE STARTS HERE</div><h2>Good opportunities.<br>Better matched to you.</h2><p>We look for the right role and real skill overlap.<br>Your preferences set the direction.</p><a href="#jobs" class="button">Explore my matches <span>↗</span></a></div><div class="hero-graphic" aria-hidden="true"><span class="graphic-arrow">↗</span><div class="bar one"></div><div class="bar two"></div><div class="bar three"></div></div></section>`+
  `<div class="stats-grid"><div class="stat"><div class="stat-label">Ready-to-review matches <span>⌕</span></div><div class="stat-value">${eligible.length}</div><div class="stat-note"><strong>Aligned with your preferences</strong></div></div><div class="stat"><div class="stat-label">${state.user.demo?'Simulated applications':'Confirmed applications'} <span>↗</span></div><div class="stat-value">${complete}</div><div class="stat-note">${state.user.demo?'Demo activity only':'Verified delivery outcomes'}</div></div><div class="stat"><div class="stat-label">${state.usage.paid?'Today’s credits left':'Free credits left'} <span>◇</span></div><div class="stat-value">${state.usage.remaining??10}<span style="font-size:13px;color:#aab09f"> / ${state.usage.paid?40:10}</span></div><div class="stat-note">${state.usage.paid?'Resets '+esc(when(state.usage.resets_at)):'Your one-time starting allowance'}</div></div><div class="stat"><div class="stat-label">Skills guiding your search <span>◎</span></div><div class="stat-value">${state.profile?.selected_skills.length||0}</div><div class="stat-note">At least ${state.profile?.minimum_skills||3} must match each job</div></div></div>`+
  `<div class="content-grid"><section><div class="section-heading"><div><h2>Opportunities with your name on them</h2><p>Filtered by role, skills, experience, and location.</p></div><a href="#jobs">View all →</a></div>${eligible.slice(0,3).map(jobCard).join('')||empty('Let’s find your fit','Add your resume and preferences, then import job descriptions to see matching roles.','<a class="button secondary small" href="#profile">Set up my profile →</a>')}</section><aside class="side-column"><div class="side-card"><h3>Your search essentials</h3><div class="resume-mini"><span>PDF</span><div><strong>${esc(state.resumes[0]?.filename||'Add your resume')}</strong><small>${state.resumes.length?'Private to your account':'PDF or DOCX · up to 5 MB'}</small></div></div><div class="progress"><div style="width:${state.profile?100:25}%"></div></div><div class="small-line"><span>${state.profile?'Profile confirmed':'Profile setup'}</span><span>${state.profile?'Ready':'Let’s begin'}</span></div><a class="side-link" href="#profile">Edit profile & preferences ↗</a></div><div class="side-card"><h3>Your application allowance</h3><div class="small-line"><span>${state.usage.paid?'Seven-day pass':'Free starter'}</span>${badge(state.usage.paid?'PAID':'ELIGIBLE')}</div><p>${state.usage.paid?'A focused week. Up to 40 confirmed applications in each 24-hour window.':'Try your first 10 confirmed applications. Upgrade when you’re ready.'}</p><a class="side-link" href="#billing">${state.usage.paid?'View pass details':'Meet the seven-day pass'} →</a></div><div class="hint-card"><div class="eyebrow">A SMALL REMINDER</div><h3>Quality is the point.</h3><p>We won’t apply to an unrelated role just to fill your daily allowance. Fewer, better matches are worth it.</p></div></aside></div>`+
  (state.user.demo?'<p class="notice">You’re exploring sample companies in a demo workspace. All delivery and billing here are simulated.</p>':'');
}
function jobsPage(){
  let jobs=state.jobs.filter(j=>(state.filter==='all'||(state.filter==='excluded'?j.match.status!=='ELIGIBLE':j.match.status==='ELIGIBLE'))&&`${j.title} ${j.company} ${j.location}`.toLowerCase().includes(state.search.toLowerCase()));
  return heading('Find the right kind of next.', 'Every match has a reason. Every preference is yours.', '<div class="action-group"><button class="button secondary" data-action="import">+ Add a job</button><button class="button primary" data-action="start">'+(state.config.delivery==='manual'&&!state.user.demo?'Prepare applications':'Start a run')+' ↗</button></div>')+
  `<div class="toolbar"><div class="tabs" role="group" aria-label="Filter jobs">${[['ELIGIBLE','Good matches'],['excluded','Needs review / excluded'],['all','All jobs']].map(([v,t])=>`<button class="tab ${state.filter===v?'active':''}" data-filter="${v}">${t}</button>`).join('')}</div><input class="search" id="job-search" type="search" placeholder="Search title, company, city…" aria-label="Search jobs" value="${esc(state.search)}"></div>`+
  `<div class="jobs-grid">${jobs.map(jobCard).join('')}</div>${!jobs.length?empty('Nothing here just yet','Add a job description or adjust your confirmed preferences. Unknown requirements are kept for review.','<button class="button secondary" data-action="import">Add a job →</button>'):''}`+
  `<p class="fine-print">Job descriptions are ${state.user.demo?'sample data':'provided by you or a configured licensed feed'}. <button class="text-button" data-action="sync">Sync configured feed ↻</button></p>`;
}
function field(name,label,value,type='text',extra=''){return `<label>${label}<input name="${name}" type="${type}" value="${esc(value??'')}" ${extra}></label>`;}
function profilePage(){
  const p=state.profile||{full_name:state.user.name,email:state.user.email,experience_years:0,notice_days:30,current_ctc_inr:0,expected_ctc_inr:0,preferred_city:'Pune',latitude:18.5204,longitude:73.8567,radius_km:50,skills:[],selected_skills:[],target_titles:['Data Engineer'],minimum_skills:3,work_modes:['remote','hybrid']};
  return heading('Start with your story.', 'Your resume and preferences guide every match. You stay in control.')+
  `<div class="card"><h2>01 / Your resume</h2><p class="subtitle">A private copy for your applications. Review all extracted suggestions.</p><div class="upload-zone"><span class="upload-icon">⇧</span><p><strong>Choose a PDF or Word document</strong></p><p>PDF & DOCX · maximum 5 MB · text-based documents</p><input id="resume-upload" type="file" accept=".pdf,.docx" aria-label="Upload your resume"></div><div id="resume-files">${state.resumes.map(r=>`<div class="resume-row"><div><strong>${esc(r.filename)}</strong><p class="fine-print">Uploaded ${esc(when(r.created_at))}</p></div><div><a href="/api/resumes/${r.id}/download">Download ↗</a><button class="text-button" data-delete-resume="${r.id}" aria-label="Delete ${esc(r.filename)}">Delete</button></div></div>`).join('')}</div></div>`+
  `<form id="profile-form"><section class="card"><h2>02 / A little about you</h2><p class="subtitle">Use accurate details. We never infer permission or invent qualifications.</p><div class="form-grid">${field('full_name','Full name',p.full_name,'text','required maxlength="150"')}${field('email','Email',p.email||state.user.email,'email','required')}${field('phone','Phone',p.phone,'tel')}${field('experience_years','Total relevant experience (years)',p.experience_years,'number','required min="0" max="60" step="0.5"')}${field('notice_days','Notice period (days)',p.notice_days,'number','required min="0" max="365"')}${field('current_ctc_inr','Current CTC (annual ₹, e.g. 1200000)',p.current_ctc_inr,'number','required min="0"')}${field('expected_ctc_inr','Expected CTC (annual ₹)',p.expected_ctc_inr,'number','required min="0"')}</div></section>`+
  `<section class="card"><h2>03 / What does a good fit look like?</h2><p class="subtitle">Use commas to separate titles and skills. Titles are matched exactly, ignoring case.</p><div class="form-grid"><label class="span-2">Approved job titles<input name="target_titles" required value="${esc(p.target_titles.join(', '))}" placeholder="Data Engineer, AWS Data Engineer"></label><label class="span-2">Your confirmed skills<input name="skills" required value="${esc(p.skills.join(', '))}" placeholder="Python, SQL, AWS, PySpark"></label><label class="span-2">Skills that must guide matching<input name="selected_skills" required value="${esc(p.selected_skills.join(', '))}" placeholder="Python, SQL, AWS, PySpark"></label>${field('minimum_skills','Minimum distinct skill matches',p.minimum_skills,'number','required min="3" max="30"')}${field('preferred_city','Preferred location',p.preferred_city,'text','required')}${field('latitude','Location latitude',p.latitude,'number','required step="any" min="-90" max="90"')}${field('longitude','Location longitude',p.longitude,'number','required step="any" min="-180" max="180"')}${field('radius_km','Nearby radius (km)',p.radius_km,'number','required min="1" max="20000"')}<div><label>Work preferences</label><div class="check-row">${['remote','hybrid','onsite'].map(v=>`<label class="check"><input type="checkbox" name="work_modes" value="${v}" ${p.work_modes.includes(v)?'checked':''}>${v==='onsite'?'On-site':v[0].toUpperCase()+v.slice(1)}</label>`).join('')}</div></div></div><p class="fine-print">Distance is approximate straight-line distance, not travel distance. Remote roles bypass the radius check. Update coordinates when changing your city.</p><label class="check"><input name="strict_salary" type="checkbox" ${p.strict_salary?'checked':''}>Only match jobs with a disclosed salary range meeting my expectation.</label><label class="check"><input name="confirmed" type="checkbox" required ${state.profile?.confirmed?'checked':''}>I’ve reviewed these details and confirm they are accurate.</label><div class="form-actions"><button class="button primary">Save profile & see matches →</button></div></section></form>`;
}
function applicationsPage(){return heading('Every step, in one place.', 'Real confirmations, honest status updates, and room to pause.', '<a class="button secondary" href="/api/export">Export CSV ↓</a>')+
  (state.runs.length?state.runs.map(r=>`<section class="card"><div class="run-header"><div><strong>${r.mode==='demo'?'Demo run':r.mode==='manual'?'Manual preparation':'Application run'} · ${esc(when(r.created_at))}</strong><p>${esc(r.message)}</p>${badge(r.status)} ${r.daily?'<span class="badge">Daily · next '+esc(when(r.next_at))+'</span>':''}</div>${!['COMPLETE','CANCELLED'].includes(r.status)?`<div class="run-actions"><button class="button secondary small" data-run="${r.id}" data-run-action="${r.status==='PAUSED'?'resume':'pause'}">${r.status==='PAUSED'?'Resume':'Pause'}</button><button class="button secondary small" data-run="${r.id}" data-run-action="cancel">Cancel</button></div>`:''}</div><div class="table-wrap"><table><thead><tr><th>Opportunity</th><th>Status</th><th>Next step</th></tr></thead><tbody>${r.attempts.map(a=>`<tr><td><strong>${esc(a.title)}</strong><small>${esc(a.company)}</small></td><td>${badge(a.status)}<small>${esc(a.reason)}</small></td><td><a href="${esc(a.url)}" target="_blank" rel="noopener noreferrer">Open job ↗</a>${a.status==='UNCERTAIN'?`<button class="text-button" data-attempt="${a.id}" data-attempt-action="reconcile">Check status</button>`:r.mode==='manual'&&a.status==='NEEDS_ACTION'?`<button class="text-button" data-attempt="${a.id}" data-attempt-action="manual-confirm">I applied manually</button>`:''}</td></tr>`).join('')}</tbody></table></div></section>`).join(''):empty('Your next step is waiting.','Start with a matching role. Your applications and their outcomes will appear here.','<a class="button primary" href="#jobs">Explore matches ↗</a>'));}
function billingPage(){return heading('A focused week. More momentum.', 'Simple pricing. No automatic renewal. No promise of a job or an interview.')+
  `<div class="billing-summary">${state.usage.paid?`${badge('PAID')} Your pass ends <strong>${esc(when(state.usage.expires_at))}</strong>. ${state.usage.remaining} credits remain in this window.`:`You have <strong>${state.usage.free_remaining} of 10</strong> free ${state.user.demo?'demo ':''}credits remaining.`}</div><div class="pricing-grid"><section class="pricing-card"><div class="eyebrow">A GOOD PLACE TO START</div><h2>First steps</h2><div class="price">₹0 <small>/ once per account</small></div><p>Find your fit before you go further.</p><ul><li>10 confirmed applications</li><li>Resume and profile setup</li><li>Role + skill matching</li><li>Application tracker</li></ul><a class="button secondary full" href="#jobs">Explore your matches →</a></section><section class="pricing-card featured"><div class="eyebrow">ONE FOCUSED WEEK</div><h2>The seven-day pass</h2><div class="price">₹199 <small>/ 7 days</small></div><p>A little more room to move forward.</p><ul><li>Up to 40 confirmed applications a day</li><li>Seven 24-hour windows · 280 maximum</li><li>Optional daily application runs</li><li>No automatic renewal</li></ul><button class="button primary full" data-action="upgrade" ${state.usage.paid?'disabled':''}>${state.usage.paid?'Your pass is active':state.user.demo?'Activate demo pass · no charge':'Get the seven-day pass ↗'}</button></section></div>`+
  `<p class="notice">${state.user.demo?'Demo billing is simulated. Activating a demo pass does not charge ₹199 or submit real applications.':state.config.sales_enabled?'Payment is processed by Razorpay. Access starts after verified payment confirmation.':'Paid checkout is disabled until a supported delivery provider is configured. Manual handoffs do not consume application credits.'}</p><div class="faq"><details open><summary>What counts as an application?</summary><p>Only a confirmed submission consumes a completed-application credit. Failed attempts release their reservation. Uncertain submissions keep a reserved credit until their outcome is reconciled.</p></details><details><summary>When does my daily allowance reset?</summary><p>Your seven-day pass starts at activation. Each 24-hour window has 40 credits, with no rollover. The dashboard shows the reset time. A pass lasts 168 hours.</p></details><details><summary>Will the tool always apply to 40 jobs?</summary><p>No. It applies only to available eligible jobs. It will not loosen your preferences to fill the allowance. Daily scheduling checks newly imported jobs; it does not promise new listings.</p></details><details><summary>Does Google sign-in connect my LinkedIn account?</summary><p>No. It signs you into ApplyWell. Application delivery is a separate integration. Without supported delivery, the tool prepares matches for you to apply manually.</p></details></div>`;}
function render(){
  if(!state.user)return;
  const requested=location.hash.slice(1)||'overview';state.route=['overview','jobs','profile','applications','billing'].includes(requested)?requested:'overview';
  const labels={overview:'Overview',jobs:'Job matches',profile:'My profile & resume',applications:'Applications',billing:'My plan'};
  $('#breadcrumb').textContent=labels[state.route];document.title=labels[state.route]+' · ApplyWell';
  document.querySelectorAll('[data-route]').forEach(a=>a.classList.toggle('active',a.dataset.route===state.route));
  $('#page').innerHTML=({overview,jobs:jobsPage,profile:profilePage,applications:applicationsPage,billing:billingPage}[state.route])();
  if(state.route==='profile')$('#page').insertAdjacentHTML('beforeend','<section class="card"><h2>Your data stays yours.</h2><p class="subtitle">Export your workspace or remove personal documents and history.</p><div class="action-group"><a class="button secondary" href="/api/account/export">Export my data ↓</a><button class="button secondary" data-action="delete-account">Delete workspace data</button></div></section>');
}
async function openRun(){
  if(!state.resumes.length||!state.profile){location.hash='profile';toast('Upload a resume and confirm your profile first.');return;}
  $('#run-resume').innerHTML=state.resumes.map(r=>`<option value="${r.id}">${esc(r.filename)}</option>`).join('');
  $('#run-mode-description').textContent=state.user.demo?'This demo simulates delivery using sample jobs. It never submits to employers.':state.config.delivery==='provider'?'This run sends your selected resume and confirmed profile to the configured application provider for eligible jobs.':'This deployment prepares manual applications. Open the job links to submit yourself. No credits are charged.';
  $('#run-dialog').showModal();
}
async function loadScript(url){return new Promise((resolve,reject)=>{const s=document.createElement('script');s.src=url;s.onload=resolve;s.onerror=()=>reject(new Error('External service could not load. Please try again.'));document.head.append(s);});}
async function upgrade(){
  if(state.user.demo){await api('/billing/demo-pass',{method:'POST'});await refresh();toast('Demo pass activated. No payment was taken.');return;}
  const order=await api('/billing/checkout',{method:'POST'});
  if(!window.Razorpay)await loadScript('https://checkout.razorpay.com/v1/checkout.js');
  const checkout=new window.Razorpay({...order,name:'ApplyWell',description:'One-time seven-day pass · no auto-renewal',prefill:{name:state.user.name,email:state.user.email},handler:async(response)=>{try{await api('/billing/verify',{method:'POST',body:response});await refresh();toast('Payment verified. Your seven-day pass is ready.');}catch(e){toast(e.message,true);}},theme:{color:'#185b49'}});checkout.open();
}
document.addEventListener('click',async(event)=>{
  const target=event.target.closest('button,[data-action]');if(!target)return;
  if(!target.dataset.action&&!target.dataset.filter&&!target.dataset.run&&!target.dataset.deleteResume&&!target.dataset.attempt)return;
  if(target.dataset.filter){state.filter=target.dataset.filter;render();return;}
  if(target.dataset.action==='close-dialog'){target.closest('dialog').close();return;}
  target.disabled=true;
  try{
    const action=target.dataset.action;
    if(action==='login')$('#login-dialog').showModal();
    if(action==='demo'){state.user=await api('/auth/demo',{method:'POST'});authenticated();await refresh();}
    if(action==='logout'){await api('/auth/logout',{method:'POST'});state.user=null;$('#workspace').hidden=true;$('#landing').hidden=false;location.hash='';}
    if(action==='start')await openRun();
    if(action==='import')$('#import-dialog').showModal();
    if(action==='upgrade')await upgrade();
    if(action==='delete-account')$('#delete-dialog').showModal();
    if(target.dataset.attempt){await api(`/attempts/${target.dataset.attempt}/${target.dataset.attemptAction}`,{method:'POST'});await refresh();toast('Application status updated.');}
    if(action==='sync'){await api('/jobs/sync',{method:'POST'});await refresh();toast('Job feed refreshed.');}
    if(target.dataset.run){await api(`/runs/${target.dataset.run}/${target.dataset.runAction}`,{method:'POST'});await refresh();toast('Run updated.');}
    if(target.dataset.deleteResume){await api('/resumes/'+target.dataset.deleteResume,{method:'DELETE'});await refresh();toast('Resume deleted.');}
  }catch(e){toast(e.message,true);}finally{target.disabled=false;}
});
document.addEventListener('input',event=>{if(event.target.id==='job-search'){state.search=event.target.value;const pos=event.target.selectionStart;render();$('#job-search').focus();if(pos!==null)$('#job-search').setSelectionRange(pos,pos);}});
document.addEventListener('change',async(event)=>{
  if(event.target.id!=='resume-upload'||!event.target.files[0])return;
  const file=event.target.files[0];if(file.size>5*1024*1024){toast('Choose a file smaller than 5 MB.',true);return;}
  event.target.disabled=true;
  try{
    const body=new FormData();body.append('file',file);toast('Reading your resume…');
    const data=await api('/resumes',{method:'POST',body});await refresh();
    const form=$('#profile-form');
    if(form){form.elements.skills.value=data.extracted.skills.join(', ');form.elements.selected_skills.value=data.extracted.skills.slice(0,4).join(', ');form.elements.confirmed.checked=false;if(data.extracted.email)form.elements.email.value=data.extracted.email;}
    toast('Resume uploaded. Review the suggested skills, then confirm and save your profile.');
  }catch(e){toast(e.message,true);event.target.disabled=false;}
});
document.addEventListener('submit',async(event)=>{
  const form=event.target;if(!['profile-form','job-form','run-form','delete-form'].includes(form.id))return;
  event.preventDefault();const submit=form.querySelector('button[type="submit"], button:not([type])');if(submit)submit.disabled=true;
  const values=new FormData(form), body=Object.fromEntries(values);
  try{
    if(form.id==='delete-form'){await api('/account',{method:'DELETE'});$('#delete-dialog').close();state.user=null;$('#workspace').hidden=true;$('#landing').hidden=false;location.hash='';toast('Workspace data removed.');return;}
    if(form.id==='profile-form'){
      for(const k of ['skills','selected_skills','target_titles'])body[k]=list(body[k]);
      for(const k of ['experience_years','notice_days','current_ctc_inr','expected_ctc_inr','latitude','longitude','radius_km','minimum_skills'])body[k]=Number(body[k]);
      body.work_modes=values.getAll('work_modes');body.strict_salary=values.has('strict_salary');body.confirmed=values.has('confirmed');
      await api('/profile',{method:'PUT',body});await refresh(false);location.hash='jobs';render();toast('Profile saved. Your matches have been updated.');
    }
    if(form.id==='job-form'){
      for(const k of ['minimum_experience','salary_max_inr','latitude','longitude'])body[k]=body[k]===''?null:Number(body[k]);
      body.required_skills=list(body.required_skills);body.source='manual';body.external_id=body.url;
      if(body.external_id.length>200)body.external_id=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(body.url)).then(b=>Array.from(new Uint8Array(b)).map(v=>v.toString(16).padStart(2,'0')).join(''));
      await api('/jobs',{method:'POST',body:{jobs:[body]}});$('#import-dialog').close();form.reset();await refresh();toast('Job added and evaluated.');
    }
    if(form.id==='run-form'){
      body.limit=Number(body.limit);body.daily=values.has('daily');body.authorized=values.has('authorized');
      await api('/runs',{method:'POST',body,headers:{'Idempotency-Key':crypto.randomUUID()}});$('#run-dialog').close();await refresh(false);location.hash='applications';render();toast('Run queued. The background worker will process it.');
    }
  }catch(e){toast(e.message,true);}finally{if(submit)submit.disabled=false;}
});
window.addEventListener('hashchange',()=>{render();window.scrollTo(0,0);});
async function init(){
  try{
    state.config=await api('/config');
    document.querySelectorAll('[data-action="demo"]').forEach(b=>b.hidden=!state.config.demo_enabled);
    $('#google-unavailable').hidden=state.config.google_ready;
    if(state.config.google_ready){
      loadScript('https://accounts.google.com/gsi/client').then(()=>{
        google.accounts.id.initialize({client_id:state.config.google_client_id,callback:async(result)=>{try{state.user=await api('/auth/google',{method:'POST',body:{credential:result.credential}});authenticated();await refresh();}catch(e){toast(e.message,true);}}});
        google.accounts.id.renderButton($('#google-button'),{theme:'outline',size:'large',width:360});
      }).catch(e=>toast(e.message,true));
    }
    try{state.user=await api('/me');authenticated();await refresh();}catch(e){state.user=null;}
  }catch(e){toast('Unable to connect to the server. '+e.message,true);}
}
setInterval(async()=>{if(!state.user||polling||document.hidden||document.querySelector('dialog[open]'))return;polling=true;try{await refresh(['overview','applications','billing'].includes(state.route));}catch(e){/* A transient network error is retried on the next poll. */}finally{polling=false;}},4000);
init();
