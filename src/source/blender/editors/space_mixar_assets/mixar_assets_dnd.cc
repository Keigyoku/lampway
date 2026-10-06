/* SPDX-FileCopyrightText: 2026 Lampway contributors
 *
 * SPDX-License-Identifier: GPL-3.0-or-later */

/** \file
 * \ingroup spmixarassets
 *
 * The Asset Vault's drag and drop (the facelift lane's native half; lane vault-ui owns the Python half).
 *
 * The Vault's tiles are Python operator buttons (`mixar.asset_library_select`, and `mixar.asset_library_place` on the
 * detail column) with an `asset_id`. After the panels lay out, each such button gets a named drag ("Vault Asset: <id>"),
 * so pressing a tile and moving past the drag threshold carries the asset; a plain click still selects.
 *
 * Three places take the drop: the 3D viewport (on an object: that object; elsewhere: the 3D cursor), a node editor
 * (the edited material's tree) and a material slot in the Properties editor. Each calls `LAMPWAY_OT_vault_drop`, which
 * hands the asset and where it landed to `mixar.asset_library_place` (asset_place, one undo step). Where it landed goes
 * in `target_where` when that operator has the property (asset_place's target: cursor | object:<name> |
 * slot:<object>:<index> | node_tree:<material>); without it the asset is placed the way its kind needs.
 */

#include <string>

#include "BLI_string.h"

#include "BKE_context.hh"
#include "BKE_report.hh"
#include "BKE_screen.hh"

#include "BLT_translation.hh"

#include "DNA_material_types.h"
#include "DNA_node_types.h"
#include "DNA_object_types.h"
#include "DNA_screen_types.h"
#include "DNA_space_types.h"

#include "ED_screen.hh"
#include "ED_view3d.hh"

#include "RNA_access.hh"
#include "RNA_define.hh"
#include "RNA_prototypes.hh"

#include "UI_interface.hh"
#include "UI_resources.hh"

#include "WM_api.hh"
#include "WM_types.hh"

#include "../interface/interface_intern.hh"

#include "mixar_assets_dnd.hh"

namespace blender {

static constexpr char vault_prefix[] = "Vault Asset: ";
static constexpr char place_operator[] = "MIXAR_OT_asset_library_place";
static constexpr char drop_operator[] = "LAMPWAY_OT_vault_drop";

/* -------------------------------------------------------------------- */
/** \name Drag: the tiles
 * \{ */

static bool is_tile_operator(const char *idname)
{
  return STREQ(idname, "MIXAR_OT_asset_library_select") || STREQ(idname, place_operator);
}

void mixar_assets_main_region_layout(const bContext *C, ARegion *region)
{
  ED_region_panels_layout(C, region);
  for (ui::Block *block = static_cast<ui::Block *>(region->runtime->uiblocks.first); block;
       block = block->next)
  {
    for (ui::Button &button : block->buttons()) {
      if (!button.optype || !button.opptr || !is_tile_operator(button.optype->idname) ||
          button.dragpoin)
      {
        continue;
      }
      PropertyRNA *prop = RNA_struct_find_property(button.opptr, "asset_id");
      if (!prop || RNA_property_type(prop) != PROP_STRING) {
        continue;
      }
      char asset_id[256];
      RNA_property_string_get(button.opptr, prop, asset_id);
      if (asset_id[0] == '\0') {
        continue;
      }
      const std::string payload = std::string(vault_prefix) + asset_id;
      ui::button_drag_set_name(&button, BLI_strdup(payload.c_str()));
      /* Ownership of the payload moves from the button to the wmDrag on the first drag. */
      button.dragflag |= ui::BUT_DRAGPOIN_FREE | ui::BUT_DRAG_FULL_BUT;
    }
  }
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Drop: the operator every target calls
 * \{ */

static const char *vault_asset_id(const wmDrag *drag)
{
  if (drag->type != WM_DRAG_NAME || !drag->poin ||
      !STRPREFIX(static_cast<const char *>(drag->poin), vault_prefix))
  {
    return nullptr;
  }
  return static_cast<const char *>(drag->poin) + strlen(vault_prefix);
}

static wmOperatorStatus vault_drop_exec(bContext *C, wmOperator *op)
{
  if (!WM_operatortype_find(place_operator, true)) {
    BKE_report(op->reports, RPT_ERROR, "The Asset Vault is not in this build: nothing was placed");
    return OPERATOR_CANCELLED;
  }
  char asset_id[256], where[512];
  RNA_string_get(op->ptr, "asset_id", asset_id);
  RNA_string_get(op->ptr, "where", where);
  PointerRNA props = WM_operator_properties_create(place_operator);
  RNA_string_set(&props, "asset_id", asset_id);
  if (where[0] && RNA_struct_find_property(&props, "target_where")) {
    RNA_string_set(&props, "target_where", where);
  }
  const wmOperatorStatus result = WM_operator_name_call(
      C, place_operator, wm::OpCallContext::ExecDefault, &props, nullptr);
  WM_operator_properties_free(&props);
  return result;
}

static wmOperatorStatus vault_drop_invoke(bContext *C, wmOperator *op, const wmEvent *event)
{
  /* The viewport's target is what is under the drop: an object, else the 3D cursor. */
  ARegion *region = CTX_wm_region(C);
  if (CTX_wm_view3d(C) && region && region->regiontype == RGN_TYPE_WINDOW &&
      !RNA_struct_property_is_set(op->ptr, "where"))
  {
    const int mval[2] = {event->xy[0] - region->winrct.xmin, event->xy[1] - region->winrct.ymin};
    Object *ob = ED_view3d_give_object_under_cursor(C, mval);
    const std::string where = ob ? std::string("object:") + (ob->id.name + 2) : "cursor";
    RNA_string_set(op->ptr, "where", where.c_str());
  }
  return vault_drop_exec(C, op);
}

static void LAMPWAY_OT_vault_drop(wmOperatorType *ot)
{
  ot->name = "Place from the Asset Vault";
  ot->idname = drop_operator;
  ot->description = "Place the dragged Vault asset where it was dropped";
  ot->invoke = vault_drop_invoke;
  ot->exec = vault_drop_exec;
  ot->flag = OPTYPE_INTERNAL;
  PropertyRNA *prop = RNA_def_string(ot->srna, "asset_id", nullptr, 256, "Asset", "The Vault asset to place");
  RNA_def_property_flag(prop, PROP_SKIP_SAVE);
  prop = RNA_def_string(
      ot->srna, "where", nullptr, 512, "Where", "asset_place's target: cursor, object:<name>, slot:<object>:<index>, node_tree:<material>");
  RNA_def_property_flag(prop, PROP_SKIP_SAVE);
}

void mixar_assets_operatortypes()
{
  WM_operatortype_append(LAMPWAY_OT_vault_drop);
}

/** \} */

/* -------------------------------------------------------------------- */
/** \name Drop targets
 * \{ */

static bool view3d_drop_poll(bContext *C, wmDrag *drag, const wmEvent * /*event*/)
{
  return vault_asset_id(drag) && CTX_wm_view3d(C);
}

static bool node_drop_poll(bContext *C, wmDrag *drag, const wmEvent * /*event*/)
{
  SpaceNode *snode = CTX_wm_space_node(C);
  return vault_asset_id(drag) && snode && snode->edittree;
}

static bool slot_drop_poll(bContext *C, wmDrag *drag, const wmEvent * /*event*/)
{
  if (!vault_asset_id(drag)) {
    return false;
  }
  PointerRNA slot = CTX_data_pointer_get_type(C, "material_slot", RNA_MaterialSlot);
  PointerRNA ob = CTX_data_pointer_get_type(C, "object", RNA_Object);
  return !RNA_pointer_is_null(&slot) && !RNA_pointer_is_null(&ob);
}

static void drop_copy_asset(wmDrag *drag, wmDropBox *drop)
{
  RNA_string_set(drop->ptr, "asset_id", vault_asset_id(drag));
}

static void view3d_drop_copy(bContext * /*C*/, wmDrag *drag, wmDropBox *drop)
{
  drop_copy_asset(drag, drop);
}

static void node_drop_copy(bContext *C, wmDrag *drag, wmDropBox *drop)
{
  drop_copy_asset(drag, drop);
  SpaceNode *snode = CTX_wm_space_node(C);
  if (snode && snode->id && GS(snode->id->name) == ID_MA) {
    RNA_string_set(drop->ptr, "where", (std::string("node_tree:") + (snode->id->name + 2)).c_str());
  }
}

static void slot_drop_copy(bContext *C, wmDrag *drag, wmDropBox *drop)
{
  drop_copy_asset(drag, drop);
  PointerRNA slot = CTX_data_pointer_get_type(C, "material_slot", RNA_MaterialSlot);
  PointerRNA ob_ptr = CTX_data_pointer_get_type(C, "object", RNA_Object);
  const Object *ob = static_cast<const Object *>(ob_ptr.data);
  const std::string where = std::string("slot:") + (ob->id.name + 2) + ":" +
                            std::to_string(RNA_int_get(&slot, "slot_index"));
  RNA_string_set(drop->ptr, "where", where.c_str());
}

static std::string vault_drop_tooltip(bContext * /*C*/,
                                      wmDrag * /*drag*/,
                                      const int /*xy*/[2],
                                      wmDropBox * /*drop*/)
{
  return TIP_("Place from the Asset Vault");
}

void mixar_assets_dropboxes()
{
  WM_dropbox_add(WM_dropboxmap_find("View3D", SPACE_VIEW3D, RGN_TYPE_WINDOW),
                 drop_operator, view3d_drop_poll, view3d_drop_copy, nullptr, vault_drop_tooltip);
  WM_dropbox_add(WM_dropboxmap_find("Node Editor", SPACE_NODE, RGN_TYPE_WINDOW),
                 drop_operator, node_drop_poll, node_drop_copy, nullptr, vault_drop_tooltip);
  /* A material slot is a list row in the Properties editor; the interface's own map is the one every such region
   * carries (it is where a dragged material lands on a slot, too). */
  WM_dropbox_add(WM_dropboxmap_find("User Interface", SPACE_EMPTY, RGN_TYPE_WINDOW),
                 drop_operator, slot_drop_poll, slot_drop_copy, nullptr, vault_drop_tooltip);
}

/** \} */

}  // namespace blender
