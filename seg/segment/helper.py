# import some common libraries
import numpy as np
from PIL import Image
from datetime import datetime
import matplotlib.pyplot as plt
from skimage import measure
import os, json, cv2, random, pathlib, shutil

random.seed(0)
CATEGORIES = ["Open", "close", "Unknown"]
INST_CATEGORIES = ["stomata"]
COLORS = {
    "Open": (0, 255, 0),  # Green
    "close": (255, 0, 0),  # Red
    "Unknown": (0, 0, 255),  # Blue
}


def random_color():
    return [random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)]


def binary_mask_to_polygon(binary_mask, tolerance=0):
    r"""Converts a binary mask to COCO polygon representation

    Args
    ----
        - binary_mask: a 2D binary numpy array where '1's represent the object
        - tolerance: Maximum distance from original points of polygon to approximated polygonal chain. If tolerance is 0, the original coordinate array is returned.

    """

    def close_contour(contour):
        if not np.array_equal(contour[0], contour[-1]):
            contour = np.vstack((contour, contour[0]))
        return contour

    polygons = []
    # pad mask to close contours of shapes which start and end at an edge
    padded_binary_mask = np.pad(
        binary_mask, pad_width=1, mode="constant", constant_values=0
    )
    contours = measure.find_contours(padded_binary_mask, 0.5, fully_connected="high")
    for contour in contours:
        contour = close_contour(contour)
        if len(contour) < 3:
            continue
        contour = np.flip(contour, axis=1)
        segmentation = contour.ravel().tolist()
        # after padding and subtracting 1 we may get -0.5 points in our segmentation
        #         segmentation = [0 if i < 0 else i for i in segmentation]
        polygons.append(segmentation)
    return polygons


def fit_polygons_to_rotated_bboxes(polygons):
    r"""
    convert polygons to rotated bboxes using cv2.minAreaRect().

    Args:
     - polygons (list): is a list of polygon points [x1, y1, x2, y2,...]
    """
    rbboxes = []
    for p in polygons:
        pts_x = p[::2]
        pts_y = p[1::2]
        pts = [[x, y] for x, y in zip(pts_x, pts_y)]
        pts = np.array(pts, np.float32)
        rect = cv2.minAreaRect(pts)  #  ((cx, cy), (w, h), a)
        rbboxes.append(rect)
    return rbboxes


def draw_rotated_bboxes(img_filename, rboxes, texts, thickness=1, color=None):
    img = cv2.imread(img_filename)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = draw_rotated_bboxes_on_image(img, rboxes, texts, thickness, color)
    return img


def draw_rotated_bboxes_on_image(img, rboxes, texts, thickness=1, color=None):
    r"""
    convert

    Args:
     - label_dicts (list): is the label dictionary. User must shuffle before split.
     - split_ratio (list): this is a list consisting of the ratio between train, val, test.
       e.g. split_ratio = [8,1,1] denotes train:val:test = 8:1:1
    """
    img_draw = img.copy()
    tl = thickness
    tf = max(tl - 1, 1)
    for rb, text in zip(rboxes, texts):
        c = random_color() if color is None else color
        box = cv2.boxPoints(rb)
        box = np.int0(box)
        cv2.drawContours(img_draw, [box], 0, color=c, thickness=thickness)
        t_size = cv2.getTextSize(text, 0, fontScale=tl / 3, thickness=thickness)[0]
        pt = np.amin(box, axis=0)
        c1 = (pt[0], pt[1])
        c2 = c1[0] + t_size[0], c1[1] - t_size[1] - 3
        cv2.rectangle(
            img_draw, c1, c2, color=color, thickness=-1, lineType=cv2.LINE_AA
        )  # filled
        cv2.putText(
            img_draw,
            text,
            (c1[0], c1[1] - 2),
            0,
            tl / 3,
            [255, 255, 255],
            thickness=tf,
            lineType=cv2.LINE_AA,
        )
    return img_draw


#
# Code for dilation and erosion on a single mask
#
def dilation_erosion_tensor_mask(mask, dilatation_size):
    r"""
    This method fix disconnected mask with dilation and erosion technique. This are tensors

    Args:
     - mask: the mask you wish to fix.
     - dilation_size: the size of dilation and erosion.
    """

    print(type(mask))
    print(mask)

    # setup a kernel
    kernel = torch.ones(dilatation_size, dilatation_size)

    # dilation and erosion
    mask = dilation(mask, kernel)
    mask = erosion(mask, kernel)

    return mask


#
# Code for dilation and erosion on a list of masks
#
def dilation_erosion_tensor_masks(masks, dilatation_size):
    r"""
    This method fix disconnected masks with dilation and erosion technique

    Args:
     - masks: a list of masks you wish to fix.
     - dilation_size: the size of dilation and erosion.
    """
    processed_masks = []
    for mask in masks:
        processed_masks.append(dilation_erosion_tensor_mask(mask, dilatation_size))

    return processed_masks


#
# Code for dilation and erosion
#
def dilation_erosion_mask(mask, dilatation_size):
    r"""
    This method fix disconnected mask with dilation and erosion technique

    Args:
     - mask: the mask you wish to fix.
     - dilation_size: the size of dilation and erosion.
    """
    # setup a kernel
    kernel = np.ones((dilatation_size, dilatation_size), np.uint8)
    mask = cv2.erode(mask, kernel, iterations=1)
    mask = cv2.dilate(mask, kernel, iterations=1)

    return mask


#
# Code for dilation and erosion
#
def dilation_erosion_masks(masks, dilatation_size):
    r"""
    This method fix disconnected masks with dilation and erosion technique

    Args:
     - mask: the mask you wish to fix.
     - dilation_size: the size of dilation and erosion.
    """
    processed_masks = []
    for mask in masks:
        processed_masks.append(dilation_erosion_mask(mask, dilatation_size))

    return processed_masks
