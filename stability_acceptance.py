"""Five isolated live scenarios. Contains synthetic profiles only; consumes API tokens."""
import json
import tempfile
import time
from datetime import datetime
from pathlib import Path

from app import create_app
from fitness.llm import PROMPT_VERSION
from fitness.store import Store
from fitness.models import Profile, ProgramResult, check_program
from fitness.planner import duration_seconds


def main():
    output=Path('reports/stability-results.json')
    output.parent.mkdir(exist_ok=True)
    evidence={'date':datetime.now().isoformat(),'prompt_version':PROMPT_VERSION,'synthetic_only':True,'runs':[]}
    def save():
        output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    profile=dict(age=28,goal='Общая физическая форма',fitness_level='beginner',current_activity='Учебный профиль: сидячая работа, прогулки',
        sessions_per_week=3,session_duration_minutes=30,training_location='home',equipment=[],health_info_status='provided',
        limitations='Со слов учебного пользователя ограничений нет',preferences='Без прыжков',data_consent=True)
    with tempfile.TemporaryDirectory() as directory:
        app=create_app(Store(Path(directory)/'stability.db'))
        llm=app.extensions['fitness'].llm
        evidence['model']=llm.model
        calls=[]
        original=llm.content
        def count(messages):
            calls.append(1)
            return original(messages)
        llm.content=count
        for i in range(5):
            client=app.test_client()
            csrf=client.get('/api/state').json['csrf']
            def post(path,body):
                return client.post('/api/'+path,json=body,headers={'X-CSRF-Token':csrf})
            row={'run':i+1,'checks':{},'generation':None,'adaptation':None}
            evidence['runs'].append(row)
            post('profile',profile)
            started=time.monotonic(); before=len(calls)
            response=post('generate',{})
            row['generation_seconds']=round(time.monotonic()-started,2)
            row['generation_calls']=len(calls)-before
            row['generation']=response.json
            first=response.json.get('record') if response.status_code==200 else None
            row['checks']['generation']=bool(first)
            if not first:
                print(f'Run {i+1}: generation FAIL: '+response.json.get('error',str(response.json.get('result',{}).get('status'))),flush=True)
                save();continue
            p=ProgramResult.model_validate(first['body']).program
            check_program(p,Profile.model_validate(profile))
            row['checks']['time_and_equipment']=all(duration_seconds(w)<=30*60 and not any(e.equipment for e in w.exercises) for w in p.workouts)
            if i==0:
                response=post('explain',dict(program_id=first['id'],workout_index=0,exercise_index=0))
                row['explanation']=response.json
                row['checks']['explanation']=response.status_code==200 and bool(response.json.get('explanation'))
                before_cache=len(calls)
                cached=post('explain',dict(program_id=first['id'],workout_index=0,exercise_index=0))
                row['checks']['explanation_cached']=cached.json==response.json and len(calls)==before_cache
            post('feedback',dict(program_id=first['id'],workout_index=0,completion_status='partial',actual_duration_minutes=30,
                perceived_difficulty=7,pain_reported=False,comment='Учебный отзыв: не хватает времени, нужно сократить до 20 минут'))
            shorter=profile | {'session_duration_minutes':20}
            post('profile',shorter)
            started=time.monotonic();before=len(calls)
            response=post('generate',{'changes':'Выделяю только 20 минут вместо 30. Сократить занятия, без прыжков.'})
            row['adaptation_seconds']=round(time.monotonic()-started,2)
            row['adaptation_calls']=len(calls)-before
            row['adaptation']=response.json
            second=response.json.get('record') if response.status_code==200 else None
            row['checks']['adaptation']=bool(second)
            if second:
                q=ProgramResult.model_validate(second['body']).program
                row['checks']['adapted_time']=all(duration_seconds(w)<=20*60 for w in q.workouts)
                state=client.get('/api/state').json
                row['checks']['confirmation_required']=second['status']=='draft' and any(r['id']==first['id'] and r['status']=='current' for r in state['programs'])
                post(f"programs/{second['id']}/confirm",{})
                row['checks']['history']=[r['status'] for r in client.get('/api/state').json['programs']]==['current','archived']
                post('feedback',dict(program_id=second['id'],workout_index=0,completion_status='partial',actual_duration_minutes=15,
                    perceived_difficulty=8,pain_reported=True,comment='Синтетический тест: боль при выполнении'))
                before_pain=len(calls)
                blocked=post('generate',{'changes':'Есть боль, сделайте план сложнее'})
                row['checks']['pain_gate']=blocked.status_code==200 and blocked.json['result']['status']=='requires_professional_review' and blocked.json['record'] is None and len(calls)==before_pain
            print(f"Run {i+1}: "+('PASS' if all(row['checks'].values()) else 'FAIL')+f" | generation {row['generation_seconds']}s/{row['generation_calls']} call(s), adaptation {row['adaptation_seconds']}s/{row['adaptation_calls']} call(s)",flush=True)
            save()
        evidence['summary']={'generation_passed':sum(bool(r['checks'].get('generation')) for r in evidence['runs']),
            'adaptation_passed':sum(bool(r['checks'].get('adaptation')) for r in evidence['runs']),
            'full_scenarios_passed':sum(all(r['checks'].values()) for r in evidence['runs']), 'runs':len(evidence['runs']),'api_calls':len(calls)}
        save();print(json.dumps(evidence['summary'],ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
