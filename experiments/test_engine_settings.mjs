import test from 'node:test';
import assert from 'node:assert/strict';
import {EngineSettings} from '../app/leva_web/engines.js';

function fixture(send=async()=>true){
 const elements=new Map(),ids=['pipeline-settings','engine-status','engine-save','engine-form','engine-summary','engine-asr-model','engine-asr-gpu','engine-asr-language','engine-agent-model','engine-agent-route'];
 for(const id of ids)elements.set(id,{dataset:{},value:'',disabled:false,hidden:false,textContent:'',replaceChildren(...items){this.options=items}});
 globalThis.document={getElementById:id=>elements.get(id)};globalThis.Option=class{constructor(label,value){this.label=label;this.value=value}};
 const values={asr_model:'qwen_asr_06b',asr_gpu:'rtx5070',asr_language:'id',agent_local_model:'saluki',agent_provider:'Dual GPU'};
 const choices=Object.fromEntries(Object.entries(values).map(([k,v])=>[k,{[v]:v}]));choices.asr_gpu.rtx4050='RTX 4050';choices.agent_provider['RTX 5070']='RTX 5070';
 const snapshot={state:{busy:false,pipeline:{values,choices,summary:'ASR 5070 · agent Dual'}},commands:[]};
 const ui=new EngineSettings(elements.get('pipeline-settings'),send);ui.update(snapshot);
 return{elements,ui,snapshot,event:{preventDefault(){}}};
}

test('initial selection follows host; unsaved GPU edits survive polling',()=>{
 const {elements,ui,snapshot}=fixture();const field=elements.get('engine-asr-gpu');assert.equal(field.value,'rtx5070');
 field.value='rtx4050';field.onchange();ui.update(snapshot);assert.equal(field.value,'rtx4050');assert.equal(ui.dirty,true);
});

test('save sends separate voice/agent values and waits for host receipt',async()=>{
 const sent=[];const {elements,ui,snapshot,event}=fixture(async(...args)=>{sent.push(args);return true});
 elements.get('engine-asr-gpu').value='rtx4050';elements.get('engine-asr-gpu').onchange();
 await elements.get('engine-form').onsubmit(event);
 assert.equal(sent[0][0],'pipeline_settings');assert.equal(sent[0][1].asr_gpu,'rtx4050');assert.equal(sent[0][1].agent_provider,'Dual GPU');
 assert.equal(elements.get('engine-save').disabled,true);assert.equal(ui.dirty,true);
 snapshot.commands=[{id:sent[0][2],status:'dispatched'}];snapshot.state.pipeline.values.asr_gpu='rtx4050';ui.update(snapshot);
 assert.equal(ui.pending,null);assert.equal(ui.dirty,false);assert.match(elements.get('engine-status').textContent,/Tersimpan/);
});

test('rejected settings preserve the draft and show the host error',async()=>{
 const {elements,ui,snapshot,event}=fixture();elements.get('engine-agent-route').value='RTX 5070';elements.get('engine-agent-route').onchange();
 await elements.get('engine-form').onsubmit(event);snapshot.commands=[{id:ui.pending,status:'failed',detail:'Tunggu transkrip HP selesai.'}];ui.update(snapshot);
 assert.equal(ui.dirty,true);assert.equal(elements.get('engine-agent-route').value,'RTX 5070');assert.match(elements.get('engine-status').textContent,/transkrip/);
});

test('pending save cannot be duplicated and missing pipeline stays hidden',async()=>{
 let release,calls=0;const {elements,ui,event}=fixture(()=>{calls++;return new Promise(resolve=>release=resolve)});
 const pending=elements.get('engine-form').onsubmit(event);await elements.get('engine-form').onsubmit(event);assert.equal(calls,1);release(true);await pending;
 ui.update({state:{}});assert.equal(elements.get('pipeline-settings').hidden,true);
});
