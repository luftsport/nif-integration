import json
import requests
from nif_api import NifApiIntegration
from settings import (
    API_HEADERS, API_URL,
    NIF_INTEGRATION_URL,
    ACLUBU, ACLUBP,
    NIF_REALM,
    NLF_ORG_STRUCTURE
)
from eve_api import EveJSONEncoder
from geocoding import add_organization_location

from pprint import pprint


class NifOrganization:
    def __init__(self, org_id):
        self.org_id = org_id
        self.org = {}
        self._get_org()

    def _get_org(self):
        resp = requests.get('{}/organizations/{}'.format(API_URL, self.org_id),
                            headers=API_HEADERS)

        if resp.status_code == 200:

            self.org = resp.json()
        else:
            raise Exception('No organization found')

    @property
    def _id(self):
        return self.org.get('_id', False)

    @property
    def activities(self):
        return self.org.get('activities', [])

    @property
    def main_activity(self):
        return self.org.get('main_activity', {})

    @property
    def created(self):
        return self.org.get('created', False)

    @property
    def describing_name(self):
        return self.org.get('describing_name', False)

    @property
    def is_active(self):
        return self.org.get('is_active', False)

    @property
    def name(self):
        return self.org.get('name', '')

    @property
    def org_type_id(self):
        return self.org.get('organization_type_id', False)


class NifOrganizations:
    raise Exception('Error in ')
    allowed = [1, 2, 4, 6, 14, 8, 5, 19, 26]

    not_orgs = [1, 523382]

    i = 0

    orgs_list = []

    orgs = []

    activities = []

    nlf_activities = [27, 237, 238, 109, 110, 111, 236, 235]  # [370,371,372,373,374,375,376,377,378,379]

    # org_id: {activity_id, name}
    """
    NLF_ORG_STRUCTURE = {376: {'id': 27, 'name': 'Luftsport'},  # Luftsportsforbundet
                          203030: {'id': 237, 'name': 'Mikrofly'},
                          203025: {'id': 238, 'name': 'Motorfly'},
                          90972: {'id': 109, 'name': 'Fallskjerm'},
                          90969: {'id': 110, 'name': 'HPG'},
                          90968: {'id': 111, 'name': 'Seilfly'},
                          203027: {'id': 236, 'name': 'Modellfly'},
                          203026: {'id': 235, 'name': 'Ballong'},
                          523382: {'id': 27, 'name': 'Luftsport'},  # FAI
                          1: {'id': 27, 'name': 'Luftsport'}  # NIF
                          }
    """

    dbg_orgs = []

    def __init__(self, org_id, log_file):

        self.log_file = log_file
        self.start_org_id = org_id

        self.integration_client = NifApiIntegration(username=ACLUBU,
                                                    password=ACLUBP,
                                                    realm=NIF_REALM,
                                                    log_file=self.log_file)

        self.faults = []

    def get_org(self, org_id, activity=[]):
        """Get all orgs recursively from a start org_id"""

        print('GET ORG', org_id)
        # Testing
        # if self.i > 4:
        #    raise Exception('Out of numbers')

        self.i = self.i + 1
        if self.i > 10000:
            raise ValueError("To many iterations %i" % self.i)

        if org_id in self.orgs_list:
            raise ValueError("Already exists in org list")

        self.orgs_list.append(org_id)

        # Hmm funny
        # if org_id in [1, 523382]:  # NIF & FAI
        status, org = self.integration_client.get_organization(org_id, NLF_ORG_STRUCTURE)

        if status is True:
            if org['type_id'] == 2 and org_id != 376:
                raise ValueError('Not correct federation {}'.format(org_id))

            if org['type_id'] in [4, 5, 6, 14] and org['main_activity'].get('id', 0) not in self.nlf_activities and len(
                    [x['id'] for x in org['activities'] if x.get('id', 0) in self.nlf_activities]) == 0:
                pprint(org)
                raise ValueError('No airsport main_activity {}'.format(org_id))

            self.dbg_orgs.append(org)
            self.orgs.append(org)

            for up in org.get('_up', []):
                if up['id'] not in self.orgs_list and org_id not in self.not_orgs and org['type_id'] != 8:
                    try:
                        self.get_org(up['id'])
                    except Exception as e:
                        print('Err up {}'.format(up['id']), str(e))
                        pass

            for down in org.get('_down', []):
                if down['id'] not in self.orgs_list and org_id not in self.not_orgs:
                    try:
                        self.get_org(down['id'])
                    except Exception as e:
                        print('Err down {}'.format(down['id']), str(e))
                        pass

    def get_org_legacy(self, org_id, activity=[]):
        """Get all orgs recursively from a start org_id"""

        # Testing
        # if self.i > 4:
        #    raise Exception('Out of numbers')

        self.i = self.i + 1
        if self.i > 10000:
            raise ValueError("To many iterations %i" % self.i)

        if org_id in self.orgs_list:
            raise ValueError("Already exists in org list")

        self.orgs_list.append(org_id)

        if org_id in [1, 523382]:  # NIF & FAI
            org = self.integration_client.service.OrganisationsGet(Ids=[org_id])
            org['Org'] = org['Orgs']['OrgPublic'][0]
        else:
            try:
                org = self.integration_client.service.OrgGet(OrgId=org_id)

            except Exception as e:  # Fallback to OrganisationsGet
                org = self.integration_client.service.OrganisationsGet(Ids=[org_id])
                org['Org'] = org['Orgs']['OrgPublic'][0]

                if len(activity) == 2:  # From group to club
                    if 'MainActivity' not in org['Org']:  # Set same as group
                        org['Org']['MainActivity'] = activity[0]
                        org['Org']['Activities'] = activity[1]
                else:
                    self.faults.append(org_id)

                    # self.dbg_org.append({'err': '', 'id':, 'name'})
        self.dbg_orgs.append(org['Org'])
        # Construct own structure for graph
        org_up = []
        org_down = []

        # Activities
        # Section
        if org_id in self.NLF_ORG_STRUCTURE:
            self.activities.append({'id': self.NLF_ORG_STRUCTURE[org_id]['id'],
                                    'name': self.NLF_ORG_STRUCTURE[org_id]['name']}
                                   )
        else:
            self.activities.append(
                {'id': org['Org']['MainActivity']['ActivityId'],
                 'name': org['Org']['MainActivity']['Name']}
            )

        # 'id': org['Org']['MainActivity']['ActivityCode']

        if org['Org']['OrganizationTypeId'] == 2 and org_id != 376:
            raise ValueError("Ikke særforbunder vårt %i" % org_id)

        if org['Org']['OrganizationTypeId'] in [4, 5, 6, 14] \
                and org['Org']['MainActivity']['ActivityId'] not in self.nlf_activities:
            raise ValueError("Ikke luftsport main activity %i" % org_id)

        for up in org['Org']['OrgStructuresUp']['OrgStructurePublic']:
            if up['OrgIdParent'] != org_id and up['OrgTypeIdParent'] in self.allowed:
                org_up.append(up)  # {'id': up['OrgIdParent'], 'type': up['OrgTypeIdParent']})

                if org_id not in self.not_orgs and up['OrgIdParent'] not in self.orgs_list and org['Org'][
                    'OrganizationTypeId'] != 8:

                    try:
                        self.get_org(up['OrgIdParent'])
                        """
                        if org['Org']['OrganizationTypeId'] == 6:  # Group up to club
                            self.get_org(org_id=up['OrgIdParent'],
                                    activitiy=[org['Org']['MainActivity'], org['Org']['Activities']])
                        else:
                            self.get_org(up['OrgIdParent'])
                        """
                    except:
                        pass

        for down in org['Org']['OrgStructuresDown']['OrgStructurePublic']:
            if down['OrgIdChild'] != org_id and down['OrgTypeIdChild'] in self.allowed and org['Org'][
                'OrganizationTypeId'] != 8:

                org_down.append(down)  # {'id': down['OrgIdChild'], 'type': down['OrgTypeIdChild']})

                if org_id not in self.not_orgs and down['OrgIdChild'] not in self.orgs_list:
                    try:
                        self.get_org(down['OrgIdChild'])
                    except:
                        # print("Down ERR: %s" % down['OrgIdChild'])
                        pass

        org['Org']['OrgStructuresDown']['OrgStructurePublic'] = org_down
        org['Org']['OrgStructuresUp']['OrgStructurePublic'] = org_up

        # self.orgs.append(org['Org'])
        self.orgs.append(org)

    def _update(self, payload):

        resp = requests.post('{}/organizations/process'.format(API_URL),
                             data=json.dumps(payload, cls=EveJSONEncoder),
                             headers=API_HEADERS)

        if resp.status_code == 422:

            try:
                resp_org = NifOrganization(payload['id'])

                resp = requests.put('{}/organizations/process/{}'.format(API_URL, resp_org._id),
                                    data=json.dumps(payload, cls=EveJSONEncoder),
                                    headers=API_HEADERS)
            except:
                pass

    def insert_orgs(self):
        """Convert every nif org object to lungo format
        - then insert if not exists
        - replace if exists and modified > _updated"""

        for o in self.orgs:
            tmp = add_organization_location(o)
            self._update(tmp)

    def get_activities(self):
        """Just return all unique activities"""
        keys = []
        act = []
        for a in self.activities:
            if a['id'] not in keys:
                # print(a)
                pass
            keys.append(a['id'])
            act.append(a)

        return act
