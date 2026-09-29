i=0; while [ $i -lt 20 ]; do wget -qO- http://127.0.0.1:80/ >/dev/null 2>&1 && break; i=$((i+1)); sleep 0.5; done; wget -qO- http://127.0.0.1:80/ | head -3; wget -qO- http://127.0.0.1:80/health
