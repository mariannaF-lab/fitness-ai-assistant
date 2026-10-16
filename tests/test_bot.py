import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot import FitnessBot
from fitness.service import Service
from fitness.store import Store
from tests.test_app import FakeLLM


class BotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/'bot.db')
        self.bot = FitnessBot(Service(self.store,FakeLLM()))
        self.reply=AsyncMock()
        self.update=SimpleNamespace(effective_user=SimpleNamespace(id=42),effective_chat=SimpleNamespace(type='private'),
            effective_message=SimpleNamespace(text='',reply_text=self.reply))
        self.context=SimpleNamespace(args=[])

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def send(self,text,command=False):
        self.update.effective_message.text=text
        await (self.bot.command(self.update,self.context) if command else self.bot.message(self.update,self.context))

    async def test_full_questionnaire_and_resume(self):
        await self.send('/profile',True)
        for answer in ['28','Общая физическая форма','Начинающий','Прогулки','3','30','Дома','Без оборудования','Предпочитаю не отвечать','Без прыжков','Согласен']:
            await self.send(answer)
        self.assertEqual(self.store.get_json('states','telegram:42')['kind'],'confirm_profile')
        # No valid profile is committed before explicit confirmation.
        self.assertIsNone(self.store.get_json('profiles','telegram:42'))
        await self.send('Подтвердить анкету')
        profile=self.store.get_json('profiles','telegram:42')
        self.assertEqual(profile['equipment'],[])
        self.assertEqual(profile['health_info_status'],'declined')
        self.assertIsNone(profile['limitations'])

    async def test_underage_does_not_advance(self):
        await self.send('/profile',True)
        await self.send('17')
        self.assertEqual(self.store.get_json('states','telegram:42')['index'],0)

    async def test_group_does_not_collect_profile(self):
        self.update.effective_chat.type='group'
        await self.send('/profile',True)
        self.assertIsNone(self.store.get_json('states','telegram:42'))

    async def test_restart_and_cancel(self):
        await self.send('/profile',True)
        await self.send('28')
        self.bot=FitnessBot(Service(Store(self.store.path),FakeLLM()))
        await self.send('/resume',True)
        self.assertEqual(self.store.get_json('states','telegram:42')['index'],1)
        await self.send('/cancel',True)
        self.assertEqual(self.store.get_json('states','telegram:42'),{})
