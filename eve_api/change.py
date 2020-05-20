import requests
from settings import API_HEADERS, API_URL
from bson import ObjectId
import dateutil.parser
import datetime
try:
    from eve_api import EveJSONEncoder
except:
    from .eve_jsonencoder import EveJSONEncoder

import json
from collections import Mapping


class ErrorNoEtag(Exception):
    pass


class ChangeStreamItem:
    def __init__(self, document):

        self.change = document.copy()

        if '_id' in self.change and isinstance(self.change['_id'], ObjectId):
            self.change['_id'] = '%s' % self.change['_id']

        if '_etag' not in self.change:
            raise Exception('Error no etag!')

        else:
            self._etag = self.change['_etag']
            self._id = self.change['_id']
            self._realm = self.change['_realm']

            if 'merge_result_of' in self.change:
                self.merged_from = self.change['merge_result_of']

            self.api_url = '{}/integration/changes'.format(API_URL)

    def _merge_dicts(self, x, y):
        z = x.copy()  # start with x's keys and values
        z.update(y)  # modifies z with y's keys and values & returns None

        return z

    def _get_headers_etag(self):

        return self._merge_dicts(API_HEADERS, {'If-Match': self._etag})

    def set_status(self, status, error=None):
        """Sets the status of a change item"""

        if status in ['ready', 'pending', 'finished', 'error']:

            payload = {'_status': status}

            if error is not None:
                if isinstance(error, Mapping) is False:
                    error = {'message': str(error)}

                payload.update({'_issues': error})

            r = requests.patch('%s/%s' % (self.api_url, self._id),
                               data=json.dumps(payload, cls=EveJSONEncoder),
                               headers=self._get_headers_etag())

            # print('Patch status %s %s - url: %s/%s' % (status, r.status_code, self.api_url, self._id))

            if r.status_code == 200:

                r_json = r.json()
                if '_etag' in r_json:
                    self.change['_etag'] = r_json['_etag']
                    self._etag = self.change['_etag']
                    self.change['_status'] = status
                    return True
            elif r.status_code == 412:
                # Client and server etags don't match
                new = requests.get('%s/%s' % (self.api_url, self._id),
                                   headers=API_HEADERS)

                if new.status_code == 200:

                    new_json = new.json()

                    if new_json['_status'] == status:
                        return True

                    elif '_etag' in new_json:
                        self._etag = new_json['_etag']
                        self.set_status(status, error)

            else:
                # print('Error in Change status', r.text)
                pass

        else:
            # print('Error wrong status Changes %s' % status)
            pass

        return False

    @property
    def entity_type(self):
        return self.change['entity_type']

    @property
    def id(self):
        return self.change['id']

    def get_id(self):

        return self.change['id']

    def get_modified(self):

        try:
            if isinstance(self.change['modified'], datetime.datetime) is not True:
                return dateutil.parser.parse(self.change['modified'])
        except:
            pass

        return self.change['modified']

    def get_merged(self):

        return self.merged_from

    def get_value(self, key):

        if key in self.change:
            return self.change[key]
