#!/usr/bin/env python
# coding: utf-8

import argparse
import difflib
import logging
import re
import sys
import tarfile

def tarfiles(archive, filter):
  for info in archive.getmembers():
    if info.isfile():
      name = re.sub(r'^\.\/', '', info.name)
      if filter(name):
        yield name

def filter_generic(name):
  return re.search(r'^(?!js)\w\w(_\w\w)?/', name)

def filter_anwiki(name):
  return '/_include/' not in name and filter_generic(name)

def filter_cms(name):
  if '/animations/' in name:
    return False
  if '/' in name and name.rsplit('/', 1)[1] == 'index':
    return False
  return filter_generic(name)

def cms_to_anwiki(name):
  if '/' in name:
    dir, file = name.rsplit('/', 1)
    if file in ('firefox', 'chrome', 'opera', 'safari', 'internet-explorer', 'android', 'yandex-browser', 'maxthon'):
      return '/'.join((dir, 'index'))
  return name

def compare_file(anwiki, anwiki_name, cms, cms_name):
  pass

def compare(anwiki, cms):
  anwiki_files = sorted(tarfiles(anwiki, filter_anwiki))
  cms_files = sorted(tarfiles(cms, filter_cms))
  seen = set()
  for name in cms_files:
    translated = cms_to_anwiki(name)
    if translated in anwiki_files:
      compare_file(anwiki, translated, cms, name)
      seen.add(translated)
    else:
      logging.warn('CMS file %s has no Anwiki correspondence' % name)

  for name in anwiki_files:
    if name not in seen:
      logging.warn('Anwiki file %s has no CMS correspondence' % name)


parser = argparse.ArgumentParser(description='Compare static content')
parser.add_argument('anwiki', metavar='anwiki.tgz', help='Anwiki-generated pages')
parser.add_argument('cms', metavar='cms.tgz', help='CMS-generated pages')
args = parser.parse_args()

anwiki = tarfile.open(args.anwiki, 'r:gz')
cms = tarfile.open(args.cms, 'r:gz')
compare(anwiki, cms)
