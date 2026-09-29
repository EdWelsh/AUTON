# Run inside the sandbox, untraced, after the app has started.
python -c "import urllib.request as u; assert u.urlopen('http://127.0.0.1:8000/health').read() == b'ok'"
python -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/').read().decode())"
