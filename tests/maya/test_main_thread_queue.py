"""MaroMainThreadQueue가 상시로 돌며, enqueue한 작업이 doIt 호출 안이
아니라 다음 타이머 틱에서 실행되는지 확인한다.
"""
import os
import time

import maya.standalone
maya.standalone.initialize(name="python")

import maya.cmds as cmds  # noqa: E402

try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    from PySide2.QtWidgets import QApplication  # noqa: F401

_qapp = QApplication.instance() or QApplication([])

plugin = os.environ["MARO_PLUGIN_PATH"]
cmds.loadPlugin(plugin)

assert cmds.maroQueueTestCounter() == 0, "counter must start at zero"

cmds.maroQueueTestEnqueueIncrement()
# 큐에 넣는 커맨드 자체는 아무것도 실행하지 않는다 -- 다음 타이머 틱을
# 기다려야 한다. 곧바로 읽으면 아직 0이어야 한다.
assert cmds.maroQueueTestCounter() == 0, \
    "enqueue must defer execution, not run inline inside doIt"
print("deferred (not inline) OK")

deadline = time.time() + 5
counter = 0
while time.time() < deadline:
    _qapp.processEvents()
    time.sleep(0.05)
    counter = cmds.maroQueueTestCounter()
    if counter > 0:
        break
assert counter == 1, f"expected the queued task to run exactly once, got {counter}"
print("drained on next tick OK")

# 두 개를 한꺼번에 넣어도 둘 다 돈다.
cmds.maroQueueTestEnqueueIncrement()
cmds.maroQueueTestEnqueueIncrement()
deadline = time.time() + 5
while time.time() < deadline:
    _qapp.processEvents()
    time.sleep(0.05)
    if cmds.maroQueueTestCounter() >= 3:
        break
assert cmds.maroQueueTestCounter() == 3, cmds.maroQueueTestCounter()
print("multiple tasks OK")

cmds.file(new=True, force=True)
cmds.unloadPlugin(os.path.splitext(os.path.basename(plugin))[0])
maya.standalone.uninitialize()
print("test_main_thread_queue OK")
