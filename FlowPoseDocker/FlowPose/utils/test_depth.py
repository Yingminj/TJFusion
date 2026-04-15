
import numpy as np
import os
os.environ['OPENCV_IO_ENABLE_OPENEXR'] = '1'
import cv2

path_or_img = '/media/kewei/KMD_DATA/dataSOPE/41/train/matterport3d/0052/0000_depth.exr'
# data = cv2.imread(str(path_or_img), cv2.IMREAD_ANYCOLOR | cv2.IMREAD_ANYDEPTH)
# a = cv2.imread(, cv2.IMREAD_ANYCOLOR | cv2.IMREAD_ANYDEPTH)

def load_depth(path_or_img: "str") -> np.ndarray:
    if isinstance(path_or_img, np.ndarray):
        data = path_or_img
        return data
    else:
        data = cv2.imread(str(path_or_img), cv2.IMREAD_ANYCOLOR | cv2.IMREAD_ANYDEPTH)
        if len(data.shape) == 3:
            data = data[:, :, 0]
        
        return data  # unit: m

depth = load_depth(path_or_img)
cv2.imshow('test_image', depth)
cv2.waitKey(0)
cv2.destroyAllWindows()