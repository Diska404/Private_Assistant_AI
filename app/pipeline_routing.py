"""One routing definition for widgets, persistence and inference payloads."""
FAMILIES = ('local', 'cascade', 'hybrid', 'router')
PREFIX = {'local':'','cascade':'Google → 9Router → ','hybrid':'Google → ','router':'9Router → '}
SINGLE_CHOICES = ('Tanpa AI', *(PREFIX[f]+g for f in FAMILIES for g in ('RTX 4050','RTX 5070')))
DUAL_CHOICES = ('Tanpa AI', *(PREFIX[f]+'Dual GPU' for f in FAMILIES))
LEGACY = {'Hybrid · Google → Lokal':'Google → RTX 4050', 'Lokal · RTX 4050':'RTX 4050',
          'Perintah saja · Tanpa AI':'Tanpa AI', 'Lokal · Saluki RTX 5070 · uji':'RTX 5070',
          '9Router → Lokal':'9Router → RTX 4050', 'Hybrid · Google → 9Router → Lokal':'Google → 9Router → RTX 4050'}

def route_spec(label,dual=False):
    label=LEGACY.get(label,label)
    if label not in SINGLE_CHOICES+DUAL_CHOICES:raise ValueError('invalid_pipeline_route')
    if label=='Tanpa AI':return {'mode':'commands','gpu':'none','local_mode':None,'label':label,'providers':[]}
    mode='cascade' if label.startswith(PREFIX['cascade']) else 'hybrid' if label.startswith('Google') else 'router' if label.startswith('9Router') else 'local'
    gpu='dual' if dual or label.endswith('Dual GPU') else 'rtx5070' if label.endswith('RTX 5070') else 'rtx4050'
    return {'mode':mode,'gpu':gpu,'local_mode':{'rtx4050':'gpu4050','rtx5070':'gpu5070','dual':'dual'}[gpu],
            'label':PREFIX[mode]+{'rtx4050':'RTX 4050','rtx5070':'RTX 5070','dual':'Dual GPU'}[gpu],
            'providers':{'local':['local'],'hybrid':['google','local'],'cascade':['google','9router','local'],'router':['9router','local']}[mode]}

def visible_route(label,dual,last_single='rtx4050'):
    spec=route_spec(label,dual)
    if spec['mode']=='commands':return 'Tanpa AI'
    if dual:return PREFIX[spec['mode']]+'Dual GPU'
    gpu=spec['gpu'] if spec['gpu']!='dual' else last_single
    return PREFIX[spec['mode']]+('RTX 5070' if gpu=='rtx5070' else 'RTX 4050')

# The conversational speech front-end is local; agent routing stays independent.
VOICE_SINGLE=('Tanpa AI','RTX 4050','RTX 5070')
VOICE_DUAL=('Tanpa AI','Dual GPU')
def local_voice_route(label,dual=False):
    spec=route_spec(label,dual)
    return 'Tanpa AI' if spec['gpu']=='none' else {'rtx4050':'RTX 4050','rtx5070':'RTX 5070','dual':'Dual GPU'}[spec['gpu']]
