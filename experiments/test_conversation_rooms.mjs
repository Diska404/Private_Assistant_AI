import test from 'node:test';
import assert from 'node:assert/strict';
import {RoomUI} from '../app/leva_web/rooms.js';

function fixture(){
 const nodes=new Map(),ids=['room-form','room-model','room-gpu','attach-message','clear-attachments','message-files','message-attachments','send','message','workspace-label','workspace-description','workspace-heading','room-heading','room-eyebrow','handoff-accept','handoff-panel','handoff-detail'];
 for(const id of ids)nodes.set(id,{dataset:{},value:'',hidden:false,textContent:'',elements:[],replaceChildren(...v){this.options=v},click(){}});
 const buttons=['assistant','chat','secret'].map(workspace=>({dataset:{workspace},classList:{toggle(){}},setAttribute(){}}));
 globalThis.document={getElementById:id=>nodes.get(id),querySelectorAll:()=>buttons,body:{dataset:{}}};globalThis.Option=class{constructor(label,value){this.label=label;this.value=value}};
 const sent=[],config={model:'auto',gpu:'gpu5070',models:{auto:'Otomatis',saluki:'Saluki 27B'},gpus:{gpu5070:'RTX 5070',dual:'Dual GPU'}};
 const ui=new RoomUI({api:async()=>({id:'owned-file',name:'notes.txt'}),command:async(...v)=>sent.push(v),notice:()=>{}});
 return{nodes,buttons,ui,sent,state:{workspace:'chat',rooms:{chat:config,secret:{...config,model:'qwen4b',models:{qwen4b:'4B (Direkomendasikan)',saluki:'27B (Tidak Direkomendasikan)'}}}}};
}
test('chat binds workspace and attachment IDs before enqueue',()=>{
 const {ui,state}=fixture();ui.update(state);ui.files=[{id:'owned-file',name:'notes.txt'}];
 assert.deepEqual(ui.chatValue('analisis'),{workspace:'chat',text:'analisis',attachments:['owned-file']});
 ui.update({...state,workspace:'secret'});assert.equal(ui.files.length,0);assert.equal(ui.chatValue('curhat').workspace,'secret');
});
test('native/phone state disables workspace changes during answer and translation',()=>{
 const {ui,state,buttons,nodes}=fixture();ui.update({...state,busy:true});assert.ok(buttons.every(b=>b.disabled));
 ui.update({...state,busy:false,translation_pending:true});assert.ok(buttons.every(b=>b.disabled));
 ui.update({...state,busy:false});assert.ok(buttons.every(b=>!b.disabled));assert.equal(nodes.get('room-form').hidden,false);
});
test('handoff asks explicit host command rather than executing a chat task',async()=>{
 const {ui,state,nodes,sent}=fixture();ui.update({...state,workspace:'secret',handoff:{source:'secret',target:'assistant',goal:'buat website'}});
 assert.equal(nodes.get('handoff-panel').hidden,false);assert.equal(sent.length,0);
 await nodes.get('handoff-accept').onclick();assert.deepEqual(sent,[['handoff','assistant']]);
});
test('manual model selection is sent with its own workspace and GPU',async()=>{
 const {ui,state,nodes,sent}=fixture();ui.update(state);nodes.get('room-model').value='saluki';nodes.get('room-gpu').value='dual';
 await nodes.get('room-form').onsubmit({preventDefault(){}});assert.deepEqual(sent,[['room_settings',{workspace:'chat',model:'saluki',gpu:'dual'}]]);
});
