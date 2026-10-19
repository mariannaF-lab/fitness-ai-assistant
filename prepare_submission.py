"""Build editable submission materials and a secret-free source archive, offline."""
import json
import re
import zipfile
from pathlib import Path

from fitness.llm import SYSTEM, TASKS, PROMPT_VERSION
from fitness.planner import PLANNER_SYSTEM, Selection

ROOT=Path(__file__).resolve().parent
DEST=ROOT/'submission'


def program_markdown(record):
    p=record['body']['program']
    lines=[f"### {p['title']} · версия {record['version']}", '', p['rationale'], '']
    for wi,w in enumerate(p['workouts'],1):
        lines += [f"#### Занятие {wi}: день {w['day']} · около {w['duration_minutes']} минут",'',
            f"Разминка — {w['warmup_minutes']} мин: {w['warmup']}",'',
            '| Упражнение | Подходы | Повторения / время | Отдых |','|---|---:|---|---:|']
        for e in w['exercises']:
            dose=e['repetitions'] or str(e['seconds'])+' сек'
            lines.append(f"| {e['name']} | {e['sets']} | {dose} | {e['rest_seconds']} сек |")
        lines += ['',f"Завершение — {w['cooldown_minutes']} мин: {w['cooldown']}",'']
    lines += ['**Восстановление:** '+p['recovery'],'','**Нагрузка:** '+p['load_guidance'],'',
              '**Дальнейшие изменения:** '+p['progression'],'']
    return '\n'.join(lines)


def main():
    DEST.mkdir(exist_ok=True)
    data=json.loads((ROOT/'reports/stability-results.json').read_text(encoding='utf-8'))
    run=data['runs'][0]
    assert data['synthetic_only'] and all(run['checks'].values())
    evidence={k:data[k] for k in ['date','model','prompt_version','synthetic_only','summary']}
    evidence['recorded_run']=run
    (DEST/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Пример работы «Ритм»','',
        'Сохранённый результат реального API-теста от 19 октября 2026 года. Это не новый живой запрос и не видеозапись интерфейса.',
        '',f"Модель: {data['model']}. Версия промпта: {data['prompt_version']}. Данные полностью синтетические.",'',
        '## 1. Исходная анкета','',
        '28 лет, начинающий, общая физическая форма, дома, без оборудования и прыжков, 3 занятия в неделю до 30 минут. Со слов учебного пользователя ограничений нет.','',
        '## 2. Полученная программа','',program_markdown(run['generation']['record']),
        '## 3. Объяснение выбранного упражнения','']
    labels={'purpose':'Назначение','equipment':'Оборудование','starting_position':'Исходное положение','steps':'Выполнение','breathing':'Дыхание','mistakes':'Частые ошибки','easier_option':'Упрощение','stop_when':'Когда прекратить'}
    for key,label in labels.items():
        value=run['explanation']['explanation'][key]
        lines += ['### '+label,'']
        lines += (['- '+v for v in value] if isinstance(value,list) else [value])+['']
    lines += ['## 4. Обратная связь и изменение условий','',
        'В API-тесте сохранён учебный отзыв: занятие выполнено частично, указано фактическое время 30 минут, сложность 7/10, боли нет. Доступное время в анкете изменено до 20 минут. Это тестовые значения, а не реально выполненная тренировка.', '',
        'Начальная оценка программы была 16 минут. Лимит 20 минут сам по себе не делает её слишком длинной; уменьшение объёма связано также с отзывом о высокой сложности.','',
        '## 5. Предложенная адаптация','',*['- '+s for s in run['adaptation']['result']['changes']],'',
        program_markdown(run['adaptation']['record']),
        '## 6. Подтверждение и история','',
        'До подтверждения новая версия имела статус draft, первая оставалась current. После подтверждения новая стала current, предыдущая — archived. Проверки обоих переходов прошли.', '',
        '## 7. Сводка серии','',
        f"Созданий: {data['summary']['generation_passed']}/5. Адаптаций: {data['summary']['adaptation_passed']}/5. Полных сценариев: {data['summary']['full_scenarios_passed']}/5. Вызовов модели: {data['summary']['api_calls']}.", '',
        'Наблюдения относятся к одному учебному профилю и не гарантируют качество для любых условий. Первичные данные этого примера — evidence.json.','']
    (DEST/'DEMO-EXAMPLE.md').write_text('\n'.join(lines),encoding='utf-8')
    prompt=['# Фактические промпты проекта «Ритм»','',f'Экспорт из исходного кода. Версия контракта: {PROMPT_VERSION}.', '',
        '## 1. Выбор упражнений и обоснование','', 'Системное сообщение для генерации и адаптации:', '',
        '```text',PLANNER_SYSTEM.strip(),'```','', 'Схема компактного ответа:', '',
        '```json',json.dumps(Selection.model_json_schema(),ensure_ascii=False,indent=2),'```','',
        'Пользовательское сообщение сериализуется как JSON: profile, catalog (доступные id, названия, назначение), sessions_required. В нём нет ключа API, имени, контактов и Telegram ID.','',
        '## 2. Адаптация','',
        'Используется тот же системный промпт. Контекст дополнен feedback, changed_conditions и previous_sessions. Сервер пересобирает дозировку, показывает изменения и сохраняет предложение до подтверждения. Отдельный запрос LLM на написание полного недельного JSON не выполняется.','',
        '## 3. Объяснение упражнения','',
        'Ниже точный системный контекст вызова объяснения. Общие правила здесь относятся к отдельному объяснению; подбор программ использует промпт из раздела 1.','',
        '```text',SYSTEM.strip()+'\n'+TASKS['explain'],'```','',
        'Вход: exercise с дозировкой, relevant_profile, program_version. К инструкции добавляется JSON Schema ExplanationResult. Результат содержит status, message, questions и explanation. Поля explanation: purpose, equipment, starting_position, steps, breathing, mistakes, easier_option, stop_when.','',
        '## 4. Исправление структуры','',
        'При ошибке валидации разрешён один дополнительный запрос. В контекст добавляются предыдущий ответ и конкретные ошибки полей без значений пользовательского ввода.','',
        '```text','Исправь предыдущий JSON. Ошибка проверки: {пути полей и сообщения, до 1800 символов}. Верни полный JSON по исходной схеме. Сохрани исходные ограничения; используй только допустимые идентификаторы из входных данных.','```','',
        'После повторной ошибки сервер сохраняет анкету и возвращает понятное сообщение. Неизвестные id не заменяются догадками, а сетевая ошибка не подменяется готовым шаблоном.','',
        '## 5. Что делает обычный код','',
        'Анкета, принадлежность данных, фильтрация оборудования, начальная дозировка, расписание, оценка времени, статусы и история проверяются сервером. Это позволяет оценивать соблюдение ограничений независимо от свободного текста модели.','']
    (DEST/'PROMPTS.md').write_text('\n'.join(prompt),encoding='utf-8')

    roots=['app.py','bot.py','requirements.txt','.env.example','.gitignore','README.md','SETUP.md',
        'start-site.ps1','start-bot.ps1','check_telegram.py','check_gigachat.py','live_acceptance.py','stability_acceptance.py','prepare_submission.py']
    files=[ROOT/name for name in roots]
    for directory in ['fitness','web','tests','skills','submission']:
        files += [p for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc','.db','.zip'}]
    files += [ROOT/'reports'/name for name in ['STABILITY-REPORT.md','stability-summary.json','SKILL-AUDIT.md']]
    archive=ROOT/'fitness-assistant-submission.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(set(files)):
            assert p.is_file(),p
            assert p.name!='.env' and p.suffix not in {'.db','.log','.pyc'},p
            rel=p.relative_to(ROOT).as_posix()
            z.write(p,'fitness-ai-assistant/'+rel)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert not any('/data/' in name or '/.validation-deps/' in name or name.endswith('/.env') for name in z.namelist())
        assert all('..' not in Path(name).parts for name in z.namelist())
    print('Prepared submission materials:',DEST)
    print('Archive:',archive.name, 'files:',len(files),'bytes:',archive.stat().st_size)


if __name__=='__main__':
    main()
