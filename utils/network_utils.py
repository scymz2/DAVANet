#!/usr/bin/python
# -*- coding: utf-8 -*-
# 
# Developed by Shangchen Zhou <shangchenzhou@gmail.com>

import os
import sys
import torch
import numpy as np
from datetime import datetime as dt
from config import cfg
import torch.nn.functional as F

import cv2


def mkdir(path):
    if not os.path.isdir(path):
        mkdir(os.path.split(path)[0])
    else:
        return
    os.mkdir(path)

def var_or_cuda(x):
    if torch.cuda.is_available():
        x = x.cuda(non_blocking=True)
    return x


def init_weights_xavier(m):
    if isinstance(m, torch.nn.Conv2d) or isinstance(m, torch.nn.ConvTranspose2d):
        torch.nn.init.xavier_uniform_(m.weight)
        if m.bias is not None:
            torch.nn.init.constant_(m.bias, 0)
    elif type(m) == torch.nn.BatchNorm2d or type(m) == torch.nn.InstanceNorm2d:
        if m.weight is not None:
            torch.nn.init.constant_(m.weight, 1)
            torch.nn.init.constant_(m.bias, 0)
    elif type(m) == torch.nn.Linear:
        torch.nn.init.normal_(m.weight, 0, 0.01)
        torch.nn.init.constant_(m.bias, 0)

def init_weights_kaiming(m):
    if isinstance(m, torch.nn.Conv2d) or isinstance(m, torch.nn.ConvTranspose2d):
        torch.nn.init.kaiming_normal_(m.weight)
        if m.bias is not None:
            torch.nn.init.constant_(m.bias, 0)
    elif type(m) == torch.nn.BatchNorm2d or type(m) == torch.nn.InstanceNorm2d:
        if m.weight is not None:
            torch.nn.init.constant_(m.weight, 1)
            torch.nn.init.constant_(m.bias, 0)
    elif type(m) == torch.nn.Linear:
        torch.nn.init.normal_(m.weight, 0, 0.01)
        torch.nn.init.constant_(m.bias, 0)

def save_disp_checkpoints(file_path, epoch_idx, dispnet, dispnet_solver, Best_Disp_EPE, Best_Epoch):
    print('[INFO] %s Saving checkpoint to %s ...' % (dt.now(), file_path))
    checkpoint = {
        'epoch_idx': epoch_idx,
        'Best_Disp_EPE': Best_Disp_EPE,
        'Best_Epoch': Best_Epoch,
        'dispnet_state_dict': dispnet.state_dict(),
        'dispnet_solver_state_dict': dispnet_solver.state_dict(),
    }
    torch.save(checkpoint, file_path)

def save_deblur_checkpoints(file_path, epoch_idx, deblurnet, deblurnet_solver, Best_Img_PSNR, Best_Epoch):
    print('[INFO] %s Saving checkpoint to %s ...\n' % (dt.now(), file_path))
    checkpoint = {
        'epoch_idx': epoch_idx,
        'Best_Img_PSNR': Best_Img_PSNR,
        'Best_Epoch': Best_Epoch,
        'deblurnet_state_dict': deblurnet.state_dict(),
        'deblurnet_solver_state_dict': deblurnet_solver.state_dict(),
    }
    torch.save(checkpoint, file_path)

def save_checkpoints(file_path, epoch_idx, dispnet, dispnet_solver, deblurnet, deblurnet_solver, Disp_EPE, Best_Img_PSNR, Best_Epoch):
    print('[INFO] %s Saving checkpoint to %s ...' % (dt.now(), file_path))
    checkpoint = {
        'epoch_idx': epoch_idx,
        'Disp_EPE': Disp_EPE,
        'Best_Img_PSNR': Best_Img_PSNR,
        'Best_Epoch': Best_Epoch,
        'dispnet_state_dict': dispnet.state_dict(),
        'dispnet_solver_state_dict': dispnet_solver.state_dict(),
        'deblurnet_state_dict': deblurnet.state_dict(),
        'deblurnet_solver_state_dict': deblurnet_solver.state_dict(),
    }
    torch.save(checkpoint, file_path)

def ckpt_single_to_multi(model, pretrained_dict):
    model_dict = model.state_dict()
    # print(model_dict.keys())
    pretrained_dict = {'module.' + str(k): v for k, v in pretrained_dict.items()}
    # print(pretrained_dict.keys())
    pretrained_dict = {k: v for k, v in pretrained_dict.items() if k in model_dict}
    for k,v in model_dict.items():
        if k in pretrained_dict and pretrained_dict[k].shape == model_dict[k].shape:
            print('matched: ' + str(k))
            model_dict[k] = pretrained_dict[k]
        else:
            if 'module.upconv2_u' in k or 'module.upconv1_u' in k:
                print('matched: ' + str(k))
                kk = k[:15] + '4' + k[16:]
                print('sss:' + str(kk))
                model_dict[k] = pretrained_dict[kk]
            else:
                print('un_matched: ' + str(k))
                model_dict[k] = model_dict[k]
    # pretrained_dict = {k: v for k, v in pretrained_dict.items() if (k in model_dict and pretrained_dict[k].shape == model_dict[k].shape)}
    # print('matched layers : ' + str(pretrained_dict.keys()))
    # return pretrained_dict
    return model_dict

def re_init(model, pretrained_dict):
    model_dict = model.state_dict()
    for k,v in model_dict.items():
        # if k in pretrained_dict and not 'module.convd_3' in k:
        if k in pretrained_dict and pretrained_dict[k].shape == model_dict[k].shape:
            model_dict[k] = pretrained_dict[k]
            print('loaded: ' + str(k))
        else:
            print('re-init: ' + str(k))
    return model_dict


def temp_init(model, pretrained_dict):
    model_dict = model.state_dict()
    for k,v in model_dict.items():
        if 'gate' in k:
            k_m = k.replace('gate', 'mask')
            model_dict[k] = pretrained_dict[k_m]
            print('loaded_mask: ' + str(k))
    return model_dict

def count_parameters(model):
    return sum(p.numel() for p in model.parameters())

def get_weight_parameters(model):
    return [param for name, param in model.named_parameters() if ('weight' in name)]

def get_bias_parameters(model):
    return [param for name, param in model.named_parameters() if ('bias' in name)]

class AverageMeter(object):
    """Computes and stores the average and current value"""
    def __init__(self):
        self.reset()

    def reset(self):
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0

    def update(self, val, n=1):
        self.val = val
        self.sum += val * n
        self.count += n
        self.avg = self.sum / self.count

    def __repr__(self):
        return '{:.5f} ({:.5f})'.format(self.val, self.avg)

'''input Tensor: 2 H W'''
def graybi2rgb(graybi):
    assert(isinstance(graybi, torch.Tensor))
    global args
    _, H, W = graybi.shape
    rgb_1 = torch.zeros((3,H,W))
    rgb_2 = torch.zeros((3,H,W))
    normalized_gray_map = graybi / (graybi.max())
    rgb_1[0] = normalized_gray_map[0]
    rgb_1[1] = normalized_gray_map[0]
    rgb_1[2] = normalized_gray_map[0]

    rgb_2[0] = normalized_gray_map[1]
    rgb_2[1] = normalized_gray_map[1]
    rgb_2[2] = normalized_gray_map[1]
    return rgb_1.clamp(0,1), rgb_2.clamp(0,1)

'''consistency check'''
'''get occlusion ground truth : 0: occlusion'''
'''input Tensor: 2 H W'''
'''torch.gater() backword, torch.scatter_() forword'''
def get_occ_bicheck(disps):
    assert(isinstance(disps[0], torch.Tensor) and isinstance(disps[1], torch.Tensor))
    alpha = 0.001
    beta  = 0.5
    _, H, W  = disps[0].shape
    disp_left  = disps[0].view(H,W)
    disp_right = disps[1].view(H,W)
    mask0_lelf  = ~np.logical_or(torch.isnan(disp_left), torch.isinf(disp_left))
    mask0_right = ~np.logical_or(torch.isnan(disp_right), torch.isinf(disp_right))
    disp_left[torch.isnan(disp_left)] = 0.0
    disp_right[torch.isnan(disp_right)] = 0.0
    disp_left[torch.isinf(disp_left)] = 0.0
    disp_right[torch.isinf(disp_right)] = 0.0

    xx = torch.arange(0, W).repeat(H, 1).float()

    warp_b = (xx-disp_left+0.5).long()
    mask1_left = warp_b >= 0
    warp_b[~mask1_left] = 0
    warp_f = torch.gather(disp_right, 1, warp_b)
    diff_temp = (disp_left - warp_f)**2 - (alpha*(disp_left**2 + warp_f**2) + beta)
    mask2_lelf = diff_temp<=0
    occ_left  = torch.zeros((H,W), dtype=torch.float32)
    occ_left[np.logical_and(np.logical_and(mask0_lelf, mask1_left), mask2_lelf)] = 1

    warp_b = (xx+disp_right+0.5).long()
    mask1_right = warp_b <= (W - 1)
    warp_b[~mask1_right] = 0
    warp_f = torch.gather(disp_left, 1, warp_b)
    diff_temp = (disp_right - warp_f)**2 - (alpha*(disp_right**2 + warp_f**2) + beta)
    mask2_right = diff_temp<=0
    occ_right  = torch.zeros((H,W), dtype=torch.float32)
    occ_right[np.logical_and(np.logical_and(mask0_right, mask1_right),mask2_right)] = 1

    ## debug ##
    # occs = torch.cat([occ_left.view(1,H,W), occ_right.view(1,H,W)], 0)
    # occimg_left, occimg_right = graybi2rgb(occs)
    # img_merge = torch.cat([occimg_left, occimg_right], 1).numpy().transpose(1,2,0)
    # cv2.namedWindow('Occlusions', 0);
    # cv2.imshow("Occlusions", img_merge)
    # cv2.waitKey(0)
    # cv2.destroyAllWindows()

    # return [occ_left.view(1,H,W), occ_right.view(1,H,W)]

def get_occ(imgs, disps, cuda = True):
    '''
    img: b, c, h, w
    disp: b, h, w
    '''
    assert(isinstance(imgs[0], torch.Tensor) and isinstance(imgs[1], torch.Tensor))
    assert(isinstance(disps[0], torch.Tensor) and isinstance(disps[1], torch.Tensor))
    if cuda == True:
        imgs = [var_or_cuda(img) for img in imgs]
        disps = [var_or_cuda(disp) for disp in disps]
    alpha = 0.001
    beta  = 0.005
    B, _, H, W  = imgs[0].shape
    disp_left  = disps[0]
    disp_right = disps[1]
    mask0_lelf  = ~np.logical_or(torch.isnan(disp_left), torch.isinf(disp_left))
    mask0_right = ~np.logical_or(torch.isnan(disp_right), torch.isinf(disp_right))
    disp_left[torch.isnan(disp_left)] = 0.0
    disp_right[torch.isnan(disp_right)] = 0.0
    disp_left[torch.isinf(disp_left)] = 0.0
    disp_right[torch.isinf(disp_right)] = 0.0

    img_warp_left = disp_warp(imgs[1], -disp_left, cuda = cuda)
    img_warp_right = disp_warp(imgs[0], disp_right, cuda = cuda)

    diff_left = (imgs[0] - img_warp_left)**2 - (alpha*(imgs[0]**2 + img_warp_left**2) + beta)
    mask1_left = torch.sum(diff_left, 1)<=0
    occ_left  = torch.zeros((B,H,W), dtype=torch.float32)
    occ_left[np.logical_and(mask0_lelf, mask1_left)] = 1

    diff_right = (imgs[1] - img_warp_right)**2 - (alpha*(imgs[1]**2 + img_warp_right**2) + beta)
    mask1_right = torch.sum(diff_right, 1)<=0
    occ_right  = torch.zeros((B,H,W), dtype=torch.float32)
    occ_right[np.logical_and(mask0_right, mask1_right)] = 1

    ## debug ##
    # occs = torch.cat([occ_left.view(1,H,W), occ_right.view(1,H,W)], 0)
    # occimg_left, occimg_right = graybi2rgb(occs)
    # img_merge = torch.cat([occimg_left, occimg_right], 1).numpy().transpose(1,2,0)
    # cv2.namedWindow('Occlusions', 0);
    # cv2.imshow("Occlusions", img_merge)
    # cv2.waitKey(0)
    # cv2.destroyAllWindows()

    return [occ_left, occ_right]


def get_disp_right(disp_left):
    assert(isinstance(disp_left, np.ndarray))
    disp_left = torch.from_numpy(disp_left)
    H, W = disp_left.shape
    xx = torch.arange(0, W).repeat(H, 1).float()
    warp_f = (xx-disp_left).long()
    warp_f[warp_f<0] = 0

    disp_right = torch.zeros(H, W, dtype=torch.float32).scatter_(1, warp_f, disp_left)

    return disp_right.numpy()


def disp_warp(img, disp, cuda=True):
    '''
    img.shape = b, c, h, w
    disp.shape = b, h, w
    '''
    b, c, h, w = img.shape
    if cuda == True:
        right_coor_x = (torch.arange(start=0, end=w, out=torch.cuda.FloatTensor())).repeat(b, h, 1)
        right_coor_y = (torch.arange(start=0, end=h, out=torch.cuda.FloatTensor())).repeat(b, w, 1).transpose(1, 2)
    else:
        right_coor_x = (torch.arange(start=0, end=w, out=torch.FloatTensor())).repeat(b, h, 1)
        right_coor_y = (torch.arange(start=0, end=h, out=torch.FloatTensor())).repeat(b, w, 1).transpose(1, 2)
    left_coor_x1 = right_coor_x + disp
    left_coor_norm1 = torch.stack((left_coor_x1 / (w - 1) * 2 - 1, right_coor_y / (h - 1) * 2 - 1), dim=1)
    ## backward warp
    warp_img = torch.nn.functional.grid_sample(img, left_coor_norm1.permute(0, 2, 3, 1))

    return warp_img
