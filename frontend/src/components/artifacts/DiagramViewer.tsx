import { useCallback, useEffect, useRef, useState } from "react";
import { getArtifactErrorMessage, renderPlantUml } from "../../api/artifacts";
import { Button } from "../common";
import "./diagram.css";

export interface DiagramViewerProps {
  title: string;
  diagramId: string;
  source: string;
  /** Disables editing (for example while the stage is locked). */
  disabled?: boolean;
  /** Persists edited source as a new artifact version. Resolves true on success. */
  onSaveSource?: (source: string) => Promise<boolean>;
}

interface RenderFailure {
  message: string;
  line: number | null;
  rendererAvailable: boolean;
}

interface View {
  scale: number;
  x: number;
  y: number;
}

type Mode = "visual" | "source" | "edit";
const MIN_SCALE = 0.1;
const MAX_SCALE = 6;
const DEBOUNCE_MS = 600;

/**
 * Rendered UML diagram (SVG produced locally by the backend) with pan, zoom and fit, plus a
 * separate PlantUML source view. Editing the source keeps the last good preview on screen
 * while the new source is being checked; a failing render shows the error and the source is
 * never discarded.
 */
export function DiagramViewer({
  title,
  diagramId,
  source,
  disabled = false,
  onSaveSource,
}: DiagramViewerProps) {
  const [mode, setMode] = useState<Mode>("visual");
  const [draft, setDraft] = useState<string>(source);
  const [svgUrl, setSvgUrl] = useState<string | null>(null);
  const [failure, setFailure] = useState<RenderFailure | null>(null);
  const [rendering, setRendering] = useState<boolean>(true);
  const [view, setView] = useState<View>({ scale: 1, x: 0, y: 0 });
  const [fullscreen, setFullscreen] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const frame = useRef<HTMLDivElement | null>(null);
  const urlRef = useRef<string | null>(null);
  const natural = useRef<{ w: number; h: number }>({ w: 0, h: 0 });
  const drag = useRef<{ px: number; py: number; x: number; y: number } | null>(null);

  const activeSource = mode === "edit" ? draft : source;

  // Render (debounced while typing). The previous image stays until a new one is ready.
  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(
      () => {
        const run = async () => {
          setRendering(true);
          try {
            const res = await renderPlantUml(activeSource);
            if (!active) {
              return;
            }
            if (res.ok && res.svg) {
              const url = URL.createObjectURL(new Blob([res.svg], { type: "image/svg+xml" }));
              if (urlRef.current) {
                URL.revokeObjectURL(urlRef.current);
              }
              urlRef.current = url;
              setSvgUrl(url);
              setFailure(null);
            } else {
              setFailure({
                message: res.error ?? "The diagram could not be rendered.",
                line: res.line,
                rendererAvailable: res.renderer_available,
              });
            }
          } catch (e) {
            if (active) {
              setFailure({
                message: getArtifactErrorMessage(e),
                line: null,
                rendererAvailable: true,
              });
            }
          } finally {
            if (active) {
              setRendering(false);
            }
          }
        };
        void run();
      },
      mode === "edit" ? DEBOUNCE_MS : 0,
    );
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [activeSource, mode]);

  useEffect(
    () => () => {
      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current);
      }
    },
    [],
  );

  const fit = useCallback(() => {
    const el = frame.current;
    const { w, h } = natural.current;
    if (!el || w === 0 || h === 0) {
      return;
    }
    const scale = Math.min(el.clientWidth / w, el.clientHeight / h, 1.25) * 0.96;
    setView({
      scale,
      x: (el.clientWidth - w * scale) / 2,
      y: (el.clientHeight - h * scale) / 2,
    });
  }, []);

  const zoomAt = useCallback((factor: number, cx?: number, cy?: number) => {
    setView((v) => {
      const el = frame.current;
      const px = cx ?? (el ? el.clientWidth / 2 : 0);
      const py = cy ?? (el ? el.clientHeight / 2 : 0);
      const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, v.scale * factor));
      const k = scale / v.scale;
      return { scale, x: px - (px - v.x) * k, y: py - (py - v.y) * k };
    });
  }, []);

  // Wheel zoom needs a non-passive listener so the page does not scroll while zooming.
  useEffect(() => {
    const el = frame.current;
    if (!el || mode === "source") {
      return;
    }
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - rect.left, e.clientY - rect.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [mode, zoomAt, svgUrl]);

  // Re-fit when switching size (fullscreen) because the frame dimensions change.
  useEffect(() => {
    const t = window.setTimeout(fit, 50);
    return () => window.clearTimeout(t);
  }, [fullscreen, fit]);

  const save = async () => {
    if (!onSaveSource) {
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      if (await onSaveSource(draft)) {
        setMode("visual");
      }
    } catch (e) {
      setSaveError(getArtifactErrorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const showImage = svgUrl !== null && mode !== "source";
  return (
    <figure className={`diagram${fullscreen ? " diagram--fullscreen" : ""}`} data-testid="diagram">
      <figcaption className="diagram__bar">
        <span className="diagram__title">
          {title} <code>{diagramId}</code>
        </span>
        <span className="diagram__tools">
          {mode !== "source" ? (
            <>
              <Button variant="secondary" aria-label="Zoom out" onClick={() => zoomAt(1 / 1.25)}>
                −
              </Button>
              <span className="diagram__zoom" data-testid="diagram-zoom">
                {Math.round(view.scale * 100)}%
              </span>
              <Button variant="secondary" aria-label="Zoom in" onClick={() => zoomAt(1.25)}>
                +
              </Button>
              <Button variant="secondary" onClick={fit}>
                Fit to screen
              </Button>
              <Button variant="secondary" onClick={() => setView({ scale: 1, x: 0, y: 0 })}>
                Reset zoom
              </Button>
              <Button variant="secondary" onClick={() => setFullscreen((f) => !f)}>
                {fullscreen ? "Exit full screen" : "Full screen"}
              </Button>
            </>
          ) : null}
          <Button
            variant="secondary"
            onClick={() => setMode(mode === "source" ? "visual" : "source")}
            disabled={mode === "edit"}
          >
            {mode === "source" ? "View diagram" : "View PlantUML Source"}
          </Button>
          {onSaveSource && mode !== "edit" ? (
            <Button
              variant="secondary"
              disabled={disabled}
              onClick={() => {
                setDraft(source);
                setSaveError(null);
                setMode("edit");
              }}
            >
              Edit source
            </Button>
          ) : null}
        </span>
      </figcaption>

      {mode === "source" ? (
        <pre className="code-block diagram__source" data-testid="diagram-source">
          {source}
        </pre>
      ) : (
        <div className={mode === "edit" ? "diagram__split" : undefined}>
          <div
            ref={frame}
            className="diagram__frame"
            data-testid="diagram-visual"
            onPointerDown={(e) => {
              drag.current = { px: e.clientX, py: e.clientY, x: view.x, y: view.y };
              e.currentTarget.setPointerCapture(e.pointerId);
            }}
            onPointerMove={(e) => {
              const d = drag.current;
              if (d) {
                setView((v) => ({ ...v, x: d.x + e.clientX - d.px, y: d.y + e.clientY - d.py }));
              }
            }}
            onPointerUp={() => {
              drag.current = null;
            }}
          >
            {showImage ? (
              <img
                src={svgUrl}
                alt={`UML diagram: ${title}`}
                draggable={false}
                className="diagram__img"
                style={{
                  transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
                }}
                onLoad={(e) => {
                  natural.current = {
                    w: e.currentTarget.naturalWidth,
                    h: e.currentTarget.naturalHeight,
                  };
                  fit();
                }}
              />
            ) : null}
            {rendering ? <span className="diagram__busy">Rendering...</span> : null}
            {!showImage && !rendering && !failure ? (
              <p className="artifact__muted">No image yet.</p>
            ) : null}
          </div>
          {mode === "edit" ? (
            <div className="diagram__editor">
              <textarea
                className="artifact__json"
                value={draft}
                rows={18}
                spellCheck={false}
                aria-label="PlantUML source"
                onChange={(e) => setDraft(e.target.value)}
                disabled={saving}
              />
              <div className="artifact__actions">
                <Button disabled={saving || draft === source} onClick={() => void save()}>
                  Save as new version
                </Button>
                <Button variant="secondary" disabled={saving} onClick={() => setMode("visual")}>
                  Cancel
                </Button>
              </div>
              <p className="artifact__muted">
                The preview keeps the last valid image while you type. Saving creates a new
                version, validates it and returns the artifact to review.
              </p>
              {saveError ? (
                <p className="diagram__error" role="alert">
                  {saveError}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      )}

      {failure && mode !== "source" ? (
        <div className="diagram__error" role="alert" data-testid="diagram-error">
          <strong>
            {failure.rendererAvailable ? "The diagram could not be rendered" : "Renderer unavailable"}
            {failure.line ? ` (line ${failure.line})` : ""}:
          </strong>{" "}
          {failure.message}
          <div className="artifact__muted">
            The PlantUML source is preserved. Use "View PlantUML Source" to inspect or fix it.
          </div>
        </div>
      ) : null}
    </figure>
  );
}
