# -*- coding: utf-8 -*-
# pylint: disable=W0604,W0312,W0102,W0232,C1001
'''
Follow the output of the same dataport alias on multiple clients.

The default behavior is to look at all client resources below the <pcik> 
and do the following:
 1. Identify all client resources that contain dataport alias <alias>, 
    by either --usetoken or <ciks_and/or_shortcut> list. Default behavior
    is to use <pcik> to look through all aliases of its 2nd generation 
    clients.
 2. Refine the set of client resources by the <cik_and/or_shortcut> list.
 3. If --usetoken is provided, disregard <cik_and/or_shortcut> list. Uses RID list
    of <model> from Provisioning API. If <model> not provided, it defaults to 
    use all RIDS from all known models.
 4. If --model=<model> provided, refine set of client resources by 
    comparing:
        >>> <model> == client.description.meta.device.model
    If --model provided and no model matches can be made, try using --token
    since this device does not conform to standard practice of putting model
    info in meta as JSON object.

Usage:
    exo [options] tailias <pcik> <alias> [options]
    exo [options] tailias <pcik> <alias> <ciks_and/or_keys>... [options]
    exo [options] tailias <pcik> <alias> --usetoken [options]
    exo [options] tailias <pcik> <alias> --model=<model> [options]
    exo [options] tailias <pcik> <alias> --usetoken --model=<model> [options]
    exo [options] tailias <pcik> <alias> (--usetoken | <ciks_and/or_keys>...) [options]

Options:
    --model=<model>         When used and <ciks_and/or_keys> is not used, 
                            tail the given alias of all clients of model 
                            <model>. Will try to find VENDORTOKEN in 
                            ~/.exoline file or can be specified with 
                            --vendor and --token.
    --usetoken              Use the Provisioning API to
                            retrieve the list of rids that belong to 
                            the model specified by --model.
    --jq=<json_keys>        Supports *some* jq-style key parsing (experimental).
    --once                  Do not set up any Websocket subscribes. Do one
                            read of each resource and exit.
    --fullrid               When printing the results to screen, the default
                            is to use a short-RID which is the first 8
                            characters. Use this option to print the full
                            RID of the resource.
    --raw                   Only show the RID and the data. Exclude timestamp
                            when printing data.
    --timeout=<timeout>     Specify a timeout in milliseconds for
                            restarting the RPC 'wait' connection.
    --limit=<limit>         Specify the amount of values you want
                            shown before the wait call is made.
    --verbose               Print out debug information.
{{ helpoption }}
'''
from exoline import __version__ as VERSION
import threading, json, queue
from datetime import datetime
from .keys import Keys, Vendor
from exoline.exoconfig import ExoConfig # needed by Keys
# from exoline.serieswriter import SeriesWriter
from .ws import OPWSS, MethodThread
from pyonep import onep
from pyonep.provision import Provision

DEFAULT_TIMEOUT = 1000 # milliseconds

global verbosity
verbosity = 0

def debug(message):
    if verbosity > 0:
        print(message)

def jqlite(options, parse_this):
    """ Function that serves as a 'jq'-lite for parsing
    through json objects according to a dot-notation.

    Example:
    >>> obj = {"This": [{"is":"a", "JSON":"object"}, {"and":"it", "hurts":true}]}
    >>> print(jqlite('This.1.and', obj))
    it
    """
    tmp = parse_this
    try:
        tmp = json.loads(tmp)
        lookahead_idx = 0
        # print("OPTIONS: ", options.split('.'))
        opts = options.split('.')
        for idx, opt in enumerate(opts):
            # try to convert numbers from strings
            try:
                opt = int(opt)
            except ValueError:
                pass
            if ':' == opt:
                # this means that we're going to parse a list
                # until we find the object pointed to by the
                # next key
                for i in range(0,len(tmp)):
                    # print(opts[i], opts[idx+1])
                    if tmp[i].get(opts[idx+1]):
                        lookahead_idx = i
            elif ':' == opts[idx-1]:
                tmp = tmp[lookahead_idx][opt]
            elif '' != opt:
                tmp = tmp[opt]
    except ValueError:
        pass
    return tmp

class Printer():
    def __init__(self, _id, timestamp, data, fullid=False, raw=False):
        self.id = _id
        self.timestamp = timestamp
        self.data = data
        self.fullid = fullid
        self.raw = raw

    def now(self, timestamp):

        return( datetime.fromtimestamp(
                    int(timestamp)
                ).strftime('%Y-%m-%d %H:%M:%S')
        )
    def Print(self):
        fmt = "{0} >>> {1},{2}".format(self.id[:8], self.now(self.timestamp), self.data)
        if self.fullid and not self.raw:
            fmt = "{0} >>> {1},{2}".format(self.id, self.now(self.timestamp), self.data)
        elif self.fullid and self.raw:
            fmt = "{0} >>> {1}".format(self.id, self.data)
        elif not self.fullid and self.raw:
            fmt = "{0} >>> {1}".format(self.id[:8], self.data)
        print(fmt)

class Plugin():
    def __init__(self):
        self.kill = threading.Event()
    def command(self): # pylint: disable=R0201
        return 'tailias'
    def run(self, cmd, args, options): # pylint: disable=R0201
        global verbosity # pylint: disable=I0011,W0603

        # this plugin only supports tokens with regards to Provisioning API
        opprov = Provision(port=443, https=True, manage_by_cik=False)
        op = onep.OnepV1(port=443, https=True)
        # parent cik passed as 1st arg on cli
        pcik = args['<pcik>']
        # parent cik might be a ~/.exoline shortcut
        try:
            pcik = Keys(ExoConfig()).show(pcik)
        except: # pylint: disable=I0011,W0702
            pass

        alias = args['<alias>']
        cik_list = args.get('<ciks_and/or_keys>')
        verbosity = 1 if args['--verbose'] else 0
        rpc = options['rpc']
        opts = {'timeout': args['--timeout']} if args['--timeout'] else {}
        all_rids = []
        tail_rids = []
        cik_clients = {}

        # gather args
        if args.get('--limit'):
            opts['limit'] = int(args['--limit'][0])
        if args.get('--jq'):
            opts['jq'] = args['--jq'][0]
        if args.get('--model'):
            opts['model'] = args['--model']
        if args.get('--fullrid'):
            fullrid = True
        else:
            fullrid = False
        if args.get('--raw'):
            raw = True
        else:
            raw = False
        if args.get('--usetoken'):
            # provisioning api method
            vendortoken = Vendor(ExoConfig()).showtoken()
            model_list = []

            if opts.get('model'):
                model_list.append(opts['model'])
            else:
                response = opprov.model_list(vendortoken)
                if "OK" == response.reason():
                    model_list = response.body.split('\r\n')
                else:
                    print(response)
                    print("Couldn't retrieve list of client models.")

            for model in model_list:
                response = opprov.serialnumber_list(vendortoken, model)
                if "OK" == response.reason():
                    snlist = response.body
                    model_rids = [    x.split(',')[1] for x in snlist.split('\n') \
                                    if len(x.split(',')) == 3 
                    ]
                    # get all dataport aliases of client resources
                    for rid in model_rids:
                        op.info(
                            {'cik': pcik}, 
                            rid, 
                            {"aliases":True}, 
                            defer=True
                        )
                    response = op.send_deferred({'cik': pcik})
                    for val in response:
                        if val[1]:
                            rid = val[0]['arguments'][0]
                            model_rids.append(rid)
                            aliases = val[2]['aliases']
                            for rid in aliases:
                                if alias in aliases[rid]:
                                    tail_rids.append( rid )
                else:
                    print("Couldn't retrieve RIDs for model: {!r}".format(model))

        else: # default method
            # if ciks not provided, get all client resources of pcik
            model = opts.get('model')
            if [] == cik_list: # ciks not provided
                response = op.listing({'cik': pcik},["client"])
                model_rids = []
                if response[0]:
                    all_client_rids = response[1][0]
                    for client_rid in all_client_rids:
                        op.info(
                            {'cik': pcik}, 
                            client_rid, 
                            {"aliases":True, "description":True}, 
                            defer=True
                        )
                    response = op.send_deferred({'cik': pcik})
                    if response[1]:
                        # iterate through every client's info
                        for val in response:
                            # first, match all client aliases
                            # then, remove matches that don't match model
                            # do it this way in case the match model via meta
                            # doesn't work. atleast you'll have every alias
                            # that matches the one you're looking for.
                            aliases = val[2]['aliases']
                            for rid in aliases:
                                # if it's an alias match, append it to the list of tail_rids
                                if alias in aliases[rid]:
                                    tail_rids.append( rid )
                                    # make best attempt to pop the previous rid if 
                                    # it doesn't pass the meta model match
                                    meta = None
                                    try:
                                        meta = json.loads(val[2]['description']['meta'])
                                        # make sure models match
                                        # print(model, meta['device']['model'])
                                        if not model == meta['device']['model'] and None != model:
                                            # if they don't match, throw out the last one.
                                            tail_rids.pop()
                                    except ValueError:
                                        pass
                                    except KeyError:
                                        pass
            else: # ciks and/or shortcuts provided
                # first, get actual ciks from keys file
                tmp = []
                for cik in cik_list:
                    try:
                        # make best attempt at using .exoline keys
                        cik = Keys(ExoConfig()).show(cik)
                    except: # pylint: disable=I0011,W0702
                        pass
                    tmp.append(cik)
                cik_list = tmp

                # iterate through clients to find the rid of <alias>
                for cik in cik_list:
                    # TODO: can speed this up if use parent cik and defer!?
                    result = rpc.info({'cik':cik}, {"alias": ""} ,{"aliases": True})

                    for rid in result['aliases']:
                        if alias in result['aliases'][rid]:
                            cik_clients[cik] = {'rid': rid}
                            tail_rids.append(rid)

                    # it's entirely possible that the alias doesn't exist in any
                    # of the clients the user wants...
                    if None == cik_clients.get(cik):
                        print("Alias {!r} not found in client {!r}".format(alias, cik))
                
                # if 'clients' is empty, don't bother continuing
                if {} == cik_clients:
                    self.kill.set()

        limit=1 if not opts.get('limit') else opts['limit']
        # read an initial value
        for tail_rid in tail_rids:
            
            read = op.read(
                {'cik': pcik},
                tail_rid,
                { "limit":limit,"sort":"desc"},
                defer = True
            )
        response = op.send_deferred({'cik': pcik})
        # print(response)
        for val in response:
            if val[1]:
                tail_rid = val[0]['arguments'][0]
                # print(val[2])
                # check for case of no data in dataport
                for idx in range(0,limit):
                    if idx < len(val[2]):
                        data = val[2][idx][1]
                        timestamp = val[2][idx][0]
                        if opts.get('jq'):
                            data = jqlite(opts['jq'], data)
                    else:
                        data = None
                        timestamp = 0
                    Printer(tail_rid, timestamp, data, fullrid, raw).Print()

        if args.get('--once'):
            self.kill.set()

        # prepare websocket
        wss = OPWSS(pcik, self.kill)
        rpcid = 0
        tails = []

        rid_tails = { k:{} for k in tail_rids}

        for tail_rid in rid_tails:
            # get clients' rids of alias
            # make rpc call
            tails.append(
                {
                    "id": rpcid, 
                    "procedure": "subscribe", 
                    "arguments": [
                      tail_rid,
                      {
                        # "since": <timestamp>,
                        # "timeout": 1000*60*5, # 5 minutes
                        # ("subs_id": <subs_id>)
                      }
                    ]
                  }
            )
            rid_tails[tail_rid]['id'] = rpcid
            rpcid+=1

        wss.Q_in.put({"calls": tails})

        ws_thread = MethodThread(wss.run_forever, ())
        ws_thread.start()

        while not self.kill.is_set():
            try:
                q_data = wss.Q_out.get(True,1)
                msgs = json.loads( q_data ) if q_data else None
                # print("q: ", q_data)
                if None == msgs:
                    print("continue")
                    continue
                # msgs can be a dictionary: {"status": "ok"}
                # or it can be a list
                elif isinstance(msgs,dict):
                    if msgs.get('status') == "ok":
                        pass # this is what usually happens for the auth response
                    else:
                        print(msgs)
                elif isinstance(msgs, list):
                    for msg in msgs:
                        result = msg.get('result')
                        if result:
                            for tail_rid in rid_tails:
                                if rid_tails[tail_rid]['id'] == msg['id']:
                                    data = result[1]
                                    # support jq-style parsing
                                    if opts.get('jq'):
                                        data = jqlite(opts['jq'], data)

                                    Printer(tail_rid, timestamp, data, fullrid, raw).Print()
                else:
                    print("type {0} not supported: {1}".format(type(msgs), msgs))
            except queue.Empty:
                pass


