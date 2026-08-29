"""Mode-independent reusable GUI components.

Concrete widgets are imported from their owning modules.  Keeping package
initialization free of Qt widget construction also lets pure registries such as
``shared_operations`` load without importing the entire GUI widget graph.
"""
