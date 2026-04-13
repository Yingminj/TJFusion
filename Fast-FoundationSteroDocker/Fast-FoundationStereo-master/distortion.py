import argparse
import re
from pathlib import Path

import cv2
import numpy as np


def parse_intrinsic_file(file_path: Path) -> dict:
	"""Parse camera intrinsic text files supporting both ':' and '=' formats."""
	values = {}
	key_map = {
		"fx": "fx",
		"fy": "fy",
		"cx": "cx",
		"cy": "cy",
		"k1": "k1",
		"k2": "k2",
		"k3": "k3",
		"k4": "k4",
		"k5": "k5",
		"k6": "k6",
		"p1": "p1",
		"p2": "p2",
		"imagewidth": "image_width",
		"imageheight": "image_height",
	}

	with file_path.open("r", encoding="utf-8", errors="ignore") as f:
		for line in f:
			line = line.strip()
			if not line:
				continue

			# Support lines like "FX:973..." and "fx= 976..."
			m = re.match(r"^\s*([A-Za-z0-9_]+)\s*[:=]\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", line)
			if not m:
				continue

			raw_key = m.group(1).strip().lower()
			raw_val = float(m.group(2))
			if raw_key in key_map:
				values[key_map[raw_key]] = raw_val

	required = ["fx", "fy", "cx", "cy", "k1", "k2", "p1", "p2", "k3", "k4", "k5", "k6"]
	missing = [k for k in required if k not in values]
	if missing:
		raise ValueError(f"{file_path} missing fields: {missing}")

	return values


def parse_intrinsics_from_yaml(file_path: Path) -> tuple[dict, dict]:
	"""Read left/right camera intrinsics from calibration_all.yaml."""
	fs = cv2.FileStorage(str(file_path), cv2.FILE_STORAGE_READ)
	if not fs.isOpened():
		raise RuntimeError(f"Failed to open calibration yaml: {file_path}")

	try:
		left_k = fs.getNode("left_eye_K").mat()
		left_d = fs.getNode("left_eye_D").mat()
		right_k = fs.getNode("right_eye_K").mat()
		right_d = fs.getNode("right_eye_D").mat()
	finally:
		fs.release()

	if left_k is None or left_d is None or right_k is None or right_d is None:
		raise ValueError("YAML missing one of: left_eye_K, left_eye_D, right_eye_K, right_eye_D")

	def _pack_params(k: np.ndarray, d: np.ndarray) -> dict:
		d_flat = d.reshape(-1)
		if d_flat.size < 8:
			raise ValueError("Distortion vector must contain at least 8 coefficients (k1,k2,p1,p2,k3,k4,k5,k6)")
		return {
			"fx": float(k[0, 0]),
			"fy": float(k[1, 1]),
			"cx": float(k[0, 2]),
			"cy": float(k[1, 2]),
			"k1": float(d_flat[0]),
			"k2": float(d_flat[1]),
			"p1": float(d_flat[2]),
			"p2": float(d_flat[3]),
			"k3": float(d_flat[4]),
			"k4": float(d_flat[5]),
			"k5": float(d_flat[6]),
			"k6": float(d_flat[7]),
		}

	return _pack_params(left_k, left_d), _pack_params(right_k, right_d)


def build_undistort_maps(params: dict, frame_w: int, frame_h: int):
	"""Build undistort remap matrices, scaling intrinsics if calib size is known."""
	calib_w = params.get("image_width", frame_w)
	calib_h = params.get("image_height", frame_h)
	sx = frame_w / calib_w
	sy = frame_h / calib_h

	k = np.array(
		[
			[params["fx"] * sx, 0.0, params["cx"] * sx],
			[0.0, params["fy"] * sy, params["cy"] * sy],
			[0.0, 0.0, 1.0],
		],
		dtype=np.float64,
	)

	# Rational model coefficients: [k1, k2, p1, p2, k3, k4, k5, k6]
	dist = np.array(
		[
			params["k1"],
			params["k2"],
			params["p1"],
			params["p2"],
			params["k3"],
			params["k4"],
			params["k5"],
			params["k6"],
		],
		dtype=np.float64,
	)

	new_k, _ = cv2.getOptimalNewCameraMatrix(k, dist, (frame_w, frame_h), 0.0)
	map1, map2 = cv2.initUndistortRectifyMap(k, dist, None, new_k, (frame_w, frame_h), cv2.CV_16SC2)
	return map1, map2


def label_image(img: np.ndarray, text: str) -> np.ndarray:
	out = img.copy()
	# cv2.rectangle(out, (10, 10), (300, 48), (0, 0, 0), -1)
	# cv2.putText(out, text, (18, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2, cv2.LINE_AA)
	return out


def main():
	parser = argparse.ArgumentParser(description="Undistort top-left/top-right eye views from a 2x2 stitched video.")
	parser.add_argument(
		"--stitched-width",
		type=int,
		default=1920,
		help="Expected stitched frame width before 2x2 split.",
	)
	parser.add_argument(
		"--stitched-height",
		type=int,
		default=1488,
		help="Expected stitched frame height before 2x2 split.",
	)
	parser.add_argument(
		"--video",
		default="/media/kewei/DATA-S2/0330/d2_cameras_h264.mp4",
		help="Input stitched 2x2 video path.",
	)
	parser.add_argument(
		"--calib-yaml",
		default="calib_output/calibration_all.yaml",
		help="Calibration yaml with left_eye_K/D and right_eye_K/D.",
	)
	parser.add_argument(
		"--output",
		default="undistort_compare_lr.mp4",
		help="Output comparison video path.",
	)
	args = parser.parse_args()

	video_path = Path(args.video)
	calib_yaml_path = Path(args.calib_yaml)
	output_path = Path(args.output)
	snapshot_path = Path("undistort_compare_lr_first_frame.jpg")
	target_w = args.stitched_width
	target_h = args.stitched_height
	quad_w = target_w // 2
	quad_h = target_h // 2

	if target_w % 2 != 0 or target_h % 2 != 0:
		raise ValueError(f"stitched size must be even, got {target_w}x{target_h}")

	if not video_path.exists():
		raise FileNotFoundError(f"Video not found: {video_path}")
	if not calib_yaml_path.exists():
		raise FileNotFoundError(f"Calibration yaml not found: {calib_yaml_path}")

	left_params, right_params = parse_intrinsics_from_yaml(calib_yaml_path)

	cap = cv2.VideoCapture(str(video_path))
	if not cap.isOpened():
		raise RuntimeError(f"Failed to open video: {video_path}")

	fps = cap.get(cv2.CAP_PROP_FPS)
	if fps <= 0:
		fps = 25.0

	writer = None
	left_map1 = left_map2 = None
	right_map1 = right_map2 = None
	first_saved = False

	try:
		while True:
			ok, frame = cap.read()
			if not ok:
				break

			h, w = frame.shape[:2]
			if w < target_w or h < target_h:
				raise ValueError(
					f"input frame {w}x{h} is smaller than required {target_w}x{target_h}, cannot crop"
				)

			# Center crop to fixed stitched size first, then split into 4 equal views.
			x0 = (w - target_w) // 2
			y0 = (h - target_h) // 2
			frame_fixed = frame[y0 : y0 + target_h, x0 : x0 + target_w]

			# 2x2 layout: TL=left eye, TR=right eye, BL=right hand, BR=left hand
			left_eye = frame_fixed[0:quad_h, 0:quad_w]
			right_eye = frame_fixed[0:quad_h, quad_w:target_w]

			if left_map1 is None:
				left_map1, left_map2 = build_undistort_maps(left_params, left_eye.shape[1], left_eye.shape[0])
				right_map1, right_map2 = build_undistort_maps(right_params, right_eye.shape[1], right_eye.shape[0])

				vis_h = left_eye.shape[0] + right_eye.shape[0]
				vis_w = left_eye.shape[1] * 2
				fourcc = cv2.VideoWriter_fourcc(*"mp4v")
				writer = cv2.VideoWriter(str(output_path), fourcc, fps, (vis_w, vis_h))
				if not writer.isOpened():
					raise RuntimeError(f"Failed to open writer: {output_path}")

			left_ud = cv2.remap(left_eye, left_map1, left_map2, interpolation=cv2.INTER_LINEAR)
			right_ud = cv2.remap(right_eye, right_map1, right_map2, interpolation=cv2.INTER_LINEAR)

			top = cv2.hconcat([label_image(left_eye, "Left Eye Raw"), label_image(left_ud, "Left Eye Undistort")])
			bottom = cv2.hconcat([label_image(right_eye, "Right Eye Raw"), label_image(right_ud, "Right Eye Undistort")])
			vis = cv2.vconcat([top, bottom])

			cv2.imshow("Left/Right Eye Undistortion Compare", vis)
			writer.write(vis)

			if not first_saved:
				cv2.imwrite(str(snapshot_path), vis)
				first_saved = True

			key = cv2.waitKey(1) & 0xFF
			if key in (27, ord("q")):
				break
	finally:
		cap.release()
		if writer is not None:
			writer.release()
		cv2.destroyAllWindows()

	print(f"Saved compare video: {output_path.resolve()}")
	if first_saved:
		print(f"Saved first-frame image: {snapshot_path.resolve()}")


if __name__ == "__main__":
	main()
