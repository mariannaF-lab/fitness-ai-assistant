from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Text = str


class Profile(StrictModel):
    age: int = Field(ge=18, le=120)
    goal: str = Field(min_length=3, max_length=300)
    fitness_level: Literal["beginner", "intermediate", "advanced"]
    current_activity: str = Field(min_length=2, max_length=500)
    sessions_per_week: int = Field(ge=1, le=7)
    session_duration_minutes: int = Field(ge=10, le=180)
    training_location: Literal["home", "gym", "outdoor"]
    equipment: list[str] = Field(max_length=15)
    health_info_status: Literal["provided", "declined"]
    limitations: str | None = Field(default=None, max_length=1000)
    preferences: str = Field(default="", max_length=500)
    data_consent: Literal[True]

    @model_validator(mode="after")
    def validate_health(self):
        if self.health_info_status == "provided" and not self.limitations:
            raise ValueError("Укажите ограничения или явно напишите: ограничений нет")
        if self.health_info_status == "declined":
            self.limitations = None
        if any(not x.strip() or len(x) > 80 for x in self.equipment):
            raise ValueError("Некорректное название оборудования")
        return self


class Exercise(StrictModel):
    name: str = Field(min_length=2, max_length=150)
    sets: int = Field(ge=1, le=10)
    repetitions: str | None = Field(default=None, max_length=40, description='Только число или диапазон: 10 или 8-12. Без слов. null при seconds.')
    seconds: int | None = Field(default=None, ge=5, le=3600, description='Целое число секунд, не диапазон. null при repetitions.')
    rest_seconds: int = Field(ge=0, le=600)
    equipment: list[str] = Field(max_length=10)
    technique: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def dosage(self):
        import re
        if bool(self.repetitions) == (self.seconds is not None):
            raise ValueError("Укажите либо repetitions, либо seconds")
        if self.repetitions and not re.fullmatch(r"[1-9]\d?(?:[-–][1-9]\d?)?", self.repetitions):
            raise ValueError("Повторения: положительное число или диапазон, например 8–12")
        if self.repetitions:
            values = [int(v) for v in re.split(r"[-–]", self.repetitions)]
            if values[-1] < values[0]:
                raise ValueError("Неверный диапазон повторений")
        return self


class Workout(StrictModel):
    day: int = Field(ge=1, le=7)
    name: str = Field(min_length=2, max_length=150)
    duration_minutes: int = Field(ge=10, le=180)
    warmup: str = Field(min_length=3, max_length=1500)
    warmup_minutes: int = Field(ge=1, le=30)
    exercises: list[Exercise] = Field(min_length=1, max_length=12)
    cooldown: str = Field(min_length=3, max_length=1500)
    cooldown_minutes: int = Field(ge=1, le=30)


class Program(StrictModel):
    title: str = Field(min_length=3, max_length=150)
    rationale: str = Field(min_length=3, max_length=1500)
    recovery: str = Field(min_length=3, max_length=1500)
    load_guidance: str = Field(min_length=3, max_length=1500)
    progression: str = Field(min_length=3, max_length=1500)
    workouts: list[Workout] = Field(min_length=1, max_length=7)


class ProgramResult(StrictModel):
    status: Literal["ready", "needs_clarification", "requires_professional_review"]
    message: str = Field(max_length=2000)
    questions: list[str] = Field(max_length=3, description='Пустой список при ready. Только вопросы для уточнения до создания программы.')
    changes: list[str] = Field(default_factory=list, max_length=20)
    program: Program | None

    @model_validator(mode="after")
    def status_program(self):
        if (self.status == "ready") != (self.program is not None):
            raise ValueError("Статус не соответствует наличию программы")
        if self.status == "ready" and self.questions:
            raise ValueError("Готовая программа не должна требовать уточнений")
        return self


class Explanation(StrictModel):
    purpose: str = Field(min_length=2, max_length=1500)
    equipment: str = Field(min_length=2, max_length=500)
    starting_position: str = Field(min_length=2, max_length=1500)
    steps: list[str] = Field(min_length=1, max_length=15)
    breathing: str = Field(min_length=2, max_length=1000)
    mistakes: list[str] = Field(max_length=10)
    easier_option: str = Field(min_length=2, max_length=1500)
    stop_when: str = Field(min_length=2, max_length=1500)


class ExplanationResult(StrictModel):
    status: Literal["ready", "needs_clarification", "requires_professional_review"]
    message: str = Field(max_length=2000)
    questions: list[str] = Field(max_length=3)
    explanation: Explanation | None

    @model_validator(mode="after")
    def status_explanation(self):
        if (self.status == "ready") != (self.explanation is not None):
            raise ValueError("Статус не соответствует объяснению")
        return self


class Feedback(StrictModel):
    program_id: int = Field(gt=0)
    workout_index: int = Field(ge=0, le=6)
    completion_status: Literal["completed", "partial", "skipped"]
    actual_duration_minutes: int | None = Field(default=None, ge=1, le=360)
    perceived_difficulty: int | None = Field(default=None, ge=1, le=10)
    pain_reported: bool | None = None
    comment: str = Field(default="", max_length=1500)

    @model_validator(mode="after")
    def completed_fields(self):
        if self.completion_status != "skipped" and (
            self.actual_duration_minutes is None or self.perceived_difficulty is None
        ):
            raise ValueError("Для выполненного занятия укажите время и сложность")
        return self


def check_program(program: Program, profile: Profile):
    import re
    if len(program.workouts) != profile.sessions_per_week:
        raise ValueError("Количество тренировок не совпадает с анкетой")
    if len({w.day for w in program.workouts}) != len(program.workouts):
        raise ValueError("Дни тренировок повторяются")
    allowed = {x.casefold() for x in profile.equipment}
    for w in program.workouts:
        if w.duration_minutes > profile.session_duration_minutes:
            raise ValueError("Превышено доступное время")
        seconds = (w.warmup_minutes + w.cooldown_minutes) * 60
        for e in w.exercises:
            if re.search(r'\b(цепь|круг)\s+[a-zа-я0-9]',e.name,re.IGNORECASE):
                raise ValueError('Каждая запись exercises должна описывать одно упражнение, а не цепь или круг из нескольких')
            implicit = {'резинк':'резин', 'гантел':'гантел', 'штанг':'штанг', 'стул':'стул', 'стол':'стол', 'возвышен':'опор'}
            for term, stem in implicit.items():
                if term in e.name.casefold() and not any(stem in item or term in item for item in allowed):
                    raise ValueError('В названии упражнения указан неподтверждённый инвентарь или опора; замените упражнение, не скрывайте оборудование в пустом списке')
            if not {x.casefold() for x in e.equipment}.issubset(allowed):
                raise ValueError("Используется отсутствующее оборудование")
            reps = int(e.repetitions.replace('–', '-').split('-')[-1]) if e.repetitions else 0
            seconds += e.sets * (e.seconds or reps * 3) + (e.sets - 1) * e.rest_seconds
        if seconds > w.duration_minutes * 60:
            raise ValueError(f"День {w.day}: подходы, отдых, разминка и завершение требуют минимум {seconds} сек., доступно {w.duration_minutes*60} сек.")
