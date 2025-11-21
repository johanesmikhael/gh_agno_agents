"""
from_rhino.py
-------------------
Conversion helpers between RhinoCommon types and geometry.py Pydantic models.
This reverses rhino_converters.py, creating serializable Pydantic geometry
instances from live Rhino.Geometry objects.
"""

import importlib
from schema.geometry import (
    Point3d, Vector3d, Line, Plane, Polyline, Circle, Arc, Mesh, NurbsSurface, PlaneSurface, RevSurface,
    NurbsCurve, PolylineCurve, Ellipse, Brep, Box, Rectangle3d, PointCloud,
    Transform, GeometryCollection
)
import math


def from_rhino(obj):
    """Converts Rhino.Geometry objects into Pydantic geometry models."""
    rg = importlib.import_module("Rhino.Geometry")

    if isinstance(obj, rg.Point3d):
        return Point3d(x=obj.X, y=obj.Y, z=obj.Z)

    elif isinstance(obj, rg.Vector3d):
        return Vector3d(x=obj.X, y=obj.Y, z=obj.Z)

    elif isinstance(obj, rg.Line):
        return Line(
            from_point=from_rhino(obj.From),
            to_point=from_rhino(obj.To)
        )
    
    elif isinstance(obj, rg.LineCurve):
    # Try to extract the underlying line geometry
        line = obj.Line
        return Line(
            from_point=from_rhino(line.From),
            to_point=from_rhino(line.To)
        )

    elif isinstance(obj, rg.Plane):
        return Plane(
            origin=from_rhino(obj.Origin),
            x_axis=from_rhino(obj.XAxis),
            y_axis=from_rhino(obj.YAxis)
        )

    elif isinstance(obj, rg.Polyline):
        return Polyline(points=[from_rhino(p) for p in obj])

    elif isinstance(obj, rg.Circle):
        return Circle(
            plane=from_rhino(obj.Plane),
            radius=obj.Radius
        )

    elif isinstance(obj, rg.Arc):
        return Arc(
            start=from_rhino(obj.StartPoint),
            mid=from_rhino(obj.MidPoint),
            end=from_rhino(obj.EndPoint)
        )
    elif isinstance(obj, rg.ArcCurve):
        # ArcCurve can represent arcs or circles
        if obj.IsCircle():
            success, circle = obj.TryGetCircle()
            if success:
                return Circle(
                    plane=from_rhino(circle.Plane),
                    radius=circle.Radius
                )
        elif obj.IsArc():
            success, arc = obj.TryGetArc()
            if success:
                return Arc(
                    start=from_rhino(arc.StartPoint),
                    mid=from_rhino(arc.MidPoint),
                    end=from_rhino(arc.EndPoint)
                )
        # If neither, fall through to NurbsCurve conversion
        success, nurbs = obj.TryGetNurbsCurve()
        if success:
            return from_rhino(nurbs)
        else:
            raise TypeError(f"Unsupported ArcCurve shape: {obj}")


    elif isinstance(obj, rg.Mesh):
        vertices = [from_rhino(v) for v in obj.Vertices.ToPoint3dArray()]
        faces = []
        for i in range(obj.Faces.Count):
            f = obj.Faces[i]
            if f.IsTriangle:
                faces.append([f.A, f.B, f.C])
            else:
                faces.append([f.A, f.B, f.C, f.D])
        return Mesh(vertices=vertices, faces=faces)

    elif isinstance(obj, rg.NurbsSurface):
        u_count = obj.Points.CountU
        v_count = obj.Points.CountV
        control_points = [
            [from_rhino(obj.Points.GetPoint(u, v)[1]) for v in range(v_count)]
            for u in range(u_count)
        ]

            # Extract degrees
        u_degree = obj.Degree(0)
        v_degree = obj.Degree(1)

        # Extract optional knot vectors
        u_knots = [obj.KnotsU[k] for k in range(obj.KnotsU.Count)]
        v_knots = [obj.KnotsV[k] for k in range(obj.KnotsV.Count)]


        return NurbsSurface(
            u_count=u_count,
            v_count=v_count,
            u_degree=u_degree,
            v_degree=v_degree,
            u_knots=u_knots,
            v_knots=v_knots,
            control_points=control_points,
        )

    elif isinstance(obj, rg.NurbsCurve):
        degree = obj.Degree
        control_points = [from_rhino(pt.Location) for pt in obj.Points]
        knots = [obj.Knots[i] for i in range(obj.Knots.Count)]
        return NurbsCurve(degree=degree, control_points=control_points, knots=knots)
    
    elif isinstance(obj, rg.PlaneSurface):
        # Extract the surface plane and UV domains
        u_dom = obj.Domain(0)
        v_dom = obj.Domain(1)

        # Get the four corner points of the surface
        p00 = obj.PointAt(u_dom.T0, v_dom.T0)
        p10 = obj.PointAt(u_dom.T1, v_dom.T0)
        p11 = obj.PointAt(u_dom.T1, v_dom.T1)
        p01 = obj.PointAt(u_dom.T0, v_dom.T1)

        # Construct plane from first corner + axes along the edges
        x_axis_vec = rg.Vector3d(p10 - p00)
        y_axis_vec = rg.Vector3d(p01 - p00)
        base_plane = rg.Plane(p00, x_axis_vec, y_axis_vec)

        # Compute the actual world distances along U and V directions
        u_size = x_axis_vec.Length
        v_size = y_axis_vec.Length

        return PlaneSurface(
            plane=from_rhino(base_plane),
            u_min=0.0,
            u_max=u_size,
            v_min=0.0,
            v_max=v_size
        )
    
    elif isinstance(obj, rg.RevSurface):
        # Surface of revolution (Revolved surface)
        axis = obj.Axis
        start_angle = getattr(obj, "AngleStart", 0.0)
        end_angle = getattr(obj, "AngleEnd", 2 * math.pi)

        # RhinoCommon compatibility — different Rhino versions expose profile differently
        profile = None
        if hasattr(obj, "ProfileCurve"):
            try:
                profile = obj.ProfileCurve()
            except:
                pass
        if profile is None and hasattr(obj, "RevoluteCurve"):
            try:
                profile = obj.RevoluteCurve()
            except:
                pass
        if profile is None:
            # As a fallback, convert the surface itself to a NURBS representation
            nurbs = obj.ToNurbsSurface()
            return from_rhino(nurbs)

        return RevSurface(
            axis=from_rhino(axis),
            profile=from_rhino(profile),
            start_angle=start_angle,
            end_angle=end_angle
        )


    elif isinstance(obj, rg.PolylineCurve):
        polyline = obj.ToPolyline()
        return PolylineCurve(points=[from_rhino(p) for p in polyline])

    elif isinstance(obj, rg.Ellipse):
        return Ellipse(
            plane=from_rhino(obj.Plane),
            radius_x=obj.Radius1,
            radius_y=obj.Radius2
        )

    elif isinstance(obj, rg.Brep):
        surfaces = []
        for s in obj.Surfaces:
            print(s)
            surfaces.append(from_rhino(s))
        edges = []
        for e in obj.Edges:
            edges.append(from_rhino(e.EdgeCurve))
        return Brep(surfaces=surfaces, edges=edges)

    elif isinstance(obj, rg.Box):
        return Box(
            base_plane=from_rhino(obj.Plane),
            x_size=obj.X[1] - obj.X[0],
            y_size=obj.Y[1] - obj.Y[0],
            z_size=obj.Z[1] - obj.Z[0]
        )

    elif isinstance(obj, rg.Rectangle3d):
        return Rectangle3d(
            plane=from_rhino(obj.Plane),
            width=obj.Width,
            height=obj.Height
        )

    elif isinstance(obj, rg.PointCloud):
        pts = [from_rhino(p.Location) for p in obj]
        normals = [from_rhino(p.Normal) for p in obj if p.HasNormal]
        return PointCloud(points=pts, normals=normals if normals else None)

    elif isinstance(obj, rg.Transform):
        matrix = [[obj[i, j] for j in range(4)] for i in range(4)]
        return Transform(matrix=matrix)

    elif isinstance(obj, list) and all(hasattr(o, "GeometryType") for o in obj):
        # Rhino collections
        return GeometryCollection(objects=[from_rhino(o) for o in obj])

    else:
        raise TypeError(f"Unsupported Rhino geometry type: {type(obj)}")
