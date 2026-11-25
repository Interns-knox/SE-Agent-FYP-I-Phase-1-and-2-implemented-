# SE Agent frontend

React 19 + TypeScript + Vite single-page application. See the repository README for the full
setup and the application workflow.

```bash
npm ci               # needs Node 20.19+ or 22.12+
npm run dev          # http://localhost:5173 (API at VITE_API_URL, default http://localhost:8000)
npx tsc -b           # type-check
npx eslint src scripts
npm run build        # production build into dist/
npm run verify:ui    # headless-Chrome check of the whole workflow (see the repository README)
```

Layout: `src/api` (typed axios client), `src/hooks` (data hooks returning
`{ data, loading, error, refetch }`), `src/types`, `src/components` (`common`, `workspace`,
`workflow`, `artifacts`) and `src/pages`.
