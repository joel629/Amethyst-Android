#!/usr/bin/env python3
"""Experimental Samsung Book Cover motion-history fix for Amethyst-Android.

Run AFTER apply_trackpad_fix.py on the v3_openjdk source branch.
The previous 90 degree rotation/pairing patch remains unchanged.

Fixes the absolute-touchpad path: previously all MotionEvent historical samples
were silently discarded because PointerTracker.trackEvent(event) read the CURRENT
coordinates for every historical event. This patch processes historical samples
with their real historical positions and forwards each delta to Minecraft.

Leaves unpaired devices on the original input path.
"""
from pathlib import Path
import argparse
import sys

JAVA_DIR = Path('app_pojavlauncher/src/main/java/net/kdt/pojavlaunch/customcontrols/mouse')
TRACKER = JAVA_DIR / 'PointerTracker.java'
CAPTURE = JAVA_DIR / 'AndroidPointerCapture.java'

TRACKER_ANCHOR = '    public float[] getMotionVector() {\n'
TRACKER_ADDITION = '''    /**
     * Track one historical absolute pointer position (not the current one).
     * The corresponding camera delta is left in the shared mMotionVector.
     */
    public void trackHistoricalEvent(MotionEvent event, int historyIndex) {
        int pointerCount = event.getPointerCount();
        int index = event.findPointerIndex(mTrackedPointerId);
        if (mColdStart || index < 0 || mPointerCount != pointerCount) {
            mTrackedPointerId = event.getPointerId(0);
            mPointerCount = pointerCount;
            mColdStart = false;
            mLastX = event.getHistoricalX(0, historyIndex);
            mLastY = event.getHistoricalY(0, historyIndex);
            mMotionVector[0] = 0f;
            mMotionVector[1] = 0f;
            return;
        }
        float x = event.getHistoricalX(index, historyIndex);
        float y = event.getHistoricalY(index, historyIndex);
        mMotionVector[0] = x - mLastX;
        mMotionVector[1] = y - mLastY;
        mLastX = x;
        mLastY = y;
    }

'''

CAPTURE_ANCHOR = '        processBatchEvents(event, MotionEvent.AXIS_X, MotionEvent.AXIS_Y, mPointerTracker::trackEvent);\n'
CAPTURE_REPLACEMENT = '''        // Paired Samsung absolute trackpad: consume historical positions in order.
        // The original path calls trackEvent(event) for every history entry, which
        // reads the *current* coordinates, discarding fine-grained motion and
        // potentially leaving the final sample at zero. Don't change other mice.
        if (CallbackBridge.isGrabbing() && shouldCorrectPairedTrackpad(event)) {
            for (int h = 0; h < event.getHistorySize(); h++) {
                mPointerTracker.trackHistoricalEvent(event, h);
                processMousePos(event); // Includes the existing 90-degree fix.
            }
        } else {
            processBatchEvents(event, MotionEvent.AXIS_X, MotionEvent.AXIS_Y, mPointerTracker::trackEvent);
        }
'''


def patch(path: Path, anchor: str, replacement: str, already: str, check: bool):
    if not path.is_file():
        raise RuntimeError(f'File not found: {path}')
    old = path.read_text(encoding='utf-8')
    if already in old:
        print(f'Already patched: {path}')
        return
    if old.count(anchor) != 1:
        raise RuntimeError(f'Unexpected source version or anchor count at {path}: {old.count(anchor)}')
    if not check:
        path.write_text(old.replace(anchor, replacement, 1), encoding='utf-8')
    print(f'{"Patch compatible" if check else "Patched"}: {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repository', nargs='?', type=Path, default=Path('.'))
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    root = args.repository.resolve()
    try:
        source = (root / CAPTURE).read_text(encoding='utf-8')
        if 'private boolean shouldCorrectPairedTrackpad(MotionEvent event)' not in source:
            raise RuntimeError('Apply apply_trackpad_fix.py first (missing Samsung pairing helper)')
        patch(root / TRACKER, TRACKER_ANCHOR, TRACKER_ADDITION + TRACKER_ANCHOR,
              'public void trackHistoricalEvent(MotionEvent event, int historyIndex)', args.check)
        patch(root / CAPTURE, CAPTURE_ANCHOR, CAPTURE_REPLACEMENT,
              'mPointerTracker.trackHistoricalEvent(event, h)', args.check)
    except Exception as e:
        print('ERROR:', e, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
