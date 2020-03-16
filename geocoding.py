import geocoder
from decorators import async
from settings import API_URL, API_HEADERS
import requests
import json
from eve_api import EveJSONEncoder


@async
def update_person_location(person, url):
    """pass"""
    if '_etag' in person and '_id' in person and '_merged_to' not in person:

        if 'address' not in person:
            person['address'] = {}

        if 'location' not in person['address']:
            geo, score, quality, confidence = get_geo(street=person['address'].get('street_address', ''),
                                                      city=person['address'].get('city', ''),
                                                      zip_code=person['address'].get('zip_code', ''),
                                                      )
            if score and int(score) > 0:
                person['address']['location'] = {}
                person['address']['location']['geo'] = geo
                person['address']['location']['score'] = score
                person['address']['location']['confidence'] = confidence
                person['address']['location']['quality'] = quality

                api_headers = API_HEADERS.copy()
                api_headers['If-Match'] = person['_etag']

                resp = requests.patch('{}/{}'.format(url, person['_id']),
                                      headers=api_headers,
                                      data=json.dumps({'address': person['address']}, cls=EveJSONEncoder)
                                      )


def get_geo(street, city='', zip_code='', country='Norway'):
    try:
        g = geocoder.arcgis('{0} {1} {2}, {3}'.format(street, zip_code, city, country))
        return g.geometry, g.score, g.quality, g.confidence

    except:
        pass

    # Default: Møllergata
    return {'type': 'Point', 'coordinates': [10.749232432252462, 59.91643658534826]}, 0, 'PointAddress', 0


def add_person_location(person):
    """Just add the location fields!"""
    try:
        if 'address' in person and '_merged_to' not in person:

            if person['address'].get('zip_code', '9999') != '9999' and 'location' not in person['address']:
                geo, score, quality, confidence = get_geo(street=person['address'].get('street_address', ''),
                                                          city=person['address'].get('city', ''),
                                                          zip_code=person['address'].get('zip_code', ''),
                                                          )
                if score and int(score) > 0:
                    person['address']['location'] = {}
                    person['address']['location']['geo'] = geo
                    person['address']['location']['score'] = score
                    person['address']['location']['confidence'] = confidence
                    person['address']['location']['quality'] = quality
    except:
        pass

    return person


def add_organization_location(organization):
    """Just add the location fields!"""
    try:
        if 'contact' in organization and '_merged_to' not in organization:

            if organization['contact'].get('zip_code', '9999') != '9999' and 'location' not in organization['contact']:
                street = '{} {}'.format(organization['contact'].get('street_address', ''),
                                        organization['contact'].get('street_address2', '')).strip()
                geo, score, quality, confidence = get_geo(street=street,
                                                          city=organization['contact'].get('city', ''),
                                                          zip_code=organization['contact'].get('zip_code', ''),
                                                          )
                if score and int(score) > 0:
                    organization['contact']['location'] = {}
                    organization['contact']['location']['geo'] = geo
                    organization['contact']['location']['score'] = score
                    organization['contact']['location']['confidence'] = confidence
                    organization['contact']['location']['quality'] = quality
    except:
        pass

    return organization
