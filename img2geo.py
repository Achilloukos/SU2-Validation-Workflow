import cv2
import numpy as np
import os
import json

def topology_to_geometry(image_path, output_geo='topology.geo', threshold=127, simplification=0.001, config_path=None, dilate=0):
    """
    Convert topology optimization image to .geo file (plain text Gmsh format)
    
    Args:
        image_path: Path to topology image
        output_geo: Output .geo filename
        threshold: Binary threshold value (0-255)
        simplification: Contour simplification factor (0-1, lower = more detail)
        config_path: Path to JSON config with image bounds and pipe types (required for inlet/outlet detection)
        dilate: Kernel size for morphological dilation of the white region (0 = disabled).
                Pushes back and smooths the black boundary. Use odd values (e.g. 3, 5, 7).
    """
    # Check if file exists
    if not os.path.exists(image_path):
        print(f"✗ Error: Image not found at {image_path}")
        return
    
    # Load image
    img = cv2.imread(image_path)
    if img is None:
        print(f"✗ Error: Could not load image {image_path}")
        return
    
    # Convert to grayscale
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img
    
    img_height, img_width = gray.shape
    
    # Load config (required for inlet/outlet detection)
    config = None
    if config_path and os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
            phys_width = config.get('box_length', 100.0) / 1000   # mm → m
            phys_height = config.get('box_width', 100.0) / 1000   # mm → m
        print(f"✓ Loaded bounds from config: {phys_width} x {phys_height} (converted from mm to m)")
    else:
        # Manual defaults - change these to your actual domain size
        phys_width = 0.1
        phys_height = 0.1
        print(f"⚠ Using default bounds: {phys_width} x {phys_height}")
        print(f"⚠ No config provided - inlet/outlet detection will use fallback logic")
    
    # Scale factors: pixels to physical coordinates
    # Divide by (width-1) because pixels are indexed 0 to width-1
    scale_x = phys_width / (img_width - 1)
    scale_y = phys_height / (img_height - 1)
    
    # Binary threshold (white = material)
    _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

    # Optional morphological dilation to push back and smooth the black boundary
    if dilate > 0:
        kernel_size = dilate if dilate % 2 == 1 else dilate + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        binary = cv2.dilate(binary, kernel, iterations=1)
        # Save dilated image for visual inspection
        dilated_path = os.path.splitext(image_path)[0] + "_dilated.png"
        cv2.imwrite(dilated_path, binary)
        print(f"✓ Applied dilation with elliptical kernel size {kernel_size}")
        print(f"  Saved dilated image to {dilated_path}")
    
    # Find bounding box of all non-white pixels
    non_white = cv2.inRange(gray, 0, threshold - 1)
    if cv2.countNonZero(non_white) > 0:
        x_min, y_min, w, h = cv2.boundingRect(non_white)
        x_max = x_min + w
        y_max = y_min + h
        print(f"⚠ Geometry pixel bounds: x=[{x_min}, {x_max}], y=[{y_min}, {y_max}]")
        print(f"  Pixel width: {x_max - x_min}, Pixel height: {y_max - y_min}")
    
    # Find ALL contours (external + internal)
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    
    print(f"✓ Found {len(contours)} contour(s)")
    
    # Simplify contours
    simplified = []
    for contour in contours:
        epsilon = max(simplification * cv2.arcLength(contour, True), 0.01)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        simplified.append(approx.reshape(-1, 2))
    
    # === Build geometry data structures ===
    # Using dicts instead of strings so we can split boundary lines before writing .geo
    tolerance = min(scale_x, scale_y) * 0.5

    geo_points = {}          # {point_id: (x, y)}
    geo_lines_data = {}      # {line_id: (p1_id, p2_id)}
    contour_line_lists = []  # [[line_ids per contour], ...]
    line_boundary_type = {}  # {line_id: "left"/"right"/"top"/"bottom"}

    point_id = 1
    line_id = 1

    for contour_idx, contour in enumerate(simplified):
        contour_points = []

        for x, y in contour:
            x_phys = float(x) * scale_x
            y_phys = float(img_height - 1 - y) * scale_y  # Flip Y
            geo_points[point_id] = (x_phys, y_phys)
            contour_points.append(point_id)
            point_id += 1

        contour_lines = []
        for i in range(len(contour_points)):
            p1 = contour_points[i]
            p2 = contour_points[(i + 1) % len(contour_points)]
            geo_lines_data[line_id] = (p1, p2)

            x1, y1 = geo_points[p1]
            x2, y2 = geo_points[p2]

            on_left = (
                abs(x1) < tolerance
                and abs(x2) < tolerance
                and abs(x1 - x2) < tolerance
            )
            on_right = (
                abs(x1 - phys_width) < tolerance
                and abs(x2 - phys_width) < tolerance
                and abs(x1 - x2) < tolerance
            )
            on_bottom = (
                abs(y1) < tolerance
                and abs(y2) < tolerance
                and abs(y1 - y2) < tolerance
            )
            on_top = (
                abs(y1 - phys_height) < tolerance
                and abs(y2 - phys_height) < tolerance
                and abs(y1 - y2) < tolerance
            )

            if on_left:
                line_boundary_type[line_id] = "left"
            elif on_right:
                line_boundary_type[line_id] = "right"
            elif on_top:
                line_boundary_type[line_id] = "top"
            elif on_bottom:
                line_boundary_type[line_id] = "bottom"

            contour_lines.append(line_id)
            line_id += 1

        contour_line_lists.append(contour_lines)

    # === Split boundary lines at pipe boundaries ===
    # pipe_line_ids tracks which line(s) correspond to each pipe opening
    pipe_line_ids = {}  # {(boundary_name, pipe_idx): [line_ids]}

    if config and config.get('pipe_width') is not None:
        pipe_width_val = config['pipe_width'] / 1000  # mm → m
        fractions_cfg = {
            'left':   config.get('fractions_left', []),
            'right':  config.get('fractions_right', []),
            'top':    config.get('fractions_top', []),
            'bottom': config.get('fractions_bottom', []),
        }

        # boundary_length is the dimension along which pipes are placed
        # axis is the varying coordinate on that boundary
        # fixed_val is the constant coordinate on that boundary
        boundary_meta = {
            'left':   (phys_height, 'y', 0.0),
            'right':  (phys_height, 'y', phys_width),
            'top':    (phys_width,  'x', phys_height),
            'bottom': (phys_width,  'x', 0.0),
        }

        def _pipe_spans(fractions, boundary_len, pw):
            spans = []
            for frac in fractions:
                c = frac * boundary_len
                spans.append((c - pw / 2, c + pw / 2))
            return spans

        for bname in ('left', 'right', 'top', 'bottom'):
            fracs = fractions_cfg[bname]
            blen, axis, fixed_val = boundary_meta[bname]
            pipe_spans = _pipe_spans(fracs, blen, pipe_width_val)
            if not pipe_spans:
                continue

            boundary_lids = [lid for lid, bt in line_boundary_type.items()
                             if bt == bname]

            for lid in boundary_lids:
                if lid not in geo_lines_data:
                    continue  # already replaced by a previous split

                p1_id, p2_id = geo_lines_data[lid]
                x1, y1 = geo_points[p1_id]
                x2, y2 = geo_points[p2_id]

                if axis == 'y':
                    span_start, span_end = y1, y2
                else:
                    span_start, span_end = x1, x2

                span_min = min(span_start, span_end)
                span_max = max(span_start, span_end)
                going_positive = span_end >= span_start

                # Find all pipes whose span overlaps this line
                overlapping = []
                for pidx, (ps, pe) in enumerate(pipe_spans):
                    os_ = max(span_min, ps)
                    oe_ = min(span_max, pe)
                    if oe_ - os_ > tolerance:
                        overlapping.append((pidx, ps, pe))

                if not overlapping:
                    continue  # purely wall, nothing to do

                # If line is entirely within a single pipe span, keep as-is
                if len(overlapping) == 1:
                    pidx, ps, pe = overlapping[0]
                    if span_min >= ps - tolerance and span_max <= pe + tolerance:
                        pipe_line_ids.setdefault((bname, pidx), []).append(lid)
                        continue

                # Collect all interior split points
                split_set = set()
                for pidx, ps, pe in overlapping:
                    if ps > span_min + tolerance and ps < span_max - tolerance:
                        split_set.add(ps)
                    if pe > span_min + tolerance and pe < span_max - tolerance:
                        split_set.add(pe)

                if not split_set:
                    # No interior cuts needed – whole line is pipe
                    for pidx, ps, pe in overlapping:
                        pipe_line_ids.setdefault((bname, pidx), []).append(lid)
                    continue

                # Sort split values along line direction
                split_vals = sorted(split_set) if going_positive else sorted(split_set, reverse=True)

                # Build point chain: p1 → split_points → p2
                chain = [p1_id]
                for val in split_vals:
                    if axis == 'y':
                        geo_points[point_id] = (fixed_val, val)
                    else:
                        geo_points[point_id] = (val, fixed_val)
                    chain.append(point_id)
                    point_id += 1
                chain.append(p2_id)

                # Remove original line
                del geo_lines_data[lid]
                del line_boundary_type[lid]

                # Create sub-lines and classify each segment
                new_lids = []
                for i in range(len(chain) - 1):
                    geo_lines_data[line_id] = (chain[i], chain[i + 1])
                    line_boundary_type[line_id] = bname

                    sp1 = geo_points[chain[i]]
                    sp2 = geo_points[chain[i + 1]]
                    seg_mid = ((sp1[1] + sp2[1]) / 2) if axis == 'y' else ((sp1[0] + sp2[0]) / 2)

                    for pidx, ps, pe in overlapping:
                        if ps - tolerance <= seg_mid <= pe + tolerance:
                            pipe_line_ids.setdefault((bname, pidx), []).append(line_id)
                            break

                    new_lids.append(line_id)
                    line_id += 1

                # Update contour_line_lists: replace old lid with new sub-lines
                for cl in contour_line_lists:
                    try:
                        idx = cl.index(lid)
                        cl[idx:idx + 1] = new_lids
                        break
                    except ValueError:
                        continue

    # === Generate .geo text from data structures ===
    geo_text = []
    geo_text.append("// Geometry from topology optimization image\n")
    geo_text.append("lc = 0.5;  // characteristic length\n\n")

    for pid in sorted(geo_points.keys()):
        x, y = geo_points[pid]
        geo_text.append(f"Point({pid}) = {{{x}, {y}, 0, lc}};\n")

    geo_text.append("\n")

    for lid in sorted(geo_lines_data.keys()):
        p1, p2 = geo_lines_data[lid]
        geo_text.append(f"Line({lid}) = {{{p1}, {p2}}};\n")

    geo_text.append("\n")

    loop_ids = []
    for contour_idx, contour_lines in enumerate(contour_line_lists):
        loop_id = contour_idx + 1
        lines_str = ", ".join(map(str, contour_lines))
        geo_text.append(f"Curve Loop({loop_id}) = {{{lines_str}}};\n")
        loop_ids.append(loop_id)

    geo_text.append("\n")

    if len(loop_ids) == 1:
        geo_text.append(f"Plane Surface(1) = {{{loop_ids[0]}}};\n")
    else:
        outer_loop = loop_ids[0]
        holes = ", ".join(map(str, loop_ids[1:]))
        geo_text.append(f"Plane Surface(1) = {{{outer_loop}, {holes}}};\n")

    geo_text.append("\nPhysical Surface(\"domain\") = {1};\n")

    # === Assign inlet/outlet physical groups (clockwise: left → top → right → bottom) ===
    pipe_types_left = config.get('pipe_types_left', []) if config else []
    pipe_types_right = config.get('pipe_types_right', []) if config else []
    pipe_types_top = config.get('pipe_types_top', []) if config else []
    pipe_types_bottom = config.get('pipe_types_bottom', []) if config else []

    inlet_index = 1
    outlet_index = 1
    inlet_physical_groups = []   # [(index, [line_ids])]
    outlet_physical_groups = []
    assigned_lines = set()

    boundary_pipe_order = [
        ('left',   pipe_types_left),
        ('top',    pipe_types_top),
        ('right',  pipe_types_right),
        ('bottom', pipe_types_bottom),
    ]

    for bname, pipe_types in boundary_pipe_order:
        for pidx, ptype in enumerate(pipe_types):
            plids = pipe_line_ids.get((bname, pidx), [])
            if not plids:
                print(f"⚠ No boundary lines found for {bname} pipe {pidx} ({ptype})")
                continue
            if ptype == "inlet":
                inlet_physical_groups.append((inlet_index, plids))
                assigned_lines.update(plids)
                inlet_index += 1
            elif ptype == "outlet":
                outlet_physical_groups.append((outlet_index, plids))
                assigned_lines.update(plids)
                outlet_index += 1

    for idx, lids in inlet_physical_groups:
        lids_str = ", ".join(map(str, lids))
        geo_text.append(f"Physical Curve(\"inlet{idx}\") = {{{lids_str}}};\n")

    for idx, lids in outlet_physical_groups:
        lids_str = ", ".join(map(str, lids))
        geo_text.append(f"Physical Curve(\"outlet{idx}\") = {{{lids_str}}};\n")

    wall_lines = [lid for lid in sorted(geo_lines_data.keys()) if lid not in assigned_lines]
    if wall_lines:
        lines_str = ", ".join(map(str, wall_lines))
        geo_text.append(f"Physical Curve(\"wall\") = {{{lines_str}}};\n")

    with open(output_geo, 'w') as f:
        f.writelines(geo_text)

    # Summary
    left_count = sum(1 for bt in line_boundary_type.values() if bt == 'left')
    right_count = sum(1 for bt in line_boundary_type.values() if bt == 'right')
    top_count = sum(1 for bt in line_boundary_type.values() if bt == 'top')
    bottom_count = sum(1 for bt in line_boundary_type.values() if bt == 'bottom')

    print(f"✓ Geometry saved to {output_geo}")
    print(f"  Image size: {img_width} x {img_height} pixels")
    print(f"  Physical size: {phys_width} x {phys_height} units")
    print(f"  Scale: {scale_x:.6f} x {scale_y:.6f} units/pixel")
    print(f"  Boundary lines (after splitting): left={left_count}, top={top_count}, right={right_count}, bottom={bottom_count}")
    print(f"  Inlets found: {len(inlet_physical_groups)}")
    print(f"  Outlets found: {len(outlet_physical_groups)}")

# Called from runWorkflow.py — no standalone execution needed.
