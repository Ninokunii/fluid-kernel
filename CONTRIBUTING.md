# Contributing

Fluid Kernel is a research kernel, not an app wrapper. Contributions should preserve these constraints:

- Runtime UI rendering must remain in the QEMU-booted handwritten kernel path.
- Browser/Chrome/WebView may be used only as tooling or golden-reference comparison, never as the runtime renderer.
- Every kernel milestone should include QEMU serial/framebuffer evidence and a verifier update.
- Do not commit generated `build/` artifacts, screenshots, logs, disk images, packet captures, private keys, keystores, or environment files.

Before sending a change, run:

```bash
python3 -m py_compile kernel/stage_b/build_html_kernel.py tools/run-fluid-kernel-html.py tools/compare-fluid-html-visual.py
python3 - <<'PY'
import kernel.stage_b.build_html_kernel as k
k.assert_memory_map_nonoverlap()
k.assert_state_words_unique()
print('maps ok')
PY
python3 tools/run-fluid-kernel-html.py
python3 tools/compare-fluid-html-visual.py
```
