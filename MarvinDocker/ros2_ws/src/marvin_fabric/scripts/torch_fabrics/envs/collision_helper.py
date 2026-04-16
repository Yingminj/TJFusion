import numpy as np
import yaml
import pinocchio as pin
from pinocchio.visualize import MeshcatVisualizer
import time
from hppfcl import Sphere, Capsule, CollisionObject, Transform3f, CollisionRequest, CollisionResult



def draw_point_sphere(viz, name, position, radius=0.01, color=(1, 0, 0)):
    import meshcat.geometry as mg
    import meshcat.transformations as mtf
    
    viz.viewer[name].set_object(
        mg.Sphere(radius),
        mg.MeshBasicMaterial(
            color=color
        )
    )
    viz.viewer[name].set_transform(mtf.translation_matrix(position))

    
def softplus(x, beta=50):
    return np.log(1 + np.exp(beta * x)) / beta


def get_link_spheres(config, link_name):
    spheres = config["geometry"]["ur10e_collision_spheres"]["spheres"]
    if link_name not in spheres:
        return []

    return [(s["center"], s["radius"]) for s in spheres[link_name]]



def approximate_geom_model(
    spheres: dict,
    capsules: dict,
    model: pin.Model,
    geom_model: pin.GeometryModel,
    default_radius: float = 0.05
):
    """
    用多个球体近似原始几何模型中每个 link 的碰撞几何，并为每个球体添加一个对应的 frame。

    :param spheres: dict, key 为 link 名称，value 为 list of {"center": [x, y, z], "radius": r}
    :param capsules: dict, 暂未使用（保留扩展）
    :param model: Pinocchio 模型
    :param geom_model: 原始的 GeometryModel（通常是 collision 模型）
    :param default_radius: 默认半径（如果未提供 radius）
    :return:
        new_geom_model: 包含球体的新 GeometryModel
        link_to_obj_indices: 每个 link 对应的球体 GeometryObject 索引
        sphere_idx_to_frame_idx: 球体索引到 frame 索引的映射
    """
    new_geom_model = pin.GeometryModel()

    idx = 0
    link_to_obj_indices = {}
    sphere_idx_to_frame_idx = {}

    for geom in geom_model.geometryObjects:
        geom_name = geom.name
        if geom_name.endswith("_0"):
            geom_name = geom_name[:-2]
        parent_joint = geom.parentJoint
        indices = []

        # 每个 link 对应多个球体
        if geom_name in spheres:
            link_spheres = spheres[geom_name]

            for i, item in enumerate(link_spheres):
                center = np.array(item["center"])
                radius = item.get("radius", default_radius)

                # === 创建球体 ===
                sphere = Sphere(radius)
                placement = pin.SE3(pin.Quaternion.Identity(), center)

                # 唯一名称
                new_name = f"{geom_name}_sphere_{i}"

                # === 添加几何对象 ===
                new_obj = pin.GeometryObject(new_name, parent_joint, placement, sphere)
                new_obj.overrideMaterial = True
                new_obj.meshColor = np.array([0.5, 0.5, 0.5, 1.0])
                new_geom_model.addGeometryObject(new_obj)
                indices.append(idx)

                # === 为该球体添加 Frame ===
                frame_id = model.addFrame(
                    pin.Frame(
                        new_name,
                        parent_joint,
                        placement,
                        pin.FrameType.OP_FRAME  # 操作 frame，能直接获取 Jacobian
                    )
                )
                sphere_idx_to_frame_idx[idx] = frame_id
                idx += 1

            link_to_obj_indices[geom_name] = indices

    geom_number = idx
    print(f"✅ Added {geom_number} sphere geometries and {geom_number} frames.")

    return model, new_geom_model, link_to_obj_indices, sphere_idx_to_frame_idx

def approximate_geom_model(
    spheres: dict,
    model: pin.Model,
    geom_model: pin.GeometryModel,
    default_radius: float = 0.05
):
    """
    用多个球体近似原始几何模型中每个 link 的碰撞几何，并为每个球体添加一个对应的 frame。

    :param spheres: dict, key 为 link 名称，value 为 list of {"center": [x, y, z], "radius": r}
    :param capsules: dict, 暂未使用（保留扩展）
    :param model: Pinocchio 模型
    :param geom_model: 原始的 GeometryModel（通常是 collision 模型）
    :param default_radius: 默认半径（如果未提供 radius）
    :return:
        new_geom_model: 包含球体的新 GeometryModel
        link_to_obj_indices: 每个 link 对应的球体 GeometryObject 索引
        sphere_idx_to_frame_idx: 球体索引到 frame 索引的映射
    """
    new_geom_model = pin.GeometryModel()

    idx = 0
    link_to_obj_indices = {}
    sphere_idx_to_frame_idx = {}

    for geom in geom_model.geometryObjects:
        geom_name = geom.name
        if geom_name.endswith("_0"):
            geom_name = geom_name[:-2]
        parent_joint = geom.parentJoint
        indices = []

        # 每个 link 对应多个球体
        if geom_name in spheres:
            link_spheres = spheres[geom_name]

            for i, item in enumerate(link_spheres):
                center = np.array(item["center"])
                radius = item.get("radius", default_radius)

                # === 创建球体 ===
                sphere = Sphere(radius)
                placement = pin.SE3(pin.Quaternion.Identity(), center)

                # 唯一名称
                new_name = f"{geom_name}_sphere_{i}"

                # === 添加几何对象 ===
                new_obj = pin.GeometryObject(new_name, parent_joint, placement, sphere)
                new_obj.overrideMaterial = True
                new_obj.meshColor = np.array([0.5, 0.5, 0.5, 1.0])
                new_geom_model.addGeometryObject(new_obj)
                indices.append(idx)

                # === 为该球体添加 Frame ===
                frame_id = model.addFrame(
                    pin.Frame(
                        new_name,
                        parent_joint,
                        placement,
                        pin.FrameType.OP_FRAME  # 操作 frame，能直接获取 Jacobian
                    )
                )
                sphere_idx_to_frame_idx[idx] = frame_id
                idx += 1

            link_to_obj_indices[geom_name] = indices

    geom_number = idx
    print(f"✅ Added {geom_number} sphere geometries and {geom_number} frames.")

    return model, new_geom_model, link_to_obj_indices, sphere_idx_to_frame_idx