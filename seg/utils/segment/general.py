import cv2
import torch
import torch.nn.functional as F


def crop(masks, boxes):
    """
    "Crop" predicted masks by zeroing out everything not in the predicted bbox.
    Vectorized by Chong (thanks Chong).

    Args:
        - masks should be a size [h, w, n] tensor of masks
        - boxes should be a size [n, 4] tensor of bbox coords in relative point form
    """

    n, h, w = masks.shape
    x1, y1, x2, y2 = torch.chunk(boxes[:, :, None], 4, 1)  # x1 shape(1,1,n)
    r = torch.arange(w, device=masks.device, dtype=x1.dtype)[
        None, None, :
    ]  # rows shape(1,w,1)
    c = torch.arange(h, device=masks.device, dtype=x1.dtype)[
        None, :, None
    ]  # cols shape(h,1,1)

    return masks * ((r >= x1) * (r < x2) * (c >= y1) * (c < y2))


def process_mask_upsample(protos, masks_in, bboxes, shape):
    """
    Crop after upsample.
    proto_out: [mask_dim, mask_h, mask_w]
    out_masks: [n, mask_dim], n is number of masks after nms
    bboxes: [n, 4], n is number of masks after nms
    shape:input_image_size, (h, w)

    return: h, w, n
    """

    c, mh, mw = protos.shape  # CHW
    masks = (masks_in @ protos.float().view(c, -1)).sigmoid().view(-1, mh, mw)
    masks = F.interpolate(masks[None], shape, mode="bilinear", align_corners=False)[
        0
    ]  # CHW
    masks = crop(masks, bboxes)  # CHW
    return masks.gt_(0.5)


def process_mask(protos, masks_in, bboxes, shape, upsample=False):
    """
    Crop before upsample.
    proto_out: [mask_dim, mask_h, mask_w]
    out_masks: [n, mask_dim], n is number of masks after nms
    bboxes: [n, 4], n is number of masks after nms
    shape:input_image_size, (h, w)

    return: h, w, n
    """

    c, mh, mw = protos.shape  # CHW
    ih, iw = shape
    masks = (masks_in @ protos.float().view(c, -1)).sigmoid().view(-1, mh, mw)  # CHW

    downsampled_bboxes = bboxes.clone()
    downsampled_bboxes[:, 0] *= mw / iw
    downsampled_bboxes[:, 2] *= mw / iw
    downsampled_bboxes[:, 3] *= mh / ih
    downsampled_bboxes[:, 1] *= mh / ih

    masks = crop(masks, downsampled_bboxes)  # CHW
    if upsample:
        masks = F.interpolate(masks[None], shape, mode="bilinear", align_corners=False)[
            0
        ]  # CHW
    return masks.gt_(0.5)


def expand_and_shift_masks(masks, target_shape=(640, 640), x_offset=0, y_offset=0):
    """
    Expand and shift segmentation masks.

    Args:
        masks (torch.Tensor): Tensor of shape (N, H, W), where N is the number of masks,
                              H and W are the height and width of each mask.
        target_shape (tuple): Desired shape to expand to, in the form (height, width).
        x_offset (int): Horizontal offset to shift the mask area.
        y_offset (int): Vertical offset to shift the mask area.

    Returns:
        torch.Tensor: Modified tensor of masks with the expanded and shifted segment areas.
    """
    # Apply padding to shift mask
    masks = F.pad(masks, (x_offset, 0, y_offset, 0), mode="constant", value=0)

    # Current mask height and width
    _, original_height, original_width = masks.shape
    target_height, target_width = target_shape

    # Padding along the bottom and right
    pad_bottom = max(0, target_height - original_height)
    pad_right = max(0, target_width - original_width)

    # Apply padding to target shape
    expanded_masks = F.pad(
        masks, (0, pad_right, 0, pad_bottom), mode="constant", value=0
    )

    return expanded_masks


def scale_masks(img1_shape, masks, img0_shape, ratio_pad=None):
    """
    img1_shape: model input shape, [h, w]
    img0_shape: origin pic shape, [h, w, 3]
    masks: [h, w, num]
    resize for the most time
    """
    # Rescale coords (xyxy) from img1_shape to img0_shape
    if ratio_pad is None:  # calculate from img0_shape
        gain = min(
            img1_shape[0] / img0_shape[0], img1_shape[1] / img0_shape[1]
        )  # gain  = old / new
        pad = (img1_shape[1] - img0_shape[1] * gain) / 2, (
            img1_shape[0] - img0_shape[0] * gain
        ) / 2  # wh padding
    else:
        gain = ratio_pad[0][0]
        pad = ratio_pad[1]
    tl_pad = int(pad[1]), int(pad[0])  # y, x
    br_pad = int(img1_shape[0] - pad[1]), int(img1_shape[1] - pad[0])

    if len(masks.shape) < 2:
        raise ValueError(
            f'"len of masks shape" should be 2 or 3, but got {len(masks.shape)}'
        )
    # masks_h, masks_w, n
    masks = masks[tl_pad[0] : br_pad[0], tl_pad[1] : br_pad[1]]
    # 1, n, masks_h, masks_w
    # masks = masks.permute(2, 0, 1).contiguous()[None, :]
    # # shape = [1, n, masks_h, masks_w] after F.interpolate, so take first element
    # masks = F.interpolate(masks, img0_shape[:2], mode='bilinear', align_corners=False)[0]
    # masks = masks.permute(1, 2, 0).contiguous()
    # masks_h, masks_w, n
    if isinstance(masks, torch.Tensor):
        masks = masks.permute(2, 0, 1)
        masks = masks.unsqueeze(1)
        masks = F.interpolate(
            masks,
            size=(img0_shape[0], img0_shape[1]),
            mode="bilinear",
            align_corners=False,
        )
        masks = masks.squeeze(1)
    else:
        masks = cv2.resize(masks, (img0_shape[1], img0_shape[0]))

    # keepdim
    if len(masks.shape) == 2:
        masks = masks[:, :, None]

    return masks


def mask_iou(mask1, mask2, eps=1e-7):
    """
    mask1: [N, n] m1 means number of predicted objects
    mask2: [M, n] m2 means number of gt objects
    Note: n means image_w x image_h

    return: masks iou, [N, M]
    """
    intersection = torch.matmul(mask1, mask2.t()).clamp(0)
    union = (
        mask1.sum(1)[:, None] + mask2.sum(1)[None]
    ) - intersection  # (area1 + area2) - intersection
    return intersection / (union + eps)


def masks_iou(mask1, mask2, eps=1e-7):
    """
    mask1: [N, n] m1 means number of predicted objects
    mask2: [N, n] m2 means number of gt objects
    Note: n means image_w x image_h

    return: masks iou, (N, )
    """
    intersection = (mask1 * mask2).sum(1).clamp(0)  # (N, )
    union = (mask1.sum(1) + mask2.sum(1))[
        None
    ] - intersection  # (area1 + area2) - intersection
    return intersection / (union + eps)
