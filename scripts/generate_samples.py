"""Generate synthetic Thai meeting audio for development and evaluation.

Uses the macOS `say` command with the Thai voice "Kanya" and ffmpeg. Each
sentence is synthesised separately so the reference transcript has exact
timestamps. Output:
  samples/audio/<id>.wav, samples/audio/<id>.mp3
  samples/reference/<id>.transcript.json

All content is fictional and non-sensitive (plan §12: samples/).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
GAP_MS = 500
RATE = 16000


def run(*cmd: str) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wav_duration_ms(path: Path) -> int:
    with wave.open(str(path)) as w:
        return int(w.getnframes() * 1000 / w.getframerate())


def build(meeting_file: Path, voice: str) -> None:
    meeting = json.loads(meeting_file.read_text(encoding="utf-8"))
    mid = meeting["id"]
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        silence = tmp / "gap.wav"
        run("ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r={RATE}:cl=mono",
            "-t", str(GAP_MS / 1000), "-c:a", "pcm_s16le", str(silence))
        parts: list[Path] = [silence]
        segments = []
        cursor = GAP_MS
        for i, sentence in enumerate(meeting["sentences"], start=1):
            aiff = tmp / f"s{i}.aiff"
            wav = tmp / f"s{i}.wav"
            run("say", "-v", voice, "-o", str(aiff), sentence)
            run("ffmpeg", "-y", "-i", str(aiff), "-ar", str(RATE), "-ac", "1",
                "-c:a", "pcm_s16le", str(wav))
            dur = wav_duration_ms(wav)
            segments.append({"id": i, "start_ms": cursor, "end_ms": cursor + dur, "text": sentence})
            cursor += dur + GAP_MS
            parts += [wav, silence]
        concat_list = tmp / "list.txt"
        concat_list.write_text("".join(f"file '{p}'\n" for p in parts))
        out_wav = SAMPLES / "audio" / f"{mid}.wav"
        out_mp3 = SAMPLES / "audio" / f"{mid}.mp3"
        run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c:a", "pcm_s16le", str(out_wav))
        run("ffmpeg", "-y", "-i", str(out_wav), "-codec:a", "libmp3lame", "-b:a", "64k", str(out_mp3))
    reference = {
        "id": mid,
        "language": meeting["language"],
        "duration_ms": cursor,
        "segments": segments,
    }
    (SAMPLES / "reference" / f"{mid}.transcript.json").write_text(
        json.dumps(reference, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"generated {mid}: {len(segments)} segments, {cursor / 1000:.1f}s")


def main() -> int:
    if not shutil.which("say") or not shutil.which("ffmpeg"):
        print("ต้องใช้ macOS `say` และ ffmpeg", file=sys.stderr)
        return 1
    voice = sys.argv[1] if len(sys.argv) > 1 else "Kanya"
    for meeting_file in sorted((SAMPLES / "meetings").glob("*.json")):
        build(meeting_file, voice)
    return 0


if __name__ == "__main__":
    sys.exit(main())
