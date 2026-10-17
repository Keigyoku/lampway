<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Render jobs and agent execution

An interactive `INVOKE_DEFAULT` render evaluates a depsgraph on Blender's job
thread. Scene edits from a main-thread agent script can tag that graph during
evaluation; the historical crash site was `graph_tag_ids_for_visible_update`.
The [render_gate](../src/scripts/mixar/modules/space_mixie_chat/core/render_gate.py)
therefore answers mutating or unknown tools immediately with
`render_in_progress`, the render kind, and a statement that nothing executed.
It never parks the request or holds the queue until the render finishes.
Known read-only tools can proceed. `lampway_inspect` is admitted by this gate,
but its evaluated mode checks render availability itself; `lampway_view` is
refused because focusing can edit visibility.

`is_job_running("RENDER")` remains a native job observation, not a reason to
restore the retired queue hold. Render code never forces `use_lock_interface`.
The user's Lock Interface choice and Preferences remain theirs.

## Held-open preview

The final-quality viewport flow starts through
`mixie_chat.agent_preview_render`. It invokes the native render asynchronously
and returns a running job key. A script's `__deferred_preview__` result is
recognized by [preview_deferral](../src/scripts/mixar/modules/space_mixie_chat/core/preview_deferral.py),
which polls on a main-thread timer and completes the original tool response
once. Other requests continue draining under the render gate.

`render_complete` and `render_cancel` handlers only mark completion and schedule
a timer. [preview_render](../src/scripts/mixar/modules/space_mixie_chat/core/preview_render.py)
waits for the native job to tear down before reading pixels, restoring
temporary settings, and publishing a result on the main thread. Restoration
checks that a setting still holds the temporary value, so a user's edit wins.
Viewport depsgraph revisions invalidate old results; polling does not call
`view_layer.update()`. Loading another file abandons the previous job state.

Splat renders retain the camera synchronization supplied by
[`splat_render_camera`](../src/scripts/mixar/modules/moodboard/core/splat_render_camera.py).
Render thread callbacks must not perform unrelated scene mutation; UI work
belongs on the main-thread timer.

## Device, engine and size

The request selects the engine and dimensions. It does not discover or enable
compute hardware. At startup,
[`render_device_module`](../src/scripts/mixar/bootstrap/render_device_module.py)
uses [render_device](../src/scripts/mixar/modules/space_mixie_chat/core/render_device.py)
to discover supported GPUs and enable a usable backend once. Discovery defers
while a native render or render reservation exists.

The `default_render_device` preference allows `AUTO`, `GPU`, or `CPU`.
An enabled device from the selected backend must exist before a job can set
`scene.cycles.device` to `GPU`; a CPU preference or unavailable device means
CPU. Preview jobs only read this decision and never write Cycles Preferences.

An unspecified size preserves the scene's aspect under the preview cap of
768 pixels. Explicit dimensions preserve aspect under `FINAL_MAX_EDGE_PX`,
currently 1920 pixels. Encoded PNG size and render samples have independent
bounds in `preview_render.py`. Temporary scene settings are restored on
completion, cancellation and failure.

The source contracts and mocked lifecycle are covered by
`tests/test_render_job_guard.py`, `tests/test_render_device.py`, and the preview
tests under `space_mixie_chat/tests/`. They do not establish a physical GPU
render result; that requires a separate native receipt.
