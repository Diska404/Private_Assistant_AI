"""Data behind the workspace graph. Edges describe ownership, never inferred thoughts."""
from collections import deque
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    group: str
    detail: str
    action: str
    target: str = ""


REPORTS = {
    "personal-models": ("Uji model Asisten/Chat/Secret 0.33", "PERSONAL_MODELS_V033.md"),
    "gpu-contract": ("GPU & Dual 0.21", "GPU_ROUTING_V021.md"),
    "responsive-pipeline": ("Reaksi & GPU 0.20", "RESPONSIVE_PIPELINE_V020.md"),
    "guide": ("Panduan Leva", "APP_README.md"),
    "duplex-review": ("Kajian full duplex", "FULL_DUPLEX_VIDEO_REVIEW.md"),
    "hud-review": ("Kajian HUD & REA", "JARVIS_HUD_VIDEO_REVIEW.md"),
    "voice-packs": ("Voice Pack Manager", "VOICE_PACKS.md"),
    "leva-research": ("Riset suara Leva", "LEVA_VOICE_RESEARCH.md"),
    "assistant-update": ("Asisten & Jepang 0.10", "ASSISTANT_V010_PROOF.md"),
}


def inventory(profiles):
    nodes = [
        Node("leva", "Leva", "core", "Ruang kerja Leva. Pilih simpul untuk melihat sumber dan tindakan yang tersedia.", "chat"),
        Node("chat", "Percakapan", "module", "Google Hybrid, Qwen 4B atau Saluki 27B. Model memilih skill host dan menerima hasil tindakan. Riwayat percakapan hanya selama sesi.", "chat"),
        Node("chrome", "Chrome", "module", "Profil dibaca dari instalasi Chrome lokal. Pilih profil sebelum membukanya. Pemulihan tab dan skip iklan belum tersedia.", "profiles"),
        Node("voice", "Google Live · Tidak Direkomendasikan", "module", "Percakapan Google Live: mendengar saat memutar suara, dengan interupsi. Mikrofon hanya aktif setelah Mulai suara di panel suara.", "voice"),
        Node("duplex", "Duplex Lab", "module", "Uji fragmen teks Qwen 35B + MicroTurn LoRA atau baseline 4B. Replay manual mencatat hasil terlambat; batas ketat 600 ms dapat diuji. Belum STT/TTS mikrofon lokal.", "duplex"),
        Node("memory", "Preferensi", "module", "Pengaturan, alias dan hitungan kebiasaan pada D. Catatan yang diminta disimpan tersedia lewat tombol Memori; percakapan tidak direkam otomatis.", "settings"),
        Node("reports", "Dokumen", "module", "Panduan dan kajian pengembangan lokal. Pilih dokumen untuk membacanya di dalam Leva.", "report", "guide"),
    ]
    edges = [("leva", n.id) for n in nodes[1:]]
    for profile in profiles:
        ident = "profile:" + profile["id"]
        nodes.append(Node(ident, profile["name"], "profile",
                          "Profil Chrome lokal · " + profile["profile_directory"] + "\nPilih Buka profil untuk mengirim perintah ke pengendali desktop.",
                          "profile", profile["id"]))
        edges.append(("chrome", ident))
    for ident, (label, filename) in REPORTS.items():
        nodes.append(Node(ident, label, "document", "Sumber: " + filename + "\nDokumen proyek lokal, bukan hasil analisis REA yang berjalan.", "report", ident))
        edges.append(("reports", ident))
    return nodes, edges


def filtered(nodes, edges, query):
    query = query.strip().casefold()
    ids = {n.id for n in nodes if not query or query in (n.label + " " + n.group).casefold()}
    return [n for n in nodes if n.id in ids], [(a, b) for a, b in edges if a in ids and b in ids]


def shortest_path(edges, first, last):
    graph = {}
    for a, b in edges:
        graph.setdefault(a, []).append(b)
        graph.setdefault(b, []).append(a)
    if first not in graph or last not in graph:
        return []
    queue = deque([[first]])
    seen = {first}
    while queue:
        path = queue.popleft()
        if path[-1] == last:
            return path
        for node in graph[path[-1]]:
            if node not in seen:
                seen.add(node)
                queue.append(path + [node])
    return []


def coordinates(nodes):
    """A stable layout of actual module, profile and document records."""
    points = {"leva": (0., 0., 0.)}
    hubs = [n for n in nodes if n.group == "module"]
    for i, node in enumerate(hubs):
        angle = -math.pi / 2 + i * 2 * math.pi / max(1, len(hubs))
        points[node.id] = (math.cos(angle) * .53, math.sin(angle) * .53, .16 * math.sin(i * 2))
    for group, parent, radius in [("profile", "chrome", .34), ("document", "reports", .30)]:
        children = [n for n in nodes if n.group == group]
        px, py, pz = points.get(parent, (0, 0, 0))
        for i, node in enumerate(children):
            angle = i * 2 * math.pi / max(1, len(children))
            points[node.id] = (px + math.cos(angle) * radius, py + math.sin(angle) * radius,
                               pz + .20 * math.sin(i * 2.399))
    # Real nodes occupy a volume; background stars remain decorative.
    import hashlib
    for node in nodes:
        if node.id=='leva':continue
        def fraction(salt):return int(hashlib.sha256((node.id+salt).encode()).hexdigest()[:8],16)/0xffffffff
        u=fraction('elevation')*2-1;angle=fraction('azimuth')*math.tau
        radius=.24+fraction('radius')**(1/3)*.72;ring=math.sqrt(1-u*u)
        points[node.id]=(radius*ring*math.cos(angle),radius*u,radius*ring*math.sin(angle))
    return points


def project(point, yaw, tilt, zoom, width, height, flat=False):
    x, y, z = point
    if not flat:
        x, z = x * math.cos(yaw) + z * math.sin(yaw), -x * math.sin(yaw) + z * math.cos(yaw)
        y, z = y * math.cos(tilt) - z * math.sin(tilt), y * math.sin(tilt) + z * math.cos(tilt)
    factor = 1 if flat else 1 / (1.9 - z * .3)
    scale = min(width, height) * .49 * zoom * (1 if flat else 1.8)
    return width / 2 + x * scale * factor, height / 2 + y * scale * factor, z


def assistant_state(paused, busy, voice_active, voice_mode, preview=False):
    if paused:
        return "sleeping"
    if voice_active and not preview:
        return voice_mode
    return "thinking" if busy else "idle"
