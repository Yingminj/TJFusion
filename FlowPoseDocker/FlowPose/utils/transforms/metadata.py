from dataclasses import dataclass
import json
import numpy as np
from scipy.spatial.transform import Rotation as _Rot

@dataclass
class Pose(object):
    """Object/Camera pose representation"""

    quaternion: "tuple[float, float, float, float]"
    """quaternion in scale-first format (wxyz)"""

    translation: "tuple[float, float, float]"
    """translation from object (centered) space to camera space"""

    def __post_init__(self):
        assert len(self.quaternion) == 4
        assert len(self.translation) == 3

    def to_affine(self, scale=None):
        """transform to affine transformation (with no additional scaling)

        :return: 4x4 numpy array.

        Here's an example of getting :class:`Pose` from rotation matrix:

        .. doctest::

            >>> from cutoop.data_types import Pose
            >>> from scipy.spatial.transform import Rotation
            >>> x, y, z, w = Rotation.from_matrix([
            ...     [ 0.,  0.,  1.],
            ...     [ 0.,  1.,  0.],
            ...     [-1.,  0.,  0.]
            ... ]).as_quat()
            >>> pose = Pose(quaternion=[w, x, y, z], translation=[1, 1, 1])
            >>> pose.to_affine()
            array([[ 0.,  0.,  1.,  1.],
                   [ 0.,  1.,  0.,  1.],
                   [-1.,  0.,  0.,  1.],
                   [ 0.,  0.,  0.,  1.]], dtype=float32)
        """
        q = self.quaternion
        rot = _Rot.from_quat([q[1], q[2], q[3], q[0]]).as_matrix()
        if scale is not None:
            rot = rot * scale
        trans = np.array(self.translation)
        mtx = np.eye(4).astype(np.float32)
        mtx[:3, :3] = rot
        mtx[:3, 3] = trans
        return mtx


@dataclass
class CameraIntrinsicsBase:
    """Camera intrinsics data.
    The unit of ``fx, fy, cx, cy, width, height`` are all pixels.
    """

    fx: float  # unit: pixel
    fy: float  # unit: pixel
    cx: float  # unit: pixel
    cy: float  # unit: pixel
    width: float  # unit: pixel
    height: float  # unit: pixel

    def to_matrix(self):
        """Transform to 3x3 K matrix. i. e.::

            [[fx, 0,  cx],
             [0,  fy, cy],
             [0,  0,  1 ]]

        :return: 3x3 numpy array.
        """
        fx = self.fx
        fy = self.fy
        cx = self.cx
        cy = self.cy
        return np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])

    def fov_x(self):
        return np.rad2deg(2 * np.arctan2(self.width, 2 * self.fx))

@dataclass
class ViewInfo(Pose):
    intrinsics: CameraIntrinsicsBase
    """Camera intrinsics"""
    scene_obj_path: str
    """Scene object mesh path"""

    background_image_path: str
    background_depth_path: str
    distances: "list[float]"
    kind: str

    def __post_init__(self):
        if not isinstance(self.intrinsics, CameraIntrinsicsBase):
            self.intrinsics = CameraIntrinsicsBase(**self.intrinsics)

@dataclass
class ObjectMetaInfo:
    oid: str
    """Object ID, which is used to index object metadata"""
    class_name: str
    """Class name of the object"""
    class_label: int
    """1-indexed class label of the object"""
    instance_path: str
    """Path to the model mesh file"""
    scale: "list[float]"
    """Scale from `object space` (not NOCS) to the `camera space`.
    For the size of the object, refer to the object meta file."""
    is_background: bool
    """Whether it is marked as a background object."""

    # bounding box side len after scaling (deprecated)
    # should be equal to np.array(obj.meta.scale) * np.array(
    #     objmeta.instance_dict[obj.meta.oid].dimensions
    # )
    bbox_side_len: "list[float]"
    
@dataclass
class ObjectPoseInfo:
    mask_id: int
    """the value identifying this object in mask image"""
    meta: ObjectMetaInfo
    """object meta information."""
    quaternion_wxyz: "list[float]"
    """object rotation in camera space"""
    translation: "list[float]"
    """object translation in camera space"""
    is_valid: bool
    """Whether the object meet requirements (faceup, reasonable real-world location)"""

    # object id in image (from 1 to the number of visible objects, deprecated)
    id: int
    # for data generation
    material: "list[str]"
    world_quaternion_wxyz: "list[float]"
    world_translation: "list[float]"

    def __post_init__(self):
        if not isinstance(self.meta, ObjectMetaInfo):
            self.meta = ObjectMetaInfo(**self.meta)

    def pose(self) -> Pose:
        """Construct :class:`Pose` relative to the camera coordinate."""
        return Pose(quaternion=self.quaternion_wxyz, translation=self.translation)
    
@dataclass
class ImageMetaData:
    objects: "list[ObjectPoseInfo]"
    """A list of visiable objects"""
    camera: ViewInfo
    """Information of the scene"""
    scene_dataset: str
    """Dataset source of the scene"""

    # for data generation
    env_param: dict
    face_up: bool
    concentrated: bool
    comments: str
    runtime_seed: int
    baseline_dis: int
    emitter_dist_l: int

    def __post_init__(self):
        if isinstance(self.objects, dict):
            self.objects = [
                ObjectPoseInfo(**x, mask_id=int(k.split("_")[0]))
                for k, x in self.objects.items()
            ]
        if not isinstance(self.camera, ViewInfo):
            self.camera = ViewInfo(**self.camera)

    @staticmethod
    def load_json(path: str) -> "ImageMetaData":
        """Load object meta data from json file


        .. doctest::

            >>> meta = ImageMetaData.load_json("../../misc/sample_real/000000_meta.json")
            >>> meta.camera.intrinsics
            CameraIntrinsicsBase(fx=915.0556030273438, fy=914.1288452148438, cx=641.2314453125, cy=363.4847412109375, width=1280, height=720)

        """

        with open(path, "r") as f:
            jsondata = json.load(f)

        return ImageMetaData(**jsondata)