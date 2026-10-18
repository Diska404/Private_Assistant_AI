"""Task-scoped multi-turn command experiment; every executor remains simulated."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import re

from action_contract import ActionState, Decision, SimulationSession, SleepStateMachine, validate_action
from command_resolution import ProfileCatalog, normalized, resolve_wake, tab_count
from source_relevance import ResearchTarget, SourceEvidence, rank_sources

NEGATION = r"\b(bukan|jangan|tidak|nggak|enggak|gak|ga|tak|belum)\b"


@dataclass(frozen=True)
class Task:
    kind: str
    profile_id: str | None = None
    count: int | None = None
    offered_sessions: tuple[str, ...] = ()


@dataclass(frozen=True)
class Plan:
    turn: int
    request_id: str
    text: str
    action: str
    arguments_json: str
    reply: str | None = None
    profile_id: str | None = None
    wake: datetime | None = None

    @property
    def args(self):
        return json.loads(self.arguments_json)


class ConversationController:
    """A deliberately bounded host grammar, not general natural-language authorization."""
    def __init__(self, catalog: ProfileCatalog, sessions: dict[str, dict[str, int]] | None = None,
                 habits: dict[str, str] | None = None, research_target: ResearchTarget | None = None,
                 sources: list[SourceEvidence] | None = None):
        self.catalog = catalog
        self.sessions = sessions or {}
        self.habits = habits or {}
        if any(pid not in catalog.profiles for pid in [*self.sessions, *self.habits.values()]):
            raise ValueError("Unknown profile ID in trusted fixture")
        self.pending: Task | None = None
        self.active_profile_id: str | None = None
        self.sleep = SleepStateMachine()
        self.executor = SimulationSession(ActionState(known_profiles=[p.name for p in catalog.profiles.values()]))
        self.research_target, self.sources = research_target, sources or []
        self.research_assessment = None
        self.turn = 0
        self.current_plan: Plan | None = None
        self.results: dict[str, dict] = {}

    def _plan(self, text, request_id, action, args=None, reply=None, profile_id=None, wake=None):
        plan = Plan(self.turn, request_id, text, action,
                    json.dumps(args or {}, ensure_ascii=False, sort_keys=True), reply, profile_id, wake)
        self.current_plan = plan
        return plan

    def _profile_question(self, text, request_id, task):
        self.pending = task
        return self._plan(text, request_id, "ask_profile",
                          reply="Profil Chrome mana yang ingin kamu gunakan: "
                          + ", ".join(self.catalog.label(p) for p in self.catalog.profiles.values()) + "?")

    def _profile_task(self, text, request_id, task, profile):
        self.pending = None
        state = self.executor.state
        state.authorized_profiles = [profile.name]  # Authorization is scoped to this task/turn.
        state.pending_confirmation = False
        if task.kind == "restore":
            available = self.sessions.get(profile.id, {})
            matches = [sid for sid, count in available.items() if count == task.count]
            state.sessions = {profile.name: dict(available)}
            state.requested_tab_count = task.count
            if len(matches) == 1:
                return self._plan(text, request_id, "restore_session",
                                  {"profile": profile.name, "session_id": matches[0]}, profile_id=profile.id)
            self.pending = Task("session", profile.id, task.count, tuple(available))
            choices = ", ".join(f"{sid} ({count} tab)" for sid, count in available.items()) or "belum ada sesi"
            reason = "Ada beberapa sesi dengan jumlah tab tersebut" if matches else "Sesi yang kamu minta belum ditemukan"
            return self._plan(text, request_id, "ask_session", {"profile": profile.name},
                              f"{reason}. Yang tersedia: {choices}. Sesi mana yang ingin dipulihkan?", profile.id)
        action = "open_youtube" if task.kind == "youtube" else "open_profile"
        reply = None
        if self.catalog.label(profile) != profile.name:
            reply = "Dalam simulasi, " + ("YouTube pada profil " if action == "open_youtube" else "profil ") + self.catalog.label(profile) + " sudah dibuka."
        return self._plan(text, request_id, action, {"profile": profile.name}, reply, profile_id=profile.id)

    def _start_task(self, text, request_id, task):
        self.executor.state.manual_control = False  # Only a new explicit supported command resumes control.
        matches = self.catalog.matches(text)
        choice_text = normalized(text)
        # A bounded correction clause can identify the positive choice, never a rejected name.
        correction = re.search(r"\b(?:bukan|jangan)\b.+?[,;]\s*(?:pakai|pake|gunakan|buka)\s+(.+)", normalized(text))
        if correction:
            choice_text = correction.group(1)
            matches = self.catalog.matches(choice_text)
        elif re.search(NEGATION, normalized(text)):
            return self._profile_question(text, request_id, task)
        if len(matches) == 1:
            profile = matches[0]
            # An exact observed name inside a longer unknown label is not a new alias:
            # the real name 'Frontline' does not establish 'Frontline Raver' automatically.
            explicit_id = normalized(profile.id) not in {normalized(profile.name), *(normalized(a) for a in profile.aliases)} and re.search(
                r"(?<![\w-])" + re.escape(normalized(profile.id)) + r"(?![\w-])", choice_text)
            if not explicit_id:
                candidate = choice_text
                for marker in [r"\b(?:profil|profile)\s+", r"\b(?:pakai|pake|gunakan)\s+",
                               r"\bdi\s+", r"\bchrome\s+", r"\b(?:buka|bukakan|bukain)\s+"]:
                    selector = re.search(marker + r"(.+)", choice_text)
                    if selector:
                        candidate = selector.group(1)
                        break
                candidate = re.split(r"\b(?:terus|lalu|kemudian|dan)\b|[,;]", candidate)[0].strip(" .!?")
                candidate = re.sub(r"(?:\s+(?:ya|dong|aja|saja|dulu))+$", "", candidate)
                resolved = self.catalog.resolve_label(candidate)
                if resolved is None or resolved.id != profile.id:
                    return self._profile_question(text, request_id, task)
            return self._profile_task(text, request_id, task, matches[0])
        if matches:
            return self._profile_question(text, request_id, task)
        if re.search(r"\b(profil|profile)\b", normalized(text)):
            return self._profile_question(text, request_id, task)
        habit_id = self.habits.get(task.kind)
        if habit_id is not None:
            self.pending = Task("confirm_" + task.kind, habit_id, task.count)
            return self._plan(text, request_id, "suggest_profile",
                              {"profile": self.catalog.profiles[habit_id].name},
                              reply="Pakai profil " + self.catalog.label(self.catalog.profiles[habit_id]) + " seperti biasanya?",
                              profile_id=habit_id)
        return self._profile_question(text, request_id, task)

    def prepare(self, text: str, request_id: str, now: datetime) -> Plan:
        if not isinstance(text, str) or not text.strip() or not request_id:
            raise ValueError("Nonempty trusted user text and request ID required")
        if request_id in self.results:
            raise ValueError("Use replay() for a completed request ID")
        if now.tzinfo is None:
            raise ValueError("Trusted clock requires timezone")
        self.turn += 1
        self.current_plan = None
        state = self.executor.state
        state.now = now
        state.authorized_profiles = []
        state.pending_confirmation = False
        state.requested_tab_count = None
        state.sleep_cancel_requested = False
        value = normalized(text).strip(" .!?")
        old_pending = self.pending
        self.pending = None

        if re.search(r"\b(contoh|terjemahkan|jelaskan|kutipan|seandainya|jika|kalau)\b", value):
            return self._plan(text, request_id, "unsupported",
                              reply="Kalimat ini belum menjadi perintah langsung yang didukung percobaan. Jelaskan tindakan yang ingin dijalankan.")

        if re.search(r"\b(biarkan|biar)\s+(saya|aku)\b.*(pilih|cari|sendiri)|\b(saya|aku)\s+yang\s+(pilih|memilih)\b", value):
            return self._plan(text, request_id, "handoff")
        if value in {"batal", "batalkan", "tidak", "nggak", "jangan", "ga", "gak", "tidak jadi"}:
            if old_pending is None and self.sleep.mode != "off" and value in {"batal", "batalkan", "tidak jadi"}:
                state.sleep_cancel_requested = True
                state.manual_control = False
                return self._plan(text, request_id, "cancel_sleep")
            # A pending question takes precedence over unrelated already-armed tasks.
            return self._plan(text, request_id, "handoff", reply="Baik, permintaan yang menunggu jawaban sudah dibatalkan.")
        if re.search(r"\b(batalkan|hapus|hentikan)\b.*\b(tidur|jadwal|mekanisme)\b", value):
            if re.search(NEGATION, value):
                return self._plan(text, request_id, "unsupported", reply="Jadwal tidak diubah. Sebutkan langsung perubahan yang kamu inginkan.")
            state.sleep_cancel_requested = True
            state.manual_control = False
            return self._plan(text, request_id, "cancel_sleep")

        is_restore = bool(re.search(r"\b(pulihkan|memulihkan|balikin|kembalikan)\b", value))
        is_open = bool(re.search(r"\b(buka|bukakan|bukain|bukalah|masuk|youtube-in|youtubein)\b", value))
        is_sleep = bool(re.search(r"\b(tidur|bobok)\b", value))
        is_research = bool(re.search(r"\b(cari|carikan|pilih|rekomendasikan)\b", value) and "egpu" in value)
        if is_restore:
            count = tab_count(text)
            if count is None:
                return self._plan(text, request_id, "unsupported", reply="Berapa tab yang ingin kamu pulihkan, dan pada profil mana?")
            return self._start_task(text, request_id, Task("restore", count=count))
        if is_open and ("chrome" in value or "youtube" in value or self.catalog.matches(text)):
            return self._start_task(text, request_id, Task("youtube" if "youtube" in value else "chrome"))
        if is_sleep or (old_pending and old_pending.kind == "time"):
            # An unrelated command invalidates a pending time question instead of inheriting it.
            if old_pending and not is_sleep and re.search(r"\b(buka|cari|kirim|hapus)\b", value):
                return self._plan(text, request_id, "unsupported")
            result = resolve_wake(text, now)
            if result.wake is None:
                self.pending = Task("time")
                return self._plan(text, request_id, "ask_schedule", reply=result.question)
            state.manual_control = False
            return self._plan(text, request_id, "schedule_sleep",
                              {"resume_at": result.wake.isoformat(), "observe_minutes": 30, "sleep_minutes": 60},
                              wake=result.wake)
        if is_research:
            if re.search(NEGATION, value):
                return self._plan(text, request_id, "unsupported", reply="Baik, pencarian tidak dilanjutkan.")
            if self.research_target is None:
                return self._plan(text, request_id, "unsupported", reply="Konteks perangkat dan gejala belum tersedia pada percobaan ini.")
            assessment = rank_sources(self.research_target, self.sources)
            self.research_assessment = assessment
            if not assessment["primary"] or not assessment["comparison"]:
                return self._plan(text, request_id, "unsupported", reply="Bukti contoh belum cukup untuk menawarkan sumber utama beserta pembanding yang relevan.")
            state.available_sources = [s["id"] for s in assessment["ranked"]]
            return self._plan(text, request_id, "recommend_source",
                              {"source_id": assessment["primary"]["id"],
                               "related_source_id": assessment["comparison"]["id"]})
        if old_pending and re.search(r"\b(buka|cari|kirim|hapus|buat|jalankan)\b", value):
            return self._plan(text, request_id, "unsupported",
                              reply="Permintaan sebelumnya sudah dilepas. Perintah baru ini belum didukung pada percobaan.")
        if old_pending:
            yes = value in {"ya", "iya", "yap", "betul", "boleh", "oke", "ok", "ya pakai itu"}
            matches = self.catalog.matches(text)
            if old_pending.kind.startswith("confirm_"):
                task = Task(old_pending.kind.removeprefix("confirm_"), count=old_pending.count)
                if yes:
                    return self._profile_task(text, request_id, task, self.catalog.profiles[old_pending.profile_id])
                if matches:
                    return self._start_task(text, request_id, task)
                return self._profile_question(text, request_id, task)
            if old_pending.kind in {"chrome", "youtube", "restore"}:
                if matches:
                    return self._start_task(text, request_id, old_pending)
                return self._profile_question(text, request_id, old_pending)
            if old_pending.kind == "session":
                profile = self.catalog.profiles[old_pending.profile_id]
                available = self.sessions.get(profile.id, {})
                count = tab_count(text)
                selected = [] if re.search(NEGATION, value) else [sid for sid in old_pending.offered_sessions
                            if normalized(text).strip(" .!?") == normalized(sid)
                            or (count is not None and available.get(sid) == count)]
                if len(selected) == 1:
                    state.authorized_profiles = [profile.name]
                    state.sessions = {profile.name: dict(available)}
                    state.requested_tab_count = available[selected[0]]
                    return self._plan(text, request_id, "restore_session",
                                      {"profile": profile.name, "session_id": selected[0]}, profile_id=profile.id)
                self.pending = old_pending
                return self._plan(text, request_id, "ask_session", {"profile": profile.name},
                                  "Sebutkan ID sesi atau jumlah tab dari pilihan tadi. Aku belum memulihkan apa pun.", profile.id)
        return self._plan(text, request_id, "unsupported",
                          reply="Perintah ini belum dikenali pada percobaan teks. Sebutkan aplikasi/profil atau waktu secara jelas.")

    def check_proposal(self, plan: Plan, proposal: dict) -> Decision:
        if self.current_plan != plan:
            return Decision("rejected", "stale_turn_plan")
        if not isinstance(proposal, dict) or proposal.get("error"):
            return Decision("rejected", "incomplete_or_invalid_model_response")
        action, args = proposal.get("action"), proposal.get("args")
        if action != plan.action or not isinstance(args, dict):
            return Decision("rejected", "action_does_not_match_current_task")
        args = dict(args)
        if "profile" in args:
            profile = self.catalog.resolve_label(args["profile"])
            if profile is None or profile.id != plan.profile_id:
                return Decision("rejected", "profile_does_not_match_current_task")
            args["profile"] = profile.name
        if args != plan.args:
            return Decision("rejected", "arguments_do_not_match_verified_task")
        schema_check = validate_action(action, args, self.executor.state)
        if schema_check.status != "allowed":
            return schema_check
        return Decision("allowed", "matches_verified_task")

    def commit(self, plan: Plan, proposal: dict | None = None, fail: bool = False) -> dict:
        if self.current_plan != plan:
            raise ValueError("Stale or already committed turn")
        model_check = self.check_proposal(plan, proposal) if proposal is not None else None
        # For this bounded grammar the host-resolved command is authoritative. A rejected
        # model proposal is recorded, never executed; it cannot replace or authorize the task.
        decision, receipt = self.executor.execute(plan.action, plan.args, plan.request_id, fail=fail)
        reply = self.executor.render(receipt, decision)
        if receipt and receipt.success:
            if plan.profile_id and plan.action in {"open_profile", "open_youtube", "restore_session"}:
                self.active_profile_id = plan.profile_id
            if plan.action == "schedule_sleep":
                self.sleep.arm(plan.wake)
            if plan.action == "cancel_sleep":
                self.sleep.cancel()
            if plan.reply:
                reply = plan.reply
            if plan.action == "recommend_source":
                ranked = self.research_assessment
                reply = ("Pada data contoh, sumber " + ranked["primary"]["id"] + " paling cocok: "
                         + "; ".join(ranked["primary"]["reasons"]) + ". Sumber "
                         + ranked["comparison"]["id"] + " menjadi pembanding: "
                         + "; ".join(ranked["comparison"]["reasons"]) + ". Mau melihat pembandingnya?")
        result = {"request_id": plan.request_id, "turn": plan.turn, "user": plan.text,
                  "resolution": "bounded_host_rules", "action": plan.action, "args": plan.args,
                  "profile_id": plan.profile_id, "decision": asdict(decision),
                  "model_check": asdict(model_check) if model_check else None,
                  "model_proposal_executed": False,
                  "receipt": asdict(receipt) if receipt else None, "reply": reply,
                  "pending": asdict(self.pending) if self.pending else None,
                  "sleep": {"mode": self.sleep.mode,
                            "next_transition": self.sleep.next_transition.isoformat() if self.sleep.next_transition else None},
                  "simulated_effect_count": self.executor.effect_count, "desktop_actions_executed": 0}
        self.results[plan.request_id] = result
        self.current_plan = None
        return result

    def replay(self, request_id: str, text: str) -> dict:
        old = self.results[request_id]
        if old["user"] != text:
            raise ValueError("Request ID reused for a different utterance")
        return {**old, "replayed": True}

    def handle(self, text: str, request_id: str, now: datetime) -> dict:
        if request_id in self.results:
            return self.replay(request_id, text)
        return self.commit(self.prepare(text, request_id, now))

    def observe(self, now: datetime, activity: bool = False) -> str:
        """Trusted input/timer simulation, not an event inferred from model text."""
        return self.sleep.advance(now, activity)
