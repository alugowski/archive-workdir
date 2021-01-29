[![](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/downloads/)
[![Build Status](https://travis-ci.com/alugowski/archive-workdir.svg?branch=main)](https://travis-ci.com/alugowski/archive-workdir)
[![codecov](https://codecov.io/gh/alugowski/archive-workdir/branch/main/graph/badge.svg?token=u3y0dvhZkp)](https://codecov.io/gh/alugowski/archive-workdir)

Copy the subdirectories of a working directory to an archive directory. Subsequent runs re-sync the copies.

The archive is expected to be a superset of the working directory, where the working directory is the "owner"
of the subdirectories it does have.

Requires Python 3.6+

### Pseudocode

In the general case this happens:
```
for sub in $workdir:
    rsync -a --delete $workdir/$sub/ $archivedir/$sub 
```

The matching of source and destination is slightly more powerful.
Directories are matched by name only if they have not been seen before. Then they are marked with an
ID written to a `sub/.awid` file, and subsequent matching is done based on this ID. This allows the
directory in the workdir to be renamed.

For this use case we manually run the first sync to ensure everything works as expected, then use this in a cron job:

```
python archive_workdir -n -e WORKDIR ARCHIVEDIR
```
 * `-n` will auto-sync any newly-added directories (but not if there is an old already-marked dir in the archive)
 * `-e` will print any un-synced directories to stderr so your cron monitor can alert you.

### Driving use case

Photo editing on a laptop, but with the full archive living on a larger machine.
The editing can be fully done locally, and this script will automatically update the changed
projects. Projects not on the laptop are not affected.

This script is expected to be run via a cron job.
