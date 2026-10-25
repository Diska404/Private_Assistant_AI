import{quality,LIGHTING,damp,expressionTargets,FixedPhysics,MaterialLayer}from'./avatar_dynamics.js';
import{NaturalPerformance,FACE_PROFILES,FACE_CHANNELS}from'./avatar_performance.js';
import{ReactivePerformance,R2_FACE_PROFILES,R2_FACE_CHANNELS,REACTIONS}from'./avatar_reactions.js';
import{SecondaryMotionLayer,PoseDiscontinuityGuard}from'./avatar_secondary.js';
import{FramePacer,AvatarFrameMetrics,FrameLoadGovernor}from'./avatar_timing.js';
// Runtime-only 3D renderer. All imports/assets stay on the authenticated local host.
export class VRMAvatarProvider{
 constructor(canvas,{level=()=>0,audioPlaying=()=>false,features=()=>null,onMetrics=()=>{}}={}){Object.assign(this,{canvas,level,audioPlaying,features,onMetrics});this.dead=false;this.state='idle';this.expression='neutral';this.quality='balanced';this.frames=[];this.physics=new FixedPhysics();this.poseGuard=new PoseDiscontinuityGuard();this.pacer=new FramePacer();this.metrics=new AvatarFrameMetrics();this.blended={};this.adaptiveEnabled=true;this.governor=new FrameLoadGovernor();this.physicsRate='auto';this.renderScale=1;this.enhanced=true;this.performanceVersion='r2';this.secondaryEnabled=true;this.physicsEnabled=true;this.animationSpeed=1;this.freezePose=false;this.performance=new ReactivePerformance();this.abort=new AbortController();this.tick=t=>this.frame(t);}
 load({url,requestedGPU='rtx4050'}={}){if(!url||!/^\/api\/avatar-model\/(?:leva_original|pixiv_sample|pixiv_polished|custom)\.vrm$/.test(url))throw new Error('vrm_requires_approved_asset');this.requestedGPU=requestedGPU;return this.loadAsset(url)}
 get physicsHz(){return this.physicsRate&&this.physicsRate!=='auto'?this.physicsRate:quality(this.quality).physicsHz}
 setPhysicsRate(value){if(!['auto',15,30,60,120].includes(value))throw new Error('invalid_physics_rate');this.physicsRate=value;this.resetSimulation()}
 setAdaptive(value){this.adaptiveEnabled=!!value;this.governor?.reset();this.effectiveFps=quality(this.quality).fps;this.pacer.reset();this.metrics.reset()}
 setRenderScale(value){if(![.75,1,1.5,2].includes(value))throw new Error('invalid_render_scale');this.renderScale=value;this.resize?.()}
 async loadAsset(url){
  const V=await import('./avatar-vendor.js');if(this.dead)return;
  this.V=V;const {THREE,GLTFLoader,VRMLoaderPlugin,VRMUtils,OrbitControls}=V;
  this.renderer=new THREE.WebGLRenderer({canvas:this.canvas,alpha:true,antialias:true,powerPreference:this.requestedGPU==='rtx4050'?'low-power':'high-performance'});
  this.renderer.outputColorSpace=THREE.SRGBColorSpace;this.renderer.setClearColor(0,0);
  const gl=this.renderer.getContext(),debug=gl.getExtension('WEBGL_debug_renderer_info');
  this.observedRenderer=debug?gl.getParameter(debug.UNMASKED_RENDERER_WEBGL):'Tidak disediakan browser';
  this.gpuMatches=this.observedRenderer.toLowerCase().includes(this.requestedGPU==='rtx4050'?'rtx 4050':'rtx 5070');
  this.scene=new THREE.Scene();this.camera=new THREE.PerspectiveCamera(32,1,.05,25);
  this.ambient=new THREE.HemisphereLight(0xffffff,0x667184,1.6);this.scene.add(this.ambient);
  this.key=new THREE.DirectionalLight(0xfff1e7,1.5);this.key.position.set(-1,2,3);this.scene.add(this.key);
  this.rim=new THREE.DirectionalLight(0xb8dfff,.7);this.rim.position.set(2,1,-2);this.scene.add(this.rim);this.setLighting(this.lighting||'default');
  this.fill=new THREE.DirectionalLight(0xd4e5ff,0);this.fill.position.set(2,1,2);this.scene.add(this.fill);this.setLighting(this.lighting||'default');
  this.controls=new OrbitControls(this.camera,this.canvas);this.controls.enableDamping=true;this.controls.enablePan=false;this.controls.minDistance=.6;this.controls.maxDistance=5;
  const loader=new GLTFLoader();loader.register(parser=>new VRMLoaderPlugin(parser));
  const response=await fetch(url,{signal:this.abort.signal,credentials:'same-origin'});if(!response.ok)throw new Error('avatar_model_unavailable');
  const raw=await response.arrayBuffer();if(this.dead)return;
  const gltf=await loader.parseAsync(raw,location.origin+'/');const vrm=gltf.userData.vrm;
  if(!vrm)throw new Error('avatar_vrm_runtime_missing');
  if(this.dead){VRMUtils.deepDispose(vrm.scene);return}
  this.vrm=vrm;VRMUtils.rotateVRM0(vrm);this.scene.add(vrm.scene);
  this.canModify=['allowModification','allowModificationRedistribution'].includes(vrm.meta?.modification);
  this.sourceInfo={title:vrm.meta?.name||vrm.meta?.title||'',version:vrm.meta?.metaVersion||vrm.meta?.version||'',expressions:Object.keys(vrm.expressionManager?.expressionMap||{}),modification_allowed:this.canModify};
  this.setPerformanceVersion(this.performanceVersion);
  this.materialLayer=new MaterialLayer(vrm.materials,{maxAnisotropy:this.renderer.capabilities.getMaxAnisotropy()});this.setMaterial(this.canModify?(this.materialPreset||'source'):'source');
  vrm.humanoid?.update();vrm.scene.updateMatrixWorld(true);vrm.scene.traverse(node=>{if(node.isSkinnedMesh)node.skeleton?.update()});
  const bounds=new THREE.Box3().setFromObject(vrm.scene),point=new THREE.Vector3();
  const yOf=name=>{const node=vrm.humanoid?.getRawBoneNode(name);return node?node.getWorldPosition(point).y:null};
  const headY=yOf('head'),hipsY=yOf('hips'),feet=[yOf('leftFoot'),yOf('rightFoot')].filter(Number.isFinite);
  const minY=feet.length?Math.min(...feet,bounds.min.y):bounds.min.y;
  const height=Number.isFinite(headY)&&headY-minY>.2?(headY-minY)*1.12:bounds.max.y-bounds.min.y;
  this.modelBounds={height,minY,headY,hipsY};this.setFraming(this.framing||'portrait');
  this.secondary=new SecondaryMotionLayer(vrm,V,{height,allowModification:this.canModify});this.secondary.setEnabled(this.secondaryEnabled&&this.performanceVersion==='r2');
  this.armDirection=String(vrm.meta?.metaVersion)==='0'?-1:1;
  vrm.humanoid?.getNormalizedBoneNode('leftUpperArm')?.rotation.set(0,0,-1.15*this.armDirection);
  vrm.humanoid?.getNormalizedBoneNode('rightUpperArm')?.rotation.set(0,0,1.15*this.armDirection);
  this.pose={};for(const name of ['head','chest','spine','leftUpperArm','rightUpperArm','leftUpperLeg','rightUpperLeg']){const bone=vrm.humanoid?.getNormalizedBoneNode(name);if(bone)this.pose[name]={bone,rotation:bone.rotation.clone()}}
  this.helpers=new THREE.Group();this.scene.add(this.helpers);this.setDebug(this.debugEnabled||false);
  const gaze=new THREE.Object3D();gaze.position.copy(this.camera.position);this.scene.add(gaze);if(vrm.lookAt)vrm.lookAt.target=gaze;this.gaze=gaze;
  this.resize=()=>{if(this.dead||!this.renderer)return;const r=this.canvas.getBoundingClientRect(),max=this.renderer.capabilities.maxTextureSize;const ratio=Math.min((devicePixelRatio||1)*(this.renderScale||1),quality(this.quality).dpr*(this.renderScale||1),Math.sqrt(6000000/Math.max(1,r.width*r.height)),max/Math.max(1,r.width),max/Math.max(1,r.height));this.renderer.setPixelRatio(ratio);this.renderer.setSize(r.width,r.height,false);this.camera.aspect=Math.max(.1,r.width/Math.max(1,r.height));this.camera.updateProjectionMatrix()};
  this.resizeObserver=new ResizeObserver(this.resize);this.resizeObserver.observe(this.canvas);this.resize();
  this.visible=true;this.intersection=new IntersectionObserver(rows=>{this.visible=rows[0].isIntersecting;this.last=0;if(this.visible)this.schedule()});this.intersection.observe(this.canvas);
  this.visibility=()=>{this.pacer.reset();this.resetSimulation();if(!document.hidden)this.schedule()};document.addEventListener('visibilitychange',this.visibility);
  this.schedule();return {provider:'three-vrm',final_character:false,requested_gpu:this.requestedGPU,observed_renderer:this.observedRenderer,gpu_verified:this.gpuMatches};
 }
 schedule(){if(!this.dead&&!this.raf&&!document.hidden&&(this.visible||this.captureActive))this.raf=requestAnimationFrame(this.tick)}
 update(value={}){if(this.generation!==value.generation_id&&this.generation!=null)this.performance.reset();this.state=value.state||'idle';this.setExpression(value.expression||'neutral');this.generation=value.generation_id;
  const reactionKey=String(value.generation_id)+'|'+String(value.reaction_id);if(this.reactionKey!==reactionKey){this.reactionKey=reactionKey;if(value.reaction&&value.reaction!=='none'&&(value.reaction_age_ms==null||value.reaction_age_ms<2500))this.triggerReaction(value.reaction)}
 }
 setExpression(value){this.expression=value}
 setExpressionOverride(value){if(value&&!Object.hasOwn(R2_FACE_PROFILES,value))throw new Error('invalid_expression_profile');this.expressionOverride=value||null}
 setPerformanceVersion(value){if(!['r1','r2'].includes(value))throw new Error('invalid_performance_version');this.performanceVersion=value;this.reactionKey=null;const Controller=value==='r2'?ReactivePerformance:NaturalPerformance;this.performance=new Controller({supported:this.sourceInfo?.expressions});this.performanceFrame=null;this.secondary?.setEnabled(this.secondaryEnabled&&value==='r2');this.refreshDebug();this.resetSimulation()}
 setSecondaryEnabled(value){this.secondaryEnabled=!!value;this.secondary?.setEnabled(this.secondaryEnabled&&this.performanceVersion==='r2');this.refreshDebug();this.resetSimulation()}
 triggerReaction(value){if(!Object.hasOwn(REACTIONS,value))throw new Error('invalid_avatar_reaction');return this.performance.triggerReaction?.(value)||false}
 setViseme(value){this.vrm?.expressionManager?.setValue('aa',Math.max(0,Math.min(1,value||0)))}
 setGaze(value){if(this.gaze&&value)this.gaze.position.set(...value)}
 setFraming(value){if(!['portrait','full','face'].includes(value))throw new Error('invalid_avatar_framing');this.framing=value;if(!this.modelBounds)return;const {height:h,minY}=this.modelBounds;
  const {headY,hipsY}=this.modelBounds;
  const y=value==='full'?minY+h*.5:value==='face'&&Number.isFinite(headY)?headY+h*.035:value==='portrait'&&Number.isFinite(hipsY)&&Number.isFinite(headY)?(hipsY+headY)*.5+h*.025:minY+h*(value==='face'?.89:.72),distance=value==='full'?h/(2*Math.tan(this.camera.fov*Math.PI/360))*1.1:h*(value==='face'?.4:1.1);
  this.controls.target.set(0,y,0);const angle=this.viewAngle||0;this.camera.position.set(Math.sin(angle)*distance,y,Math.cos(angle)*distance);this.controls.update();
 }
 setView(name){const angles={front:0,quarter:Math.PI/4,side:Math.PI/2,back:Math.PI};if(!(name in angles))throw new Error('invalid_avatar_view');this.viewAngle=angles[name];if(this.modelBounds)this.setFraming(this.framing||'portrait')}
 setQuality(value){if(!['ultra','premium','performance','balanced','gaming','eco'].includes(value))throw new Error('invalid_avatar_quality');this.quality=value;this.effectiveFps=quality(value).fps;this.governor??=new FrameLoadGovernor();this.governor.reset();this.frames=[];this.reported=0;this.pacer.reset();this.metrics.reset();this.resetSimulation();this.resize?.()}
 setLighting(name){if(!LIGHTING[name])throw new Error('invalid_lighting_preset');this.lighting=name;if(this.ambient){const p=LIGHTING[name];this.ambient.intensity=p.ambient;this.key.intensity=p.key;this.key.color.setHex(p.color);this.rim.intensity=p.rim;if(this.fill)this.fill.intensity=p.fill||0}}
 setEnhanced(value){this.enhanced=!!value;this.performance.reset();for(const name of R2_FACE_CHANNELS)this.vrm?.expressionManager?.setValue(name,0);this.blended={};this.frames=[]}
 setPhysicsEnabled(value){this.physicsEnabled=!!value;this.resetSimulation()}
 setFreezePose(value){this.freezePose=!!value}
 setAnimationSpeed(value){if(![1,.25].includes(value))throw new Error('invalid_animation_speed');this.animationSpeed=value}
 resetSimulation(){this.physics.reset();this.poseGuard?.reset();this.vrm?.scene?.updateMatrixWorld(true);this.vrm?.springBoneManager?.reset();if(this.metrics)this.metrics.resets++}
 setMaterial(name){if(this.vrm&&!this.canModify&&name!=='source')throw new Error('Izin perubahan material aset ini belum terverifikasi.');this.materialPreset=name;this.materialLayer?.apply(name)}
 setDebug(value){this.debugEnabled=!!value;if(!this.helpers)return;this.helpers.visible=this.debugEnabled;if(!this.debugEnabled||this.helpers.children.length)return;
  const V=this.V;this.helpers.add(new V.THREE.SkeletonHelper(this.vrm.scene));for(const c of this.vrm.springBoneManager?.colliders||[])this.helpers.add(new V.VRMSpringBoneColliderHelper(c));for(const j of this.vrm.springBoneManager?.joints||[])this.helpers.add(new V.VRMSpringBoneJointHelper(j));
 }
 refreshDebug(){if(!this.helpers)return;for(const helper of [...this.helpers.children]){helper.dispose?.();helper.geometry?.dispose();helper.material?.dispose();this.helpers.remove(helper)}if(this.debugEnabled)this.setDebug(true)}
 playMotion(name='head_turn'){if(!['reactions','r2_validation','head_turn','head_pitch','head_tilt','fast_turn','shoulders','arms','body_turn','walk','hair','clothing','expressions'].includes(name))throw new Error('invalid_motion_test');this.motionTest={name,start:performance.now(),duration:12000}}
 animatePose(t,delta){
  for(const p of Object.values(this.pose))p.bone.rotation.copy(p.rotation);
  const scale=quality(this.quality).motion,head=this.pose.head?.bone,chest=this.pose.chest?.bone;
  if(this.enhanced&&this.performanceFrame){const p=this.performanceFrame;if(head){head.rotation.x+=p.headX;head.rotation.y+=p.headY;head.rotation.z+=p.headZ}if(chest)chest.rotation.x+=p.chestX+p.posture;if(this.pose.spine)this.pose.spine.bone.rotation.y+=p.spineY}
  else{if(head){head.rotation.y+=Math.sin(t*.00065)*.025*scale;head.rotation.z+=Math.sin(t*.0009)*.014*scale;if(this.state==='listening')head.rotation.z+=.04}if(chest)chest.rotation.x+=Math.sin(t*.0016)*.008*scale;}
  const test=this.motionTest;if(!test)return;const elapsed=(t-test.start)*this.animationSpeed;if(elapsed>test.duration){this.motionTest=null;return}const x=Math.max(0,Math.min(1,elapsed/600,(test.duration-elapsed)/600)),envelope=x*x*(3-2*x),wave=Math.sin(elapsed*.0018)*envelope,arm=(.5+.5*Math.sin(elapsed*.0012))*.75*envelope;
  if(test.name==='r2_validation'){
   const section=Math.floor(elapsed/2000),local=elapsed%2000,e=Math.sin(local/2000*Math.PI)**2;
   if(section===0&&head)head.rotation.y+=Math.sin(local*.004)*.45*e;
   if(section===1&&head)head.rotation.x+=Math.sin(local*.003)*.28*e;
   if(section===2&&head)head.rotation.z+=Math.sin(local*.004)*.16*e;
   if(section===3){if(this.pose.leftUpperArm)this.pose.leftUpperArm.bone.rotation.x+=.18*e;if(this.pose.rightUpperArm)this.pose.rightUpperArm.bone.rotation.x-=.18*e}
   if(section>=4){if(this.pose.spine)this.pose.spine.bone.rotation.y+=Math.sin(local*.003)*.24*e;if(this.pose.leftUpperArm)this.pose.leftUpperArm.bone.rotation.z+=.6*e*(this.armDirection||1);if(this.pose.rightUpperArm)this.pose.rightUpperArm.bone.rotation.z-=.6*e*(this.armDirection||1)}
  }
  if(['head_turn','hair'].includes(test.name)&&head)head.rotation.y+=wave*.45;
  if(test.name==='head_pitch'&&head)head.rotation.x+=wave*.28;
  if(test.name==='head_tilt'&&head)head.rotation.z+=wave*.18;
  if(test.name==='fast_turn'&&head)head.rotation.y+=Math.sin(elapsed*.004)*.48*envelope;
  if(['arms','clothing'].includes(test.name)){if(this.pose.leftUpperArm)this.pose.leftUpperArm.bone.rotation.z+=arm*(this.armDirection||1);if(this.pose.rightUpperArm)this.pose.rightUpperArm.bone.rotation.z-=arm*(this.armDirection||1)}
  if(['body_turn','clothing'].includes(test.name)&&this.pose.spine)this.pose.spine.bone.rotation.y+=wave*.3;
  if(test.name==='shoulders'){if(this.pose.leftUpperArm)this.pose.leftUpperArm.bone.rotation.x+=wave*.12;if(this.pose.rightUpperArm)this.pose.rightUpperArm.bone.rotation.x-=wave*.12;}
  if(test.name==='walk'){for(const [name,sign]of[['leftUpperLeg',1],['rightUpperLeg',-1]])if(this.pose[name])this.pose[name].bone.rotation.x+=Math.sin(elapsed*.005)*.2*sign}
 }
 frame(t){this.raf=0;if(this.dead||document.hidden||!this.visible&&!this.captureActive)return;
  const paced=this.pacer.accept(t,this.effectiveFps||quality(this.quality).fps);if(!paced){this.schedule();return}const {elapsed,delta}=paced;this.last=t;if(paced.stalled)this.resetSimulation();
  const started=performance.now();const exp=this.vrm.expressionManager;
  if(this.motionTest&&(t-this.motionTest.start)*this.animationSpeed>=this.motionTest.duration)this.motionTest=null;
  const phase=this.motionTest?Math.floor((t-this.motionTest.start)*this.animationSpeed/2000)%6:0;
  if(this.motionTest?.name==='reactions'&&this.motionTest.reactionPhase!==phase){this.motionTest.reactionPhase=phase;this.triggerReaction(['greeting','celebrate','ponder','playful','apology','comfort'][phase])}
  const tested=this.expressionOverride||(this.motionTest?.name==='reactions'?['gentle','proud','thinking','teasing','apologetic','grateful'][phase]:this.motionTest?.name==='expressions'?(this.enhanced?['soft_smile','laugh','confused','thinking','surprised','sad']:['neutral','happy','sad','angry','surprised','shy'])[phase]:this.expression);
  if(this.enhanced){this.performance.configure(this.state,tested);const p=this.performanceFrame=this.performance.update(delta,this.level(),{speed:this.animationSpeed,motion:quality(this.quality).motion,audioPlaying:this.audioPlaying(),features:this.features()});for(const name of R2_FACE_CHANNELS)exp?.setValue(name,p.weights[name]||0);this.mouth=p.weights.aa;}
  else{for(const [name,target]of Object.entries(expressionTargets(this.state,tested))){this.blended[name]=damp(this.blended[name]||0,target,delta,7);exp?.setValue(name,this.blended[name])}const blinkPhase=(t%4800)-4490;this.lastBlink=blinkPhase>0&&blinkPhase<220?Math.sin(blinkPhase/220*Math.PI):0;exp?.setValue('blink',this.lastBlink);this.mouth=damp(this.mouth||0,this.state==='interrupted'?0:this.level(),delta,22);this.setViseme(this.mouth);}
  if(!this.freezePose)this.animatePose(t,delta);this.controls.update();this.gaze.position.copy(this.camera.position);
  if(this.enhanced&&this.performanceFrame){this.gaze.position.x+=this.performanceFrame.gazeX*this.modelBounds.height;this.gaze.position.y+=this.performanceFrame.gazeY*this.modelBounds.height;}
  // Same component order as three-vrm 3.5.5 VRM.update, with bounded fixed spring steps.
  this.vrm.humanoid.update();this.vrm.lookAt?.update(delta);this.vrm.expressionManager?.update();this.vrm.nodeConstraintManager?.update();
  if(this.poseGuard.check(this.vrm.scene.position,this.vrm.scene.quaternion,this.modelBounds.height))this.resetSimulation();
  const physicsStarted=performance.now();let steps=0;if(this.physicsEnabled)steps=this.physics.update(delta*this.animationSpeed,this.physicsHz,dt=>this.vrm.springBoneManager?.update(dt));this.physicsCost=performance.now()-physicsStarted;
  for(const material of this.vrm.materials||[])material.update?.(delta);
  const renderStarted=performance.now();this.renderer.render(this.scene,this.camera);const renderCost=performance.now()-renderStarted;
  this.metrics.push(elapsed,performance.now()-started,this.physicsCost,steps,renderCost);
  if(!this.reported||t-this.reported>1000){this.reported=t;const report=this.metrics.snapshot(this.effectiveFps||quality(this.quality).fps);this.effectiveFps=this.governor.observe(report,quality(this.quality).fps,this.adaptiveEnabled);this.onMetrics({...report,requested_fps:quality(this.quality).fps,effective_next_fps:this.effectiveFps,adaptive_fallback:this.governor.fallback,render_width:this.canvas.width,render_height:this.canvas.height,render_scale:this.renderScale,model_bounds:this.modelBounds,ray_tracing:false,renderer:this.observedRenderer,gpu_verified:this.gpuMatches,profile:this.quality,physics_hz:this.physicsEnabled?this.physicsHz:0,physics_dropped_seconds:this.physics.discardedSeconds,physics_capped_frames:this.physics.cappedFrames,secondary:this.secondary?.summary(),controller:this.performanceVersion,enhanced:this.enhanced,calibration:this.enhanced&&this.performanceFrame?{state:this.state,profile:this.performanceFrame.profile,reaction:this.performanceFrame.reaction||'none',reaction_sequence:this.performanceFrame.reaction_sequence||0,transitioning:this.performanceFrame.transitioning,limited:this.performanceFrame.limited,weights:{...this.performanceFrame.weights}}:{state:this.state,profile:tested,transitioning:false,limited:false,weights:{...this.blended,blink:this.lastBlink||0,aa:this.mouth||0}},supported_expressions:this.sourceInfo.expressions,spring_joints:this.vrm.springBoneManager?.joints.size||0,colliders:this.vrm.springBoneManager?.colliders.length||0,mtoon_materials:this.materialLayer.items.length,draw_calls:this.renderer.info.render.calls,triangles:this.renderer.info.render.triangles});this.secondary?.beginWindow()}
  this.schedule();
 }
 dispose(){if(this.dead)return;this.dead=true;this.abort.abort();cancelAnimationFrame(this.raf);this.controls?.dispose();this.resizeObserver?.disconnect();this.intersection?.disconnect();if(this.visibility)document.removeEventListener('visibilitychange',this.visibility);for(const helper of this.helpers?.children||[]){helper.dispose?.();helper.geometry?.dispose();helper.material?.dispose()}this.secondary?.dispose();this.materialLayer?.restore();if(this.vrm)this.V.VRMUtils.deepDispose(this.vrm.scene);this.renderer?.dispose();this.renderer?.forceContextLoss();this.vrm=null;this.scene=null;this.frames=[];}
}
