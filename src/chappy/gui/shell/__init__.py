"""GUI shell composition and lifecycle coordinators.

Shell components are imported from their owning modules.  Avoiding eager
composition imports keeps individual controllers independently importable and
prevents package-initialization cycles.
"""
