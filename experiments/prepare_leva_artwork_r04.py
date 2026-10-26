"""R04-A: reversible, manually traced artwork partition; no generative fill.

Extracts visible parts from the existing R03 base sprite into editable OpenRaster
layers and a new packed atlas. Hidden surfaces remain explicitly unpainted.
"""
import argparse,copy,hashlib,io,json,math,struct,zipfile,zlib
from pathlib import Path
from xml.etree.ElementTree import Element,SubElement,tostring
import msgpack
from PIL import Image,ImageDraw,ImageChops,ImageFilter

# Coordinates refer to the 1182x1686 base sprite, not screen coordinates.
# R/L refer to the character. The bionic hand is character-right, viewer-left.
TRACES=[
 ('right_hand','BODY/Right hand · visible fist',[(0,710),(110,710),(145,810),(125,925),(96,980),(45,965),(0,915)]),
 ('right_forearm','BODY/Right forearm · bionic',[(0,925),(90,925),(147,986),(220,1038),(315,1098),(352,1160),(333,1297),(275,1280),(225,1225),(90,1100),(10,1005)]),
 ('right_upper_arm','BODY/Right upper arm · partial sleeve',[(405,610),(426,640),(402,740),(392,880),(382,1030),(366,1170),(335,1310),(278,1280),(292,1175),(309,1105),(315,932),(349,806),(370,690),(393,626)]),
 ('left_forearm','BODY/Left forearm · cropped; hand absent',[(997,1335),(1095,1335),(1160,1510),(1182,1540),(1182,1686),(1090,1686),(1067,1560),(1030,1435)]),
 ('left_upper_arm','BODY/Left upper arm and cuff',[(919,580),(980,590),(1022,665),(1036,888),(1048,1020),(1074,1085),(1100,1255),(1110,1360),(1056,1400),(1000,1372),(942,1288),(916,1186),(858,1085),(851,973),(856,864),(867,750),(886,663)]),
 ('ribbon','HAIR/Hair ribbon · visible only',[(726,0),(825,0),(850,78),(852,142),(828,239),(790,200),(772,118),(744,68)]),
 ('back_hair_right','HAIR/Back hair · visible silhouette',[(786,65),(880,110),(925,247),(1012,338),(1102,393),(1037,407),(1098,472),(1035,489),(1130,552),(1051,541),(1090,631),(1048,619),(1120,733),(1065,716),(1150,788),(1068,760),(1040,866),(1012,830),(1000,680),(969,590),(908,566),(857,543),(828,474),(823,320)]),
 ('back_hair_left','HAIR/Side hair · visible left silhouette',[(447,336),(506,384),(559,486),(538,562),(466,594),(414,615),(432,532),(424,452)]),
 ('face_base','HEAD/Face base · nose; no corrective side art',[(484,180),(555,203),(598,177),(662,162),(706,189),(765,208),(787,290),(801,336),(773,365),(754,433),(696,488),(654,505),(602,479),(555,434),(524,387),(505,323),(481,278)]),
 ('neck','HEAD/Neck · visible only',[(659,475),(731,441),(757,470),(750,504),(723,540),(660,543),(614,516)]),
 ('collar','COSTUME/Collar and tie · partial',[(532,535),(609,511),(652,531),(748,498),(785,557),(749,672),(702,696),(681,769),(624,774),(580,715),(550,692),(520,626)]),
]

def binary(values):return struct.pack('<'+'f'*len(values),*values)
def rgba_bytes(im):b=io.BytesIO();im.save(b,format='PNG');return b.getvalue()
def read_aom(path):
 b=path.read_bytes();magic,v,flags,n=struct.unpack('<4sHHI',b[:12]);assert (magic,v,flags)==(b'AOMX',1,1)
 raw=zlib.decompress(b[12:],-15);assert len(raw)==n
 return msgpack.unpackb(raw,raw=False),hashlib.sha256(b).hexdigest()
def write_aom(doc,path):
 raw=msgpack.packb(doc,use_bin_type=True);c=zlib.compressobj(6,zlib.DEFLATED,-15)
 path.write_bytes(struct.pack('<4sHHI',b'AOMX',1,1,len(raw))+c.compress(raw)+c.flush())

def build(source,out):
 doc,source_hash=read_aom(source);out.mkdir(parents=True,exist_ok=False)
 (out/'layers').mkdir();mesh=doc['model']['art_meshes'][33]
 uv=struct.unpack('<'+'f'*(len(mesh['uvs'])//4),mesh['uvs']);pos=struct.unpack('<'+'f'*(len(mesh['positions'])//4),mesh['positions'])
 u0,u1=min(uv[::2]),max(uv[::2]);v0,v1=min(uv[1::2]),max(uv[1::2]);px0,px1=min(pos[::2]),max(pos[::2]);py0,py1=min(pos[1::2]),max(pos[1::2])
 atlas=Image.open(io.BytesIO(doc['textures'][0])).convert('RGBA')
 # Source UV Y runs downward; preserve subpixel UV extents when remapping.
 box=(round(u0*atlas.width),round(v0*atlas.height),round(u1*atlas.width),round(v1*atlas.height));base=atlas.crop(box);assert base.size==(1182,1686),base.size
 width,height=base.size;remaining=Image.new('L',base.size,255);pieces=[];masks=[]
 for key,label,polygon in TRACES:
  mask=Image.new('L',base.size);ImageDraw.Draw(mask).polygon(polygon,fill=255);mask=ImageChops.multiply(mask,remaining);remaining=ImageChops.subtract(remaining,mask)
  layer=base.copy();layer.putalpha(ImageChops.multiply(base.getchannel('A'),mask));pieces.append((key,label,layer));masks.append((key,polygon))
 layer=base.copy();layer.putalpha(ImageChops.multiply(base.getchannel('A'),remaining));pieces.append(('torso_remainder','BODY/Torso and hair remainder · still fused',layer))
 # Add a two-pixel underlap only within fully opaque source pixels. This
 # prevents bilinear filtering opening seams, without inventing hidden surfaces.
 opaque=base.getchannel('A').point(lambda v:255 if v==255 else 0)
 for _,_,im in pieces:
  alpha=im.getchannel('A');im.putalpha(ImageChops.lighter(alpha,ImageChops.multiply(alpha.filter(ImageFilter.MaxFilter(5)),opaque)))
 # Layer composition still reproduces source pixels exactly.
 merged=Image.new('RGBA',base.size)
 for _,_,im in pieces:merged.alpha_composite(im)
 assert merged.getchannel('A').tobytes()==base.getchannel('A').tobytes()
 bbox=ImageChops.difference(merged,base).getbbox();assert bbox is None
 stack=Element('image',{'w':str(width),'h':str(height),'name':'Leva R04-A · visible artwork separation'});layers=SubElement(stack,'stack')
 inventory=[]
 with zipfile.ZipFile(out/'Leva_R04A_Visible_Layers.ora','w') as z:
  z.writestr('mimetype','image/openraster',compress_type=zipfile.ZIP_STORED)
  for key,label,im in reversed(pieces):
   filename=f'layers/{key}.png';raw=rgba_bytes(im);(out/filename).write_bytes(raw);z.writestr(filename,raw,compress_type=zipfile.ZIP_DEFLATED)
   SubElement(layers,'layer',{'name':label,'src':filename,'x':'0','y':'0','opacity':'1.0','visibility':'visible','composite-op':'svg:src-over'})
   alpha=im.getchannel('A');bounds=alpha.getbbox();inventory.append({'id':key,'label':label,'bounds':bounds,'visible_pixels':sum(alpha.histogram()[1:]),'hidden_surface_complete':False,'source':'R03 base ArtMesh 33; manually traced partition'})
  z.writestr('stack.xml',tostring(stack,encoding='utf8'));z.writestr('mergedimage.png',rgba_bytes(merged));thumb=merged.copy();thumb.thumbnail((256,256));z.writestr('Thumbnails/thumbnail.png',rgba_bytes(thumb))
 # Editable path masks with source bitmap embedded, avoiding brittle file URLs.
 import base64
 paths=''.join(f'<path id="{key}" d="M'+ ' L'.join(f'{x},{y}' for x,y in polygon)+' Z" fill="none" stroke="#57dce8" stroke-width="2"/>' for key,polygon in masks)
 (out/'layer-traces.svg').write_text(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><image width="{width}" height="{height}" xlink:href="data:image/png;base64,{base64.b64encode(rgba_bytes(base)).decode()}"/>{paths}</svg>',encoding='utf8')
 # Pack tight crops, with transparent padding; source atlas 0 remains byte-identical.
 packed=Image.new('RGBA',(2048,2048));placements={};free=[(0,0,2048,2048)]
 for key,label,im in sorted(pieces,key=lambda p:(p[2].getchannel('A').getbbox()[2]-p[2].getchannel('A').getbbox()[0])*(p[2].getchannel('A').getbbox()[3]-p[2].getchannel('A').getbbox()[1]),reverse=True):
  b=im.getchannel('A').getbbox();crop=im.crop(b);w,h=crop.size;pw,ph=w+8,h+8
  candidates=[(min(rw-pw,rh-ph),rw*rh-pw*ph,x,y) for x,y,rw,rh in free if pw<=rw and ph<=rh]
  if not candidates:raise ValueError('atlas overflow')
  _,_,x,y=min(candidates);splits=[]
  for fx,fy,fw,fh in free:
   if x>=fx+fw or x+pw<=fx or y>=fy+fh or y+ph<=fy:splits.append((fx,fy,fw,fh));continue
   if x>fx:splits.append((fx,fy,x-fx,fh))
   if x+pw<fx+fw:splits.append((x+pw,fy,fx+fw-x-pw,fh))
   if y>fy:splits.append((fx,fy,fw,y-fy))
   if y+ph<fy+fh:splits.append((fx,y+ph,fw,fy+fh-y-ph))
  free=[r for i,r in enumerate(splits) if not any(i!=j and r[0]>=q[0] and r[1]>=q[1] and r[0]+r[2]<=q[0]+q[2] and r[1]+r[3]<=q[1]+q[3] for j,q in enumerate(splits))]
  packed.paste(crop,(x+4,y+4));placements[key]=(b,x+4,y+4,w,h)
 packed.save(out/'layer-atlas.png');doc['textures'].append(rgba_bytes(packed))
 model=doc['model'];names=doc['display']['mesh_names'];indices=[]
 for key,label,im in pieces:
  b,ax,ay,w,h=placements[key];m=copy.deepcopy(mesh);m['id']='Leva_R04A_'+key;m['texture']=1;m['binding']={'axes':[]};m['opacities']=[1.];m['draw_orders']=[500.];m['masks']=[]
  cols=max(2,math.ceil(w/36));rows=max(2,math.ceil(h/36));positions=[];uvs=[];triangles=[]
  for row in range(rows+1):
   for col in range(cols+1):
    sx=b[0]+w*col/cols;sy=b[1]+h*row/rows;u=(box[0]+sx)/2048;v=(box[1]+sy)/2048
    positions.extend((px0+(u-u0)/(u1-u0)*(px1-px0),py0+(v-v0)/(v1-v0)*(py1-py0)))
    uvs.extend(((ax+w*col/cols)/2048,(ay+h*row/rows)/2048))
  for row in range(rows):
   for col in range(cols):
    a=row*(cols+1)+col;b0=a+1;c=a+cols+1;triangles.extend((a,c,b0,b0,c,c+1))
  m['vertex_count']=(cols+1)*(rows+1);m['positions']=binary(positions);m['uvs']=binary(uvs);m['indices']=struct.pack('<'+'H'*len(triangles),*triangles)
  if key=='torso_remainder':index=33;model['art_meshes'][index]=m;names[index]=label
  else:index=len(model['art_meshes']);model['art_meshes'].append(m);names.append(label)
  indices.append(index)
 # All base-derived parts precede original face overlays and fringe.
 for group in model['draw_groups']:
  items=[]
  for item in group['items']:
   if not item['part'] and item['object']==33:items.extend({'part':False,'object':i,'child_group':None} for i in indices)
   else:items.append(item)
  group['items']=items;group['total']=len(items)
 assert doc['textures'][0]==read_aom(source)[0]['textures'][0]
 assert doc['expressions']==read_aom(source)[0]['expressions']
 target=out/'Leva_artwork_r04a.aom';write_aom(doc,target)
 report={'phase':'R04-A artwork structure checkpoint, not R04 complete','source_sha256':source_hash,'aom_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'layers':inventory,'model':{'parameters':len(model['parameters']),'deformers':len(model['deformers']),'meshes':len(model['art_meshes']),'textures':len(doc['textures'])},'neutral_layer_composite_exact':True,'original_atlas_unchanged':True,'source_expressions_unchanged':True,'premium_repainting_complete':False,'independent_arms_rigged':False,'full_body_complete':False,'generated_artwork':False,'trace_space':{'size':list(base.size),'atlas_box':box},'runtime_status':'requires_export_and_visual_QA'}
 (out/'artwork-audit.json').write_text(json.dumps(report,indent=2),encoding='utf8');return report

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=build(a.input,a.out);print(json.dumps({k:v for k,v in r.items() if k!='layers'}))
