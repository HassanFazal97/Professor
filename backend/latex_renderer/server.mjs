import express from "express";

import { mathjax } from "mathjax-full/js/mathjax.js";
import { TeX } from "mathjax-full/js/input/tex.js";
import { SVG } from "mathjax-full/js/output/svg.js";
import { liteAdaptor } from "mathjax-full/js/adaptors/liteAdaptor.js";
import { RegisterHTMLHandler } from "mathjax-full/js/handlers/html.js";
import { AllPackages } from "mathjax-full/js/input/tex/AllPackages.js";

const app = express();
app.use(express.json({ limit: "1mb" }));

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);

const tex = new TeX({
  packages: AllPackages,
  inlineMath: [
    ["$", "$"],
    ["\\(", "\\)"],
  ],
  displayMath: [
    ["$$", "$$"],
    ["\\[", "\\]"],
  ],
});

const svg = new SVG({ fontCache: "none" });
const html = mathjax.document("", { InputJax: tex, OutputJax: svg });

app.get("/health", (_req, res) => {
  res.json({ status: "ok" });
});

app.post("/mathjax", (req, res) => {
  const latex = typeof req.body?.latex === "string" ? req.body.latex.trim() : "";
  const display = req.body?.display !== false;

  if (!latex) {
    return res.status(400).json({ error: "Missing 'latex' string in request body." });
  }

  try {
    const node = html.convert(latex, {
      display,
      em: 16,
      ex: 8,
      containerWidth: 1200,
    });
    const svgText = adaptor.outerHTML(node);
    return res.type("image/svg+xml").send(svgText);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to render LaTeX";
    return res.status(400).json({ error: message });
  }
});

const port = Number(process.env.LATEX_RENDER_PORT || 3001);
app.listen(port, () => {
  console.log(`LaTeX renderer listening on http://localhost:${port}`);
});
