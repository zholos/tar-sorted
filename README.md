**tar-sorted** sorts files in an order designed to improve tar file compression:
* by extension and filename, so similar files appear consecutively in the tar stream
* by MD5 checksum, so identical files appear consecutively in the tar stream

Whether this actually works depends on the data. The intended use is manual backups, specifically compressing multiple snapshots of the same filesystem (with many identical files across snapshots) into the same tar file.

By default `tar-sorted` lists filenames to stdout, much like `find`:

```
tar-sorted -0 backups/* | tar cf - --null --no-recursion -T - | xz -9e >backups.tar.xz
```

It can also create a tar file directly:

```
tar-sorted -c backups/* | xz -9e >backups.tar.xz
```

When creating a tar file directly mtimes are preserved but permissions are not. In either mode only directories and regular files are supported.

In order for two identical files that appear consecutively in the tar stream to be compressed efficiently, the xz dictionary must be at least as large as either file. The size of the dictionary at `-9` is 64 MB. The maximum possible compression setting is `--lzma2=preset=9e,dict=1536m` (1.5 GB dictionary), but this is slow and needs more than 15 GB of RAM.

Another way to handle identical files is to store subsequent files as hardlinks to the first. `tar-sorted -cl` does this. However, it's not possible to extract only parts of such a tar file, and extracted identical files will be hardlinked to each other, which may not be desired.

This is experimental software. After creating the archive, please extract and verify its contents (try [`dedup -d`](http://althenia.net/dedup)).
