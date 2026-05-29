"""
Master script to run the full SU2 validation workflow:
1. Convert topology image to .geo file
2. Mesh the geometry with Gmsh
3. Configure the SU2 analysis file
4. (Optional) Run SU2 simulation
"""

import subprocess
import sys
import os
import glob

# SU2 executable path
SU2_CFD_PATH = r"C:\Users\q661850\CAE\SU2-v8.4.0-win64\win64\bin\SU2_CFD.exe"


def run_step(description, func, *args, **kwargs):
    """Run a step and report status"""
    print(f"\n{'='*60}")
    print(f"STEP: {description}")
    print('='*60)
    
    try:
        func(*args, **kwargs)
        print(f"✓ {description} - COMPLETED")
        return True
    except Exception as e:
        print(f"✗ {description} - FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_pipeline(case_dir, run_su2=False, mesh_size=1.1, quads=False, boundary_layer=False, dilate=0):
    """
    Run the complete workflow.

    All input files (.png, config.json, topology_config.json, case.cfg)
    are expected inside *case_dir*.  The single .png found there is used
    as the geometry image, and its stem (filename without extension) is
    prepended to every output file.

    Args:
        case_dir:  Path to the case folder containing inputs.
        run_su2:   Whether to run SU2 simulation at the end.
    """
    case_dir = os.path.abspath(case_dir)
    if not os.path.isdir(case_dir):
        print(f"✗ Case directory not found: {case_dir}")
        return False

    # --- Auto-detect files inside case_dir ---
    png_files = glob.glob(os.path.join(case_dir, '*.png'))
    if len(png_files) == 0:
        print(f"✗ No .png file found in {case_dir}")
        return False
    if len(png_files) > 1:
        print(f"⚠ Multiple .png files found – using {os.path.basename(png_files[0])}")
    image_path = png_files[0]

    prefix = os.path.splitext(os.path.basename(image_path))[0]  # e.g. "ref"

    config_path          = os.path.join(case_dir, 'config.json')
    topology_config_path = os.path.join(case_dir, 'topology_config.json')
    # case.cfg is shared — always read from the scripts directory
    script_dir   = os.path.dirname(os.path.abspath(__file__))
    template_cfg = os.path.join(script_dir, 'case.cfg')

    for f in [config_path, topology_config_path, template_cfg]:
        if not os.path.exists(f):
            print(f"✗ Required file not found: {f}")
            return False

    # --- Build output paths (all inside case_dir, prefixed) ---
    geo_path  = os.path.join(case_dir, f'{prefix}_topology.geo')
    msh_path  = os.path.join(case_dir, f'{prefix}_topology.msh')
    su2_path  = os.path.join(case_dir, f'{prefix}_topology.su2')
    cfg_path  = os.path.join(case_dir, f'{prefix}_analysis2run.cfg')

    print("\n" + "="*60)
    print(f"SU2 VALIDATION WORKFLOW  –  {prefix}")
    print("="*60)

    # Step 1: Image to geometry
    from img2geo import topology_to_geometry
    success = run_step(
        "Convert image to geometry",
        topology_to_geometry,
        image_path,
        output_geo=geo_path,
        simplification=0.00000005,
        config_path=config_path,
        dilate=dilate,
    )
    if not success:
        return False

    # Step 2: Mesh generation
    from geo2mesh import mesh_geo
    # success = run_step(
    #     "Generate mesh",
    #     mesh_geo,
    #     geo_path, msh_path, su2_path,
    #     mesh_size=mesh_size, dim=2,
    # )
    success = run_step(
        "Generate mesh",
        mesh_geo,
        geo_path, msh_path, su2_path,
        mesh_size=mesh_size, dim=2,
        quads=quads,
        boundary_layer=boundary_layer,
        bl_first_layer=0.02,
        bl_growth=1.2,
        bl_thickness=0.5,
        bl_quads=True,
    )
    if not success:
        return False

    # Step 3: Configure analysis
    from config2analysis import config_to_analysis
    success = run_step(
        "Configure SU2 analysis",
        config_to_analysis,
        config_path, topology_config_path, template_cfg, cfg_path,
        file_prefix=prefix,
    )
    if not success:
        return False

    # Step 4: Run SU2 (optional)
    if run_su2:
        print(f"\n{'='*60}")
        print("STEP: Run SU2 simulation")
        print('='*60)

        if not os.path.exists(SU2_CFD_PATH):
            print(f"✗ SU2_CFD not found at: {SU2_CFD_PATH}")
            return False

        try:
            subprocess.run(
                [SU2_CFD_PATH, cfg_path],
                cwd=case_dir,
                check=True,
            )
            print("✓ SU2 simulation - COMPLETED")
        except subprocess.CalledProcessError as e:
            print(f"✗ SU2 simulation failed with code {e.returncode}")
            return False

    # Step 5: Plot pressure drop history
    from plot_history import plot_pressure_drop
    history_csv = os.path.join(case_dir, f'{prefix}_history.csv')
    output_png  = os.path.join(case_dir, f'{prefix}_pdrop.png')
    run_step(
        "Plot pressure drop history",
        plot_pressure_drop,
        history_csv,
        output_png=output_png,
    )

    print(f"\n{'='*60}")
    print("WORKFLOW COMPLETED SUCCESSFULLY")
    print("="*60)
    print(f"\nOutput files (in {case_dir}):")
    print(f"  - {prefix}_topology.geo")
    print(f"  - {prefix}_topology.msh")
    print(f"  - {prefix}_topology.su2")
    print(f"  - {prefix}_analysis2run.cfg")
    print(f"  - {prefix}_pdrop_history.png")

    return True


if __name__ == "__main__":
    run_pipeline(
        case_dir='ref_geom',
        run_su2=True,
        mesh_size=0.00082,
        boundary_layer=False,
        quads=False,
        dilate=5, # has to be integer
    )
