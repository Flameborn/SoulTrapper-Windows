"""Direct NVDA Controller Client, with optional Windows SAPI fallback."""
import ctypes
from pathlib import Path


class Speech:
    def __init__(self, root, silent=False):
        self.last = ''
        self.silent = silent
        self.nvda = None
        self.voice = None
        if silent:
            return
        try:
            self.nvda = ctypes.WinDLL(str(Path(root)/'vendor'/'nvdaControllerClient64.dll'))
            for name in ('speakText', 'brailleMessage'):
                fn = getattr(self.nvda, 'nvdaController_'+name)
                fn.argtypes = [ctypes.c_wchar_p]
                fn.restype = ctypes.c_ulong
            for name in ('testIfRunning', 'cancelSpeech'):
                fn = getattr(self.nvda, 'nvdaController_'+name)
                fn.argtypes = []
                fn.restype = ctypes.c_ulong
        except (OSError, AttributeError):
            self.nvda = None
        try:
            import comtypes.client
            self.voice = comtypes.client.CreateObject('SAPI.SpVoice')
            voices = self.voice.GetVoices()
            for index in range(voices.Count):
                voice = voices.Item(index)
                if '409' in voice.GetAttribute('Language').split(';'):
                    self.voice.Voice = voice
                    break
        except Exception:
            pass

    def say(self, text):
        self.last = text
        if self.silent:
            return
        try:
            if self.nvda and self.nvda.nvdaController_testIfRunning() == 0:
                if self.voice:
                    self.voice.Speak('', 3)
                self.nvda.nvdaController_cancelSpeech()
                if self.nvda.nvdaController_speakText(text) == 0:
                    self.nvda.nvdaController_brailleMessage(text)
                    return
        except OSError:
            pass
        if self.voice:
            self.voice.Speak(text, 3)

    def stop(self):
        if self.nvda and self.nvda.nvdaController_testIfRunning() == 0:
            self.nvda.nvdaController_cancelSpeech()
        if self.voice:
            self.voice.Speak('', 3)
