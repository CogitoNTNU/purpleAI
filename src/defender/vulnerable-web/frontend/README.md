# SecureReview frontend

React/TypeScript application built with Vite and Tailwind CSS. Source code
is under `src/`; dependency versions and scripts are in `package.json`.

From this directory:

```bash
npm install
npm run dev
```

The development server uses port 3000, configured in `vite.config.ts`.

| Command | Purpose |
| --- | --- |
| `npm run dev` | Start Vite development server |
| `npm run build` | Type-check and build `dist/` |
| `npm run preview` | Serve the build on port 3000 |
| `npm run lint` | Run ESLint |

The Dockerfile builds the frontend and serves `dist/` with `serve` on
container port 3000. See [Compose setup](../README.md) and the
[developer guide](../docs/developer-guide.md).
