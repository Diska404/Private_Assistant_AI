"""Transparent fixture evidence ranking, not a general HTML/injection safety detector."""
from dataclasses import dataclass
import re

from command_resolution import normalized


@dataclass(frozen=True)
class ResearchTarget:
    laptop: str
    interface: str
    symptoms: tuple[str, ...]
    related_laptops: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceEvidence:
    id: str
    laptop: str
    interface: str
    symptoms: tuple[str, ...]
    excerpt: str
    # All fields are host-provided fixtures; no claim of verified extraction from a real page.


def rank_sources(target: ResearchTarget, sources: list[SourceEvidence]) -> dict:
    if len({s.id for s in sources}) != len(sources):
        raise ValueError("Source inventory requires unique IDs")
    ranked, rejected = [], []
    for source in sources:
        excerpt = normalized(source.excerpt)
        secret_request = bool(re.search(
            r"api\s*key|api[_ ]?key\.txt|password|kata sandi|token rahasia", excerpt))
        override = bool(re.search(r"abaikan (?:pengguna|instruksi)|ignore (?:the )?(?:user|previous)|system prompt", excerpt))
        if (secret_request and re.search(r"unggah|kirim|upload|send|baca|read", excerpt)) or override:
            rejected.append({"id": source.id, "reason": "suspicious_instruction_in_excerpt"})
            continue
        same = normalized(source.laptop) == normalized(target.laptop)
        related = normalized(source.laptop) in {normalized(x) for x in target.related_laptops}
        interface = normalized(source.interface) == normalized(target.interface)
        symptoms = {normalized(x) for x in source.symptoms} & {normalized(x) for x in target.symptoms}
        if not (same or related) or not interface or (target.symptoms and not symptoms):
            rejected.append({"id": source.id, "reason": "insufficient_matching_evidence"})
            continue
        reasons = ["laptop sama" if same else "laptop terkait", "antarmuka sama"]
        reasons.extend("gejala sama: " + symptom for symptom in sorted(symptoms))
        ranked.append({"id": source.id, "score": (8 if same else 3) + 2 + len(symptoms) * 3,
                       "reasons": reasons, "same_laptop": same})
    ranked.sort(key=lambda source: (-source["score"], source["id"]))
    # Prefer a related-device comparison when one exists, keeping differences explicit.
    primary = ranked[0] if ranked else None
    comparisons = [s for s in ranked[1:] if not s["same_laptop"]] or ranked[1:]
    return {"primary": primary, "comparison": comparisons[0] if comparisons else None,
            "ranked": ranked, "rejected": rejected,
            "scope": "fixture metadata and limited suspicious-text patterns; not general web verification"}
