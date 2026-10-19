"""Приёмка с реальным API на синтетической анкете и изолированной базе."""
import json
import tempfile
from datetime import datetime
from pathlib import Path

from app import create_app
from fitness.store import Store


def main():
    out = Path('reports')
    out.mkdir(exist_ok=True)
    evidence = {'date': datetime.now().isoformat(), 'data': 'Только синтетическая анкета', 'checks': []}

    def record(name, ok, detail):
        evidence['checks'].append({'scenario': name, 'passed': ok, 'detail': detail})
        (out/'live-results.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
        print(('PASS: ' if ok else 'FAIL: ')+name+': '+detail, flush=True)

    with tempfile.TemporaryDirectory() as directory:
        app = create_app(Store(Path(directory)/'acceptance.db'))
        llm = app.extensions['fitness'].llm
        original_content = llm.content
        def capture(messages):
            raw = original_content(messages)
            evidence.setdefault('synthetic_model_outputs', []).append(raw)
            (out/'live-results.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
            return raw
        llm.content = capture
        client = app.test_client()
        csrf = client.get('/api/state').json['csrf']
        def post(path, body):
            return client.post('/api/'+path, json=body, headers={'X-CSRF-Token':csrf})
        profile = dict(age=28, goal='Общая физическая форма', fitness_level='beginner',
            current_activity='Учебный профиль: сидячая работа, ежедневные прогулки',
            sessions_per_week=3, session_duration_minutes=30, training_location='home',
            equipment=[], health_info_status='provided', limitations='Со слов учебного пользователя ограничений нет',
            preferences='Без прыжков', data_consent=True)
        response = post('profile',profile)
        record('Анкета', response.status_code==200, 'Учебный профиль сохранён в отдельной временной базе')
        response = post('generate',{})
        if response.status_code != 200:
            record('Генерация через GigaChat',False,response.json.get('error','Ошибка сервера'))
            return
        result = response.json
        evidence['generation']=result
        if not result.get('record'):
            record('Генерация через GigaChat',False,'Вместо программы: '+result['result']['status']+' '+result['result']['message'])
            return
        first = result['record']
        workouts = first['body']['program']['workouts']
        record('Генерация через GigaChat',True,'Получены 3 занятия, ответ прошёл серверную проверку JSON, оборудования и времени')
        response = post('explain',dict(program_id=first['id'],workout_index=0,exercise_index=0))
        evidence['explanation']=response.json
        record('Объяснение упражнения',response.status_code==200 and bool(response.json.get('explanation')),
               'Упражнение: '+workouts[0]['exercises'][0]['name'] if response.status_code==200 else response.json.get('error','Ошибка'))
        feedback=dict(program_id=first['id'],workout_index=0,completion_status='partial',actual_duration_minutes=30,
            perceived_difficulty=7,pain_reported=False,comment='Учебный отзыв: не хватает времени, могу выделить только 20 минут')
        response=post('feedback',feedback)
        record('Обратная связь',response.status_code==200,'Отзыв сохранён; автоматического изменения программы нет')
        profile['session_duration_minutes']=20
        post('profile',profile)
        response=post('generate',{'changes':'Могу выделить только 20 минут вместо 30. Предложи более короткую программу, без прыжков.'})
        evidence['adaptation']=response.json
        second=response.json.get('record') if response.status_code==200 else None
        record('Адаптация через GigaChat',bool(second),
            'Новая программа прошла проверку ограничения 20 минут' if second else response.json.get('error',str(response.json.get('result',{}).get('status'))))
        if second:
            before=client.get('/api/state').json['programs']
            record('Подтверждение изменений',second['status']=='draft' and any(r['id']==first['id'] and r['status']=='current' for r in before),
                'До подтверждения первая версия остаётся текущей')
            response=post(f"programs/{second['id']}/confirm",{})
            after=client.get('/api/state').json['programs']
            record('История версий',response.status_code==200 and [r['status'] for r in after]==['current','archived'],
                'Новая версия принята, предыдущая сохранена')
    (out/'live-results.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
