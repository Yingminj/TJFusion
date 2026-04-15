"""
Minimal visualization utilities for YomniFlow inference.
Draws 3D bounding boxes using camera intrinsics and object poses.
"""
import cv2
import numpy as np


def get_3d_bbox(size):
    """
    Generate 8 corners of a 3D bounding box in object frame.
    
    Args:
        size: [width, height, depth] in meters
    
    Returns:
        bbox_3d: [3, 8] array of corner coordinates
    """
    w, h, d = size[0], size[1], size[2]
    bbox_3d = np.array([
        [+w/2, +w/2, -w/2, -w/2, +w/2, +w/2, -w/2, -w/2],
        [+h/2, +h/2, +h/2, +h/2, -h/2, -h/2, -h/2, -h/2],
        [+d/2, -d/2, +d/2, -d/2, +d/2, -d/2, +d/2, -d/2]
    ])
    return bbox_3d


def transform_3d_coords(coords, pose):
    """
    Transform 3D coordinates using a 4x4 pose matrix.
    
    Args:
        coords: [3, N] array of 3D points
        pose: [4, 4] homogeneous transformation matrix
    
    Returns:
        transformed: [3, N] array of transformed points
    """
    coords_hom = np.vstack([coords, np.ones((1, coords.shape[1]))])
    new_coords = pose @ coords_hom
    return new_coords[:3, :] / new_coords[3, :]


def project_to_2d(coords_3d, intrinsics):
    """
    Project 3D points to 2D image using camera intrinsics.
    
    Args:
        coords_3d: [3, N] array of 3D points in camera frame
        intrinsics: camera intrinsics object with fx, fy, cx, cy
    
    Returns:
        points_2d: [N, 2] array of 2D image coordinates
    """
    K = np.array([
        [intrinsics.fx, 0, intrinsics.cx],
        [0, intrinsics.fy, intrinsics.cy],
        [0, 0, 1]
    ])
    proj = K @ coords_3d  # [3, N]
    proj_2d = proj[:2, :] / proj[2, :]  # [2, N]
    return proj_2d.T.astype(np.int32)  # [N, 2]


def draw_axes(img, pose, intrinsics, axis_length=0.1, thickness=2):
    """
    Draw coordinate axes (X=red, Y=green, Z=blue) for object pose.
    
    Args:
        img: image to draw on
        pose: [4, 4] object pose matrix
        intrinsics: camera intrinsics object
        axis_length: length of axes in meters
        thickness: line thickness
    
    Returns:
        img: image with axes drawn
    """
    # Define axes in object frame: origin + 3 unit vectors
    axes_3d = np.array([
        [0, axis_length, 0, 0],  # X, Y, Z origins and endpoints
        [0, 0, axis_length, 0],
        [0, 0, 0, axis_length]
    ])
    
    # Transform to camera frame
    transformed = transform_3d_coords(axes_3d, pose)  # [3, 4]
    
    # Project to 2D
    pts_2d = project_to_2d(transformed, intrinsics)  # [4, 2]
    
    origin = tuple(pts_2d[0])
    
    # Draw X axis (red)
    cv2.line(img, origin, tuple(pts_2d[1]), (0, 0, 255), thickness)
    # Draw Y axis (green)
    cv2.line(img, origin, tuple(pts_2d[2]), (0, 255, 0), thickness)
    # Draw Z axis (blue)
    cv2.line(img, origin, tuple(pts_2d[3]), (255, 0, 0), thickness)
    
    return img


def draw_transparent_polygon(img, points, color, alpha=0.3):
    """
    Draw a filled polygon with transparency.
    
    Args:
        img: image to draw on
        points: [N, 2] array of 2D points forming the polygon
        color: BGR color tuple
        alpha: transparency level (0=transparent, 1=opaque)
    
    Returns:
        img: image with transparent polygon drawn
    """
    overlay = img.copy()
    cv2.fillPoly(overlay, [points], color)
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)
    return img


def draw_3d_bbox(img, pose, size, intrinsics, color=(0, 255, 0), thickness=2, draw_axes_flag=False, axes_length=0.1, alpha=0.3):
    """
    Draw 3D bounding box on image with transparent surfaces.
    
    Args:
        img: image to draw on
        pose: [4, 4] object pose matrix
        size: [3] object dimensions [width, height, depth]
        intrinsics: camera intrinsics object
        color: BGR color tuple
        thickness: line thickness
        draw_axes_flag: whether to draw coordinate axes
        axes_length: length of coordinate axes in meters
        alpha: transparency level for surfaces (0=transparent, 1=opaque)
    
    Returns:
        img: image with bounding box drawn
    """
    # Generate 3D bbox corners
    bbox_3d = get_3d_bbox(size)  # [3, 8]
    
    # Transform to camera frame
    transformed = transform_3d_coords(bbox_3d, pose)  # [3, 8]
    
    # Project to 2D
    pts_2d = project_to_2d(transformed, intrinsics)  # [8, 2]
    
    # Define the 6 faces of the bounding box
    # Each face is defined by 4 corner indices
    faces = [
        [0, 1, 3, 2],  # top face
        [4, 5, 7, 6],  # bottom face
        [0, 1, 5, 4],  # front face
        [2, 3, 7, 6],  # back face
        [0, 2, 6, 4],  # left face
        [1, 3, 7, 5],  # right face
    ]
    
    # Draw transparent faces
    for face_indices in faces:
        face_pts = pts_2d[face_indices]
        img = draw_transparent_polygon(img, face_pts, color, alpha)
    
    # Draw edges with layered colors (ground darker, top brighter)
    color_ground = (int(color[0]*0.3), int(color[1]*0.3), int(color[2]*0.3))
    color_pillar = (int(color[0]*0.6), int(color[1]*0.6), int(color[2]*0.6))
    
    # Ground layer (bottom 4 edges): indices 4,5,6,7
    for i, j in zip([4, 5, 6, 7], [5, 7, 4, 6]):
        cv2.line(img, tuple(pts_2d[i]), tuple(pts_2d[j]), color_ground, thickness)
    
    # Pillars (4 vertical edges)
    for i, j in zip(range(4), range(4, 8)):
        cv2.line(img, tuple(pts_2d[i]), tuple(pts_2d[j]), color_pillar, thickness)
    
    # Top layer (top 4 edges): indices 0,1,2,3
    for i, j in zip([0, 1, 2, 3], [1, 3, 0, 2]):
        cv2.line(img, tuple(pts_2d[i]), tuple(pts_2d[j]), color, thickness)
    
    # Draw coordinate axes if requested
    if draw_axes_flag:
        img = draw_axes(img, pose, intrinsics, axes_length, thickness)
    
    return img


def visualize_detections(img, poses, lengths, intrinsics, color=(0, 255, 0), thickness=2, draw_axes=True, axes_length=0.1, alpha=0.3):
    """
    Draw all detected objects on image.
    
    Args:
        img: image to draw on
        poses: [N, 4, 4] array of object poses
        lengths: [N, 3] array of object dimensions
        intrinsics: camera intrinsics object
        color: BGR color tuple
        thickness: line thickness
        draw_axes: whether to draw coordinate axes for each object
        axes_length: length of coordinate axes in meters
        alpha: transparency level for surfaces (0=transparent, 1=opaque)
    
    Returns:
        img: image with all detections drawn
    """
    for pose, length in zip(poses, lengths):
        img = draw_3d_bbox(img, pose, length, intrinsics, color, thickness, draw_axes, axes_length, alpha)
    return img
