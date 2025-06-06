Here are the files to run via nginx and gunicorn, which will give greater performance
Unfortunately, I do not remember the necessary libraries for work, so I will provide a list of what I installed, but I do not know what exactly is needed from this

command to run:  gunicorn --workers 1 -k gevent --bind 127.0.0.1:5000 app:app

pip install gevent
pip uninstall gevent-websocket
pip install simple-websocket


pip install -U Flask-SocketIO python-socketio python-engineio eventlet 
pip install gunicorn
pip install eventlet