// Apply the source expression recipes without changing source artwork or compiled moc3.
const PROFILES={neutral:'Idle',laugh:'Happy',confused:'Helpless',embarrassed:'Helpless',attentive:'Idle',excited:'Happy',soft_smile:'Tender',happy:'Happy',gentle:'Tender',grateful:'Tender',comfort:'Tender',relieved:'Tender',shy:'Helpless',apologetic:'Helpless',sad:'Cry',concerned:'Solemn',disappointed:'Helpless',angry:'Angry',surprised:'Surprised',curious:'Suspect',thinking:'Solemn',confident:'Determined',proud:'Determined',playful:'Ridicule',teasing:'Smirk',sleepy:'Idle',listening:'Idle',speaking:'Tender',interrupted:'Surprised'};
export function sourceExpressionName(profile){return PROFILES[profile]||'Idle'}
export class SourceExpressionLayer{
 constructor(recipes=[]){this.recipes=new Map();this.current=new Map();for(const row of recipes){if(!row||typeof row.name!=='string'||!Array.isArray(row.parameters)||row.parameters.length>500)throw new Error('invalid_source_expression');for(const p of row.parameters)if(typeof p.Id!=='string'||!Number.isFinite(p.Value)||!['Add','Multiply','Overwrite'].includes(p.Blend))throw new Error('invalid_source_expression');this.recipes.set(row.name,row.parameters)}}
 apply(profile,dt,model,ids){const key=sourceExpressionName(profile);const recipe=this.recipes.get(key)||this.recipes.get('Idle')||[],alpha=1-Math.exp(-Math.max(0,Math.min(.1,dt))*22);this.active=key;
  for(const p of recipe){const index=ids.get(p.Id);if(index===undefined)continue;const base=model.getParameterValueByIndex(index),target=p.Blend==='Multiply'?base*p.Value:p.Blend==='Overwrite'?p.Value:base+p.Value,prior=this.current.get(p.Id)??base,value=prior+(target-prior)*alpha;this.current.set(p.Id,value);model.setParameterValueByIndex(index,value)}
 }
 reset(){this.current.clear()}
}
