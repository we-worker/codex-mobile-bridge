import os
import tempfile
import unittest
from pathlib import Path
from bridge.features.workspace.files import artifact_paths, reference_path, workspace_relative_path, workspace_references


class ArtifactCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / '.tmp')
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / 'project'
        self.project.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def artifacts(self, references):
        return artifact_paths({'cwd': str(self.project), 'turns': [{'items': [{
            'type': 'agentMessage', 'text': '\n'.join('[file](<' + ref + '>)' for ref in references)}]}]}, None)

    def test_file_aliases_share_one_id_without_granting_external_files(self):
        file = self.project / 'report space.pdf'
        file.write_bytes(b'pdf fixture')
        outside = self.root / 'outside.pdf'
        outside.write_bytes(b'private fixture')
        references = [str(file), file.as_uri()]
        files = self.artifacts(references + [str(outside), outside.as_uri()])
        self.assertEqual(len(files), 1)
        artifact = next(iter(files.values()))
        self.assertEqual(set(artifact['references']), set(references))
        messages = [{'role': 'assistant', 'text': ' '.join('[file](<' + ref + '>)' for ref in references)}]
        self.assertEqual(set(workspace_references(messages, str(self.project))[0]['references']), set(references))
        self.assertEqual(workspace_relative_path(file, self.project), 'report space.pdf')
        self.assertIsNone(workspace_relative_path(outside, self.project))
        link = self.project / 'link.pdf'
        try:
            link.symlink_to(outside)
        except OSError as exc:
            self.skipTest('File symlinks unavailable: ' + str(exc))
        self.assertEqual(self.artifacts([str(link)]), {})

    @unittest.skipUnless(os.name == 'nt', 'Windows path semantics')
    def test_windows_drive_and_extended_workspace_aliases(self):
        file = self.project / 'report.pdf'
        file.write_bytes(b'fixture')
        references = [str(file), file.as_posix(), '/' + file.as_posix(), file.as_uri()]
        for reference in references:
            self.assertEqual(reference_path(reference).resolve(), file)
        files = self.artifacts(references)
        self.assertEqual(len(files), 1)
        self.assertEqual(set(next(iter(files.values()))['references']), set(references))
        self.assertEqual(workspace_relative_path(file, '\\\\?\\' + str(self.project)), 'report.pdf')
        messages = [{'role': 'assistant', 'text': '[file](<' + str(file) + '>)'}]
        self.assertEqual(workspace_references(messages, '\\\\?\\' + str(self.project))[0]['path'], 'report.pdf')

    @unittest.skipIf(os.name == 'nt', 'POSIX path semantics')
    def test_posix_backslash_names_and_case_are_preserved(self):
        file = self.project / 'Report\\name.txt'
        file.write_bytes(b'fixture')
        self.assertEqual(reference_path(str(file)), file)
        self.assertEqual(workspace_relative_path(file, self.project), file.name)
