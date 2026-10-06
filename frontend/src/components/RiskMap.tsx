import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

type Point = [string, number, number, number]; // id, lat, lon, probability

const color = (p: number) => (p >= 0.55 ? "244,63,94" : p >= 0.3 ? "245,158,11" : "16,185,129");

/**
 * Every customer plotted by latitude/longitude and coloured by risk.
 * Drawn on a canvas (thousands of points stay smooth); the shape of the
 * state emerges from the customers themselves - no map tiles or internet.
 */
export default function RiskMap({ points, height = 380 }: { points: Point[]; height?: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [hover, setHover] = useState<{ x: number; y: number; p: Point } | null>(null);
  const [filter, setFilter] = useState<"all" | "high">("all");
  const navigate = useNavigate();

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const project = useMemo(() => {
    if (!points.length) return null;
    const lats = points.map((p) => p[1]), lons = points.map((p) => p[2]);
    const [minLat, maxLat, minLon, maxLon] = [Math.min(...lats), Math.max(...lats), Math.min(...lons), Math.max(...lons)];
    const pad = 16;
    // Keep geographic proportions (longitude shrinks with cos(latitude)).
    const kx = Math.cos(((minLat + maxLat) / 2) * Math.PI / 180);
    const spanX = (maxLon - minLon) * kx, spanY = maxLat - minLat;
    const scale = Math.min((width - 2 * pad) / spanX, (height - 2 * pad) / spanY);
    const offX = (width - spanX * scale) / 2, offY = (height - spanY * scale) / 2;
    return (lat: number, lon: number) => [offX + (lon - minLon) * kx * scale, offY + (maxLat - lat) * scale];
  }, [points, width, height]);

  const shown = useMemo(() => (filter === "high" ? points.filter((p) => p[3] >= 0.55) : points)
    .slice().sort((a, b) => a[3] - b[3]), [points, filter]);

  useEffect(() => {
    const c = canvas.current;
    if (!c || !project) return;
    const dpr = window.devicePixelRatio || 1;
    c.width = width * dpr;
    c.height = height * dpr;
    const ctx = c.getContext("2d")!;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);
    for (const p of shown) {
      const [x, y] = project(p[1], p[2]);
      ctx.beginPath();
      ctx.arc(x, y, p[3] >= 0.55 ? 2.6 : 2, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${color(p[3])},${p[3] >= 0.55 ? 0.85 : 0.55})`;
      ctx.fill();
    }
  }, [shown, project, width, height]);

  const nearest = (mx: number, my: number) => {
    if (!project) return null;
    let best: Point | null = null, bestD = 64;
    for (const p of shown) {
      const [x, y] = project(p[1], p[2]);
      const d = (x - mx) ** 2 + (y - my) ** 2;
      if (d < bestD) { bestD = d; best = p; }
    }
    return best;
  };

  return (
    <div ref={wrap} className="relative">
      <div className="absolute right-0 top-0 z-10 flex gap-1 rounded-lg border border-line bg-surface/80 p-0.5 text-xs backdrop-blur">
        {(["all", "high"] as const).map((f) => (
          <button key={f} onClick={() => setFilter(f)}
                  className={`rounded-md px-2 py-1 font-medium ${filter === f ? "bg-surface-2 text-ink" : "text-muted"}`}>
            {f === "all" ? "All" : "High risk"}
          </button>
        ))}
      </div>
      <canvas ref={canvas} style={{ width, height }} className="cursor-crosshair"
              onMouseMove={(e) => {
                const r = e.currentTarget.getBoundingClientRect();
                const p = nearest(e.clientX - r.left, e.clientY - r.top);
                setHover(p ? { x: e.clientX - r.left, y: e.clientY - r.top, p } : null);
              }}
              onMouseLeave={() => setHover(null)}
              onClick={() => hover && navigate(`/customers/${hover.p[0]}`)} />
      {hover && (
        <div className="pointer-events-none absolute z-20 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs shadow-lg"
             style={{ left: hover.x + 12, top: hover.y - 10 }}>
          <span className="font-mono font-semibold text-ink">{hover.p[0]}</span>
          <span className="ml-2 font-semibold" style={{ color: `rgb(${color(hover.p[3])})` }}>{Math.round(hover.p[3] * 100)}%</span>
          <span className="ml-1 text-muted">· click to open</span>
        </div>
      )}
      <div className="mt-2 flex items-center gap-4 text-xs text-muted">
        {[["Low", "16,185,129"], ["Medium", "245,158,11"], ["High", "244,63,94"]].map(([l, c]) => (
          <span key={l} className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: `rgb(${c})` }} />{l}</span>
        ))}
        <span className="ml-auto">{shown.length.toLocaleString()} customers · California</span>
      </div>
    </div>
  );
}
