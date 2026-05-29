"""
Convert a Star-CCM+ topology-optimization CSV export to a binary PNG image.

Usage:
    python csv2img.py <path_to_csv> [--size 128]

The PNG is saved next to the CSV with the same stem name.
"""

import os
import sys
import csv
import glob
import numpy as np
from scipy.interpolate import griddata
import cv2


def csv_to_image(case_dir, grid_size=128):
    """
    Read a Star-CCM+ export CSV containing topology data and produce
    a binary PNG (white = material, black = void).

    Args:
        case_dir:  Path to the case folder containing a single CSV.
        grid_size: Resolution of the output image (square).

    Returns:
        Path to the created PNG file.
    """
    case_dir = os.path.abspath(case_dir)
    if not os.path.isdir(case_dir):
        raise FileNotFoundError(f"Directory not found: {case_dir}")

    csv_files = glob.glob(os.path.join(case_dir, '*.csv'))
    if len(csv_files) == 0:
        raise FileNotFoundError(f"No .csv file found in {case_dir}")
    if len(csv_files) > 1:
        print(f"⚠ Multiple .csv files found – using {os.path.basename(csv_files[0])}")
    csv_path = csv_files[0]

    # --- Read CSV ---
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    x = np.array([float(r['Position[X] (m)']) for r in rows])
    y = np.array([float(r['Position[Y] (m)']) for r in rows])
    topo = np.array([float(r['Topology Level Set']) for r in rows])

    # --- Interpolate onto regular grid ---
    xi = np.linspace(x.min(), x.max(), grid_size)
    yi = np.linspace(y.min(), y.max(), grid_size)
    xi_grid, yi_grid = np.meshgrid(xi, yi)

    grid = griddata(
        np.column_stack((x, y)),
        topo,
        (xi_grid, yi_grid),
        method='nearest',
    )

    # --- Threshold to binary image ---
    # material (topo >= 0) → white (255), void → black (0)
    binary = np.where(grid >= 0, 255, 0).astype(np.uint8)

    # Flip vertically so that +Y is up (image origin is top-left)
    binary = np.flip(binary, axis=0)

    # --- Save PNG ---
    # Strip "_geom" suffix from directory name for the output filename
    dir_name = os.path.basename(case_dir)
    stem = dir_name.removesuffix('_geom')
    out_path = os.path.join(case_dir, f'{stem}.png')
    cv2.imwrite(out_path, binary)
    print(f"✓ Saved {grid_size}x{grid_size} topology image to {out_path}")
    return out_path


if __name__ == '__main__':
    csv_to_image(
        case_dir='ref3_geom',
        grid_size=128,
    )
