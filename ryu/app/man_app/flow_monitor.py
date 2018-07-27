#!/usr/bin/env python
# -*- coding: utf-8 -*-

from operator import attrgetter
from ryu.app import simple_switch_13
from ryu.controller.handler import set_ev_cls
from ryu.controller.handler import MAIN_DISPATCHER,DEAD_DISPATCHER
from ryu.controller import ofp_event
from ryu.lib import hub

class FlowMonitor(simple_switch_13.SimpleSwitch13):
    """string fro description"""

    def __init__(self,*args,**kwargs):
        super(FlowMonitor,self).__init__(*args,**kwargs)
        self.datapaths = {}
        # add son thread for a monitor
        self.monitor_thread = hub.spawn(self._monitor)

    # get datapath info
    @set_ev_cls(ofp_event.EventOFPStateChange,[MAIN_DISPATCHER,DEAD_DISPATCHER])
    def _state_change_handler(self,ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.datapaths:
                self.datapaths[datapath.id] = datapath
                self.logger.debug("Regiseter datapath: %16x",datapath.id)

        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                del self.datapaths[datapath.id] # delete
                self.logger.debug("Unregister datapath: %16x",datapath.id)


    # send request msg periodically
    def _monitor(self):
        while True:
            for dp in self.datapaths.values():
                self._request_stats(dp)
            hub.sleep(10)


    # send stats request msg to datapath
    def _request_stats(self,datapath):
        ofproto = datapath.ofproto
        ofp_parser = datapath.ofproto_parser

        # send port stats request msg:
        req = ofp_parser.OFPPortStatsRequest(datapath,0,ofproto.OFPP_ANY)
        datapath.send_msg(req)

        # send flow stats request msg:
        req_flow = ofp_parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req_flow)
        self.logger.debug("send stats to requests to datapath: %16x", datapath.id)

    # handler the port stats reply msg.
    @set_ev_cls(ofp_event.EventOFPPortStatsReply,MAIN_DISPATCHER)
    def _port_stats_reply_handler(self,ev):
        body = ev.msg.body

        self.logger.info('datapath                   port     '
                         'rx-pkts        rx-bytes    rx-errors'
                         'tx-pkts        tx-bytes    tx-errors')
        self.logger.info('------------------------   -----------'
                         '--------------  --------   -----------'
                         '--------------  --------   -----------')
        for stat in sorted(body,key=attrgetter('port_no')):
            self.logger.info("%16x %8x %8d %8d %8d %8d %8d %8d",
                             ev.msg.datapath.id, stat.port_no,
                             stat.rx_packets,stat.rx_bytes,stat.rx_errors,
                             stat.tx_packets,stat.tx_bytes,stat.tx_errors)

    # handler the flow entry stats reply msg
    @set_ev_cls(ofp_event.EventOFPFlowStatsReply,MAIN_DISPATCHER)
    def _flow_state_reply_handler(self,ev):
        body = ev.msg.body

        self.logger.info('datapath----------------'
                         'in_port           eht_dst          '
                         'out_port          packets     bytes')
        self.logger.info('------------------------   -----------'
                         '--------------  --------   -----------'
                         '--------------  --------   -----------')
        for stat in sorted([flow for flow in body if flow.priority == 1],
                           key=lambda flow:(flow.match['in_port'],
                                            flow.match['eth_dst'])):
            self.logger.info("%16x %8x %8d %8d %8d %8d",
                             ev.msg.datapath.id,
                             stat.match['in_port'],stat.match['eth_dst'],
                             stat.instructions[0].actions[0].port,
                             stat.packet_count,stat.byte_count)
