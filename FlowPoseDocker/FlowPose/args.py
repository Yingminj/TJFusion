import argparse

def parse_arguments():
    parser = argparse.ArgumentParser()

    parser.add_argument('--drop_step', type=int, default=1, help='Keep every Nth sample from the dataset')
    parser.add_argument('--tracking', action='store_true', help='Enable object tracking between frames')
    parser.add_argument('--frame_gap_threshold', type=int, default=10, help='Maximum frame gap to continue tracking')
    parser.add_argument('--show', action='store_true', help='Display the video output')
    parser.add_argument('--shard_path', type=str, default='', help='Path to the data shards')
    parser.add_argument('--realsense', action='store_true', help='Use RealSense camera as input source')
    parser.add_argument('--n_pts', type=int, default=1024, help='Number of points to sample from point cloud')

    """ model architecture """
    parser.add_argument('--arch', type=str, default='pointnet', help='Model architecture: pointnet or scalenet')
    parser.add_argument("--dropout", default=0.2, type=float, help="Dropout rate.")
    parser.add_argument("--use_edm_aug", action="store_true", dest="use_edm_aug", default=False, help="Enable EDM augmentation with augment labels as conditions.")
    parser.add_argument('--compile', default=False, action='store_true', help='Use torch.compile')
    parser.add_argument("--norm_p", default=0.75, type=float, help="Norm power for adaptive weight.")
    parser.add_argument("--norm_eps", default=1e-3, type=float, help="Small constant for adaptive weight division.")
    parser.add_argument("--tr_sampler", default="v0", type=str, choices=["v0", "v1"], help="Joint (t, r) sampler version.")
    parser.add_argument("--P_mean_t", default=-0.6, type=float, help="P_mean_t of lognormal sampler.")
    parser.add_argument("--P_std_t", default=1.6, type=float, help="P_std_t of lognormal sampler.")
    parser.add_argument("--P_mean_r", default=-4.0, type=float, help="P_mean_r of lognormal sampler.")
    parser.add_argument("--P_std_r", default=1.6, type=float, help="P_std_r of lognormal sampler.")
    parser.add_argument("--ratio", default=100.0, type=float, help="Probability of sampling r (or h) DIFFERENT from t")
    
    
    
    """ data """
    parser.add_argument('--data_path', type=str)
    parser.add_argument('--batch_size', type=int, default=192)
    parser.add_argument('--max_batch_size', type=int, default=192)
    parser.add_argument('--pose_mode', type=str, default='rot_matrix')
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--percentage_data_for_train', type=float, default=1.0) 
    parser.add_argument('--percentage_data_for_val', type=float, default=1.0) 
    parser.add_argument('--percentage_data_for_test', type=float, default=1.0) 
    parser.add_argument('--train_source', type=str, default='Omni6DPose')
    parser.add_argument('--val_source', type=str, default='Omni6DPose')
    parser.add_argument('--test_source', type=str, default='Omni6DPose')
    parser.add_argument('--device', type=str, default='cuda')
    parser.add_argument('--num_points', type=int, default=1024)
    parser.add_argument('--per_obj', type=str, default='')
    parser.add_argument('--num_workers', type=int, default=32)
    parser.add_argument('--omni6dmug', action='store_true') # set to true if evaluating/fintuning an omni6dpose model on NOCS data
    
    
    """ model """
    parser.add_argument('--sampler_mode', nargs='+')
    parser.add_argument('--sampling_steps', type=int)
    parser.add_argument('--sde_mode', type=str, default='ve')
    parser.add_argument('--regression_head', type=str, default='Rx_Ry_and_T')
    parser.add_argument('--pointnet2_params', type=str, default='light')
    parser.add_argument('--pts_encoder', type=str, default='pointnet2') 
    parser.add_argument('--dino', type=str, default='pointwise') # none / global / pointwise
    parser.add_argument('--scale_embedding', type=int, default=180)
    
    
    """ training """
    parser.add_argument('--agent_type', type=str, default='flow', help='one of the [flow, scale]')
    parser.add_argument('--pretrained_flow_model_path', type=str)
    parser.add_argument('--pretrained_scale_model_path', type=str)
    parser.add_argument('--distillation', default=False, action='store_true')
    parser.add_argument('--n_epochs', type=int, default=1000)
    parser.add_argument('--log_dir', type=str, default='debug')
    parser.add_argument('--optimizer',  type=str, default='Adam')
    parser.add_argument('--eval_freq', type=int, default=100)
    parser.add_argument('--repeat_num', type=int, default=20)
    parser.add_argument('--grad_clip', type=float, default=1.)
    parser.add_argument('--ema_rate', type=float, default=0.999)
    parser.add_argument('--lr', type=float, default=1e-2)
    parser.add_argument('--warmup', type=int, default=100)
    parser.add_argument('--lr_decay', type=float, default=0.98)
    parser.add_argument('--use_pretrain', default=False, action='store_true')
    parser.add_argument('--parallel', default=False, action='store_true')   
    parser.add_argument('--num_gpu', type=int, default=4)
    parser.add_argument('--is_train', default=False, action='store_true')
    parser.add_argument('--perfect_depth', default=False, action='store_true')
    parser.add_argument('--load_per_object', default=False, action='store_true')
    parser.add_argument('--scale_batch_size', type=int, default=64)
    
    
    """ testing """
    parser.add_argument('--eval', default=False, action='store_true')
    parser.add_argument('--pred', default=False, action='store_true')
    parser.add_argument('--eval_repeat_num', type=int, default=50)
    parser.add_argument('--real_drop', type=int, default=10) # only keep part of the frames in test set for faster inference
    parser.add_argument('--save_video', default=False, action='store_true')
    parser.add_argument('--T0', type=float, default=1.0)
    
    
    parser.add_argument('--img_size', type=int, default=224, help='cropped image size')
    parser.add_argument('--result_dir', type=str, default='', help='result directory')
    parser.add_argument('--clustering', type=int, default=1, help='use clustering to solve multimodal issue')
    parser.add_argument('--clustering_eps', type=float, default=0.05, 
                        help='hyperparameter in clustering (see runners/evaluation_single.py for details)')
    parser.add_argument('--clustering_minpts', type=float, default=0.1667, 
                        help='hyperparameter in clustering (see runners/evaluation_single.py for details)')
    parser.add_argument('--retain_ratio', type=float, default=0.4, help='how much to retain in outlier removal stage')

    cfg = parser.parse_args()
    
    # some of these augmentation parameters are only for NOCS training
    # dynamic zoom in parameters
    cfg.DYNAMIC_ZOOM_IN_PARAMS = {
        'DZI_PAD_SCALE': 1.5,
        'DZI_TYPE': 'uniform',
        'DZI_SCALE_RATIO': 0.25,
        'DZI_SHIFT_RATIO': 0.25
    }
    # pts aug parameters
    cfg.PTS_AUG_PARAMS = {
        'aug_pc_pro': 0.2,
        'aug_pc_r': 0.2,
        'aug_rt_pro': 0.3,
        'aug_bb_pro': 0.3,
        'aug_bc_pro': 0.3
    }
    # 2D aug parameters
    cfg.DEFORM_2D_PARAMS = {
        'roi_mask_r': 3,
        'roi_mask_pro': 0.5
    }
    if cfg.eval or cfg.pred: # disable augmentation in evaluation
        cfg.DYNAMIC_ZOOM_IN_PARAMS['DZI_TYPE'] = 'none'
        cfg.DEFORM_2D_PARAMS['roi_mask_pro'] = 0

    assert cfg.dino in ['none', 'global', 'pointwise']
    
    return cfg