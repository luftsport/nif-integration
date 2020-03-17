import requests
from settings import API_URL, API_HEADERS

class Api:
    def __init__(self, resource):

        self.resource = '{}/{}'.format(API_URL, resource)


    def get_item(self, item, query=None):

        resp = requests.get('{}/{}'.format(self.resource, item), headers=API_HEADERS)

class Query:

    def __init__(self):

        self.where = None
        self.max_results = None
        self.page = None
        self.sort = None
        self.aggregate = None
        self.projection = None
        self.version = None

    def __repr__(self):

        query = ''

class Item(Api):
    def __init__(self):
        super().__init__()


class List(Api):
    def __init__(self):
        super().__init__()
