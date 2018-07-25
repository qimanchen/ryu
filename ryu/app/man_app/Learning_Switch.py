#!/usr/bin/env python
# -*- coding: utf-8 -*-
from ryu.base import app_manager
from ryu.ofproto import ofproto_v1_3
from ryu.controller import ofp_event
from ryu.controller.handler import set_ev_cls
from ryu.controller.handler import CONFIG_DISPATCHER,MAIN_DISPATCHER
from ryu.lib.packet import packet,ethernet
from ryu.lib.packet import ether_types

class LearningSwitch(app_manager.RyuApp):
    """Learning a self learning switch
       time: 20180724
    """
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self,*args,**kwargs):
        super(LearningSwitch,self).__init__(*args,**kwargs)
        # mac data library
        self.mac_to_port = {}

    # switch link with controller
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures,CONFIG_DISPATCHER)
    def switch_features_handler(self,ev):

        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        ofp_parser = datapath.ofproto_parser

        # install the table miss flow entry
        match = ofp_parser.OFPMatch()
        actions = [ofp_parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,ofproto.OFPCML_NO_BUFFER)]

        self.add_flow(datapath,0,match,actions)


    def add_flow(self,datapath,priority,match,actions):
        # add a flow entry, and install it into datapath
        ofproto = datapath.ofproto
        ofp_parser = datapath.ofproto_parser

        # Construct a flow_mod msg and sent it
        inst = [ofp_parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,actions)]

        mod = ofp_parser.OFPFlowMod(datapath=datapath,priority=priority,
                                    match=match,instructions=inst)

        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        ofp_parser = datapath.ofproto_parser

        # get datapath id to identify openflow switch
        dpid = datapath.id # switch id
        if dpid not in self.mac_to_port:
            self.logger.info("add new Switch %s to mac_to_port",dpid)
            self.mac_to_port.setdefault(dpid,{})

        # store the information
        # parse and analysis the received packets
        pkt = packet.Packet(msg.data) # parser the flow
        eth_pkt = pkt.get_protocol(ethernet.ethernet)

        if eth_pkt.ethertype == ether_types.ETH_TYPE_LLDP:
            # ignore lldp packet
            return
        dst = eth_pkt.dst # destination mac address
        src = eth_pkt.src
        in_port = msg.match['in_port']

        self.logger.info("packet in %s %s %s %s",dpid,src,dst,in_port)

        # learn a src mac address to avoid Flood in next time
        self.mac_to_port[dpid][src] = in_port

        # if dst mac address has already exist
        # decide which port to send the packets, otherwise flood
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        # construct actions
        actions = [ofp_parser.OFPActionOutput(out_port)]
        # OFPActionOutput(port, max_len=ofproto.OFPCML_MAX,type_=None, len_=None):

        # install flow mod msg
        if out_port != ofproto.OFPP_FLOOD:
            match = ofp_parser.OFPMatch(in_port=in_port,eth_dst=dst)
            self.add_flow(datapath,1,match,actions)

        # send packet out
        out = ofp_parser.OFPPacketOut(
            datapath=datapath,buffer_id=msg.buffer_id,in_port=in_port,
            actions=actions
        )
        datapath.send_msg(out)
