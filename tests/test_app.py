import copy
import json
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from pydantic import ValidationError

from app import create_app
from fitness.llm import GigaChat, LLMError
from fitness.models import Profile, ProgramResult, check_program
from fitness.service import Service
from fitness.store import Store

PROFILE = dict(age=28, goal="Общая физическая форма", fitness_level="beginner", current_activity="Прогулки",
    sessions_per_week=1, session_duration_minutes=30, training_location="home", equipment=[],
    health_info_status="provided", limitations="Ограничений нет", preferences="", data_consent=True)
RESULT = dict(status="ready", message="План на неделю", questions=[], changes=[], program=dict(
    title="Первая неделя", rationale="Постепенное начало", recovery="Прогулки в свободные дни",
    load_guidance="Посильный темп", progression="По обратной связи", workouts=[dict(day=2,name="Знакомство с движением",
        duration_minutes=20,warmup="Спокойная ходьба",warmup_minutes=5,cooldown="Спокойное завершение",cooldown_minutes=3,
        exercises=[dict(name="Приседание",sets=2,repetitions="8–10",seconds=None,rest_seconds=60,equipment=[],technique="Двигайтесь плавно")])]))


class FakeLLM:
    configured = True
    model = "test-model"

    def structured(self, task, data, schema, extra_check=None):
        result = schema.model_validate(copy.deepcopy(RESULT))
        if extra_check:
            extra_check(result)
        return result


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/"test.db")
        self.service = Service(self.store, FakeLLM())
        self.app = create_app(self.store, self.service)
        self.client = self.app.test_client()
        self.csrf = self.client.get('/api/state').json['csrf']

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, path, data):
        return self.client.post('/api/'+path, json=data, headers={'X-CSRF-Token':self.csrf})

    def test_profile_validation(self):
        for invalid in [dict(age=17), dict(sessions_per_week=10), dict(session_duration_minutes=-1),dict(data_consent=False)]:
            p = PROFILE | invalid
            self.assertEqual(self.post('profile',p).status_code,400)
        self.assertIsNone(self.client.get('/api/state').json['profile'])

    def test_declined_is_not_no_limitations(self):
        self.post('profile',PROFILE | dict(health_info_status='declined', limitations='Старые данные'))
        p = self.client.get('/api/state').json['profile']
        self.assertEqual(p['health_info_status'],'declined')
        self.assertIsNone(p['limitations'])

    def test_csrf_blocks_write(self):
        self.assertEqual(self.client.post('/api/profile',json=PROFILE).status_code,403)

    def test_other_session_cannot_read_or_confirm(self):
        self.post('profile',PROFILE)
        record = self.post('generate',{}).json['record']
        other = self.app.test_client()
        other_state = other.get('/api/state').json
        self.assertEqual(other_state['programs'],[])
        self.assertIsNone(other_state['profile'])
        r=other.post(f"/api/programs/{record['id']}/confirm",json={},headers={'X-CSRF-Token':other_state['csrf']})
        self.assertEqual(r.status_code,400)

    def test_adaptation_requires_confirmation(self):
        self.post('profile',PROFILE)
        first = self.post('generate',{}).json['record']
        second = self.post('generate',{'changes':'Занятие оказалось сложным'}).json['record']
        self.assertEqual(second['status'],'draft')
        records=self.client.get('/api/state').json['programs']
        self.assertEqual(next(r for r in records if r['id']==first['id'])['status'],'current')
        self.assertEqual(self.post(f"programs/{second['id']}/confirm",{}).status_code,200)
        records=self.client.get('/api/state').json['programs']
        self.assertEqual([r['status'] for r in records],['current','archived'])

    def test_feedback_distinguishes_unknown_pain(self):
        self.post('profile',PROFILE)
        record=self.post('generate',{}).json['record']
        base=dict(program_id=record['id'],workout_index=0,completion_status='skipped',comment='Не было времени')
        for value in [None,False,True]:
            self.assertEqual(self.post('feedback',base | {'pain_reported':value}).status_code,200)
        feedback=self.client.get('/api/state').json['feedback']
        self.assertEqual([r['pain_reported'] for r in feedback],[True,False,None])
        self.assertEqual(self.post('feedback',base | {'workout_index':5}).status_code,400)

    def test_busy_job_rejected(self):
        with self.store.job('user'):
            with self.assertRaises(ValueError):
                with self.store.job('user'):
                    pass

    def test_state_survives_new_store(self):
        self.store.put_json('states','telegram:1',{'index':4,'kind':'profile','data':{'age':28}})
        new=Store(self.store.path)
        self.assertEqual(new.get_json('states','telegram:1')['index'],4)

    def test_llm_error_preserves_profile(self):
        self.post('profile',PROFILE)
        def fail(*a,**kw):
            raise LLMError('Тестовый сбой')
        self.service.llm.structured=fail
        self.assertEqual(self.post('generate',{}).status_code,503)
        self.assertEqual(self.client.get('/api/state').json['profile']['age'],28)
        self.assertEqual(self.client.get('/api/state').json['programs'],[])

    def test_program_time_equipment_and_count(self):
        for mutation in ['time','equipment','count']:
            data=copy.deepcopy(RESULT)
            if mutation=='time':data['program']['workouts'][0]['exercises'][0]['sets']=10
            if mutation=='equipment':data['program']['workouts'][0]['exercises'][0]['equipment']=['Штанга']
            if mutation=='count':data['program']['workouts']*=2
            with self.assertRaises(ValueError):
                check_program(ProgramResult.model_validate(data).program,Profile.model_validate(PROFILE))

    def test_incompatible_result_status(self):
        with self.assertRaises(ValidationError):
            ProgramResult.model_validate(RESULT | {'status':'needs_clarification'})

    def test_security_headers_and_page(self):
        r=self.client.get('/')
        self.assertEqual(r.status_code,200)
        self.assertIn("frame-ancestors 'none'",r.headers['Content-Security-Policy'])
        r.close()
        self.assertEqual(self.client.get('/api/state').headers['Cache-Control'],'no-store')


class GigaTests(unittest.TestCase):
    def test_token_lock_expiry_and_authorization(self):
        calls=[]
        def handler(request):
            calls.append(request.url.path)
            return httpx.Response(200,json={'access_token':'temporary','expires_at':int((time.time()+1800)*1000)})
        giga=GigaChat(httpx.MockTransport(handler))
        giga.credentials='test'
        with ThreadPoolExecutor(max_workers=5) as pool:
            tokens=list(pool.map(lambda _:giga.token(),range(5)))
        self.assertEqual(tokens,['temporary']*5)
        self.assertEqual(len(calls),1)
        giga._expires=0
        giga.token()
        self.assertEqual(len(calls),2)

    def test_401_refreshes_once(self):
        count={'auth':0,'chat':0}
        def handler(request):
            if request.url.path.endswith('oauth'):
                count['auth']+=1
                return httpx.Response(200,json={'access_token':str(count['auth']),'expires_at':time.time()+1800})
            count['chat']+=1
            if count['chat']==1:return httpx.Response(401)
            return httpx.Response(200,json={'choices':[{'message':{'content':'{}'},'finish_reason':'stop'}]})
        g=GigaChat(httpx.MockTransport(handler));g.credentials='test';g.model='test'
        self.assertEqual(g.content([]),'{}')
        self.assertEqual(count,{'auth':2,'chat':2})

    def test_single_structure_repair(self):
        g=GigaChat(); calls=[]
        def content(messages):
            calls.append(1)
            return 'invalid' if len(calls)==1 else json.dumps(RESULT)
        g.content=content
        self.assertEqual(g.structured('generate',{},ProgramResult).status,'ready')
        self.assertEqual(len(calls),2)
        calls.clear();g.content=lambda messages: calls.append(1) or 'invalid'
        with self.assertRaises(LLMError):g.structured('generate',{},ProgramResult)
        self.assertEqual(len(calls),2)


if __name__=='__main__':
    unittest.main()
