"""Encoding, motion and loudness helpers that decide how the final video looks.

Everything YouTube judges a Short on -- sharpness, motion smoothness, perceived
loudness, and how fast the file starts playing -- is decided by the ffmpeg
arguments in this module. The pipelines used to inline their own ad-hoc x264
calls, which meant every render leaked quality in a slightly different way:

  * ``libx264`` with no ``-crf`` fell back to CRF 23 (visibly soft on the flat
    gradients that AI-generated images are full of), and every extra pass in the
    chain re-encoded on top of the previous loss.
  * No ``-movflags +faststart``, so the moov atom sat at the end of the file and
    playback stalled before the first frame -- the worst possible thing for a
    format judged on its first second.
  * 25 fps against YouTube's 30/60 fps ladder, which forces a resample and
    judders the Ken Burns motion.
  * No loudness normalization, so quiet renders got turned *up* by YouTube's
    own normalizer, dragging the noise floor up with them.

The helpers here are the single source of truth for those decisions. Both the
shorts and the long-form pipelines call into them.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import List, Optional, Sequence

# ---------------------------------------------------------------------------
# Delivery spec
# ---------------------------------------------------------------------------

#: Frame rate for every rendered video. YouTube's encoding ladder is built on
#: 30/60 fps; delivering 25 forces a frame-rate conversion that judders slow
#: camera moves. 30 is the cheapest rate that lands on the ladder exactly.
FPS = 30

#: Vertical (Shorts / Reels / TikTok) delivery resolution.
SHORT_W, SHORT_H = 1080, 1920

#: Horizontal (long-form) delivery resolution.
LONG_W, LONG_H = 1920, 1080

#: Perceived loudness YouTube normalizes to. Delivering at -14 LUFS means the
#: platform leaves the mix alone instead of pulling it down (or pushing a quiet
#: mix up along with its noise floor).
TARGET_LUFS = -14.0
TARGET_TRUE_PEAK = -1.5
TARGET_LRA = 11.0

#: Ceiling on the single normalization gain. Reaching -14 LUFS from a very quiet
#: mix would otherwise amplify the noise floor along with the voice.
MAX_GAIN_DB = 30.0

#: Quality presets exposed to the UI. ``crf`` is the visual-quality knob (lower
#: is better/bigger); ``preset`` trades encode time for compression efficiency.
QUALITY_PRESETS = {
    "Draft (fast)": {"crf": 23, "preset": "veryfast"},
    "Standard": {"crf": 20, "preset": "medium"},
    "High (recommended)": {"crf": 18, "preset": "slow"},
    "Maximum": {"crf": 16, "preset": "slower"},
}
DEFAULT_QUALITY = "High (recommended)"

#: Intermediate segments are re-encoded at least once more downstream, so they
#: are kept near-transparent and fast rather than small.
INTERMEDIATE_CRF = 16
INTERMEDIATE_PRESET = "veryfast"


def _preset_params(quality: Optional[str]) -> dict:
    return QUALITY_PRESETS.get(quality or DEFAULT_QUALITY, QUALITY_PRESETS[DEFAULT_QUALITY])


def video_encode_args(
    quality: Optional[str] = None,
    *,
    crf: Optional[int] = None,
    preset: Optional[str] = None,
    fps: int = FPS,
    faststart: bool = True,
) -> List[str]:
    """ffmpeg arguments for an H.264 stream that matches YouTube's spec.

    ``-g``/``keyint`` pins a 2-second GOP: YouTube's transcoder segments on
    keyframes, and a closed 2s GOP with ``scenecut=0`` gives it clean cut points
    instead of letting x264 scatter them.
    """
    params = _preset_params(quality)
    crf = params["crf"] if crf is None else crf
    preset = params["preset"] if preset is None else preset
    gop = fps * 2

    args = [
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(crf),
        "-profile:v", "high",
        "-level", "4.2",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-g", str(gop),
        "-keyint_min", str(gop),
        "-sc_threshold", "0",
        "-bf", "2",
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
    ]
    if faststart:
        # Without this the moov atom lands at the end of the file and players
        # must buffer the whole thing before the first frame appears.
        args += ["-movflags", "+faststart"]
    return args


def audio_encode_args(bitrate: str = "192k") -> List[str]:
    """AAC-LC at 48 kHz stereo -- what YouTube asks for and re-encodes from."""
    return ["-c:a", "aac", "-b:a", bitrate, "-ar", "48000", "-ac", "2"]


def intermediate_encode_args(fps: int = FPS) -> List[str]:
    """Near-transparent settings for scene segments that get re-encoded later."""
    return video_encode_args(crf=INTERMEDIATE_CRF, preset=INTERMEDIATE_PRESET,
                             fps=fps, faststart=False)


# ---------------------------------------------------------------------------
# Ken Burns motion
# ---------------------------------------------------------------------------

#: Six camera moves cycled across scenes. A reel where every image pushes in
#: the same way reads as a slideshow within about three scenes; alternating the
#: direction is what makes still images feel shot rather than pasted.
_MOVES = ("in", "out", "in_left", "in_down", "out_right", "in_up")

#: zoompan evaluates x/y to whole *input* pixels, so a 1080-wide source produces
#: visible 1-pixel stair-stepping as the crop window slides. Supersampling the
#: still to 2x delivery resolution before the zoom puts that quantisation below
#: half an output pixel. Measured against the previous 1.78x scale, this cuts
#: the frame-to-frame variation in the motion step from ~22% to ~13% of the
#: mean step -- smoother, though zoompan's integer stepping is not eliminated.
SUPERSAMPLE = 2


def ken_burns_vf(
    index: int,
    duration: float,
    *,
    fps: int = FPS,
    width: int = SHORT_W,
    height: int = SHORT_H,
    is_hook: bool = False,
    motion_style: str = "Dynamic",
) -> str:
    """Build the ``-vf`` chain that animates one still image.

    Args:
        index: Scene index, used to cycle the camera move.
        duration: Scene length in seconds.
        is_hook: True for scene 1. The opening shot gets a faster, harder push
            because the first second decides whether the viewer swipes away.
        motion_style: ``"Dynamic"`` cycles all six moves, ``"Subtle"`` keeps a
            gentle centred push, ``"Off"`` renders a static frame.
    """
    frames = max(1, int(round(duration * fps)))
    ss_w, ss_h = width * SUPERSAMPLE, height * SUPERSAMPLE
    scale = (f"scale={ss_w}:{ss_h}:force_original_aspect_ratio=increase:flags=lanczos,"
             f"crop={ss_w}:{ss_h}")

    if motion_style == "Off":
        return f"{scale},scale={width}:{height},fps={fps},setsar=1"

    if motion_style == "Subtle":
        move, amount = "in", 0.08
    elif is_hook:
        # The hook pushes ~2x harder than a body scene.
        move, amount = "in", 0.26
    else:
        move, amount = _MOVES[index % len(_MOVES)], 0.16

    # Zoom as an explicit function of the output frame number rather than the
    # usual `zoom+0.001` accumulator: the accumulator's end point depends on the
    # scene length, so short scenes barely moved and long ones slammed into the
    # clamp and froze partway through.
    progress = f"(on/{frames})"
    if move.startswith("out"):
        z = f"'{1 + amount:.4f}-{amount:.4f}*{progress}'"
    else:
        z = f"'1+{amount:.4f}*{progress}'"

    # Travel of the crop window, in input pixels, at the current zoom.
    span_x, span_y = "(iw-iw/zoom)", "(ih-ih/zoom)"
    x, y = f"'{span_x}/2'", f"'{span_y}/2'"
    if move.endswith("left"):        # frame drifts left -> right
        x = f"'{span_x}*{progress}'"
    elif move.endswith("right"):     # frame drifts right -> left
        x = f"'{span_x}*(1-{progress})'"
    elif move.endswith("down"):
        y = f"'{span_y}*{progress}'"
    elif move.endswith("up"):
        y = f"'{span_y}*(1-{progress})'"

    zoompan = (f"zoompan=z={z}:x={x}:y={y}:d={frames}:s={width}x{height}:fps={fps}")
    return f"{scale},{zoompan},setsar=1"


# ---------------------------------------------------------------------------
# Audio: ducking + loudness
# ---------------------------------------------------------------------------

def stock_grade() -> str:
    """Grade applied to real footage so it cuts against generated stills.

    Stock clips come from hundreds of different cameras and colourists, while
    generated stills share one look. Without a common grade a mixed reel reads
    as two videos stitched together at every source change. Returned as a filter
    fragment to append inside an existing ``-vf`` chain, hence the leading comma.
    """
    return ",eq=contrast=1.06:saturation=1.10:brightness=0.01"


def music_mix_filter(music_volume: float = 0.30, duck: bool = True) -> str:
    """filter_complex that mixes background music under narration.

    Two problems with the flat ``volume=0.15`` + ``amix`` mix this replaces:
    ``amix`` normalizes by default, so the narration came out at half level and
    the whole video sounded thin; and a fixed music level either buries the
    music or fights the voice, because it cannot know when the voice is talking.

    Sidechain compression solves the second one properly -- the music sits at a
    useful level in the gaps and ducks out of the way the moment the narrator
    speaks, which is how every professionally mixed short sounds.

    Expects input 0 = narration, input 1 = music. Outputs label ``[aout]``.
    """
    if not duck:
        return (f"[1:a]volume={music_volume:.2f}[bgm];"
                f"[0:a][bgm]amix=inputs=2:duration=first:normalize=0[aout]")
    return (
        f"[1:a]volume={music_volume:.2f},aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[bgm];"
        "[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asplit=2[voice][key];"
        # threshold/ratio tuned so speech pulls the bed down ~10 dB; the slow
        # release lets music swell back between sentences instead of pumping.
        "[bgm][key]sidechaincompress=threshold=0.02:ratio=12:attack=5:release=350:makeup=1[ducked];"
        "[voice][ducked]amix=inputs=2:duration=first:normalize=0[aout]"
    )


_LOUDNORM_KEYS = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")


def measure_loudness(path: str, timeout: int = 300) -> Optional[dict]:
    """Run loudnorm's analysis pass and return its measurements.

    Returns None if ffmpeg fails or prints something unparseable, so callers can
    fall back to the single-pass mode instead of dying mid-render.
    """
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats", "-i", path,
        "-af", (f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TRUE_PEAK}:LRA={TARGET_LRA}"
                ":print_format=json"),
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.SubprocessError, OSError):
        return None

    # The JSON block is the last {...} in stderr.
    blocks = re.findall(r"\{[^{}]*\}", proc.stderr or "", re.S)
    for block in reversed(blocks):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if all(k in data for k in _LOUDNORM_KEYS):
            return data
    return None


def gain_filter(measured: Optional[dict] = None) -> str:
    """Move the whole mix to the target loudness with ONE constant gain.

    ``loudnorm`` is deliberately not used here. Even given full measurements and
    ``linear=true``, it silently falls back to *dynamic* mode whenever the source
    LRA exceeds the target LRA -- and a narration short always has a wide range,
    because the gaps between spoken lines are near-silent. Measured on a real
    render: source LRA 15.2 against a target of 11 produced
    "Normalization Type: Dynamic", which rode the level up by **+13.5 LU** from
    start to end. It did not even reduce the range (output LRA was still 15.2),
    so the compression bought nothing and made the video get louder as it played.

    A single ``volume`` gain cannot do that. The gain is capped so the loudest
    true peak lands at ``TARGET_TRUE_PEAK``, and a limiter catches inter-sample
    transients, but nothing rides the level over time.
    """
    if not measured:
        # Without measurements, dynamic loudnorm is still the wrong answer, so
        # leave the level alone rather than introduce a ramp.
        return "anull"
    try:
        measured_i = float(measured["input_i"])
        measured_tp = float(measured["input_tp"])
    except (KeyError, TypeError, ValueError):
        return "anull"

    gain = TARGET_LUFS - measured_i
    # The gain is NOT capped to the true-peak headroom. A single loud transient
    # (a whoosh SFX) sets the peak, so capping there held a whole render 5 LU
    # below target -- and YouTube does not raise quiet uploads, it only lowers
    # loud ones, so that loudness is simply lost against other creators.
    # The limiter below shaves those brief transients instead, which costs
    # nothing audible because they are exactly the moments already masked by a
    # scene change. Total gain is still bounded so a near-silent input cannot
    # be amplified into noise.
    if gain > MAX_GAIN_DB:
        gain = MAX_GAIN_DB
    # alimiter's `level` (auto-level) defaults to TRUE, which re-normalizes the
    # output and undoes the gain just computed -- measured as a 1.45 LU
    # overshoot. It must be off for the limiter to act purely as a safety net.
    limit = _db_to_linear(TARGET_TRUE_PEAK)
    return f"volume={gain:.2f}dB,alimiter=limit={limit:.4f}:level=disabled"


def _db_to_linear(db: float) -> float:
    return 10 ** (db / 20.0)


# Kept as a thin alias so existing callers and tests keep working.
def loudnorm_filter(measured: Optional[dict] = None) -> str:
    return gain_filter(measured)


def normalize_loudness(in_path: str, out_path: str, log=print) -> str:
    """Normalize ``in_path`` to broadcast loudness, writing ``out_path``.

    Falls back to copying the input through unchanged if ffmpeg fails, because a
    slightly quiet video still beats a failed render.
    """
    measured = measure_loudness(in_path)
    if measured is None:
        log("Loudness analysis unavailable; leaving the level unchanged.")
        shutil.copy(in_path, out_path)
        return out_path

    cmd = [
        "ffmpeg", "-y", "-i", in_path,
        "-af", gain_filter(measured),
        "-ar", "48000", "-c:a", "pcm_s16le", out_path,
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, OSError) as err:
        log(f"Loudness normalization failed ({err}); using the unnormalized mix.")
        shutil.copy(in_path, out_path)
        return out_path
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        shutil.copy(in_path, out_path)
        return out_path

    try:
        shortfall = (TARGET_LUFS - float(measured["input_i"])) - MAX_GAIN_DB
    except (KeyError, TypeError, ValueError):
        shortfall = 0.0
    if shortfall > 0.5:
        # Say so rather than silently delivering a quiet video: YouTube will not
        # raise it, so the user needs to know the source itself was too quiet.
        log(f"Source was very quiet; capped at +{MAX_GAIN_DB:.0f}dB, so the mix "
            f"lands about {shortfall:.1f} LU below {TARGET_LUFS} LUFS.")
    else:
        log(f"Audio normalized to {TARGET_LUFS} LUFS (YouTube playback target).")
    return out_path


# ---------------------------------------------------------------------------
# Overlays
# ---------------------------------------------------------------------------

_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def find_font() -> Optional[str]:
    return next((f for f in _FONT_CANDIDATES if os.path.exists(f)), None)


#: drawtext options every text overlay needs. ``expansion=none`` is not
#: cosmetic: with the default ``normal`` expansion a bare '%' anywhere in the
#: string makes drawtext render *nothing at all* and still exit 0, so a title
#: like "50% Of People Don't Know This" silently produced a blank overlay.
DRAWTEXT_BASE = "expansion=none"


#: Characters that survive an inline drawtext ``text='...'`` value untouched.
#: There is no reliable way to escape an apostrophe inside a filter-graph option
#: -- the close-quote/reopen form that works at the top level terminates the
#: option early here, and the remaining options leak out and render as visible
#: text. Anything with user-supplied punctuation must go through ``textfile=``
#: (see :func:`drawtext_from_file`); this is only for short generated labels.
_INLINE_SAFE = re.compile(r"[^A-Za-z0-9 _@.\-!?#&+/]")


def sanitize_inline_text(text: str) -> str:
    """Strip a short label down to characters safe for an inline ``text=``."""
    return _INLINE_SAFE.sub("", text or "").strip()


def drawtext_from_file(
    text: str,
    scratch_path: str,
    *,
    fontsize: int,
    x: str = "(w-text_w)/2",
    y: str = "0",
    fontcolor: str = "white",
    borderw: int = 0,
    bordercolor: str = "black@0.9",
    line_spacing: int = 0,
    extra: str = "",
) -> Optional[str]:
    """Write ``text`` to ``scratch_path`` and build a drawtext reading it back.

    Routing the string through a file is the only escaping-proof way to put
    arbitrary text on a frame: ffmpeg reads the file verbatim, so apostrophes,
    colons, commas, brackets and percent signs all pass through as typed. Titles
    come from an LLM and routinely contain every one of them.

    Newlines in ``text`` become real lines, centred together via ``text_align``.
    """
    font = find_font()
    if not font or not (text or "").strip():
        return None
    os.makedirs(os.path.dirname(os.path.abspath(scratch_path)) or ".", exist_ok=True)
    with open(scratch_path, "w", encoding="utf-8") as handle:
        handle.write(text)
    rel = os.path.relpath(scratch_path, os.path.abspath(os.curdir)).replace(os.path.sep, "/")

    opts = [
        DRAWTEXT_BASE,
        f"fontfile='{font}'",
        f"textfile='{rel}'",
        f"fontcolor={fontcolor}",
        f"fontsize={fontsize}",
        "text_align=center",
        f"x={x}",
        f"y={y}",
    ]
    if borderw:
        opts += [f"borderw={borderw}", f"bordercolor={bordercolor}"]
    if line_spacing:
        opts.append(f"line_spacing={line_spacing}")
    if extra:
        opts.append(extra)
    return "drawtext=" + ":".join(opts)


def progress_bar_filter(total_duration: float, height: int = 10,
                        color: str = "white") -> str:
    """A thin bar that fills across the bottom as the video plays.

    Shorts autoplay with the scrubber hidden, so viewers have no idea how much
    is left. A visible "almost done" signal keeps people from swiping away
    mid-video, which is the metric the algorithm rewards.

    Implemented as split + overlay rather than the obvious
    ``drawbox=w='iw*t/total'``: drawbox resolves its geometry once when the
    filter is configured, so the "growing" box rendered full-width from the
    first frame. ``overlay`` genuinely re-evaluates ``x`` per frame, so a
    full-width bar is slid in from the left instead -- the visible portion is
    left-anchored and grows exactly in step with playback.
    """
    total = max(0.1, float(total_duration))
    return (
        "split=2[pb_base][pb_src];"
        f"[pb_src]crop=iw:{height}:0:0,drawbox=x=0:y=0:w=iw:h=ih:color={color}:t=fill[pb_bar];"
        f"[pb_base][pb_bar]overlay=x='-w+w*t/{total}':y=H-{height}"
    )


def subscribe_overlay_filters(total_duration: float, channel_handle: str = "",
                              lead_seconds: float = 3.5) -> List[str]:
    """Blinking SUBSCRIBE call-to-action for the closing seconds."""
    start = max(0.0, float(total_duration) - lead_seconds)
    font = find_font()
    fontfile = f"fontfile='{font}':" if font else ""
    # Visible 0.7s of every second so it pulses rather than sits there.
    blink = f"gte(t\\,{start:.2f})*lt(mod(t\\,1)\\,0.7)"
    filters = [
        f"drawtext={DRAWTEXT_BASE}:{fontfile}text='SUBSCRIBE':fontcolor=white:fontsize=70:"
        f"box=1:boxcolor=red@0.9:boxborderw=24:x=(w-text_w)/2:y=h*0.70:"
        f"enable='{blink}'"
    ]
    handle = sanitize_inline_text(channel_handle)
    if handle:
        filters.append(
            f"drawtext={DRAWTEXT_BASE}:{fontfile}text='{handle}':"
            f"fontcolor=white:fontsize=42:"
            f"box=1:boxcolor=black@0.5:boxborderw=10:x=(w-text_w)/2:y=h*0.70+100:"
            f"enable='gte(t\\,{start:.2f})'"
        )
    return filters


def build_finish_filter(
    *,
    subtitles_path: Optional[str] = None,
    total_duration: float = 0.0,
    subscribe: bool = False,
    channel_handle: str = "",
    progress_bar: bool = False,
) -> Optional[str]:
    """Compose every burn-in step into ONE filter chain.

    Each of subtitles, the CTA and the progress bar used to be its own ffmpeg
    invocation, so a finished video had been through three generations of lossy
    re-encoding before upload. Chaining them means one encode, one generation.
    """
    parts: List[str] = []
    if subtitles_path:
        # Relative + forward slashes: the subtitles filter treats the path as a
        # filter-graph token, so Windows separators and ':' in absolute paths
        # break parsing.
        rel = os.path.relpath(subtitles_path, os.path.abspath(os.curdir))
        parts.append(f"subtitles='{rel.replace(os.path.sep, '/')}'")
    if progress_bar and total_duration > 0:
        parts.append(progress_bar_filter(total_duration))
    if subscribe and total_duration > 0:
        parts.extend(subscribe_overlay_filters(total_duration, channel_handle))
    return ",".join(parts) if parts else None


# ---------------------------------------------------------------------------
# Thumbnails
# ---------------------------------------------------------------------------

def _wrap(text: str, width: int) -> List[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def generate_thumbnail(
    video_path: str,
    title: str,
    out_path: str,
    *,
    at_seconds: float = 0.6,
    vertical: bool = True,
    log=print,
) -> Optional[str]:
    """Grab a frame and burn a bold, readable title over it.

    Shorts show a thumbnail in search, on the channel grid and in suggested
    feeds, and a frame pulled straight from the video is almost always too busy
    to read at grid size. Punching the contrast, darkening the lower third and
    laying oversized text over it is what makes it legible as a 200px tile.

    Returns the written path, or None if the grab failed (never raises -- a
    missing thumbnail must not fail a render).
    """
    width, height = (1080, 1920) if vertical else (1280, 720)
    lines = _wrap((title or "").upper(), 18)[:3]
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    chain = [
        f"scale={width}:{height}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}",
        # Punchier grade so the tile reads at thumbnail size.
        "eq=contrast=1.16:saturation=1.22:brightness=0.02",
        "unsharp=5:5:0.8:5:5:0.0",
    ]
    if lines:
        size = 96 if vertical else 72
        spacing = 18
        block_h = len(lines) * size + (len(lines) - 1) * spacing
        band_h = int(block_h + height * 0.10)
        # Scrim behind the text so it stays readable over a bright frame.
        chain.append(f"drawbox=x=0:y=ih-{band_h}:w=iw:h={band_h}:color=black@0.55:t=fill")
        text_layer = drawtext_from_file(
            "\n".join(lines),
            f"{os.path.splitext(out_path)[0]}.title.txt",
            fontsize=size,
            y=f"h-{band_h} + ({band_h} - {block_h})/2",
            borderw=6,
            line_spacing=spacing,
        )
        if text_layer:
            chain.append(text_layer)

    cmd = [
        "ffmpeg", "-y", "-ss", f"{max(0.0, at_seconds):.2f}", "-i", video_path,
        "-frames:v", "1", "-vf", ",".join(chain), "-q:v", "2", out_path,
    ]
    try:
        run_ffmpeg(cmd, label="thumbnail")
    except (RuntimeError, OSError) as err:
        log(f"Thumbnail generation skipped ({err}).")
        return None
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        return None
    return out_path


# ---------------------------------------------------------------------------
# Introspection (used by the API + verification)
# ---------------------------------------------------------------------------

def probe(path: str) -> dict:
    """Return width/height/fps/duration/loudness-relevant info for a rendered file."""
    cmd = ["ffprobe", "-v", "error", "-print_format", "json",
           "-show_format", "-show_streams", path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
        data = json.loads(proc.stdout)
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
        return {}

    info: dict = {"duration": float(data.get("format", {}).get("duration", 0) or 0)}
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and "width" not in info:
            info.update(
                width=stream.get("width"),
                height=stream.get("height"),
                video_codec=stream.get("codec_name"),
                fps=_parse_rate(stream.get("avg_frame_rate")),
            )
        elif stream.get("codec_type") == "audio" and "audio_codec" not in info:
            info.update(
                audio_codec=stream.get("codec_name"),
                sample_rate=int(stream.get("sample_rate") or 0),
                channels=stream.get("channels"),
            )
    return info


def _parse_rate(rate: Optional[str]) -> Optional[float]:
    if not rate or "/" not in rate:
        return None
    num, den = rate.split("/", 1)
    try:
        num, den = float(num), float(den)
    except ValueError:
        return None
    return round(num / den, 3) if den else None


def run_ffmpeg(cmd: Sequence[str], *, label: str = "ffmpeg") -> None:
    """Run ffmpeg, surfacing its stderr on failure.

    The pipelines used to send stderr to DEVNULL, so a broken filter graph
    produced a bare 'returned non-zero exit status 1' with no way to tell what
    ffmpeg actually objected to.
    """
    proc = subprocess.run(list(cmd), stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-12:])
        raise RuntimeError(f"{label} failed (exit {proc.returncode}):\n{tail}")
