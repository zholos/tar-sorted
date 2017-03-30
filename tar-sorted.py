#!/usr/bin/env python3
import sys, os, stat, hashlib, filecmp, tarfile

def read_md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            b = f.read(1048576)
            if not b:
                break
            h.update(b)
    return h.digest()

class Tree:
    def __init__(self, mode="print", file=sys.stdout, verbose=False):
        self.files = {} # md5: [(dirname, basename, ext, md5, path)]
        self.mode = mode
        self.file = file
        self.verbose = verbose
        assert self.mode in ("print", "print0", "tar", "tar_links")
        if self.mode.startswith("tar"):
            self.tar = tarfile.open(fileobj=file, bufsize=1048576, mode="w|",
                                    format=tarfile.PAX_FORMAT)
            # GNU format is shorter, but PAX can store fractional mtime
        else:
            self.tar = None

    def emit(self, path, isdir, link_candidates):
        if self.tar:
            info = self.tar.gettarinfo(path)
            if info.islnk():
                # tarfile detects same inodes, but doesn't check device numbers,
                # so there's a chance of spurious links, especially with zfs
                # snapshots which have same inodes but different file versions.
                # Undo link and check data instead.
                info.type = tarfile.REGTYPE
                info.linkname = ""
            if not (info.isdir() if isdir else info.isreg()):
                raise Exception("tar info doesn't match scan")
            info.mode = 0o755 if info.isdir() else 0o644
            info.uid = info.gid = 0
            info.uname = "root"
            info.gname = "wheel"
            if not isdir and info.size:
                for link in link_candidates:
                    link_info = self.tar.gettarinfo(link)
                    # Hardlink mtime can be saved, but can't be extracted with
                    # command-line tool, so only link when mtime is the same
                    if link_info.mtime == info.mtime:
                        if filecmp.cmp(path, link, shallow=False):
                            info.type = tarfile.LNKTYPE
                            info.linkname = link
                            info.size = 0
                            assert not info.isreg()
                            break
            if self.verbose:
                print(path+(" -> "+info.linkname)*bool(info.linkname),
                      file=sys.stderr)
            if info.isreg():
                with open(path, "rb") as f:
                    self.tar.addfile(info, fileobj=f)
            else:
                self.tar.addfile(info)
        else:
            self.file.write(path)
            self.file.write("\0" if self.mode == "print0" else "\n")

    def scan(self, path):
        st = os.lstat(path)
        if stat.S_ISREG(st.st_mode):
            dirname, basename = os.path.split(path)
            ext = os.path.splitext(basename)[1].lower()
            md5 = read_md5(path)
            self.files.setdefault(md5, []).append(
                (dirname, basename, ext, md5, path))
        elif stat.S_ISDIR(st.st_mode):
            self.emit(os.path.join(path, ""), True, ())
            for item in os.listdir(path):
                self.scan(os.path.join(path, item))
        else:
            raise Exception("unsupported file type: %s" % path)

    def process(self):
        def sort_key(x):
            return x[2], x[1], x[0] # ext, basename, dirname

        # Sort by extension, but emit all files with the same MD5 together
        md5s = set()
        for _, _, _, md5, _ in sorted(
                (y for x in self.files.values() for y in x), key=sort_key):
            if md5 not in md5s:
                md5s.add(md5)
                # emit all paths with the same md5
                link_candidates = []
                for path in sorted(
                        (path for _, _, _, _, path in self.files[md5])):
                    self.emit(path, False, link_candidates)
                    if self.mode == "tar_links":
                        link_candidates.append(path)

    def close(self):
        if self.tar:
            self.tar.close()

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="sort files to improve tar compression")
    parser.add_argument("-0", dest="nul", action="store_true",
                        help="like -print0")
    parser.add_argument("-c", action="store_true",
                        help="write tar file instead of printing filenames")
    parser.add_argument("-l", action="store_true",
                        help="emit hardlinks for identical files")
    parser.add_argument("-o", metavar="output", help="output file")
    parser.add_argument("-v", action="store_true", help="verbose mode with -c")
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    if args.c:
        if args.nul:
            parser.error("can't use -0 with -c")
        mode = "tar_links" if args.l else "tar"
    else:
        if args.l:
            parser.error("can't use -l without -c")
        mode = "print0" if args.nul else "print"
    if args.o:
        file = open(args.o, "wb")
    else:
        file = sys.stdout.buffer if args.c else sys.stdout
    tree = Tree(mode, file, verbose=bool(args.v))
    for path in args.paths:
        tree.scan(path)
    tree.process()
    tree.close()
    if args.o:
        file.close()

if __name__ == "__main__":
    main()
