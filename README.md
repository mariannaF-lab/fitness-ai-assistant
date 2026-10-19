# «Ритм» — ИИ-гид по фитнес-программам

Работающий учебный прототип: сайт и Telegram-бот с GigaChat API. Исходный код приложения находится в ветке [implement-fitness-assistant](https://github.com/mariannaF-lab/fitness-ai-assistant/tree/implement-fitness-assistant).

## Материалы для сдачи

- [Коммерческое предложение со скриншотами (PDF)](https://github.com/mariannaF-lab/fitness-ai-assistant/blob/implement-fitness-assistant/submission/COMMERCIAL-PROPOSAL.pdf)
- [Текст сообщения к домашнему заданию](https://github.com/mariannaF-lab/fitness-ai-assistant/blob/implement-fitness-assistant/submission/HOMEWORK-MESSAGE.md)
- [Полный пакет: описание, промпты, примеры и проверки](https://github.com/mariannaF-lab/fitness-ai-assistant/tree/implement-fitness-assistant/submission)
- [Инструкция запуска](https://github.com/mariannaF-lab/fitness-ai-assistant/blob/implement-fitness-assistant/SETUP.md)
- [Telegram-бот](https://t.me/ritm_fitness_bot)

Сайт запускается локально. Бот отвечает при запущенном процессе. Скриншоты показывают действующий интерфейс на сохранённых результатах реального API-теста с вымышленной анкетой. Публичный хостинг пока не настроен.

## Навык

[skills/build-fitness-assistant/SKILL.md](skills/build-fitness-assistant/SKILL.md)

Внутри: согласованная архитектура и данные, сценарии интерфейсов, промпты версии 1.0, правила подключения GigaChat и план приёмки. Первая версия рассчитана на взрослых от 18 лет; планы составляются на неделю. Отдельный лендинг, питание и медицинская реабилитация не входят в объём.

## Установка в Codex

Вызовите установленный системный skill-installer:

```text
Используй $skill-installer и установи навык из репозитория
mariannaF-lab/fitness-ai-assistant, путь skills/build-fitness-assistant.
```

После установки навык будет доступен со следующего сообщения.

Пример использования:

```text
Используй $build-fitness-assistant. Проверь текущий проект и приступи
к реализации согласованных этапов: сайт, Telegram-бот и GigaChat API.
```

Установка навыка не подключает GigaChat и не запускает бота автоматически. Секреты настраиваются отдельно локально. Не загружайте в репозиторий ключи API, Access token, токен Telegram, анкеты пользователей или локальную базу данных.
