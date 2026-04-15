import torch.utils.data as data
import webdataset as wds
import pickle
import numpy as np
import json
import os
import cv2
import torch

os.environ["OPENCV_IO_ENABLE_OPENEXR"]="1"
from dataset.augmentation import rgb_transform, depth_to_pcl, sample_points
from utils.transforms.rotation import SymLabel
from utils.transforms.mask import get_2d_coord_np, crop_resize_by_warp_affine
from utils.transforms.box import get_bbox, aug_bbox_eval
from utils.transforms.pixel import pixel2xyz
from utils.transforms.metadata import ImageMetaData, ViewInfo, CameraIntrinsicsBase

def load_color(path_or_img: "str | os.PathLike | np.ndarray") -> np.ndarray:
        if path_or_img is None:
            return None
        
        if isinstance(path_or_img, np.ndarray):
            data = path_or_img
            return data
        else:
            data = cv2.imread(str(path_or_img))[:, :, ::-1]  # RGB order
            return data

def load_depth(path_or_img: "str | os.PathLike | np.ndarray") -> np.ndarray:
        if path_or_img is None:
            return None
        if isinstance(path_or_img, np.ndarray):
            data = path_or_img
            return data
        else:
            data = cv2.imread(str(path_or_img), cv2.IMREAD_ANYCOLOR | cv2.IMREAD_ANYDEPTH)
            if len(data.shape) == 3:
                data = data[:, :, 0]
            
            return data  # unit: m
        
def load_mask(path_or_img: "str | os.PathLike | np.ndarray") -> np.ndarray:
        if path_or_img is None:
            return None
        
        if isinstance(path_or_img, np.ndarray):
            data = path_or_img
            return data
        else:
            data = cv2.imread(str(path_or_img), cv2.IMREAD_ANYCOLOR | cv2.IMREAD_ANYDEPTH)
            if len(data.shape) == 3:
                data = data[:, :, 2]
            return np.array(data * 255, dtype=np.uint8)

def array_to_CameraIntrinsicsBase(intrinsics_list):
    return [CameraIntrinsicsBase(*item) for item in intrinsics_list]

def array_to_SymLabel(arr_Nx4: np.ndarray):
    syms_N = []
    tags = ['none', 'any', 'half', 'quarter']
    for a, x, y, z in arr_Nx4:
        syms_N.append(SymLabel(bool(a), tags[x], tags[y], tags[z]))
    return syms_N

class OmniXTrainDataset(data.IterableDataset):
    def __init__(self, shard_path, transform=None, shuffle=1000):
        """
        Args:
            shard_path: Path pattern to shards
            transform: Optional transforms
            shuffle: Shuffle buffer size (0 for no shuffle)
        """
        self.shard_path = shard_path
        self.transform = transform
        self.shuffle = shuffle
        
    def __iter__(self):
        dataset = (
            wds.WebDataset(self.shard_path)
            .shuffle(self.shuffle)
            .decode(self._pose_data_decoder)
        )
        
        for sample in dataset:
            if self.transform:
                sample = self.transform(sample)
            yield sample
    
    @staticmethod
    def _pose_data_decoder(sample):
        """Custom decoder to reconstruct numpy arrays from bytes"""
        try:
            rgb_bytes = sample["rgb.pyd"]
            rgb_shape = pickle.loads(sample["rgb_shape.pyd"])
            rgb_dtype = np.dtype(sample["rgb_dtype.txt"].decode('utf-8'))
            rgb = np.frombuffer(rgb_bytes, dtype=rgb_dtype).reshape(rgb_shape).copy()
            
            depth_bytes = sample["depth.pyd"]
            depth_shape = pickle.loads(sample["depth_shape.pyd"])
            depth_dtype = np.dtype(sample["depth_dtype.txt"].decode('utf-8'))
            depth = np.frombuffer(depth_bytes, dtype=depth_dtype).reshape(depth_shape).copy()
            
            mask_bytes = sample["mask.pyd"]
            mask_shape = pickle.loads(sample["mask_shape.pyd"])
            mask_dtype = np.dtype(sample["mask_dtype.txt"].decode('utf-8'))
            mask = np.frombuffer(mask_bytes, dtype=mask_dtype).reshape(mask_shape).copy()
            
            meta = json.loads(sample["meta.json"].decode('utf-8'))
            
            return {
                "rgb": rgb,
                "depth": depth,
                "mask": mask,
                "meta": meta
            }
        except Exception as e:
            print(f"Decoder error: {e}")
            print(f"Sample keys: {list(sample.keys())}")
            raise

class OmniXInferDataset(object):
    def __init__(self, data: dict, img_size: int=224, device='cuda', n_pts=1024):
        """
        Args:
            data (dict): dictionary containing depth, color, mask, and meta data
                depth (np.ndarray): depth image
                color (np.ndarray): color image
                mask (np.ndarray): mask image
                meta (dict): camera intrinsics
            img_size (int): size of the image to be used for the network
            device (str): device to be used for the network
            n_pts (int): number of points to be used for the network
        """
        self._depth: np.ndarray = data['depth']
        self._color: np.ndarray = data['color']
        self._mask: np.ndarray = data['mask']
        self.intrinsics= {
            "fx": 606.5540161132812,
            "fy": 606.3988647460938,
            "cx": 325.6007080078125,
            "cy": 252.87457275390625,
            "width": 640,
            "height": 480
            }
        
        camera_intrinsics = self.intrinsics
        camera_intrinsics = CameraIntrinsicsBase(
            fx=camera_intrinsics['fx'],
            fy=camera_intrinsics['fy'],
            cx=camera_intrinsics['cx'],
            cy=camera_intrinsics['cy'],
            width=camera_intrinsics['width'],
            height=camera_intrinsics['height']
        )
        camera = ViewInfo(None, None, camera_intrinsics, None, None, None, None, None)
        self._meta: ImageMetaData = ImageMetaData(None, camera, None, None, None, None, None, None, None, None)
        self._img_size = img_size
        self._device = device
        self._n_pts = n_pts

    @classmethod
    def alternetive_init(cls, data, img_size: int=224, device='cuda', n_pts=1024, intrinsics=None):
        """
        Requires depth in meters and mask in uint8 with 0 as background and non-zero as object
        
        """
        if isinstance(data, dict):
            depth = load_depth(data.get("depth"))/1000
            color = load_color(data.get("color"))
            mask = load_mask(data.get("mask"))
        else:
            prefix = data if data.endswith(os.sep) else data + os.sep
            prefix = data.rstrip("/\\")
            depth_file = prefix + "depth.exr"
            color_file = prefix + "color.png"
            mask_file  = prefix + "mask.png"
            depth = load_depth(depth_file)
            color = load_color(color_file)
            mask = load_mask(mask_file)
            
        if depth is None:
            print("Warning: depth is None")
        if color is None:
            print("Warning: color is None")
        if mask is None:
            print("Warning: mask is None")
        print(f'mask shape: {mask.shape}, unique values: {np.unique(mask)[:10]}')
        
        # Create dataset instance
        dataset = cls({'depth': depth, 'color': color, 'mask': mask}, 
                  img_size=img_size, device=device, n_pts=n_pts)
    
        # Override intrinsics if provided
        if intrinsics is not None:
            dataset.intrinsics = intrinsics
            # Update the meta camera intrinsics
            camera_intrinsics = CameraIntrinsicsBase(
                fx=intrinsics['fx'],
                fy=intrinsics['fy'],
                cx=intrinsics['cx'],
                cy=intrinsics['cy'],
                width=intrinsics['width'],
                height=intrinsics['height']
            )
            dataset._meta.camera.intrinsics = camera_intrinsics
    
        return dataset
    
    def get_per_object(self, obj_idx): ##
        object_mask = np.equal(self._mask, obj_idx)
        if not object_mask.any():
            assert False, f"Object {obj_idx} not found in mask"
        max_depth = 3 ###!!!
        self._depth[self._depth > max_depth] = 0
        if not (self._mask.shape[:2] == self._depth.shape[:2] == self._color.shape[:2]):
            assert False, "depth, mask, and rgb should have the same shape"
        intrinsics = self._meta.camera.intrinsics
        intrinsic_matrix = np.array([
            [intrinsics.fx, 0,             intrinsics.cx], 
            [0,             intrinsics.fy, intrinsics.cy], 
            [0,             0,             1]
            ], dtype=np.float32)
        
        img_width, img_height = self._color.shape[1], self._color.shape[0]
        scale_x = img_width / intrinsics.width
        scale_y = img_height / intrinsics.height
        intrinsic_matrix[0] *= scale_x
        intrinsic_matrix[1] *= scale_y

        coord_2d = get_2d_coord_np(img_width, img_height).transpose(1, 2, 0)

        ys, xs = np.argwhere(object_mask).transpose(1, 0)
        rmin, rmax, cmin, cmax = np.min(ys), np.max(ys), np.min(xs), np.max(xs)
        rmin, rmax, cmin, cmax = get_bbox([rmin, cmin, rmax, cmax], img_height, img_width)

        # here resize and crop to a fixed size 224 x 224
        bbox_xyxy = np.array([cmin, rmin, cmax, rmax])
        bbox_center, scale = aug_bbox_eval(bbox_xyxy, img_height, img_width)

        # crop and resize
        roi_coord_2d = crop_resize_by_warp_affine(
            coord_2d, bbox_center, scale, self._img_size, interpolation=cv2.INTER_NEAREST
        ).transpose(2, 0, 1)

        roi_rgb_ = crop_resize_by_warp_affine(
            self._color, bbox_center, scale, self._img_size, interpolation=cv2.INTER_LINEAR
        )
        roi_rgb = rgb_transform(roi_rgb_)

        mask_target = self._mask.copy().astype(np.float32)
        mask_target[self._mask != obj_idx] = 0.0
        mask_target[self._mask == obj_idx] = 1.0

        # depth[mask_target == 0.0] = 0.0
        roi_mask = crop_resize_by_warp_affine(
            mask_target, bbox_center, scale, self._img_size, interpolation=cv2.INTER_NEAREST
        )
        roi_mask = np.expand_dims(roi_mask, axis=0)
        roi_depth = crop_resize_by_warp_affine(
            self._depth, bbox_center, scale, self._img_size, interpolation=cv2.INTER_NEAREST
        )

        roi_depth = np.expand_dims(roi_depth, axis=0)

        valid = (np.squeeze(roi_depth, axis=0) > 0) * (np.squeeze(roi_mask, axis=0) > 0)
        xs, ys = np.argwhere(valid).transpose(1, 0)
        valid = valid.reshape(-1)
        pcl_in = depth_to_pcl(roi_depth, intrinsic_matrix, roi_coord_2d, valid)
        # print(pcl_in)
        # quit()

        if len(pcl_in) < 10:
            # assert False, f"Not enough points for pose estimation. {len(pcl_in)} points found"
            print(f"Warning: Not enough points for pose estimation. {len(pcl_in)} points found")
            return None
        ids, pcl_in = sample_points(pcl_in, self._n_pts)
        xs, ys = xs[ids], ys[ids]

        data = {}
        data['pcl_in'] = torch.as_tensor(pcl_in.astype(np.float32)).contiguous()
        data['roi_rgb'] = torch.as_tensor(np.ascontiguousarray(roi_rgb), dtype=torch.float32).contiguous()
        data['roi_rgb_'] = torch.as_tensor(np.ascontiguousarray(roi_rgb_), dtype=torch.uint8).contiguous()
        data['roi_xs'] = torch.as_tensor(np.ascontiguousarray(xs), dtype=torch.int64).contiguous()
        data['roi_ys'] = torch.as_tensor(np.ascontiguousarray(ys), dtype=torch.int64).contiguous()
        data['roi_center_dir'] = torch.as_tensor(pixel2xyz(img_height, img_height, bbox_center, intrinsics), dtype=torch.float32).contiguous()

        return data
    
    def get_objects(self): ##
        obj_idx = np.unique(self._mask)
        obj_idx = obj_idx[(obj_idx != 0) & (obj_idx != 255)]  # remove background and unknown/invalid labels
        objects = {}
        labels = []

        for idx in obj_idx:
            obj = self.get_per_object(idx)
            if obj is None:
                continue
            
            labels.append(int(idx))

            for key, value in obj.items():
                if key not in objects:
                    objects[key] = []
                objects[key].append(value)

        for key, value in objects.items():
            objects[key] = torch.stack(value, dim=0)
            if 'pcl_in' not in objects:
                raise ValueError(f"No valid objects found / no pcl_in produced. Mask unique values: {np.unique(self._mask)}")
            
        try:
            PC_da = objects['pcl_in'].to(self._device)
        except:
            print(f"Warning: No valid pcl_in found for any object. Mask unique values: {np.unique(self._mask)}")
            return None
        
        data = {}
        data['labels'] = labels                     # list of object ids
        data['pts'] = PC_da                         # [bs, 1024, 3]
        data['pts_color'] = PC_da                   # [bs, 1024, 3]
        data['roi_rgb'] = objects['roi_rgb'].to(self._device)   # [bs, 3, imgsize, imgsize]
        assert data['roi_rgb'].shape[-1] == data['roi_rgb'].shape[-2]
        assert data['roi_rgb'].shape[-1] % 14 == 0

        data['roi_xs'] = objects['roi_xs'].to(self._device)     # [bs, 1024]
        data['roi_ys'] = objects['roi_ys'].to(self._device)     # [bs, 1024]
        data['roi_center_dir'] = objects['roi_center_dir'].to(self._device)     # [bs, 3]

        """ zero center """
        num_pts = data['pts'].shape[1]
        zero_mean = torch.mean(data['pts'][:, :, :3], dim=1)
        # data['zero_mean_pts'] = copy.deepcopy(data['pts'])
        data['zero_mean_pts'] = data['pts'].clone()
        data['zero_mean_pts'][:, :, :3] -= zero_mean.unsqueeze(1).repeat(1, num_pts, 1)
        data['pts_center'] = zero_mean

        return data

    @property
    def cam_intrinsics(self):
        return self._meta.camera.intrinsics
    
    @cam_intrinsics.setter
    def cam_intrinsics(self, intrinsics):
        self._meta.camera.intrinsics = intrinsics

class OmniXValDataset(data.IterableDataset):
    def __init__(self, shard_path, transform=None, drop_step=1, per_object=False):
        """
        Args:
            shard_path: Path pattern to shards
            transform: Optional transforms
            drop_step: Keep 1 every drop_step samples (e.g., drop_step=5 keeps every 5th sample)
            per_object: If True, yield each object in an image separately (for evaluation).
        """
        self.shard_path = shard_path
        self.transform = transform
        self.drop_step = max(1, drop_step)
        self.per_object = per_object
        
    def __iter__(self):
        dataset = wds.WebDataset(self.shard_path, shardshuffle=False)
        
        count = 0
        for sample in dataset:
            # keep every Nth sample
            if self.drop_step > 1:
                if count % self.drop_step != 0:
                    count += 1
                    continue
            
            # Decode the sample manually
            try:
                decoded_sample = self._decode_sample(sample)
            except Exception as e:
                print(f"Error decoding sample: {e}")
                count += 1
                continue
            
            if self.transform:
                decoded_sample = self.transform(decoded_sample)
            
            count += 1
            
            # Handle per_object mode
            if self.per_object and isinstance(decoded_sample, list):
                for s in decoded_sample:
                    if s is not None:
                        yield s
            elif decoded_sample is not None:
                yield decoded_sample
    
    @staticmethod
    def _decode_sample(sample):
        """Decode webdataset sample to standard format"""
        try:
            rgb_bytes = sample["rgb.pyd"]
            rgb_shape = pickle.loads(sample["rgb_shape.pyd"])
            rgb_dtype = np.dtype(sample["rgb_dtype.txt"].decode('utf-8'))
            rgb = np.frombuffer(rgb_bytes, dtype=rgb_dtype).reshape(rgb_shape).copy()
            
            depth_bytes = sample["depth.pyd"]
            depth_shape = pickle.loads(sample["depth_shape.pyd"])
            depth_dtype = np.dtype(sample["depth_dtype.txt"].decode('utf-8'))
            depth = np.frombuffer(depth_bytes, dtype=depth_dtype).reshape(depth_shape).copy()
            
            mask_bytes = sample["mask.pyd"]
            mask_shape = pickle.loads(sample["mask_shape.pyd"])
            mask_dtype = np.dtype(sample["mask_dtype.txt"].decode('utf-8'))
            mask = np.frombuffer(mask_bytes, dtype=mask_dtype).reshape(mask_shape).copy()
            
            meta = json.loads(sample["meta.json"].decode('utf-8'))
            
            return {
                "rgb": rgb,
                "depth": depth,
                "mask": mask,
                "meta": meta
            }
        except Exception as e:
            print(f"Decoder error: {e}")
            print(f"Sample keys: {list(sample.keys())}")
            raise