from filecmp import dircmp
import unittest

from archive_workdir import archive_workdir

from .util import recursive_dircmp, TempTestDirectories


class ArchiveWorkDirTestCase(unittest.TestCase):
    @staticmethod
    def dumpMismatch(cmp, side=""):  # pragma: no cover
        """
        Verbose dump of directories for easier debugging.
        """
        import os
        print(f"MISMATCH {side}")
        print("------------ left:")
        os.system("find " + str(cmp.left))
        print("------------ right:")
        os.system("find " + str(cmp.right))
        print("------------")
        cmp.report_full_closure()
        print("------------")
        print()

    def assertIdenticalDirs(self, a, b):
        for cmp in recursive_dircmp(dircmp(a=a, b=b, ignore=["README.md", ".awid"])):
            if cmp.left_only or cmp.right_only:  # pragma: no cover
                # verbose listing for easier debugging
                ArchiveWorkDirTestCase.dumpMismatch(cmp)

            self.assertFalse(cmp.right_only)
            self.assertFalse(cmp.left_only)
            self.assertFalse(cmp.diff_files)
            self.assertFalse(cmp.funny_files)

    def setUp(self):
        TempTestDirectories.setup_paths()

    def test_dry_run(self):
        for work_path in TempTestDirectories.all_work_paths():
            for archive_path in TempTestDirectories.all_archive_paths():
                with TempTestDirectories(work_path=work_path, archive_path=archive_path) as dirs, \
                        self.subTest(**dirs.describe_subtest()):
                    archive_workdir.main(args=["--dry-run", "-v", str(dirs.work_path), str(dirs.archive_path)])

                    # the work dir should not have changed
                    self.assertIdenticalDirs(dirs.orig_work_path, dirs.work_path)

                    # the archive dir should not have changed
                    self.assertIdenticalDirs(dirs.orig_archive_path, dirs.archive_path)

    def test_sync(self):
        for work_path in TempTestDirectories.all_work_paths():
            for archive_path in TempTestDirectories.all_archive_paths():
                with TempTestDirectories(work_path=work_path, archive_path=archive_path) as dirs:
                    expected_dir = dirs.get_expected_dir()

                    if expected_dir is None:
                        # test is undefined for this work/archive pair
                        continue

                    with self.subTest(**dirs.describe_subtest()):
                        archive_workdir.main(args=["-v", str(dirs.work_path), str(dirs.archive_path)])

                        self.assertIdenticalDirs(dirs.archive_path, expected_dir)

    def test_rename_only(self):
        with TempTestDirectories(work_path=TempTestDirectories.get_work_path("basic"),
                                 archive_path=TempTestDirectories.get_archive_path("rename_marked")) as dirs:
            archive_workdir.main(args=["-v", "--test-no-rsync", str(dirs.work_path), str(dirs.archive_path)])

            self.assertIdenticalDirs(dirs.archive_path, dirs.get_expected_dir())

    def test_mark_all(self):
        # ensure no changes when run normally
        with TempTestDirectories(work_path=TempTestDirectories.get_work_path("basic"),
                                 archive_path=TempTestDirectories.get_archive_path("existing_unmarked")) as dirs:
            archive_workdir.main(args=["-v", str(dirs.work_path), str(dirs.archive_path)])

            expected_dir = TempTestDirectories.get_archive_path("existing_unmarked")
            self.assertIdenticalDirs(dirs.archive_path, expected_dir)

        # run again with --mark-all which should overwrite the unmarked archive directory
        with TempTestDirectories(work_path=TempTestDirectories.get_work_path("basic"),
                                 archive_path=TempTestDirectories.get_archive_path("existing_unmarked")) as dirs:
            archive_workdir.main(args=["-v", "--mark-new", str(dirs.work_path), str(dirs.archive_path)])

            expected_dir = TempTestDirectories.get_expected_archive_path("basic")
            self.assertIdenticalDirs(dirs.archive_path, expected_dir)

    def test_mark_single(self):
        with TempTestDirectories(work_path=TempTestDirectories.get_work_path("basic"),
                                 archive_path=TempTestDirectories.get_archive_path("existing_unmarked")) as dirs:
            # mark the unmarked workdir
            archive_workdir.main(args=["-v", "--mark", "unmarked", str(dirs.work_path), str(dirs.archive_path)])

            # run normally
            archive_workdir.main(args=["-v", str(dirs.work_path), str(dirs.archive_path)])

            expected_dir = TempTestDirectories.get_expected_archive_path("basic")
            self.assertIdenticalDirs(dirs.archive_path, expected_dir)

    def test_report_skipped(self):
        # report
        with TempTestDirectories(work_path=TempTestDirectories.get_work_path("basic"),
                                 archive_path=TempTestDirectories.get_archive_path("marked_conflict")) as dirs:

            ret = archive_workdir.main(args=["-v", "--report-skipped", str(dirs.work_path), str(dirs.archive_path)])

            self.assertNotEqual(ret, 0)
            self.assertIdenticalDirs(dirs.archive_path, dirs.get_expected_dir())


if __name__ == "__main__":
    unittest.main()  # pragma: no cover
