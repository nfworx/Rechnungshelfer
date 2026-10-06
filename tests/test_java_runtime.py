import json
import tempfile
import unittest
from pathlib import Path

from build_support.java_runtime import JavaRuntimeError, validate_installed_runtime


MODULES = "java.base java.compiler java.desktop java.logging java.xml jdk.httpserver"


class JavaRuntimeTests(unittest.TestCase):
    def _project(self, root: Path, *, modules: str = MODULES) -> Path:
        (root / "external" / "java" / "bin").mkdir(parents=True)
        (root / "external" / "java" / "bin" / "java.exe").write_bytes(b"java")
        (root / "external" / "java" / "release").write_text(
            '\n'.join([
                'IMPLEMENTOR="Eclipse Adoptium"',
                'IMPLEMENTOR_VERSION="Temurin-21.0.12.1+1"',
                'JAVA_RUNTIME_VERSION="21.0.12.1+1-LTS"',
                'JAVA_VERSION="21.0.12.1"',
                f'MODULES="{modules}"',
                'OS_ARCH="x86_64"',
                'OS_NAME="Windows"',
                'JVM_VARIANT="Hotspot"',
                'IMAGE_TYPE="JRE"',
            ]) + '\n',
            encoding="utf-8",
        )
        (root / "external" / "components.json").write_text(
            json.dumps({"schema_version": 1, "components": {"java-runtime": "21.0.12.1"}}),
            encoding="utf-8",
        )
        (root / "build_support").mkdir()
        (root / "build_support" / "java_trusted_releases.json").write_text(
            json.dumps({
                "schema_version": 1,
                "releases": {
                    "21.0.12.1": {
                        "implementor": "Eclipse Adoptium",
                        "implementor_version": "Temurin-21.0.12.1+1",
                        "runtime_version": "21.0.12.1+1-LTS",
                        "image_type": "JRE",
                        "os_name": "Windows",
                        "os_arch": "x86_64",
                        "jvm": "hotspot",
                        "package": {
                            "filename": "runtime.zip",
                            "url": "https://github.com/adoptium/temurin21-binaries/releases/download/test/runtime.zip",
                            "size": 123,
                            "sha256": "a" * 64,
                        },
                    }
                },
            }),
            encoding="utf-8",
        )
        return root

    def test_matching_jre_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = validate_installed_runtime(self._project(Path(directory)))
            self.assertEqual(runtime.image_type, "JRE")
            self.assertEqual(runtime.package_sha256, "a" * 64)

    def test_jdk_is_rejected_when_jre_is_approved(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(Path(directory))
            release = project / "external" / "java" / "release"
            release.write_text(release.read_text().replace('IMAGE_TYPE="JRE"', 'IMAGE_TYPE="JDK"'))
            with self.assertRaisesRegex(JavaRuntimeError, "IMAGE_TYPE"):
                validate_installed_runtime(project)

    def test_missing_kosit_module_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(Path(directory), modules=MODULES.replace("jdk.httpserver", ""))
            with self.assertRaisesRegex(JavaRuntimeError, "jdk.httpserver"):
                validate_installed_runtime(project)

    def test_unapproved_component_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._project(Path(directory))
            registry = project / "external" / "components.json"
            registry.write_text(registry.read_text().replace("21.0.12.1", "21.0.13"))
            with self.assertRaisesRegex(JavaRuntimeError, "nicht .* freigegeben"):
                validate_installed_runtime(project)


if __name__ == "__main__":
    unittest.main()
