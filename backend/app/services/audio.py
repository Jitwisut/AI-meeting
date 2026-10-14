"""Audio inspection and conversion with ffprobe/ffmpeg (plan §8 Speech-to-Text).

The real container/codec is detected from the bytes, never trusted from the
file extension or the browser-supplied MIME type. Browsers record WebM/Opus
(Chrome, Firefox) or MP4/AAC (Safari), so recordings are accepted separately
from uploads, which are limited to MP3/WAV as in the project scope.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import get_settings
from app.errors import AppError

UPLOAD_FORMATS = {"mp3", "wav"}
RECORDING_FORMATS = {"matroska,webm", "webm", "ogg", "mov,mp4,m4a,3gp,3g2,mj2"}
SHAREPOINT_FORMATS = UPLOAD_FORMATS | RECORDING_FORMATS
TARGET_RATE = 16000


@dataclass
class AudioInfo:
    format_name: str
    codec: str
    duration_ms: int
    sample_rate: int
    channels: int
    size_bytes: int

    def to_dict(self) -> dict:
        return asdict(self)


def _require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise AppError(500, "ffmpeg_missing", f"ไม่พบโปรแกรม {name} บนเซิร์ฟเวอร์")
    return path


def probe(path: Path) -> AudioInfo:
    proc = subprocess.run(
        [_require_tool("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        raise AppError(422, "invalid_audio", "ไฟล์นี้ไม่ใช่ไฟล์เสียงที่อ่านได้ หรือไฟล์เสียหาย")
    data = json.loads(proc.stdout or "{}")
    streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
    if not streams:
        raise AppError(422, "no_audio_stream", "ไม่พบสัญญาณเสียงในไฟล์นี้")
    stream, fmt = streams[0], data.get("format", {})
    duration_ms = int(float(fmt.get("duration") or stream.get("duration") or 0) * 1000)
    if duration_ms <= 0:
        # Chrome/Edge MediaRecorder writes WebM without a Duration element: measure by decoding.
        duration_ms = _decoded_duration_ms(path)
    return AudioInfo(
        format_name=fmt.get("format_name", ""),
        codec=stream.get("codec_name", ""),
        duration_ms=duration_ms,
        sample_rate=int(stream.get("sample_rate") or 0),
        channels=int(stream.get("channels") or 0),
        size_bytes=path.stat().st_size,
    )


def _decoded_duration_ms(path: Path) -> int:
    proc = subprocess.run(
        [_require_tool("ffmpeg"), "-v", "error", "-nostats", "-i", str(path), "-vn", "-f", "null", "-",
         "-progress", "pipe:1"],
        capture_output=True, text=True, timeout=900,
    )
    out_us = 0
    for line in proc.stdout.splitlines():
        if line.startswith("out_time_us="):
            try:
                out_us = max(out_us, int(line.split("=", 1)[1]))
            except ValueError:
                continue
    return out_us // 1000


def validate(info: AudioInfo, source_type: str) -> None:
    s = get_settings()
    allowed = {"upload": UPLOAD_FORMATS, "recording": RECORDING_FORMATS}.get(source_type, SHAREPOINT_FORMATS)
    if info.format_name not in allowed:
        nice = "MP3 หรือ WAV" if source_type == "upload" else "ไฟล์เสียงที่รองรับ"
        raise AppError(415, "unsupported_format", f"รองรับเฉพาะ {nice} (ไฟล์นี้เป็น {info.format_name})")
    if info.size_bytes > s.max_upload_mb * 1024 * 1024:
        raise AppError(413, "file_too_large", f"ไฟล์ใหญ่เกิน {s.max_upload_mb} MB")
    if info.duration_ms <= 0:
        raise AppError(422, "empty_audio", "ไฟล์เสียงไม่มีความยาว")
    if info.duration_ms > s.max_audio_minutes * 60_000:
        raise AppError(413, "audio_too_long", f"ไฟล์เสียงยาวเกิน {s.max_audio_minutes} นาที")


def convert_to_wav(src: Path, dest: Path) -> None:
    """Normalise to 16 kHz mono PCM WAV, the most portable STT input."""
    proc = subprocess.run(
        [_require_tool("ffmpeg"), "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1",
         "-ar", str(TARGET_RATE), "-c:a", "pcm_s16le", str(dest)],
        capture_output=True, text=True, timeout=1800,
    )
    if proc.returncode != 0 or not dest.exists():
        raise AppError(422, "convert_failed", "ไม่สามารถแปลงไฟล์เสียงได้")


def encode_compact(src: Path, dest: Path, bitrate: str = "32k") -> None:
    """Small mono MP3 for sending speech to cloud models (~4 KB per second of audio)."""
    proc = subprocess.run(
        [_require_tool("ffmpeg"), "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", str(TARGET_RATE),
         "-c:a", "libmp3lame", "-b:a", bitrate, str(dest)],
        capture_output=True, text=True, timeout=900,
    )
    if proc.returncode != 0 or not dest.exists():
        raise AppError(500, "encode_failed", "ไม่สามารถเตรียมไฟล์เสียงสำหรับส่งถอดเสียงได้")


def split_wav(src: Path, out_dir: Path, chunk_seconds: int) -> list[tuple[Path, int]]:
    """Split a long WAV into chunks; returns (path, offset_ms) pairs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / "chunk_%04d.wav"
    subprocess.run(
        [_require_tool("ffmpeg"), "-y", "-v", "error", "-i", str(src), "-f", "segment",
         "-segment_time", str(chunk_seconds), "-c", "copy", str(pattern)],
        check=True, capture_output=True, timeout=1800,
    )
    chunks = sorted(out_dir.glob("chunk_*.wav"))
    return [(p, i * chunk_seconds * 1000) for i, p in enumerate(chunks)]


def waveform_peaks(wav: Path, buckets: int) -> list[float]:
    """RMS envelope of a 16-bit mono WAV in ``buckets`` points (0..1), streamed in chunks.

    Computed server-side so the browser never has to decode hours of audio.
    """
    import array
    import math
    import wave

    with wave.open(str(wav)) as w:
        if w.getsampwidth() != 2:
            raise AppError(422, "unsupported_wav", "รูปแบบไฟล์เสียงไม่รองรับการสร้างคลื่นเสียง")
        frames = w.getnframes()
        out: list[float] = []
        for i in range(buckets):
            count = round((i + 1) * frames / buckets) - round(i * frames / buckets)
            samples = array.array("h", w.readframes(count)) if count > 0 else array.array("h")
            out.append(math.sqrt(sum(x * x for x in samples) / len(samples)) / 32768 if samples else 0.0)
    peak = max(out, default=0.0) or 1.0
    # perceptual curve so quiet speech is still visible
    return [round((v / peak) ** 0.6, 3) for v in out]


def scan_for_malware(path: Path) -> None:
    """Hook for the organisation's malware scanning (plan §9).

    MVP: no-op. Replace with the approved scanner (e.g. Defender for Storage
    or an ICAP/ClamAV service) before handling production uploads.
    """
    return None


def meeting_audio_dir(meeting_id: str) -> Path:
    d = get_settings().storage_dir / "audio" / meeting_id
    d.mkdir(parents=True, exist_ok=True)
    return d
