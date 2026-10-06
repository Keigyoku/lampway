"""compute_backend (specs/cloud/compute_backend.md): one provider-agnostic seam for renting compute. The runner owns every hard thing (write-ahead receipt, caps, privacy gate, egress consent,
reconcile, teardown verification); a backend adapter is thin."""
