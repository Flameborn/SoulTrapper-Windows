import gzip,json,os
from pathlib import Path
class Saves:
 def __init__(self,root=None):
  portable=Path(__file__).resolve().parent.parent
  self.root=Path(root) if root else (portable/'saves' if Path(__file__).resolve().parent.name=='_internal' or (portable/'portable.txt').is_file() else Path(os.environ.get('LOCALAPPDATA',Path.home()))/'SoulTrapperWindows')
  self.root.mkdir(parents=True,exist_ok=True)
 def path(self,slot='continue'):return self.root/(slot+'.json.gz')
 def exists(self,slot='continue'):return self.path(slot).is_file()
 def write(self,engine,slot='continue'):
  p=self.path(slot);tmp=p.with_suffix('.tmp')
  state=dict((getattr(engine,'chapter_start',None) if slot in ('continue','chapter-start') else getattr(engine,'checkpoint',None)) or engine.snapshot())
  # Listening history is player knowledge even if Continue replays an earlier
  # scene checkpoint. Keep it without advancing the saved gameplay state.
  for key in ('heard_tracks','asked_topics'):
   state[key]=list(dict.fromkeys(state.get(key,[])+getattr(engine,key,[])))
  with gzip.open(tmp,'wt',encoding='utf8',compresslevel=3) as f:json.dump(state,f,separators=(',',':'))
  os.replace(tmp,p)
  progress=self.progress();progress['unlocked']=max(progress.get('unlocked',1),engine.chapter)
  if engine.done:progress['completed']=sorted(set(progress.get('completed',[]))|{engine.chapter})
  t=self.root/'progress.tmp';t.write_text(json.dumps(progress));os.replace(t,self.root/'progress.json')
 def read(self,slot='continue'):
  with gzip.open(self.path(slot),'rt',encoding='utf8') as f:return json.load(f)
 def progress(self):
  try:return json.loads((self.root/'progress.json').read_text())
  except (OSError,ValueError):return {'unlocked':1}
