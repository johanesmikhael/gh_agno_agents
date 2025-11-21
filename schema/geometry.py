"""
geometry.py
------------------
Structured Pydantic geometry models for Rhino/Grasshopper AI agent integration.

This unified schema covers base and extended RhinoCommon geometry types:
Points, Vectors, Curves, Surfaces, Meshes, Breps, Boxes, and Point Clouds.

All units are in meters. Conversion to RhinoCommon types is handled separately
in rhino_converters.py to maintain environment independence.

Author: (your name)
"""

from __future__ import annotations
from pydantic import BaseModel, Field, model_validator
from typing import List, Literal, Optional, Union


# ------------------------------------------------------------------------------
# Base class
# ------------------------------------------------------------------------------

class Geometry(BaseModel):
    """Base class for all geometry types."""
    type: str = Field(..., description="Geometry type identifier")
    id: Optional[str] = Field(None, description="Optional name or label")


    @model_validator(mode="after")
    def round_floats(cls, values):
        """Round all float values in the model (recursively) to 2 decimal places."""
        def round_recursive(obj):
            if isinstance(obj, float):
                return round(obj, 2)
            elif isinstance(obj, list):
                return [round_recursive(v) for v in obj]
            elif isinstance(obj, dict):
                return {k: round_recursive(v) for k, v in obj.items()}
            return obj

        return round_recursive(values)

    class Config:
        frozen = True
        extra = "forbid"


# ------------------------------------------------------------------------------
# Core Primitives
# ------------------------------------------------------------------------------

class Point3d(Geometry):
    """3D point in Cartesian coordinates (meters)."""
    type: Literal["Point3d"] = "Point3d"
    x: float
    y: float
    z: float


class Vector3d(Geometry):
    """3D vector in Cartesian coordinates (meters)."""
    type: Literal["Vector3d"] = "Vector3d"
    x: float
    y: float
    z: float


class Line(Geometry):
    """Straight line between two 3D points."""
    type: Literal["Line"] = "Line"
    from_point: Point3d
    to_point: Point3d


class Plane(Geometry):
    """Plane defined by origin and orthogonal axes."""
    type: Literal["Plane"] = "Plane"
    origin: Point3d
    x_axis: Vector3d
    y_axis: Vector3d


class Polyline(Geometry):
    """Polyline defined by a sequence of connected 3D points."""
    type: Literal["Polyline"] = "Polyline"
    points: List[Point3d]


class Circle(Geometry):
    """Circle defined by a plane and radius."""
    type: Literal["Circle"] = "Circle"
    plane: Plane
    radius: float = Field(..., gt=0)


class Arc(Geometry):
    """Arc defined by start, mid, and end points."""
    type: Literal["Arc"] = "Arc"
    start: Point3d
    mid: Point3d
    end: Point3d


# ------------------------------------------------------------------------------
# Surfaces and Meshes
# ------------------------------------------------------------------------------

class Mesh(Geometry):
    """Triangle or quad mesh."""
    type: Literal["Mesh"] = "Mesh"
    vertices: List[Point3d]
    faces: List[List[int]]  # supports triangles or quads


class NurbsSurface(Geometry):
    """Simplified NURBS surface model."""
    type: Literal["NurbsSurface"] = "NurbsSurface"
    u_count: int
    v_count: int
    control_points: List[List[Point3d]]
    # Optional explicit degrees, default cubic
    u_degree: int = Field(3, ge=1, description="Degree of the surface in U direction (default 3).")
    v_degree: int = Field(3, ge=1, description="Degree of the surface in V direction (default 3).")

    # Optional knot vectors
    u_knots: Optional[List[float]] = Field(
        None, description="Optional U-direction knot vector"
    )
    v_knots: Optional[List[float]] = Field(
        None, description="Optional V-direction knot vector"
    )


class PlaneSurface(Geometry):
    """Rectangular surface defined by a base plane and UV extents."""
    type: Literal["PlaneSurface"] = "PlaneSurface"
    plane: Plane = Field(..., description="Base plane defining the surface orientation.")
    u_min: float = Field(..., description="Lower bound of the U parameter domain.")
    u_max: float = Field(..., description="Upper bound of the U parameter domain.")
    v_min: float = Field(..., description="Lower bound of the V parameter domain.")
    v_max: float = Field(..., description="Upper bound of the V parameter domain.")


class RevSurface(Geometry):
    """Surface of revolution defined by a profile curve and an axis."""
    type: Literal["RevSurface"] = "RevSurface"
    axis: Line = Field(..., description="Axis of revolution represented as a line.")
    profile: NurbsCurve = Field(..., description="Profile curve revolved around the axis.")
    start_angle: float = Field(..., description="Start angle of the revolution, in radians.")
    end_angle: float = Field(..., description="End angle of the revolution, in radians.")


# ------------------------------------------------------------------------------
# Curves (Extended)
# ------------------------------------------------------------------------------

class NurbsCurve(Geometry):
    """NURBS curve defined by degree, control points, and optional knots."""
    type: Literal["NurbsCurve"] = "NurbsCurve"
    degree: int = Field(..., ge=1)
    control_points: List[Point3d]
    knots: Optional[List[float]] = Field(None, description="Optional knot vector")


class PolylineCurve(Geometry):
    """Polyline curve representation."""
    type: Literal["PolylineCurve"] = "PolylineCurve"
    points: List[Point3d]


class Ellipse(Geometry):
    """Ellipse defined by a plane and two radii."""
    type: Literal["Ellipse"] = "Ellipse"
    plane: Plane
    radius_x: float = Field(..., gt=0)
    radius_y: float = Field(..., gt=0)


# ------------------------------------------------------------------------------
# Solids and Composite Geometry
# ------------------------------------------------------------------------------

class Brep(Geometry):
    """Simplified boundary representation (Brep)."""
    type: Literal["Brep"] = "Brep"
    surfaces: List[Union[NurbsSurface, PlaneSurface]]
    edges: List[Union[Line, NurbsCurve, Arc, Circle]] = None


class Box(Geometry):
    """Box primitive defined by a base plane and dimensions."""
    type: Literal["Box"] = "Box"
    base_plane: Plane
    x_size: float = Field(..., gt=0)
    y_size: float = Field(..., gt=0)
    z_size: float = Field(..., gt=0)


class Rectangle3d(Geometry):
    """Rectangle defined by a plane, width, and height."""
    type: Literal["Rectangle3d"] = "Rectangle3d"
    plane: Plane
    width: float = Field(..., gt=0)
    height: float = Field(..., gt=0)


# ------------------------------------------------------------------------------
# Point Collections
# ------------------------------------------------------------------------------

class PointCloud(Geometry):
    """A set of 3D points with optional normals."""
    type: Literal["PointCloud"] = "PointCloud"
    points: List[Point3d]
    normals: Optional[List[Vector3d]] = None


# ------------------------------------------------------------------------------
# Transformations and Collections
# ------------------------------------------------------------------------------

class Transform(BaseModel):
    """4x4 transformation matrix (row-major)."""
    matrix: List[List[float]] = Field(..., min_items=4, max_items=4)


class GeometryCollection(BaseModel):
    """A collection of heterogeneous geometry objects."""
    objects: List[Geometry]
