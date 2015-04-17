#!/usr/bin/env python
# coding: utf-8

import argparse
import difflib
import re
import sys
import tarfile

def tarfiles(archive, mapper):
  for info in archive.getmembers():
    if info.isfile():
      mapped = mapper(re.sub(r'^\.\/', '', info.name))
      if mapped:
        yield mapped

def map_generic(name):
  if re.search(r'^(?!js)\w\w(_\w\w)?/', name):
    return name
  else:
    return None

def map_anwiki(name):
  if '/_include/' in name:
    return None
  return map_generic(name)

def map_cms(name):
  if '/animations/' in name:
    return None
  if '/' in name:
    dir, file = name.rsplit('/', 1)
    if file == 'index':
      return None
    if file in ('firefox', 'chrome', 'opera', 'safari', 'internet-explorer', 'android', 'yandex-browser', 'maxthon'):
      name = '/'.join((dir, 'index'))
  return map_generic(name)

def compare(anwiki, cms):
  files1 = sorted(set(tarfiles(anwiki, map_anwiki)))
  files2 = sorted(set(tarfiles(cms, map_cms)))
  for line in difflib.context_diff(files1, files2):
    sys.stdout.write(line if line.endswith('\n') else line + '\n')

parser = argparse.ArgumentParser(description='Compare static content')
parser.add_argument('anwiki', metavar='anwiki.tgz', help='Anwiki-generated pages')
parser.add_argument('cms', metavar='cms.tgz', help='CMS-generated pages')
args = parser.parse_args()

anwiki = tarfile.open(args.anwiki, 'r:gz')
cms = tarfile.open(args.cms, 'r:gz')
compare(anwiki, cms)
