"""Evaluate recovered attempts and observed UI input without discarding evidence."""


def dispatch_verified(receipts,index):
    row=receipts[index];name=row.get('name');args=row.get('args',{})
    later=receipts[index+1:]
    if name=='browser_action':
        return any(r.get('name')=='browser_action' and r.get('args',{}).get('action')=='inspect' and r.get('args',{}).get('tab')==args.get('tab') and r['result'].get('status')=='done' for r in later)
    if name=='computer_action':
        return any(r.get('name')=='computer_action' and r.get('args',{}).get('action')=='inspect' and r.get('args',{}).get('window')==args.get('window') and r['result'].get('status')=='done' for r in later)
    if name=='screen_action':return any(r.get('name')=='describe_screen' and r['result'].get('status')=='done' for r in later)
    return False


def unresolved_receipts(receipts):
    unresolved=[]
    for index,row in enumerate(receipts):
        status=row['result'].get('status')
        if status=='done':continue
        if row.get('name')=='image_action' and status=='running':
            args=row.get('args',{});ident=row['result'].get('job_id');engine=args.get('engine')
            if args.get('action') in ('start','status') and any(r.get('name')=='image_action' and r.get('args',{}).get('engine')==engine and r.get('args',{}).get('action')=='status' and r['result'].get('status')=='done' for r in receipts[index+1:]):continue
            if ident and any(r.get('name')=='image_action' and r.get('args',{}).get('engine')==engine and r.get('args',{}).get('job_id')==ident and r['result'].get('status') in ('done','failed') for r in receipts[index+1:]):continue
        if row.get('name')=='comfy_action' and status=='running':
            action=row.get('args',{}).get('action');ident=row['result'].get('workflow_id') or row.get('args',{}).get('workflow_id')
            if action in ('start','status') and any(r.get('name')=='comfy_action' and r.get('args',{}).get('action')=='status' and r['result'].get('status')=='done' for r in receipts[index+1:]):continue
            if ident and any(r.get('name')=='comfy_action' and r.get('args',{}).get('action')=='poll' and r.get('args',{}).get('workflow_id')==ident and r['result'].get('status') in ('done','failed','unverified') for r in receipts[index+1:]):continue
        if row.get('name')=='terminal' and status=='running':
            ident=row['result'].get('process_id') or row.get('args',{}).get('process_id')
            if any(r.get('name')=='terminal' and r.get('args',{}).get('process_id')==ident and r['result'].get('status') in ('done','failed','cancelled') for r in receipts[index+1:]):continue
        if status=='dispatched' and dispatch_verified(receipts,index):continue
        if row['result'].get('retryable'):
            recovered=False
            for after in range(index+1,len(receipts)):
                later=receipts[after]
                if later.get('name')!=row.get('name') or later.get('args',{}).get('action')!=row.get('args',{}).get('action'):continue
                if row.get('name')=='terminal' and row['result'].get('command_id')!=later['result'].get('command_id'):continue
                if row.get('name')=='file_action' and row.get('args',{}).get('path')!=later.get('args',{}).get('path'):continue
                if row.get('name')=='browser_action' and row.get('args',{}).get('tab')!=later.get('args',{}).get('tab'):continue
                if row.get('name')=='computer_action' and row.get('args',{}).get('window')!=later.get('args',{}).get('window'):continue
                if row.get('name')=='comfy_action' and (row.get('args',{}).get('workflow_id')!=later.get('args',{}).get('workflow_id') or row.get('args',{}).get('checkpoint')!=later.get('args',{}).get('checkpoint')):continue
                if later['result'].get('status')=='done' or later['result'].get('status')=='dispatched' and dispatch_verified(receipts,after):recovered=True;break
            if recovered:continue
        unresolved.append(row)
    return unresolved
