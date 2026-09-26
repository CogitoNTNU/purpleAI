import http from 'k6/http';
import { check, sleep } from 'k6';

const baseUrl = 'http://vulnerable-app:5000';

const USERS = [
  { username: 'alice', password: 'alice123'},
  { username: 'bob', password: 'bob123' },
  ...Array.from({ length: 20 }, (_, i) => ({
    username: `bruker${i + 1}`,
    password: `Passord${i + 1}!`,
  })),
]

const PRODUCTS = [
  { id: 1, name: 'Eplejuice', price: '39.0' },
  { id: 2, name: 'Appelsinjuice', price: '45.0' },
  { id: 3, name: 'Bærmix', price: '55.0' },
  { id: 4, name: 'VIP Gullpakke', price: '999.0' },
];

//brukere vi vet får logget inn
const VALID_USERS = [
  { username: 'alice', password: 'alice123'},
  { username: 'bob', password: 'bob123' },
]

export const options = {
  scenarios: {
    login: {
      executor: 'shared-iterations',
      exec: 'login',
      vus: 10,
      iterations: 50,
      startTime: '0s',
    },

    buyProduct: {
      executor: 'shared-iterations',
      exec: 'buyProduct',
      vus: 10,
      iterations: 40,
      startTime: '10s',
    },

    browse: {
      executor: 'shared-iterations',
      exec: 'browse',
      vus: 10,
      iterations: 100,
      startTime: '5s',
    },
  },
}

export function login(){
  const user = USERS[Math.floor(Math.random()* USERS.length)]

  const res = http.post(baseUrl + '/login', {username: user.username, password: user.password}, {redirects: 0});

  check(res, { 'login OK': (r) => r.status === 302 });
}

export function buyProduct(){
  const user = VALID_USERS[Math.floor(Math.random()* VALID_USERS.length)]
  const product = PRODUCTS[Math.floor(Math.random() * PRODUCTS.length)];

  http.post(baseUrl + '/login', {username: user.username, password: user.password}, {redirects: 0});

  sleep(1);

  const res = http.post(`${baseUrl}/checkout`, { product_name: product.name, price: product.price, });
 
  check(res, { 'kjøp OK': (r) => r.status === 200 });
}

export function browse(){
  const choice = Math.random();

  let path;

  if (choice < 0.45) {
    path = '/';
  } else if (choice < 0.65) {
    path = `/search?q=${encodeURIComponent('juice')}`;
  } else if (choice < 0.90) {
    const productId = Math.floor(Math.random() * 4) + 1;
    path = `/product/${productId}`;
  } else if (choice < 0.97) {
    path = '/login';
  } else {
    path = '/register';
  }

  const response = http.get(`${baseUrl}${path}`);

  check(response, {
    'browse ok': (response) => response.status === 200,
  });

  sleep(Math.random() * 3 + 1);
}