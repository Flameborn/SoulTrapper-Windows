"""Local-only error reports. Reports are never uploaded automatically."""
import os, platform, sys, traceback
from datetime import datetime, timezone
from pathlib import Path

def write_error(context=''):
 root=Path(__file__).resolve().parent
 if root.name=='_internal':root=root.parent
 text=('Soul Trapper 1.0\n'+datetime.now(timezone.utc).isoformat()+'\n'
       +platform.platform()+'\nPython '+sys.version+'\n'+context+'\n'+traceback.format_exc())
 for folder in (root,Path(os.environ.get('LOCALAPPDATA',str(root)))/'SoulTrapperWindows'):
  try:
   folder.mkdir(parents=True,exist_ok=True)
   target=folder/'error.log'
   with target.open('a',encoding='utf8') as f:f.write('\n'+text+'\n')
   return target
  except OSError:continue
 return None
