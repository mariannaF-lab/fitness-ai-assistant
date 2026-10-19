import json
import unittest

from fitness.llm import GigaChat, LLMError
from fitness.models import Profile, ProgramResult, check_program
from fitness.planner import Selection, available_catalog, compose, duration_seconds, validate_selection
from tests.test_app import PROFILE


def choice(count):
    return dict(status='ready',message='Подобран план',questions=[],reason='Учтены опыт, время и цель.',
        sessions=[['wall_push','march','hip_hinge'] for _ in range(count)])


class PlannerTests(unittest.TestCase):
    def test_time_budget_across_supported_durations_and_frequencies(self):
        for minutes in [10,11,14,15,20,30,60,180]:
            for count in range(1,8):
                for level in ['beginner','intermediate','advanced']:
                    p=Profile.model_validate(PROFILE | dict(session_duration_minutes=minutes,sessions_per_week=count,fitness_level=level))
                    selection=Selection.model_validate(choice(count))
                    catalog=available_catalog(p)
                    validate_selection(selection,p,catalog)
                    result=compose(selection,p,{},catalog)
                    check_program(result.program,p)
                    self.assertEqual(len(result.program.workouts),count)
                    for w in result.program.workouts:
                        self.assertLessEqual(duration_seconds(w),minutes*60)
                        self.assertLessEqual(w.duration_minutes,minutes)

    def test_equipment_filtering(self):
        empty=available_catalog(Profile.model_validate(PROFILE))
        self.assertNotIn('chair_stand',empty)
        self.assertNotIn('dumbbell_curl',empty)
        p=Profile.model_validate(PROFILE | {'equipment':['Гантели 2 кг','Стул']})
        catalog=available_catalog(p)
        self.assertEqual(catalog['dumbbell_curl']['actual_equipment'],['Гантели 2 кг'])
        result=Selection.model_validate(choice(1) | {'sessions':[['wall_push','chair_stand','dumbbell_curl']]})
        check_program(compose(result,p,{},catalog).program,p)

    def test_invalid_ids_and_duplicates_are_not_silently_replaced(self):
        p=Profile.model_validate(PROFILE)
        for ids in [['wall_push','wall_push','march'],['wall_push','march','unknown'],['chair_stand','march','hip_hinge']]:
            with self.assertRaises(ValueError):
                validate_selection(Selection.model_validate(choice(1) | {'sessions':[ids]}),p,available_catalog(p))

    def test_real_client_dispatch_and_one_repair(self):
        g=GigaChat(); outputs=[json.dumps(choice(1) | {'sessions':[['wall_push','march','invented']]}),json.dumps(choice(1))]
        g.content=lambda messages:outputs.pop(0)
        result=g.structured('generate',{'profile':PROFILE},ProgramResult)
        self.assertEqual(result.status,'ready')
        self.assertEqual(outputs,[])
        self.assertEqual(result.program.workouts[0].exercises[0].name,'Отжимания от стены')

    def test_two_bad_selections_fail_closed(self):
        g=GigaChat(); calls=[]
        g.content=lambda messages:calls.append(1) or json.dumps(choice(1) | {'sessions':[['wall_push','march','invented']]})
        with self.assertRaises(LLMError):g.structured('generate',{'profile':PROFILE},ProgramResult)
        self.assertEqual(len(calls),2)

    def test_pain_feedback_prevents_prescription_without_calling_llm(self):
        g=GigaChat()
        def unexpected(messages):
            self.fail('Pain gate should not call LLM')
        g.content=unexpected
        result=g.structured('adapt',{'profile':PROFILE,'feedback':[{'pain_reported':True}]},ProgramResult)
        self.assertEqual(result.status,'requires_professional_review')
        self.assertIsNone(result.program)

    def test_adaptation_never_increases_repeated_exercise_dose(self):
        p=Profile.model_validate(PROFILE)
        first=compose(Selection.model_validate(choice(1)),p,{},available_catalog(p))
        p.session_duration_minutes=10
        new=compose(Selection.model_validate(choice(1)),p,{'current_program':first.model_dump(),'feedback':[{'perceived_difficulty':8}]},available_catalog(p))
        for old,e in zip(first.program.workouts[0].exercises,new.program.workouts[0].exercises):
            self.assertLessEqual(e.sets,old.sets)
            if e.seconds:self.assertLessEqual(e.seconds,old.seconds)
            if e.repetitions:self.assertLessEqual(int(e.repetitions),int(old.repetitions))
        self.assertLessEqual(duration_seconds(new.program.workouts[0]),600)

    def test_questions_are_returned_without_program(self):
        g=GigaChat()
        g.content=lambda messages:json.dumps(dict(status='needs_clarification',message='Уточните ограничения',questions=['Какие движения запрещены?'],reason='',sessions=[]))
        result=g.structured('generate',{'profile':PROFILE},ProgramResult)
        self.assertIsNone(result.program)
        self.assertEqual(len(result.questions),1)
