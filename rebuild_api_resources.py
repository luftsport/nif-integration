from nif_api import NifApiIntegration, NifApiCompetence
from settings import (
    ACLUBU,
    ACLUBP,
    NLF_ORG_STRUCTURE,
    API_HEADERS,API_URL,
    NLF_ORG_STRUCTURE
)
import requests
import json
from eve_api import EveJSONEncoder
from geocoding import add_organization_location


class NifRebuildResources:
    def __init__(self, realm='PROD', log_file='prod-rebuild.log'):

        self.api_club = NifApiIntegration(ACLUBU, ACLUBP, realm, log_file)
        # self.api_fed = NifApiIntegration(NIF_FEDERATION_USERNAME, NIF_FEDERATION_PASSWORD)
        # self.api_competences = NifApiCompetence(NIF_FEDERATION_USERNAME, NIF_FEDERATION_PASSWORD)

    def _get_list(self, resource):

        resp = requests.get('{}/{}/?max_results=100000'.format(API_URL, resource),
                            headers=API_HEADERS)

        if resp.status_code == 200:
            result = resp.json()
            return True, result['_items']
        else:
            return False, {}

    def _get_item(self, item_id, resource):

        resp = requests.get('{}/{}/{}'.format(API_URL, resource, item_id),
                            headers=API_HEADERS)

        if resp.status_code == 200:

            return True, resp.json()
        else:
            return False, {}

    def _replace(self, payload, resource, etag):

        if '_id' in payload:
            pass

        headers = API_HEADERS.copy()

        headers['If-Match'] = etag

        resp = requests.put('{}/{}/{}'.format(API_URL, resource, payload['_id']),
                            data=json.dumps(payload, cls=EveJSONEncoder),
                            headers=headers)

        if resp.status_code == 200:
            return True, resp.json()
        else:
            return False, {}

    def _insert(self, payload, resource):

        resp = requests.post('{}/{}'.format(API_URL, resource),
                             data=json.dumps(payload, cls=EveJSONEncoder),
                             headers=API_HEADERS)

        if resp.status_code == 201:
            return True, resp.json()
        else:
            try:
                print(resp.json())
            except:
                pass
            return False, {}

    def _delete_resource(self, resource):

        resp = requests.delete('{}/{}'.format(API_URL, resource),
                               headers=API_HEADERS)

        if resp.status_code == 404 or resp.status_code == 204:
            return True
        else:
            return False

    def _delete_item(self, resource, item_id):

        resp = requests.delete('{}/{}/{}'.format(API_URL, resource, item_id),
                               headers=API_HEADERS)

        if resp.status_code == 204:
            return True

        return False

    def _get_gren(self, club):
        activities = []
        main_activity = {}
        # Now get all others
        for group in club.get('_down', []):
            if group.get('type', 0) == 6:  # gruppe
                api_status, api_group = self.api_club.get_organization(group['id'], NLF_ORG_STRUCTURE)
                if api_status is True:
                    self._update_org(api_group.get('id', 0))
                    for gren in api_group.get('_down', []):
                        if gren.get('type', 0) == 14:  # Gren
                            gren_status, gren_item = self.api_club.get_organization(gren['id'], NLF_ORG_STRUCTURE)
                            if gren_status is True:
                                self._update_org(gren_item.get('id', 0))
                                if 'main_activity' in gren_item:
                                    main_activity = gren_item.get('main_activity', {})
                                if 'activities' in gren_item:
                                    for a in gren_item.get('activities', []):
                                        activities.append(a)

        activities = list({v['id']: v for v in activities}.values())
        return activities, main_activity

    def _update_org(self, club_id):

        api_status, api_club = self.api_club.get_organization(club_id, NLF_ORG_STRUCTURE)
        if api_status is True:

            api_club = add_organization_location(api_club)

            if club_id not in list(NLF_ORG_STRUCTURE.keys()) and api_club.get('type_id', 0) == 5:
                if api_club.get('main_activity', {}).get('id', 27) == 27:
                    activities, main_activity = self._get_gren(api_club)
                    if len(activities) > 0:
                        api_club['activities'] = activities
                    if len(main_activity) > 0:
                        api_club['main_activity'] = main_activity

            elif club_id not in [1] and club_id in list(NLF_ORG_STRUCTURE.keys()):
                api_club['activities'] = [NLF_ORG_STRUCTURE.get(club_id)]
                api_club['main_activity'] = NLF_ORG_STRUCTURE.get(club_id)

            exists, item = self._get_item(club_id, resource='organizations')

            if exists is True:
                api_club['_id'] = item.get('_id', None)
                s, r = self._replace(payload=api_club, resource='organizations/process', etag=item.get('_etag', None))
            else:
                s, r = self._insert(payload=api_club, resource='organizations/process')

            if s is not True:
                print('Error inserting club', club_id)

    def organizations(self):
        # raise NotImplementedError  # Actually is in organizations
        # get organizations
        # for org in organizations:
        # update with logo= file api.get_org_logo(org_id)

        status, clubs = self._get_list(resource='ka/clubs')

        # Needs to have NLF
        for k in list(NLF_ORG_STRUCTURE.keys()):
            clubs.append({'Id': k, 'OrgTypeId': 5})
        # Atna, Borgen, KS, Nordby, NLF, Testklubb, Bø
        for xtra in [861435, 852558, 61726, 874011, 376, 781765, 908228]:
            clubs.append({'Id': xtra, 'OrgTypeId': 5})

        if status is True:
            for club in clubs:
                if club['OrgTypeId'] == 5:
                    self._update_org(club['Id'])

    def organizations_logo(self):
        """
        status, logo = i.get_org_logo(376)
        r = requests.get('{}/organizations/376'.format(API_URL), headers=API_HEADERS)

        org = r.json()
        headers = API_HEADERS.copy()
        headers['If-Match']= org['_etag']
        headers.pop('Content-Type')
        pr = requests.patch('{}/organizations/process/{}'.format(API_URL, org['_id']),
                                   files=dict(logo=base64.b64encode(logo)),headers=hea

        :return:
        """
        # _get all orgs from api, patch logo
        raise NotImplementedError

    def organizations_types(self):
        resource = 'organizations/types'
        if self._delete_resource(resource):

            status, result = self.api_club.get_organization_types()

            if status is True and isinstance(result, list):
                # for r in result:
                status, resp = self._insert(result, resource)

                if status is not True:
                    print('Error inserting county', result, resp)

    def competence_types(self):

        raise NotImplementedError

        count = self._get_list('competences/types/count')

        for competence in count:
            payload = self.api_competences.get_competece_type(competence['type_id'])
            _, _ = self._insert(payload, 'competences/types')

    def counties(self):
        resource = 'counties'
        if self._delete_resource(resource):

            status, result = self.api_club.get_counties()

            if status is True and isinstance(result, list):
                # for r in result:
                status, resp = self._insert(result, resource)

                if status is not True:
                    print('Error inserting county', result, resp)

    def countries(self):
        resource = 'countries'
        if self._delete_resource(resource):

            status, result = self.api_club.get_countries()

            if status is True and isinstance(result, list):
                # for r in result:
                status, resp = self._insert(result, resource)

                if status is not True:
                    print('Error inserting country', result, resp)

    def function_types(self):
        resource = 'functions/types'
        if self._delete_resource(resource):

            status, result = self.api_club.get_function_types()

            if status is True and isinstance(result, list):
                # for r in result: # If each item
                status, resp = self._insert(result, resource)

                if status is not True:
                    print('Error inserting', resource, result, resp)

    def license_status(self):
        resource = 'licenses/status'
        if self._delete_resource(resource):

            status, result = self.api_club.get_licenses_status()

            if status is True and isinstance(result, list):
                # for r in result:
                status, resp = self._insert(result, resource)

                if status is not True:
                    print('Error inserting', resource, result, resp)

    def license_types(self):
        resource = 'licenses/types'
        if self._delete_resource(resource):

            status, result = self.api_club.get_licenses_types()

            if status is True and isinstance(result, list):
                for r in result:  # Batch won't work due to Decimal and encoder?

                    # @TODO filter in NLF org_id's?
                    status, resp = self._insert(r, resource)

                    if status is not True:
                        print('Error inserting', resource, result, resp)

    def activities(self):

        resource = 'activities'

        activities = [
            {'org_id_owner': 376, 'org_name_owner': 'Norges Luftsportforbund', 'id': 27, 'code': 370,
             'name': 'Luftsport', 'parent_activity_id': 1},
            {'org_id_owner': 90972, 'org_name_owner': 'Fallskjermseksjonen', 'id': 109, 'code': 371,
             'name': 'Fallskjerm', 'parent_activity_id': 27},
            {'org_id_owner': 90969, 'org_name_owner': 'HPS seksjonen', 'id': 110, 'code': 372, 'name': 'HPS',
             'parent_activity_id': 27},
            {'org_id_owner': 90968, 'org_name_owner': 'Seilflyseksjonen', 'id': 111, 'code': 373, 'name': 'Seilfly',
             'parent_activity_id': 27},
            {'org_id_owner': 203026, 'org_name_owner': 'Ballongseksjonen', 'id': 235, 'code': 374, 'name': 'Ballong',
             'parent_activity_id': 27},
            {'org_id_owner': 203027, 'org_name_owner': 'Modellflyseksjonen', 'id': 236, 'code': 375,
             'name': 'Modellfly', 'parent_activity_id': 27},
            {'org_id_owner': 203030, 'org_name_owner': 'Mikroflyseksjonen', 'id': 237, 'code': 376, 'name': 'Mikrofly',
             'parent_activity_id': 27},
            {'org_id_owner': 203025, 'org_name_owner': 'Motorflyseksjonen', 'id': 238, 'code': 377, 'name': 'Motorfly',
             'parent_activity_id': 27},
        ]

        if self._delete_resource(resource) is True:

            status, result = True, activities  # self.api_club.get_activities()

            if status is True and isinstance(result, list):
                status, resp = self._insert(result, resource)

                if status is not True:
                    print('Error inserting', resource, result, resp)

    def rebuild(self):

        #self.organizations()
        #self.organizations_types()
        # self.competence_types()
        self.counties()
        self.countries()
        self.function_types()
        #self.license_types()
        #self.license_status()
        #self.activities()

    def run(self):
        self.rebuild()
