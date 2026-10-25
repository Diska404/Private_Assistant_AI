"""Authorized real VTS handshake. Token stays DPAPI-encrypted and is never printed."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'app'),str(ROOT/'experiments')]
OUT=Path(r'D:\AI\AI Lokal Asisten\Leva\verification\leva-premium-avatar-r2\reports')
from vts_bridge import VTSClient
def main():
 client=VTSClient()
 try:
  state=client.connect();print(json.dumps({'api_active':state.get('active'),'version':state.get('vTubeStudioVersion'),'waiting_for_user_plugin_consent':True}),flush=True)
  model=client.authenticate(authorize='--authorize' in sys.argv)
  parameters=client.request('InputParameterListRequest');live=client.request('Live2DParameterListRequest')
  report={'api_state':state,'authentication_successful':True,'model':model,'input_parameters':parameters,'live2d_parameters':live,'token_storage':'Windows DPAPI local credential file; token not included','native_web_renderer':False,'model_is_leva':False}
  (OUT/'vts-handshake-private.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
  print(json.dumps({'authenticated':True,'model_loaded':model.get('modelLoaded'),'model_name':model.get('modelName'),'model_is_leva':False,'token_in_report':False}),flush=True)
 finally:client.close()
if __name__=='__main__':main()
