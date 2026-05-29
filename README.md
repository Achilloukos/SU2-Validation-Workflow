# SU2-Validation-Workflow

Python scripts that combine OpenCV for creating a geometry file out of a final topology, Gmsh for meshing, and SU2 simulation template file editing, to form an open-source workflow for validating topology optimization results.

## Project Structure

- 2 `.json` config files for the geometry/physics.
- 1 template `case.cfg` file for setting up everything regarding the numerics of the SU2 CFD simulation.
- 6 Python scripts:

| Script | Description |
|--------|-------------|
| `csv2img.py` | If needed, reads the `.csv` output of STAR-CCM+ and translates it to a final topology `.png`. |
| `img2geo.py` | Topology → geometry (`.geo`) |
| `geo2mesh.py` | Geometry → mesh (`.su2`) |
| `config2analysis.py` | Geometry/physics configs → `.cfg` file for CFD setup |
| `plot_history.py` | Plots the Pressure Drop vs Iterations history and stores the plot as .png inside the case directory. |
| `runWorkflow.py` | Runs everything sequentially and calls SU2 in the terminal. |

## **HOW TO USE**

1. Install [SU2](https://su2code.github.io/) and set the full path of its `SU2_CFD.exe` in `runWorkflow.py`.

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   For BMW internal network, use the Nexus mirror:
   ```bash
   pip install -r requirements.txt -i https://nexus.bmwgroup.net/repository/pypi/simple
   ```

3. Create a folder called `prefix_geom` (where `prefix` is a name for the case) and place inside it your case's final topology `.png`, along with the `config.json` and `topology_config.json` files.

4. All solver settings (CFL number, wall functions, max iterations, convergence criteria) must be set in the `case.cfg` file located in the parent directory alongside the Python scripts. This serves as a template for the final `.cfg` files created inside each case folder.

5. Set up the main workflow settings (directory with geometry, global mesh settings) in the final lines of `runWorkflow.py`, as arguments in the call to `run_pipeline()`. Run the script and wait patiently.

## Miscellaneous

- **Geometry dilation** — The workflow supports morphological dilation of the topology image before geometry extraction. This pushes back and smooths the black boundary. Set the `dilate` parameter in `run_pipeline()` to an odd kernel size (e.g. 3, 5, 7) to enable it.
- **Boundary layer mesh** *(experimental)* — There is an option to generate a boundary layer mesh. This feature is still experimental and may not work reliably for all geometries.

