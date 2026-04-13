import argparse
from pathlib import Path

import cv2


def center_crop(img, target_w: int, target_h: int):
	h, w = img.shape[:2]
	if w < target_w or h < target_h:
		raise ValueError(
			f"View size {w}x{h} is smaller than crop size {target_w}x{target_h}."
		)

	x0 = (w - target_w) // 2
	y0 = (h - target_h) // 2
	return img[y0 : y0 + target_h, x0 : x0 + target_w]


def main():
	parser = argparse.ArgumentParser(
		description="Crop each view from a 2x2 stitched video and re-stitch in original order."
	)
	parser.add_argument(
		"--input",
		default="cameras.mp4",
		help="Input 2x2 stitched video path (default: cameras.mp4).",
	)
	parser.add_argument(
		"--output",
		default="cameras_cropped.mp4",
		help="Output video path (default: cameras_cropped.mp4).",
	)
	parser.add_argument(
		"--crop-width",
		type=int,
		default=640,
		help="Crop width for each single view.",
	)
	parser.add_argument(
		"--crop-height",
		type=int,
		default=480,
		help="Crop height for each single view.",
	)
	args = parser.parse_args()

	input_path = Path(args.input)
	output_path = Path(args.output)

	if not input_path.exists():
		raise FileNotFoundError(f"Input video not found: {input_path}")

	cap = cv2.VideoCapture(str(input_path))
	if not cap.isOpened():
		raise RuntimeError(f"Failed to open video: {input_path}")

	fps = cap.get(cv2.CAP_PROP_FPS)
	if fps <= 0:
		fps = 25.0

	writer = None
	processed = 0

	try:
		while True:
			ok, frame = cap.read()
			if not ok:
				break

			h, w = frame.shape[:2]
			if w % 2 != 0 or h % 2 != 0:
				raise ValueError(f"Stitched frame size must be even, got {w}x{h}")

			half_w = w // 2
			half_h = h // 2

			# 2x2 layout:
			# top-left: left eye
			# top-right: right eye
			# bottom-left: right hand
			# bottom-right: left hand
			left_eye = frame[0:half_h+100, 0:half_w]
			right_eye = frame[0:half_h+100, half_w:w]
			right_hand = frame[half_h:h, 0:half_w]
			left_hand = frame[half_h:h, half_w:w]

			left_eye_c = center_crop(left_eye, args.crop_width, args.crop_height)
			right_eye_c = center_crop(right_eye, args.crop_width, args.crop_height)
			right_hand_c = center_crop(right_hand, args.crop_width, args.crop_height)
			left_hand_c = center_crop(left_hand, args.crop_width, args.crop_height)

			top = cv2.hconcat([left_eye_c, right_eye_c])
			bottom = cv2.hconcat([right_hand_c, left_hand_c])
			stitched = cv2.vconcat([top, bottom])

			if writer is None:
				fourcc = cv2.VideoWriter_fourcc(*"mp4v")
				writer = cv2.VideoWriter(
					str(output_path),
					fourcc,
					fps,
					(stitched.shape[1], stitched.shape[0]),
				)
				if not writer.isOpened():
					raise RuntimeError(f"Failed to open output video: {output_path}")

			writer.write(stitched)
			processed += 1
	finally:
		cap.release()
		if writer is not None:
			writer.release()

	print(f"Done. Processed {processed} frames.")
	print(f"Saved: {output_path.resolve()}")


if __name__ == "__main__":
	main()
