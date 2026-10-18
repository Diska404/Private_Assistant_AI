"""Bounded Indonesian command helpers; no browser reads, inference or OS changes."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
import unicodedata

WIB = timezone(timedelta(hours=7))


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    aliases: tuple[str, ...] = ()


class ProfileCatalog:
    """IDs come from the trusted host inventory, never an LLM-generated identifier."""
    def __init__(self, profiles: list[Profile]):
        self.profiles = {p.id: p for p in profiles}
        if len(self.profiles) != len(profiles) or any(not p.id or not p.name.strip() for p in profiles):
            raise ValueError("Profile inventory requires unique nonempty IDs and names")

    def matches(self, text: str) -> list[Profile]:
        value = normalized(text)
        explicit = [p for p in self.profiles.values() if re.search(
            r"(?<![\w-])" + re.escape(normalized(p.id)) + r"(?![\w-])", value)]
        if explicit:
            return explicit
        occurrences = []
        for profile in self.profiles.values():
            labels = (profile.name, *profile.aliases)
            for label in labels:
                if label.strip():
                    occurrences.extend((profile, m.start(), m.end()) for m in re.finditer(
                        r"(?<!\w)" + re.escape(normalized(label)) + r"(?!\w)", value))
        # 'User 1' inside 'User 1-1' is not a second independent choice.
        maximal = [p for p, start, end in occurrences if not any(
            other_start <= start and other_end >= end and (other_start < start or other_end > end)
            for _, other_start, other_end in occurrences)]
        return list({p.id: p for p in maximal}.values())

    def label(self, profile: Profile) -> str:
        duplicate = sum(normalized(p.name) == normalized(profile.name) for p in self.profiles.values()) > 1
        return f"{profile.name} [{profile.id}]" if duplicate else profile.name

    def resolve_label(self, value: str) -> Profile | None:
        """Whole labels only; accept the harmless Chrome/profile prefix, never fuzzy names."""
        if not isinstance(value, str):
            return None
        label = normalized(value)
        if value in self.profiles:
            return self.profiles[value]
        candidates = []
        for profile in self.profiles.values():
            for name in (profile.name, *profile.aliases):
                base = normalized(name)
                if label in {base, "chrome " + base, "profil " + base, "chrome profil " + base}:
                    candidates.append(profile)
                    break
        return candidates[0] if len(candidates) == 1 else None


ONES = {"nol": 0, "satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5,
        "enam": 6, "tujuh": 7, "delapan": 8, "sembilan": 9, "sepuluh": 10,
        "sebelas": 11, "dua belas": 12, "tiga belas": 13, "empat belas": 14,
        "lima belas": 15, "enam belas": 16, "tujuh belas": 17, "delapan belas": 18,
        "sembilan belas": 19, "dua puluh": 20, "dua puluh satu": 21,
        "dua puluh dua": 22, "dua puluh tiga": 23, "dua puluh empat": 24}
for tens_word, tens_value in [("dua", 20), ("tiga", 30), ("empat", 40), ("lima", 50),
                              ("enam", 60), ("tujuh", 70), ("delapan", 80), ("sembilan", 90)]:
    ONES[tens_word + " puluh"] = tens_value
    for ones_word, ones_value in list(ONES.items()):
        if 1 <= ones_value <= 9:
            ONES[tens_word + " puluh " + ones_word] = tens_value + ones_value
NUMBER = r"(?:\d{1,2}|" + "|".join(re.escape(k) for k in sorted(ONES, key=len, reverse=True)) + r")"


def number(value: str) -> int:
    return int(value) if value.isdigit() else ONES[value]


def tab_count(text: str) -> int | None:
    value = normalized(text)
    matches = list(re.finditer(r"(?<!\w)(\d{1,3}|" + NUMBER + r")\s*tab\b", value))
    counts = []
    for match in matches:
        preceding = value[:match.start()].split()
        # Do not accept a suffix of an unsupported/invalid compound number as the full count.
        if preceding and preceding[-1] in {*ONES, "puluh", "belas", "seratus", "ratus", "ribu"}:
            return None
        counts.append(number(match.group(1)))
    return counts[0] if len(counts) == 1 and counts[0] > 0 else None


@dataclass(frozen=True)
class TimeResolution:
    wake: datetime | None
    reason: str
    question: str | None = None


def resolve_wake(text: str, now: datetime) -> TimeResolution:
    """Supported grammar only. Ambiguous/out-of-range/unsupported expressions ask again."""
    if now.tzinfo is None:
        raise ValueError("Trusted clock requires timezone")
    now = now.astimezone(WIB)
    value = normalized(text)
    # Do not guess through negations, dates or unsupported arithmetic/timezones.
    if re.search(r"\b(bukan|jangan|tidak|nggak|enggak|gak|ga|tak|belum|kecuali|tanggal|lusa|kemarin|wita|wit|utc|wib\s*[+-])\b", value):
        return TimeResolution(None, "unsupported_time_expression", "Sebutkan satu waktu aktif kembali dalam WIB, misalnya besok pukul 04.30.")
    if re.search(r"\b\d+\s*(menit|jam)\s*lagi\b|\b(kurang|seperempat|lewat)\b", value):
        return TimeResolution(None, "unsupported_time_expression", "Jam tepatnya berapa dalam WIB?")
    patterns = [
        ("clock", r"(?<![\w:.])(\d{1,2})[:.](\d{2})(?![\w:.])"),
        ("half", r"\bsetengah\s+(" + NUMBER + r")(?!\w)"),
        ("hour", r"\b(?:jam|pukul)\s+(" + NUMBER + r")(?![\w:.])"),
    ]
    matches = []
    for kind, pattern in patterns:
        for match in re.finditer(pattern, value):
            # 'jam 04:30' is one clock expression, not a separate bare-hour proposal.
            if kind == "hour" and any(start <= match.end() <= end for _, _, start, end in matches):
                continue
            matches.append((kind, match, match.start(), match.end()))
    if not matches:
        return TimeResolution(None, "time_missing", "Jam berapa kamu ingin aku aktif kembali?")
    if len(matches) != 1:
        return TimeResolution(None, "multiple_times", "Pilih satu waktu aktif kembali dalam WIB.")
    kind, match, _, _ = matches[0]
    if re.match(r"\s+(?:" + NUMBER + r"|puluh|belas)\b", value[match.end():]):
        return TimeResolution(None, "unsupported_number_expression", "Sebutkan waktu dalam format angka 24 jam, misalnya 04.30.")
    hour = number(match.group(1))
    minute = int(match.group(2)) if kind == "clock" else 30 if kind == "half" else 0
    if kind == "half":
        if not 1 <= hour <= 12:
            return TimeResolution(None, "invalid_time", "Jam yang dimaksud berapa? Gunakan format 24 jam, misalnya 04.30.")
        hour -= 1  # Indonesian 'setengah lima' = 04:30, not 05:30.
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return TimeResolution(None, "invalid_time", "Waktunya belum valid. Sebutkan jam dan menit dalam format 24 jam.")
    periods = re.findall(r"\b(subuh|pagi|siang|sore|malam)\b", value)
    if len(set(periods)) > 1:
        return TimeResolution(None, "ambiguous_period", "Waktu aktifnya pagi atau sore/malam? Sebutkan satu waktu.")
    if periods:
        period = periods[0]
        candidate_hours = {hour}
        if hour < 12:
            candidate_hours.add(hour + 12)
        elif hour == 12:
            candidate_hours.add(0)
        ranges = {"subuh": {0, 1, 2, 3, 4, 5}, "pagi": set(range(0, 12)),
                  "siang": {11, 12, 13, 14}, "sore": {15, 16, 17, 18},
                  "malam": {18, 19, 20, 21, 22, 23, 0}}
        valid = candidate_hours & ranges[period]
        if kind == "clock" and hour >= 13:
            valid &= {hour}
        if len(valid) != 1:
            return TimeResolution(None, "period_conflict", "Jam dan keterangan waktunya belum cocok. Sebutkan waktu dalam format 24 jam.")
        hour = valid.pop()
    elif kind == "half" or (kind != "clock" and 1 <= hour <= 12):
        return TimeResolution(None, "ambiguous_period", "Yang dimaksud pagi atau sore/malam? Sebutkan waktu seperti 04.30 atau 16.30.")
    target_date = now.date() + timedelta(days=1 if re.search(r"\bbesok\b", value) else 0)
    wake = datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=WIB)
    if wake <= now:
        if re.search(r"\b(hari ini|malam ini|pagi ini|siang ini|sore ini)\b", value):
            return TimeResolution(None, "explicit_time_passed", "Waktu hari ini sudah lewat. Apakah yang dimaksud besok?")
        wake += timedelta(days=1)
    return TimeResolution(wake, "resolved")
