import json
import re

def config_to_analysis(config_path='config.json', topology_config_path='topology_config.json', 
                       template_cfg='case.cfg', output_cfg='case_configured.cfg',
                       file_prefix=None, use_massflowint=False):
    """
    Update SU2 case.cfg based on config.json and topology_config.json
    
    Args:
        config_path: Path to geometry config with pipe types
        topology_config_path: Path to topology config with viscosity/density
        template_cfg: Template case.cfg file
        output_cfg: Output configured .cfg file
        file_prefix: If set, prefix all SU2 I/O filenames (mesh, restart, history, volume, surface)
        use_massflowint: If True, compute phigh/plow via MassFlowInt ratios instead of MassFlowAvg (default: False)
    """
    
    # Load configs
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    with open(topology_config_path, 'r') as f:
        topo_config = json.load(f)
    
    # Get pipe types from each boundary
    pipe_types_left = config.get('pipe_types_left', [])
    pipe_types_right = config.get('pipe_types_right', [])
    pipe_types_top = config.get('pipe_types_top', [])
    pipe_types_bottom = config.get('pipe_types_bottom', [])
    
    # Direction vectors (inward-pointing normals)
    direction_left = (1.0, 0.0, 0.0)    # Left wall, inward = +x
    direction_right = (-1.0, 0.0, 0.0)  # Right wall, inward = -x
    direction_top = (0.0, -1.0, 0.0)    # Top wall, inward = -y
    direction_bottom = (0.0, 1.0, 0.0)  # Bottom wall, inward = +y
    
    # Collect inlets and outlets in clockwise order: left -> top -> right -> bottom
    inlets = []  # List of (index, direction_tuple)
    outlets = []  # List of index
    
    inlet_idx = 1
    outlet_idx = 1
    
    # Left boundary
    for pipe_type in pipe_types_left:
        if pipe_type == "inlet":
            inlets.append((inlet_idx, direction_left))
            inlet_idx += 1
        elif pipe_type == "outlet":
            outlets.append(outlet_idx)
            outlet_idx += 1
    
    # Top boundary
    for pipe_type in pipe_types_top:
        if pipe_type == "inlet":
            inlets.append((inlet_idx, direction_top))
            inlet_idx += 1
        elif pipe_type == "outlet":
            outlets.append(outlet_idx)
            outlet_idx += 1
    
    # Right boundary
    for pipe_type in pipe_types_right:
        if pipe_type == "inlet":
            inlets.append((inlet_idx, direction_right))
            inlet_idx += 1
        elif pipe_type == "outlet":
            outlets.append(outlet_idx)
            outlet_idx += 1
    
    # Bottom boundary
    for pipe_type in pipe_types_bottom:
        if pipe_type == "inlet":
            inlets.append((inlet_idx, direction_bottom))
            inlet_idx += 1
        elif pipe_type == "outlet":
            outlets.append(outlet_idx)
            outlet_idx += 1
    
    num_inlets = len(inlets)
    num_outlets = len(outlets)
    
    # Read template cfg and detect turbulence model + parameters from comments
    with open(template_cfg, 'r') as f:
        cfg_content = f.read()

    # Detect turbulence model (SA or SST)
    turb_model_match = re.search(
        r'^\s*KIND_TURB_MODEL\s*=\s*([A-Za-z0-9_]+)',
        cfg_content,
        flags=re.MULTILINE
    )
    turb_model = turb_model_match.group(1).strip().upper() if turb_model_match else 'SST'

    # SST defaults
    turb_intensity = '0.05'
    turb_visc_ratio = '10.0'
    # SA default
    sa_nu_factor = '3e-4'

    # SST-style comment: % turbulence_intensity = <val>, turb_to_lam_visc_ratio = <val>
    turb_match = re.search(
        r'%\s*turbulence_intensity\s*=\s*([0-9eE+\-.]+)\s*,\s*turb_to_lam_visc_ratio\s*=\s*([0-9eE+\-.]+)',
        cfg_content
    )
    if turb_match:
        turb_intensity = turb_match.group(1)
        turb_visc_ratio = turb_match.group(2)

    # SA-style comment: % Nu = <val>
    nu_match = re.search(
        r'%\s*Nu\s*=\s*([0-9eE+\-.]+)',
        cfg_content
    )
    if nu_match:
        sa_nu_factor = nu_match.group(1)

    # Build INC_INLET_TYPE line
    inc_inlet_type = "INC_INLET_TYPE= " + ", ".join(["VELOCITY_INLET"] * num_inlets)
    
    # Build MARKER_INLET line
    # Format: (inlet1, 300.0, 1.0, dx, dy, dz, inlet2, 300.0, 1.0, dx, dy, dz, ...)
    marker_inlet_parts = []
    for idx, direction in inlets:
        dx, dy, dz = direction
        marker_inlet_parts.append(f"inlet{idx}, 300.0, 1.0, {dx}, {dy}, {dz}")
    marker_inlet = "MARKER_INLET= (" + ", ".join(marker_inlet_parts) + ")"
    
    # Build INC_OUTLET_TYPE line
    inc_outlet_type = "INC_OUTLET_TYPE= " + ", ".join(["PRESSURE_OUTLET"] * num_outlets)
    
    # Build MARKER_OUTLET line
    # Format: (outlet1, 0.0, outlet2, 0.0, ...)
    marker_outlet_parts = [f"outlet{idx}, 0.0" for idx in outlets]
    marker_outlet = "MARKER_OUTLET= ( " + ", ".join(marker_outlet_parts) + " )"
    
    # Build MARKER_INLET_TURBULENT line depending on turbulence model
    if turb_model == 'SA':
        # SA format: (inlet1, NuFactor1, inlet2, NuFactor2, ...)
        marker_turb_parts = [f"inlet{idx}, {sa_nu_factor}" for idx, _ in inlets]
    else:
        # SST (and fallback) format: (inlet1, turb_intensity, turb_to_lam_visc_ratio, ...)
        marker_turb_parts = [f"inlet{idx}, {turb_intensity}, {turb_visc_ratio}" for idx, _ in inlets]
    marker_inlet_turbulent = "MARKER_INLET_TURBULENT= ( " + ", ".join(marker_turb_parts) + " )"

    # Build MARKER_PLOTTING line from detected inlets/outlets + wall
    inlet_markers = [f"inlet{idx}" for idx, _ in inlets]
    outlet_markers = [f"outlet{idx}" for idx in outlets]
    marker_plotting = "MARKER_PLOTTING= ( " + ", ".join(inlet_markers + outlet_markers + ["wall"]) + " )"

    # Output files for surface/volume Paraview (.vtu)
    output_files = "OUTPUT_FILES= ( PARAVIEW, SURFACE_PARAVIEW )"

    # Build CUSTOM_OUTPUTS for pressure drop
    custom_parts = []
    # Dynamic pressure macro and total pressure (STARCCM+ convention)
    custom_parts.append("pDyna : Macro{0.5*DENSITY*(pow(VELOCITY_X,2) + pow(VELOCITY_Y,2))}")
    custom_parts.append("p_starccm : Macro{PRESSURE + $pDyna}")

    # Static and dynamic pressure averages (always included)
    inlet_marker_list = ",".join([f"inlet{idx}" for idx, _ in inlets])
    outlet_marker_list = ",".join([f"outlet{idx}" for idx in outlets])

    if inlets:
        custom_parts.append(f"pstatic_in : MassFlowAvg{{PRESSURE}}[{inlet_marker_list}]")
        custom_parts.append(f"pdyn_in : MassFlowAvg{{$pDyna}}[{inlet_marker_list}]")
    if outlets:
        custom_parts.append(f"pstatic_out : MassFlowAvg{{PRESSURE}}[{outlet_marker_list}]")
        custom_parts.append(f"pdyn_out : MassFlowAvg{{$pDyna}}[{outlet_marker_list}]")

    # Per-marker static/dynamic pressure breakdowns
    for idx, _ in inlets:
        custom_parts.append(f"pstatic_in{idx} : MassFlowAvg{{PRESSURE}}[inlet{idx}]")
        custom_parts.append(f"pdyn_in{idx} : MassFlowAvg{{$pDyna}}[inlet{idx}]")
    for idx in outlets:
        custom_parts.append(f"pdyn_out{idx} : MassFlowAvg{{$pDyna}}[outlet{idx}]")

    if use_massflowint:
        # MassFlowInt approach: phigh = sum(MassFlowInt{p}[inlet_i]) / sum(MassFlowInt{1}[inlet_i])
        inlet_num_terms = []
        inlet_den_terms = []
        for idx, _ in inlets:
            num_name = f"in_num{idx}"
            den_name = f"in_den{idx}"
            custom_parts.append(f"{num_name} : MassFlowInt{{$p_starccm}}[inlet{idx}]")
            custom_parts.append(f"{den_name} : MassFlowInt{{1}}[inlet{idx}]")
            inlet_num_terms.append(num_name)
            inlet_den_terms.append(den_name)

        outlet_num_terms = []
        outlet_den_terms = []
        for idx in outlets:
            num_name = f"out_num{idx}"
            den_name = f"out_den{idx}"
            custom_parts.append(f"{num_name} : MassFlowInt{{$p_starccm}}[outlet{idx}]")
            custom_parts.append(f"{den_name} : MassFlowInt{{1}}[outlet{idx}]")
            outlet_num_terms.append(num_name)
            outlet_den_terms.append(den_name)

        if inlet_num_terms and inlet_den_terms:
            phigh_expr = f"({'+'.join(inlet_num_terms)})/({'+'.join(inlet_den_terms)})"
            custom_parts.append(f"phigh : Function{{{phigh_expr}}}")
        else:
            custom_parts.append("phigh : Function{0.0}")

        if outlet_num_terms and outlet_den_terms:
            plow_expr = f"({'+'.join(outlet_num_terms)})/({'+'.join(outlet_den_terms)})"
            custom_parts.append(f"plow : Function{{{plow_expr}}}")
        else:
            custom_parts.append("plow : Function{0.0}")

        mflow_in_expr = f"({'+'.join(inlet_den_terms)})"
        custom_parts.append(f"mflow_in : Function{{{mflow_in_expr}}}")

        mflow_out_expr = f"({'+'.join(outlet_den_terms)})"
        custom_parts.append(f"mflow_out : Function{{{mflow_out_expr}}}")
    else:
        # MassFlowAvg approach: phigh/plow computed directly via MassFlowAvg
        if inlets:
            custom_parts.append(f"phigh : MassFlowAvg{{$p_starccm}}[{inlet_marker_list}]")
        else:
            custom_parts.append("phigh : Function{0.0}")

        if outlets:
            custom_parts.append(f"plow : MassFlowAvg{{$p_starccm}}[{outlet_marker_list}]")
        else:
            custom_parts.append("plow : Function{0.0}")

        # Mass flow tracking via MassFlowInt{1} per marker
        inlet_den_terms = []
        for idx, _ in inlets:
            den_name = f"in_den{idx}"
            custom_parts.append(f"{den_name} : MassFlowInt{{1}}[inlet{idx}]")
            inlet_den_terms.append(den_name)

        outlet_den_terms = []
        for idx in outlets:
            den_name = f"out_den{idx}"
            custom_parts.append(f"{den_name} : MassFlowInt{{1}}[outlet{idx}]")
            outlet_den_terms.append(den_name)

        mflow_in_expr = f"({'+'.join(inlet_den_terms)})" if inlet_den_terms else "0.0"
        custom_parts.append(f"mflow_in : Function{{{mflow_in_expr}}}")

        mflow_out_expr = f"({'+'.join(outlet_den_terms)})" if outlet_den_terms else "0.0"
        custom_parts.append(f"mflow_out : Function{{{mflow_out_expr}}}")

    custom_parts.append("pdrop : Function{phigh-plow}")
    custom_outputs_value = ";\\\n                 ".join(custom_parts) + ";"
    custom_outputs = f"CUSTOM_OUTPUTS= '{custom_outputs_value}'"

    # Build SCREEN_OUTPUT with pdrop
    screen_output = "SCREEN_OUTPUT= ( INNER_ITER, RMS_VELOCITY-X, mflow_in, mflow_out, phigh, plow, pdrop )"
    
    # Get viscosity and density from topology config
    viscosity = topo_config.get('viscosity', 1.0e-3)
    density = topo_config.get('density', 1.0)

    # Replace lines using regex
    # INC_INLET_TYPE
    cfg_content = re.sub(
        r'^INC_INLET_TYPE=.*$',
        inc_inlet_type,
        cfg_content,
        flags=re.MULTILINE
    )
    
    # MARKER_INLET (not MARKER_INLET_TURBULENT)
    cfg_content = re.sub(
        r'^MARKER_INLET=.*$',
        marker_inlet,
        cfg_content,
        flags=re.MULTILINE
    )
    
    # INC_OUTLET_TYPE
    cfg_content = re.sub(
        r'^INC_OUTLET_TYPE=.*$',
        inc_outlet_type,
        cfg_content,
        flags=re.MULTILINE
    )
    
    # MARKER_OUTLET
    cfg_content = re.sub(
        r'^MARKER_OUTLET=.*$',
        marker_outlet,
        cfg_content,
        flags=re.MULTILINE
    )
    
    # MARKER_INLET_TURBULENT
    cfg_content = re.sub(
        r'^MARKER_INLET_TURBULENT=.*$',
        marker_inlet_turbulent,
        cfg_content,
        flags=re.MULTILINE
    )
    
    # MU_CONSTANT
    cfg_content = re.sub(
        r'^MU_CONSTANT=.*$',
        f'MU_CONSTANT= {viscosity}',
        cfg_content,
        flags=re.MULTILINE
    )
    
    # INC_DENSITY_INIT
    cfg_content = re.sub(
        r'^INC_DENSITY_INIT=.*$',
        f'INC_DENSITY_INIT= {density}',
        cfg_content,
        flags=re.MULTILINE
    )

    # CUSTOM_OUTPUTS (multi-line in template, replace with generated single-line)
    cfg_content = re.sub(
        r"CUSTOM_OUTPUTS=\s*'[^']*'",
        custom_outputs,
        cfg_content,
        flags=re.DOTALL
    )

    # SCREEN_OUTPUT
    cfg_content = re.sub(
        r'^SCREEN_OUTPUT=.*$',
        screen_output,
        cfg_content,
        flags=re.MULTILINE
    )

    # Remove deprecated surface output options if present
    cfg_content = re.sub(r'^SURFACE_OUTPUT=.*$\n?', '', cfg_content, flags=re.MULTILINE)
    cfg_content = re.sub(r'^SURFACE_OUTPUT_FILES=.*$\n?', '', cfg_content, flags=re.MULTILINE)

    # OUTPUT_FILES
    if re.search(r'^OUTPUT_FILES=.*$', cfg_content, flags=re.MULTILINE):
        cfg_content = re.sub(
            r'^OUTPUT_FILES=.*$',
            output_files,
            cfg_content,
            flags=re.MULTILINE
        )
    else:
        cfg_content += "\n" + output_files

    # MARKER_PLOTTING
    if re.search(r'^MARKER_PLOTTING=.*$', cfg_content, flags=re.MULTILINE):
        cfg_content = re.sub(
            r'^MARKER_PLOTTING=.*$',
            marker_plotting,
            cfg_content,
            flags=re.MULTILINE
        )
    else:
        cfg_content += "\n" + marker_plotting
    
    # Prefix SU2 I/O filenames if requested
    if file_prefix:
        su2_file_options = {
            'MESH_FILENAME': f'{file_prefix}_topology.su2',
            'RESTART_FILENAME': f'{file_prefix}_restart',
            'CONV_FILENAME': f'{file_prefix}_history',
            'VOLUME_FILENAME': f'{file_prefix}_vol_solution',
            'SURFACE_FILENAME': f'{file_prefix}_surface',
        }
        for key, value in su2_file_options.items():
            if re.search(rf'^{key}=.*$', cfg_content, flags=re.MULTILINE):
                cfg_content = re.sub(
                    rf'^{key}=.*$',
                    f'{key}= {value}',
                    cfg_content,
                    flags=re.MULTILINE,
                )
            else:
                cfg_content += f'\n{key}= {value}'

    # Write output cfg
    with open(output_cfg, 'w') as f:
        f.write(cfg_content)
    
    print(f"✓ Configuration saved to {output_cfg}")
    print(f"  Inlets: {num_inlets}")
    print(f"  Outlets: {num_outlets}")
    print(f"  Density: {density}")
    print(f"  Viscosity: {viscosity}")


# Called from runWorkflow.py — no standalone execution needed.
