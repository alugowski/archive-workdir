#!/usr/bin/env python3
"""
Copy the subdirectories of a working directory to an archive directory. Subsequent runs re-sync the copies.

The archive is expected to be a superset of the working directory, where the working directory is the "owner"
of the subdirectories it does have.
"""

import argparse
from datetime import datetime
import logging
import os
import sys
import subprocess
from pathlib import Path

logger = logging.getLogger("")

WORK_DIR_ID_FILENAME = ".awid"
RSYNC_FLAGS = ["-a", "--delete"]


def dir_path(path):
    """
    Argparse argument type for directories.
    """
    if os.path.isdir(path):
        return path
    else:  # pragma: no cover
        raise argparse.ArgumentTypeError(f"{path} is not a directory")


class ArgumentParser(argparse.ArgumentParser):
    """
    Subclass ArgumentParser so if user pass no or invalid arguments they will see the help screen.
    """
    def error(self, message):  # pragma: no cover
        import sys
        self.print_help(sys.stderr)
        print("")
        self.exit(2, f"error: {message}\n")


def parse_args(args=None):
    parser = ArgumentParser(description=__doc__)

    parser.add_argument("work_dir", type=dir_path)
    parser.add_argument("archive_dir", type=dir_path)

    parser.add_argument("-d", "--dry-run", action="store_true", default=False,
                        help="Do not make any changes.")

    parser.add_argument("-e", "--report-skipped", action="store_true", default=False,
                        help="If any directories are skipped then report that to stderr and return an error code. "
                             "Useful to warn you of problems when run in a cron job.")

    parser.add_argument("-m", "--mark", type=str, metavar="SUBDIR_NAME",
                        help="Mark an unmarked directory that exists in both work dir and archive dir and exit. "
                             "This directory will then get synced on a subsequent run."
                             "By default such directories are ignored to avoid accidental data loss by "
                             "overwriting any changes on the archive side.")

    parser.add_argument("-n", "--mark-new", action="store_true", default=False,
                        help="Automatically mark (and sync) all unmarked sub directories that exist "
                             "in both work dir and archive dir. Use with caution.")

    parser.add_argument("-r", "--rename", action="store_true", default=False,
                        help="Attempt to detect files that have been renamed and rename the archive's copy. "
                             "Cheaper than rsync's copy/delete.")

    parser.add_argument("-v", "--verbose", action="store_true", default=False,
                        help="Extra logging.")

    parser.add_argument("--rsync-arg", action="append", type=str, default=[],
                        help="Argument to forward to rsync. Can be specified multiple times. "
                             "If the argument begins with a dash, use this format: --rsync-arg=\"--no-p\"")

    # Do not run rsync. For testing rename functionality.
    parser.add_argument("--test-no-rsync", action="store_true", default=False,
                        help=argparse.SUPPRESS)

    return parser.parse_args(args=args)


def read_dir_id(path):
    """
    Read the ID of the directory at path.

    This is the contents of path/.awid
    """
    id_path = os.path.join(path, WORK_DIR_ID_FILENAME)
    if os.path.isfile(id_path):
        with open(id_path, mode="r") as f:
            dir_id = f.readline().strip()
            return dir_id if dir_id else None

    return None


def mark_dir(args, path1, path2=None):
    """
    Mark a directory with a identifier stored in a .awid file. This means the directory can be synced.

    If path2 is present then it will be marked with the same identifier as path1.
    """
    dir_id = f"{datetime.now()} {str(path1)}"

    for path in filter(lambda p: p is not None, (path1, path2)):
        id_path = os.path.join(path, WORK_DIR_ID_FILENAME)
        logger.debug(f"{args.dry_run_prefix}Marking {id_path}")
        if not args.dry_run:
            with open(id_path, mode="w") as f:
                f.write(dir_id)

    return dir_id


def attempt_renames(args, work_path: Path, archive_path: Path):
    """
    Attempt to find files that have been renamed, then rename them in the archive dir.

    This method does not guarantee anything, the assumption is that an rsync will follow.

    The utility of this is that a filesystem rename is cheaper than a copy/delete that rsync would do. This is
    especially true if the filesystem uses snapshot-based replication, where a rename is significantly cheaper.
    """
    if not archive_path.is_dir():
        return

    # recurse
    for sub in filter(lambda p: p.is_dir(), work_path.iterdir()):
        arch_sub = archive_path / sub.name
        if arch_sub.is_dir():
            attempt_renames(args, sub, arch_sub)

    work_fnames = set(f.name for f in filter(lambda p: p.is_file(), work_path.iterdir()))
    arch_fnames = set(f.name for f in filter(lambda p: p.is_file(), archive_path.iterdir()))

    work_candidates = [work_path / c for c in (work_fnames - arch_fnames)]
    arch_candidates = [archive_path / c for c in (arch_fnames - work_fnames)]

    if not work_candidates or not arch_candidates:
        return

    def get_stat_id(p: Path):
        """
        Get an ID based on cheap to get metadata.

        Size is a great discriminator for the use cases we're targeting. Does not need to be perfect.
        """
        return p.stat().st_size

    work_to_id = {p: get_stat_id(p) for p in work_candidates}
    id_to_arch = {get_stat_id(p): p for p in arch_candidates}

    for work, fid in work_to_id.items():
        arch = id_to_arch.get(fid, None)
        if not arch:
            # no file in the archive directory matches this work directory file
            continue

        # rename
        src = arch
        dst = src.parent / work.name
        logger.debug(f"{args.dry_run_prefix}Renaming '{src}' to '{dst.name}'")
        if not args.dry_run:
            src.rename(dst)


def rsync_dir(args, work_path: Path, archive_path: Path):
    """
    Run rsync work_path/ archive_path
    """
    command = ["rsync"] + RSYNC_FLAGS
    if args.dry_run:
        command.extend(["--dry-run"])
    if args.verbose:
        command.extend(["-v"])
    command.extend(args.rsync_arg)
    command.extend([str(work_path) + "/", str(archive_path)])

    logger.info(" ".join(f"'{w}'" for w in command))
    subprocess.run(command)


def main(args=None):
    """
    :param args: Command-line arguments. If None then default to system args.
    """
    args = parse_args(args)
    logging.basicConfig(stream=sys.stdout, format="%(message)s", level=logging.DEBUG if args.verbose else logging.INFO)

    dry_run = args.dry_run
    work_base_path = Path(args.work_dir)
    archive_base_path = Path(args.archive_dir)
    args.dry_run_prefix = "Dry run: " if dry_run else ""
    skipped = []

    # mark single directory in workdir and archive
    if args.mark:
        mark_dir(args,
                 work_base_path / args.mark,
                 archive_base_path / args.mark)
        return

    logger.info(f"Archiving from '{work_base_path}' to '{archive_base_path}'")

    # collect known archive subdirectories.
    # any changes to these are updated, including rename of the directory itself
    known_archive_dirs = {}
    for archive_dir in filter(lambda p: p.is_dir(), archive_base_path.iterdir()):
        dir_id = read_dir_id(archive_dir)
        if dir_id:
            logger.debug(f"Known archive directory: {archive_dir}")
            known_archive_dirs[dir_id] = archive_dir

    # scan the work dir
    rsync_todo = []
    logger.info(f"Scanning '{work_base_path}'")
    for work_dir in sorted(filter(lambda p: p.is_dir(), work_base_path.iterdir())):
        archive_subdir = None
        work_dir_id = read_dir_id(work_dir)

        if not work_dir_id:
            test_known_archive_subdir = archive_base_path / work_dir.name

            if test_known_archive_subdir.exists():
                if args.mark_new:
                    archive_subdir = test_known_archive_subdir
                    action = "NEW OVERWRITING directory of same name in archive"
                    mark_dir(args, work_dir, archive_subdir)
                else:
                    action = "SKIPPING: new, but exists in archive. Mark with --mark to sync in future"
            else:
                archive_subdir = test_known_archive_subdir
                action = "NEW"
                mark_dir(args, work_dir)

        else:
            known_archive_subdir = known_archive_dirs.get(work_dir_id, None)
            if known_archive_subdir:
                # known work and archive subdirs
                action = "re-syncing"
                if known_archive_subdir.name != work_dir.name:
                    action = f"has been renamed from {known_archive_subdir.name}, archive to be updated"
                    if not dry_run:
                        new_known_archive_subdir = known_archive_subdir.parent / work_dir.name
                        # noinspection PyTypeChecker
                        # Type checker can't tell that a Path is PathLike
                        os.rename(src=known_archive_subdir, dst=new_known_archive_subdir)
                        archive_subdir = new_known_archive_subdir
                else:
                    archive_subdir = known_archive_subdir
            else:
                # subdir marked in workdir but not present in archive
                test_archive_subdir = archive_base_path / work_dir.name
                if test_archive_subdir.exists():
                    action = "SKIPPING because marked but conflicts with archive. Re-mark with --mark to overwrite"
                else:
                    action = "RESTORING to archive"
                    archive_subdir = test_archive_subdir

        logger.info(f"'{work_dir.name}' : {action}")
        if archive_subdir:
            rsync_todo.append(dict(args=args, work_path=work_dir, archive_path=archive_subdir))
        else:
            skipped.append(dict(args=args, work_path=work_dir, action=action))
    logger.info(f"\n")

    # run rsync
    for rsync_args in rsync_todo:
        if args.rename:
            attempt_renames(**rsync_args)

        if args.test_no_rsync:
            # skip rsync for some tests
            logger.info("Skipping rsync")
            continue

        rsync_dir(**rsync_args)

    # report errors
    if skipped and args.report_skipped:
        print()
        print(f"Skipped directories while archiving from '{work_base_path}' to '{archive_base_path}':", file=sys.stderr)
        for sub in skipped:
            print(f"{sub['work_path'].name} : {sub['action']}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
