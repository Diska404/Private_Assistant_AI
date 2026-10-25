"""Build the user's already downloaded SDK locally; no vendor files enter source export."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path(r'D:\AI\AI Lokal Asisten\Github\Live2D-SDK')
SDK=BASE/'CubismSdkForWeb-5-r.4'
DEPS=Path(r'D:\AI\AI Lokal Asisten\Github\Leva-Avatar-Renderer')
ROOT=Path(__file__).resolve().parents[1]

def main():
    framework=SDK/'Framework/src'
    entry=BASE/'leva-cubism-entry.ts'
    def imp(name,relative):return 'import {'+name+'} from '+json.dumps((framework/relative).as_posix())+';\n'
    source=imp('CubismFramework','live2dcubismframework')+imp('CubismUserModel','model/cubismusermodel')+imp('CubismMatrix44','math/cubismmatrix44')
    source+='''export {CubismFramework,CubismMatrix44};
export class LevaCubismModel extends CubismUserModel {
  constructor(){super();}
  physicsStep(dt){this._physics?.evaluate(this._model,dt);}
  poseStep(dt){this._pose?.updateParameters(this._model,dt);}
  resetPhysics(){this._physics?.stabilization(this._model);}
}
'''
    entry.write_text(source,encoding='utf8');target=BASE/'leva-cubism-framework.js'
    subprocess.run([str(DEPS/'node_modules/@esbuild/win32-x64/esbuild.exe'),str(entry),'--bundle','--format=esm','--minify','--legal-comments=eof','--outfile='+str(target)],check=True,timeout=30)
    files={}
    def add(key,path):files[key]={'path':path.relative_to(BASE).as_posix(),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    add('runtime/core.js',SDK/'Core/live2dcubismcore.min.js');add('runtime/framework.js',target)
    sample=SDK/'Samples/Resources/Hiyori'
    # Explicit sample resources only: no arbitrary filesystem endpoint or code from a model.
    for path in sample.rglob('*'):
        if path.is_file() and path.suffix in ('.json','.png','.moc3'):add('model/'+path.relative_to(sample).as_posix(),path)
    row={'sdk_version':'Cubism SDK for Web 5 R4','model':'Hiyori · official SDK sample','model_is_leva':False,'files':files,'license_files':['CubismSdkForWeb-5-r.4/LICENSE.md','CubismSdkForWeb-5-r.4/Core/LICENSE.md'],'source_zip_sha256':hashlib.sha256((BASE/'CubismSdkForWeb-5-r.4.zip').read_bytes()).hexdigest()}
    (BASE/'leva-runtime-manifest.json').write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'prepared':True,'resources':len(files),'model_is_leva':False,'sdk_version':row['sdk_version']}))
if __name__=='__main__':main()
