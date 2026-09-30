python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:5000/').read()"
python -c "import urllib.request as u, urllib.parse as p; print(u.urlopen('http://127.0.0.1:5000/add', data=p.urlencode({'a': 2, 'b': 3}).encode()).read())"
