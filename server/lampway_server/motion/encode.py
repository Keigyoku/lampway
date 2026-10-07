# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The encoder: ONE ffmpeg process, the captured PNGs on stdin (image2pipe), an MP4 and a WebM out (motion_graphics.md section 6).

MP4: libx264 -preset slow -crf 18 -profile:v high, BT.709 limited range tagged (``setparams``: without it the transfer and primaries came out
``unknown``), x264's settings SEI dropped (``filter_units=remove_types=6``), faststart. WebM: libvpx-vp9 constant quality. Both: no metadata, no
encoder tag, bitexact, and a FIXED thread count (measured on the teaser: the MP4 bytes change with x264's thread count; the WebM did not)."""
import json
import shutil
import subprocess
from pathlib import Path

THREADS = 4
NICE = ["nice", "-n", "15"]
VF = "scale=out_color_matrix=bt709:out_range=tv:flags=bicubic,format=yuv420p,setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709"
_COLOR = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]
_CLEAN = ["-map_metadata", "-1", "-map_chapters", "-1", "-metadata:s:v:0", "encoder=", "-fflags", "+bitexact", "-flags:v", "+bitexact"]
FORMATS = ("mp4", "webm")


class FfmpegMissing(RuntimeError):
    pass


def require() -> None:
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        raise FfmpegMissing("ffmpeg not found on PATH: install ffmpeg")


def version() -> str:
    """ffmpeg's version line (the receipt pins the engine; verify compares it)."""
    return subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.split("\n")[0]


def argv(paths: dict, fps: int, threads: int = THREADS) -> list:
    """The ffmpeg command line for ``paths`` ({"mp4": path, "webm": path}, either or both)."""
    a = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-threads", str(threads), "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png", "-i", "-"]
    if "mp4" in paths:
        a += ["-map", "0:v", "-vf", VF, "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high", "-threads", str(threads), *_COLOR,
              "-bsf:v", "filter_units=remove_types=6", "-movflags", "+faststart", *_CLEAN, str(paths["mp4"])]
    if "webm" in paths:
        a += ["-map", "0:v", "-vf", VF, "-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-deadline", "good", "-cpu-used", "2", "-row-mt", "1",
              "-threads", str(threads), *_COLOR, *_CLEAN, str(paths["webm"])]
    return a


def receipt_args(a: list) -> list:
    """The command line as the receipt records it: output paths reduced to their file names (no home paths in a receipt)."""
    return [Path(x).name if x.startswith("/") else x for x in a]


class Encoder:
    """One ffmpeg process fed frame by frame; ``finish`` closes the pipe and raises on a failed encode."""

    def __init__(self, a: list, pass_fds=()):
        self.argv, self.pass_fds = a, tuple(pass_fds)
        self.outputs = [Path(value) for value in a if value.endswith((".mp4", ".webm"))]
        self.proc = subprocess.Popen(NICE + a, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, pass_fds=self.pass_fds)

    def write(self, png: bytes) -> None:
        try:
            self.proc.stdin.write(png)
        except BrokenPipeError:
            self.proc.wait()
            raise RuntimeError("encode failed: " + self.proc.stderr.read().decode(errors="replace")[-1200:]) from None

    def finish(self) -> None:
        self.proc.stdin.close()
        err = self.proc.stderr.read().decode(errors="replace")
        if self.proc.wait() != 0:
            raise RuntimeError("encode failed: " + err[-1200:])
        for path in self.outputs:
            # Newer ffmpeg versions add a stream encoder tag after applying metadata options.
            # Older engines remain byte-for-byte unchanged when their output is already clean.
            tags = probe(path, pass_fds=self.pass_fds)["stream"].get("tags", {})
            if any(key.lower() == "encoder" for key in tags):
                clean = path.with_name(path.stem + ".clean" + path.suffix)
                command = NICE + ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path), "-map", "0", "-c", "copy", *_CLEAN]
                if path.suffix == ".mp4":
                    command += ["-movflags", "+faststart"]
                command.append(str(clean))
                try:
                    result = subprocess.run(command, capture_output=True, pass_fds=self.pass_fds)
                    if result.returncode:
                        raise RuntimeError("metadata cleanup failed: " + result.stderr.decode(errors="replace")[-1200:])
                    if any(key.lower() == "encoder" for key in probe(clean, pass_fds=self.pass_fds)["stream"].get("tags", {})):
                        raise RuntimeError("metadata cleanup failed: encoder tag remains")
                    clean.replace(path)
                finally:
                    clean.unlink(missing_ok=True)

    def abort(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()


def probe(path, pass_fds=()) -> dict:
    j = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                   "format=duration,size,bit_rate:stream=codec_name,profile,width,height,pix_fmt,r_frame_rate,nb_frames,color_space,color_range,color_transfer,color_primaries:stream_tags",
                                   "-of", "json", str(path)], capture_output=True, text=True, pass_fds=tuple(pass_fds)).stdout or "{}")
    return {"format": j.get("format", {}), "stream": (j.get("streams") or [{}])[0]}
