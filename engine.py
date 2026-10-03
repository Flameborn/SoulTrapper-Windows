"""Compatibility bridge for Soul Trapper build 48's original ARM game scripts.
Only original chapter/HUD logic executes. iOS UI and audio APIs are bridged.
Unknown gameplay calls fail explicitly instead of silently skipping story.
"""
import json,struct,random,math
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import *
ROOT=Path(__file__).resolve().parent
REGS=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]
def f32(n):return struct.unpack('<f',struct.pack('<I',n))[0]
def b32(n):return struct.unpack('<I',struct.pack('<f',n))[0]
def signed(n):return n if n<0x80000000 else n-0x100000000
class Engine:
 def __init__(self,audio,chapter=1,seed=None):
  self.audio=audio;self.chapter=chapter;self.rng=random.Random(seed);self.now=0.;self.done=False;self.events=[];self.title='';self.location='';self.buttons=False;self.enabled=True;self.organ=False
  self.repeat_tracks=[];self.prompt_tracks=[];self.prompt_variants=[];self.checkpoint_requested=True;self.fade_flags={}
  self.beach_bonus_added=False;self.beach_pending_item=None;self.recording_choices={};self.recording_scene=None;self.lock_scene=None;self.beach_instructions=[]
  self.asked_topics=[];self.pending_topic=None;self.topic_left_menu=False
  self.dialog_candidate=None;self.dialog_stable_ticks=0
  self.replay_chapter=False
  self.checkpoint_locked=False
  self.heard_tracks=[];self.listening_track=None;self.repeated_topic=False;self.skip_repeated=False
  self.meta=json.loads((ROOT/'data/metadata.json').read_text());self.classes={c['name']:c for c in self.meta['classes']}
  self.strings={int(k):v for k,v in self.meta['strings'].items()};self.selectors={int(k):v for k,v in self.meta['selectors'].items()};self.seladdr={v:k for k,v in self.selectors.items()}
  self.cls=self.classes[f'Chapter{chapter:02}'];self.ivars={i['name']:i for c in [self.classes['InGameHUD'],self.cls] for i in c['ivars']}
  self.methods={m['name']:m['imp'] for c in [self.classes['InGameHUD'],self.cls] for m in c['methods']}
  self.u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);self.u.mem_map(0,0x100000);b=(ROOT/'data/SoulTrapper.arm').read_bytes()
  for s in self.meta['sections']:
   if s['name'] not in ('__bss','__common'):self.u.mem_write(s['addr'],b[s['off']:s['off']+s['size']])
  self.apply_script_patches()
  self.u.mem_map(0x100000,0x400000);self.obj=0x100000;self.heap=0x110000;self.objects={};self.intern={};self.timers={};self.effects={};self.next_effect=1
  self.put(0x1b8,0x100800);self.objects[0x100800]={'delegate':True}
  self.handlers={int(k):v for k,v in self.meta['stubs'].items() if v!='?'}
  self.handlers.update({int(k):v for k,v in self.meta['functions'].items() if v.startswith('_SoundEngine_') or v=='_HeadPhoneCheck'})
  self.u.hook_add(UC_HOOK_CODE,self.hook)
  self.button_fields=['ForwardButton','BackButton','LeftButton','RightButton','ActionButton','ReleaseButton','AimLeftButton','AimRightButton']+['Dialog'+w+'Button' for w in ['One','Two','Three','Four','Five']]
  for n in self.button_fields:self.set(n,self.alloc({'enabled':True}))
  self.call('initWithNibName:bundle:');self.call('DrawRect')
 def apply_script_patches(self):
  if self.chapter==13:
   # Allow one additional native sequence, exposing the previously unreachable
   # fifth intro and the congratulations at SequenceComplete % 5 == 1.
   for address,register in ((0x1708c,0x29),(0x17132,0x2b)):
    old=bytes(self.u.mem_read(address,2))
    if old not in (bytes((5,register)),bytes((6,register))):raise ValueError('Unexpected beach script revision')
    self.u.mem_write(address,bytes((6,register)))
 def read(self,a):return struct.unpack('<I',self.u.mem_read(a,4))[0]
 def write(self,a,v):self.u.mem_write(a,struct.pack('<I',int(v)&0xffffffff))
 def put(self,o,v):self.write(self.obj+o,v)
 def get(self,n):
  i=self.ivars[n];a=self.obj+i['offset'];return self.u.mem_read(a,1)[0] if i['size']==1 else signed(self.read(a))
 def set(self,n,v):
  i=self.ivars[n];a=self.obj+i['offset']
  if i['size']==1:self.u.mem_write(a,bytes([int(v)&255]))
  else:self.write(a,v)
 def alloc(self,value=None):
  if isinstance(value,str) and value in self.intern:return self.intern[value]
  a=self.heap;self.heap+=max(64,((len(value.encode())+1+63)//64)*64) if isinstance(value,str) else 64
  if self.heap>=0x3f0000:raise RuntimeError('Compatibility heap exhausted')
  self.objects[a]=value if value is not None else {}
  if isinstance(value,str):self.intern[value]=a
  return a
 def string(self,a):
  if a in self.strings:return self.strings[a]
  v=self.objects.get(a)
  if isinstance(v,str):return v
  if not a:return ''
  try:return bytes(self.u.mem_read(a,512)).split(b'\0')[0].decode('utf8')
  except Exception:return ''
 def cstring(self,s):
  a=self.alloc(s);self.u.mem_write(a,s.encode()+b'\0');return a
 def reg(self,n):return self.u.reg_read(REGS[n])
 def args(self):return [self.reg(i) for i in range(4)]+[self.read(self.u.reg_read(UC_ARM_REG_SP)+i*4) for i in range(12)]
 def ret(self,v=0):
  if isinstance(v,tuple):
   for i,x in enumerate(v):self.u.reg_write(REGS[i],x&0xffffffff)
  else:self.u.reg_write(UC_ARM_REG_R0,int(v)&0xffffffff)
  self.u.reg_write(UC_ARM_REG_PC,self.u.reg_read(UC_ARM_REG_LR))
 def double(self,lo,hi):return struct.unpack('<d',struct.pack('<II',lo,hi))[0]
 def dbits(self,x):return struct.unpack('<II',struct.pack('<d',x))
 def call(self,sel,*args):
  if sel not in self.methods:return
  self.u.reg_write(UC_ARM_REG_SP,0x4ff000);self.u.reg_write(UC_ARM_REG_LR,0x80001)
  for i,v in enumerate([self.obj,self.seladdr.get(sel,0),*args]):
   if i<4:self.u.reg_write(REGS[i],v)
   else:self.write(0x4ff000+(i-4)*4,v)
  try:self.u.emu_start(self.methods[sel],0x80000,count=150000)
  except Exception as e:raise RuntimeError(f'Chapter {self.chapter}, scene {self.get("SceneIndex")}, {sel}, PC {self.u.reg_read(UC_ARM_REG_PC):x}: {e}') from e
  if self.u.reg_read(UC_ARM_REG_PC)!=0x80000:raise RuntimeError('Script exceeded instruction limit')
 def hook(self,u,address,size,data):
  # The original checks the next target's sentinel after incrementing Target,
  # cutting off the watch discovery. During its pending speech, test the
  # item just dug up instead; the final target still follows the original path.
  if self.chapter==13 and address==0x17dc8:
   if self.get('TimeThrough')==0:self.beach_pending_item=self.get('Target') if self.reg(3) else None
   if self.beach_pending_item is not None:
    base=self.obj+self.ivars['BeachTargets']['offset']+self.beach_pending_item*32
    u.reg_write(UC_ARM_REG_R3,self.read(base+28))
  name=self.handlers.get(address)
  if not name:return
  a=self.args()
  if name=='_objc_msgSend':self.message(a);return
  if name=='_objc_msgSendSuper2':self.ret(self.read(a[0]));return
  if name=='_objc_msgSend_stret':
   self.u.mem_write(a[0],struct.pack('<4f',0,0,320,480));self.ret();return
  if name.startswith('_SoundEngine_'):self.sound(name[13:],a);return
  if name.startswith('___') and name.endswith('vfp'):self.math(name,a);return
  if name in ('_rand','_random'):self.ret(self.rng.randrange(0x7fffffff));return
  if name in ('___modsi3','___umodsi3','___udivsi3'):
   x,y=(signed(a[0]),signed(a[1])) if name=='___modsi3' else a[:2];self.ret((x-int(x/y)*y if 'mod' in name else x//y) if y else 0);return
  if name=='_sqrt':self.ret(self.dbits(math.sqrt(self.double(*a[:2]))));return
  if name in ('_HeadPhoneCheck','_srandom','_free','_CFRelease','_AudioSessionSetActive','_AudioSessionSetProperty'):self.ret();return
  if name=='_strlen':self.ret(len(self.string(a[0])));return
  raise RuntimeError('Unbridged function '+name)
 def math(self,name,a):
  n=name[3:-3];double='df' in n;f=lambda i:self.double(a[i],a[i+1]) if double else f32(a[i]);x=f(0);y=f(2 if double else 1)
  op=n[:3]
  if n.startswith('floatsi'):v=float(signed(a[0]))
  elif n.startswith('fix'):self.ret(int(x));return
  elif n.startswith('extendsf'):self.ret(self.dbits(f32(a[0])));return
  elif n.startswith('truncdf'):self.ret(b32(self.double(*a[:2])));return
  elif op=='add':v=x+y
  elif op=='sub':v=x-y
  elif op=='mul':v=x*y
  elif op=='div':v=x/y if y else 0.
  else:
   # Darwin's VFP helpers return boolean predicates, unlike soft-float libgcc.
   if n.startswith('eq'):v=int(x==y)
   elif n.startswith('ne'):v=int(x!=y)
   elif n.startswith('ge'):v=int(x>=y)
   elif n.startswith('gt'):v=int(x>y)
   elif n.startswith('le'):v=int(x<=y)
   elif n.startswith('lt'):v=int(x<y)
   elif n.startswith('unord'):v=int(math.isnan(x) or math.isnan(y))
   else:raise RuntimeError('Unknown VFP helper '+name)
   self.ret(v);return
  self.ret(self.dbits(v) if double else b32(v))
 def message(self,a):
  r,sel,x,y=a[:4];s=self.selectors.get(sel) or self.string(sel)
  if s=='Initialization':
   for iv in self.classes['InGameHUD']['ivars']:
    n=iv['name']
    if n.endswith('Index') and n!='SceneIndex':self.set(n,-1)
   self.set('PauseGame',0);self.ret();return
  if s=='ShowButtons:':
   self.buttons=bool(x);self.set('ShowButtons',x)
   if x:
    self.enabled=True
    for n in self.button_fields:self.objects[self.get(n)]['enabled']=True
   self.ret();return
  if s=='EnableButtons:':
   self.enabled=bool(x)
   for n in self.button_fields:self.objects[self.get(n)]['enabled']=bool(x)
   self.ret();return
  if s=='SetLocationHeader:':
   if self.location!=self.string(x):self.checkpoint_locked=False
   self.location=self.string(x);self.audio.scene_location=self.location;self.stop_departed_trap_ambience()
   for q in ('bg','bg2'):self.audio.volume(q,self.audio.volumes.get(q,1.))
   self.set('LocationHeader1',x);self.ret();return
  if s=='SetChapterHeader:':self.title=self.string(x);self.ret();return
  if s=='setMapImage:width:height:':self.set('CurrentMapImage',x);self.ret();return
  if s in ('SetBackgroundImage:','SetBackgroundImage:transitionTime:','setupButtonsPlaneView','SetStandardButtons','TransitionScenes:','SaveMe'):self.ret();return
  if s=='SetMapView:':self.ret();return
  if s=='displayOrganPuzzle:':self.organ=bool(x);self.ret();return
  if s=='disableOrgan:':self.organ=not bool(x);self.ret();return
  if s=='respondsToSelector:':self.ret(1);return
  if r==0x100800:
   if s=='DidFinishScene:':self.done=True;self.events.append(('chapter_complete',s))
   elif s in ('PlaySuccClick','PlayUnSuccClick'):
    self.input_clicks=getattr(self,'input_clicks',0)+1
    self.audio.load('click','SFX_BUTTON_CLICK.caf' if s=='PlaySuccClick' else 'SFX_BUTTON_DISABLED.caf');self.audio.start('click')
   else:raise RuntimeError('Unknown delegate '+s)
   self.ret();return
  if r==self.obj and s in self.methods:
   if s.startswith('PlayForegroundTrack'):
    original=self.string(x);replacement=self.extra_recording(original,s,y)
    if original in ('C01_0014','C05_0027'):self.lock_scene=self.get('SceneIndex')
    if replacement!=original:
     x=self.alloc(replacement);self.u.reg_write(UC_ARM_REG_R2,x)
   if s in ('PlayForegroundTrack:','PlayForegroundTrack2:','PlayForegroundTrackLong:ForegroundTrackShort:'):
    name=self.string(x)
    if name:
     self.prompt_tracks=[name+'.caf'];self.prompt_variants=list(self.prompt_tracks)
     if s=='PlayForegroundTrackLong:ForegroundTrackShort:' and y:self.prompt_variants.append(self.string(y)+'.caf')
    repeat=getattr(self,'manual_repeat',None)
    if repeat and repeat['scene']==self.get('SceneIndex') and name+'.caf' in repeat['tracks'] and self.now<repeat['until']:
     self.ret();return
   self.u.reg_write(UC_ARM_REG_PC,self.methods[s]);return
  if s in ('mainBundle','defaultManager','defaultCenter','standardUserDefaults','mainScreen'):self.ret(0x100900);return
  if s=='pathForResource:ofType:':self.ret(self.alloc(self.string(x)+'.'+self.string(y)));return
  if s=='UTF8String':self.ret(self.cstring(self.string(r)));return
  if s=='fileExistsAtPath:':self.ret(self.audio.exists(self.string(x)));return
  if s=='isEqualToString:':self.ret(int(self.string(r)==self.string(x)));return
  if s=='alloc':self.ret(self.alloc());return
  if s in ('init','initWithFrame:'):self.ret(r);return
  if s=='initWithObjects:':
   vals=[]
   for v in a[2:]:
    if not v:break
    vals.append(v)
   self.objects[r]=vals;self.ret(r);return
  if s in ('numberWithInt:','numberWithUnsignedInt:'):self.ret(self.alloc(x));return
  if s=='intValue':self.ret(self.objects.get(r,0));return
  if s=='count':self.ret(len(self.objects.get(r,[])));return
  if s=='addObject:':
   if not isinstance(self.objects.get(r),list):self.objects[r]=[]
   self.objects[r].append(x);self.ret();return
  if s=='objectAtIndex:':
   if not r:self.ret(0);return
   value=self.objects[r]
   if not isinstance(value,list):raise TypeError('objectAtIndex requires an array')
   self.ret(value[x]);return
  if s=='exchangeObjectAtIndex:withObjectAtIndex:':
   v=self.objects[r];v[x],v[y]=v[y],v[x];self.ret();return
  if s=='removeObjectAtIndex:':self.objects[r].pop(x);self.ret();return
  if s=='objectForKey:':self.ret(self.objects.get(r,{}).get(self.string(x),0));return
  if s=='setObject:forKey:':self.objects.setdefault(r,{})[self.string(y)]=x;self.ret();return
  if s=='synchronize':self.ret();return
  if s=='dictionaryWithObjectsAndKeys:':
   values={}
   for i in range(2,len(a)-1,2):
    if not a[i]:break
    values[self.string(a[i+1])]=a[i]
   self.ret(self.alloc(values));return
  if s=='scheduledTimerWithTimeInterval:target:selector:userInfo:repeats:':
   interval=self.double(x,y);target,selector,info,repeats=a[4:8];p=self.alloc();self.timers[p]={'due':self.now+interval,'interval':interval,'selector':self.selectors.get(selector) or self.string(selector),'repeat':bool(repeats),'valid':True};self.ret(p);return
  if s=='invalidate':
   if r in self.timers:self.timers[r]['valid']=False
   self.ret();return
  if s=='isValid':self.ret(int(self.timers.get(r,{}).get('valid',False)));return
  if s in ('date','distantFuture','dateWithTimeIntervalSinceNow:'):
   self.ret(self.alloc(self.now+(self.double(x,y) if s.startswith('dateWith') else (1e9 if s=='distantFuture' else 0))));return
  if s=='fireDate':self.ret(self.alloc(self.timers[r]['due']));return
  if s=='setFireDate:':self.timers[r]['due']=self.objects[x];self.ret();return
  if s=='timeIntervalSinceDate:':self.ret(self.dbits(self.objects[r]-self.objects[x]));return
  if s=='addObserver:selector:name:object:':self.ret();return
  if s=='setEnabled:':
   if r:self.objects.setdefault(r,{})['enabled']=bool(x)
   self.ret();return
  if s=='isEnabled':self.ret(int(self.objects.get(r,{}).get('enabled',True)));return
  if s in ('release','retain','autorelease','setNeedsDisplay','setTransitioning:','setDelegate:','addSubview:','removeFromSuperview','resignFirstResponder','becomeFirstResponder','setContentHorizontalAlignment:','setBackgroundColor:','setImage:'):self.ret(r);return
  if s in ('view','superview','imageNamed:','clearColor'):self.ret(self.alloc());return
  if s=='buttonWithTitle:target:selector:frame:image:imagePressed:darkTextColor:':self.ret(self.alloc({'enabled':True}));return
  raise RuntimeError(f'Unbridged selector {s!r} receiver {r:x}')
 def sound(self,s,a):
  # The original uses five streaming queues plus positional OpenAL effects.
  queue='fg' if 'Foreground' in s else ('fx2' if 'FX' in s and s.endswith('2') else 'fx' if 'FX' in s else 'bg2' if s.endswith('2') else 'bg')
  if s.startswith('BackgroundMusic') and 'Fade' in s:
   key=queue+('In' if 'FadeIn' in s else 'Out')
   if 'Set' in s:
    self.fade_flags[key]=bool(a[0])
    if a[0]:self.fade_flags[queue+('Out' if 'FadeIn' in s else 'In')]=False
    self.ret()
   else:self.ret(int(self.fade_flags.get(key,False)))
   return
  if s.startswith('GetIs'):self.ret(int(self.audio.busy(queue)));return
  if s.startswith('Load') and 'Track' in s:
   if queue=='fg':
    self.listening_track=None
    # A new narration starts a scene checkpoint; timed puzzle responses do not.
    if not self.checkpoint_locked and not self.interactive_challenge():self.checkpoint_requested=True
    if self.chapter==4 and Path(self.string(a[0])).stem=='C04_0011' and Path(self.audio.loaded.get('fx2','')).stem=='C04_FX_000A':self.audio.stop('fx2')
    if self.chapter==7 and Path(self.string(a[0])).stem=='C07_0001':
     for q in ('fx','fx2'):
      if Path(self.audio.loaded.get(q,'')).stem=='C04_FX_000A':self.audio.stop(q)
   if queue.startswith('bg'):
    self.fade_flags[queue+'In']=False;self.fade_flags[queue+'Out']=False
   self.audio.load(queue,self.string(a[0]));self.ret();return
  if s.startswith('Start') and 'Music' in s:
   self.audio.start(queue,queue.startswith('bg'))
   if queue=='fg':
    self.checkpoint_pending=True
    name=self.audio.loaded.get('fg')
    self.listening_track=name
    if self.chapter==13 and name:
     if name.startswith('C13_0001'):self.beach_instructions=[]
     elif name.startswith(('C13_0002','C13_0003','C13_0004','C13_0005')):self.beach_instructions.append(name)
    if name and (not self.repeat_tracks or self.repeat_tracks[-1]!=name):self.repeat_tracks.append(name)
   self.ret();return
  if s.startswith(('Unload','Stop','Pause')) and ('Music' in s or 'Track' in s):
   if queue=='fg' and not (s.startswith('Stop') and a[0]):self.listening_track=None
   if s.startswith('Unload') and queue.startswith('bg'):
    self.fade_flags[queue+'In']=False;self.fade_flags[queue+'Out']=False
   if not (s.startswith('Stop') and a[0]):self.audio.stop(queue)
   self.ret();return
  if s.startswith('Get') and 'Volume' in s:self.ret(b32(self.audio.volumes.get(queue,.75)));return
  if s.startswith('Set') and 'Volume' in s:self.audio.volume(queue,min(1.,max(0.,f32(a[0]))));self.ret();return
  if s.startswith('Load') and 'Effect' in s:
   ptr=a[3] if 'Looping' in s else a[1];i=self.next_effect;self.next_effect+=1
   self.effects[i]={'name':self.string(a[0]),'loop':'Looping' in s,'attack':self.string(a[1]) if 'Looping' in s else '', 'pos':(0.,0.,0.),'gain':1.};self.write(ptr,i);self.ret();return
  if s=='StartEffect':
   pos=self.detector_position(a[0])
   if pos is not None:self.effects[a[0]]['pos']=pos
   self.audio.effect(a[0],self.effects[a[0]]);self.ret();return
  if s in ('StopEffect','UnloadEffect'):self.audio.stop('e'+str(a[0]));self.ret();return
  if s=='SetEffectPosition':
   if a[0] in self.effects:
    self.effects[a[0]]['pos']=self.detector_position(a[0]) or tuple(f32(n) for n in a[1:4])
    self.audio.position(a[0],self.effects[a[0]]['pos'])
   self.ret();return
  if s=='SetEffectLevel':
   if a[0] in self.effects:self.effects[a[0]]['gain']=f32(a[1]);self.audio.volume('e'+str(a[0]),f32(a[1]))
   self.ret();return
  if s in ('SetListenerPosition','SetListenerVectorV','SetDistanceModel','SetListenerGain','SetMaxDistance','Initialize','Teardown','UnloadEffects','SetLooping'):self.ret();return
  raise RuntimeError('Unbridged sound '+s)
 def stop_departed_trap_ambience(self):
  if self.chapter!=16 or self.location not in ("Ned's Camper",'Church','Nave','Church Altar','Church Organ Bay'):return
  for q in ('bg','bg2'):
   if Path(self.audio.loaded.get(q,'')).stem=='C02_BG_001':
    self.audio.stop(q);self.fade_flags[q+'In']=False;self.fade_flags[q+'Out']=False
 def detector_position(self,effect_id):
  if self.chapter!=13 or effect_id not in (self.get('SlowFX'),self.get('OverObject')):return None
  target=self.get('Target')
  if not 0<=target<4:return None
  player=struct.unpack('<2f',self.u.mem_read(self.obj+self.ivars['Player']['offset'],8))
  dest=struct.unpack('<2f',self.u.mem_read(self.obj+self.ivars['BeachTargets']['offset']+target*32+16,8))
  dx,dy=dest[0]-player[0],dest[1]-player[1]
  heading=self.get('PlayerDir')%4
  fx=(0,1,0,-1)[heading];fy=(1,0,-1,0)[heading]
  distance=math.hypot(dx,dy)
  if distance<.001:return (0.,0.,-.05)
  # Listener-relative bearing. Native distance still controls beep rate/gain.
  return ((dx*fy-dy*fx)/distance,0.,-(dx*fx+dy*fy)/distance)
 def update_detector_bearing(self):
  if self.chapter!=13:return
  for effect_id in (self.get('SlowFX'),self.get('OverObject')):
   if effect_id not in self.effects:continue
   pos=self.detector_position(effect_id)
   if pos is not None:
    self.effects[effect_id]['pos']=pos;self.audio.position(effect_id,pos)
 def extra_recording(self,name,selector,following):
  if self.chapter==13 and name in {f'C13_0001{s}' for s in 'ABCDE'}:
   return 'C13_0001'+'ABCDE'[(max(1,self.get('SequenceComplete'))-1)%5]
  scene=self.get('SceneIndex')
  if self.recording_scene!=scene:self.recording_scene=scene;self.recording_choices={}
  field=None;candidate=None;chance=2
  if self.chapter==13 and selector=='PlayForegroundTrack:FollowingScene:' and following in (32,33,34,35):
   field='NumSteps'+('One','Two','Three','Four')[following-32]
   candidate={'C13_0005B':'C13_0005A','C13_0005D':'C13_0005C','C13_0005F':'C13_0005E'}.get(name)
   if name[:8] in ('C13_0002','C13_0003','C13_0004') and name[-1:] in ('B','C','D'):candidate=name[:8]+'A';chance=4
  elif name in ('C01_0010','C01_0012') and 'CorrectAimCount' in self.ivars and self.get('CorrectAimCount')>0:
   candidate={'C01_0010':'C01_0011','C01_0012':'C01_0013'}[name]
  if not candidate:return name
  # Native scripts call this on successive ticks while a recording plays.
  # Keep both the selected file and its counter stable until the scene changes.
  if name not in self.recording_choices:self.recording_choices[name]=candidate if self.rng.randrange(chance)==0 else name
  replacement=self.recording_choices[name]
  if field and replacement!=name:self.set(field,1)
  return replacement
 def update_lock_on(self):
  fire=any(self.get(field)!=-1 and self.string(self.get(image)&0xffffffff)=='FIRE_BTTN.png' for field,image in (('ActionSceneIndex','ActionButtonImage'),('ReleaseSceneIndex','ReleaseButtonImage')))
  # Chapter 9 reuses the fire icon to release Ollie (scene 181).
  # Only its two actual capture prompts should have a targeting tone.
  if self.chapter==9:fire=self.get('SceneIndex') in (11,80) and self.get('ActionSceneIndex') in (12,81)
  ready=(fire or (self.lock_scene is not None and self.lock_scene==self.get('SceneIndex'))) and not self.done
  if ready and not getattr(self,'lock_on_ready',False):
   self.audio.load('lock-on','C01_FX_004.caf');self.audio.volume('lock-on',.5);self.audio.start('lock-on',True)
  elif not ready and getattr(self,'lock_on_ready',False):self.audio.stop('lock-on')
  self.lock_on_ready=ready
 def tick(self,dt=1/30):
  if self.listening_track and not self.audio.busy('fg'):
   if self.listening_track not in self.heard_tracks:self.heard_tracks.append(self.listening_track)
   self.listening_track=None
  self.now+=dt;self.audio.tick(dt)
  for p,t in list(self.timers.items()):
   if t['valid'] and self.now>=t['due']:
    if t['repeat']:t['due']=self.now+max(.01,t['interval'])
    else:t['valid']=False
    self.call(t['selector'])
  self.prepare_beach_bonus()
  last_organ_note=self.chapter==9 and self.get('SceneIndex')==71 and self.get('CurrentOrganSequence')>=6 and self.audio.busy('fx')
  if last_organ_note and hasattr(self.audio,'preserve_tail'):self.audio.preserve_tail('fx')
  if not self.done:self.call('runScript')
  if self.chapter==9 and self.get('SceneIndex')!=71:self.organ=False
  if self.interactive_challenge():self.skip_repeated=False;self.checkpoint_locked=True
  self.update_detector_bearing()
  self.update_lock_on()
  topics=tuple(o for o in self.options(False) if o[0].isdigit())
  candidate=(self.get('SceneIndex'),topics) if topics and not self.audio.busy('fg') else None
  self.dialog_stable_ticks=self.dialog_stable_ticks+1 if candidate and candidate==self.dialog_candidate else 0
  self.dialog_candidate=candidate
  if self.pending_topic:
   topics=[o for o in self.options() if o[0].isdigit()]
   if not topics:self.topic_left_menu=True
   elif self.topic_left_menu:
    if self.pending_topic not in self.asked_topics:self.asked_topics.append(self.pending_topic)
    self.pending_topic=None;self.topic_left_menu=False;self.repeated_topic=False;self.skip_repeated=False
  if self.skip_repeated and self.audio.busy('fg'):
   if not self.skip_heard():self.skip_repeated=False
  elif self.skip_repeated and not self.pending_topic and self.options():self.skip_repeated=False
 def prepare_beach_bonus(self):
  # The watch is already target 2. After its recording ends, reuse that
  # completed slot for the unused sand dollar; keep the final story target.
  if self.chapter!=13 or self.beach_bonus_added or self.get('SceneIndex')!=110 or self.get('Target')!=3:return
  base=self.obj+self.ivars['BeachTargets']['offset']+2*32
  old=struct.unpack('<2f',self.u.mem_read(base+16,8))
  x0,y0,x1,y1=struct.unpack('<4f',self.u.mem_read(base,16))
  choices=[(x,y) for x in range(int(x0),int(x1)) for y in range(int(y0),int(y1)) if math.hypot(x-old[0],y-old[1])>=4]
  x,y=self.rng.choice(choices)
  self.u.mem_write(base+16,struct.pack('<2f',x,y))
  self.write(base+28,self.alloc('C13_0014'))
  self.set('Target',2);self.beach_bonus_added=True
 def trap_controls(self):
  if self.chapter==13 and self.get('SceneIndex')<150:return False
  return self.chapter in (1,2,5,7,9,12,13,16,19,20) and (self.get('AimLeftIndex')!=-1 or self.get('AimRightIndex')!=-1)
 def interactive_challenge(self):
  if self.chapter==9 and self.get('SceneIndex')==11:return True
  if self.organ or self.trap_controls() or self.safe_active():return True
  if self.chapter==9 and self.get('SceneIndex')==71:return True
  if self.chapter==13 and self.get('SceneIndex') in (21,40,41,50,51,60,61):return True
  for field,image in (('ActionSceneIndex','ActionButtonImage'),('ReleaseSceneIndex','ReleaseButtonImage')):
   if self.get(field)!=-1 and self.string(self.get(image)&0xffffffff) in ('HEART_RATE_BTTN.png','INHALE_EXHALE_BUTTN.png','FIRE_BTTN.png','SWORD_CENTER_BTTN.png','MALLET_BTTN.png','SHOVEL_BTTN.png','GET_CRYSTAL_BTTN.png','FREQUENCY_BTTN.png','SHELLGAME_BUTTON.png'):return True
  return False
 def options(self,ready_dialogue=True,include_disabled=False):
  if not self.buttons and not include_disabled:return []
  out=[]
  names=[('up','UpSceneIndex','UpAction:'),('down','DownSceneIndex','DownAction:'),('left','LeftSceneIndex','LeftAction:'),('right','RightSceneIndex','RightAction:'),('space','ActionSceneIndex','ActionButtonAction:'),('enter','ReleaseSceneIndex','ReleaseButtonAction:'),('left','AimLeftIndex','AimLeftAction:'),('right','AimRightIndex','AimRightAction:')]
  for key,field,method in names:
   if self.get(field)!=-1:
    image_field={'ActionSceneIndex':'ActionButtonImage','ReleaseSceneIndex':'ReleaseButtonImage'}.get(field)
    img=self.string(self.get(image_field)&0xffffffff) if image_field else ''
    if self.chapter==9 and self.get('SceneIndex')==11 and field=='ActionSceneIndex':key='up'
    elif img=='HEART_RATE_BTTN.png':key='down'
    elif img=='INHALE_EXHALE_BUTTN.png':key='up'
    elif img=='LEVER_BTTN.png':key='space'
    elif self.chapter==13 and img=='SHOVEL_BTTN.png':key='down'
    elif self.chapter==4 and img in ('UNLOCK_SAFE_BTTN.png','GET_CRYSTAL_BTTN.png','FREQUENCY_BTTN.png'):key='up'
    elif self.chapter==15 and img=='FREQUENCY_BTTN.png':key='up'
    elif self.chapter in (5,17) and img=='MALLET_BTTN.png':key='up'
    elif 'NAV_UP' in img or 'MOVE_FORWARD' in img or img in ('SWORD_CENTER_BTTN.png','FIRE_BTTN.png') or (self.chapter==17 and img=='MALLET_BTTN.png') or (field=='ActionSceneIndex' and self.trap_controls()) or (self.chapter==23 and img=='SHELLGAME_BUTTON.png'):key='up'
    elif 'NAV_DWN' in img:key='down'
    button={'UpAction:':'ForwardButton','DownAction:':'BackButton','ActionButtonAction:':'ActionButton','ReleaseButtonAction:':'ReleaseButton'}.get(method,method.replace('Action:','Button'))
    if not include_disabled and not self.objects.get(self.get(button),{}).get('enabled',True):continue
    out.append((key,('Action' if key=='space' else 'Release' if key=='enter' else key.title()),method))
  # Chapter scripts briefly restore stale topics while advancing scenes.
  # Expose them to both speech and input only after three quiet script ticks.
  if ready_dialogue and (self.dialog_stable_ticks<2 or self.audio.busy('fg')):return out
  for i,w in enumerate(['One','Two','Three','Four','Five'],1):
   if self.get('DialogLine'+w+'Index')!=-1 and self.objects.get(self.get('Dialog'+w+'Button'),{}).get('enabled',True):out.append((str(i),self.string(self.get('DialogLine'+w)&0xffffffff),'Dialog'+w+'Action:'))
  return out
 def press(self,key):
  # Original samples ascend B, C, E, F, G (the original F sample is F sharp).
  if self.organ and key in ('1','2','3','4','5'):
   self.call(('B','C','E','F','G')[int(key)-1]+'NoteButton:',0);return True
  for k,label,method in self.options():
   if k==key:
    # Aim feedback replaces the active action cue, without touching ambience.
    if method in ('AimLeftAction:','AimRightAction:'):
     self.audio.stop('fx');self.audio.stop('fx2')
     if self.chapter in (4,7,15) and self.string(self.get('ActionButtonImage')&0xffffffff)=='FREQUENCY_BTTN.png':
      self.audio.stop('fg');self.listening_track=None
    if self.chapter==4 and method=='ActionButtonAction:' and self.string(self.get('ActionButtonImage')&0xffffffff)=='GET_CRYSTAL_BTTN.png':
     self.audio.stop('fg');self.listening_track=None
     self.audio.stop('fx');self.audio.stop('fx2')
    self.skip_repeated=False
    if key.isdigit():
     self.repeated_topic=self.topic_label((k,label,method)).startswith('Already selected. ')
     self.pending_topic=self.topic_id((k,label,method));self.topic_left_menu=False
    else:self.repeated_topic=False
    if not self.interactive_challenge():
     self.checkpoint_locked=False
     self.checkpoint_requested=True;self.repeat_tracks=[];self.prompt_tracks=[];self.prompt_variants=[]
    heartbeat=key=='down' and self.string(self.get('ActionButtonImage')&0xffffffff)=='HEART_RATE_BTTN.png'
    clicks=getattr(self,'input_clicks',0)
    frequency_confirm=self.chapter==7 and method=='ActionButtonAction:' and self.string(self.get('ActionButtonImage')&0xffffffff)=='FREQUENCY_BTTN.png'
    self.call(method,0)
    self.update_lock_on()
    if frequency_confirm:
     self.audio.load('frequency-confirm','INTER_CHANGEIVERCHANNEL.caf');self.audio.start('frequency-confirm')
    if heartbeat and getattr(self,'input_clicks',0)==clicks:
     self.audio.load('click','SFX_BUTTON_CLICK.caf');self.audio.start('click')
    self.dialog_candidate=None;self.dialog_stable_ticks=0;return True
  if key=='down' and self.get('ActionSceneIndex')!=-1 and self.string(self.get('ActionButtonImage')&0xffffffff)=='HEART_RATE_BTTN.png':
   self.audio.load('click','SFX_BUTTON_DISABLED.caf');self.audio.start('click')
  return False
 def skip_heard(self):
  if self.interactive_challenge():self.skip_repeated=False;return False
  if Path(self.audio.loaded.get('fg','')).stem=='C02_FX_000':return False
  # Space keeps its original puzzle/action meaning whenever that button exists.
  if any(k=='space' for k,_,_ in self.options()):return False
  img=self.string(self.get('ActionButtonImage')&0xffffffff)
  if self.get('ActionSceneIndex')!=-1 and (img=='SWORD_CENTER_BTTN.png' or (self.chapter==23 and img=='SHELLGAME_BUTTON.png')):return False
  name=self.audio.loaded.get('fg')
  if not self.audio.busy('fg') or not (self.replay_chapter or name in self.heard_tracks or self.repeated_topic):return False
  self.call('SkipButtonAction:',0);self.skip_repeated=True
  return True
 def topic_id(self,option):
  key,label,_=option
  word=['One','Two','Three','Four','Five'][int(key)-1]
  return json.dumps([self.chapter,self.location,label,self.get('DialogLine'+word+'Index')])
 def topic_label(self,option):
  asked=self.topic_id(option) in self.asked_topics
  # Chapter 14 already records these answers in original saves, including
  # saves made before the Windows accessibility annotations existed.
  if self.chapter==14:
   flag={'Ask why he haunts the beach.':'askedHaunts','Ask about the Lonzi crash.':'askedCrash',
         'Ask him if he remembers Ollie.':'askedOllie','Ask him about Donna.':'askedDonna',
         "Tell him it's time to move on.":'askedMoveOn','Ask if he has other regrets.':'askedRegrets'}.get(option[1])
   if flag:asked=asked or bool(self.get(flag))
  return ('Already selected. ' if asked else '')+option[1]
 def safe_active(self):
  return self.chapter==4 and (self.get('SceneIndex') in (1400,1401) or 2000<=self.get('SceneIndex')<=2300)
 def instructions(self):
  # Radio dialogue belongs to its tuned frequency, not the repeat prompt.
  if self.chapter in (4,7,15) and self.string(self.get('ActionButtonImage')&0xffffffff)=='FREQUENCY_BTTN.png':return []
  if self.chapter==4 and self.get('ActionSceneIndex')!=-1 and self.string(self.get('ActionButtonImage')&0xffffffff)=='GET_CRYSTAL_BTTN.png':
   table=self.objects.get(self.get('CrystalSounds'),[]);target=self.get('targetCrystal')
   if isinstance(table,list) and 0<=target<len(table):
    item=table[target];entry=self.objects.get(item)
    name=self.string(entry['FileName'] if isinstance(entry,dict) and 'FileName' in entry else item)
    if name:return [name if name.endswith('.caf') else name+'.caf']
  if self.chapter==13 and self.get('SceneIndex') in (21,40,41,50,51,60,61) and self.beach_instructions:return list(self.beach_instructions)
  if self.safe_active() and self.get('RandIntFound') and self.get('CrystalSounds'):
   table=self.objects[self.get('CrystalSounds')]
   digits=[self.get(n)+offset for n,offset in [('SafeFirstDigit',0),('SafeSecondDigit',2),('SafeThirdDigit',0),('SafeFourthDigit',2)]]
   return ['C04_0020.caf']+[self.string(self.objects[table[i]]['FileName'])+'.caf' for i in digits]+['C04_0029.caf']
  # Repeat only an interactive directional prompt, never the narration history
  # or a conversation topic. The safe has its own multi-recording prompt above.
  options=self.options()
  if any(key.isdigit() for key,_,_ in options):return []
  if not any(key in ('up','down','left','right') for key,_,_ in options):return []
  return list(self.prompt_tracks)
 def navigation_hint(self):
  # These Chapter 16 hubs have no recurring recorded navigation prompt while
  # Agnes is present. Describe only exits verified in the original script.
  if self.chapter!=16 or self.get('SceneIndex') not in (50,60,70):return ''
  if self.get('AgnesInSacricitry') or self.audio.busy('fg'):return ''
  options=self.options();parts=[]
  destinations={50:'Nave',60:'Church altar',70:'Church organ bay'}
  for key,_,method in options:
   field={'LeftAction:':'LeftSceneIndex','RightAction:':'RightSceneIndex','ReleaseButtonAction:':'ReleaseSceneIndex'}.get(method)
   if not field:continue
   target=self.get(field)
   if method=='ReleaseButtonAction:':label='attempt to release Ollie'
   elif target in destinations:label=destinations[target]
   elif target in (61,71):label='check the passage in that direction'
   else:continue
   parts.append(key.title()+': '+label+'.')
  if not parts:return ''
  # At the organ bay the original waits 150 ticks before Agnes's scene.
  # Leaving or checking the locked door resets that waiting period.
  waiting=' Stay here and wait a few moments for the next scene before moving or trying to release Ollie.' if self.get('SceneIndex')==70 else ''
  return self.location+'. '+' '.join(parts)+waiting+' Press Tab to repeat these directions.'
 def snapshot(self):
  import base64
  keys=['chapter','now','done','title','location','buttons','enabled','organ','heap','objects','intern','timers','effects','next_effect','repeat_tracks','prompt_tracks','prompt_variants','fade_flags']
  keys+=['checkpoint_locked']
  keys+=['beach_instructions','lock_scene','recording_choices','recording_scene','replay_chapter','beach_pending_item','beach_bonus_added','asked_topics','pending_topic','topic_left_menu','heard_tracks','listening_track','repeated_topic']
  state={k:getattr(self,k) for k in keys};state['format']=1;state['rng']=self.rng.getstate();state['memory']=base64.b64encode(bytes(self.u.mem_read(0,0x500000))).decode();state['audio']=self.audio.snapshot();return state
 def restore(self,state):
  import base64
  if state.get('format')!=1 or state['chapter']!=self.chapter:raise ValueError('Incompatible save')
  mem=base64.b64decode(state['memory'],validate=True)
  if len(mem)!=0x500000:raise ValueError('Invalid save memory')
  self.u.mem_write(0,mem);self.apply_script_patches()
  for k in ['now','done','title','location','buttons','enabled','organ','heap','intern','next_effect']:setattr(self,k,state[k])
  self.audio.scene_location=self.location
  if self.chapter==9 and self.get('SceneIndex')!=71:self.organ=False
  self.checkpoint_locked=state.get('checkpoint_locked',False)
  self.recording_choices=state.get('recording_choices',{});self.recording_scene=state.get('recording_scene');self.beach_instructions=state.get('beach_instructions',[]);self.lock_scene=state.get('lock_scene');self.lock_on_ready=self.audio.busy('lock-on')
  for k in ['objects','timers','effects']:setattr(self,k,{int(a):v for a,v in state[k].items()})
  if self.safe_active() and self.get('CrystalSounds'):
   table=self.objects.get(self.get('CrystalSounds'))
   if not isinstance(table,list) or any(not isinstance(self.objects.get(item),dict) or 'FileName' not in self.objects[item] for item in table):
    raise ValueError('Legacy safe save has an invalid recording table; use Continue or a newer save.')
  def tup(v):return tuple(tup(x) for x in v) if isinstance(v,list) else v
  self.rng.setstate(tup(state['rng']));self.audio.restore(state['audio']);self.update_detector_bearing();self.stop_departed_trap_ambience()
  self.dialog_candidate=None;self.dialog_stable_ticks=0
  self.repeat_tracks=state.get('repeat_tracks',[]);self.prompt_tracks=state.get('prompt_tracks',[])
  self.prompt_variants=state.get('prompt_variants',list(self.prompt_tracks))
  self.fade_flags=dict(state.get('fade_flags',{}))
  for q in ('bg','bg2'):
   if self.fade_flags.get(q+'In') and self.fade_flags.get(q+'Out'):
    current=Path(self.string(self.get('CurrentBackground')&0xffffffff)).stem
    keep_in=Path(self.audio.loaded.get(q,'')).stem==current
    self.fade_flags[q+('Out' if keep_in else 'In')]=False
  self.replay_chapter=state.get('replay_chapter',False)
  self.beach_pending_item=state.get('beach_pending_item')
  self.beach_bonus_added=state.get('beach_bonus_added',False)
  self.asked_topics=list(state.get('asked_topics',[]));self.pending_topic=state.get('pending_topic');self.topic_left_menu=state.get('topic_left_menu',False)
  self.heard_tracks=list(state.get('heard_tracks',[]));self.listening_track=state.get('listening_track');self.repeated_topic=state.get('repeated_topic',False);self.skip_repeated=False
