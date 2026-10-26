// Developer-only numeric QA; absent channels are never invented by the UI.
export class RigOverrides{
 constructor(schema=[]){this.schema=new Map(schema.map(p=>[p.id,p]));this.values=new Map();this.enabled=false}
 set(id,value){const p=this.schema.get(id);if(!p||!Number.isFinite(value))throw new Error('invalid_rig_parameter');this.values.set(id,Math.max(p.min,Math.min(p.max,value)))}
 clear(){this.values.clear()}
 apply(write,{physics=false,audioPlaying=false}={}){if(!this.enabled)return;for(const [id,value]of this.values){if(/^ParamMouth/.test(id)&&audioPlaying)continue;const secondary=/^Param(Hair|Jacket|Ribbon)/.test(id);if(secondary===physics)write(id,value)}}
}
export class Live2DRigLab{
 constructor(){
  const el=this.element=document.createElement('details');el.className='live2d-rig-lab';el.hidden=true;
  el.innerHTML='<summary>Developer · parameter & mesh Live2D</summary><p>QA manual hanya pada perangkat ini. Slider mengikuti parameter model yang dimuat; layer terpisah belum berarti rig lengan selesai. Gerak bibir audio aktif tetap mendapat prioritas.</p><div class="rig-toolbar"><label><input type="checkbox" data-rig="enabled">Override parameter QA</label><label><input type="checkbox" data-rig="wire">Garis ArtMesh</label><button type="button" data-rig="reset">Reset override</button><input type="search" aria-label="Filter parameter rig" placeholder="Cari Angle, Eye, Mouth, Hair…"></div><label>Mesh untuk diperiksa <select aria-label="ArtMesh QA"></select></label><output aria-live="polite"></output><div class="rig-parameters"></div>';
  this.query=s=>el.querySelector(s);this.query('[data-rig=enabled]').onchange=e=>{if(this.provider)this.provider.qa.enabled=e.target.checked;this.describe()};
  this.query('[data-rig=wire]').onchange=e=>this.provider?.setWireframe(e.target.checked);
  this.query('[data-rig=reset]').onclick=()=>{this.provider?.qa.clear();for(const input of el.querySelectorAll('input[type=range]')){input.value=input.dataset.default;input.nextElementSibling.value=input.value}this.describe()};
  this.query('input[type=search]').oninput=e=>{const text=e.target.value.toLowerCase();for(const row of this.query('.rig-parameters').children)row.hidden=!row.textContent.toLowerCase().includes(text)};
  this.query('select').onchange=e=>{if(this.provider)this.provider.qaMesh=e.target.value};
 }
 bind(provider){
  this.provider?.setWireframe(false);this.provider=provider;this.query('input[type=search]').value='';this.element.hidden=!provider;this.query('.rig-parameters').replaceChildren();this.query('select').replaceChildren();
  for(const input of this.element.querySelectorAll('input[type=checkbox]'))input.checked=false;
  if(!provider)return;provider.qa.enabled=false;this.query('select').append(new Option('Semua ArtMesh',''));
  for(let i=0;i<provider.model.getDrawableCount();i++){const id=provider.model.getDrawableId(i).getString().s;this.query('select').append(new Option(id,id))}
  for(const p of provider.parameterSchema()){
   const row=document.createElement('label');row.className='rig-parameter';const name=document.createElement('span');name.textContent=p.id;const input=document.createElement('input');input.type='range';input.min=p.min;input.max=p.max;input.step=(p.max-p.min)/200||.001;input.value=p.default;input.dataset.default=p.default;input.setAttribute('aria-label','QA '+p.id);const value=document.createElement('output');value.value=String(p.default);input.oninput=()=>{provider.qa.set(p.id,Number(input.value));value.value=Number(input.value).toFixed(3);this.describe()};row.append(name,input,value);this.query('.rig-parameters').append(row)
  }this.describe();
 }
 describe(){this.query('output').textContent=this.provider?`${this.provider.ids.size} parameter nyata · ${this.provider.model.getDrawableCount()} ArtMesh · override ${this.provider.qa.enabled?'AKTIF':'off'} · ${this.provider.qa.values.size} kanal dipilih`:'Belum ada model native'}
 dispose(){this.bind(null);this.element.remove()}
}
