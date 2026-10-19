"""Build a four-page commercial proposal offline from reviewed screenshots."""
from pathlib import Path
from io import BytesIO
from PIL import Image as PILImage
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'submission/COMMERCIAL-PROPOSAL.pdf'
pdfmetrics.registerFont(TTFont('Arial', 'C:/Windows/Fonts/arial.ttf'))
pdfmetrics.registerFont(TTFont('Arial-Bold', 'C:/Windows/Fonts/arialbd.ttf'))
pdfmetrics.registerFontFamily('Arial', normal='Arial', bold='Arial-Bold')
W, H = 595.28, 841.89
M = 42
INK = HexColor('#242b24')
ORANGE = HexColor('#dc642f')
TEXT = ParagraphStyle('body', fontName='Arial', fontSize=10.5, leading=15,
                      textColor=INK, spaceAfter=8)
SMALL = ParagraphStyle('small', parent=TEXT, fontSize=8.2, leading=11,
                       textColor=HexColor('#5a6258'))
HEAD = ParagraphStyle('head', parent=TEXT, fontName='Arial-Bold', fontSize=15, leading=20)
c = canvas.Canvas(str(OUT), pagesize=(W,H))
c.setTitle('Ритм | Коммерческое предложение')
c.setAuthor('mariannaF-lab')
y = 0

def paragraph(text, style=TEXT, gap=9):
    global y
    p=Paragraph(text,style)
    _, height=p.wrap(W-2*M, H)
    assert y-height > 48, (text[:60],y,height)
    p.drawOn(c,M,y-height)
    y -= height+gap

def page(number, label, title):
    global y
    c.setFillColor(HexColor('#f8f7f2'))
    c.rect(0,0,W,H,fill=1,stroke=0)
    c.setFillColor(ORANGE)
    c.rect(M,H-43,30,4,fill=1,stroke=0)
    c.setFont('Arial-Bold',9)
    c.setFillColor(INK)
    c.drawString(M+40,H-43,'РИТМ / '+label.upper())
    c.setFont('Arial',8)
    c.setFillColor(HexColor('#666d63'))
    c.drawString(M,27,'Учебный прототип | 19 октября 2026 | mariannaF-lab')
    c.drawRightString(W-M,27,f'{number} / 4')
    y=H-82
    paragraph(title, ParagraphStyle('title',parent=HEAD,fontSize=25,leading=29),16)

def shot(name,caption,crop=None,width=None):
    global y
    im=PILImage.open(ROOT/'submission/screenshots'/name)
    if crop: im=im.crop(crop)
    iw,ih=im.size
    dw=width or W-2*M
    dh=dw*ih/iw
    assert y-dh>70,(name,y,dh)
    if crop:
        image_bytes=BytesIO()
        im.save(image_bytes, format='JPEG', quality=92)
        image_bytes.seek(0)
        source=ImageReader(image_bytes)
    else:
        source=ImageReader(str(ROOT/'submission/screenshots'/name))
    c.drawImage(source,M+(W-2*M-dw)/2,y-dh,width=dw,height=dh)
    y-=dh+9
    paragraph(caption,SMALL,14)

page(1,'коммерческое предложение','ИИ-гид по фитнес-программам')
paragraph('Предлагаем цифрового помощника для фитнес-проекта: сайт и Telegram-бот, которые собирают анкету, подбирают недельный план и помогают изменить его по обратной связи.')
paragraph('<b>Для кого:</b> тренер, небольшая фитнес-студия или онлайн-проект. Помощник даёт клиенту понятный первый шаг: что делать, как выполнять упражнение и как сообщить о сложности.')
shot('01-site.jpg','Рис. 1. Главная страница сайта «Ритм» со ссылкой на Telegram-бота.')
paragraph('Что уже работает',HEAD)
paragraph('Анкета пользователя от 18 лет; программа с дозировкой и оценкой времени; объяснения упражнений; отзыв; предложение адаптации; подтверждение и история версий.')
paragraph('Статус: работающий учебный прототип. Предполагаемая коммерческая область применения не означает наличие действующего заказа.',SMALL)
c.showPage()

page(2,'результат подбора','От анкеты к плану на неделю')
paragraph('<b>Учебная анкета:</b> 28 лет, начинающий, общая физическая форма, дома, без инвентаря и прыжков, 3 занятия в неделю до 30 минут.')
shot('02-program.jpg','Рис. 2. Текущая программа: разминка, упражнения, подходы, повторения и отдых.')
paragraph('Понятный результат',HEAD)
paragraph('В сохранённом примере занятия рассчитаны примерно на 16 минут. Лимит 30 минут задаёт верхнюю границу, а не обязательную продолжительность тренировки. Для отжиманий от стены в первом занятии назначены 2 подхода по 8 повторений с отдыхом 60 секунд.')
paragraph('GigaChat выбирает упражнения из допустимой части каталога и объясняет выбор. Сервер формирует расписание, дозировку и оценку времени, проверяет оборудование и структуру ответа.')
paragraph('Все скриншоты в документе сняты с действующего интерфейса на сохранённых результатах реального API-теста. Анкета вымышленная. Это не новый запрос к модели и не свидетельство выполненной тренировки.',SMALL)
c.showPage()

page(3,'объяснение и архитектура','Помощь в выполнении упражнения')
shot('03-technique.jpg','Рис. 3. Фрагмент окна объяснения отжиманий от стены. Исходный скриншот доступен в папке screenshots.',crop=(309,53,942,660),width=335)
paragraph('Объяснение по запросу',HEAD)
paragraph('Пользователь открывает «Как выполнять». Ответ содержит назначение, исходное положение, шаги, дыхание, частые ошибки, упрощение и условия прекращения. Объяснение сохраняется в кэше.')
paragraph('<b>Общая логика:</b> сайт / Telegram → сервис Python → проверка анкеты → GigaChat API → проверка ответа → SQLite и интерфейс пользователя.')
paragraph('Стек: Flask, python-telegram-bot, Pydantic, SQLite, HTML/CSS/JavaScript. Ключ API хранится локально в .env; временный токен обновляет сервер. Секреты не включены в материалы сдачи.',SMALL)
c.showPage()

page(4,'адаптация и передача','Изменения под контролем пользователя')
shot('04-adaptation.jpg','Рис. 4. Версия 2: предложение облегчённого плана с отдельной кнопкой принятия.')
paragraph('После учебного отзыва о сложности 7/10 и изменения доступного времени до 20 минут предложены занятия около 10 минут. Новая версия становится текущей после подтверждения.')
paragraph('<b>Проверено:</b> 28 автоматических тестов, включая 168 сочетаний длительности, частоты и уровня. На одной синтетической анкете: 5/5 созданий и 5/5 адаптаций через настоящий API. Серия не покрывает все условия.')
paragraph('<b>Передача:</b> исходники, промпты, инструкции запуска, тесты и материалы демонстрации. Сайт локальный; бот отвечает при запущенном процессе. Публичный хостинг и привязка профилей пока не реализованы.')
paragraph('<b>Развитие:</b> расширение каталога из 12 упражнений, экспертная оценка, дополнительные сценарии обработки боли и переноса упражнений между днями, затем размещение на сервере. Стоимость, сроки, API и сопровождение согласуются отдельно.',SMALL)
paragraph('<link href="https://github.com/mariannaF-lab/fitness-ai-assistant/tree/implement-fitness-assistant/submission" color="#b95123">Материалы проекта на GitHub</link> · <link href="https://t.me/ritm_fitness_bot" color="#b95123">Telegram: @ritm_fitness_bot</link><br/>Рекомендации информационные и не заменяют консультацию тренера или врача.',SMALL,0)
c.showPage()
c.save()
print(OUT)
