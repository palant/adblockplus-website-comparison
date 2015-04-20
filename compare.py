#!/usr/bin/env python
# coding: utf-8

import argparse
import cgi
import difflib
import logging
import re
import sys
import tarfile
from xml.dom import minidom

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

def sort_attributes(data):
  def do_sort(match):
    source = '%s</%s>' % (re.sub(r'/>$', '>', match.group(0)), match.group(1))
    element = minidom.parseString(source).documentElement
    attributes = []
    for name, value in sorted(element.attributes.items()):
      attributes.append('%s="%s"' % (cgi.escape(name).encode('utf-8'), cgi.escape(value).encode('utf-8')))
    return '<%s %s>' % (match.group(1), ' '.join(attributes))
  return re.sub(r'<(\w+)\s+[^>]*[^>/]/?>', do_sort, data)

def normalize_contents(data):
  data = sort_attributes(data)
  data = re.sub(r'^\s+', '', data, flags=re.M)
  data = re.sub(r'\s+$', '', data, flags=re.M)
  data = re.sub(r'[\t ]+', ' ', data)
  data = re.sub(r'>\s+', '>\n', data, flags=re.S)
  data = re.sub(r'\s+<', '\n<', data, flags=re.S)
  data = re.sub(r'>\s*<', '>\n<', data, flags=re.S)
  data = re.sub(r'([^>])[\r\n]+([^<])', r'\1 \2', data)
  data = re.sub(r'&mdash;', u'\u2014'.encode('utf-8'), data)
  data = re.sub(r'&nbsp;', u'\u00A0'.encode('utf-8'), data)
  data = re.sub(r'&copy;', u'\u00A9'.encode('utf-8'), data)
  return data.strip()

def process_anwiki_contents(data, pagename, existant_files):
  locale, pagename = pagename.split('/', 1)

  # Remove boilerplate
  data = re.sub(r'^.*?<div class="viewcontent [^>]*>', '', data, flags=re.S)
  data = re.sub(r'</div>\s*</div>\s*<footer>.*', '', data, flags=re.S)

  # Fix unescaped ampersands
  data = re.sub(r'&(?!\w+;)', '&amp;', data)

  # <br />   =>   <br>
  data = data.replace('<br />', '<br>')

  # Fix unresolved links to home page
  data = re.sub(r' href="(firefox|chrome|opera|safari|internet-explorer|android|yandex-browser|maxthon)"', r' href="/%s/\1" hreflang="%s"' % (locale, locale), data)

  # Fix Anwiki linking to non-existant pages
  def check_link(match):
    if cms_to_anwiki(re.sub(r'#.*', '', match.group(1))) in existant_files:
      return match.group(0)
    else:
      locale, pagename = match.group(1).split('/', 1)
      return ' href="/en/%s" hreflang="en"' % pagename
  data = re.sub(r' href="/(%s/[^"]+)" hreflang="%s"' % (locale, locale), check_link, data)

  # Remove duplicated hreflang attributes
  data = re.sub(r'(hreflang="[^">]*")(?:\s+hreflang="[^">]*")+', r'\1', data)

  # Escape quotation marks outside of tags
  def escape_quotes(match):
    match = match.group(0)
    if match.startswith('<'):
      return match
    return match.replace('"', '&quot;').replace("'", '&#39;')
  data = re.sub(r'<.*?>|[^<>]+', escape_quotes, data)

  # Remove "untranslated" markers
  data = re.sub(r'<span class="untranslated">(.*?)</span>', r'\1', data, flags=re.S)

  # Simplify script and image URLs
  data = data.replace('/_override-static/global/global', '')
  data = re.sub(r'\?a=show("(?:>|\s))', r'\1', data)
  data = re.sub(r'\?\d+("(?:>|\s))', r'\1', data)

  return normalize_contents(data)

def process_cms_contents(data):
  # Remove boilerplate
  data = re.sub(r'^.*?<div id="content"[^>]*>', '', data, flags=re.S)
  data = re.sub(r'</div>\s*<footer>.*', '', data, flags=re.S)

  # Simplify script and image URLs
  data = re.sub(r'\?\d+("(?:>|\s))', r'\1', data)

  return normalize_contents(data)

def compare_file(anwiki, anwiki_name, anwiki_files, cms, cms_name):
  anwiki_data = anwiki.extractfile('./' + anwiki_name).read()
  if not anwiki_name.endswith('.png'):
    anwiki_data = process_anwiki_contents(anwiki_data, anwiki_name, anwiki_files)

  cms_data = cms.extractfile('./' + cms_name).read()
  if not cms_name.endswith('.png'):
    cms_data = process_cms_contents(cms_data)

  if anwiki_data != cms_data:
    logging.warn("Anwiki file %s and CMS file %s differ" % (anwiki_name, cms_name))
    for line in difflib.unified_diff(anwiki_data.splitlines(True), cms_data.splitlines(True), anwiki_name, cms_name):
      sys.stdout.write(line if line.endswith('\n') else line + '\n')
    print
    print

def compare(anwiki, cms):
  anwiki_files = sorted(tarfiles(anwiki, filter_anwiki))
  cms_files = sorted(tarfiles(cms, filter_cms))
  seen = set()
  for name in cms_files:
    translated = cms_to_anwiki(name)
    if translated in anwiki_files:
      if not translated in seen:
        compare_file(anwiki, translated, anwiki_files, cms, name)
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
