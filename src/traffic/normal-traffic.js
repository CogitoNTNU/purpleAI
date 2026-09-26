import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '10s', target: 5 },
    { duration: '30s', target: 10 },
    { duration: '10s', target: 0 },
  ],
};

const baseUrl = 'http://host.docker.internal:5000';

export default function () {
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
    'status is 200': (response) => response.status === 200,
  });

  sleep(Math.random() * 3 + 1);
}