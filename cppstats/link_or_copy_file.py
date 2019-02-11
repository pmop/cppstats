#!/usr/bin/env python

import os
import sys
import shutil
import argparse
import errno

def split_all(path):
    tails=[]
    while True:
        head, tail = os.path.split(path)
        if tail:
            tails.append(tail)
            path = head
        else:
            if head:
                tails.append(head)
            break
    tails.reverse()
    return tails

def common_prefix(p1, p2):
    common = []
    for d1,d2 in zip(split_all(p1), split_all(p2)):
        if d1 == d2:
            common.append(d1)
        else:
            break
    if common:
        if len(common) == 1:
            return common[0]
        else:
            return os.path.join(*common)
    else:
        return ''

def is_root_or_empty(path):
    if path and os.path.split(path)[1]:
        return False
    else:
        return True

_os_symlink = getattr(os, "symlink", None)


# Mac OSX, for instance, defines MAXSYMLINKS to be 32 (see
# sys/param.h).  Thus, this value should be more than sufficient.
_MAXSYMLINK = 64

def link_or_copy_file(srcPath, destPath, overwrite=False, verbose=False):
    # Will raise an OS error if the file does not exist

    # Resolve symbolic srcPath if srcPath itself is already a sybolic
    # link.  Note that this does *not* resolve symbolic links in the
    # directory of srcPath, as os.path.realpath does.
    if os.path.islink(srcPath):
        resolvedSrcPath=srcPath
        linkCount=0
        while os.path.islink(resolvedSrcPath):
            linkCount += 1
            if linkCount > _MAXSYMLINK:
                raise IOError(errno.EMLINK, os.strerror(errno.EMLINK), srcPath,)
            #if verbose:
            #    print >> sys.stderr, "resolvedSrcPath = `%s', readlink= `%s'" \
            #        %(repr(resolvedSrcPath)[1:-1],repr(os.readlink(resolvedSrcPath))[1:-1],)
            resolvedSrcPath = os.path.normpath(os.path.join(os.path.dirname(resolvedSrcPath),
                                                     os.readlink(resolvedSrcPath)))
        if verbose:
            print >> sys.stderr, "Resolved source path `%s' to `%s'" \
              %(repr(srcPath)[1:-1],repr(resolvedSrcPath)[1:-1],)
        srcPath = resolvedSrcPath
    
    srcLStat = os.lstat(srcPath)

    srcDir = os.path.dirname(srcPath)
    destDir = os.path.dirname(destPath)

    if os.path.isdir(srcPath):
        ###print "XXX 1: is a directory %s" %(srcPath,)
        raise IOError(errno.EISDIR, os.strerror(errno.EISDIR), srcPath,)

    if destDir == '':
        destDir = '.'
    if not os.path.isdir(destDir):
        ###print "XXX 2: not a directory %s" %(destDir,)
        raise IOError(errno.ENOENT, os.strerror(errno.ENOENT), destDir,)

    if os.path.exists(destPath) and os.path.samefile(srcPath, destPath):
        # We may have conflict here, unless `destPath' is a symbolic link to `srcPath'
        if srcLStat == os.lstat(destPath):
            raise IOError(errno.EINVAL, os.strerror(errno.EINVAL),
                "Source and destination point to the same file: `%s' and `%s'" %(srcPath,destPath,))

    if os.path.lexists(destPath):
        if overwrite:
            if os.path.isdir(destPath) and (not os.path.islink(destPath)):
                if verbose:
                    print >> sys.stderr, "Destination is a directory, removing it: %s" %(repr(destPath)[1:-1],)
                os.rmdir(destPath)
            else:
                if verbose:
                    print >> sys.stderr, "Removing destination file: %s" %(repr(destPath)[1:-1],)
                os.unlink(destPath)
        else:
            raise IOError(errno.EEXIST, os.strerror(errno.EEXIST), destPath)

    if _os_symlink:
        prefix = common_prefix(srcDir, destDir)
        if is_root_or_empty(prefix) and (os.path.isabs(srcPath) or os.path.isabs(destPath)):
            if os.path.isabs(srcPath):
                relSrcName = srcPath
            else:
                relSrcName = os.path.abspath(srcPath)
            #print >> sys.stderr, "Without prefix: os.symlink(%s, %s)" %(repr(relSrcName), repr(destPath),)
        else:
            relSrcPath = os.path.relpath(srcPath, prefix)
            relDestDir = os.path.relpath(destDir, prefix)
            relSrcName = os.path.relpath(relSrcPath, relDestDir)
            #print >> sys.stderr, "With prefix `%s': os.symlink(%s, %s)" %(repr(prefix), repr(relSrcName), repr(destPath),)
        _os_symlink(relSrcName, destPath)
        if verbose:
            print >> sys.stderr, "%s@ -> %s" %(repr(destPath)[1:-1],repr(relSrcName)[1:-1],)
    else:
        shutil.copy2(srcPath, destPath)
        if verbose:
            print >> sys.stderr, "%s -> %s" %(repr(srcPath)[1:-1],repr(destPath)[1:-1],)

def strip_newline_at_end(fn):
    if fn.endswith('\n'):
        return fn[:-1]
    else:
        return fn

def main():
    parser = argparse.ArgumentParser(description='Create a symbolic link from SRC to DEST. If that fails, create a regular file copy.')
    parser.add_argument("src", metavar="SRC", help="source file", nargs='?')
    parser.add_argument("dest", metavar="DEST", help="destination file", nargs='?')
    parser.add_argument("-f", "--force", help="overwrite the destination file if it exists",
                    action="store_true")
    parser.add_argument("-v", "--verbose", help="print progress messages to standard error",
                    action="store_true")
    args = parser.parse_args()
    
    try:
        if args.src and args.dest:
            link_or_copy_file(args.src, args.dest, overwrite=args.force, verbose=args.verbose)
        elif not args.src and not args.dest:
            ##print >> sys.stderr, "Reading files from stdin"
            src=None
            for fn in sys.stdin.readlines():
                if src is None:
                    src=strip_newline_at_end(fn)
                else:
                    dest=strip_newline_at_end(fn)
                    ###print "%s -> %s" %(src,dest,)
                    link_or_copy_file(src, dest, overwrite=args.force, verbose=args.verbose)
                    src=None
            if src is not None:
                print >> sys.stderr, "WARNING: One unprocessed file remains in input: `%s'" % (src,)
        else:
            print >> sys.stderr, "Either need source and destination file or no files at all."
            sys.exit(1)
    except Exception as e:
        if args.verbose:
            import traceback
            traceback.print_exc()
        else:
            print >> sys.stderr, e
        sys.exit(1)

if __name__ == '__main__':
    main()
