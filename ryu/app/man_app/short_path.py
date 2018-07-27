#!/usr/bin/env python
# -*- coding: utf-8 -*-

from ryu.base import app_manager
from ryu.ofproto import ofproto_v1_3
from ryu.controller.handler import set_ev_cls
from ryu.controller.handler import CONFIG_DISPATCHER,MAIN_DISPATCHER
from ryu.controller import ofp_event
from ryu.lib.packet import packet,ethernet
from ryu.topology import event
from ryu.topology.api import get_switch,get_link

import networkx as nx

class ShortPath(app_manager.RyuApp):
    """test"""

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self,*args,**kwargs):
        super(ShortPath,self).__init__(*args,**kwargs)
        self.network = nx.DiGraph()
        self.topology_api_app = self
        self.paths = {}
        # self.mac_to_port = {}

    # handler switch features info
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures,CONFIG_DISPATCHER)
    def switch_features_handler(self,ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        ofp_parser = datapath.ofproto_parser

        # install table miss flow entry for each datapath
        match = ofp_parser.OFPMatch()
        actions = [ofp_parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                              ofproto.OFPCML_NO_BUFFER)]
        # install flow entry
        self.add_flow(datapath,0,match,actions)

    # send a flow
    def add_flow(self,datapath,priority,match,actions):
        ofproto = datapath.ofproto
        ofp_parser = datapath.ofproto_parser

        # construct a flow mod msg and send it to datapath
        inst = [ofp_parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                                 actions)]
        mod = ofp_parser.OFPFlowMod(datapath=datapath,priority=priority,
                                    match=match,instructions=inst)
        datapath.send_msg(mod)

    # get topology and store it into network object
    @set_ev_cls(event.EventSwitchEnter,[CONFIG_DISPATCHER,MAIN_DISPATCHER])
    def get_topology(self,ev):
        # get nodes
        switch_list = get_switch(self.topology_api_app,None)
        switches = [switch.dp.id for switch in switch_list]
        self.network.add_nodes_from(switches)

        # get links
        links_list = get_link(self.topology_api_app,None)
        # print "links_list -> ",links_list
        links = [(link.src.dpid,link.dst.dpid,{'port':link.src.port_no}) for link in links_list]
        # print "links->:",links
        self.network.add_edges_from(links)

        # resource links
        links = [(link.dst.dpid, link.src.dpid, {'port':link.dst.port_no}) for link in links_list]
        self.network.add_edges_from(links)

    # get out port by using networkx's Dijkstra algorithm
    def get_out_port(self,datapath,eth_src,eth_dst,in_port):
        dpid = datapath.id

        # add links between host and access switch
        if eth_src not in self.network:
            self.network.add_node(eth_src)
            self.network.add_edge(dpid,eth_src,port=in_port)
            self.network.add_edge(eth_src,dpid)
            self.paths.setdefault(eth_src,{}) # eth_dst:[1,2,3,4]

        # search eth_dst's shortest path.
        if eth_dst in self.network:
            if eth_dst not in self.paths[eth_src]:
                path = nx.shortest_path(self.network,eth_src,eth_dst)
                self.paths[eth_src][eth_dst] = path

            path = self.paths[eth_src][eth_dst]
            next_hop = path[path.index(dpid)+1]
            out_port = self.network[dpid][next_hop]['port']
            print "out_port-> ",out_port
            print 'path-> ',path
        else:
            out_port = datapath.ofproto.OFPP_FLOOD
        return out_port

    # handler packet in msg
    @set_ev_cls(ofp_event.EventOFPPacketIn,MAIN_DISPATCHER)
    def packet_in_handler(self,ev):
        # get topology info
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        ofp_parser = datapath.ofproto_parser

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        in_port = msg.match['in_port']

        # get out_port info
        out_port = self.get_out_port(datapath,eth.src,eth.dst,in_port)
        actions = [ofp_parser.OFPActionOutput(out_port)]


        if out_port != ofproto.OFPP_FLOOD:
            match = ofp_parser.OFPMatch(in_port=in_port,eth_dst=eth.dst)
            self.add_flow(datapath,1,match,actions)

        # install flow entry
        out = ofp_parser.OFPPacketOut(datapath=datapath,buffer_id=msg.buffer_id,
                                      in_port=in_port,actions=actions)
        datapath.send_msg(out)
