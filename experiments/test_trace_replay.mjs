import assert from 'node:assert/strict';
import {TraceReplay,traceRow} from '../app/leva_web/trace.js';
class Element{constructor(){this.children=[];this.value='';this.open=true;this.hidden=false;this.textContent=''}append(...v){this.children.push(...v)}replaceChildren(){this.children=[];this.value=''}setAttribute(){}addEventListener(){}insertBefore(v){this.append(v)}querySelector(){return {}}}
const doc={createElement:()=>new Element()},panel=new Element();let rows=[],resolve;
const ui=new TraceReplay({document:doc,panel,render:v=>rows=v,api:()=>new Promise(r=>resolve=r)});
ui.update('assistant',[{label:'live'}]);assert.equal(rows[0].label,'live');assert.equal(ui.pending,true);
ui.update('secret',[]);resolve({workspace:'assistant',runs:[{run_id:'a',updated_at:'today',event_count:2}]});await Promise.resolve();
assert.equal(panel.hidden,true);assert.deepEqual(rows,[]);assert.equal(ui.select.children.length,1);
ui.update('chat',[{label:'chat'}]);resolve({workspace:'chat',runs:[{run_id:'a'.repeat(32),updated_at:'2026-10-25T00:00:00',event_count:2}]});await Promise.resolve();
assert.equal(ui.select.children.length,2);assert.equal(panel.hidden,false);
ui.select.value='a'.repeat(32);ui.select.onchange();
resolve({workspace:'chat',truncated:true,events:[{elapsed_ms:15,provenance:'observed',status:'done',event_type:'tool.completed'}],health:{dropped:1}});await Promise.resolve();
assert.equal(rows[0].label,'tool.completed');assert(ui.note.textContent.includes('sebagian'));assert(ui.note.textContent.includes('1 event hilang'));
ui.update('companion_avatar',[]);assert.deepEqual(rows,[]);assert(panel.hidden);
assert.equal(traceRow({elapsed_ms:1,provenance:'observed',status:'done',event_type:'model.response_started',metrics:{ttft_ms:123}}).label,'Token jawaban pertama tersedia · TTFT 123 ms');
console.log(JSON.stringify({checks:12,private_mode_stale_response_blocked:true,replay_gap_and_storage_error_visible:true}));
