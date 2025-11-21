"""
rhino_converters.py
-------------------
Conversion helpers between geometry.py Pydantic models and RhinoCommon types.
Uses dynamic import to allow running outside Rhino environments gracefully.
"""

import importlib
from schema.geometry import (
    Point3d, Vector3d, Line, Plane, Polyline, Circle, Arc, Mesh, NurbsSurface, PlaneSurface,
    NurbsCurve, PolylineCurve, Ellipse, Brep, Box, Rectangle3d, PointCloud,
    Transform, GeometryCollection
)
import numpy as np


def to_rhino(obj):
    """Converts Pydantic geometry models to Rhino.Geometry equivalents."""
    rg = importlib.import_module("Rhino.Geometry")

    if isinstance(obj, Point3d):
        return rg.Point3d(obj.x, obj.y, obj.z)
    elif isinstance(obj, Vector3d):
        return rg.Vector3d(obj.x, obj.y, obj.z)
    elif isinstance(obj, Line):
        return rg.Line(to_rhino(obj.from_point), to_rhino(obj.to_point))
    elif isinstance(obj, Plane):
        return rg.Plane(to_rhino(obj.origin), to_rhino(obj.x_axis), to_rhino(obj.y_axis))
    elif isinstance(obj, Polyline):
        return rg.Polyline([to_rhino(p) for p in obj.points])
    elif isinstance(obj, Circle):
        return rg.Circle(to_rhino(obj.plane), obj.radius)
    elif isinstance(obj, Arc):
        return rg.Arc(to_rhino(obj.start), to_rhino(obj.mid), to_rhino(obj.end))
    elif isinstance(obj, Mesh):
        mesh = rg.Mesh()
        for v in obj.vertices:
            mesh.Vertices.Add(v.x, v.y, v.z)
        for f in obj.faces:
            if len(f) == 3:
                mesh.Faces.AddFace(f[0], f[1], f[2])
            elif len(f) == 4:
                mesh.Faces.AddFace(f[0], f[1], f[2], f[3])
        mesh.Normals.ComputeNormals()
        mesh.Compact()
        return mesh
    elif isinstance(obj, NurbsSurface):
        u_order = obj.u_degree + 1
        v_order = obj.v_degree + 1
        surface = rg.NurbsSurface.Create(3, False, u_order, v_order, obj.u_count, obj.v_count)
        if not surface:
            raise ValueError("Failed to create NurbsSurface")

        # Set control points
        for i, row in enumerate(obj.control_points):
            for j, pt in enumerate(row):
                surface.Points.SetPoint(i, j, to_rhino(pt))

        # Use provided knots or uniform open defaults
        def assign_knots(knot_col, target_knots):
            count = target_knots.Count
            if knot_col:
                for i, val in enumerate(knot_col[:count]):
                    target_knots[i] = val
            else:
                for i in range(count):
                    target_knots[i] = i / (count - 1) if count > 1 else 0.0

        assign_knots(obj.u_knots, surface.KnotsU)
        assign_knots(obj.v_knots, surface.KnotsV)

        surface.SetDomain(0, rg.Interval(0.0, 1.0))
        surface.SetDomain(1, rg.Interval(0.0, 1.0))
        return surface

    elif isinstance(obj, PlaneSurface):
        plane = to_rhino(obj.plane)
        u_interval = rg.Interval(obj.u_min, obj.u_max)
        v_interval = rg.Interval(obj.v_min, obj.v_max)
        return rg.PlaneSurface(plane, u_interval, v_interval)
    elif isinstance(obj, NurbsCurve):
        curve = rg.NurbsCurve(3, False, obj.degree + 1, len(obj.control_points))
        for i, pt in enumerate(obj.control_points):
            curve.Points.SetPoint(i, pt.x, pt.y, pt.z)
        if obj.knots:
            for i, k in enumerate(obj.knots):
                curve.Knots[i] = k
        return curve
    elif isinstance(obj, PolylineCurve):
        return rg.PolylineCurve([to_rhino(p) for p in obj.points])
    elif isinstance(obj, Ellipse):
        return rg.Ellipse(to_rhino(obj.plane), obj.radius_x, obj.radius_y)
    elif isinstance(obj, Brep):
        # brep = rg.Brep()
        sub_breps = []

        for surf in obj.surfaces:
            srf_rh = to_rhino(surf)
            print(srf_rh)
            # Convert surface → brep
            surf_brep = rg.Brep.CreateFromSurface(srf_rh)
            print(surf_brep)
            if surf_brep:
                sub_breps.append(surf_brep)
            else:
                print(f"Failed to create Brep from surface {surf}")

        if not sub_breps:
            raise ValueError("No valid sub-breps created from surfaces")

        # If multiple Breps, try joining them into one
        if len(sub_breps) > 1:
            joined = rg.Brep.JoinBreps(sub_breps, 1e-6)
            print(joined)
            print(len(joined))
            if joined and len(joined) > 0:
                return joined
            else:
                print("Could not join Breps, returning list instead.")
                return sub_breps
        else:
            return sub_breps[0]
        
    elif isinstance(obj, Box):
        return rg.Box(to_rhino(obj.base_plane), obj.x_size, obj.y_size, obj.z_size)
    elif isinstance(obj, Rectangle3d):
        return rg.Rectangle3d(to_rhino(obj.plane), obj.width, obj.height)
    elif isinstance(obj, PointCloud):
        pc = rg.PointCloud()
        for i, pt in enumerate(obj.points):
            if obj.normals and i < len(obj.normals):
                n = obj.normals[i]
                pc.Add(pt.x, pt.y, pt.z, n.x, n.y, n.z)
            else:
                pc.Add(pt.x, pt.y, pt.z)
        return pc
    elif isinstance(obj, Transform):
        t = rg.Transform()
        for i in range(4):
            for j in range(4):
                t[i, j] = obj.matrix[i][j]
        return t
    elif isinstance(obj, GeometryCollection):
        return [to_rhino(g) for g in obj.objects]
    else:
        raise TypeError(f"Unsupported geometry type: {type(obj)}")
