import json
import time

from .llm import GigaChat
from .models import Profile, ProgramResult, ExplanationResult, Feedback, check_program


class Service:
    def __init__(self, store, llm=None):
        self.store = store
        self.llm = llm or GigaChat()

    def profile(self, owner):
        raw = self.store.get_json("profiles", owner)
        if not raw:
            raise ValueError("Сначала заполните и подтвердите анкету")
        return Profile.model_validate(raw)

    def save_profile(self, owner, raw):
        profile = Profile.model_validate(raw)
        self.store.put_json("profiles", owner, profile.model_dump())
        return profile.model_dump()

    @staticmethod
    def llm_profile(profile):
        return profile.model_dump(exclude={"data_consent"})

    def generate(self, owner, changes=""):
        with self.store.job(owner):
            profile = self.profile(owner)
            records = self.store.programs(owner)
            current = next((p for p in records if p["status"] == "current"), None)
            data = {"profile": self.llm_profile(profile)}
            task = "generate"
            if changes:
                if not current:
                    raise ValueError("Сначала создайте первую программу")
                task = "adapt"
                feedback = [{k:v for k,v in item.items() if k != "program_id"} for item in self.store.feedback(owner)]
                data.update(current_program=current["body"], feedback=feedback, changed_conditions=changes)
            def validate(result):
                if result.program:
                    check_program(result.program, profile)
            result = self.llm.structured(task, data, ProgramResult, validate)
            response = {"result": result.model_dump(), "record": None}
            if result.program:
                response["record"] = self.store.save_program(owner, result.model_dump(), profile.model_dump(), self.llm.model)
            return response

    def explain(self, owner, pid, wi, ei):
        record = self.store.program(owner, pid)
        workouts = record["body"]["program"]["workouts"]
        if wi < 0 or wi >= len(workouts) or ei < 0 or ei >= len(workouts[wi]["exercises"]):
            raise ValueError("Упражнение не найдено")
        with self.store.connect() as db:
            cached = db.execute("SELECT body FROM explanations WHERE owner=? AND program_id=? AND workout=? AND exercise=?", (owner,pid,wi,ei)).fetchone()
        if cached:
            return json.loads(cached[0])
        with self.store.job(owner):
            result = self.llm.structured("explain", {"exercise":workouts[wi]["exercises"][ei],
                "relevant_profile": self.llm_profile(Profile.model_validate(record["profile"])), "program_version": record["version"]}, ExplanationResult)
            if result.explanation:
                with self.store.connect() as db:
                    db.execute("INSERT OR REPLACE INTO explanations VALUES (?,?,?,?,?)", (owner,pid,wi,ei,result.model_dump_json()))
            return result.model_dump()

    def feedback(self, owner, raw):
        feedback = Feedback.model_validate(raw)
        record = self.store.program(owner, feedback.program_id)
        if feedback.workout_index >= len(record["body"]["program"]["workouts"]):
            raise ValueError("Тренировка не найдена")
        with self.store.connect() as db:
            db.execute("INSERT INTO feedback(owner,created,body) VALUES (?,?,?)", (owner,time.time(),feedback.model_dump_json()))
        return feedback.model_dump()
