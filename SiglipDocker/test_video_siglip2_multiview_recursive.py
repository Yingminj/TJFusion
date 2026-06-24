"""
SigLIP2 多视角(Multi-View) 视频测试脚本 (递归扫描版)
=======================================================

基于 test_video_siglip2_jitter_recursive.py 改写,
训练架构参考 fine_tuning_siglip2_multiview.py。

核心变更:
  - 模型: MultiViewSigLIPModel (frozen SigLIP2 + CrossViewAttentionPooler)
  - 输入: 每帧为 2x2 grid 或 1x3 horizontal 的拼接图,
          使用 split_image_to_views 拆分为多视角后送入模型
  - 推理: model.encode_views(pixel_values) -> [1, D] 融合特征
  - 类中心: 优先从 graph_info.json 读取 center_feature_siglip2,
            缺失时从训练图片重新计算多视角中心
  - 保留原脚本的 EMA 平滑、稳定性/切换响应评价、递归扫描、汇总报告等功能
"""

import os
import sys
import argparse
import re
import json
import time

import torch
import numpy as np
from PIL import Image
import cv2

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE

# Add train directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'train'))

from transformers import AutoModel, AutoProcessor
from siglip2_trainer.multiview_models import (
    MultiViewSigLIPModel,
    CrossViewAttentionPooler,
    split_image_to_views,
)
from siglip2_trainer.augmentation import apply_background_mask


# =============================================================================
# 配置与命令行参数
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description='SigLIP2 Multi-View 视频帧分类测试 (递归扫描版)'
    )
    parser.add_argument('--video_dir', type=str,
                        default="/home/kewei/spatial_encoder/clip/data/test_data/gift_m8_multi_test10",
                        help='递归扫描该目录下所有子目录中的 mp4+标注配对')
    parser.add_argument('--save_dir', type=str,
                        default="/home/kewei/spatial_encoder/clip/data/test_result/gift_m8_multi_0624",
                        help='所有测试结果的保存根目录, 自动创建子目录(保留原始子目录结构)')
    parser.add_argument('--graph_info', type=str,
                        default="/home/kewei/spatial_encoder/clip/train/siglip2_output/gift_m8_multiview_0623/graph_info_best_eval.json",
                        help='graph_info.json 路径')
    parser.add_argument('--image_root', type=str,
                        default="/home/kewei/spatial_encoder/clip/data/train_data/gift_m8_picture_train40_multi",
                        help='训练图片根目录 (用于计算缺失的类中心)')
    parser.add_argument('--base_model', type=str,
                        default="/home/kewei/Data/CLIPNEW/models/siglip2-so400m-patch14-224",
                        help='SigLIP2 base model 路径')
    parser.add_argument('--model_checkpoint', type=str,
                        default="/home/kewei/spatial_encoder/clip/train/siglip2_output/gift_m8_multiview_0623/model_siglip2_multiview_v2_best_eval.pt",
                        help='MultiViewSigLIPModel checkpoint 路径 (为空则使用预训练 base)')
    parser.add_argument('--use_pretrained', action='store_true',
                        help='使用预训练 base model, 不加载训练好的 pooler 权重')

    # 多视角模型配置 (必须与训练时一致)
    parser.add_argument('--num_views', type=int, default=3,
                        help='视角数 (由 split_image_to_views 自动推断时此值仅作校验)')
    parser.add_argument('--num_query_tokens', type=int, default=8)
    parser.add_argument('--pooler_num_layers', type=int, default=2)
    parser.add_argument('--pooler_num_heads', type=int, default=8)

    # 背景 mask (与训练保持一致)
    parser.add_argument('--background_mask_ratio', type=float, default=0,
                        help='对拼接图顶部遮盖比例, 0=不启用')

    # EMA 平滑
    parser.add_argument('--no_sim_ema', action='store_true',
                        help='禁用相似度空间 EMA 平滑 (默认启用)')
    parser.add_argument('--ema_beta', type=float, default=0.7,
                        help='EMA 系数: 0=无平滑, 越大越平滑')

    # 其他
    parser.add_argument('--dim_reduction', type=str, default='pca', choices=['pca', 'tsne'],
                        help='特征空间降维方法 (仅用于可视化, 默认关闭实时显示)')
    parser.add_argument('--feature_key', type=str, default='center_feature_siglip2',
                        help='graph_info.json 中类中心特征字段名')
    return parser.parse_args()


args = parse_args()

# 全局常量
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {DEVICE}")

BASE_MODEL_PATH = args.base_model
CHECKPOINT_PATH = args.model_checkpoint
USE_PRETRAINED = args.use_pretrained

VIDEO_DIR = args.video_dir
SAVE_DIR = args.save_dir
os.makedirs(SAVE_DIR, exist_ok=True)

IMAGE_ROOT = args.image_root
GRAPH_INFO_PATH = args.graph_info
FEATURE_KEY = args.feature_key

BACKGROUND_MASK_RATIO = args.background_mask_ratio
USE_SIM_EMA = not args.no_sim_ema
EMA_BETA = args.ema_beta
DIMENSION_REDUCTION_METHOD = args.dim_reduction

# 轨迹/实时显示配置 (默认关闭窗口)
TRAJECTORY_COLOR = (255, 140, 0)
TRAJECTORY_MAX_LENGTH = 10000


# =============================================================================
# 模型加载
# =============================================================================

def load_model():
    """
    加载 SigLIP2 base model 与多视角 pooler。
    若提供 checkpoint 且非预训练模式, 则加载训练权重。
    """
    print("=" * 60)
    print("SigLIP2 Multi-View 模型加载")
    print("=" * 60)
    print(f"Base model: {BASE_MODEL_PATH}")

    base_model = AutoModel.from_pretrained(BASE_MODEL_PATH)
    processor = AutoProcessor.from_pretrained(BASE_MODEL_PATH)
    embed_dim = base_model.config.vision_config.hidden_size
    print(f"Vision embedding dim: {embed_dim}")

    # 构建 pooler (推理时 dropout=0)
    pooler = CrossViewAttentionPooler(
        embed_dim=embed_dim,
        num_queries=args.num_query_tokens,
        num_heads=args.pooler_num_heads,
        num_layers=args.pooler_num_layers,
        dropout=0.0,
    )

    model = MultiViewSigLIPModel(
        base_model, pooler,
        num_views=args.num_views,
        embed_dim=embed_dim,
    )

    if not USE_PRETRAINED and CHECKPOINT_PATH and os.path.exists(CHECKPOINT_PATH):
        print(f"加载训练权重: {CHECKPOINT_PATH}")
        checkpoint = torch.load(CHECKPOINT_PATH, map_location='cpu')
        model.load_state_dict(checkpoint['model_state_dict'])
        print("  ✓ 模型权重加载完成")
        if 'epoch' in checkpoint:
            print(f"  训练轮次: {checkpoint['epoch']}")
        if 'loss' in checkpoint:
            print(f"  训练损失: {checkpoint['loss']:.4f}")
        if 'eval_accuracy' in checkpoint:
            print(f"  验证准确率: {checkpoint['eval_accuracy']:.2%}")
    else:
        if USE_PRETRAINED:
            print("使用预训练 base model (pooler 随机初始化)")
        else:
            print(f"⚠ 未找到 checkpoint: {CHECKPOINT_PATH}, 使用预训练 base model")

    model = model.to(DEVICE)
    model.eval()
    print("=" * 60)
    return model, processor


# =============================================================================
# graph_info 加载与保存
# =============================================================================

def load_graph_info(graph_info_path, feature_key=FEATURE_KEY):
    """
    加载 graph_info.json, 返回 graph_data, category_descriptions, category_centers。
    category_centers 按 sorted node_id 顺序对应 category_descriptions。
    """
    if not os.path.exists(graph_info_path):
        print(f"❌ 错误: graph_info.json 不存在: {graph_info_path}")
        return None, None, None, False

    print(f"\n✓ 发现 graph_info.json: {graph_info_path}")
    print(f"  正在加载...")

    with open(graph_info_path, 'r', encoding='utf-8') as f:
        graph_data = json.load(f)

    nodes = graph_data.get('nodes', [])
    all_node_ids = sorted([node.get('node_id') for node in nodes if node.get('node_id')])

    category_descriptions = []
    for node_id in all_node_ids:
        node = next((n for n in nodes if n.get('node_id') == node_id), None)
        desc = node.get('state_description', '') if node else ''
        category_descriptions.append(desc)

    print(f"  节点数量: {len(nodes)}")
    print(f"  类别描述数量: {len(category_descriptions)}")
    print(f"  特征字段: {feature_key}")
    for i, desc in enumerate(category_descriptions):
        print(f"  Category {i+1} (node_id={all_node_ids[i]}): {desc}")

    category_centers = {}
    nodes_with_center = 0
    for node_id in all_node_ids:
        node = next((n for n in nodes if n.get('node_id') == node_id), None)
        if node is None:
            continue
        center_feature = node.get(feature_key)
        if center_feature is not None and center_feature != "":
            if isinstance(center_feature, str):
                center_feature = json.loads(center_feature)
            arr = np.array(center_feature, dtype=np.float32)
            norm = np.linalg.norm(arr)
            if norm > 0:
                arr = arr / norm
            category_centers[node_id] = arr
            nodes_with_center += 1

    print(f"\n  中心特征统计 ({feature_key}):")
    print(f"    已缓存: {nodes_with_center} 个节点")
    print(f"    未缓存: {len(nodes) - nodes_with_center} 个节点")

    return graph_data, category_descriptions, category_centers, True


def save_graph_info(graph_info_path, graph_data, feature_key=FEATURE_KEY):
    """保存更新后的 graph_info.json, center_feature 紧凑保存"""
    try:
        temp_data = json.loads(json.dumps(graph_data))
        for node in temp_data.get('nodes', []):
            if node.get(feature_key) is not None:
                node[feature_key] = json.dumps(node[feature_key], separators=(',', ':'))
        with open(graph_info_path, 'w', encoding='utf-8') as f:
            json.dump(temp_data, f, indent=2, ensure_ascii=False)
        print(f"✓ graph_info.json 已更新并保存: {graph_info_path}")
        return True
    except Exception as e:
        print(f"✗ 保存 graph_info.json 失败: {e}")
        return False


# =============================================================================
# 多视角类中心计算
# =============================================================================

def extract_category_number(name):
    match = re.search(r'\d+', name)
    return int(match.group()) if match else 0


def compute_multiview_class_centers(model, processor, image_root, category_descriptions):
    """
    从训练图片计算多视角类中心特征。
    每张图片先 split_image_to_views 拆分为多视角, 再 model.encode_views 融合。
    返回: dict {category_name: center_vector}
    """
    if not os.path.exists(image_root):
        print(f"❌ 错误: 图片根目录不存在: {image_root}")
        return {}

    categories = sorted(
        [d for d in os.listdir(image_root) if os.path.isdir(os.path.join(image_root, d))],
        key=extract_category_number
    )

    print(f"\n从训练数据计算多视角类中心: {len(categories)} 个类别")
    if len(categories) == 0:
        print("❌ 未找到类别文件夹")
        return {}

    if len(categories) != len(category_descriptions):
        print(f"⚠ 警告: 类别文件夹数 ({len(categories)}) 与类别描述数 ({len(category_descriptions)}) 不一致")

    category_centers = {}
    batch_size = 8

    with torch.no_grad():
        for idx, category in enumerate(categories):
            if idx >= len(category_descriptions):
                print(f"跳过类别 {category}: 没有对应类别描述")
                continue

            category_dir = os.path.join(image_root, category)
            images = sorted([
                os.path.join(category_dir, f)
                for f in os.listdir(category_dir)
                if f.lower().endswith(('.jpg', '.jpeg', '.png'))
            ])

            if len(images) == 0:
                print(f"警告: 类别 {category} 中没有图片")
                continue

            print(f"\n  正在计算类别 {category} 的中心特征 ({len(images)} 张图片)...")

            features_list = []
            for i in range(0, len(images), batch_size):
                batch_paths = images[i:i + batch_size]
                batch_views = []

                for img_path in batch_paths:
                    try:
                        with Image.open(img_path) as img:
                            img = img.convert('RGB')
                            img.load()

                        # 背景 mask 应用于整张拼接图
                        if BACKGROUND_MASK_RATIO > 0:
                            img = apply_background_mask(img, BACKGROUND_MASK_RATIO)

                        views = split_image_to_views(img)
                        batch_views.extend(views)
                    except Exception as e:
                        print(f"    警告: 无法加载图片 {img_path}: {e}")
                        continue

                if len(batch_views) == 0:
                    continue

                inputs = processor(images=batch_views, return_tensors="pt")
                pixel_values = inputs['pixel_values'].to(DEVICE)

                fused = model.encode_views(pixel_values)  # [B, D]
                features_list.append(fused.cpu().numpy())

                if (i // batch_size + 1) % 5 == 0:
                    print(f"    已处理 {min(i + batch_size, len(images))}/{len(images)} 张图片")

            if features_list:
                features = np.vstack(features_list)
                center = np.mean(features, axis=0)
                center = center / (np.linalg.norm(center) + 1e-12)
                category_centers[category] = center
                print(f"    ✓ {category} 中心特征计算完成 (dim: {center.shape})")

    return category_centers


# =============================================================================
# 通用辅助函数
# =============================================================================

def find_nearest_category(feature_vector, category_centers, category_descriptions):
    """找到最相似类别 (余弦相似度)"""
    max_similarity = -1.0
    nearest_category = None
    all_similarities = {}

    for idx, (node_id, center) in enumerate(category_centers.items()):
        description = category_descriptions[idx] if idx < len(category_descriptions) else node_id
        similarity = float(np.dot(feature_vector, center))
        all_similarities[description] = similarity
        if similarity > max_similarity:
            max_similarity = similarity
            nearest_category = description

    return nearest_category, max_similarity, all_similarities


def load_ground_truth_labels(label_path):
    """
    加载 Ground Truth 标注, 支持:
      - _lable.txt: 每行 "frame_idx category_idx" (category_idx 1-based)
      - _merged_segments.json: segments 列表, label 格式如 M1/M2/...
    返回: (gt_dict {frame_idx: category_idx_1based}, exists)
    """
    if not os.path.exists(label_path):
        print(f"⚠ 未找到 Ground Truth 标注文件: {label_path}")
        return None, False

    print(f"\n✓ 发现 Ground Truth 标注文件: {label_path}")
    gt_dict = {}

    try:
        if label_path.endswith('.json'):
            with open(label_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for seg in data.get('segments', []):
                label_str = seg.get('label', seg.get('category_id', ''))
                match = re.search(r'\d+', str(label_str))
                if match is None:
                    continue
                cat_idx = int(match.group())  # 1-based
                start_frame = int(seg['start_frame'])
                end_frame = int(seg['end_frame'])
                for fi in range(start_frame, end_frame + 1):
                    gt_dict[fi] = cat_idx
        else:
            with open(label_path, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        frame_seq = int(parts[0])
                        category_idx = int(parts[1])  # 1-based
                        gt_dict[frame_seq] = category_idx

        print(f"  加载了 {len(gt_dict)} 个标注帧")
        if gt_dict:
            seqs = sorted(gt_dict.keys())
            print(f"  帧范围: {seqs[0]} ~ {seqs[-1]}")
            print(f"  类别数量: {len(set(gt_dict.values()))} ({sorted(set(gt_dict.values()))})")
        return gt_dict, True

    except Exception as e:
        print(f"✗ 加载 Ground Truth 失败: {e}")
        return None, False


def save_prediction_results(timeline_data, save_path, fps, category_descriptions=None):
    """保存预测结果到文本文件 (1-based 索引)"""
    category_to_idx = {}
    if category_descriptions:
        for idx, cat in enumerate(category_descriptions):
            category_to_idx[cat] = idx + 1

    with open(save_path, 'w') as f:
        for timestamp, category in timeline_data:
            frame_idx = int(timestamp * fps)
            if category in category_to_idx:
                category_idx = category_to_idx[category]
            else:
                match = re.search(r'\d+', category)
                category_idx = int(match.group()) if match else 1
            f.write(f"{frame_idx} {category_idx}\n")

    print(f"✓ 预测结果已保存: {save_path}")


def calculate_accuracy(pred_dict, gt_dict, category_descriptions):
    """计算准确率和混淆矩阵 (1-based 索引)"""
    if gt_dict is None or len(gt_dict) == 0:
        return None, 0, 0, None

    correct_count = 0
    total_count = 0
    num_classes = len(category_descriptions) if category_descriptions else 10
    confusion_matrix = np.zeros((num_classes + 1, num_classes + 1), dtype=int)

    for frame_seq, gt_cat in gt_dict.items():
        if frame_seq in pred_dict:
            pred_cat = pred_dict[frame_seq]
            total_count += 1
            if pred_cat == gt_cat:
                correct_count += 1
            if 1 <= gt_cat <= num_classes and 1 <= pred_cat <= num_classes:
                confusion_matrix[gt_cat, pred_cat] += 1

    accuracy = (correct_count / total_count * 100) if total_count > 0 else 0
    return accuracy, correct_count, total_count, confusion_matrix


def print_accuracy_report(accuracy, correct_count, total_count, confusion_matrix, category_descriptions):
    """打印准确率报告"""
    print("\n" + "=" * 60)
    print("📊 准确率分析报告 (Multi-View)")
    print("=" * 60)
    print(f"\n总体准确率: {accuracy:.2f}%")
    print(f"正确预测: {correct_count}/{total_count} 帧")
    print(f"错误预测: {total_count - correct_count} 帧")

    if confusion_matrix is not None and category_descriptions:
        num_classes = len(category_descriptions)
        active_classes = []
        for i in range(1, num_classes + 1):
            row_sum = confusion_matrix[i, 1:num_classes + 1].sum()
            col_sum = confusion_matrix[1:num_classes + 1, i].sum()
            if row_sum > 0 or col_sum > 0:
                active_classes.append(i)

        print(f"\n混淆矩阵（共 {len(active_classes)} 个活跃类别）:")
        print("-" * 60)
        header = "真实\\预测"
        for cls_id in active_classes:
            header += f"{cls_id:>8}"
        print(header)
        print("-" * 60)
        for cls_id in active_classes:
            row = f"{cls_id:<10}"
            for pred_id in active_classes:
                row += f"{confusion_matrix[cls_id, pred_id]:>8}"
            print(row)

        print("\n类别ID对应表:")
        print("-" * 60)
        for cls_id in active_classes:
            desc = category_descriptions[cls_id - 1]
            print(f"  ID {cls_id}: {desc}")

        print("\n各类别准确率:")
        print("-" * 60)
        for cls_id in active_classes:
            desc = category_descriptions[cls_id - 1]
            total_in_class = confusion_matrix[cls_id, 1:num_classes + 1].sum()
            correct_in_class = confusion_matrix[cls_id, cls_id]
            if total_in_class > 0:
                class_acc = (correct_in_class / total_in_class * 100)
                print(f"  ID {cls_id}: {class_acc:.2f}% ({correct_in_class}/{total_in_class})  [{desc}]")
            else:
                print(f"  ID {cls_id}: N/A (无样本)  [{desc}]")
    print("=" * 60)


def save_accuracy_report(accuracy, correct_count, total_count, confusion_matrix,
                         category_descriptions, save_path):
    """保存准确率报告到文件"""
    with open(save_path, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("准确率分析报告 (SigLIP2 Multi-View)\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"总体准确率: {accuracy:.2f}%\n")
        f.write(f"正确预测: {correct_count}/{total_count} 帧\n")
        f.write(f"错误预测: {total_count - correct_count} 帧\n\n")

        if confusion_matrix is not None and category_descriptions:
            num_classes = len(category_descriptions)
            active_classes = []
            for i in range(1, num_classes + 1):
                row_sum = confusion_matrix[i, 1:num_classes + 1].sum()
                col_sum = confusion_matrix[1:num_classes + 1, i].sum()
                if row_sum > 0 or col_sum > 0:
                    active_classes.append(i)

            f.write(f"混淆矩阵（共 {len(active_classes)} 个活跃类别）:\n")
            f.write("-" * 60 + "\n")
            header = "真实\\预测"
            for cls_id in active_classes:
                header += f"{cls_id:>8}"
            f.write(header + "\n")
            f.write("-" * 60 + "\n")
            for cls_id in active_classes:
                row = f"{cls_id:<10}"
                for pred_id in active_classes:
                    row += f"{confusion_matrix[cls_id, pred_id]:>8}"
                f.write(row + "\n")

            f.write("\n类别ID对应表:\n")
            f.write("-" * 60 + "\n")
            for cls_id in active_classes:
                desc = category_descriptions[cls_id - 1]
                f.write(f"  ID {cls_id}: {desc}\n")

            f.write("\n各类别准确率:\n")
            f.write("-" * 60 + "\n")
            for cls_id in active_classes:
                desc = category_descriptions[cls_id - 1]
                total_in_class = confusion_matrix[cls_id, 1:num_classes + 1].sum()
                correct_in_class = confusion_matrix[cls_id, cls_id]
                if total_in_class > 0:
                    class_acc = (correct_in_class / total_in_class * 100)
                    f.write(f"  ID {cls_id}: {class_acc:.2f}% ({correct_in_class}/{total_in_class})  [{desc}]\n")
                else:
                    f.write(f"  ID {cls_id}: N/A (无样本)  [{desc}]\n")
        f.write("=" * 60 + "\n")
    print(f"✓ 准确率报告已保存: {save_path}")


def evaluate_stability(pred_dict, category_descriptions=None, label=""):
    """评价状态预测序列的稳定性"""
    if not pred_dict or len(pred_dict) < 2:
        return None

    sorted_seqs = sorted(pred_dict.keys())
    pred_seq = [pred_dict[s] for s in sorted_seqs]
    total_frames = len(pred_seq)

    transitions = sum(1 for i in range(1, total_frames) if pred_seq[i] != pred_seq[i - 1])
    transition_rate = transitions / (total_frames - 1)

    segments = []
    seg_start = 0
    for i in range(1, total_frames):
        if pred_seq[i] != pred_seq[seg_start]:
            segments.append(i - seg_start)
            seg_start = i
    segments.append(total_frames - seg_start)

    jitter_threshold = 3
    jitter_count = sum(1 for seg_len in segments if seg_len <= jitter_threshold)

    bounce_threshold = 10
    seg_info = []
    seg_start = 0
    for i in range(1, total_frames):
        if pred_seq[i] != pred_seq[seg_start]:
            seg_info.append((pred_seq[seg_start], i - seg_start))
            seg_start = i
    seg_info.append((pred_seq[seg_start], total_frames - seg_start))

    bounce_count = 0
    for i in range(2, len(seg_info)):
        cat_a, _ = seg_info[i - 2]
        cat_b, len_b = seg_info[i - 1]
        cat_c, _ = seg_info[i]
        if cat_a == cat_c and cat_a != cat_b and len_b <= bounce_threshold:
            bounce_count += 1

    stability_score = 1.0 - (jitter_count / len(segments)) if segments else 0.0

    result = {
        "total_frames": total_frames,
        "transitions": transitions,
        "transition_rate": transition_rate,
        "num_segments": len(segments),
        "jitter_threshold": jitter_threshold,
        "jitter_count": jitter_count,
        "bounce_threshold": bounce_threshold,
        "bounce_count": bounce_count,
        "stability_score": stability_score,
    }

    print(f"\n  [{label}] 状态稳定性指标:")
    print(f"    总帧数:           {total_frames}")
    print(f"    跳变次数:         {transitions} (跳变率: {transition_rate:.4f})")
    print(f"    连续段数:         {len(segments)}")
    print(f"    抖动段数(≤{jitter_threshold}帧): {jitter_count} / {len(segments)} 段")
    print(f"    反复横跳次数(A→B→A, B≤{bounce_threshold}帧): {bounce_count}")
    print(f"    稳定性得分:       {stability_score:.4f} (1.0=完全稳定, 0.0=全抖动)")

    return result


def save_stability_report(results_dict, category_descriptions, save_path):
    """将稳定性指标追加到报告文件"""
    with open(save_path, 'a', encoding='utf-8') as f:
        f.write("\n\n" + "=" * 60 + "\n")
        f.write("状态稳定性评价\n")
        f.write("=" * 60 + "\n")
        f.write("指标说明:\n")
        f.write("  跳变次数: 相邻帧预测类别不同的次数\n")
        f.write("  跳变率: 跳变次数 / (总帧数-1)，越低越稳定\n")
        f.write("  连续段数: 预测类别相同的连续帧段数，越低越稳定\n")
        f.write("  抖动段数: 连续停留≤3帧的段数，直接反映短暂误判\n")
        f.write("  反复横跳(A->B->A): 跳到B后在10帧内跳回A的次数\n")
        f.write("  稳定性得分: 1 - 抖动段占比，范围[0,1]，越高越稳定\n\n")

        for label, r in results_dict.items():
            if r is None:
                continue
            f.write(f"[{label}]\n")
            f.write(f"  总帧数:           {r['total_frames']}\n")
            f.write(f"  跳变次数:         {r['transitions']} (跳变率: {r['transition_rate']:.4f})\n")
            f.write(f"  连续段数:         {r['num_segments']}\n")
            f.write(f"  抖动段数(≤{r['jitter_threshold']}帧): {r['jitter_count']} / {r['num_segments']} 段\n")
            f.write(f"  反复横跳(A->B->A, B≤{r['bounce_threshold']}帧): {r['bounce_count']}\n")
            f.write(f"  稳定性得分:       {r['stability_score']:.4f}\n\n")
        f.write("=" * 60 + "\n")
    print(f"✓ 稳定性报告已追加到: {save_path}")


def evaluate_transition_response(pred_dict, gt_dict, category_descriptions=None,
                                 response_window=10, hold_window=5, label=""):
    """评价在 GT 状态切换点处预测序列的切换响应准确性"""
    if not pred_dict or not gt_dict:
        return None

    gt_sorted_seqs = sorted(gt_dict.keys())
    gt_transitions = []
    for i in range(1, len(gt_sorted_seqs)):
        prev_seq = gt_sorted_seqs[i - 1]
        curr_seq = gt_sorted_seqs[i]
        if gt_dict[prev_seq] != gt_dict[curr_seq]:
            gt_transitions.append((curr_seq, gt_dict[prev_seq], gt_dict[curr_seq]))

    if not gt_transitions:
        print(f"\n  [{label}] GT 无状态切换，跳过切换响应评价")
        return None

    total_switches = len(gt_transitions)
    responded = 0
    held = 0
    response_delays = []
    details = []

    max_pred_seq = max(pred_dict.keys()) if pred_dict else 0

    for t_idx, (switch_seq, old_cat, new_cat) in enumerate(gt_transitions):
        if t_idx + 1 < len(gt_transitions):
            search_limit = gt_transitions[t_idx + 1][0]
        else:
            search_limit = max_pred_seq + 1

        found_response = False
        response_delay = None
        actual_delay = None
        first_correct_seq = None

        # 向前搜索
        for offset in range(-response_window, 0):
            check_seq = switch_seq + offset
            if check_seq in pred_dict and pred_dict[check_seq] == new_cat:
                actual_delay = offset
                first_correct_seq = check_seq
                break

        # 向后搜索
        if actual_delay is None:
            for offset in range(0, search_limit - switch_seq):
                check_seq = switch_seq + offset
                if check_seq in pred_dict and pred_dict[check_seq] == new_cat:
                    actual_delay = offset
                    first_correct_seq = check_seq
                    break

        if actual_delay is not None and abs(actual_delay) <= response_window:
            found_response = True
            response_delay = actual_delay

        if found_response:
            responded += 1
            response_delays.append(response_delay)
            hold_ok = True
            for h in range(hold_window):
                h_seq = first_correct_seq + h
                if h_seq in pred_dict and pred_dict[h_seq] != new_cat:
                    hold_ok = False
                    break
            if hold_ok:
                held += 1
        else:
            hold_ok = False

        details.append({
            "switch_seq": switch_seq,
            "old_cat": old_cat,
            "new_cat": new_cat,
            "responded": found_response,
            "delay": response_delay,
            "actual_delay": actual_delay,
            "held": found_response and hold_ok,
        })

    response_rate = responded / total_switches * 100 if total_switches > 0 else 0
    hold_rate = held / total_switches * 100 if total_switches > 0 else 0
    avg_delay = np.mean(response_delays) if response_delays else float('nan')

    result = {
        "total_switches": total_switches,
        "responded": responded,
        "response_rate": response_rate,
        "held": held,
        "hold_rate": hold_rate,
        "avg_delay": avg_delay,
        "response_window": response_window,
        "hold_window": hold_window,
        "details": details,
    }

    print(f"\n  [{label}] 状态切换响应指标 (response±{response_window}帧, hold≥{hold_window}帧):")
    print(f"    GT 切换次数:      {total_switches}")
    print(f"    及时响应次数:     {responded}/{total_switches} ({response_rate:.1f}%)")
    print(f"    响应并保持次数:   {held}/{total_switches} ({hold_rate:.1f}%)")
    if response_delays:
        if avg_delay > 0:
            print(f"    平均响应延迟:     {avg_delay:.1f} 帧")
        elif avg_delay < 0:
            print(f"    平均响应提前:     {abs(avg_delay):.1f} 帧")
        else:
            print(f"    平均响应延迟:     0.0 帧")

    return result


def save_transition_report(results_dict, save_path):
    """将切换响应指标追加到报告文件"""
    with open(save_path, 'a', encoding='utf-8') as f:
        f.write("\n\n" + "=" * 60 + "\n")
        f.write("状态切换响应评价\n")
        f.write("=" * 60 + "\n")
        f.write("指标说明:\n")
        f.write("  及时响应: GT切换前后，预测在response_window帧内切换到正确新状态\n")
        f.write("  响应并保持: 及时响应后，在hold_window帧内持续保持正确状态不跳回\n")
        f.write("  平均响应延迟: 成功响应时，从GT切换到预测首次正确的平均帧数\n\n")

        for label, r in results_dict.items():
            if r is None:
                continue
            f.write(f"[{label}] (response±{r['response_window']}帧, hold≥{r['hold_window']}帧)\n")
            f.write(f"  GT 切换次数:      {r['total_switches']}\n")
            f.write(f"  及时响应:         {r['responded']}/{r['total_switches']} ({r['response_rate']:.1f}%)\n")
            f.write(f"  响应并保持:       {r['held']}/{r['total_switches']} ({r['hold_rate']:.1f}%)\n")
            if not np.isnan(r['avg_delay']):
                if r['avg_delay'] > 0:
                    f.write(f"  平均响应延迟:     {r['avg_delay']:.1f} 帧\n")
                elif r['avg_delay'] < 0:
                    f.write(f"  平均响应提前:     {abs(r['avg_delay']):.1f} 帧\n")
                else:
                    f.write(f"  平均响应延迟:     0.0 帧\n")

            f.write(f"\n  切换点明细:\n")
            for d in r['details']:
                if d['held']:
                    status = "OK"
                    if d['delay'] > 0:
                        delay_str = f"延迟{d['delay']}帧"
                    elif d['delay'] < 0:
                        delay_str = f"提前{abs(d['delay'])}帧"
                    else:
                        delay_str = "立即响应"
                elif d['responded']:
                    status = "响应但未保持"
                    if d['delay'] > 0:
                        delay_str = f"延迟{d['delay']}帧"
                    elif d['delay'] < 0:
                        delay_str = f"提前{abs(d['delay'])}帧"
                    else:
                        delay_str = "立即响应"
                else:
                    status = "未及时响应"
                    if d.get('actual_delay') is not None:
                        if d['actual_delay'] > 0:
                            delay_str = f"实际延迟{d['actual_delay']}帧"
                        elif d['actual_delay'] < 0:
                            delay_str = f"实际提前{abs(d['actual_delay'])}帧"
                        else:
                            delay_str = "实际立即响应"
                    else:
                        delay_str = "始终未切换到目标状态"
                f.write(f"    帧{d['switch_seq']}: C{d['old_cat']}->C{d['new_cat']}  {status}  {delay_str}\n")
            f.write("\n")
        f.write("=" * 60 + "\n")
    print(f"✓ 切换响应报告已追加到: {save_path}")


# =============================================================================
# 可视化辅助函数
# =============================================================================

def matplotlib_to_cv2(fig):
    """将 matplotlib 图形转换为 OpenCV 格式"""
    canvas = fig.canvas
    canvas.draw()
    buf = np.asarray(canvas.buffer_rgba())
    img = buf[:, :, :3].copy()
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


def create_feature_space_plot(features, category_centers, current_feature_vector=None,
                             current_category=None, method="pca", reducer=None,
                             current_similarity=None, trajectory_points=None):
    """创建特征空间可视化图 (类别中心 + 当前帧 + 轨迹)"""
    fig, ax = plt.subplots(figsize=(8, 8), dpi=100)

    if len(category_centers) == 0:
        ax.text(0.5, 0.5, 'No category centers available',
                ha='center', va='center', fontsize=14, transform=ax.transAxes)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        return fig, None, None, None

    all_features = np.vstack(list(category_centers.values()))

    if method.lower() == "tsne":
        if reducer is None:
            reducer = TSNE(n_components=2, perplexity=min(30, len(all_features) - 1),
                           n_iter=1000, random_state=42, verbose=0)
    else:
        if reducer is None:
            reducer = PCA(n_components=2)

    if not hasattr(reducer, 'components_'):
        features_2d = reducer.fit_transform(all_features)
    else:
        features_2d = reducer.transform(all_features)

    centers_2d = features_2d
    categories_sorted = list(category_centers.keys())

    # 绘制类别顺序箭头
    for i in range(len(categories_sorted) - 1):
        x1, y1 = centers_2d[i]
        x2, y2 = centers_2d[i + 1]
        arrow = FancyArrowPatch(
            (x1, y1), (x2, y2),
            arrowstyle='->,head_width=0.4,head_length=0.8',
            linestyle='--', linewidth=2, color='dodgerblue', alpha=0.6,
            zorder=1.5, mutation_scale=20
        )
        ax.add_patch(arrow)

    if len(categories_sorted) > 1:
        ax.text(0.02, 0.02, "Blue arrows: Category sequence",
                transform=ax.transAxes, fontsize=9, color='dodgerblue', weight='bold',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                          edgecolor='dodgerblue', alpha=0.8))

    for i, category in enumerate(categories_sorted):
        x, y = centers_2d[i]
        color = 'green' if category == current_category else 'blue'
        size = 600 if category == current_category else 400
        alpha = 1.0 if category == current_category else 0.8

        ax.scatter(x, y, c=color, s=size, marker='o',
                   edgecolors='darkblue' if color == 'blue' else 'darkgreen',
                   linewidths=3, alpha=alpha, zorder=2)
        ax.annotate(category, (x, y), fontsize=11, ha='center', va='center',
                    color='white', weight='bold',
                    bbox=dict(boxstyle='round,pad=0.5', facecolor=color,
                              edgecolors='darkblue' if color == 'blue' else 'darkgreen',
                              alpha=alpha), zorder=3)

    if trajectory_points is not None and len(trajectory_points) > 1:
        trajectory_array = np.array(trajectory_points)
        for i in range(len(trajectory_array) - 1):
            alpha_value = 0.3 + 0.7 * (i / len(trajectory_array))
            ax.plot(trajectory_array[i:i + 2, 0], trajectory_array[i:i + 2, 1],
                    color='darkorange', linewidth=2.5, alpha=alpha_value, zorder=2.5)
        ax.scatter(trajectory_array[:-1, 0], trajectory_array[:-1, 1],
                   c='orange', s=20, alpha=0.5, zorder=2.6, edgecolors='darkorange')

    current_point = None
    if current_feature_vector is not None:
        if reducer is not None and hasattr(reducer, 'components_'):
            current_point = reducer.transform(current_feature_vector.reshape(1, -1))[0]
        else:
            current_full = np.vstack([all_features, current_feature_vector])
            if method.lower() == "tsne":
                new_reducer = TSNE(n_components=2, perplexity=min(30, len(current_full) - 1),
                                   n_iter=1000, random_state=42, verbose=0)
            else:
                new_reducer = PCA(n_components=2)
            current_2d_full = new_reducer.fit_transform(current_full)
            current_point = current_2d_full[-1]

        ax.scatter(current_point[0], current_point[1], c='red', s=600, marker='*',
                   edgecolors='darkred', linewidths=3, alpha=1.0, zorder=4, label='Current Frame')
        ax.annotate("CURRENT", (current_point[0], current_point[1]),
                    fontsize=11, ha='center', va='bottom', color='white', weight='bold',
                    zorder=5, bbox=dict(boxstyle='round,pad=0.4', facecolor='red',
                                        edgecolor='darkred', alpha=0.9, linewidth=2))

    ax.set_xlabel(f'{method.upper()} Dimension 1', fontsize=11)
    ax.set_ylabel(f'{method.upper()} Dimension 2', fontsize=11)
    ax.set_title('SigLIP2 Multi-View Feature Space Visualization', fontsize=13, fontweight='bold')

    if current_category is not None:
        info_text = f"Current Frame\nCategory: {current_category}"
        if current_similarity is not None:
            info_text += f"\nSimilarity: {current_similarity:.4f}"
        if trajectory_points is not None:
            info_text += f"\nTrajectory Points: {len(trajectory_points)}"
        ax.text(0.98, 0.98, info_text, transform=ax.transAxes, fontsize=12,
                verticalalignment='top', horizontalalignment='right',
                bbox=dict(boxstyle='round,pad=0.7', facecolor='lightyellow',
                          edgecolor='orange', alpha=0.9, linewidth=2),
                weight='bold')

    ax.legend(fontsize=9, loc='lower left')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    return fig, ax, reducer, current_point


def save_timeline_plot(timestamps, categories, category_descriptions, save_path,
                       video_name, gt_data=None):
    """保存时间-类别折线图 (1-based 索引)"""
    unique_categories = category_descriptions if category_descriptions else sorted(list(set(categories)))
    category_to_idx = {cat: idx + 1 for idx, cat in enumerate(unique_categories)}
    category_indices = [category_to_idx.get(c, 1) for c in categories]

    fig, ax = plt.subplots(figsize=(14, 8), dpi=150)

    if gt_data is not None and len(gt_data) > 0:
        gt_timestamps = [t for t, _ in gt_data]
        gt_category_indices = [cat_idx for _, cat_idx in gt_data]
        ax.step(gt_timestamps, gt_category_indices, where='post',
                linewidth=1, color='limegreen', alpha=0.7, label='Ground Truth')

    ax.step(timestamps, category_indices, where='post',
            linewidth=1, color="#E2510DDD", alpha=0.8, label='Prediction')

    y_ticks = list(range(1, len(unique_categories) + 1))
    ax.set_yticks(y_ticks)
    ax.set_yticklabels(unique_categories, fontsize=10)
    ax.set_xlabel('Time (seconds)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Predicted Category', fontsize=12, fontweight='bold')
    ax.set_title(f'SigLIP2 Multi-View Timeline: {video_name}', fontsize=14, fontweight='bold', pad=20)

    ax.grid(True, alpha=0.3, linestyle='--', axis='y')
    ax.grid(True, alpha=0.3, linestyle='--', axis='x')
    ax.set_xlim(0, max(timestamps) * 1.05 if timestamps else 1)
    ax.set_ylim(0.5, len(unique_categories) + 0.5)

    for i in range(1, len(unique_categories) + 1):
        if i % 2 == 0:
            ax.axhspan(i - 0.5, i + 0.5, alpha=0.1, color='gray')

    total_frames = len(categories)
    duration = timestamps[-1] if timestamps else 0
    info_text = f"Total Frames: {total_frames}\nDuration: {duration:.2f}s\nCategories: {len(unique_categories)}"
    ax.text(0.02, 0.98, info_text, transform=ax.transAxes, fontsize=10,
            verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    ax.legend(loc='upper right', fontsize=10)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"\n✓ 时间轴折线图已保存: {save_path}")


def save_classification_detail_plot(samples, category_descriptions, save_path, video_name):
    """可视化采样帧的分类详情: 左侧图像 + 右侧相似度柱状图"""
    if not samples:
        return

    num_samples = len(samples)
    fig, axes = plt.subplots(num_samples, 2, figsize=(16, num_samples * 2.5))
    if num_samples == 1:
        axes = axes.reshape(1, -1)

    for idx, sample in enumerate(samples):
        ax_img = axes[idx, 0]
        ax_img.imshow(sample['image'])
        ax_img.axis('off')

        true_cls = sample.get('true_class')
        pred_cls = sample['pred_class']
        frame_idx = sample['frame_idx']

        if true_cls is not None:
            correct = (true_cls == pred_cls)
            status = "OK" if correct else "X"
            color = "green" if correct else "red"
            title = f"Frame {frame_idx} | {status} True: {true_cls} | Pred: {pred_cls}"
        else:
            color = "blue"
            title = f"Frame {frame_idx} | Pred: {pred_cls}"
        ax_img.set_title(title, fontsize=9, fontweight='bold', color=color)

        ax_bar = axes[idx, 1]
        sims = sample['similarities']
        classes_sorted = [c for c in category_descriptions if c in sims]
        classes_display = list(reversed(classes_sorted))
        values_display = [sims[c] for c in classes_display]

        colors = []
        for cls in classes_display:
            if true_cls is not None and cls == true_cls and cls == pred_cls:
                colors.append('green')
            elif true_cls is not None and cls == true_cls:
                colors.append('green')
            elif cls == pred_cls and (true_cls is None or pred_cls != true_cls):
                colors.append('red')
            else:
                colors.append('lightgray')

        ax_bar.barh(range(len(classes_display)), values_display,
                    color=colors, alpha=0.7, edgecolor='black', linewidth=0.5)
        for i, (cls, val) in enumerate(zip(classes_display, values_display)):
            ax_bar.text(val + 0.005, i, f'{val:.3f}', va='center', fontsize=7)

        short_labels = [c[:50] + '...' if len(c) > 50 else c for c in classes_display]
        ax_bar.set_yticks(range(len(classes_display)))
        ax_bar.set_yticklabels(short_labels, fontsize=7)
        ax_bar.set_xlabel('Cosine Similarity', fontsize=8)
        ax_bar.set_xlim(-0.2, 1.0)
        ax_bar.grid(True, alpha=0.3, axis='x')

    plt.suptitle(f'Multi-View Classification Details - {video_name}',
                 fontsize=13, fontweight='bold', y=1.0)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  分类详情图已保存: {save_path}")


# =============================================================================
# 多视角帧编码
# =============================================================================

def encode_multiview_frame(model, processor, pil_image):
    """
    将一帧拼接图编码为多视角融合特征。

    Args:
        pil_image: PIL Image (2x2 grid 或 1x3 horizontal)
    Returns:
        feature: numpy array [D]
    """
    views = split_image_to_views(pil_image)

    # 校验视角数 (仅警告, split_image_to_views 根据宽高比自动推断)
    if len(views) != args.num_views:
        print(f"⚠ 警告: 当前帧拆分为 {len(views)} 个视角, 与 --num_views={args.num_views} 不一致")

    inputs = processor(images=views, return_tensors="pt")
    pixel_values = inputs['pixel_values'].to(DEVICE)  # [V, C, H, W]

    with torch.no_grad():
        fused = model.encode_views(pixel_values)  # [1, D]

    return fused[0].cpu().numpy().astype(np.float32)


# =============================================================================
# 视频扫描与处理
# =============================================================================

def find_video_label_pairs(video_dir):
    """
    递归扫描 video_dir, 找出所有 .mp4 与对应标注文件的配对。
    优先匹配 {stem}_merged_segments.json, 其次 {stem}_lable.txt。
    返回: list of (video_path, label_path, rel_subdir)
    """
    pairs = []
    for dirpath, dirnames, filenames in os.walk(video_dir):
        dirnames.sort()
        rel_subdir = os.path.relpath(dirpath, video_dir)
        for fname in sorted(filenames):
            if not fname.lower().endswith('.mp4'):
                continue
            stem = os.path.splitext(fname)[0]
            json_label = os.path.join(dirpath, stem + '_merged_segments.json')
            txt_label = os.path.join(dirpath, stem + '_lable.txt')
            if os.path.exists(json_label):
                pairs.append((os.path.join(dirpath, fname), json_label, rel_subdir))
            elif os.path.exists(txt_label):
                pairs.append((os.path.join(dirpath, fname), txt_label, rel_subdir))
            else:
                print(f"  警告: 未找到 {fname} 对应的标注文件, 跳过")
    return pairs


def run_video_mode(model, processor, video_dir, category_descriptions, category_centers, save_dir):
    """
    多视角视频模式主循环:
    遍历 video_dir 下所有 mp4+标注配对, 每帧拆分为多视角后推理, 保存每个视频的分析结果。
    """
    category_to_idx = {cat: idx + 1 for idx, cat in enumerate(category_descriptions)}

    video_pairs = find_video_label_pairs(video_dir)
    print(f"\n发现 {len(video_pairs)} 个视频-标注配对:")
    for vp, lp, rel in video_pairs:
        print(f"  [{rel}] {os.path.basename(vp)}  ->  {os.path.basename(lp)}")

    summary_records = []

    for video_path, label_path, rel_subdir in video_pairs:
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        if rel_subdir == '.':
            video_out_dir = os.path.join(save_dir, video_name)
        else:
            video_out_dir = os.path.join(save_dir, rel_subdir, video_name)
        os.makedirs(video_out_dir, exist_ok=True)

        print(f"\n{'=' * 60}")
        print(f"处理视频: {video_name}")
        print(f"{'=' * 60}")

        gt_dict, gt_exists = load_ground_truth_labels(label_path)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"  错误: 无法打开视频 {video_path}, 跳过")
            continue

        video_fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if video_fps <= 0:
            video_fps = 30.0
        print(f"  视频信息: {total_frames} 帧, {video_fps:.1f} FPS")

        gt_data = []
        if gt_exists:
            for seq in sorted(gt_dict.keys()):
                gt_data.append((seq / video_fps, gt_dict[seq]))

        timeline_data = []
        similarity_history = []
        pred_dict = {}
        inference_times = []
        frame_idx = 0
        ema_sim = None
        classification_samples = []

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            timestamp = frame_idx / video_fps
            img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)

            # 背景 mask 在拆分前应用于整张拼接图
            if BACKGROUND_MASK_RATIO > 0:
                pil_img = apply_background_mask(pil_img, BACKGROUND_MASK_RATIO)

            inference_start = time.time()
            frame_feature = encode_multiview_frame(model, processor, pil_img)
            if DEVICE == "cuda":
                torch.cuda.synchronize()
            inference_times.append((time.time() - inference_start) * 1000)

            frame_feature_np = frame_feature.squeeze()
            nearest_category, max_similarity, all_similarities = find_nearest_category(
                frame_feature_np, category_centers, category_descriptions
            )

            if USE_SIM_EMA:
                sim_keys = list(all_similarities.keys())
                sim_vals = np.array([all_similarities[k] for k in sim_keys], dtype=np.float32)
                if ema_sim is None:
                    ema_sim = sim_vals.copy()
                else:
                    ema_sim = EMA_BETA * ema_sim + (1 - EMA_BETA) * sim_vals
                best_idx = int(np.argmax(ema_sim))
                nearest_category = sim_keys[best_idx]
                max_similarity = float(ema_sim[best_idx])
                all_similarities = {k: float(ema_sim[i]) for i, k in enumerate(sim_keys)}

            timeline_data.append((timestamp, nearest_category))
            similarity_history.append((timestamp, all_similarities.copy()))

            if nearest_category in category_to_idx:
                pred_dict[frame_idx] = category_to_idx[nearest_category]

            # 采样分类错误的帧用于详情图
            sample_interval = max(1, total_frames // 30)
            if frame_idx % sample_interval == 0 and gt_exists and frame_idx in gt_dict:
                gt_idx = gt_dict[frame_idx]
                gt_class_name = None
                if 1 <= gt_idx <= len(category_descriptions):
                    gt_class_name = category_descriptions[gt_idx - 1]
                if gt_class_name is not None and gt_class_name != nearest_category:
                    classification_samples.append({
                        'image': img_rgb,
                        'frame_idx': frame_idx,
                        'true_class': gt_class_name,
                        'pred_class': nearest_category,
                        'similarities': all_similarities.copy(),
                    })

            if (frame_idx + 1) % 50 == 0:
                avg_inf = np.mean(inference_times[-10:])
                print(f"  Frame {frame_idx + 1}/{total_frames}: {nearest_category} "
                      f"(sim={max_similarity:.4f}, inf={avg_inf:.2f}ms)")

            frame_idx += 1

        cap.release()
        frame_count = frame_idx
        print(f"  视频读取完成，共处理 {frame_count} 帧")

        # ---------- 保存该视频结果 ----------
        pred_save_path = os.path.join(video_out_dir, f"{video_name}_prediction_siglip2_multiview.txt")
        save_prediction_results(timeline_data, pred_save_path, video_fps, category_descriptions)

        report_path = os.path.join(video_out_dir, f"{video_name}_accuracy_report_siglip2_multiview.txt")
        if gt_exists:
            accuracy, correct_count, total_count, confusion_matrix = calculate_accuracy(
                pred_dict, gt_dict, category_descriptions
            )
            if accuracy is not None:
                print_accuracy_report(accuracy, correct_count, total_count,
                                      confusion_matrix, category_descriptions)
                save_accuracy_report(accuracy, correct_count, total_count,
                                     confusion_matrix, category_descriptions, report_path)

        if timeline_data:
            timestamps_v = [t for t, _ in timeline_data]
            categories_v = [c for _, c in timeline_data]
            save_timeline_plot(
                timestamps=timestamps_v, categories=categories_v,
                category_descriptions=category_descriptions,
                save_path=os.path.join(video_out_dir, f"{video_name}_timeline_siglip2_multiview.png"),
                video_name=video_name, gt_data=gt_data
            )

        if classification_samples:
            detail_path = os.path.join(video_out_dir, f"{video_name}_classification_detail_multiview.png")
            save_classification_detail_plot(
                classification_samples, category_descriptions, detail_path, video_name)

        stability_results = {}
        if pred_dict:
            stability_results["离线推理"] = evaluate_stability(
                pred_dict, category_descriptions, label="离线推理")
        if gt_exists and gt_dict:
            stability_results["Ground Truth"] = evaluate_stability(
                gt_dict, category_descriptions, label="Ground Truth")
        if stability_results:
            save_stability_report(stability_results, category_descriptions, report_path)

        transition_result_offline = None
        if gt_exists and gt_dict and pred_dict:
            transition_results = {
                "离线推理": evaluate_transition_response(
                    pred_dict, gt_dict, category_descriptions, label="离线推理")
            }
            save_transition_report(transition_results, report_path)
            transition_result_offline = transition_results["离线推理"]

        avg_t = None
        if inference_times:
            avg_t = np.mean(inference_times)
            print(f"\n  推理效率: 平均 {avg_t:.2f}ms/帧 ({1000 / avg_t:.1f} FPS)")

        rec = {
            "subdir": rel_subdir,
            "video": video_name,
            "frames": frame_count,
            "gt_exists": gt_exists,
            "accuracy": None,
            "correct": None,
            "total": None,
            "stability": None,
            "trans_resp": None,
            "trans_hold": None,
            "avg_inf_ms": avg_t,
        }
        if gt_exists and pred_dict:
            accuracy, correct_count, total_count, _ = calculate_accuracy(
                pred_dict, gt_dict, category_descriptions)
            rec["accuracy"] = accuracy
            rec["correct"] = correct_count
            rec["total"] = total_count
        stab = stability_results.get("离线推理")
        if stab:
            rec["stability"] = stab["stability_score"]
        if transition_result_offline:
            rec["trans_resp"] = transition_result_offline["response_rate"]
            rec["trans_hold"] = transition_result_offline["hold_rate"]
        summary_records.append(rec)

    # ==================== 汇总报告 ====================
    summary_path = os.path.join(save_dir, "summary_report_siglip2_multiview.txt")
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("SigLIP2 Multi-View 批量测试汇总报告\n")
        f.write(f"视频根目录: {video_dir}\n")
        f.write(f"测试视频数: {len(summary_records)}\n")
        f.write("=" * 80 + "\n\n")

        f.write(f"{'子目录':<25} {'视频名':<20} {'帧数':>6}  {'准确率':>8}  {'正确/总帧':>12}  "
                f"{'稳定性':>8}  {'响应率':>8}  {'保持率':>8}  {'推理ms':>8}\n")
        f.write("-" * 110 + "\n")

        acc_list, stab_list, resp_list, hold_list = [], [], [], []
        for r in summary_records:
            acc_str = f"{r['accuracy']:.2f}%" if r['accuracy'] is not None else "N/A"
            frac_str = f"{r['correct']}/{r['total']}" if r['correct'] is not None else "N/A"
            stab_str = f"{r['stability']:.4f}" if r['stability'] is not None else "N/A"
            resp_str = f"{r['trans_resp']:.1f}%" if r['trans_resp'] is not None else "N/A"
            hold_str = f"{r['trans_hold']:.1f}%" if r['trans_hold'] is not None else "N/A"
            inf_str = f"{r['avg_inf_ms']:.2f}" if r['avg_inf_ms'] is not None else "N/A"

            f.write(f"{r['subdir']:<25} {r['video']:<20} {r['frames']:>6}  "
                    f"{acc_str:>8}  {frac_str:>12}  {stab_str:>8}  "
                    f"{resp_str:>8}  {hold_str:>8}  {inf_str:>8}\n")

            if r['accuracy'] is not None: acc_list.append(r['accuracy'])
            if r['stability'] is not None: stab_list.append(r['stability'])
            if r['trans_resp'] is not None: resp_list.append(r['trans_resp'])
            if r['trans_hold'] is not None: hold_list.append(r['trans_hold'])

        f.write("-" * 110 + "\n")

        subdirs = sorted(set(r['subdir'] for r in summary_records))
        if len(subdirs) > 1:
            f.write("\n按子目录汇总:\n")
            f.write("-" * 60 + "\n")
            for sd in subdirs:
                recs = [r for r in summary_records if r['subdir'] == sd]
                sd_acc = [r['accuracy'] for r in recs if r['accuracy'] is not None]
                sd_stab = [r['stability'] for r in recs if r['stability'] is not None]
                sd_resp = [r['trans_resp'] for r in recs if r['trans_resp'] is not None]
                sd_hold = [r['trans_hold'] for r in recs if r['trans_hold'] is not None]
                f.write(f"  [{sd}]  {len(recs)} 个视频\n")
                if sd_acc:
                    f.write(f"    平均准确率:   {np.mean(sd_acc):.2f}%\n")
                if sd_stab:
                    f.write(f"    平均稳定性:   {np.mean(sd_stab):.4f}\n")
                if sd_resp:
                    f.write(f"    平均响应率:   {np.mean(sd_resp):.1f}%\n")
                if sd_hold:
                    f.write(f"    平均保持率:   {np.mean(sd_hold):.1f}%\n")
            f.write("\n")

        f.write("整体平均:\n")
        f.write("-" * 60 + "\n")
        if acc_list:
            f.write(f"  平均准确率:   {np.mean(acc_list):.2f}%  "
                    f"(min={min(acc_list):.2f}%, max={max(acc_list):.2f}%)\n")
        if stab_list:
            f.write(f"  平均稳定性:   {np.mean(stab_list):.4f}  "
                    f"(min={min(stab_list):.4f}, max={max(stab_list):.4f})\n")
        if resp_list:
            f.write(f"  平均响应率:   {np.mean(resp_list):.1f}%\n")
        if hold_list:
            f.write(f"  平均保持率:   {np.mean(hold_list):.1f}%\n")
        f.write("=" * 80 + "\n")

    print(f"\n汇总报告已保存: {summary_path}")
    print(f"\n所有视频处理完成！结果保存在: {save_dir}")


# =============================================================================
# 主函数
# =============================================================================

def main():
    print("=" * 60)
    print("SigLIP2 Multi-View 视频测试 (递归扫描版)")
    print("=" * 60)

    # 1. 加载模型
    model, processor = load_model()

    # 2. 加载 graph_info.json
    print("\n步骤 1: 加载 graph_info.json")
    graph_data, category_descriptions, category_centers, graph_loaded = load_graph_info(
        GRAPH_INFO_PATH, feature_key=FEATURE_KEY)

    if not graph_loaded:
        return

    # 3. 检查是否有未缓存的类中心
    nodes_without_center = []
    for node in graph_data.get('nodes', []):
        center_feature = node.get(FEATURE_KEY)
        if center_feature is None or center_feature == "":
            nodes_without_center.append(node.get('node_id'))

    if len(nodes_without_center) > 0:
        print(f"\n步骤 2: 发现 {len(nodes_without_center)} 个节点的 {FEATURE_KEY} 未缓存")
        print(f"  需要计算的节点: {nodes_without_center}")
        print("\n步骤 3: 从训练图片计算多视角类中心")

        computed_centers = compute_multiview_class_centers(
            model, processor, IMAGE_ROOT, category_descriptions)

        # 将计算的中心特征更新到 graph_data 中
        for idx, node in enumerate(graph_data.get('nodes', [])):
            category_num = idx + 1
            for fmt in [f"category{category_num}", f"category_{category_num}"]:
                if fmt in computed_centers:
                    node[FEATURE_KEY] = computed_centers[fmt].tolist()
                    print(f"  ✓ 节点 {node.get('node_id')}: {FEATURE_KEY} 已更新")
                    break

        print("\n步骤 4: 保存更新后的 graph_info.json")
        save_success = save_graph_info(GRAPH_INFO_PATH, graph_data, feature_key=FEATURE_KEY)

        if save_success:
            _, category_descriptions, category_centers, _ = load_graph_info(
                GRAPH_INFO_PATH, feature_key=FEATURE_KEY)
        else:
            print("✗ 保存失败，使用临时计算的特征")
            category_centers = {}
            for idx, node in enumerate(graph_data.get('nodes', [])):
                node_id = node.get('node_id')
                center_feature = node.get(FEATURE_KEY)
                if center_feature is not None:
                    category_centers[node_id] = np.array(center_feature)
    else:
        print(f"\n步骤 2: 所有节点的 {FEATURE_KEY} 已缓存")
        print(f"  共 {len(category_centers)} 个节点")

    # 4. 预拟合降维器 (仅用于可视化, 默认不显示)
    print("\n步骤 5: 预拟合降维器")
    center_features_list = list(category_centers.values())
    global_reducer = None
    if len(center_features_list) > 0:
        all_features = np.vstack(center_features_list)
        if DIMENSION_REDUCTION_METHOD.lower() == "tsne":
            global_reducer = TSNE(n_components=2, perplexity=min(30, len(all_features) - 1),
                                  n_iter=1000, random_state=42, verbose=0)
        else:
            global_reducer = PCA(n_components=2)
        global_reducer.fit(all_features)
        print(f"降维器已拟合: {DIMENSION_REDUCTION_METHOD.upper()}")
    else:
        print("警告: 没有类别中心特征，跳过降维器拟合")

    # 5. 运行视频模式
    print("\n步骤 6: 开始处理视频")
    run_video_mode(model, processor, VIDEO_DIR, category_descriptions,
                   category_centers, SAVE_DIR)

    print("\n" + "=" * 60)
    print("🎉 全部完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
