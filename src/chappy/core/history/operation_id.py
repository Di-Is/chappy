"""Operation identifiers for history events.

This module defines the OperationId enum used to identify different types
of undoable operations in the application. The naming follows the HIS.01.02.G02
convention: namespace.action format.

Namespaces:
    - ident: Identify mode operations
    - group: Organize mode / group operations (including masks)
    - cont: Continuum mode operations
    - model: Model editing operations
    - draw: Display range operations
"""

from __future__ import annotations

from enum import StrEnum


class OperationId(StrEnum):
    """Operation identifier for history events.

    Naming convention (HIS.01.02.G02):
        namespace.action

    The qualifier (e.g., "nav", "manual") is stored separately in HistoryEvent
    to form the full operation ID: namespace.action[.qualifier]
    """

    # Identify mode operations (ident.*)
    IDENT_ADD_CANDIDATE = "ident.add_candidate"
    IDENT_REMOVE_CANDIDATE = "ident.remove_candidate"
    IDENT_CLEAR_CANDIDATES = "ident.clear_candidates"
    IDENT_REGISTER_SELECTED = "ident.register_selected"

    # Group/Organize mode operations (group.*)
    GROUP_MOVE_SYSTEMS = "group.move_systems"
    GROUP_SPLIT = "group.split"
    GROUP_MERGE = "group.merge"
    GROUP_DELETE = "group.delete"
    GROUP_UNLINK_SYSTEM = "group.unlink_system"

    # Mask operations (group.mask_*)
    GROUP_MASK_CREATE = "group.mask_create"
    GROUP_MASK_DELETE = "group.mask_delete"
    GROUP_MASK_EDIT = "group.mask_edit"

    # Continuum mode operations (cont.*)
    CONT_ADD_COMPONENT = "cont.add_component"
    CONT_ADD_POINT = "cont.add_point"
    CONT_DELETE_POINT = "cont.delete_point"
    CONT_MOVE_POINT = "cont.move_point"
    CONT_RESET = "cont.reset"

    # Model operations (model.*)
    MODEL_ADD = "model.add"
    MODEL_DELETE = "model.delete"
    MODEL_BULK_ADD = "model.bulk_add"
    MODEL_BULK_DELETE = "model.bulk_delete"
    MODEL_EDIT_PARAMS = "model.edit_params"
    MODEL_EDIT_RESOLUTION = "model.edit_resolution"
    MODEL_EDIT_LINE_ANALYSIS_HALF_WIDTH = "model.edit_line_analysis_half_width"
    MODEL_BULK_ADD_MULTIPLET = "model.bulk_add_multiplet"
    MODEL_BULK_DELETE_MULTIPLET = "model.bulk_delete_multiplet"
    MODEL_OPTIMIZE_APPLY = "model.optimize_apply"
    MODEL_TIE_SET_CREATE = "model.tie_set_create"
    MODEL_TIE_SET_REMOVE = "model.tie_set_remove"
    MODEL_TIE_SET_DISSOLVE = "model.tie_set_dissolve"

    # Display range operations (draw.*)
    DRAW_RANGE_CHANGE = "draw.range_change"
