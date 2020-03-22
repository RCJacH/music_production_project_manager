import os
import shutil

from music_production_project_manager.audio_file_handler import AudioFile
from music_production_project_manager.utils import lazy_property

extensions = [".wav", ".wave"]
"""
Potential additions supported by PySoundFile library
{'AIFF': 'AIFF (Apple/SGI)',
 'AU': 'AU (Sun/NeXT)',
 'AVR': 'AVR (Audio Visual Research)',
 'CAF': 'CAF (Apple Core Audio File)',
 'FLAC': 'FLAC (FLAC Lossless Audio Codec)',
 'HTK': 'HTK (HMM Tool Kit)',
 'IRCAM': 'SF (Berkeley/IRCAM/CARL)',
 'MAT4': 'MAT4 (GNU Octave 2.0 / Matlab 4.2)',
 'MAT5': 'MAT5 (GNU Octave 2.1 / Matlab 5.0)',
 'MPC2K': 'MPC (Akai MPC 2k)',
 'NIST': 'WAV (NIST Sphere)',
 'OGG': 'OGG (OGG Container format)',
 'PAF': 'PAF (Ensoniq PARIS)',
 'PVF': 'PVF (Portable Voice Format)',
 'RAW': 'RAW (header-less)',
 'RF64': 'RF64 (RIFF 64)',
 'SD2': 'SD2 (Sound Designer II)',
 'SDS': 'SDS (Midi Sample Dump Standard)',
 'SVX': 'IFF (Amiga IFF/SVX8/SV16)',
 'VOC': 'VOC (Creative Labs)',
 'W64': 'W64 (SoundFoundry WAVE 64)',
 'WAV': 'WAV (Microsoft)',
 'WAVEX': 'WAVEX (Microsoft)',
 'WVE': 'WVE (Psion Series 3)',
 'XI': 'XI (FastTracker 2)'}
"""


def _iterate_files(folder):
    return (os.path.join(folder, f) for f in _list_audio_files(folder))


def _create_analysis(filepath, options):
    return AudioFile(
        filepath,
        null_threshold=options["null_threshold"],
        empty_threshold=options["empty_threshold"],
    )


def _list_audio_files(folder):
    return (f for f in os.listdir(folder) if _is_audio_file(f))


def _is_audio_file(file):
    _, file_extension = os.path.splitext(file)
    return file_extension.upper() in (name.upper() for name in extensions)


class FileList:
    def __init__(self, folder=None, options=None):
        self._options = options or {
            "backup": True,
            "delimiter": ".",
            "null_threshold": -100,
            "empty_threshold": -100,
        }
        self._files = []
        self._joinlists = None
        self._flat_joinlists = None
        self._folderpath = ""
        self.folderpath = folder

    def __enter__(self):
        return self

    def __exit__(self, *args):
        del self

    def __iter__(self):
        return iter(self.files)

    def __len__(self):
        return len(self.files) if self._folderpath != "" else 0

    def __getitem__(self, key):
        return self.files[key]

    @lazy_property
    def files(self):
        self._files = [x for x in self._search_folder(self._folderpath)]
        return self._files

    @lazy_property
    def joinlists(self):
        self._joinlists = self._search_for_join()
        return self._joinlists

    @lazy_property
    def flat_joinlists(self):
        self._flat_joinlist = [y for x in self.joinlists for y in x]
        return self._flat_joinlist

    basenames = property(lambda self: [f.basename for f in self.files])
    filenames = property(lambda self: [f.filename for f in self.files])

    filepaths = property(lambda self: [f.filepath for f in self.files])

    empty_files = property(lambda self: [f for f in self.files if f.isEmpty])

    fake_stereo_files = property(lambda self: [f for f in self.files if f.isFakeStereo])

    multichannel_files = property(
        lambda self: [f for f in self.files if f.isMultichannel]
    )

    options = property(lambda self: dict(self._options))

    @property
    def folderpath(self):
        return self._folderpath

    @folderpath.setter
    def folderpath(self, folder):
        if folder and os.path.exists(folder):
            self._files = []
            self._folderpath = folder

    def update_options(self, options={}):
        self._options.update(options)

    def _search_folder(self, folder):
        return (_create_analysis(f, self._options) for f in _iterate_files(folder))

    def proceed(self):
        if self.options.pop("backup", True):
            self.backup(**self.options.pop("backup_options", {}))
        for f in self:
            options = self.options
            if f in self.flat_joinlists:
                o = self._get_join_options(f)
                f.action = "J" if o.pop("first") else "N"
                options.update({"join_options": o})
            f.proceed(options=options)
        self.folderpath = self.folderpath

    def backup(self, folder="bak", newFolder=True, read_only=False):
        def join(*args, inc="", ext=""):
            return (
                os.path.join(*args).rstrip("\\")
                + (inc if inc != "0" else "")
                + (ext if ext else "")
            )

        def unique(*args, new=False, **kwargs):
            if not new:
                return join(*args, **kwargs)
            name = ""
            i = 0
            while os.path.exists(name := join(*args, inc=str(i), **kwargs)):
                i += 1
            return name

        def backup(file):
            newfile = unique(folderpath, file.filename, new=False, ext=file.extension)
            return file.backup(newfile, read_only=read_only)

        bakpath, bakfolder = os.path.split(folder)
        path = self.folderpath if (not bakpath or bakpath.isspace) else bakpath
        folderpath = unique(path, bakfolder, new=newFolder)

        return [backup(f) for f in self.files]

    def _get_join_options(self, f):
        base, ch = f.filename.rsplit(self.options.pop("delimiter", "."), 1)
        l = self.joinlists[base]
        i = l.index(f.filepath)
        if i == 0:
            return {"first": True, "others": l[1:], "newfile": base}
        else:
            return {"first": False}

    def _search_for_join(self):
        if len(self) <= 1:
            return {}

        d = {}
        for f in self:
            if not f.channelnum:
                continue
            flat_d = [y for x in d for y in x]
            if f in flat_d:
                continue
            base = f.filebase
            ch = f.channelnum
            try:
                if ch in [v[1] for v in d[base]]:
                    continue
            except KeyError:
                d[base] = list()
            d[base].append((f, ch))
        return {
            k: (x[0] for x in sorted(v, key=lambda y: y[1]))
            for k, v in d.items()
            if len(v) > 1
        }
