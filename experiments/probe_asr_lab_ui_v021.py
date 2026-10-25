"""Isolated headless Edge check of the local app; no personal profile or real mic."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT=Path('D:/AI/AI Lokal Asisten/Leva/verification/gpu-contract-v021');OUT.mkdir(parents=True,exist_ok=True)
proof={'microphone_opened':False,'real_audio_devices_opened':False,'errors':[]}
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True,args=['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream'])
    context=browser.new_context(viewport={'width':1500,'height':1050})
    page=context.new_page();page.on('pageerror',lambda error:proof['errors'].append(str(error)))
    page.goto('http://127.0.0.1:8771/',wait_until='networkidle')
    page.get_by_role('heading',name='Dengar. Ukur. Bandingkan.').wait_for()
    page.wait_for_function("() => document.querySelector('#prompt').options.length===13")
    page.locator('#prompt').select_option('comfy')
    assert 'jangan generate' in page.locator('#reference').input_value()
    proof['scenarios']=page.locator('#prompt option').count()
    proof['default_gpu']=page.locator('#gpu').input_value()
    page.locator('#gpu').select_option('dual')
    proof['dual_option']=page.locator('#gpu').input_value()=='dual'
    proof['record_disabled_before_permission']=page.locator('#record').is_disabled()
    proof['no_horizontal_overflow']=page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#origin-filter').select_option('all')
    page.wait_for_timeout(250)
    rows=page.locator('tr[data-id]')
    if rows.count():
        rows.first.click();page.locator('#save-review').wait_for()
        proof['dual_replay_button']=page.locator('#replay-dual').count()==1
        proof['gpu_evidence_rendered']='module' in page.locator('#detail').inner_text() or 'first_module_forward_cuda_ms' in page.locator('#detail').inner_text()
        proof['result_detail_rendered']=True
        page.get_by_text('Resource, waktu dan metadata lengkap',exact=True).click()
        proof['resource_samples_in_view']=page.locator('pre').last.inner_text().count('sample_cost_ms')
    page.screenshot(path=str(OUT/'desktop.png'),full_page=True)
    page.set_viewport_size({'width':420,'height':900});page.wait_for_timeout(100)
    proof['mobile_no_horizontal_overflow']=page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(OUT/'mobile.png'),full_page=True)
    page.locator('#enable').click()
    page.wait_for_function("() => !document.querySelector('#record').disabled",timeout=12000)
    page.locator('#record').click();page.wait_for_timeout(650);page.locator('#stop').click()
    page.wait_for_function("() => document.querySelector('#preview').src.startsWith('blob:')")
    proof['fake_browser_recording']=page.evaluate("""async () => {const b=await wav.arrayBuffer();const v=new DataView(b);return {bytes:b.byteLength,sample_rate:v.getUint32(24,true),channels:v.getUint16(22,true),pcm_bits:v.getUint16(34,true),device:document.querySelector('#mic-status').textContent};}""")
    assert proof['fake_browser_recording']['bytes']>44
    page.locator('#disable').click();proof['fake_stream_stopped']=page.locator('#record').is_disabled()
    context.close();browser.close()
(OUT/'ui-proof.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
print(json.dumps(proof))
