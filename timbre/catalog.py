"""Static model knowledge: built-in voices, control vocabularies, languages, tags."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    language: str
    gender: str
    accent: str
    use: str


PRESETS = [
    Preset("UK_George", "George", "English", "Male", "British", "Audiobooks, formal announcements"),
    Preset("US_Emma", "Emma", "English", "Female", "American", "Assistants, narration, product voice"),
    Preset("UK_Charlotte", "Charlotte", "English", "Female", "British", "General English voice"),
    Preset("灵楷", "Ling Kai", "Chinese", "Male", "Mandarin", "Late-night radio, documentary narration"),
    Preset("灵小川", "Ling Xiaochuan", "Chinese", "Male", "Mandarin", "Radio monologues, food documentaries"),
    Preset("灵小锋", "Ling Xiaofeng", "Chinese", "Male", "Mandarin", "Daily dialogue, explanations"),
    Preset("灵朵儿", "Ling Duoer", "Chinese", "Female", "Mandarin", "Cultural documentaries, audiobooks"),
    Preset("灵小柔", "Ling Xiaorou", "Chinese", "Female", "Mandarin", "Customer service, IVR"),
    Preset("灵小雅", "Ling Xiaoya", "Chinese", "Female", "Mandarin", "News, audiobooks"),
    Preset("灵小棠", "Ling Xiaotang", "Chinese", "Female", "Mandarin", "Travel vlogs, storytelling"),
]

# Ming's control vocabulary is Chinese; the UI shows English labels.
EMOTIONS = [("Neutral", "中性"), ("Happy", "高兴"), ("Sad", "悲伤"), ("Angry", "愤怒"),
            ("Fearful", "恐惧"), ("Surprised", "惊讶"), ("Disgusted", "厌恶")]
SPEEDS = [("Slow", "慢速"), ("Medium", "中速"), ("Fast", "快速")]
LEVELS = [("Low", "低"), ("Medium", "中"), ("High", "高")]

LANGUAGES = [("Auto", "auto"), ("English", "English"), ("Chinese", "Chinese"), ("German", "German"),
             ("Spanish", "Spanish"), ("French", "French"), ("Korean", "Korean"), ("Japanese", "Japanese")]

TAGS = [
    ("Breath", "[Breathing]"), ("Sigh", "[Sigh]"), ("Laugh", "[Laughter]"), ("Cough", "[Cough]"),
    ("Hesitation “uhm”", "[Uhm]"), ("Surprised “ah”", "[Surprise-ah]"), ("Surprised “oh”", "[Surprise-oh]"),
    ("Questioning “huh”", "[Question-huh]"), ("Questioning “ah”", "[Question-ah]"),
    ("Affirming “mm”", "[Confirmation-en]"), ("Displeased “hmph”", "[Dissatisfaction-hnn]"),
]

DESIGN_CHIPS = ["deep", "warm", "bright", "raspy", "breathy", "calm", "energetic", "slow pace",
                "fast pace", "British accent", "American accent", "young adult", "middle-aged",
                "elderly", "audiobook narrator", "news anchor", "documentary", "quiet studio"]

DIRECT_EXAMPLES = [
    ("Storyteller", "Speak in a warm, intimate storytelling voice, unhurried, with a hint of nostalgia."),
    ("Coach", "Sound like an encouraging sports coach, energetic and firm without shouting."),
    ("Whisper", "Whisper softly and slowly, as if telling a secret late at night."),
    ("Newsreader", "Read like a calm, authoritative evening newsreader with crisp diction."),
]

FORMATS = [("WAV", "wav"), ("FLAC", "flac"), ("MP3", "mp3"), ("Ogg Vorbis", "ogg")]
BIT_DEPTHS = [("16-bit", "16"), ("24-bit", "24"), ("32-bit float", "32f")]
SAMPLE_RATES = [("Native · 44.1 kHz", 0), ("48 kHz", 48000), ("32 kHz", 32000), ("24 kHz", 24000),
                ("22.05 kHz", 22050), ("16 kHz", 16000)]


def preset(pid: str) -> Preset | None:
    return next((p for p in PRESETS if p.id == pid), None)
