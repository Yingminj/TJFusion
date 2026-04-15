#!/usr/bin/env python3
# Minimal script to list unique values in PNG mask files.

import argparse
import numpy as np
from PIL import Image

def unique_values(path):
	img = Image.open(path)
	arr = np.array(img)
	if arr.ndim == 3:
		pixels = arr.reshape(-1, arr.shape[2])
		uniq, counts = np.unique(pixels, axis=0, return_counts=True)
	else:
		uniq, counts = np.unique(arr, return_counts=True)
	return uniq, counts

def fmt(v):
	if isinstance(v, np.ndarray):
		return tuple(int(x) for x in v)
	try:
		return int(v)
	except Exception:
		return v

def main():
	parser = argparse.ArgumentParser(description="Show unique values and counts in PNG mask(s).")
	parser.add_argument("paths", nargs="+", help="PNG file(s)")
	args = parser.parse_args()
	for p in args.paths:
		try:
			uniq, counts = unique_values(p)
		except Exception as e:
			print(f"{p}: error: {e}")
			continue
		print(p)
		for v, c in zip(uniq, counts):
			print(f"  {fmt(v)}: {c}")

if __name__ == "__main__":
	main()
