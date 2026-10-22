#!/usr/bin/env python3
"""Apply a user-assignable Samsung Book Cover 90-degree camera-axis fix to Amethyst-Android.

Based on v3_openjdk source as viewed on 2026-10-22. Compatible only if exact
source anchors are still present; makes backups and refuses unknown variants.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

BASE = Path('app_pojavlauncher/src/main')
JAVA = BASE / 'java/net/kdt/pojavlaunch/customcontrols/mouse/AndroidPointerCapture.java'
PREFS = BASE / 'res/xml/pref_control.xml'

IMPORT_OLD = 'import android.content.SharedPreferences;\n'
IMPORT_NEW = IMPORT_OLD + 'import android.content.res.Configuration;\n'

METHOD_ANCHOR = '    private void processMousePos(MotionEvent event) {\n'
HELPER = '''    /**
     * Samsung Book Cover devices can report captured relative motion in the
     * tablet's native screen axes instead of its current landscape axes.
     * Only fix the physical input device explicitly paired by the user.
     */
    private boolean shouldCorrectPairedTrackpad(MotionEvent event) {
        if (!DEFAULT_PREF.getBoolean("samsungTrackpadFix", false)) return false;
        if (mHostView.getResources().getConfiguration().orientation !=
                Configuration.ORIENTATION_LANDSCAPE) return false;
        InputDevice device = event.getDevice();
        if (device == null) return false;
        String descriptor = device.getDescriptor();
        if (descriptor == null || descriptor.isEmpty()) descriptor = device.getName();
        if (descriptor == null || descriptor.isEmpty()) return false;

        // Pair the NEXT device that produces a captured movement; do not use
        // heuristic names, since a working Bluetooth mouse must stay normal.
        if (DEFAULT_PREF.getBoolean("samsungTrackpadBindNext", false)
                && (event.getActionMasked() == MotionEvent.ACTION_MOVE
                        || event.getActionMasked() == MotionEvent.ACTION_HOVER_MOVE)) {
            DEFAULT_PREF.edit()
                    .putString("samsungTrackpadDevice", descriptor)
                    .putBoolean("samsungTrackpadBindNext", false)
                    .apply();
        }
        return descriptor.equals(DEFAULT_PREF.getString("samsungTrackpadDevice", ""));
    }

'''
METHOD_NEW = METHOD_ANCHOR + '''        // Physical movement is rotated clockwise by the Samsung keyboard cover
        // (up -> right, right -> down). Undo it: corrected (x,y)=(rawY,-rawX).
        // Deliberately only change *grabbed camera movement*: menu cursor and
        // all unpaired devices, including a Bluetooth mouse, remain unchanged.
        if (CallbackBridge.isGrabbing() && shouldCorrectPairedTrackpad(event)) {
            float rawX = mVector[0];
            float rawY = mVector[1];
            if (DEFAULT_PREF.getBoolean("samsungTrackpadReverse", false)) {
                mVector[0] = -rawY;
                mVector[1] = rawX;
            } else {
                mVector[0] = rawY;
                mVector[1] = -rawX;
            }
        }
'''

XML_OLD = '''        <SwitchPreference
            android:key="always_grab_mouse"
            android:title="@string/mcl_setting_title_grab_mouse"
            android:summary="@string/mcl_setting_subtitle_grab_mouse"
            android:defaultValue="false"/>
'''
XML_NEW = XML_OLD + '''        <!-- Optional workaround for GitHub issue AngelAuraMC/Amethyst-Android#335. -->
        <androidx.preference.SwitchPreferenceCompat
            android:key="samsungTrackpadFix"
            android:title="Fix Samsung Book Cover camera rotation"
            android:summary="Correct the 90 degree camera movement in landscape for the paired trackpad only."
            android:defaultValue="false" />
        <androidx.preference.SwitchPreferenceCompat
            android:key="samsungTrackpadBindNext"
            android:title="Pair trackpad on next movement"
            android:summary="Enable, enter a Minecraft world, then move ONLY the Book Cover trackpad. Automatically turns off after pairing."
            android:defaultValue="false" />
        <androidx.preference.SwitchPreferenceCompat
            android:key="samsungTrackpadReverse"
            android:title="Reverse trackpad rotation direction"
            android:summary="Try this if the corrected camera still turns the wrong way."
            android:defaultValue="false" />
'''


def apply_one(path: Path, substitutions: list[tuple[str, str]], dry_run: bool):
    if not path.exists():
        raise FileNotFoundError(f'Missing file: {path}')
    content = path.read_text(encoding='utf-8')
    new = content
    changed = False
    for before, after in substitutions:
        if after in new:
            continue
        count = new.count(before)
        if count != 1:
            raise RuntimeError(f'{path}: expected exactly one source anchor, found {count}: {before[:65]!r}')
        new = new.replace(before, after, 1)
        changed = True
    if changed and not dry_run:
        backup = path.with_suffix(path.suffix + '.before-trackpad-fix.bak')
        if not backup.exists():
            backup.write_text(content, encoding='utf-8')
        path.write_text(new, encoding='utf-8')
    return 'would patch' if changed and dry_run else ('patched' if changed else 'already patched')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repository', nargs='?', type=Path, default=Path('.'), help='Amethyst source root')
    parser.add_argument('--check', action='store_true', help='Verify applicable without changing files')
    args = parser.parse_args()
    root = args.repository.resolve()
    targets = (
        (root / JAVA, [(IMPORT_OLD, IMPORT_NEW), (METHOD_ANCHOR, HELPER + METHOD_NEW)]),
        (root / PREFS, [(XML_OLD, XML_NEW)]),
    )
    # Validate all first, then write. No partial patch if anchors are unavailable.
    try:
        for file, subs in targets:
            result = apply_one(file, subs, dry_run=True)
            print(f'{result}: {file.relative_to(root)}')
        if not args.check:
            for file, subs in targets:
                result = apply_one(file, subs, dry_run=False)
                print(f'{result}: {file.relative_to(root)}')
    except Exception as err:
        print(f'ERROR: {err}', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
