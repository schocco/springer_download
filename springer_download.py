#! /usr/bin/env python

# -*- coding: utf-8 -*-

import getopt
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib
import threading

# Set some kind of User-Agent so we don't get blocked by SpringerLink
class SpringerURLopener(urllib.FancyURLopener):
    version = "Mozilla 5.0"
    
class Book(object):
    '''
    Representation of a single e-book.
    '''
    hash = None
    url = None
    title = None
    subtitle = None
    isbn = None
    chapters = list()
    edition = None
    year = None
    publisher = None
    cover_link = None
    cover_path = None
    
    def __init__(self, hash):
        '''
        :param hash: Content code of the book
        :param url: absolute or relative url to the book
        '''
        self.hash = hash
        self.url = "http://springerlink.com/content/%s/contents" % hash
        self._fetch_book_info()
        
    def _load_chapters(self, page):
        'Creates chapter objects and appends them to self.chapters.'
        for index, match in enumerate(re.finditer('href="([^"]+\.pdf)"', page)):
            chapterLink = match.group(1)
            if chapterLink[:7] == "http://": # skip external links
                continue

            if re.search(r'front-matter.pdf', chapterLink):
                if front_matter:
                    continue
                else:
                    front_matter = True
            if re.search(r'back-matter.pdf', chapterLink) and re.search(r'<a href="([^"#]+)"[^>]*>Next</a>', page):
                continue
            #skip backmatter if it is in list as second chapter - will be there at the end of the book also
            if re.search(r'back-matter.pdf', chapterLink):
                if len(chapters) < 2:
                    continue
            if chapterLink[0] == "/":
                chapterLink = "http://springerlink.com" + chapterLink
            else:
                chapterLink = baseLink + chapterLink
            chapterLink = re.sub("/[^/]+/\.\.", "", chapterLink)
            chapters.append(Chapter(chapterLink, index))

        # get next page
        match = re.search(r'<a href="([^"#]+)"[^>]*>Next</a>', page)
        if match:
            link = "http://springerlink.com" + match.group(1).replace("&amp;", "&")
            page = self._get_page(link)
            self._load_chapters(page)
        else:
            if len(chapters) == 0:
                error("No chapters found - bad link?")
            else:
                print "found %d chapters" % len(chapters)
        
    def get_path(self):
        return curDir + "%s/%s.pdf" % (os.getcwd(), sanitizeFilename(bookTitle))
    
    def get_file_list(self):
        fileList = []
        if self.cover_path:
            fileList.append(self.cover_path)
        return fileList + [c.path for c in self.chapters]
    
    def _get_page(self, link):
        ':returns: html source of the given link.'
        try:
            loader = SpringerURLopener()
            page = loader.open(link).read()
        except IOError, e:
            error("Bad link given (%s)" % e)

        if re.search(r'403 Forbidden', page):
            error("Could not access page: 403 Forbidden error.")
        
    
    def _fetch_book_info(self):
        '''Parses the books Web page to retrieve its information'''

        page = self._get_page(self.url)
        # get title
        match = re.search(r'<h1[^<]+class="title">(.+?)(?:<br/>\s*<span class="subtitle">(.+?)</span>\s*)?</h1>', page, re.S)
        if not match or match.group(1).strip() == "":
            error("Could not evaluate book title - bad link %s" % link)
        else:
            self.title = match.group(1).strip()
            # remove tags, e.g. <sub>
            self.title = re.sub(r'<[^>]*?>', '', bookTitle)
            
        # get subtitle
        if match and match.group(2) and match.group(2).strip() != "":
            self.subtitle = match.group(2).strip()

            # edition
            #match = re.search(r'<td class="labelName">Edition</td><td class="labelValue">([^<]+)</td>', page)
            #if match:
                #bookTitle += " " + match.group(1).strip()

            ## year
            #match = re.search(r'<td class="labelName">Copyright</td><td class="labelValue">([^<]+)</td>', page)
            #if match:
                #bookTitle += " " + match.group(1).strip()

            ## publisher
            #match = re.search(r'<td class="labelName">Publisher</td><td class="labelValue">([^<]+)</td>', page)
            #if match:
                #bookTitle += " - " + match.group(1).strip()

        # coverimage
        match = re.search(r'<div class="coverImage" title="Cover Image" style="background-image: url\(/content/([^/]+)/cover-medium\.gif\)">', page)
        if match:
            self.cover_link = "http://springerlink.com/content/" + match.group(1) + "/cover-large.gif"
            print "downloading front cover from %s" % coverLink
            localFile, mimeType = geturl(coverLink, "frontcover")
            if os.system("convert %s %s.pdf" % (localFile, localFile)) == 0:
                self.cover_path = "%s.pdf" % localFile
        
    def download(self):
        '''
        Downloads all chapters to disk.
        Starts one thread for each chapter
        '''
        #FIXME: wrong statement?
        if self.get_path() == "":
            error("could not transliterate book title %s" % bookTitle)
        if os.path.isfile(self.get_path()):
            error("%s already downloaded" % self.get_path())

        print "\nNow Trying to download book '%s'\n" % self.title

        # setup; set tempDir as working directory
        tempDir = tempfile.mkdtemp()
        os.chdir(tempDir)
        prev_c = None
        for c in self.chapters:
            c.setDaemon(True)
            c.start()
            #if prev_c is not None:
            #    prev_c.join(c)
            #prev_c = c
        
        #wait for threads to finish
        while threading.activeCount()>1:
            sleep(1)
            
            

class Chapter(threading.Thread):
    '''
    Representation of a chapter in an e-book.
    '''
    url = None
    path = None
    index = 0
    
    def __init__(self, url, index):
        threading.Thread.__init__(self)
        self.url = url
        self.index = index
        
    def run(self):
        'Downloads the chapter as pdf'
        print "downloading chapter %d/%d" % (i, len(chapters))
        localFile, mimeType = geturl(self.url, "%d.pdf" % self.index)

        if mimeType.gettype() != "application/pdf":
            os.chdir(curDir)
            shutil.rmtree(tempDir)
            error("downloaded chapter %s has invalid mime type %s - are you allowed to download %s?" % (chapterLink, mimeType.gettype(), bookTitle))

        self.path = localFile
        

def pdfcat(fileList, bookTitlePath):
    if findInPath("pdftk") != False:
        command = [findInPath("pdftk")]
        command.extend(fileList)
        command.extend(["cat", "output", bookTitlePath])
        subprocess.Popen(command, shell=False).wait()
    elif findInPath("stapler") != False:
        command = [findInPath("stapler"), "cat"]
        command.extend(fileList)
        command.append(bookTitlePath)
        subprocess.Popen(command, shell=False).wait()
    else:
        error("You have to install pdftk (http://www.accesspdf.com/pdftk/) or stapler (http://github.com/hellerbarde/stapler).")

# validate CLI arguments and start downloading
def main(argv):
    if not findInPath("iconv"):
        error("You have to install iconv.")

    #Test if convert is installed
    if os.system("convert --version > /dev/null 2>&1")!=0:
        error("You have to install the packet ImageMagick in order to use convert")

    try:
        opts, args = getopt.getopt(argv, "hl:c:n", ["help", "link=", "content=", "no-merge"])
    except getopt.GetoptError:
        error("Could not parse command line arguments.")

    link = ""
    hash = ""
    merge = True

    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit()
        elif opt in ("-c", "--content"):
            if link != "":
                usage()
                error("-c and -l arguments are mutually exclusive")
            hash = arg
        elif opt in ("-l", "--link"):
            if hash != "":
                usage()
                error("-c and -l arguments are mutually exclusive")
            match = re.match("(https?://)?(www\.)?springer(link)?.(com|de)/(content|.*book)/(?P<hash>[a-z0-9\-]+)/?(\?[^/]*)?$", arg)
            if not match:
                usage()
                error("Bad link given. See example link.")
            hash = match.group("hash")
        elif opt in ("-n", "--no-merge"):
            merge = False

    if hash == "":
      usage()
      error("Either a link or a hash must be given.")

    if merge and not findInPath("pdftk") and not findInPath("stapler"):
        error("You have to install pdftk (http://www.accesspdf.com/pdftk/) or stapler (http://github.com/hellerbarde/stapler).")

    book = Book(hash)
    book.download()

    if merge:
        print "merging chapters"
        if len(fileList) == 1:
            shutil.move(fileList[0], bookTitlePath)
        else:
            fileList = book.get_file_list()
            pdfcat(fileList, book.get_path())

        # cleanup
        os.chdir(curDir)
        shutil.rmtree(tempDir)

        print "book %s was successfully downloaded, it was saved to %s" % (bookTitle, bookTitlePath)
        log("downloaded %s chapters (%.2fMiB) of %s\n" % (len(chapters),  os.path.getsize(bookTitlePath)/2.0**20, bookTitle))
    else: #HL: if merge=False
        print "book %s was successfully downloaded, unmerged chapters can be found in %s" % (bookTitle, tempDir)
        log("downloaded %s chapters of %s\n" % (len(chapters), bookTitle))

    sys.exit()

# give a usage message
def usage():
    print """Usage:
%s [OPTIONS]

Options:
  -h, --help              Display this usage message
  -l LINK, --link=LINK    defines the link of the book you intend to download
  -c ISBN, --content=ISBN builds the link from a given ISBN (see below)

  -n, --no-merge          Only download the chapters but don't merge them into a single PDF.

You have to set exactly one of these options.

LINK:
  The link to your the detail page of the ebook of your choice on SpringerLink.
  It lists book metadata and has a possibly paginated list of the chapters of the book.
  It has the form:
    http://springerlink.com/content/ISBN/STUFF
  Where: ISBN is a string consisting of lower-case, latin chars and numbers.
         It alone identifies the book you intent do download.
         STUFF is optional and looks like #section=... or similar. It will be stripped.
""" % os.path.basename(sys.argv[0])

# raise an error and quit
def error(msg=""):
    if msg != "":
        log("ERR: " + msg + "\n")
        print "\nERROR: %s\n" % msg
    sys.exit(2)

    return None

# log to file
def log(msg=""):
    logFile = open('springer_download.log', 'a')
    logFile.write(msg)
    logFile.close()

# based on http://stackoverflow.com/questions/377017/test-if-executable-exists-in-python
def findInPath(prog):
    for path in os.environ["PATH"].split(os.pathsep):
        exe_file = os.path.join(path, prog)
        if os.path.exists(exe_file) and os.access(exe_file, os.X_OK):
            return exe_file
    return False

# based on http://mail.python.org/pipermail/python-list/2005-April/319818.html
def _reporthook(numblocks, blocksize, filesize, url=None):
    #XXX Should handle possible filesize=-1.
    try:
        percent = min((numblocks*blocksize*100)/filesize, 100)
    except:
        percent = 100
    if numblocks != 0:
        sys.stdout.write("\b"*70)
    sys.stdout.write("%-66s%3d%%" % (url, percent))

def geturl(url, dst):
    downloader = SpringerURLopener()
    if sys.stdout.isatty():
        response = downloader.retrieve(url, dst,
                           lambda nb, bs, fs, url=url: _reporthook(nb,bs,fs,url))
        sys.stdout.write("\n")
    else:
        response = downloader.retrieve(url, dst)

    return response

def sanitizeFilename(filename):
    p1 = subprocess.Popen(["echo", filename], stdout=subprocess.PIPE)
    p2 = subprocess.Popen(["iconv", "-f", "UTF-8", "-t" ,"ASCII//TRANSLIT"], stdin=p1.stdout, stdout=subprocess.PIPE)
    return re.sub("\s+", "_", p2.communicate()[0].strip().replace("/", "-"))

# start program
if __name__ == "__main__":
    main(sys.argv[1:])

# kate: indent-width 4; replace-tabs on;
