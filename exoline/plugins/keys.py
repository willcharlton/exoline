# -*- coding: utf-8 -*-
'''Read and write CIK shortcuts in .exoline config

Usage:
    exo [options] keys
    exo [options] keys add <new_cik> <new_name>
    exo [options] keys rm <name>
    exo [options] keys show <name>
    exo [options] keys clean
    exo [options] keys wipe
    exo [options] keys setvendor <vendor>
    exo [options] keys settoken <vendortoken>
    exo [options] keys showvendor
    exo [options] keys showtoken

Command Options:
    --hack                 This option hacks the gibson.
    --comment=<comment>    Add comment to key.
{{ helpoption }}
'''

import ruamel.yaml as yaml
import os, re
from pyonep.exceptions import OnePlatformException

class Keys():
    def __init__(self, config_option):
        try:
            with open(config_option.configfile) as f:
                self.config = yaml.load(f, yaml.RoundTripLoader)
                if self.config['keys'] is None:
                    self.config['keys'] = {}
        except IOError as ex:
            self.config = {'keys': {}}
    def show(self, name):
        return self.config['keys'][name]

class Vendor():
    def __init__(self, config_option):
        try:
            with open(config_option.configfile) as f:
                self.config = yaml.load(f, yaml.RoundTripLoader)
                if self.config['vendor'] is None:
                    self.config['vendor'] = ''
                if self.config['vendortoken'] is None:
                    self.config['vendortoken'] = ''
        except IOError as ex:
            self.config = {'keys': {}}
    def showvendor(self):
        return self.config['vendor']
    def showtoken(self):
        return self.config['vendortoken']


class Plugin():
    regex_rid = re.compile("[0-9a-fA-F]{40}$")

    def command(self):
        return 'keys'

    def run(self, cmd, args, options):
        rpc = options['rpc']
        config_option = options['config']
        ExoException = options['exception']
        if config_option.configfile is None:
            # normally we don't mention this, but the keys command
            # needs a config file.
            raise ExoException('config file was not found: {0}'.format(
                config_option.askedconfigfile))
        o_keys = Keys(config_option)
        o_vend = Vendor(config_option)

        if len(args['<args>']) > 0:
            subcommand = args['<args>'][0]
        else:
            subcommand = None

        if subcommand == "add":
            cik = args["<new_cik>"]
            name = args["<new_name>"]

            if self.regex_rid.match(cik) is None:
                print("{0} is not a valid cik".format(cik))
                return

            o_keys.config['keys'][name] = cik

            if args.get('--comment', False):
                o_keys.config['keys'].yaml_add_eol_comment(args['--comment'], name)

            print("Added `{0}: {1}` to {2}".format(name, cik, config_option.configfile))
        elif subcommand == "rm":
            name = args["<name>"]

            if o_keys.config['keys'].get(name, None) == None:
                print("That key does not exist.")
                return

            del o_keys.config['keys'][name]
        elif subcommand == "show":
            name = args["<name>"]
            print("{0}: {1}".format(name, o_keys.show(name)))
        elif subcommand == "wipe":
            del o_keys.config['keys']
            o_keys.config['keys'] = {}
        elif subcommand == "clean":
            to_trim = []
            for name in o_keys.config['keys']:
                try:
                    print("Checking {0}...".format(name)),
                    rpc.info(o_keys.config['keys'][name], {'alias': ''}, {'basic': True})
                    print("OK")
                except OnePlatformException as e:
                    to_trim.append(name)
                    print("ERR (Removing)")

            if len(to_trim) > 0:
                for name in to_trim:
                    del o_keys.config['keys'][name]
        elif subcommand == "setvendor":
            vendor = args["<vendor>"]
            o_keys.config['vendor'] = vendor
            print("Set vendor to {0}".format(vendor))
        elif subcommand == "settoken":
            vendor = args["<vendor>"]
            o_keys.config['vendor'] = vendor
            print("Set vendor to {0}".format(vendor))
        elif subcommand == "showvendor":
            print("{0}".format(o_vendor.showvendor()))
        elif subcommand == "showtoken":
            print("{0}".format(o_vendor.showtoken()))
        else:
            if len(o_keys.config.get("keys", {})) > 0:
                print(" ".join(map(str, o_keys.config.get("keys", {}).keys())))

        with open(config_option.configfile, 'w') as f:
            f.write(yaml.dump(o_keys.config, Dumper=yaml.RoundTripDumper))
