import sys
sys.path.append("/robotaction/scripts")
from pose_correct import correct_orientation
import numpy as np
from scipy.spatial.transform import Rotation as R
from geometry_msgs.msg import Pose


class ActionHandler:
    def __init__(self, template, node=None):
        self.node = node
        self.action_map = {}

        # 修复：这里不要用 template_yaml（未定义）
        template_yaml = template or {}
        if not isinstance(template_yaml, dict):
            raise TypeError(f"template must be dict, got {type(template_yaml)}")

        for k, v in template_yaml.items():
            self.action_map[k] = v

        # build top_level_actions
        self.top_level_actions = []
        for k, v in template_yaml.items():
            if k in ("obj_name", "action_type"):
                continue
            self.top_level_actions.append((k, v))

    def process_for_object(self, tf_pose, action_name, task_arm=None, task_speed=1.0, correction_mode="none"):
        blocks = self.action_map.get(action_name, [])
        if not isinstance(blocks, list):
            blocks = [blocks]

        # 跳过空 block，避免 block={}
        blocks = [b for b in blocks if isinstance(b, dict) and b]

        if not blocks:
            self._warn(f"Action '{action_name}' not found or empty in template.")
            return []

        all_kps = []
        for block in blocks:
            all_kps.extend(
                self._process_single_block(
                    block, action_name, tf_pose,
                    task_arm=task_arm, task_speed=task_speed, correction_mode=correction_mode
                )
            )
        return all_kps

    def _process_single_block(self, block, action_name, ts_transform,
                            task_arm=None, task_speed=None, correction_mode="none"):
        if block is None:
            return []

        rotation_constraint = block.get("rotation_constraint", [1, 1, 1])
        pose_rel = block.get("pose_relative")
        gripper_states = block.get("gripper_state", [])
        time_list = block.get("time", [])

        if pose_rel is None:
            self._warn("Warning: pose_relative is None in block: %s" % (block,))
            return []
        if isinstance(pose_rel[0], (float, int)):
            pose_rel_list = [pose_rel]
        else:
            pose_rel_list = pose_rel

        arm = task_arm
        speed = task_speed

        if not isinstance(gripper_states, list):
            gripper_states = [gripper_states]
        if not isinstance(time_list, list):
            time_list = [time_list]

        final_arm = arm  # 保存初始 arm 值
        poses = []

        for rel in pose_rel_list:
            pos_world, quat_world = self.apply_relative(ts_transform, rel, correction_mode, final_arm)
            pose_msg = self.to_pose_msg(pos_world, quat_world)
            poses.append(pose_msg)
        
        # 保存当前 arm 到 node 供下一个动作使用
        if final_arm not in ("correct", "copy last one") and final_arm is not None:
            if self.node:
                self.node.last_arm = final_arm
        else:
            print(f"[DEBUG] Not saving arm: final_arm={final_arm}")

        return [{
            "name": action_name,
            "arm": final_arm,
            "poses": poses,
            "constraints": [
                float(rotation_constraint[0]),
                float(rotation_constraint[1]),
                float(rotation_constraint[2])
            ],
            "speed": float(speed if speed is not None else 1.0),
            "gripper_value": gripper_states,
            "time": time_list,
        }]

    def to_pose_msg(self, pos, quat):
        p = Pose()
        p.position.x, p.position.y, p.position.z = float(pos[0]), float(pos[1]), float(pos[2])
        p.orientation.x, p.orientation.y, p.orientation.z, p.orientation.w = float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3])
        return p

    def apply_relative(self, ts_transform, rel, correction_mode="org", arm=None):
        # 支持 ts_transform 为 None（例如 base_link），此时使用单位位姿
        if ts_transform is None:
            t_world_org = np.zeros(3, dtype=float)
            q_world_org = np.array([0.0, 0.0, 0.0, 1.0], dtype=float)
        else:
            t_world_org = np.array([ts_transform.translation.x,
                                    ts_transform.translation.y,
                                    ts_transform.translation.z], dtype=float)
            q_world_org = np.array([ts_transform.rotation.x,
                                    ts_transform.rotation.y,
                                    ts_transform.rotation.z,
                                    ts_transform.rotation.w], dtype=float)
        t_world, q_world = correct_orientation(t_world_org, q_world_org, mode=correction_mode, arm=arm)
        
        t_relative = np.array(rel[:3], dtype=float)
        q_relative = np.array(rel[3:], dtype=float)

        # normalize quats
        if np.linalg.norm(q_world) > 1e-8:
            q_world = q_world / np.linalg.norm(q_world)
        else:
            q_world = np.array([0.0, 0.0, 0.0, 1.0], dtype=float)
        if np.linalg.norm(q_relative) > 1e-8:
            q_relative = q_relative / np.linalg.norm(q_relative)
        else:
            q_relative = np.array([0.0, 0.0, 0.0, 1.0], dtype=float)

        r_world_rot = R.from_quat(q_world)
        r_relative_rot = R.from_quat(q_relative)

        pos_final = r_world_rot.apply(t_relative) + t_world
        r_final = r_world_rot * r_relative_rot
        q_final = r_final.as_quat()
        return pos_final.tolist(), q_final.tolist()

    def _warn(self, msg: str):
        if self.node is not None:
            try:
                self.node.get_logger().warning(str(msg))
                return
            except Exception:
                pass
        print(f"[ActionHandler][WARN] {msg}")

    def _info(self, msg: str):
        if self.node is not None:
            try:
                self.node.get_logger().info(str(msg))
                return
            except Exception:
                pass
        print(f"[ActionHandler][INFO] {msg}")