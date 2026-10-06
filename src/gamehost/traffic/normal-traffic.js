import http from 'k6/http';
import { check, sleep } from 'k6';

// One ordinary user, with sequential requests to avoid flooding the model gateway.
// The gamehost runner stops this container when the attacker finishes.
export const options = { vus: 1, duration: '24h', gracefulStop: '0s' };
const baseUrl = __ENV.TARGET;
const params = {
  headers: { 'X-PurpleAI-Traffic': 'normal', 'X-PurpleAI-Run-ID': __ENV.PURPLEAI_RUN_ID },
  timeout: '150s',
};

export default function () {
  const paths = ['/', '/search?q=juice', '/product/1', '/login', '/register'];
  const path = paths[__ITER % paths.length];
  const response = http.get(baseUrl + path, params);
  check(response, { 'ordinary request accepted': (r) => r.status === 200 });
  sleep(3);
}
