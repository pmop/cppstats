#!/usr/bin/env python
# -*- coding: utf-8 -*-
# cppstats is a suite of analyses for measuring C preprocessor-based
# variability in software product lines.
# Copyright (C) 2014-2015 University of Passau, Germany
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program.  If not, see
# <http://www.gnu.org/licenses/>.
#
# Contributors:
#     Claus Hunsen <hunsen@fim.uni-passau.de>
#     Andreas Ringlstetter <andreas.ringlstetter@gmail.com>


# #################################################
# imports from the std-library

import os
import sys
import shutil  # for copying files and folders
import errno  # for error/exception handling
import subprocess  # for calling other commands
import re  # for regular expressions
from abc import ABCMeta, abstractmethod  # abstract classes
from collections import OrderedDict
import filecmp

# #################################################
# paths

import preparations

def getPreparationScript(filename):
    return os.path.join(os.path.dirname(preparations.__file__), filename)


# #################################################
# imports from subfolders

import cli

# for rewriting of #ifdefs to "if defined(..)"
# for turning multiline macros to oneliners
# for deletion of include guards in H files
from preparations import rewriteIfdefs, rewriteMultilineMacros, deleteIncludeGuards

from lib import cpplib

from link_or_copy_file import link_or_copy_file

# #################################################
# global constants

_filepattern_c = ('.c', '.C')
_filepattern_h = ('.h', '.H')
_filepattern = _filepattern_c + _filepattern_h

_cvs_pattern = (".git", ".cvs", ".svn")


# #################################################
# helper functions

def notify(message):
    pass

    # import pynotify  # for system notifications
    #
    # pynotify.init("cppstats")
    # notice = pynotify.Notification(message)
    # notice.show()

def handle_cygwinlike_path(cygwin_path_like):
    cygwin_path_like = cygwin_path_like.replace("/cygdrive/c/","")
    cygwin_path_like = cygwin_path_like.replace("/","\\")
    cygwin_path_like = "C:\\" + cygwin_path_like
    return cygwin_path_like


# function for ignore pattern
def filterForFiles(dirpath, contents, pattern=_filepattern):
    filesToIgnore = [filename for filename in contents if
                     not filename.endswith(pattern) and
                     not os.path.isdir(os.path.join(dirpath, filename))
                     ]
    foldersToIgnore = [dir for dir in contents if
                       dir in _cvs_pattern and
                       os.path.isdir(os.path.join(dirpath, dir))
                       ]
    return filesToIgnore + foldersToIgnore

def dieWithExSoftware(command, returnCode):
    print >> sys.stderr, "ERROR Command %s failed with exitcode %d and was killed by an OS signal." \
        %(repr(command),returnCode,)
    print >> sys.stderr, "ERROR Working directory was: %s" %(repr(os.getcwd()),)
    sys.exit(os.EX_SOFTWARE)

def printWarningErrorHandler(command, returnCode):
    print >> sys.stderr, "WARN Command %s failed with exitcode %d." \
        %(repr(command), returnCode,)
    print >> sys.stderr, "WARN Working directory was: %s" %(repr(os.getcwd()),)
    return returnCode

def makeBashCommandErrorHandler(osErrorHandler=dieWithExSoftware):
    def handler(command, returnCode):
        if returnCode < 0:
            return osErrorHandler(command, returnCode)
        else:
            return printWarningErrorHandler(command, returnCode)
    return handler

defaultBashCommandErrorHandler = makeBashCommandErrorHandler()

def runBashCommand(command, shell=False, stdin=None, stdout=None, onFailure=defaultBashCommandErrorHandler):
    # split command if not a list/tuple is given already
    if type(command) is str:
        command = command.split()

    print("\033[31;1;4mDEBUG " + str (command) + "\033[0m")
    if len(command) >= 2 and command[1].startswith("/cygdrive"):
        command[1] = handle_cygwinlike_path(command[1])
        print("\033[31;1;4mDEBUG " + str (command) + "\033[0m")
    process = subprocess.Popen(command, shell=shell, stdin=stdin, stdout=stdout, stderr=stdout)
    out, err = process.communicate()  # TODO do something with the output
    process.wait()


    if process.returncode != 0:
        return onFailure(command, process.returncode)
    return process.returncode

              
def replaceMultiplePatterns(replacements, infile, outfile):
    with open(infile, "rb") as source:
        with open(outfile, "w") as target:
            data = source.read()
            for pattern, replacement in replacements.iteritems():
                data = re.sub(pattern, replacement, data, flags=re.MULTILINE)
            target.write(data)


def stripEmptyLinesFromFile(infile, outfile):
    with open(infile, "rb") as source:
        with open(outfile, "w") as target:
            for line in source:
                if not line.isspace():
                    target.write(line)


def silentlyRemoveFile(filename):
    try:
        os.remove(filename)
    except OSError as e:  # this would be "except OSError, e:" before Python 2.6
        if e.errno != errno.ENOENT:  # errno.ENOENT = no such file or directory
            raise  # re-raise exception if a different error occured


def src2srcml(src, srcml, osErrorHandler=dieWithExSoftware):
    errorHandler = makeBashCommandErrorHandler(osErrorHandler)
    __s2sml = "srcml"
    runBashCommand([__s2sml, src, "--language=C"]
                   , stdout=open(srcml, 'w+')
                   , onFailure=errorHandler
    ) # + " -o " + srcml)
    # FIXME incorporate "|| rm ${f}.xml" from bash


def srcml2src(srcml, src):
    __sml2s = "srcml"
    runBashCommand([__sml2s, srcml], stdout=open(src, 'w+'))  # + " -o " + src)

def copy_missing_files(src_dir, dest_dir, ignore=None):
    if not os.path.isdir(dest_dir):
        os.makedirs(dest_dir)
    existing_dest_files = find_files(dest_dir)
    files_not_to_copy = [ os.path.join(src_dir, os.path.relpath(fn, dest_dir))
                          for fn in existing_dest_files ]

    def file_filter(src_dir, files_in_src_dir, **kwargs):
        files_not_to_overwrite = [ fn for fn in files_in_src_dir
                                   if os.path.join(src_dir, fn) in files_not_to_copy ]
        #if files_not_to_overwrite:
        #    print "copy_missing_files: ignoring existing files in %s: %s" %(src_dir, files_not_to_overwrite,)
            
        if ignore:
            other_ignored_files = ignore(src_dir, files_in_src_dir, **kwargs)
            return other_ignored_files + files_not_to_overwrite
        else:
            return files_not_to_overwrite

    all_files_in_source_dir = find_files(src_dir)

    for src_file in all_files_in_source_dir:
        dir_name = os.path.dirname(src_file)
        base_name = os.path.basename(src_file)
        files_to_ignore = file_filter(dir_name, [base_name])
        if base_name in files_to_ignore:
            continue
        rel_dir_name = os.path.relpath(dir_name, src_dir)
        dest_dir_name = os.path.join(dest_dir, rel_dir_name)
        if not os.path.isdir(dest_dir_name):
            os.makedirs(dest_dir_name)
        dest_name = os.path.join(dest_dir_name, base_name)
        shutil.copy2(src_file,dest_name)
        #print 'shutil.copy2("%s","%s")' %(src_file,dest_name,)

def find_files(dir_name):
    names = os.listdir(dir_name)
    result = []
    errors = []
    for name in names:
        src_name = os.path.join(dir_name, name)
        src_test_name = src_name
        try:
            if os.path.islink(src_name):
                src_test_name = os.readlink(src_name)
            if os.path.isdir(src_test_name):
                files_below = find_files(src_name)
                result.extend(files_below)
            else:
                result.append(src_name)
        except (IOError, os.error) as why:
            errors.append((dir_name, src_name, str(why)))
        # catch the Error from the recursive call so that we can
        # continue with other files
        except shutil.Error as err:
            errors.extend(err.args[0])
    if errors:
        raise shutil.Error(errors)
    return result


class DieWithExSoftwareIfThresholdReached(object):
    def __init__(self, maxErrors,):
        self.maxErrors = maxErrors
        self.errorsSeen = 0

    def __call__(self, command, returnCode):
        print >> sys.stderr, "WARN Command %s failed with exitcode %d and was killed by an OS signal." \
            %(repr(command), returnCode,)
        print >> sys.stderr, "WARN Working directory was: %s" %(repr(os.getcwd()),)
        self.errorsSeen += 1
        if self.errorsSeen > self.maxErrors:
            print >> sys.stderr, "ERROR: Too many errors (%d). Aborting cppstats." \
                %(self.errorsSeen,)
            sys.exit(os.EX_SOFTWARE)
        
        return returnCode


# #################################################
# abstract preparation thread

class AbstractPreparationThread(object):
    '''This class prepares a single folder according to the given kind of preparations in an independent thread.'''
    __metaclass__ = ABCMeta
    sourcefolder = "source"

    def __init__(self, options, inputfolder=None, inputfile=None):
        self.options = options
        self.notrunnable = False
        self.src2srcmlErrorHandler = dieWithExSoftware

        if (inputfolder):
            self.file = None
            self.folder = inputfolder
            self.source = os.path.join(self.folder, self.sourcefolder)

            self.project = os.path.basename(self.folder)

            # get full path of subfolder "_cppstats"
            self.subfolder = os.path.join(self.folder, self.getSubfolder())

        elif (inputfile):
            self.file = inputfile
            self.outfile = self.options.outfile
            self.folder = os.path.dirname(self.file)

            self.project = os.path.basename(self.file)

            # get full path of temp folder for
            import tempfile
            self.subfolder = tempfile.mkdtemp(suffix=self.getSubfolder())


        else:
            self.notrunnable = True

    def startup(self):
        # LOGGING
        notify("starting '" + self.getPreparationName() + "' preparations:\n " + self.project)
        print "# starting '" + self.getPreparationName() + "' preparations: " + self.project

    def teardown(self):

        # delete temp folder for file-based preparation
        if (self.file):
            shutil.rmtree(self.subfolder)

        # LOGGING
        notify("finished '" + self.getPreparationName() + "' preparations:\n " + self.project)
        print "# finished '" + self.getPreparationName() + "' preparations: " + self.project

    def run(self):

        if (self.notrunnable):
            print "ERROR: No single file or input list of projects given!"
            return

        self.startup()

        self.preparedFilesByRelName = self.findPreparedFiles()

        ## Some log messages for debuggin the --prepareFrom option
        if False:
            print >> sys.stderr, "The following prepared files were found:"
            for k,v in self.preparedFilesByRelName.items():
                print >> sys.stderr, "\t%s" %(k,)
                for e in v:
                    print >> sys.stderr, "\t\t%s" %([os.path.relpath(p, '.') for p in e],)
        
        if (self.file):
            self.currentFile = os.path.join(self.subfolder, self.project)

            if not self.canSkipPreparation():
                shutil.copyfile(self.file, self.currentFile)
                self.backupCounter = 0
                self.prepareFile()
            else:
                self.logLazySkip()

            shutil.copyfile(self.resultFilename(self.currentFile), self.outfile)
        else:
            # copy C and H files to self.subfolder
            self.copyToSubfolder()

            self.installSrc2srcmlErrorHandlerForFilesInSubfolder()
            
            # preparation for all files in the self.subfolder (only C and H files)
            for dirname, subFolders, files in os.walk(self.subfolder):
                non_source_files = filterForFiles(dirname, files)
                for fn in files:
                    if fn in non_source_files:
                        #print >> sys.stderr, "Refusing to prepare of non-source file %s" %(fn,)
                        continue
                    self.currentFile = os.path.join(dirname, fn)
                    if not self.canSkipPreparation():
                        self.backupCounter = 0
                        self.prepareFile()
                    else:
                        self.logLazySkip()
                
        self.teardown()

    def installSrc2srcmlErrorHandlerForFilesInSubfolder(self,):
        PERCENT_ERRORS=0.5

        numAllFiles = self.countFilesToPrepareInSubfolder()
        # Don't allow any errors if there is only one file.  Otherwise
        # allow a tiny percentage of files to fail, but at least one.
        threshold=0
        if numAllFiles > 1:
            fthreshold = numAllFiles / 100.0 * PERCENT_ERRORS
            roundedIntThreshold = int(round(fthreshold))
            # Allow at least on erroneous file
            threshold = max(roundedIntThreshold, 1)
        self.src2srcmlErrorHandler = DieWithExSoftwareIfThresholdReached(threshold)

    def countFilesToPrepareInSubfolder(self,):
        result = 0
        for dirname, subFolders, files in os.walk(self.subfolder):
            non_source_files = filterForFiles(dirname, files)
            for fn in files:
                if fn in non_source_files:
                    continue
                else:
                    result += 1
        return result


    def canSkipPreparation(self):
        if not self.options.lazyPreparation:
            return False
        resFn = self.resultFilename(self.currentFile)
        return os.path.isfile(resFn) and (resFn != self.currentFile)

    def logLazySkip(self):
        relName = os.path.relpath(self.currentFile, self.subfolder)
        #print >> sys.stderr, "Lazily skipping preparation of %s" %(relName,)

    def findPreparedFiles(self):
        res = {}
        if not self.options.prepareFrom:
            return res

        preparedFolders = getFoldersFromInputListFile(self.options.prepareFrom)
        for folder in preparedFolders:
            # Actual source files are located here
            sourceFolder = os.path.join(folder, self.sourcefolder)
            # Preparation results are found here
            preparedFolder = os.path.join(folder, self.getSubfolder())

            if (not os.path.isdir(sourceFolder)) or (not os.path.isdir(preparedFolder)):
                continue
            
            filenames = find_files(sourceFolder)
            for fn in filenames:
                relName = os.path.relpath(fn, sourceFolder)
                preparedName = os.path.join(preparedFolder, relName)
                preparationResultName = \
                    os.path.join(preparedFolder, self.resultFilename(relName))

                if not os.path.isfile(preparedName):
                    continue
                if not os.path.isfile(preparationResultName):
                    continue

                v = (fn,preparedName,preparationResultName,)
                
                valuesForRelName = res.get(relName)
                if valuesForRelName:
                    valuesForRelName.append(v)
                else:
                    res[relName] = [v]
        
        return res

    def copyToSubfolder(self):
        # TODO debug
        # echo '### preparing sources ...'
        # echo '### copying all-files to one folder ...'

        if self.options.lazyPreparation:
            if self.options.prepareFrom:
                for fn in find_files(self.source):
                    self.tryCopyPreparedFile(fn, os.path.relpath(fn, self.source))
            copy_missing_files(self.source, self.subfolder,
                               ignore=filterForFiles)
        else:
            # delete folder if already existing (shutil.copytree will
            # otherwise fail)
            if os.path.isdir(self.subfolder):
                shutil.rmtree(self.subfolder)
            # copy all C and H files recursively to the subfolder
            shutil.copytree(self.source, self.subfolder, ignore=filterForFiles)

    def tryCopyPreparedFile(self, fullName, relName):
        preparedFiles = self.preparedFilesByRelName.get(relName)
        if not preparedFiles:
            return
        subfolderPath = os.path.join(self.subfolder, relName)
        potentialResultName = self.resultFilename(subfolderPath)
        if os.path.exists(potentialResultName):
            #print >> sys.stderr, "Cowardly refusing to reuse other preparation result for %s: Prepared file already exists in target folder. (matches %s)" %(relName,(pOrigPath,pSubfolderPath,pResultPath,),)
            return

        for pOrigPath,pSubfolderPath,pResultPath in preparedFiles:
            if filecmp.cmp(fullName, pOrigPath):
                #print >> sys.stderr, "Reusing preparation result for %s from %s" % (relName, os.path.relpath(pOrigPath, '.'))
                self.copyPreparedFileToSubfolder(pSubfolderPath,pResultPath,subfolderPath)
                break

    def copyPreparedFileToSubfolder(self, prepSubfolderPath, prepResultPath, destSubfolderPath):
        #print >> sys.stderr, "copyPreparedFileToSubfolder: %s, %s => %s" % (prepSubfolderPath,prepResultPath,destSubfolderPath)
        #sys.stderr.flush()
        destDir = os.path.dirname(destSubfolderPath)
        if not os.path.isdir(destDir):
            os.makedirs(destDir)
        destResultPath = self.resultFilename(destSubfolderPath)
        
        # copy files
        #shutil.copy2(prepSubfolderPath, destSubfolderPath)
        link_or_copy_file(prepSubfolderPath, destSubfolderPath)
        # Copy the result file, also fixing the source path reference
        # if it is a srcml file
        if destResultPath.endswith('.xml'):
            oldTxt = 'filename="%s"' % (prepSubfolderPath,)
            newTxt = 'filename="%s"' % (destSubfolderPath,)
            with open(prepResultPath, 'r') as fin:
                with open(destResultPath, 'w') as fout:
                    for line in fin:
                        modLine = line.replace(oldTxt, newTxt)
                        fout.write(modLine)
        else:
            #shutil.copy2(prepResultPath, destResultPath)
            link_or_copy_file(prepResultPath, destResultPath)

    def backupCurrentFile(self):
        '''# backup file'''
        if (not self.options.nobak):
            bak = self.currentFile + ".bak" + str(self.backupCounter)
            shutil.copyfile(self.currentFile, bak)
            self.backupCounter += 1
            return bak
        else:
            return None

    @classmethod
    @abstractmethod
    def getPreparationName(cls):
        pass

    @abstractmethod
    def getSubfolder(self):
        pass

    @abstractmethod
    def prepareFile(self):
        pass

    @abstractmethod
    def resultFilename(self, name):
        # Return the name of the file that is the result of the
        # preparation. This is used to determine which files to
        # re-prepare when --lazy-preparation is active. If this
        # returns the same name as self.currentFile, then lazy
        # preparation will be ineffective.
        pass

    # TODO refactor such that file has not be opened several times! (__currentfile)
    def rewriteMultilineMacros(self):
        tmp = self.currentFile + "tmp.txt"

        self.backupCurrentFile()  # backup file

        # turn multiline macros to oneliners
        shutil.move(self.currentFile, tmp)  # move for script
        rewriteMultilineMacros.translate(tmp, self.currentFile)  # call function

        os.remove(tmp)  # remove temp file

    def formatCode(self):
        tmp = self.currentFile + "tmp.txt"

        self.backupCurrentFile()  # backup file

        # call astyle to format file in Java-style
        shutil.move(self.currentFile, tmp)  # move for script
        runBashCommand(["astyle", "--style=java"], stdin=open(tmp, 'r'), stdout=open(self.currentFile, 'w+'))

        os.remove(tmp)  # remove temp file

    def deleteComments(self):
        tmp = self.currentFile + "tmp.xml"
        tmp_out = self.currentFile + "tmp_out.xml"

        self.backupCurrentFile()  # backup file

        # call src2srcml to transform code to xml
        src2srcml(self.currentFile, tmp, osErrorHandler=self.src2srcmlErrorHandler)

        # delete all comments in the xml and write to another file
        def retryOnFailure(command, returnCode):
            print >> sys.stderr, \
                "INFO Command %s failed with exitcode %d. Retrying ..." \
                %(repr(command), returnCode,)
            return runBashCommand(["xsltproc",
                                   ## Prevent parser error : Excessive depth in
                                   ## document: 256 use XML_PARSE_HUGE option
                                   "--maxparserdepth", "1024",
                                   getPreparationScript("deleteComments.xsl"),
                                   tmp],
                                  stdout=open(tmp_out, 'w+'))
        
        runBashCommand(["xsltproc",
                        getPreparationScript("deleteComments.xsl"),
                        tmp],
                       stdout=open(tmp_out, 'w+'),
                       onFailure=retryOnFailure)

        # re-transform the xml to a normal source file
        srcml2src(tmp_out, self.currentFile)

        # delete temp files
        silentlyRemoveFile(tmp)
        silentlyRemoveFile(tmp_out)

    def deleteWhitespace(self):
        """Deletes leading, trailing and inter (# ... if) whitespaces,
        replaces multiple whitespace with a single space. Also deletes empty lines."""
        tmp = self.currentFile + "tmp.txt"

        self.backupCurrentFile()  # backup file

        # replace patterns with replacements
        #replacements = {
        #    '^[ \t]+': '',  # leading whitespaces
        #    '[ \t]+$': '',  # trailing whitespaces
        #    '#[ \t]+': '#',  # inter (# ... if) whitespaces # TODO '^#[ \t]+' or '#[ \t]+'
        #    '\t': ' ',  # tab to space
        #    '[ \t]{2,}': ' '  # multiple whitespace to one space
        #}
        #replaceMultiplePatterns(replacements, self.currentFile, tmp)
        with open(self.currentFile, "r") as source:
            with open(tmp, "w") as target:
                #data = source.read()
                for line in source:
                    # skip empty lines (`for line in source' returns
                    # the lines with their line-ending, so we won't
                    # actually get an empty string ('') for an empty
                    # line, but '\n'.)
                    if line.isspace():
                        continue
                    # inter (# ... if) whitespaces
                    if line.startswith('# ') or line.startswith('#\t'):
                        line = '#' + line[1:].lstrip()
                    # Squeeze multiple subsequent whitespace
                    # characters into a single space. This solution is
                    # apparently faster than using a regexp.  It was
                    # proposed here:
                    #
                    # http://stackoverflow.com/questions/1546226/a-simple-way-to-remove-multiple-spaces-in-a-string-in-python
                    #
                    # Due to the way split() works, it also removes
                    # leading and trailing whitespace from a line.
                    # I.e., line=line.strip() is not necessary to do that. 
                    line = ' '.join(line.split())
                    target.write(line)
                    # Reomving trailing whitespace will have removed
                    # the newline, so we need to add it back.
                    target.write('\n')

        # move temp file to output file
        shutil.move(tmp, self.currentFile)

    def rewriteIfdefsAndIfndefs(self):
        tmp = self.currentFile + "tmp.txt"

        self.backupCurrentFile()  # backup file

        # rewrite #if(n)def ... to #if (!)defined(...)
        d = rewriteIfdefs.rewriteFile(self.currentFile, open(tmp, 'w'))

        # move temp file to output file
        shutil.move(tmp, self.currentFile)

    def removeIncludeGuards(self):
        # include guards only exist in H files, otherwise return
        _, extension = os.path.splitext(self.currentFile)
        if (extension not in _filepattern_h):
            return

        tmp = self.currentFile + "tmp.txt"

        self.backupCurrentFile()  # backup file

        # delete include guards
        deleteIncludeGuards.apply(self.currentFile, open(tmp, 'w'))

        # move temp file to output file
        shutil.move(tmp, self.currentFile)

    def removeOtherPreprocessor(self):
        tmp = self.currentFile + "tmp.txt"

        self.backupCurrentFile()  # backup file

        # delete other preprocessor statements than #ifdefs
        cpplib._filterAnnotatedIfdefs(self.currentFile, tmp)

        # move temp file to output file
        shutil.copyfile(tmp, self.currentFile)

    def deleteEmptyLines(self):
        tmp = self.currentFile + "tmp.txt"

        self.backupCurrentFile()  # backup file

        # remove empty lines
        stripEmptyLinesFromFile(self.currentFile, tmp)

        # move temp file to output file
        shutil.move(tmp, self.currentFile)

    def transformFileToSrcml(self):
        source = self.currentFile
        dest = self.currentFile + ".xml"

        # transform to srcml
        src2srcml(source, dest, osErrorHandler=self.src2srcmlErrorHandler)


# #################################################
# preparation-thread implementations

class GeneralPreparationThread(AbstractPreparationThread):
    @classmethod
    def getPreparationName(cls):
        return "general"

    def getSubfolder(self):
        return "_cppstats"

    def prepareFile(self):
        # multiline macros
        self.rewriteMultilineMacros()

        # delete comments
        self.deleteComments()

        # delete leading, trailing and inter (# ... if) whitespaces
        self.deleteWhitespace()

        # rewrite #if(n)def ... to #if (!)defined(...)
        self.rewriteIfdefsAndIfndefs()

        # removes include guards from H files
        self.removeIncludeGuards()

        # delete empty lines
        self.deleteEmptyLines()

        # transform file to srcml
        self.transformFileToSrcml()

    def resultFilename(self, name):
        return name + ".xml"


class DisciplinePreparationThread(AbstractPreparationThread):
    @classmethod
    def getPreparationName(cls):
        return "discipline"

    def getSubfolder(self):
        return "_cppstats_discipline"

    def prepareFile(self):
        # multiline macros
        self.rewriteMultilineMacros()

        # delete comments
        self.deleteComments()

        # delete leading, trailing and inter (# ... if) whitespaces
        self.deleteWhitespace()

        # rewrite #if(n)def ... to #if (!)defined(...)
        self.rewriteIfdefsAndIfndefs()

        # removes include guards from H files
        self.removeIncludeGuards()

        # removes other preprocessor than #ifdefs
        self.removeOtherPreprocessor()

        # delete empty lines
        self.deleteEmptyLines()

        # transform file to srcml
        self.transformFileToSrcml()

    def resultFilename(self, name):
        return name + ".xml"


class FeatureLocationsPreparationThread(AbstractPreparationThread):
    @classmethod
    def getPreparationName(cls):
        return "featurelocations"

    def getSubfolder(self):
        return "_cppstats_featurelocations"

    def prepareFile(self):
        # multiline macros
        self.rewriteMultilineMacros()

        # delete comments
        self.deleteComments()

        # delete leading, trailing and inter (# ... if) whitespaces
        self.deleteWhitespace()

        # FIXME remove include guards?!

        # rewrite #if(n)def ... to #if (!)defined(...)
        self.rewriteIfdefsAndIfndefs()

        # transform file to srcml
        self.transformFileToSrcml()

    def resultFilename(self, name):
        return name + ".xml"


class PrettyPreparationThread(AbstractPreparationThread):
    @classmethod
    def getPreparationName(cls):
        return "pretty"

    def getSubfolder(self):
        return "_cppstats_pretty"

    def prepareFile(self):
        # multiline macros
        self.rewriteMultilineMacros()

        # format the code
        self.formatCode()

        # # delete comments
        # self.deleteComments()
        #
        # # delete empty lines
        # self.deleteEmptyLines()

    def resultFilename(self, name):
        return name


# #################################################
# collection of preparation threads

# add all subclass of AbstractPreparationThread as available preparation kinds
__preparationkinds = []
for cls in AbstractPreparationThread.__subclasses__():
    entry = (cls.getPreparationName(), cls)
    __preparationkinds.append(entry)

# exit, if there are no preparation threads available
if (len(__preparationkinds) == 0):
    print "ERROR: No preparation tasks found! Revert your changes or call the maintainer."
    print "Exiting now..."
    sys.exit(1)
__preparationkinds = OrderedDict(__preparationkinds)


def getKinds():
    return __preparationkinds


# #################################################
# main method


def applyFile(kind, inputfile, options):
    kinds = getKinds()

    # get proper preparation thread and call it
    threadClass = kinds[kind]
    thread = threadClass(options, inputfile=inputfile)
    thread.run()


def getFoldersFromInputListFile(inputlist):
    ''' This method reads the given inputfile line-wise and returns the read lines without line breaks.'''

    file = open(inputlist, 'r')  # open input file
    folders = file.read().splitlines()  # read lines from file without line breaks
    file.close()  # close file

    folders = filter(lambda f: not f.startswith("#"), folders)  # remove commented lines
    folders = filter(os.path.isdir, folders)  # remove all non-directories
    folders = map(os.path.normpath, folders)  # normalize paths for easier transformations

    # TODO log removed folders

    return folders


def applyFolders(kind, inputlist, options):
    kinds = getKinds()

    # get the list of projects/folders to process
    folders = getFoldersFromInputListFile(inputlist)

    # for each folder:
    for folder in folders:
        # start preparations for this single folder

        # get proper preparation thread and call it
        threadClass = kinds[kind]
        thread = threadClass(options, inputfolder=folder)
        thread.run()


def applyAllPreparationKindsToFolders(inputlist, options):
    kinds = getKinds()
    for kind in kinds.keys():
        applyFolders(kind, inputlist, options)

def main():
    kinds = getKinds()

    # #################################################
    # options parsing

    options = cli.getOptions(kinds, step=cli.steps.PREPARATION)

    # #################################################
    # main

    if (options.inputfile):
        # split --file argument
        options.infile = os.path.normpath(os.path.abspath(options.inputfile[0]))  # IN
        options.outfile = os.path.normpath(os.path.abspath(options.inputfile[1]))  # OUT
        applyFile(options.kind, options.infile, options)
    elif (options.inputlist):
        # handle --list argument
        options.inputlist = os.path.normpath(os.path.abspath(options.inputlist))
        if (options.allkinds):
            applyAllPreparationKindsToFolders(options.inputlist, options)
        else:
            applyFolders(options.kind, options.inputlist, options)
    else:
        print >> sys.stderr, "This should not happen! No input file or list of projects given!"
        sys.exit(1)


if __name__ == '__main__':
    main()
