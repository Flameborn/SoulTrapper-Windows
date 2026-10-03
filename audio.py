"""Stereo original recordings, independent queues, deterministic resume offsets."""
from pathlib import Path
from collections import OrderedDict
import pygame,math
from sound_levels import enhance
class Audio:
 def __init__(self,root):
  self.root=Path(root)/'assets';self.volumes={};self.loaded={};self.active={};self.channels={};self.cache=OrderedDict();self.cache_bytes=0;self.now=0.;self.master=1.;self.spatial=None;self.effect_defs={};self.spatial_error=None
  import os
  if os.environ.get("SDL_AUDIODRIVER")!="dummy":
   try:
    from spatial_audio import SpatialAudio
    self.spatial=SpatialAudio(root)
   except Exception as e:self.spatial_error=str(e)
  pygame.mixer.set_num_channels(64)
 def resolve(self,name):
  p=self.root/Path(name).name
  candidates=[p]
  if p.suffix.lower()=='.caf':
   candidates=[p.with_suffix('.ogg'),p.with_suffix('.wav'),p.with_suffix('.mp3')]
  for candidate in candidates:
   if candidate.is_file(): return candidate
  return candidates[0]
 def exists(self,name):return self.resolve(name).is_file()
 def channel(self,q):
  if q not in self.channels:
   if len(self.channels)>=64:raise RuntimeError('Too many audio sources')
   self.channels[q]=pygame.mixer.Channel(len(self.channels))
  return self.channels[q]
 def sound(self,name):
  p=self.resolve(name);key=p.name
  if key in self.cache:self.cache.move_to_end(key);return self.cache[key]
  s=pygame.mixer.Sound(str(p))
  if '_BG_' in p.stem or p.stem in {f'C19_FX_{i:03}' for i in range(8)}:s=pygame.mixer.Sound(buffer=enhance(name,s.get_raw()))
  self.cache[key]=s;self.cache_bytes+=int(s.get_length()*44100*4)
  while self.cache_bytes>90_000_000 and len(self.cache)>1:
   _,old=self.cache.popitem(last=False);self.cache_bytes-=int(old.get_length()*44100*4)
  return s
 def load(self,q,name):self.stop(q);self.loaded[q]=name
 def start(self,q,loop=False,offset=0.):
  if q not in self.loaded:return
  name=self.loaded[q];sound=self.sound(name);length=sound.get_length()
  if offset>=length:
   if loop:offset%=length
   else:return
  play=sound
  if offset>0:
   raw=sound.get_raw();play=pygame.mixer.Sound(buffer=raw[int(offset*44100)*4:])
  c=self.channel(q);c.play(play,loops=-1 if loop and offset==0 else 0)
  self.active[q]={'name':name,'loop':loop,'start':self.now-offset,'length':length,'partial':bool(loop and offset>0),'pos':None}
  self.volume(q,self.volumes.get(q,1.))
 def busy(self,q):
  if self.spatial and q.startswith('e') and q in self.spatial.sources:return self.spatial.busy(q)
  return self.channel(q).get_busy()
 def stop(self,q):
  if self.spatial:self.spatial.stop(q)
  if q in self.channels:self.channels[q].stop()
  self.active.pop(q,None)
 def preserve_tail(self,q):
  tail=q+'-tail';self.stop(tail)
  # Transfer the playing channel itself, preserving the exact sample position.
  spare=self.channel(tail);self.channels[tail]=self.channel(q);self.channels[q]=spare
  if q in self.active:self.active[tail]=self.active.pop(q)
  self.loaded[tail]=self.loaded[q];self.volumes[tail]=self.volumes.get(q,1.)
 def output_gain(self,q):
  name=self.effect_defs.get(q,{}).get('name',self.loaded.get(q,''))
  boost=2. if name in {f'C19_FX_{i:03}.caf' for i in range(8)} else 1.
  if q in ('bg','bg2') and '_BG_' in name:
   location=getattr(self,'scene_location','')
   if location in ('Soul Trap','Inside the Soul Trap'):boost=1.6
   elif location and location!="Kane's Apartment":boost=1.15
  return self.master*min(1.,self.volumes.get(q,1.)*boost)
 def volume(self,q,v):
  self.volumes[q]=max(0.,v)
  if self.spatial and q in self.spatial.sources:
   if q in self.spatial.sources:self.spatial.lib.alSourcef(self.spatial.sources[q],0x100A,self.output_gain(q))
   return
  self.channel(q).set_volume(self.output_gain(q))
  a=self.active.get(q)
  if a and a['pos'] is not None:self.position(int(q[1:]),a['pos'])
 def position(self,i,pos):
  q='e'+str(i)
  if q in self.effect_defs:self.effect_defs[q]['pos']=pos
  if q in self.active:self.active[q]['pos']=pos
  if self.spatial and q in self.spatial.sources:self.spatial.move(q,pos);return
  x,y,z=pos;pan=max(-1,min(1,x/(abs(z)+1)));g=self.output_gain(q)
  # Original stereo story recordings remain untouched; only original mono effects are panned.
  self.channel(q).set_volume(g*math.sqrt((1-pan)/2),g*math.sqrt((1+pan)/2))
 def effect(self,i,e):
  q='e'+str(i);self.effect_defs[q]=dict(e);self.volumes[q]=e['gain'];path=self.resolve(e['name']).with_suffix('.wav')
  if self.spatial and path.exists():
   attack=self.resolve(e['attack']).with_suffix('.wav') if e.get('attack') else None
   self.effect_defs[q]=dict(e);self.spatial.load(e['name'],path,attack);self.spatial.play(q,e['name'],e['pos'],self.output_gain(q),e['loop'])
   self.active[q]={'name':e['name'],'loop':e['loop'],'start':self.now,'length':0,'partial':False,'pos':e['pos']};self.volumes[q]=e['gain']
  else:
   self.load(q,e['name']);self.volume(q,e['gain']);self.start(q,e['loop']);self.position(i,e['pos'])
 def tick(self,dt):
  self.now+=dt
  for q,a in list(self.active.items()):
   if not self.busy(q):
    if a['partial']:self.start(q,True)
    else:self.active.pop(q,None)
 def pause(self):
  pygame.mixer.pause()
  if self.spatial:self.spatial.pause()
 def resume(self):
  pygame.mixer.unpause()
  if self.spatial:self.spatial.resume()
 def stop_all(self):
  pygame.mixer.stop();self.active.clear()
  if self.spatial:
   for q in self.spatial.sources:self.spatial.stop(q)
 def snapshot(self):return {'volumes':{q:v for q,v in self.volumes.items() if q!='menu'},'loaded':{q:v for q,v in self.loaded.items() if q!='menu'},'effects':self.effect_defs,'master':self.master,'active':{q:{**a,'offset':self.spatial.offset(q) if self.spatial and q in self.effect_defs else max(0,self.now-a['start'])} for q,a in self.active.items() if q!='menu' and self.busy(q)}}
 def restore(self,s):
  self.stop_all();self.volumes={q:v for q,v in s['volumes'].items() if q!='menu'};self.loaded={q:v for q,v in s['loaded'].items() if q!='menu'}
  for q,a in s['active'].items():
   if q=='menu':continue
   if q in s.get('effects',{}):
    self.effect(int(q[1:]),s['effects'][q])
    if self.spatial:self.spatial.seek(q,a['offset'])
   else:self.start(q,a['loop'],a['offset'])
   if a['pos'] is not None:self.position(int(q[1:]),a['pos'])
