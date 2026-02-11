# backend/bev/homography.py
import numpy as np

def make_virtual_H(
    img_w=1280, img_h=720,
    fov_deg=90.0,
    cam_h_m=1.5,
    pitch_deg=15.0,
    ppm=20.0,
    bev_origin_px=(0.0, 0.0),
    yaw_deg=0.0
):
    fov = np.deg2rad(fov_deg)
    fx = (img_w / 2) / np.tan(fov / 2)
    fy = fx
    cx = img_w / 2
    cy = img_h / 2
    K = np.array([[fx, 0, cx],
                  [0, fy, cy],
                  [0,  0,  1]], dtype=np.float64)

    yaw = np.deg2rad(yaw_deg)
    pitch = np.deg2rad(pitch_deg)

    R_yaw = np.array([[ np.cos(yaw), -np.sin(yaw), 0],
                      [ np.sin(yaw),  np.cos(yaw), 0],
                      [          0,           0, 1]], dtype=np.float64)

    R_pitch = np.array([[ np.cos(pitch), 0, np.sin(pitch)],
                        [            0, 1,            0],
                        [-np.sin(pitch), 0, np.cos(pitch)]], dtype=np.float64)

    R_wc = R_pitch @ R_yaw

    Cw = np.array([0, 0, cam_h_m], dtype=np.float64)
    t = -R_wc @ Cw

    r1 = R_wc[:, 0:1]
    r2 = R_wc[:, 1:2]
    H_w2i = K @ np.concatenate([r1, r2, t.reshape(3,1)], axis=1)
    H_i2w = np.linalg.inv(H_w2i)

    bev_x, bev_y = bev_origin_px
    S = np.array([[ppm,  0, bev_x],
                  [ 0, ppm, bev_y],
                  [ 0,  0,    1]], dtype=np.float64)

    H = S @ H_i2w
    return H

def apply_homography(point, H):
    x, y = point
    x_new = (H[0][0] * x + H[0][1] * y + H[0][2])
    y_new = (H[1][0] * x + H[1][1] * y + H[1][2])
    denom = H[2][0] * x + H[2][1] * y + H[2][2]
    return (x_new/denom, y_new/denom)
