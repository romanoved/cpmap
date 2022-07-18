#!/usr/bin/python3

import argparse
import html.parser
import json
import logging
import os
import urllib.parse

import requests


RUNCITY_ROOT = 'https://www.runcity.org/ru/'
NO_ROUTE_GAMES = [
    'pushkin2005',
    'dobrypiter2008',
    'dobrypiter2009',
    'ekb2009',
    'ekb2010',
    'magnitogorsk2011',
    'verhneuralsk2011',
    'ekb2011',
    'magnitogorsk2012',
    'concert2012',
    'metromsk2012',
    'victory2012',
    'ekb2012',
    'ufa2012',
    'deephigh2012',
    'metropolia2013',
    'magnitogorsk2013',
    'ekb2013',
    'college2013',
    'ufa2013',
    'constructivnoekb',
    'nizhnynovgorod2014',
    'magnitogorsk2014',
    'vuoksa2014',
    'ufa2014',
    'cleanpeterhof2015',
    'magnitogorsk2015',
    'verhneuralsk2015',
    'cleankuyvozi2015',
    'krapivin2016',
    'nizhnynovgorod2016',
    'ufa2016',
    'intellectuada2018autumn',
    'kazan2019',
    'intellectuada2021spring',
    'poets2021',
    'vdnh',  # TODO: add subgames
    'onlineintegral2021',
]


def process_html(get_parser, text):
    parser = get_parser()
    parser.feed(text)
    parser.close()
    return parser.get_result()


class LinkParser(html.parser.HTMLParser):
    def __init__(self):
        self.links = []
        self.in_link = None
        super().__init__()

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.in_link = dict(attrs)['href']

    def handle_endtag(self, tag):
        if tag == 'a':
            self.in_link = None

    def handle_data(self, data):
        if self.in_link is not None:
            self.links.append((self.in_link, data.strip()))

    def get_result(self):
        return self.links


class RouteParser(html.parser.HTMLParser):
    def __init__(self):
        self.routes = []
        self.in_routes = False
        self.in_a = False
        self.in_id = False
        self.in_description = False
        super().__init__()

    def handle_starttag(self, tag, attrs):
        if not self.in_routes:
            if tag == 'dl' and dict(attrs).get('class') == 'route':
                self.in_routes = True
            return
        logging.debug('BEG %s %s %s %s', tag, attrs, self.in_id, self.in_description)
        if tag == 'a':
            self.in_a = True
        if tag == 'dt':
            self.routes.append({'id': dict(attrs)['id']})
            self.in_id = True
        if tag == 'abbr':
            self.routes[-1][dict(attrs)['class']] = dict(attrs)['title']
        if tag == 'dd' and dict(attrs).get('class') == 'description':
            self.in_description = True
        if self.in_id and tag == 'a' and 'link' not in self.routes[-1] and 'href' in dict(attrs):
            self.routes[-1]['link'] = dict(attrs)['href']

    def handle_endtag(self, tag):
        if not self.in_routes:
            return
        logging.debug('END %s', tag)
        if tag == 'dl':
            self.in_routes = False
        if self.in_a and tag == 'a':
            self.in_a = False
        if self.in_id and tag == 'dt':
            self.in_id = False
        if self.in_description and tag == 'dd':
            self.in_description = False

    def handle_data(self, data):
        if not self.in_routes:
            return
        data = data.strip()
        logging.debug('DAT %s', data)
        if self.in_id and not self.in_a:
            self.routes[-1]['title'] = self.routes[-1].get('title', '') + data
        if self.in_description and not self.in_a:
            self.routes[-1]['description'] = self.routes[-1].get('description', '') + data

    def get_result(self):
        return self.routes


def cache_wrapper(fname, use_cache=True):
    def decorator(func):
        def wrapper(*args, **kwargs):
            ext = os.path.splitext(fname)[-1]
            if use_cache:
                if os.path.dirname(fname):
                    os.makedirs(os.path.dirname(fname), exist_ok=True)
                if os.path.exists(fname):
                    logging.info('get data from %s', fname)
                    with open(fname) as fobj:
                        to_return = fobj.read()
                    if ext == '.json':
                        to_return = json.loads(to_return)
                    return to_return
            logging.info('gen data using %s(*%s, **%s)', func, args, kwargs)
            to_return = func(*args, **kwargs)
            to_store = to_return
            if ext == '.json':
                to_store = json.dumps(to_store, indent=4, sort_keys=True)
            if use_cache:
                logging.info('write data to %s', fname)
                with open(fname, 'w') as fobj:
                    fobj.write(to_store)
            return to_return

        return wrapper

    return decorator


def do_get_html(url):
    logging.info('loading %s', url)
    req = requests.get(url)
    req.raise_for_status()
    return req.text


def get_html(args, fname, url):
    return cache_wrapper(fname, not args.disable_html_cache)(do_get_html)(url)


@cache_wrapper('cache/events.json')
def get_events(args):
    url = urllib.parse.urljoin(RUNCITY_ROOT, 'events/archive')
    text = get_html(args, 'cache/events/archive.html', url)
    events = [
        {
            'id': os.path.basename(link.rstrip('/')),
            'url': urllib.parse.urljoin(url, link),
            'title': data,
        }
        for link, data in process_html(LinkParser, text)
        if len(data.split()) > 1 and '/events/' in link
    ]
    for event in events:
        event['parsed_path'] = os.path.join('cache/parsed', event['id']) + '.json'
        event['is_parsed'] = os.path.exists(event['parsed_path'])
    return list(reversed(events))


def list_events(args):
    print('# id title url is_parsed')
    for event in get_events(args):
        print('\t'.join([event['id'], event['title'], event['url'], str(event['is_parsed'])]))


def parse_event(args, event):
    event_main_text = get_html(args, os.path.join('cache/events', event['id']), event['url'])
    all_routes_url = urllib.parse.urljoin(event['url'], 'routes/all/')
    for link, data in process_html(LinkParser, event_main_text):
        if data.strip() in ['Маршрут', 'Маршруты', 'Контрольные пункты', 'Маршруты соренований']:
            assert urllib.parse.urljoin(event['url'], link) + 'all/' == all_routes_url
            break
    else:
        if event['id'] not in NO_ROUTE_GAMES:
            logging.error('No routes found for %s, check %s manually', event['id'], event['url'])
        return {}

    routes = get_html(args, os.path.join('cache/routes_all', event['id']), all_routes_url)
    items = process_html(RouteParser, routes)
    result = []
    for item in items:
        if 'longitude' not in item and 'latitude' not in item:
            continue
        item['longitude'] = float(item['longitude'])
        item['latitude'] = float(item['latitude'])
        item['url'] = urllib.parse.urljoin(all_routes_url, item['link'])
        result.append(item)
    return result


def update_events(args):
    features = []
    for event in get_events(args):
        parsed = cache_wrapper(event['parsed_path'], args.use_cache)(parse_event)(args, event)
        for item in parsed:
            feature = {
                'type': 'Feature',
                'id': len(features),
                'geometry': {
                    'type': 'Point',
                    'coordinates': [float(item['latitude']), float(item['longitude'])],
                },
                'properties': {
                    'balloonContentHeader': event['title'] + ': ' + item['title'],
                    'balloonContentBody': item.get('description', ''),
                    'balloonContentFooter': '<a href="{0}">{0}</a>'.format(item['url']),
                },
            }
            features.append(feature)
    data = {
        "type": "FeatureCollection",
        "features": features,
    }
    js_data = 'function get_runcity_points() {return ' + json.dumps(data) + ';}'
    with open('runcity_points.js', 'w') as fobj:
        fobj.write(js_data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--disable-html-cache', action='store_true')
    parser.add_argument('--use-cache', action='store_true')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--update', action='store_true')
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.ERROR)

    if args.list:
        list_events(args)
    if args.update:
        update_events(args)


if __name__ == '__main__':
    main()
