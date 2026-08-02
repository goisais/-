"""
WSGI config for trial_project project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

import socketio

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'trial_project.settings')

django_application = get_wsgi_application()

# Socket.IOのサーバー(trial/sockets.py)をDjangoのWSGIアプリと同じポートで
# 動かすためのラップ。これにより `python manage.py runserver` のままで
# Djangoの画面とSocket.IOの通信の両方が使えるようになる。
from trial.sockets import sio  # noqa: E402  (Django設定初期化後にimportする必要がある)

application = socketio.WSGIApp(sio, django_application)
