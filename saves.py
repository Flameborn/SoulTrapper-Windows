import gzip,json,os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
class Saves:
 def __init__(self,root=None):
  portable=Path(__file__).resolve().parent.parent
  self.root=Path(root) if root else (portable/'saves' if Path(__file__).resolve().parent.name=='_internal' or (portable/'portable.txt').is_file() else Path(os.environ.get('LOCALAPPDATA',Path.home()))/'SoulTrapperWindows')
  self.root.mkdir(parents=True,exist_ok=True)
  self.writer=ThreadPoolExecutor(max_workers=1,thread_name_prefix='save');self.pending=[]
 def path(self,slot='continue'):return self.root/(slot+'.json.gz')
 def exists(self,slot='continue'):return self.path(slot).is_file()
 def write(self,engine,slot='continue',background=False):
  self.check_pending()
  state=dict((getattr(engine,'chapter_start',None) if slot in ('continue','chapter-start') else getattr(engine,'checkpoint',None)) or engine.snapshot())
  # Listening history is player knowledge even if Continue replays an earlier
  # scene checkpoint. Keep it without advancing the saved gameplay state.
  for key in ('heard_tracks','asked_topics'):
   state[key]=list(dict.fromkeys(state.get(key,[])+getattr(engine,key,[])))
  # Checkpoints are replaced, never mutated. Capture all live engine fields
  # here; the worker must not access the emulator or audio devices.
  future=self.writer.submit(self._write,state,slot,engine.chapter,engine.done)
  if background:self.pending.append(future)
  else:future.result()
 def _write(self,state,slot,chapter,done):
  p=self.path(slot);tmp=p.with_suffix('.tmp')
  with gzip.open(tmp,'wt',encoding='utf8',compresslevel=3) as f:json.dump(state,f,separators=(',',':'))
  os.replace(tmp,p)
  progress=self._progress();progress['unlocked']=max(progress.get('unlocked',1),chapter)
  if done:progress['completed']=sorted(set(progress.get('completed',[]))|{chapter})
  t=self.root/'progress.tmp';t.write_text(json.dumps(progress));os.replace(t,self.root/'progress.json')
 def read(self,slot='continue'):
  self.flush()
  with gzip.open(self.path(slot),'rt',encoding='utf8') as f:return json.load(f)
 def progress(self):
  self.flush()
  return self._progress()
 def _progress(self):
  try:return json.loads((self.root/'progress.json').read_text())
  except (OSError,ValueError):return {'unlocked':1}
 def check_pending(self):
  while self.pending and self.pending[0].done():self.pending.pop(0).result()
 def flush(self):
  while self.pending:self.pending.pop(0).result()
 def close(self):
  try:self.flush()
  finally:self.writer.shutdown(wait=True)
