import gmsh


def mesh_geo(
    geo_path,
    msh_path="mesh.msh",
    su2_path="mesh.su2",
    mesh_size=None,
    dim=2,
    quads=False,
    boundary_layer=False,
    wall_group_name="wall",
    bl_first_layer=0.1,
    bl_growth=1.2,
    bl_thickness=1.0,
    bl_quads=False,
):
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1)

    try:
        # Load the .geo
        gmsh.open(geo_path)

        # Global sizing:
        # - keep original behavior if no BL
        # - if BL is on, only cap max size so BL first layer can be smaller
        if mesh_size is not None:
            if boundary_layer:
                gmsh.option.setNumber("Mesh.CharacteristicLengthMax", mesh_size)
            else:
                gmsh.option.setNumber("Mesh.CharacteristicLengthMin", mesh_size)
                gmsh.option.setNumber("Mesh.CharacteristicLengthMax", mesh_size)

        # Optional boundary layer on curves in Physical Curve("wall")
        if boundary_layer and dim == 2:
            wall_curve_tags = []
            for phys_dim, phys_tag in gmsh.model.getPhysicalGroups():
                if phys_dim != 1:
                    continue
                name = gmsh.model.getPhysicalName(phys_dim, phys_tag)
                if name == wall_group_name:
                    wall_curve_tags.extend(
                        gmsh.model.getEntitiesForPhysicalGroup(phys_dim, phys_tag)
                    )

            # Deduplicate while preserving order
            wall_curve_tags = list(dict.fromkeys(wall_curve_tags))

            if wall_curve_tags:
                bl_field = gmsh.model.mesh.field.add("BoundaryLayer")
                gmsh.model.mesh.field.setNumbers(bl_field, "CurvesList", wall_curve_tags)
                gmsh.model.mesh.field.setNumber(bl_field, "Size", bl_first_layer)
                gmsh.model.mesh.field.setNumber(bl_field, "Ratio", bl_growth)
                gmsh.model.mesh.field.setNumber(bl_field, "Thickness", bl_thickness)
                gmsh.model.mesh.field.setNumber(bl_field, "Quads", 1 if bl_quads else 0)
                gmsh.model.mesh.field.setAsBoundaryLayer(bl_field)

                print(
                    f"✓ Boundary layer enabled on {len(wall_curve_tags)} wall curve(s): "
                    f"first={bl_first_layer}, growth={bl_growth}, thickness={bl_thickness}"
                )
            else:
                print(
                    f"⚠ boundary_layer=True but no Physical Curve(\"{wall_group_name}\") curves found"
                )

        elif boundary_layer and dim != 2:
            print("⚠ BoundaryLayer field path currently configured for 2D curves only.")

        # Recombine into quads if requested
        if quads and dim == 2:
            gmsh.option.setNumber("Mesh.RecombineAll", 1)
            gmsh.option.setNumber("Mesh.Algorithm", 8)  # Frontal-Delaunay for Quads

        # Generate mesh
        gmsh.model.mesh.generate(dim)

        # Write mesh outputs
        if msh_path:
            gmsh.write(msh_path)
        if su2_path:
            gmsh.write(su2_path)

    finally:
        gmsh.finalize()

    if msh_path:
        print(f"✓ Wrote mesh to {msh_path}")
    if su2_path:
        print(f"✓ Wrote mesh to {su2_path}")

# def mesh_geo(geo_path, msh_path="mesh.msh", su2_path="mesh.su2", mesh_size=None, dim=2):
#     gmsh.initialize()
#     gmsh.option.setNumber("General.Terminal", 1)

#     # Load the .geo
#     gmsh.open(geo_path)

#     # Optional: override mesh size globally
#     if mesh_size is not None:
#         gmsh.option.setNumber("Mesh.CharacteristicLengthMin", mesh_size)
#         gmsh.option.setNumber("Mesh.CharacteristicLengthMax", mesh_size)

#     # Generate mesh
#     gmsh.model.mesh.generate(dim)

#     # Write mesh outputs
#     if msh_path:
#         gmsh.write(msh_path)
#     if su2_path:
#         gmsh.write(su2_path)

#     gmsh.finalize()
#     if msh_path:
#         print(f"✓ Wrote mesh to {msh_path}")
#     if su2_path:
#         print(f"✓ Wrote mesh to {su2_path}")

# # Called from runWorkflow.py — no standalone execution needed.
