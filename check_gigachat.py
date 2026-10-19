"""Диагностика авторизации без вывода ключа или токена."""
from dotenv import load_dotenv
from fitness.llm import GigaChat
import sys

load_dotenv()
client=GigaChat()
try:
    client.token()
    print('Authorization OK')
    headers={'Authorization':'Bearer '+client.token()}
    response=client.client.get('https://api.giga.chat/v1/models',headers=headers)
    print('Models HTTP:',response.status_code)
    if response.status_code==200:
        print('Available models:',[item['id'] for item in response.json().get('data',[])])
    print('Configured model:',client.model)
    if '--chat' in sys.argv:
        response=client.client.post('https://api.giga.chat/v1/chat/completions',headers=headers,
            json={'model':client.model,'messages':[{'role':'user','content':'Ответь одним словом: привет'}],'max_tokens':10})
        print('Minimal chat HTTP:',response.status_code)
        if response.status_code!=200:
            detail=response.text
            for secret in [client.credentials,client._token]:
                if secret:
                    detail=detail.replace(secret,'[REDACTED]')
            print('API error:',detail[:700])
except Exception as error:
    print('Authorization failed:',type(error).__name__)
    while error is not None:
        detail=str(error)
        for secret in [client.credentials,client._token]:
            if secret:
                detail=detail.replace(secret,'[REDACTED]')
        print(type(error).__name__,detail[:500])
        error=error.__cause__
