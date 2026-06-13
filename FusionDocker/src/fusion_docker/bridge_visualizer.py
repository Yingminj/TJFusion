"""Unified OpenCV visualization for the custom_pipeline bridge.

The bridge runs a model DAG (RealSense source -> Fast-Foundation depth,
SAM3 mask, VLM/SigLIP status, FlowPose pose).  Historically nothing was
drawn on screen, so starting ``bridge.realsense_split.yaml`` produced no
visible result.  :class:`PipelineVisualizer` collects whatever each node
left in the pipeline *store* and renders one labelled tile per docker into
a single OpenCV window:

    +---------------------+---------------------+---------------------+
    | RealSense (color)   | Fast-Foundation     | SAM3 (mask)         |
    |                     | (depth)             |                     |
    +---------------------+---------------------+---------------------+
    | VLM (status)        | SigLIP (status)     | FlowPose (pose)     |
    +---------------------+---------------------+---------------------+

Tiles whose node did not (yet) produce data show a "waiting..." placeholder
so the layout stays stable and the user can immediately see which stage is
missing.

The module only depends on numpy + OpenCV (already required by the bridge).
When the installed OpenCV is the *headless* build (no ``imshow`` support) the
visualizer logs a one-time hint and falls back to writing the composite frame
to ``visualize_save_path`` if one was configured.
"""

from __future__ import annotations

from typing import Any

from fusion_docker.console import print_status, print_warning

try:
    import cv2  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - bridge already requires cv2
    cv2 = None

try:
    import numpy as np  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - bridge already requires numpy
    np = None


# Pretty display names for known pipeline node names. The visualizer only
# shows a tile per node that is actually in the running pipeline (which mirrors
# the started/selected dockers), so a node that isn't launched gets no tile.
_PRETTY_NAMES: dict[str, str] = {
    "fast_foundation": "Fast-Foundation",
    "ffs": "Fast-Foundation",
    "sam3": "SAM3",
    "vlm": "VLM",
    "siglip": "SigLIP",
    "siglip2": "SigLIP",
    "flowpose": "FlowPose",
    "flowpose_sidecar": "FlowPose",
    "yomni": "Yomni",
    "realsense": "RealSense",
}

# A small palette (BGR) reused for per-instance masks / object axes labels.
_PALETTE: tuple[tuple[int, int, int], ...] = (
    (66, 135, 245),
    (66, 245, 135),
    (245, 66, 135),
    (245, 197, 66),
    (135, 66, 245),
    (66, 245, 245),
    (245, 66, 66),
    (180, 245, 66),
)


def _palette(idx: int) -> tuple[int, int, int]:
    return _PALETTE[idx % len(_PALETTE)]


class PipelineVisualizer:
    """Render pipeline outputs into one unified OpenCV window."""

    def __init__(
        self,
        *,
        window_name: str = "TJFusion Pipeline",
        scale: float = 1.0,
        save_path: str = "",
        nodes: list[dict[str, str]] | None = None,
        source_title: str = "RealSense (color)",
    ) -> None:
        if cv2 is None or np is None:
            raise RuntimeError(
                "PipelineVisualizer requires numpy and opencv. Install the "
                "bridge requirements first."
            )
        self.window_name = window_name
        # Base tile is 16:9; scale lets the user shrink/grow the whole grid.
        self.tile_w = max(160, int(round(480 * scale)))
        self.tile_h = max(90, int(round(270 * scale)))
        self.save_path = save_path
        self._window_ready = False
        self._imshow_disabled = False
        self._save_hint_shown = False
        # Build one panel per pipeline node (plus the always-on camera source),
        # so the layout reflects exactly the dockers that are running.
        self._panels: list[tuple[str, Any]] = self._build_panel_layout(
            nodes or [], source_title
        )

    def _build_panel_layout(
        self, nodes: list[dict[str, str]], source_title: str
    ) -> list[tuple[str, Any]]:
        panels: list[tuple[str, Any]] = [(source_title, self._panel_source)]
        for node in nodes:
            name = str(node.get("name", "") or "")
            data_type = str(node.get("data_type", "") or "")
            kind = self._resolve_kind(name, data_type)
            pretty = _PRETTY_NAMES.get(name.lower(), name or "node")
            if kind == "depth":
                panels.append((f"{pretty} (depth)", self._panel_depth))
            elif kind == "mask":
                panels.append((f"{pretty} (mask)", self._panel_mask))
            elif kind == "status":
                panels.append(
                    (f"{pretty} (status)", self._make_status_builder(name))
                )
            elif kind == "pose":
                panels.append((f"{pretty} (pose)", self._panel_pose))
            # Unknown node kinds are skipped: nothing meaningful to draw.
        return panels

    @staticmethod
    def _resolve_kind(name: str, data_type: str) -> str:
        """Map a pipeline node to a panel kind via data_type, then name."""
        dt = (data_type or "").strip().lower()
        if dt in {"depth", "mask", "status", "pose"}:
            return dt
        low = (name or "").lower()
        if "depth" in low or "foundation" in low or low in {"ffs"}:
            return "depth"
        if "sam" in low or "mask" in low or "seg" in low:
            return "mask"
        if "siglip" in low or "vlm" in low or "status" in low or "class" in low:
            return "status"
        if "pose" in low or "flow" in low or "yomni" in low:
            return "pose"
        return ""

    def _make_status_builder(self, node_name: str):
        def _builder(store, results):
            return self._status_panel(store, results, node_name)

        return _builder

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(
        self,
        store: dict[str, Any],
        model_results: dict[str, dict[str, Any]],
        *,
        frame_id: int = -1,
        request_id: str = "",
    ) -> None:
        """Build and show the composite frame for one processed frame."""
        try:
            tiles = [
                self._build_panel(title, builder, store, model_results)
                for title, builder in self._panels
            ]
            composite = self._compose_grid(tiles)
            composite = self._add_status_bar(composite, frame_id, request_id)
            self._show(composite)
        except Exception as exc:  # noqa: BLE001 - never let drawing kill the bridge
            print_warning(f"Visualization skipped this frame: {exc}")

    def close(self) -> None:
        if cv2 is None:
            return
        try:
            cv2.destroyAllWindows()
            # destroyAllWindows needs a few waitKey pumps to actually close.
            for _ in range(3):
                cv2.waitKey(1)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Per-docker panels
    # ------------------------------------------------------------------

    def _build_panel(
        self,
        title: str,
        builder: Any,
        store: dict[str, Any],
        model_results: dict[str, dict[str, Any]],
    ) -> Any:
        try:
            img, subtitle = builder(store, model_results)
        except Exception as exc:  # noqa: BLE001
            img, subtitle = None, f"render error: {exc}"

        if img is None:
            img = self._placeholder(subtitle or "waiting...")
        tile = self._fit_tile(img)
        return self._label_tile(tile, title, subtitle)

    def _panel_source(self, store, _results):
        color = self._get_image(store, "color")
        if color is None:
            return None, "no color frame"
        view = self._to_bgr(color)
        # Inset the two IR views (and hw_depth if present) as small thumbnails
        # so the camera source is fully represented in one tile.
        thumbs = []
        for name in ("ir_left", "ir_right"):
            ir = self._get_image(store, name)
            if ir is not None:
                thumbs.append(self._to_bgr(ir))
        hw_depth = self._get_image(store, "hw_depth")
        if hw_depth is not None:
            thumbs.append(self._colorize_depth(hw_depth))
        view = self._inset_thumbnails(view, thumbs)
        h, w = view.shape[:2]
        return view, f"{w}x{h}  ir={len(thumbs)}"

    def _panel_depth(self, store, _results):
        depth = self._get_image(store, "depth")
        if depth is None:
            return None, "no depth"
        colored = self._colorize_depth(depth)
        valid = np.count_nonzero(np.nan_to_num(depth) > 0)
        total = int(depth.size) or 1
        finite = depth[np.isfinite(depth) & (depth > 0)]
        h, w = depth.shape[:2]
        if finite.size:
            rng = f"{float(finite.min()):.2f}-{float(finite.max()):.2f}m"
        else:
            # The node responded with a depth array (shape proves it ran), but
            # every value is 0/invalid -> a runtime depth-estimation problem,
            # not a container start failure.
            rng = "all-zero/invalid"
        return colored, f"{w}x{h} valid={100.0 * valid / total:.0f}% {rng}"

    def _panel_mask(self, store, _results):
        color = self._get_image(store, "color")
        base = self._to_bgr(color) if color is not None else None
        masks = self._get_array(store, "sam3_response", "masks")
        combined = self._get_image(store, "combined_mask")
        class_names = self._get_list(store, "class_names")
        obj_ids = self._get_list(store, "obj_ids")

        if base is None:
            # Fall back to showing the combined mask itself.
            if combined is None:
                return None, "no mask"
            return self._colorize_label_mask(combined), f"objs={len(obj_ids)}"

        overlay = base.copy()
        count = 0
        if masks is not None and getattr(masks, "ndim", 0) == 3:
            count = masks.shape[0]
            for idx in range(count):
                m = masks[idx]
                label = class_names[idx] if idx < len(class_names) else ""
                self._blend_mask(overlay, m, _palette(idx), label)
        elif combined is not None:
            overlay = cv2.addWeighted(
                overlay, 0.6, self._colorize_label_mask(combined), 0.4, 0.0
            )
            count = int(len(obj_ids))
        else:
            return None, "no mask"
        return overlay, f"objs={count}  prompts={','.join(self._get_list(store, 'prompts'))[:24]}"

    def _status_panel(self, store, results, node):
        resp = store.get(f"{node}_response")
        best_cat = ""
        best_sim = None
        topk: list[Any] = []
        if isinstance(resp, dict):
            best_cat = str(resp.get("best_category", "") or "")
            best_sim = resp.get("best_similarity")
            topk = resp.get("topk") or []
        else:
            # No node-specific response yet: fall back to the shared status
            # keys written via response_map.
            best_cat = str(store.get("best_category", "") or "")
            best_sim = store.get("best_similarity")

        if not best_cat and not topk:
            return None, "waiting..."

        img = self._blank()
        lines = [f"best: {best_cat or '-'}"]
        if isinstance(best_sim, (int, float)):
            lines.append(f"score: {float(best_sim):.3f}")
        state_name = store.get("state_name") or store.get("name")
        state_id = store.get("state_id")
        if state_name or state_id is not None:
            lines.append(f"state: {state_name or '-'} (#{state_id})")
        if topk:
            lines.append("top-k:")
            for item in topk[:4]:
                if isinstance(item, dict):
                    cat = str(item.get("category", ""))
                    sim = item.get("similarity")
                    sim_txt = f" {float(sim):.2f}" if isinstance(sim, (int, float)) else ""
                    lines.append(f"  - {cat}{sim_txt}")
        self._draw_text_block(img, lines)
        return img, best_cat[:28]

    def _panel_pose(self, store, _results):
        color = self._get_image(store, "color")
        objects = store.get("objects")
        if not isinstance(objects, list):
            return (self._to_bgr(color) if color is not None else None), "no poses"
        base = self._to_bgr(color) if color is not None else self._blank()
        K = self._get_matrix(store, "color_intrinsics") or self._get_matrix(store, "intrinsics")
        drawn = 0
        for idx, obj in enumerate(objects):
            if not isinstance(obj, dict):
                continue
            if self._draw_object_pose(base, obj, K, _palette(idx)):
                drawn += 1
        return base, f"objects={len(objects)}  drawn={drawn}"

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _draw_object_pose(self, img, obj, K, color) -> bool:
        name = str(obj.get("name", obj.get("obj_id", "?")))
        pose = self._to_pose_matrix(obj.get("pose"))
        if pose is None or K is None:
            return False
        origin = pose[:3, 3]
        if not np.isfinite(origin).all() or origin[2] <= 1e-6:
            return False
        axis_len = self._pose_axis_length(obj)
        axes_cam = [
            origin,
            origin + pose[:3, 0] * axis_len,
            origin + pose[:3, 1] * axis_len,
            origin + pose[:3, 2] * axis_len,
        ]
        pts = [self._project(p, K) for p in axes_cam]
        if any(p is None for p in pts):
            return False
        o, x, y, z = pts
        cv2.line(img, o, x, (0, 0, 255), 2)   # X red
        cv2.line(img, o, y, (0, 255, 0), 2)   # Y green
        cv2.line(img, o, z, (255, 0, 0), 2)   # Z blue
        cv2.circle(img, o, 4, color, -1)
        label = f"{name} ({origin[0]:.2f},{origin[1]:.2f},{origin[2]:.2f})"
        cv2.putText(
            img, label, (o[0] + 6, o[1] - 6),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA,
        )
        return True

    def _project(self, point, K):
        z = float(point[2])
        if z <= 1e-6:
            return None
        u = K[0][0] * point[0] / z + K[0][2]
        v = K[1][1] * point[1] / z + K[1][2]
        if not (np.isfinite(u) and np.isfinite(v)):
            return None
        return (int(round(u)), int(round(v)))

    def _pose_axis_length(self, obj) -> float:
        length = obj.get("length")
        try:
            if isinstance(length, (list, tuple)) and length:
                vals = [float(v) for v in np.asarray(length).ravel()[:3]]
                m = max(vals) if vals else 0.0
                if m > 0:
                    return float(min(max(m, 0.03), 0.3))
            elif isinstance(length, (int, float)) and length > 0:
                return float(min(max(length, 0.03), 0.3))
        except Exception:
            pass
        return 0.1

    def _blend_mask(self, img, mask, color, label) -> None:
        binary = mask > 0
        if not binary.any():
            return
        if binary.shape[:2] != img.shape[:2]:
            binary = cv2.resize(
                binary.astype(np.uint8), (img.shape[1], img.shape[0]),
                interpolation=cv2.INTER_NEAREST,
            ).astype(bool)
        tint = np.zeros_like(img)
        tint[binary] = color
        cv2.addWeighted(tint, 0.45, img, 1.0, 0.0, dst=img)
        if label:
            ys, xs = np.where(binary)
            if xs.size:
                cx, cy = int(xs.mean()), int(ys.mean())
                cv2.putText(
                    img, str(label), (cx, cy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA,
                )

    def _draw_text_block(self, img, lines) -> None:
        y = 34
        for line in lines:
            cv2.putText(
                img, line, (12, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (235, 235, 235), 1, cv2.LINE_AA,
            )
            y += 26

    # ------------------------------------------------------------------
    # Image conversion helpers
    # ------------------------------------------------------------------

    def _to_bgr(self, img):
        # Always returns a fresh array so callers can draw onto it without
        # mutating the shared pipeline-store arrays.
        arr = np.asarray(img)
        if arr.ndim == 2:
            return cv2.cvtColor(self._to_uint8(arr), cv2.COLOR_GRAY2BGR)
        if arr.ndim == 3:
            if arr.shape[2] == 1:
                return cv2.cvtColor(self._to_uint8(arr[..., 0]), cv2.COLOR_GRAY2BGR)
            if arr.shape[2] == 4:
                return cv2.cvtColor(self._to_uint8(arr), cv2.COLOR_BGRA2BGR)
            return np.ascontiguousarray(self._to_uint8(arr)).copy()
        return self._blank()

    def _to_uint8(self, arr):
        arr = np.asarray(arr)
        if arr.dtype == np.uint8:
            return arr
        arr = arr.astype(np.float32)
        finite = arr[np.isfinite(arr)]
        if finite.size == 0:
            return np.zeros(arr.shape, dtype=np.uint8)
        lo, hi = float(finite.min()), float(finite.max())
        if hi - lo < 1e-9:
            return np.clip(arr, 0, 255).astype(np.uint8)
        norm = (np.nan_to_num(arr) - lo) / (hi - lo)
        return (np.clip(norm, 0, 1) * 255).astype(np.uint8)

    def _colorize_depth(self, depth):
        arr = np.asarray(depth).astype(np.float32)
        valid = np.isfinite(arr) & (arr > 0)
        out = np.zeros((*arr.shape[:2], 3), dtype=np.uint8)
        if valid.any():
            vals = arr[valid]
            lo, hi = float(np.percentile(vals, 2)), float(np.percentile(vals, 98))
            if hi - lo < 1e-6:
                hi = lo + 1e-6
            norm = np.clip((arr - lo) / (hi - lo), 0, 1)
            colored = cv2.applyColorMap((norm * 255).astype(np.uint8), cv2.COLORMAP_JET)
            out[valid] = colored[valid]
        return out

    def _colorize_label_mask(self, mask):
        arr = np.asarray(mask)
        if arr.ndim == 3:
            arr = arr[..., 0]
        out = np.zeros((*arr.shape[:2], 3), dtype=np.uint8)
        labels = [v for v in np.unique(arr) if v != 0]
        for idx, value in enumerate(labels):
            out[arr == value] = _palette(idx)
        return out

    # ------------------------------------------------------------------
    # Store accessors
    # ------------------------------------------------------------------

    def _get_image(self, store, key):
        value = store.get(key)
        if np is not None and isinstance(value, np.ndarray) and value.size:
            return value
        return None

    def _get_array(self, store, response_key, field):
        resp = store.get(response_key)
        if isinstance(resp, dict):
            value = resp.get(field)
            if np is not None and isinstance(value, np.ndarray) and value.size:
                return value
        return None

    def _get_list(self, store, key):
        value = store.get(key)
        if isinstance(value, (list, tuple)):
            return list(value)
        return []

    def _get_matrix(self, store, key):
        value = store.get(key)
        if value is None:
            return None
        try:
            arr = np.asarray(value, dtype=np.float64).reshape(3, 3)
        except Exception:
            return None
        return arr.tolist()

    def _to_pose_matrix(self, pose):
        if pose is None:
            return None
        try:
            arr = np.asarray(pose, dtype=np.float64)
        except Exception:
            return None
        if arr.shape == (4, 4):
            return arr
        if arr.size == 16:
            return arr.reshape(4, 4)
        return None

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _blank(self):
        return np.full((self.tile_h, self.tile_w, 3), 32, dtype=np.uint8)

    def _placeholder(self, text):
        img = self._blank()
        cv2.putText(
            img, text, (12, self.tile_h // 2),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (120, 120, 120), 1, cv2.LINE_AA,
        )
        return img

    def _fit_tile(self, img):
        """Letterbox *img* into a fixed tile while preserving aspect ratio."""
        img = np.asarray(img)
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        h, w = img.shape[:2]
        if h == 0 or w == 0:
            return self._blank()
        scale = min(self.tile_w / w, self.tile_h / h)
        new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        canvas = np.zeros((self.tile_h, self.tile_w, 3), dtype=np.uint8)
        y0 = (self.tile_h - new_h) // 2
        x0 = (self.tile_w - new_w) // 2
        canvas[y0:y0 + new_h, x0:x0 + new_w] = resized
        return canvas

    def _label_tile(self, tile, title, subtitle):
        bar_h = 24
        cv2.rectangle(tile, (0, 0), (self.tile_w, bar_h), (40, 40, 40), -1)
        cv2.putText(
            tile, title, (8, 17),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 1, cv2.LINE_AA,
        )
        if subtitle:
            (tw, _), _ = cv2.getTextSize(subtitle, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
            cv2.putText(
                tile, subtitle, (max(8, self.tile_w - tw - 8), 17),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 180, 180), 1, cv2.LINE_AA,
            )
        cv2.rectangle(tile, (0, 0), (self.tile_w - 1, self.tile_h - 1), (70, 70, 70), 1)
        return tile

    def _inset_thumbnails(self, base, thumbs):
        if not thumbs:
            return base
        base = base.copy()
        n = len(thumbs)
        th = max(40, base.shape[0] // 4)
        tw = max(40, base.shape[1] // 4)
        for i, thumb in enumerate(thumbs):
            small = cv2.resize(thumb, (tw, th), interpolation=cv2.INTER_AREA)
            x1 = base.shape[1] - tw - 6
            y1 = 6 + i * (th + 6)
            if y1 + th > base.shape[0]:
                break
            base[y1:y1 + th, x1:x1 + tw] = small
            cv2.rectangle(base, (x1, y1), (x1 + tw, y1 + th), (200, 200, 200), 1)
        return base

    def _compose_grid(self, tiles):
        if not tiles:
            return self._blank()
        cols = min(3, len(tiles))
        rows = (len(tiles) + cols - 1) // cols
        blank = self._label_tile(self._blank(), "", "")
        padded = tiles + [blank] * (rows * cols - len(tiles))
        row_imgs = [
            np.hstack(padded[r * cols:(r + 1) * cols]) for r in range(rows)
        ]
        return np.vstack(row_imgs)

    def _add_status_bar(self, composite, frame_id, request_id):
        bar = np.full((28, composite.shape[1], 3), 24, dtype=np.uint8)
        rid = (request_id or "")[:8]
        text = f"TJFusion pipeline   frame={frame_id}   req={rid}   [Ctrl-C in terminal to stop]"
        cv2.putText(
            bar, text, (8, 19),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA,
        )
        return np.vstack([bar, composite])

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def _show(self, composite):
        if not self._imshow_disabled:
            try:
                if not self._window_ready:
                    cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
                    self._window_ready = True
                cv2.imshow(self.window_name, composite)
                cv2.waitKey(1)
                return
            except Exception as exc:  # noqa: BLE001 - headless build / no display
                self._imshow_disabled = True
                print_warning(
                    "OpenCV cannot open a display window "
                    f"({exc}). If you want the live window, install the GUI "
                    "build (pip install opencv-python, not headless) and "
                    "ensure DISPLAY is set."
                )
        self._save_fallback(composite)

    def _save_fallback(self, composite):
        path = self.save_path or "/tmp/tjfusion_pipeline.jpg"
        try:
            cv2.imwrite(path, composite)
            if not self._save_hint_shown:
                print_status(
                    "VIS", f"Writing composite frames to {path}", color="cyan"
                )
                self._save_hint_shown = True
        except Exception:
            pass
