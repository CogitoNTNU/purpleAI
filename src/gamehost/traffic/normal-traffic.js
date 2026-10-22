import http from 'k6/http';
import { check, sleep } from 'k6';

const baseUrl = (__ENV.TARGET || '').replace(/\/$/, '');
if (!baseUrl) {
  throw new Error('Set TARGET to the BlueAI defender URL, for example http://192.168.0.120:8080');
}

export const options = { vus: 1, duration: '10m' };

const users = [
  { username: 'alice', password: 'alice123' },
  { username: 'bob', password: 'bob123' },
];
const products = [
  { id: 1, name: 'Eplejuice', price: '39.0' },
  { id: 2, name: 'Appelsinjuice', price: '45.0' },
  { id: 3, name: 'Bærmix', price: '55.0' },
  { id: 4, name: 'VIP Gullpakke', price: '999.0' },
];

function pick(items) {
  return items[Math.floor(Math.random() * items.length)];
}

export function browse() {
  const path = pick(['/', '/search?q=juice', `/product/${pick(products).id}`, '/login', '/register']);
  check(http.get(`${baseUrl}${path}`), { 'browse returned 200': (r) => r.status === 200 });
}

export function login() {
  const response = http.post(`${baseUrl}/login`, pick(users), { redirects: 0 });
  return check(response, { 'login returned 302': (r) => r.status === 302 });
}

export function buyProduct() {
  if (!login()) return;
  sleep(1);
  const product = pick(products);
  const response = http.post(`${baseUrl}/checkout`, {
    product_name: product.name,
    price: product.price,
  }, { redirects: 0 });
  check(response, { 'purchase returned 200': (r) => r.status === 200 });
}

export default function () {
  pick([browse, browse, browse, login, buyProduct])();
  sleep(3);
}
