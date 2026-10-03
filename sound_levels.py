"""Conservative PCM headroom adjustment for quiet original recordings."""
import audioop
from pathlib import Path

def enhance(name, pcm):
    stem=Path(name).stem
    if stem in {f'C19_FX_{i:03}' for i in range(8)}:
        peak=audioop.max(pcm,2)
        return audioop.mul(pcm,2,min(1.6,32000/max(1,peak)))
    if '_BG_' in stem:
        # Fixed per-recording gain preserves dynamics, stereo and authored fades.
        # Leave louder ambiences (including the apartment) at their original level.
        rms=audioop.rms(pcm,2);peak=audioop.max(pcm,2)
        gain=max(1.,min(4.,400/max(1,rms),30000/max(1,peak)))
        if gain>1.:return audioop.mul(pcm,2,gain)
    return pcm
