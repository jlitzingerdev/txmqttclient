"""
Copyright 2018 Jason Litzinger
See LICENSE for details.
"""
from __future__ import absolute_import

import binascii

from twisted.internet import ssl, endpoints, reactor, protocol, task, defer
from twisted.logger import Logger
import mqttpacket.v311 as mqttpacket

defer.setDebugging(True)

_logMQTT = True


class MQTTClient(protocol.Protocol):
    """
    A client for an MQTT Broker.
    """
    log = Logger()

    def __init__(self, client_id):
        self.client_id = client_id
        self._incoming = bytearray()
        self._conn_d = defer.Deferred()

    def makeConnection(self, transport):
        """Connect this protocol to the broker."""
        self.log.info('Transport acquired, connect to broker')
        connpkt = mqttpacket.connect(self.client_id)
        transport.write(connpkt)

        def _on_broker_connect(_):
            protocol.Protocol.makeConnection(self, transport)

        def _on_error(failure):
            return failure

        self._conn_d.addCallbacks(_on_broker_connect, _on_error)

    def connectionMade(self):
        self.log.info("Protocol Connected")

    def connectionLost(self, reason=protocol.connectionDone):
        self.log.warn(
            "Connection dropped: {reason}",
            reason=reason.getErrorMessage()
        )

    def logPrefix(self):
        return "mqttclient"

    def _send_ping(self):
        msg = mqttpacket.pingreq()
        self.transport.write(msg)

    def dataReceived(self, data):
        if _logMQTT:
            self.log.info("Data: {bdata}", bdata=binascii.hexlify(data))
        self._incoming.extend(data)
        packets = []
        consumed = mqttpacket.parse(self._incoming, packets)
        if _logMQTT:
            self.log.info('Consumed {cons}', cons=consumed)

        for packet in packets:
            self.log.debug('Received packet {pkt}', pkt=packet)
            if packet.pkt_type == mqttpacket.MQTT_PACKET_CONNACK:
                if not self.connected:
                    self.connected = True
                    t = task.LoopingCall(self._send_ping)
                    t.start(20, now=False)
                    self._conn_d.callback(True)

        self._incoming = self._incoming[consumed:]

    def subscribe(self, topic):
        """Subscribe to the provided topicfilters

        :param topic: The topic to subscribe to.
        :type topic: text

        """
        tfs = [
            mqttpacket.SubscriptionSpec(topic, 0)
        ]
        subscription = mqttpacket.subscribe(1, tfs)
        if _logMQTT:
            self.log.info(binascii.hexlify(subscription))
        self.transport.write(subscription)


def connect_mqtt_tls(client_id, host, rootpath, port, client_creds=None):
    """Connect an MQTT Client over TLS without client auth.

    :param host: The hostname to connect
    :type host: str

    :param rootpath: Path to the root certificate
    :type rootpath: str

    :param port (optional): The port to use, default 8883
    :type port: int

    :param client_creds: Client cert/key pair
    :type client_creds: ssl.PrivateCertificate

    """
    with open(rootpath, 'rb') as rootf:
        rootblob = rootf.read()

    trust_root = ssl.trustRootFromCertificates(
        [ssl.Certificate.loadPEM(rootblob)]
    )

    tls_options = ssl.optionsForClientTLS(
        host,
        trustRoot=trust_root,
        clientCertificate=client_creds,
    )

    endpoint = endpoints.SSL4ClientEndpoint(
        reactor,
        host,
        port,
        tls_options
    )

    return endpoints.connectProtocol(
        endpoint,
        MQTTClient(client_id)
    )
