import eventlet
import eventlet.wsgi

from trial_project.wsgi import application

listener = eventlet.listen(("127.0.0.1", 8000))
eventlet.wsgi.server(listener, application)