"""
Tests for 'analyze' module
"""
import os
import shutil

import numpy as np
import pytest

from soundfile import SoundFile as sf
from soundfile import read

from mppm import AudioFile


def get_audio_path(name="", ext=".wav"):
    return os.path.join("tests", "audio_files", name + ext)


@pytest.fixture(scope="function")
def tmp_file(request, tmp_path):
    try:
        filename = request.param
    except AttributeError:
        filename = "sin-m"
    testfile = get_audio_path(filename)
    file = os.path.join(tmp_path, os.path.split(testfile)[1])
    shutil.copyfile(testfile, file)
    yield (file, testfile)


class AudioInfo(object):
    def __init__(self, shape):
        self.shape = shape
        self.filepath = get_audio_path(shape)
        self.src = AudioFile(self.filepath)
        self.channels = 1 if "-m" in shape else 2
        self.isCorrelated = False if ("+" in shape or "100" in shape) else True
        self.isEmpty = shape[0] == "0"
        self.isMono = self.channels == 1 and not self.isEmpty
        self.validChannel = (
            0 if "0-" in shape else 3 if "+" in shape else 2 if "r" in shape else 1
        )
        self.flag = (
            0 if self.isEmpty else 1 if "-m" in shape else 2 if "-r100" in shape else 3
        )
        self.isFakeStereo = not (self.isEmpty or "+" in shape) and self.channels == 2
        self.isMultichannel = shape[-1] == "n" or shape.count("+") > 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        del self.src


@pytest.fixture(
    params=["sin-m", "sin-s", "0-m", "0-s", "sin+tri", "sin-l50", "sin-r25", "sin-r100"]
)
def audioinfo(request):
    with AudioInfo(request.param) as info:
        yield info


class TestAudioFile:
    @pytest.fixture(
        params=[
            "flag",
            "isCorrelated",
            "validChannel",
            "channels",
            "isMono",
            "isEmpty",
            "isFakeStereo",
            "isMultichannel",
        ]
    )
    def each_attribute(self, request, audioinfo):
        yield [getattr(x, request.param) for x in (audioinfo.src, audioinfo)]

    def test_analyze(self, each_attribute):
        assert each_attribute[0] == each_attribute[1]

    def test_empty_file(self):
        with AudioFile(get_audio_path("empty")) as src:
            assert src.flag == None
            assert src.isCorrelated == None
            assert src.isMono == False
            assert src.isFakeStereo == False
            assert src.isMultichannel == False

    def test__enter__exit(self):
        with AudioFile(get_audio_path("empty")) as obj:
            assert obj.file is not None
            assert obj.channels == 1
        assert obj.file is None
        assert obj.channels == 1
        with AudioFile() as obj:
            assert obj.file == None
        obj = AudioFile(get_audio_path("empty"), analyze=False)
        assert obj.file == None
        with AudioFile(get_audio_path("empty"), analyze=False) as obj:
            assert obj.file

    @pytest.mark.parametrize(
        "filename, othernames",
        [
            pytest.param("sin", [".wav", "sin", ""], id="NoDot"),
            pytest.param("sin.R", [".wav", "sin", "2"], id="OneDot"),
            pytest.param("sin.wave.R", [".wav", "sin.wave", "2"], id="MultiDots"),
            pytest.param("sin.wave", [".wav", "sin.wave", ""], id="InvalidDot"),
        ],
    )
    def test_file_names(self, filename, othernames):
        filepath = get_audio_path(filename)
        dirname, basename = os.path.split(filepath)
        extension = othernames[0]
        filebase = othernames[1]
        channelnum = othernames[2]
        with AudioFile(filepath, analyze=False) as obj:
            assert obj.filepath == filepath
            assert obj.dirname == dirname
            assert obj.basename == basename
            assert obj.filename == filename
            assert obj.extension == extension
            assert obj.root == filepath[:-4]
            assert obj.filebase == filebase
            assert obj.channelnum == channelnum

    def test__eq__(self):
        filepath = get_audio_path("empty")
        with AudioFile(filepath) as obj, AudioFile(filepath) as obj2:
            assert obj == obj2

    def test_file_setter_error(self):
        obj = AudioFile("error")
        assert not os.path.exists("error")
        assert obj.filepath == "error"
        assert obj.file == None

    def test_action(self):
        def setter(obj, x):
            obj.action = x
            return obj._action

        def getter(obj, x):
            obj.action = x
            return obj.action

        with AudioFile(get_audio_path("empty")) as obj:
            assert all(setter(obj, x) == x for x in "MRSJD")
            assert not any(setter(obj, x) == x for x in "ABCE")
            a = {
                "D": "Default",
                "M": "Monoize",
                "R": "Remove",
                "S": "Split",
                "J": "Join",
            }
            assert all(getter(obj, x) == a[x] for x in "MRSJD")
            assert getter(obj, "#") == a["D"]  # No assignment

    @pytest.mark.parametrize(
        "file, options, result",
        [
            ("0-s", {}, "R"),
            ("0-s", {"remove": False}, "N"),
            ("sin-s", {}, "M"),
            ("sin-s", {"monoize": False}, "N"),
            ("sin.L", {"join_files": ["1"]}, "J"),
            ("sin.L", {"join": False, "join_file": True}, "N"),
        ],
    )
    def test_analyze_actions(self, file, options, result):
        with AudioFile(get_audio_path(file)) as af:
            af.join_files = options.pop("join_files", [])
            assert af.default_action(options) == result

    @pytest.mark.parametrize(
        "options, func",
        [
            ({"action": "M"}, "monoize"),
            ({"action": "R"}, "remove"),
            ({"action": "S"}, "split"),
            ({"action": "J"}, "join"),
            ({"action": "S", "delimiter": "-"}, "split"),
        ],
    )
    def test_proceed(self, mocker, options, func):
        with AudioFile("empty") as obj:
            setattr(obj, func, mocker.Mock())
            if "action" in options:
                obj.action = options.pop("action")
            if "delimiter" in options:
                obj.update_options({"delimiter": options.pop("delimiter")})
            obj.proceed(options=options)
            if not options:
                getattr(obj, func).assert_called()
            else:
                getattr(obj, func).assert_called_with(**options)

    def test_proceed_read_only(self, mocker):
        with AudioFile("empty") as obj:
            assert obj.proceed(options={"read_only": True}) == "None"
            obj.action = "M"
            obj.monoize = mocker.Mock()
            assert obj.proceed(options={"read_only": True}) == "Monoize"
            assert not obj.monoize.called

    def test_backup(self, tmp_file):
        file, testfile = tmp_file
        filename = os.path.split(testfile)[1]
        tmppath = os.path.split(file)[0]
        bakpath = os.path.join(tmppath, "bak")
        bakfile = os.path.join(bakpath, filename)
        with AudioFile(file) as obj:
            assert obj.backup(bakfile, read_only=True) == bakfile
            assert not os.path.exists(bakfile)
            assert obj.backup(bakfile) == bakfile
            assert os.path.exists(bakfile)

    @pytest.mark.parametrize(
        "tmp_file, params, result",
        [
            ("sin-s", {}, True),
            ("sin+tri", {}, True),
            ("sin+tri", {"channel": 1}, False),
        ],
        indirect=["tmp_file"],
    )
    def test_monoize(self, tmp_file, params, result):
        file, testfile = tmp_file
        with AudioFile(filepath=file) as obj:
            obj.monoize(**params)
            assert (
                np.all(
                    np.equal(
                        read(testfile, always_2d=True)[0],
                        list(obj.read(always_2d=True)),
                    )
                )
                == result
            )

    @pytest.mark.parametrize(
        "tmp_file, params, result",
        [
            ("empty", {}, False),
            ("0-s", {}, False),
            ("sin-m", {}, True),
            ("sin-m", {"forced": True}, False),
        ],
        indirect=["tmp_file"],
    )
    def test_remove(self, tmp_file, params, result):
        file, _ = tmp_file
        with AudioFile(filepath=file) as obj:
            obj.remove(**params)
        assert os.path.exists(file) == result

    @pytest.mark.parametrize(
        "tmp_file, params, isSplit",
        [("sin-s", {}, True), ("sin-m", {}, False), ("empty", {}, False)],
        indirect=["tmp_file"],
    )
    def test_split(self, tmp_file, params, isSplit):
        file = tmp_file[0]
        _, filename = os.path.split(file)
        path, ext = os.path.splitext(file)
        with AudioFile(filepath=file) as obj:
            obj.split(**params)
        assert os.path.exists(file) != isSplit
        for ch in (".L", ".R"):
            assert os.path.exists(path + ch + ext) == isSplit

    @pytest.mark.parametrize(
        "params, result",
        [
            ({"delimiter": ".", "chFlag": 3}, True),
            ({"delimiter": ".", "chFlag": 3, "chSelect": "R"}, True),
            ({"delimiter": ".", "chFlag": 2, "chSelect": "R"}, False),
            ({"delimiter": "_", "chFlag": 3,}, True),
            ({"delimiter": ".", "chFlag": 1}, False),
        ],
    )
    def test_join_old(self, params, result, tmp_file):
        file, testfile = tmp_file
        path, ext = os.path.splitext(file)
        basename = path + params.pop("delimiter")
        chFlag = params.pop("chFlag") if "chFlag" in params else 0
        for i, v in enumerate(bin(chFlag)[-1:1:-1]):
            if v == "1":
                shutil.copyfile(file, basename + ["L", "R"][i] + ext)
        os.remove(file)
        assert not os.path.exists(file)
        chSelect = (
            params.pop("chSelect")
            if "chSelect" in params
            else (1 if chFlag > 3 else "L")
        )
        with AudioFile(filepath=basename + chSelect + ext) as obj:
            obj.join_old(**params)
        assert os.path.exists(file) == result
        assert os.path.exists(basename + chSelect + ext) != result

    @pytest.mark.parametrize(
        "files, params, filename, others",
        [
            pytest.param(["sin-m"], {}, "sin-m.wav", False, id="noInput"),
            pytest.param(
                ["sin-m.L", "sin-m.R"], {}, "sin-m.wav", False, id="two_monos"
            ),
            pytest.param(
                ["sin-m.L", "sin-m.R"],
                {"newfile": "sin"},
                "sin.wav",
                False,
                id="newfile",
            ),
            pytest.param(
                ["sin-m.L", "sin-m.R"],
                {"remove": False},
                "sin-m.wav",
                True,
                id="noRemove",
            ),
            pytest.param(
                ["sin-m_L", "sin-m_R"],
                {"delimiter": "_"},
                "sin-m.wav",
                False,
                id="delimiter",
            ),
            pytest.param(
                ["sin-m.L", "sin-m.R"],
                {"string": True},
                "sin-m.wav",
                False,
                id="othersAsString",
            ),
            pytest.param(
                ["sin-m.L", "sin-m.R"],
                {"error": FileNotFoundError},
                "sin-m.wav",
                False,
                id="Nofile",
            ),
            pytest.param(
                ["sin-m.1", "sin-m.2", "sin-m.3"],
                {},
                "sin-m.wav",
                False,
                id="multichannel",
            ),
        ],
    )
    def test_join(self, tmp_file, files, params, filename, others):
        file, testfile = tmp_file
        path, _ = os.path.split(file)
        pathfile, ext = os.path.splitext(file)
        delimiter = params.pop("delimiter", ".")
        basename = pathfile + delimiter
        b_string = params.pop("string", False)
        error = params.pop("error", None)

        files = [os.path.join(path, x + ext) for x in files]
        for f in files:
            if not f == file:
                shutil.copyfile(testfile, f)

        root = files.pop(0)
        with AudioFile(filepath=root) as obj:
            obj.update_options({"delimiter": delimiter})
            if error is not None:
                with pytest.raises(error) as e:
                    obj.join(others=files[0][0:-2], **params)
            else:
                obj.join(others=files[0] if b_string else files, **params)
                assert os.path.exists(os.path.join(path, filename))
                assert all(os.path.exists(f) == others for f in files)

    def test_join_different_size(self, tmp_file):
        file, testfile = tmp_file
        testpath, _ = os.path.split(testfile)
        path, _ = os.path.split(file)
        pathfile, ext = os.path.splitext(file)
        testfile2 = os.path.join(testpath, "empty.wav")
        file2 = os.path.join(path, "empty.wav")
        shutil.copyfile(testfile2, file2)

        with AudioFile(filepath=file) as obj:
            obj.join(others=file2, newfile=os.path.join(path, "new.wav"))
            assert not os.path.exists(os.path.join(path, "new.wav"))
            assert all(os.path.exists(f) for f in (file, file2))
            obj.join(others=file2, forced=True, newfile=os.path.join(path, "new.wav"))
            assert os.path.exists(os.path.join(path, "new.wav"))
            assert all(not os.path.exists(f) for f in (file, file2))

    @pytest.mark.parametrize(
        "file, s, result",
        [
            ("sin-m", None, get_audio_path("sin-m")),
            ("sin.L", None, get_audio_path("sin")),
            ("sin-m", "saw", get_audio_path("saw")),
            ("sin.L", "saw", get_audio_path("saw")),
            (
                "sin.L",
                os.path.join(get_audio_path(), "bak", "saw"),
                os.path.join(get_audio_path(), "bak", "saw"),
            ),
        ],
    )
    def test_get_newfile_path(self, file, s, result):
        with AudioFile(get_audio_path(file)) as af:
            assert af.get_newfile_path(s) == result
