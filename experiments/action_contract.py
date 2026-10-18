"""State-checked simulation tools. This module never controls desktop applications."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json


SCHEMAS = {
    "ask_profile": {}, "open_profile": {"profile": "string"},
    "open_youtube": {"profile": "string"},
    "restore_session": {"profile": "string", "session_id": "string"},
    "ask_session": {"profile": "string"}, "handoff": {},
    "suggest_profile": {"profile": "string"},
    "schedule_sleep": {"resume_at": "string", "observe_minutes": "integer", "sleep_minutes": "integer"},
    "ask_schedule": {}, "cancel_sleep": {},
    "recommend_source": {"source_id": "string", "related_source_id": "string"},
    "report_failure": {}, "unsupported": {},
}
DESCRIPTIONS = {
    "ask_profile": "Tanyakan profil ketika pilihan belum jelas. Tidak membuka aplikasi.",
    "open_profile": "Usulkan membuka satu profil yang sudah dipilih eksplisit atau dikonfirmasi.",
    "open_youtube": "Usulkan membuka profil yang dipilih dan YouTube di dalamnya sebagai satu task.",
    "restore_session": "Usulkan memulihkan sesi tersedia yang cocok dengan permintaan pengguna.",
    "ask_session": "Tanyakan sesi pengganti jika sesi yang diminta tidak tersedia; jangan memulihkan dahulu.",
    "handoff": "Serahkan pemilihan/kendali kepada pengguna dan hentikan tindakan pemilihan otomatis.",
    "suggest_profile": "Tawarkan profil berdasarkan kebiasaan dan tunggu persetujuan; tidak membuka aplikasi.",
    "schedule_sleep": "Usulkan jadwal tidur Leva: observasi 30 menit, jeda 60 menit. Bukan sleep Windows.",
    "ask_schedule": "Tanyakan jam aktif kembali dengan bahasa sehari-hari, tanpa menebak default.",
    "cancel_sleep": "Batalkan mekanisme tidur ketika ada aktivitas saat observasi; tidak perlu konfirmasi ulang.",
    "recommend_source": "Rekomendasikan sumber relevan dan tawarkan pembanding tanpa membukanya otomatis.",
    "report_failure": "Laporkan kegagalan tool yang benar-benar tercatat tanpa mengklaim berhasil.",
    "unsupported": "Nyatakan kemampuan/tindakan belum tersedia.",
}


def tool_definitions():
    return [{"type": "function", "function": {"name": name, "description": DESCRIPTIONS[name],
             "parameters": {"type": "object", "properties": {
                 key: {"type": kind} for key, kind in fields.items()},
                 "required": list(fields), "additionalProperties": False}}}
            for name, fields in SCHEMAS.items()]


@dataclass
class ActionState:
    known_profiles: list[str] = field(default_factory=list)
    authorized_profiles: list[str] = field(default_factory=list)
    active_profile: str | None = None
    sessions: dict[str, dict[str, int]] = field(default_factory=dict)
    requested_tab_count: int | None = None
    manual_control: bool = False
    pending_confirmation: bool = False
    sleep_observation_input: bool = False
    sleep_cancel_requested: bool = False
    last_tool_status: str | None = None
    available_sources: list[str] = field(default_factory=list)
    # This is a trusted simulation clock, never a timestamp supplied by a model.
    now: datetime | None = None


@dataclass(frozen=True)
class Decision:
    status: str
    reason: str


def validate_action(action, args, state: ActionState) -> Decision:
    if not isinstance(action, str) or action not in SCHEMAS or not isinstance(args, dict):
        return Decision("rejected", "unknown_action_or_arguments")
    schema = SCHEMAS[action]
    if set(args) != set(schema):
        return Decision("rejected", "argument_schema_mismatch")
    for key, kind in schema.items():
        if kind == "string" and (not isinstance(args[key], str) or not args[key].strip()):
            return Decision("rejected", "invalid_argument_type")
        if kind == "integer" and type(args[key]) is not int:
            return Decision("rejected", "invalid_argument_type")
    effects = {"open_profile", "open_youtube", "restore_session", "schedule_sleep"}
    if action in effects and state.manual_control:
        return Decision("rejected", "user_has_control")
    if action in effects and state.pending_confirmation:
        return Decision("needs_confirmation", "confirmation_pending")
    if "profile" in args:
        if args["profile"] not in state.known_profiles:
            return Decision("rejected", "unknown_profile")
        if action in {"open_profile", "open_youtube", "restore_session"}:
            if args["profile"] not in state.authorized_profiles:
                return Decision("needs_confirmation", "profile_not_confirmed")
    if action == "restore_session":
        count = state.sessions.get(args["profile"], {}).get(args["session_id"])
        if count is None:
            return Decision("rejected", "unknown_session")
        if state.requested_tab_count is not None and count != state.requested_tab_count:
            return Decision("needs_confirmation", "alternative_session_not_authorized")
    if action == "schedule_sleep":
        if args["observe_minutes"] != 30 or args["sleep_minutes"] != 60:
            return Decision("rejected", "sleep_policy_mismatch")
        try:
            wake = datetime.fromisoformat(args["resume_at"])
        except ValueError:
            return Decision("rejected", "invalid_wake_time")
        if wake.utcoffset() != timedelta(hours=7):
            return Decision("rejected", "wake_time_requires_wib")
        if state.now is None or wake <= state.now:
            return Decision("rejected", "wake_time_not_in_future")
    if action == "cancel_sleep" and not (state.sleep_observation_input or state.sleep_cancel_requested):
        return Decision("rejected", "sleep_cancel_event_missing")
    if action == "report_failure" and state.last_tool_status != "failed":
        return Decision("rejected", "failure_evidence_missing")
    if action == "recommend_source":
        if any(args[k] not in state.available_sources for k in ["source_id", "related_source_id"]):
            return Decision("rejected", "unknown_source")
        if args["source_id"] == args["related_source_id"]:
            return Decision("rejected", "duplicate_source")
    return Decision("allowed", "validated")


@dataclass(frozen=True)
class Receipt:
    request_id: str
    action: str
    arguments_json: str
    success: bool
    simulated: bool = True


class SimulationSession:
    simulated = True

    def __init__(self, state: ActionState):
        self.state = state
        self.receipts: dict[str, Receipt] = {}
        self.effect_count = 0

    def apply_user_profile_choice(self, profile: str):
        """Trusted host/UI input only; this method is never exposed as a model tool."""
        if profile not in self.state.known_profiles:
            raise ValueError("Unknown profile")
        if profile not in self.state.authorized_profiles:
            self.state.authorized_profiles.append(profile)
        self.state.pending_confirmation = False
        self.state.manual_control = False

    def execute(self, action, args, request_id: str, fail: bool = False):
        signature = json.dumps(args, sort_keys=True, ensure_ascii=False)
        if request_id in self.receipts:
            old = self.receipts[request_id]
            if old.action != action or old.arguments_json != signature:
                return Decision("rejected", "request_id_conflict"), None
            return Decision("allowed", "already_recorded_no_reexecution"), old
        decision = validate_action(action, args, self.state)
        if decision.status != "allowed":
            return decision, None
        # Evidence exists only after this simulator returns, never from model prose.
        succeeded = self.perform(action, args, fail)
        receipt = Receipt(request_id, action, signature, succeeded, self.simulated)
        self.receipts[request_id] = receipt
        if not succeeded:
            self.state.last_tool_status = "failed"
            return decision, receipt
        if action in {"open_profile", "open_youtube", "restore_session", "schedule_sleep"}:
            self.effect_count += 1
        if action in {"open_profile", "open_youtube"}:
            self.state.active_profile = args["profile"]
        if action == "handoff":
            self.state.manual_control = True
        if action == "suggest_profile":
            self.state.pending_confirmation = True
        if action in {"open_profile", "open_youtube", "restore_session", "schedule_sleep"}:
            self.state.last_tool_status = "success"
        return decision, receipt

    def perform(self, action, args, fail=False):
        """Simulation default; desktop subclass must return real execution evidence."""
        return not fail

    def render(self, receipt: Receipt | None, decision: Decision | None = None) -> str:
        if receipt is None or self.receipts.get(receipt.request_id) != receipt:
            if decision and decision.status == "needs_confirmation":
                return "Aku perlu persetujuanmu dahulu. Tindakannya belum dijalankan."
            return "Tindakan belum dijalankan; rencananya perlu diperiksa."
        if not receipt.success:
            return "Percobaan tindakan gagal dalam simulasi. Belum ada keberhasilan yang terverifikasi."
        args = json.loads(receipt.arguments_json)
        questions = {
            "ask_profile": "Profil Chrome mana yang ingin kamu gunakan?",
            "ask_session": "Sesi yang diminta belum tersedia. Mau memilih sesi lain?",
            "handoff": "Baik, silakan pilih sendiri. Aku tunggu perintah berikutnya.",
            "ask_schedule": "Jam berapa kamu ingin aku aktif kembali?",
            "unsupported": "Kemampuan itu belum tersedia pada percobaan ini.",
            "report_failure": "Tindakan sebelumnya gagal. Aku belum bisa menyatakan berhasil.",
        }
        if receipt.action in questions:
            return questions[receipt.action]
        if receipt.action == "suggest_profile":
            return f"Pakai profil {args['profile']} seperti biasanya?"
        completed = {
            "open_profile": lambda: f"Dalam simulasi, profil {args['profile']} sudah dibuka.",
            "open_youtube": lambda: f"Dalam simulasi, YouTube pada profil {args['profile']} sudah dibuka.",
            "restore_session": lambda: f"Dalam simulasi, sesi yang dipilih pada profil {args['profile']} sudah dipulihkan.",
            "schedule_sleep": lambda: "Dalam simulasi, jadwal istirahat Leva sudah tercatat sampai "
                + datetime.fromisoformat(args["resume_at"]).strftime("%H.%M WIB pada %d-%m-%Y") + ".",
            "cancel_sleep": lambda: "Dalam simulasi, mekanisme tidur sudah dibatalkan. Aku siap menerima perintah.",
            "recommend_source": lambda: f"Sumber {args['source_id']} menjadi pilihan utama; "
                f"sumber {args['related_source_id']} tersedia sebagai pembanding. Mau melihatnya?",
        }
        return completed[receipt.action]()


@dataclass
class SleepStateMachine:
    mode: str = "off"
    next_transition: datetime | None = None

    def arm(self, wake: datetime):
        if wake.tzinfo is None:
            raise ValueError("Timezone required")
        self.mode, self.next_transition = "paused", wake

    def cancel(self):
        self.mode, self.next_transition = "off", None

    def advance(self, now: datetime, activity: bool = False):
        if self.mode == "off":
            return self.mode
        # Catch up scheduled boundaries before interpreting the current input event.
        while self.next_transition is not None and now >= self.next_transition:
            boundary = self.next_transition
            if self.mode == "paused":
                self.mode, self.next_transition = "observing", boundary + timedelta(minutes=30)
            else:
                self.mode, self.next_transition = "paused", boundary + timedelta(minutes=60)
        if self.mode == "observing" and activity:
            self.cancel()
        return self.mode
