// A delta is valid only for a retained server cursor. Resets arrive as replace.
export function mergeMessages(previous,snapshot){
 if(snapshot.messages_mode!=='append')return snapshot.messages||[];
 const rows=new Map(previous.filter(row=>row.id>=snapshot.messages_first_id).map(row=>[row.id,row]));
 for(const row of snapshot.messages||[])rows.set(row.id,row);
 return [...rows.values()].sort((a,b)=>a.id-b.id);
}
