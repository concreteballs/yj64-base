from pathlib import Path

from pythonforandroid.toolchain import ToolchainCL


ACTIVITY = 'org.blackmirror.blackmirror.MonitorActivity'
PROCESS = ':monitor_ui'


def after_apk_build(toolchain: ToolchainCL) -> None:
    manifest_file = (
        Path(toolchain._dist.dist_dir)
        / 'src'
        / 'main'
        / 'AndroidManifest.xml'
    )
    text = manifest_file.read_text(encoding='utf-8')

    marker = f'android:name="{ACTIVITY}"'
    position = text.find(marker)
    if position < 0:
        raise RuntimeError(
            f'Cannot find {ACTIVITY} in generated AndroidManifest.xml'
        )

    tag_end = text.find('>', position)
    if tag_end < 0:
        raise RuntimeError(
            'Cannot find the end of MonitorActivity manifest tag'
        )

    tag_start = text.rfind('<activity', 0, position)
    if tag_start < 0:
        raise RuntimeError('Cannot find MonitorActivity opening tag')

    tag = text[tag_start:tag_end + 1]
    if 'android:process=' in tag:
        return

    replacement = (
        tag[:-1]
        + f' android:process="{PROCESS}">'
    )
    text = text[:tag_start] + replacement + text[tag_end + 1:]
    manifest_file.write_text(text, encoding='utf-8')
    print(
        f'YJ-64: {ACTIVITY} assigned to android:process="{PROCESS}"'
    )
