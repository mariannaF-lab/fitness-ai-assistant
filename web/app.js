'use strict';
const $ = s => document.querySelector(s);
const form = $('#profile-form');
let step = 0, csrf = '', state = {programs: []}, busy = false;
const labels = {age:'Возраст',goal:'Цель',fitness_level:'Опыт',current_activity:'Активность',sessions_per_week:'Занятий в неделю',session_duration_minutes:'Минут на занятие',training_location:'Место',equipment:'Оборудование',health_info_status:'Ответ об ограничениях',limitations:'Ограничения',preferences:'Пожелания'};
const values = {beginner:'Начинающий',intermediate:'Есть опыт',advanced:'Продвинутый',home:'Дома',gym:'В зале',outdoor:'На улице',provided:'Сообщены',declined:'Отказ от ответа'};
const el = (tag, text, cls) => {const e=document.createElement(tag); if(text!==undefined)e.textContent=text; if(cls)e.className=cls; return e;};
const button = (text, handler, cls='button secondary') => {const b=el('button',text,cls);b.type='button';b.onclick=handler;return b;};
function status(selector, text, error=false) {const e=$(selector);e.textContent=text;e.className='status '+(error?'error':'success');}
async function api(path, data) {
  const response = await fetch('/api/'+path, {method:data===undefined?'GET':'POST',headers:data===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:data===undefined?undefined:JSON.stringify(data)});
  let result;try{result=await response.json();}catch{throw Error('Сервер вернул неожиданный ответ. Повторите позже.');}
  if(!response.ok)throw Error(result.error||'Не удалось выполнить запрос');return result;
}
function profile() {
  const f=new FormData(form);return {age:Number(f.get('age')),goal:f.get('goal'),fitness_level:f.get('fitness_level'),current_activity:f.get('current_activity'),sessions_per_week:Number(f.get('sessions_per_week')),session_duration_minutes:Number(f.get('session_duration_minutes')),training_location:f.get('training_location'),equipment:f.get('equipment').split(',').map(x=>x.trim()).filter(Boolean),health_info_status:f.get('health_info_status'),limitations:f.get('health_info_status')==='declined'?null:f.get('limitations'),preferences:f.get('preferences'),data_consent:f.get('data_consent')==='on'};
}
function showStep() {
  document.querySelectorAll('[data-step]').forEach(f=>f.hidden=Number(f.dataset.step)!==step);
  $('#back').hidden=step===0;$('#next').hidden=step===3;$('#save').hidden=step!==3;
  $('#step-label').textContent=`ШАГ ${step+1} ИЗ 4`;$('#progress-bar').style.width=((step+1)*25)+'%';
  document.querySelectorAll('#steps li').forEach((e,i)=>{e.classList.toggle('selected',i===step);if(i===step)e.setAttribute('aria-current','step');else e.removeAttribute('aria-current');});
  if(step===3){const summary=$('#summary');summary.replaceChildren();const p=profile();for(const [key,label] of Object.entries(labels)){const row=el('div');let value=p[key];value=Array.isArray(value)?value.join(', ')||'Без оборудования':values[value]||value||'Не указано';row.append(el('dt',label),el('dd',String(value)));summary.append(row);}}
}
function validStep(){for(const input of $(`[data-step="${step}"]`).querySelectorAll('input,textarea,select'))if(!input.reportValidity())return false;return true;}
$('#next').onclick=()=>{if(validStep()){step++;showStep();}};
$('#back').onclick=()=>{step--;showStep();};
function health(){const declined=$('#health-status').value==='declined';$('#limitations-wrap').hidden=declined;$('#limitations').required=!declined;$('#decline-note').hidden=!declined;}
$('#health-status').onchange=health;
form.addEventListener('submit',async event=>{event.preventDefault();if(busy)return;busy=true;$('#save').disabled=true;try{await api('profile',profile());await refresh();status('#form-status','Анкета сохранена. Теперь можно создать программу.');$('#programs').scrollIntoView({behavior:'smooth'});}catch(e){status('#form-status',e.message,true);}finally{busy=false;$('#save').disabled=false;}});
async function refresh(fill=false){state=await api('state');csrf=state.csrf;
  if(fill&&state.profile){for(const [key,value]of Object.entries(state.profile)){const input=form.elements.namedItem(key);if(!input)continue;if(input.type==='checkbox')input.checked=Boolean(value);else input.value=Array.isArray(value)?value.join(', '):value||'';}health();}
  $('#connection').textContent=state.configured?'GigaChat настроен. После подтверждения анкеты можно запросить программу.':'Анкету можно заполнить и сохранить. Генерация пока не подключена: добавьте ключ и название модели в локальный .env.';
  $('#generate').disabled=!state.profile||!state.configured||busy;
  if(state.telegram_url){$('#telegram').hidden=false;$('#telegram').href=state.telegram_url;}
  $('#adapt-panel').hidden=!state.programs.some(p=>p.status==='current');$('#adapt').disabled=!state.configured||busy;
  renderPrograms();
}
function openDialog(content){$('#dialog-body').replaceChildren(content);if(!$('#dialog').open)$('#dialog').showModal();}
$('#close-dialog').onclick=()=>$('#dialog').close();
async function generate(changes=''){if(busy)return;busy=true;$('#generate').disabled=true;$('#adapt').disabled=true;status('#program-status','Подготавливаем программу. Обычно это занимает около минуты…');
 try{const response=await api('generate',{changes});const r=response.result;status('#program-status',[r.message,...r.questions,...(r.changes||[])].join('\n'));await refresh();}catch(e){status('#program-status',e.message,true);}finally{busy=false;$('#generate').disabled=!state.profile||!state.configured;$('#adapt').disabled=!state.configured;}}
$('#generate').onclick=()=>generate();$('#adapt').onclick=()=>{const changes=$('#changes').value.trim();if(!changes)return status('#program-status','Опишите, что требуется изменить.',true);generate(changes);};
function renderPrograms(){const list=$('#program-list');if(!state.programs.length)return;list.replaceChildren();
 for(const record of state.programs){const p=record.body.program;const card=el('article',undefined,'program-record '+record.status);const kind={current:'Текущая программа',draft:'Предложение — требуется подтверждение',archived:'Предыдущая версия'}[record.status];card.append(el('div',`${kind} · версия ${record.version}`,'program-meta'),el('h3',p.title),el('p',p.rationale));
  if(record.body.changes?.length)card.append(el('p',record.body.changes.join('\n'),'soft-note'));
  if(record.status==='draft')card.append(button('Принять эту версию ✓',async()=>{try{await api(`programs/${record.id}/confirm`,{});await refresh();status('#program-status','Новая версия принята. Предыдущая сохранена.');}catch(e){status('#program-status',e.message,true);}}));
  p.workouts.forEach((w,wi)=>{const section=el('section',undefined,'workout');section.append(el('h4',`День ${w.day} · ${w.name}`),el('span',`≈ ${w.duration_minutes} минут`,'pill'),el('p',`Разминка · ${w.warmup_minutes} мин\n${w.warmup}`,'phase'));
   w.exercises.forEach((e,ei)=>{const row=el('div',undefined,'exercise'),copy=el('div');copy.append(el('h5',`${ei+1}. ${e.name}`),el('p',`${e.sets} подхода × ${e.repetitions||e.seconds+' сек'} · отдых ${e.rest_seconds} сек`),el('p',e.technique));row.append(copy,button('Как выполнять ↗',()=>explain(record.id,wi,ei),'text-button'));section.append(row);});
   section.append(el('p',`Завершение · ${w.cooldown_minutes} мин\n${w.cooldown}`,'phase'),button('Оставить отзыв о занятии',()=>feedbackDialog(record,wi),'text-button'));card.append(section);
  });card.append(el('p','Восстановление: '+p.recovery),el('p','Нагрузка: '+p.load_guidance),el('p','Дальнейшая адаптация: '+p.progression));list.append(card);
 }
}
async function explain(pid,wi,ei){const box=el('div');box.append(el('h3','Техника упражнения'),el('p','Подготавливаем объяснение…'));openDialog(box);try{const r=await api('explain',{program_id:pid,workout_index:wi,exercise_index:ei});box.replaceChildren(el('h3','Техника упражнения'),el('p',r.message));for(const q of r.questions)box.append(el('p',q));if(r.explanation){const labels={purpose:'Назначение',equipment:'Оборудование',starting_position:'Исходное положение',steps:'Выполнение',breathing:'Дыхание',mistakes:'Частые ошибки',easier_option:'Упрощение',stop_when:'Когда прекратить'};for(const[key,label]of Object.entries(labels)){box.append(el('h4',label));const value=r.explanation[key];if(Array.isArray(value)){const ul=el('ul');value.forEach(t=>ul.append(el('li',t)));box.append(ul);}else box.append(el('p',value));}}}catch(e){box.append(el('p',e.message,'status error'));}}
function feedbackDialog(record,wi){const box=el('div'),f=el('form');box.append(el('h3','Как прошла тренировка?'),el('p',record.body.program.workouts[wi].name));
 const fields=[['completion_status','Выполнение','select',[['completed','Полностью'],['partial','Частично'],['skipped','Пропущена']]],['actual_duration_minutes','Продолжительность, минуты','number'],['perceived_difficulty','Сложность от 1 до 10','number'],['pain_reported','Была ли боль?','select',[['','Предпочитаю не отвечать'],['false','Нет'],['true','Да']]],['comment','Комментарий','textarea']];
 for(const[name,label,type,options]of fields){const id='feedback-'+name,l=el('label',label);l.htmlFor=id;const input=el(type==='select'?'select':type==='textarea'?'textarea':'input');input.id=id;input.name=name;if(options)for(const[v,t]of options){const o=el('option',t);o.value=v;input.append(o);}if(type==='number'){input.type='number';input.min='1';input.max=name==='perceived_difficulty'?'10':'360';input.required=true;}if(type==='textarea')input.maxLength=1500;f.append(l,input);}
 const completed=f.elements.namedItem('completion_status');completed.onchange=()=>{for(const name of ['actual_duration_minutes','perceived_difficulty']){const input=f.elements.namedItem(name);input.required=completed.value!=='skipped';input.disabled=completed.value==='skipped';}};
 const submit=el('button','Сохранить отзыв','button');submit.type='submit';const message=el('p');message.setAttribute('role','status');f.append(submit,message);box.append(f);openDialog(box);
 f.onsubmit=async event=>{event.preventDefault();submit.disabled=true;const data=new FormData(f);const number=name=>data.get(name)?Number(data.get(name)):null;try{const pain=data.get('pain_reported');await api('feedback',{program_id:record.id,workout_index:wi,completion_status:data.get('completion_status'),actual_duration_minutes:number('actual_duration_minutes'),perceived_difficulty:number('perceived_difficulty'),pain_reported:pain===''?null:pain==='true',comment:data.get('comment')});message.textContent='Отзыв сохранён. Программа автоматически не меняется.'+(pain==='true'?' Не продолжайте болезненное упражнение. Обратитесь к специалисту для оценки причины и нагрузки.':'');message.className='feedback-success';}catch(e){message.textContent=e.message;}finally{submit.disabled=false;}};
}
showStep();refresh(true).catch(e=>{status('#form-status','Не удалось связаться с сервером: '+e.message,true);$('#connection').textContent='Подключение к серверу недоступно. Обновите страницу.';});
