import contextlib
from filecmp import dircmp
import re
import shutil
import tempfile
from pathlib import Path

resources_root = Path(__file__).parent / "resources"


class TempTestDirectories:
    """
    Manage providing workdir, archive, and post-run expected archive directories.

    Each directory used for testing is a temporary copy of a template. Tests are free to modify at will.
    """
    def __init__(self, work_path, archive_path):
        self.orig_work_path = work_path
        self.orig_archive_path = archive_path

        self.work_name = work_path.name
        self.archive_name = archive_path.name

        self.stack = contextlib.ExitStack()

        self.work_path = Path(self.stack.enter_context(tempfile.TemporaryDirectory())) / self.work_name
        self.archive_path = Path(self.stack.enter_context(tempfile.TemporaryDirectory())) / self.archive_name

        shutil.copytree(src=self.orig_work_path, dst=self.work_path)
        shutil.copytree(src=self.orig_archive_path, dst=self.archive_path)

    def describe_subtest(self):
        return {"archive": self.archive_name, "work": self.work_name}

    def get_expected_dir(self):
        """
        Expected directory is listed in the <code>archive_dir/README.md</code> of the format
        <code>`(workdir) expects (expected_dir)`</code>.
        where <code>(expected_dir)</code> can be
        <ul>
        <li>a subdir of <code>expected_archive_dirs</code></li>
        <li><code>"MATCHING_WORKDIR"</code>: the expected directory is identical to the workdir</li>
        <li><code>"UNCHANGED_ARCHIVE"</code>: the expected directory is identical to the archive dir</li>
        </ul>
        :return: a Path to the expected directory or None if this work dir/archive dir pairing is not tested
        """
        with open(self.archive_path / "README.md", 'r') as f:
            readme = f.read()

        m = re.search(f"`{self.work_name} expects ([^`]+)`", readme)
        if not m:
            return None

        expected = m.group(1)
        if expected == "MATCHING_WORKDIR":
            return self.orig_work_path
        if expected == "UNCHANGED_ARCHIVE":
            return self.orig_archive_path

        return resources_root / "expected_archive_dirs" / expected

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stack.close()

    @staticmethod
    def get_work_path(name):
        return resources_root / "work_dirs" / name

    @staticmethod
    def get_archive_path(name):
        return resources_root / "archive_dirs" / name

    @staticmethod
    def get_expected_archive_path(name):
        return resources_root / "expected_archive_dirs" / name

    @staticmethod
    def all_work_paths():
        """
        Return paths for all test work directories.

        :return: Generator[Path, None, None]
        """
        for path in (resources_root / "work_dirs").iterdir():
            yield path

    @staticmethod
    def all_archive_paths():
        """
        Return paths for all test archive directories.

        :return: Generator[Path, None, None]
        """
        for path in (resources_root / "archive_dirs").iterdir():
            yield path

    @staticmethod
    def setup_paths():
        """
        Ensure assumptions about the test directories are met.

         - delete .DS_Store files that may have been placed by Finder
        """

        # delete .DS_Store files
        dirs_to_check = [resources_root]
        while dirs_to_check:
            cur = dirs_to_check.pop()
            for path in cur.iterdir():
                if path.is_file() and path.name == ".DS_Store":
                    path.unlink()  # pragma: no cover
                elif path.is_dir():
                    dirs_to_check.append(path)


def recursive_dircmp(cmp: dircmp):
    cmp.recursion_level = 0
    to_check = [cmp]
    while to_check:
        cur = to_check.pop()
        yield cur
        for subdir in cur.subdirs.values():
            subdir.recursion_level = cur.recursion_level + 1
            to_check.append(subdir)
