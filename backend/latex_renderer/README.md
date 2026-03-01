# Local LaTeX Renderer

Small local service that renders LaTeX to SVG using MathJax.

## Run

```bash
cd backend/latex_renderer
npm install
npm run start
```

Default URL: `http://localhost:3001/mathjax`

## API

- `GET /health`
- `POST /mathjax`
  - body: `{ "latex": "\\frac{a}{b}", "display": true }`
  - response: SVG text (`image/svg+xml`)

