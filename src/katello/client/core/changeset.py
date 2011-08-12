#
# Katello Organization actions
# Copyright (c) 2010 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public License,
# version 2 (GPLv2). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. You should have received a copy of GPLv2
# along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
#
# Red Hat trademarks are not licensed under GPLv2. No permission is
# granted to use or replicate Red Hat trademarks that are incorporated
# in this software or its documentation.
#

import os
import urlparse
from gettext import gettext as _
from optparse import OptionValueError
from pprint import pprint

from katello.client.api.changeset import ChangesetAPI
from katello.client.config import Config
from katello.client.core.base import Action, Command
from katello.client.core.utils import system_exit, is_valid_record, get_abs_path, run_spinner_in_bg, format_date, wait_for_async_task
from katello.client.api.utils import get_environment, get_changeset

try:
    import json
except ImportError:
    import simplejson as json

Config()


# base changeset action ========================================================
class ChangesetAction(Action): 

    def __init__(self):
        super(ChangesetAction, self).__init__()
        self.api = ChangesetAPI()
        
# ==============================================================================
class List(ChangesetAction):

    description = _('list new changesets of an environment')

    def setup_parser(self):
        self.parser.add_option('--org', dest='org',
                               help=_("name of organization (required)"))
        self.parser.add_option('--environment', dest='env',
                               help=_("environment name (required)"))

    def check_options(self):
        self.require_option('org')
        self.require_option('env', '--environment')

    def run(self):
        orgName = self.get_option('org')
        envName = self.get_option('env')
        
        env = get_environment(orgName, envName)
        if env == None:
            return os.EX_DATAERR

        
        changesets = self.api.changesets(orgName, env['id'])
        for cs in changesets:
            cs['updated_at'] = format_date(cs['updated_at'])

        self.printer.addColumn('id')
        self.printer.addColumn('name')
        self.printer.addColumn('updated_at')
        self.printer.addColumn('state')
        self.printer.addColumn('environment_id')
        self.printer.addColumn('environment_name')
        
        self.printer.setHeader(_("Changeset List"))
        self.printer.printItems(changesets)
        return os.EX_OK
        
        
# ==============================================================================
class Info(ChangesetAction):

    description = _('detailed information about a changeset')

    def setup_parser(self):
        self.parser.add_option('--org', dest='org',
                               help=_("name of organization (required)"))
        self.parser.add_option('--environment', dest='env',
                               help=_("environment name (required)"))
        self.parser.add_option('--name', dest='name',
                               help=_("changeset name (required)"))
                               
    def check_options(self):
        self.require_option('org')
        self.require_option('name')
        self.require_option('env', '--environment')

    def run(self):
        orgName = self.get_option('org')
        envName = self.get_option('env')
        csName = self.get_option('name')
        
        cset = get_changeset(orgName, envName, csName)
        if cset == None:
            return os.EX_DATAERR

        cset['updated_at'] = format_date(cset['updated_at'])
        cset['environment_name'] = envName

        cset["errata"]   = "\n".join([e["display_name"] for e in cset["errata"]])
        cset["products"] = "\n".join([p["name"] for p in cset["products"]])
        cset["packages"] = "\n".join([p["display_name"] for p in cset["packages"]])
        cset["repositories"] = "\n".join([r["display_name"] for r in cset["repos"]])

        self.printer.addColumn('id')
        self.printer.addColumn('name')
        self.printer.addColumn('updated_at')
        self.printer.addColumn('state')
        self.printer.addColumn('environment_id')
        self.printer.addColumn('environment_name')
        self.printer.addColumn('errata', multiline=True, show_in_grep=False)
        self.printer.addColumn('products', multiline=True, show_in_grep=False)
        self.printer.addColumn('packages', multiline=True, show_in_grep=False)
        self.printer.addColumn('repositories', multiline=True, show_in_grep=False)
        
        self.printer.setHeader(_("Changeset Info"))
        self.printer.printItem(cset)
        return os.EX_OK
        

# ==============================================================================
class Create(ChangesetAction):

    description = _('create a new changeset for an environment')

    def setup_parser(self):
        self.parser.add_option('--org', dest='org',
                               help=_("name of organization (required)"))
        self.parser.add_option('--environment', dest='env',
                               help=_("environment name (required)"))
        self.parser.add_option('--name', dest='name',
                               help=_("changeset name (required)"))
                               
    def check_options(self):
        self.require_option('org')
        self.require_option('name')
        self.require_option('env', '--environment')

    def run(self):
        orgName = self.get_option('org')
        envName = self.get_option('env')
        csName = self.get_option('name')
        
        env = get_environment(orgName, envName)
        if env != None:

            cset = self.api.create(orgName, env["id"], csName)
            if is_valid_record(cset):
                print _("Successfully created changeset [ %s ] for environment [ %s ]") % (cset['name'], env["name"])
            else:
                print _("Could not create changeset [ %s ] for environment [ %s ]") % (cset['name'], env["name"])

        return os.EX_OK
        
        
# ==============================================================================
class UpdateContent(ChangesetAction):
    
    description = _('updates content of a changeset')

    def __init__(self):
        self.current_product = None
        self.items = {}
        super(UpdateContent, self).__init__()


    def store_from_product(self, option, opt_str, value, parser):
        self.current_product = value
        parser.values.from_product = True


    def store_item(self, option, opt_str, value, parser):
        if parser.values.from_product == None:
            raise OptionValueError(_("%s must be preceded by %s") % (option, "--from_product") )

        self.items[option.dest].append({"name": value, "product": self.current_product})
        

    def setup_parser(self):
        self.parser.add_option('--name', dest='name',
                                help=_("changeset name (required)"))
        self.parser.add_option('--org', dest='org',
                                help=_("name of organization (required)"))
        self.parser.add_option('--environment', dest='env',
                                help=_("environment name (required)"))
        self.parser.add_option('--add_product', dest='add_product',
                                action="append",
                                help=_("product to add to the changeset"))
        self.parser.add_option('--remove_product', dest='remove_product',
                                action="append",
                                help=_("product to remove from the changeset"))                                
        self.parser.add_option('--from_product', dest='from_product',
                                action="callback", callback=self.store_from_product, type="string",
                                help=_("determines product from which the packages/errata/repositories are picked"))

        for ct in ['package', 'erratum', 'repo']:
            self.parser.add_option('--add_'+ct, dest='add_'+ct,
                                action="callback", callback=self.store_item, type="string",
                                help=_(ct+" to add to the changeset"))
            self.parser.add_option('--remove_'+ct, dest='remove_'+ct,
                                action="callback", callback=self.store_item, type="string",
                                help=_(ct+" to remove from the changeset"))
        self.reset_items()

    def reset_items(self):
        for ct in ['package', 'erratum', 'repo']:
            self.items['add_'+ct]    = []
            self.items['remove_'+ct] = []        

    def check_options(self):
        self.require_option('name')
        self.require_option('org')
        self.require_option('env', '--environment')


    def run(self):
        #reset stored patch items (neccessary for shell mode)
        items = self.items.copy()
        self.reset_items()
        
        csName  = self.get_option('name')
        orgName = self.get_option('org')
        envName = self.get_option('env')

        cset = get_changeset(orgName, envName, csName)
        if cset == None:
           return os.EX_DATAERR
        
        patch = {}
        patch['+packages'] = items["add_package"]
        patch['-packages'] = items["remove_package"]
        patch['+errata'] = items["add_erratum"]
        patch['-errata'] = items["remove_erratum"]
        patch['+repos'] = items["add_repo"]
        patch['-repos'] = items["remove_repo"]
        patch['+products'] = self.get_option('add_product') or []
        patch['-products'] = self.get_option('remove_product') or []

        msg = self.api.update_content(orgName, cset["environment_id"], cset["id"], patch)
        print _("Successfully updated changeset [ %s ]") % csName
        
        return os.EX_OK
        
        
# ==============================================================================
class Delete(ChangesetAction):
    
    description = _('deletes a changeset')

    def setup_parser(self):
        self.parser.add_option('--name', dest='name',
                               help=_("changeset name (required)"))
        self.parser.add_option('--org', dest='org',
                               help=_("name of organization (required)"))
        self.parser.add_option('--environment', dest='env',
                               help=_("environment name (required)"))

    def check_options(self):
        self.require_option('name')
        self.require_option('org')
        self.require_option('env', '--environment')

    def run(self):
        csName  = self.get_option('name')
        orgName = self.get_option('org')
        envName = self.get_option('env')

        cset = get_changeset(orgName, envName, csName)
        if cset == None:
            return os.EX_DATAERR
  
        msg = self.api.delete(orgName, cset["environment_id"], cset["id"])
        print msg
        return os.EX_OK
        

# ==============================================================================
class Promote(ChangesetAction):
    
    description = _('promotes a changeset to the next environment')

    def setup_parser(self):
        self.parser.add_option('--name', dest='name',
                               help=_("changeset name (required)"))
        self.parser.add_option('--org', dest='org',
                               help=_("name of organization (required)"))
        self.parser.add_option('--environment', dest='env',
                               help=_("environment name (required)"))

    def check_options(self):
        self.require_option('name')
        self.require_option('org')
        self.require_option('env', '--environment')

    def run(self):
        csName  = self.get_option('name')
        orgName = self.get_option('org')
        envName = self.get_option('env')

        cset = get_changeset(orgName, envName, csName)
        if cset == None:
            return os.EX_DATAERR
  
        try:
            task = self.api.promote(orgName, cset["environment_id"], cset["id"])
        except Exception, e:
            system_exit(os.EX_DATAERR, _("Error: %s" % e))
        
        result = run_spinner_in_bg(wait_for_async_task, [task], message=_("Promoting the changeset, please wait... "))

        if result['state'] == 'finished':    
            print _("Changeset [ %s ] promoted" % csName)
            return os.EX_OK
        else:
            print _("Changeset [ %s ] promotion failed: %s" % (csName, json.loads(result["result"])['errors'][0]))
            return os.EX_DATAERR


# changeset command ============================================================
class Changeset(Command):
    description = _('changeset specific actions in the katello server')
    
