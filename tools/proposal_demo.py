"""Isolated UI for capturing saved synthetic API evidence. Not a public server."""
import json
import secrets
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import create_app
from fitness.store import Store
from flask import redirect


def main():
    root=ROOT/'tmp'/'proposal-demo'
    root.mkdir(parents=True,exist_ok=True)
    store=Store(root/('demo-'+secrets.token_hex(4)+'.db'))
    record=json.loads((ROOT/'submission/evidence.json').read_text(encoding='utf-8'))['recorded_run']
    owner='web:proposal-demo'
    token=secrets.token_urlsafe(32)
    store.put_json('profiles',owner,record['generation']['record']['profile'])
    first=store.save_program(owner,record['generation']['record']['body'],record['generation']['record']['profile'],'GigaChat-3-Ultra')
    with store.connect() as db:
        db.execute('INSERT INTO sessions VALUES (?,?,?,?)',(token,owner,secrets.token_urlsafe(32),time.time()+3600))
        db.execute('INSERT INTO explanations VALUES (?,?,?,?,?)',(owner,first['id'],0,0,json.dumps(record['explanation'],ensure_ascii=False)))
    app=create_app(store)
    added=[]
    @app.get('/demo')
    def start():
        response=redirect('/')
        response.set_cookie('fitness_session',token,httponly=True,samesite='Strict')
        return response
    @app.get('/demo/adaptation')
    def adaptation():
        if not added:
            second=store.save_program(owner,record['adaptation']['record']['body'],record['adaptation']['record']['profile'],'GigaChat-3-Ultra')
            added.append(second['id'])
            store.put_json('profiles',owner,record['adaptation']['record']['profile'])
        return redirect('/#programs')
    print('Isolated saved-results demonstration: http://localhost:8001/demo',flush=True)
    app.run(host='127.0.0.1',port=8001,debug=False)


if __name__=='__main__':
    main()
