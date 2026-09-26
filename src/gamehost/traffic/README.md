# Python normal traffic from gamehost

`locustfile.py` simulates ordinary page visits from the gamehost. It only sends
GET requests: it does not register users, log in, buy products, or upload files.
The weights make home and product visits more common than the other pages.
Each simulated user waits 2–5 seconds between requests.

On gamehost, from the repository root:

```bash
python3 -m venv ~/traffic-venv
~/traffic-venv/bin/python -m pip install locust
~/traffic-venv/bin/locust -f src/gamehost/traffic/locustfile.py --headless \
  --host http://192.168.0.120:5000 \
  --users 2 --spawn-rate 1 --run-time 3m \
  --csv ~/normal-traffic
```

The `--host` address must be reachable from gamehost. The example points
directly to the vulnerable app. To exercise the defender as well, point it at
the defender's reachable URL instead (usually port 8080). Do not run both the
existing k6 generator and Locust if you only want one normal-traffic source.

Locust writes CSV summaries with the `~/normal-traffic` prefix. Increase users
and duration only after checking response times and errors in the short run.
